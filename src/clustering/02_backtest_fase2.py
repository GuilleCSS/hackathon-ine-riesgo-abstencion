"""Fase 2 · ¿Mejoran los grupos y las variables territoriales al modelo 2027?

Experimento aparte del pipeline: reutiliza las ventanas clean10 de la etapa 07,
sus métricas, el bootstrap por municipio de la etapa 08 y la misma regla de
selección de la etapa 09. No modifica `selected_architecture.json` ni ninguna
salida del modelo actual.

Toda variable de una fila con elección objetivo t se calcula sólo con
elecciones anteriores a t (incluidos los grupos, que se reconstruyen por t).

Uso: python src/clustering/02_backtest_fase2.py
"""
from pathlib import Path
import importlib.util
import json
import time
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[2]


def load_stage(name):
    # Reutiliza las definiciones exactas del pipeline (métricas y bootstrap).
    spec = importlib.util.spec_from_file_location(name, ROOT / "src" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S07 = load_stage("07_dual_history_backtest")
S08 = load_stage("08_robustness_model_selection")

MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
WINDOWS_DIR = ROOT / "data" / "processed" / "dual_history"
CARTO_DIR = ROOT / "data" / "raw" / "cartography_2027"
OUT_DATA = ROOT / "data" / "processed" / "clustering" / "fase2"
OUT_REPORT = ROOT / "reports" / "clustering" / "fase2"

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
INTERMEDIAS = {2009, 2015, 2021, 2027}
EXPERIMENTS = {
    "2021_temporal_dual": {"train": [2015, 2018], "test": 2021},
    "2024_temporal_dual": {"train": [2015, 2018, 2021], "test": 2024},
}
BASELINE = "baseline_same_family"
CURRENT = "two_history_linear"
RANDOM_STATE = 42

# Grupos: mismo método que la fase 1, rehecho por elección objetivo.
K = 5
TREND_PP = 5.0
LEVEL_PP = 5.0
NEIGHBOR_BUFFER_M = 5

TWO = ["SAME_PCT_ABSTENCION", "RECENT_PCT_ABSTENCION"]
HIST = ["H_NIVEL_MISMA", "H_NIVEL_OTRA", "H_TENDENCIA", "H_VOLATILIDAD"]
TERRITORY = ["NB_SAME_ABST", "NB_RECENT_ABST", "MPIO_SAME_ABST", "MPIO_RECENT_ABST", "LOG_DENSIDAD"]
CATS = ["H_GRUPO", "TIPO_ELECCION", "RECENT_TIPOSEC", "EDOCVE"]
BOOST_NUM = TWO + HIST + TERRITORY + [
    "SAME_PCT_NS_LN", "RECENT_PCT_NS_LN", "RECENT_LOG1P_LN", "RECENT_EDAD_PROM_LN",
    "RECENT_PROP_LN_18_24", "RECENT_PROP_LN_60_plus", "DELTA_RECENT_MINUS_SAME_ABST",
]

# Hiperparámetros fijados antes de evaluar (sin ajustar con los años de prueba).
HGB_PARAMS = dict(learning_rate=0.05, max_iter=400, max_leaf_nodes=31,
                  min_samples_leaf=50, l2_regularization=2.0, random_state=RANDOM_STATE)
XGB_PARAMS = dict(n_estimators=500, learning_rate=0.05, max_depth=6, subsample=0.8,
                  colsample_bytree=0.8, min_child_weight=20, reg_lambda=2.0,
                  tree_method="hist", random_state=RANDOM_STATE, n_jobs=-1)
XGB_RESIDUAL_PARAMS = dict(XGB_PARAMS, n_estimators=300, learning_rate=0.03, max_depth=4)


def family(year):
    return "intermedia" if year in INTERMEDIAS else "presidencial"


# ---------------------------------------------------------------- variables

def relative_abstention(master):
    totals = master.groupby("AELEC")[["SV", "NV"]].sum()
    national = totals["NV"] / (totals["SV"] + totals["NV"])
    rel = master.assign(REL=master["PCT_ABSTENCION"] - master["AELEC"].map(national))
    return rel.pivot(index="SECTION_KEY", columns="AELEC", values="REL")


def name_group(c):
    if c["H_TENDENCIA"] * 100 > TREND_PP:
        return "Empeorando"
    if c["H_TENDENCIA"] * 100 < -TREND_PP:
        return "Mejorando"
    level = (c["H_NIVEL_MISMA"] + c["H_NIVEL_OTRA"]) / 2 * 100
    if level > LEVEL_PP:
        return "Abstención alta persistente"
    if level < -LEVEL_PP:
        return "Abstención baja persistente"
    return "En el promedio"


def history_features(rel, target):
    """Trayectoria frente al promedio nacional usando sólo elecciones < target."""
    prior = [y for y in YEARS if y < target]
    same = [y for y in prior if family(y) == family(target)]
    other = [y for y in prior if family(y) != family(target)]
    half = len(prior) // 2
    r = rel[prior]
    feats = pd.DataFrame({
        "H_NIVEL_MISMA": rel[same].mean(axis=1),
        "H_NIVEL_OTRA": rel[other].mean(axis=1),
        # Mitad reciente menos mitad antigua de las elecciones previas.
        "H_TENDENCIA": rel[prior[-half:]].mean(axis=1) - rel[prior[:half]].mean(axis=1),
        "H_VOLATILIDAD": r.sub(r.mean(axis=1), axis=0).abs().mean(axis=1),
    })
    feats = feats.loc[feats[["H_NIVEL_MISMA", "H_NIVEL_OTRA"]].notna().all(axis=1)]

    filled = feats.fillna(feats.median())
    km = KMeans(K, n_init=10, random_state=RANDOM_STATE).fit(StandardScaler().fit_transform(filled))
    centroids = filled.groupby(km.labels_).mean()
    names = {c: name_group(row) for c, row in centroids.iterrows()}
    feats["H_GRUPO"] = pd.Series(km.labels_, index=feats.index).map(names)
    feats["TARGET_YEAR"] = target
    return feats.reset_index().rename(columns={"index": "SECTION_KEY"})


def read_sections():
    parts = []
    for z in sorted(CARTO_DIR.glob("*.zip")):
        e = z.stem.split("_")[1].zfill(2)
        inner = next(n for n in zipfile.ZipFile(z).namelist() if n.endswith("SECCION.shp"))
        g = pyogrio.read_dataframe(f"/vsizip/{z}/{inner}", columns=["entidad", "seccion"])
        g = g.to_crs(epsg=6372)
        g["SECTION_KEY"] = g["entidad"].astype(int).astype(str).str.zfill(2) + "-" + g["seccion"].astype(int).astype(str).str.zfill(4)
        parts.append(g[["SECTION_KEY", "geometry"]])
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:6372")


def neighbors_and_area():
    cache = OUT_DATA / "section_neighbors.parquet"
    area_cache = OUT_DATA / "section_area.parquet"
    if cache.exists() and area_cache.exists():
        return pd.read_parquet(cache), pd.read_parquet(area_cache)
    sec = read_sections()
    area = pd.DataFrame({"SECTION_KEY": sec["SECTION_KEY"], "AREA_KM2": sec.area / 1e6})
    buffered = sec.copy()
    buffered["geometry"] = sec.buffer(NEIGHBOR_BUFFER_M)
    pairs = gpd.sjoin(sec, buffered, predicate="intersects")
    pairs = pairs.loc[pairs["SECTION_KEY_left"] != pairs["SECTION_KEY_right"],
                      ["SECTION_KEY_left", "SECTION_KEY_right"]]
    pairs.columns = ["SECTION_KEY", "NEIGHBOR"]
    pairs = pairs.drop_duplicates()
    pairs.to_parquet(cache, index=False)
    area.to_parquet(area_cache, index=False)
    return pairs, area


def territory_features(master, pairs, area):
    abst = master.pivot(index="SECTION_KEY", columns="AELEC", values="PCT_ABSTENCION")
    nb = {}
    for y in YEARS:
        m = pairs.merge(abst[y].rename("v"), left_on="NEIGHBOR", right_index=True, how="left")
        nb[y] = m.groupby("SECTION_KEY")["v"].mean()
    mun = master.groupby(["AELEC", "EDOCVE", "MPIOCVE"])[["SV", "NV"]].sum()
    mun = (mun["NV"] / (mun["SV"] + mun["NV"])).rename("MPIO_ABST").reset_index()
    return nb, mun, area.set_index("SECTION_KEY")["AREA_KM2"]


def enrich(window, hist, nb, mun, area):
    w = window.merge(hist, on=["SECTION_KEY", "TARGET_YEAR"], how="left")
    w["NB_SAME_ABST"] = [nb[y].get(k, np.nan) for k, y in zip(w["SECTION_KEY"], w["SAME_YEAR"])]
    w["NB_RECENT_ABST"] = [nb[y].get(k, np.nan) for k, y in zip(w["SECTION_KEY"], w["RECENT_YEAR"])]
    for prefix in ["SAME", "RECENT"]:
        w = w.merge(
            mun.rename(columns={"AELEC": f"{prefix}_YEAR", "MPIOCVE": f"{prefix}_MPIOCVE", "MPIO_ABST": f"MPIO_{prefix}_ABST"}),
            on=[f"{prefix}_YEAR", "EDOCVE", f"{prefix}_MPIOCVE"], how="left",
        )
    w["LOG_DENSIDAD"] = np.log1p(w["RECENT_LN"] / w["SECTION_KEY"].map(area))
    w["H_GRUPO"] = w["H_GRUPO"].fillna("Sin grupo")
    return w


# ---------------------------------------------------------------- modelos

def preprocessor(num, cats, scale):
    steps = [("imputer", SimpleImputer(strategy="median"))] + ([("scale", StandardScaler())] if scale else [])
    parts = [("num", Pipeline(steps), num)]
    if cats:
        parts.append(("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False, drop=None), cats))
    return ColumnTransformer(parts, remainder="drop")


def tree_preprocessor(num, cats):
    # Árboles: sin imputar (manejan NaN) y categorías en one-hot.
    return ColumnTransformer(
        [("num", "passthrough", num),
         ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cats)],
        remainder="drop",
    )


def prepare(df, num, cats):
    x = df[num + cats].copy()
    for c in num:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    for c in cats:
        x[c] = x[c].astype(str)
    # Vecinos sin dato (sección sin polígono 2025): se usa la propia sección.
    if "NB_SAME_ABST" in x:
        x["NB_SAME_ABST"] = x["NB_SAME_ABST"].fillna(x["SAME_PCT_ABSTENCION"])
        x["NB_RECENT_ABST"] = x["NB_RECENT_ABST"].fillna(x["RECENT_PCT_ABSTENCION"])
    return x


def fit_predict(name, train, test):
    y = train["Y_ABSTENCION"].to_numpy(float)
    importance = None
    if name == BASELINE:
        return np.clip(test["SAME_PCT_ABSTENCION"].to_numpy(float), 0, 1), None
    if name == CURRENT:
        model = LinearRegression().fit(prepare(train, TWO, []), y)
        return np.clip(model.predict(prepare(test, TWO, [])), 0, 1), None
    if name == "linear_grupo":
        num, cats = TWO, ["H_GRUPO"]
        model = Pipeline([("prep", ColumnTransformer([("num", "passthrough", num), ("cat", OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False), cats)])),
                          ("lr", LinearRegression())])
        model.fit(prepare(train, num, cats), y)
        return np.clip(model.predict(prepare(test, num, cats)), 0, 1), None
    if name == "linear_por_grupo":
        pred = np.full(len(test), np.nan)
        glob = LinearRegression().fit(prepare(train, TWO, []), y)
        for g, idx in test.groupby("H_GRUPO").indices.items():
            tr = train["H_GRUPO"].eq(g).to_numpy()
            model = LinearRegression().fit(prepare(train.loc[tr], TWO, []), y[tr]) if tr.sum() >= 500 else glob
            pred[idx] = model.predict(prepare(test.iloc[idx], TWO, []))
        return np.clip(pred, 0, 1), None
    if name == "linear_vecinos":
        num = TWO + ["NB_SAME_ABST", "NB_RECENT_ABST"]
        model = LinearRegression().fit(prepare(train, num, []), y)
        return np.clip(model.predict(prepare(test, num, [])), 0, 1), None
    if name == "linear_contexto":
        num, cats = TWO + HIST + TERRITORY, ["H_GRUPO"]
        model = Pipeline([("prep", preprocessor(num, cats, scale=True)), ("ridge", Ridge(alpha=1.0))])
        model.fit(prepare(train, num, cats), y)
        return np.clip(model.predict(prepare(test, num, cats)), 0, 1), None
    if name in ("hgb_fase2", "xgb_fase2", "xgb_residual_fase2"):
        num, cats = BOOST_NUM, CATS
        prep = tree_preprocessor(num, cats)
        x_train = prep.fit_transform(prepare(train, num, cats))
        x_test = prep.transform(prepare(test, num, cats))
        features = list(prep.get_feature_names_out())
        if name == "hgb_fase2":
            model = HistGradientBoostingRegressor(**HGB_PARAMS).fit(x_train, y)
            return np.clip(model.predict(x_test), 0, 1), None
        if name == "xgb_fase2":
            model = XGBRegressor(**XGB_PARAMS).fit(x_train, y)
            pred = model.predict(x_test)
        else:
            # XGBoost sobre el residuo del modelo actual: corrige, no reemplaza.
            lin = LinearRegression().fit(prepare(train, TWO, []), y)
            base_train = lin.predict(prepare(train, TWO, []))
            model = XGBRegressor(**XGB_RESIDUAL_PARAMS).fit(x_train, y - base_train)
            pred = lin.predict(prepare(test, TWO, [])) + model.predict(x_test)
        gain = model.get_booster().get_score(importance_type="gain")
        importance = pd.DataFrame({
            "feature": features,
            "gain": [gain.get(f"f{i}", 0.0) for i in range(len(features))],
        })
        return np.clip(pred, 0, 1), importance
    raise ValueError(name)


MODELS = [BASELINE, CURRENT, "linear_grupo", "linear_por_grupo", "linear_vecinos",
          "linear_contexto", "hgb_fase2", "xgb_fase2", "xgb_residual_fase2"]

MODEL_NOTES = {
    BASELINE: "Repite la abstención de la última elección del mismo tipo (línea base de la regla).",
    CURRENT: "Modelo actual: regresión lineal con las dos historias.",
    "linear_grupo": "Modelo actual + ajuste fijo por grupo de trayectoria.",
    "linear_por_grupo": "Una regresión de dos historias por grupo de trayectoria.",
    "linear_vecinos": "Modelo actual + abstención de las secciones vecinas en ambas historias.",
    "linear_contexto": "Ridge con dos historias, trayectoria, grupo, vecinos, municipio y densidad.",
    "hgb_fase2": "HistGradientBoosting con todas las variables.",
    "xgb_fase2": "XGBoost con todas las variables.",
    "xgb_residual_fase2": "Modelo actual + XGBoost que corrige su residuo con todas las variables.",
}


def main():
    print("\n=== Clustering · Fase 2: backtest de variables territoriales ===")
    for p in [MASTER_PATH, CARTO_DIR]:
        if not p.exists():
            raise FileNotFoundError(f"No existe {p}. Corre el pipeline hasta la etapa 07.")
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)

    master = pd.read_csv(
        MASTER_PATH,
        usecols=["AELEC", "SECTION_KEY", "EDOCVE", "MPIOCVE", "SV", "NV", "PCT_ABSTENCION"],
        low_memory=False,
    )
    rel = relative_abstention(master)
    print("Vecinos y área desde la cartografía DIC-2025...")
    pairs, area = neighbors_and_area()
    nb, mun, area_s = territory_features(master, pairs, area)
    print(f"  {pairs['SECTION_KEY'].nunique():,} secciones con vecinos · mediana "
          f"{pairs.groupby('SECTION_KEY').size().median():.0f} vecinos")

    windows = {}
    for t in [2015, 2018, 2021, 2024]:
        w = pd.read_parquet(WINDOWS_DIR / f"dual_history_target_{t}_clean10.parquet")
        windows[t] = enrich(w, history_features(rel, t), nb, mun, area_s)
        print(f"  ventana {t}: {len(w):,} secciones · grupos: "
              + ", ".join(f"{k} {v:,}" for k, v in windows[t]["H_GRUPO"].value_counts().items()))

    results, boots, importances, candidates = [], [], [], []
    for exp, cfg in EXPERIMENTS.items():
        train = pd.concat([windows[t] for t in cfg["train"]], ignore_index=True)
        test = windows[cfg["test"]].reset_index(drop=True)
        print(f"\n{exp}: train {len(train):,} · test {len(test):,}")
        frame = test[["SECTION_KEY", "EDOCVE", "TGT_MPIOCVE", "Y_ABSTENCION", "H_GRUPO"]].copy()
        for name in MODELS:
            t0 = time.perf_counter()
            pred, imp = fit_predict(name, train, test)
            frame[f"PRED_{name}"] = pred
            m = S07.metrics(test["Y_ABSTENCION"], pred)
            results.append({"experiment": exp, "model": name, **m,
                            "fit_seconds": round(time.perf_counter() - t0, 1), "note": MODEL_NOTES[name]})
            print(f"  {name:<22} MAE {m['mae_pp']:.3f} pp · Top20 {m['top20_overlap']:.3f} · sesgo {m['bias_pp']:+.2f}")
            if imp is not None:
                importances.append(imp.assign(experiment=exp, model=name))
        frame.to_parquet(OUT_DATA / f"predictions_{exp}.parquet", index=False)

        for name in MODELS[1:]:
            for ref in [BASELINE, CURRENT]:
                if name == ref:
                    continue
                b = S08.cluster_bootstrap(frame, f"PRED_{name}", f"PRED_{ref}")
                lo, med, hi = S08.qci(b["delta_mae_vs_same_family_pp"])
                boots.append({"experiment": exp, "model": name, "reference": ref,
                              "delta_mae_pp_ci_low": lo, "delta_mae_pp_median": med,
                              "delta_mae_pp_ci_high": hi, "improvement_supported_95pct": bool(hi < 0)})

    res = pd.DataFrame(results)
    boot = pd.DataFrame(boots)
    res.to_csv(OUT_REPORT / "01_model_comparison.csv", index=False)
    boot.to_csv(OUT_REPORT / "02_bootstrap.csv", index=False)
    if importances:
        imp = pd.concat(importances)
        imp["gain_share"] = imp["gain"] / imp.groupby(["experiment", "model"])["gain"].transform("sum")
        imp.sort_values(["experiment", "model", "gain_share"], ascending=[True, True, False]).to_csv(
            OUT_REPORT / "04_xgb_feature_importance.csv", index=False)

    # Misma regla que la etapa 09.
    base = res.loc[res["model"].eq(BASELINE), ["experiment", "mae_pp"]].rename(columns={"mae_pp": "baseline_mae_pp"})
    cur = res.loc[res["model"].eq(CURRENT), ["experiment", "mae_pp"]].rename(columns={"mae_pp": "current_mae_pp"})
    ev = res.merge(base, on="experiment").merge(cur, on="experiment")
    ev["mae_ratio_vs_baseline"] = ev["mae_pp"] / ev["baseline_mae_pp"]
    sup = boot.pivot_table(index=["experiment", "model"], columns="reference",
                           values="improvement_supported_95pct", aggfunc="first").reset_index()
    ev = ev.merge(sup, on=["experiment", "model"], how="left")
    for model, g in ev.groupby("model", sort=False):
        candidates.append({
            "model": model,
            "nota": MODEL_NOTES[model],
            "mae_2021_pp": g.loc[g["experiment"].str.startswith("2021"), "mae_pp"].iloc[0],
            "mae_2024_pp": g.loc[g["experiment"].str.startswith("2024"), "mae_pp"].iloc[0],
            "improved_mae_both_years": bool((g["mae_pp"] < g["baseline_mae_pp"]).all()),
            "bootstrap_vs_baseline_both_years": bool(g[BASELINE].eq(True).all()) if BASELINE in g else False,
            "eligible_primary": model != BASELINE and bool((g["mae_pp"] < g["baseline_mae_pp"]).all())
                                and bool(g.get(BASELINE, pd.Series(False)).eq(True).all()),
            "max_mae_ratio_vs_baseline": g["mae_ratio_vs_baseline"].max(),
            "mean_mae_ratio_vs_baseline": g["mae_ratio_vs_baseline"].mean(),
            "mean_top20": g["top20_overlap"].mean(),
            "beats_current_both_years": bool((g["mae_pp"] < g["current_mae_pp"]).all()) and model != CURRENT,
            "bootstrap_vs_current_both_years": bool(g[CURRENT].eq(True).all()) if CURRENT in g and model != CURRENT else False,
        })
    cand = pd.DataFrame(candidates).sort_values(
        ["eligible_primary", "max_mae_ratio_vs_baseline", "mean_mae_ratio_vs_baseline", "mean_top20"],
        ascending=[False, True, True, False],
    )
    cand.to_csv(OUT_REPORT / "03_candidate_summary.csv", index=False)

    manifest = pd.DataFrame([
        {"variable": "SAME_PCT_ABSTENCION / RECENT_PCT_ABSTENCION", "calculo": "Abstención en la elección del mismo tipo y en la más reciente (ventanas de la etapa 07).", "antes_del_objetivo": True},
        {"variable": "H_NIVEL_MISMA / H_NIVEL_OTRA", "calculo": "Abstención frente al promedio nacional, promedio de las elecciones previas del mismo tipo / del otro tipo.", "antes_del_objetivo": True},
        {"variable": "H_TENDENCIA", "calculo": "Mitad reciente menos mitad antigua de las elecciones previas (frente al promedio nacional).", "antes_del_objetivo": True},
        {"variable": "H_VOLATILIDAD", "calculo": "Desviación media de las elecciones previas frente al promedio de la sección.", "antes_del_objetivo": True},
        {"variable": "H_GRUPO", "calculo": "k-means (k=5) sobre las 4 variables H_*, rehecho para cada elección objetivo con su historia previa.", "antes_del_objetivo": True},
        {"variable": "NB_SAME_ABST / NB_RECENT_ABST", "calculo": "Promedio de abstención de las secciones colindantes (cartografía DIC-2025) en cada historia.", "antes_del_objetivo": True},
        {"variable": "MPIO_SAME_ABST / MPIO_RECENT_ABST", "calculo": "Abstención agregada del municipio en cada historia.", "antes_del_objetivo": True},
        {"variable": "LOG_DENSIDAD", "calculo": "log(1 + lista nominal reciente / km² de la sección en DIC-2025).", "antes_del_objetivo": True},
    ])
    manifest.to_csv(OUT_REPORT / "05_feature_manifest.csv", index=False)

    write_report(res, boot, cand)
    print("\nResumen (regla de la etapa 09):")
    print(cand[["model", "mae_2021_pp", "mae_2024_pp", "eligible_primary", "beats_current_both_years",
                "bootstrap_vs_current_both_years"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\nReportes: {OUT_REPORT.relative_to(ROOT)}")


def write_report(res, boot, cand):
    cur = res.loc[res["model"].eq(CURRENT)].set_index("experiment")["mae_pp"]
    rows = []
    for r in cand.itertuples():
        g = boot.loc[boot["model"].eq(r.model) & boot["reference"].eq(CURRENT)]
        ci = "; ".join(f"{e[:4]}: [{a:+.2f}, {b:+.2f}]" for e, a, b in zip(g["experiment"], g["delta_mae_pp_ci_low"], g["delta_mae_pp_ci_high"])) or "—"
        rows.append(f"| `{r.model}` | {r.mae_2021_pp:.2f} | {r.mae_2024_pp:.2f} | "
                    f"{'sí' if r.eligible_primary else 'no'} | {'sí' if r.beats_current_both_years else 'no'} | {ci} |")
    winners = cand.loc[cand["eligible_primary"]]
    best = winners.iloc[0]["model"] if len(winners) else BASELINE
    better = cand.loc[cand["beats_current_both_years"] & cand["bootstrap_vs_current_both_years"], "model"].tolist()
    verdict = (
        f"Con la regla de la etapa 09, el mejor candidato es `{best}`. "
        + ("Ningún modelo nuevo mejora al actual de forma robusta en ambos años."
           if not better else
           f"Mejoran al modelo actual de forma robusta en 2021 y 2024: {', '.join(f'`{m}`' for m in better)}.")
    )
    text = f"""# Fase 2 · ¿Mejoran los grupos y las variables territoriales al modelo?

Generado por `src/clustering/02_backtest_fase2.py`. Experimento aparte: no cambia
`reports/model_selection/selected_architecture.json` ni las salidas del modelo actual.

## Protocolo

- Mismas ventanas `clean10` de la etapa 07: se predice 2021 entrenando con 2015 y
  2018, y 2024 entrenando con 2015, 2018 y 2021.
- Mismas métricas (etapa 07), bootstrap por municipio con 400 réplicas (etapa 08)
  y regla de selección (etapa 09): mejorar a la línea base en ambos años con IC95%
  de ΔMAE completamente bajo cero; gana el menor cociente de MAE en el peor año.
- Sin fuga de información: cada variable de una fila con objetivo t usa sólo
  elecciones anteriores a t; los grupos se reconstruyen para cada t.
- Hiperparámetros fijados antes de evaluar.

Modelo actual (`two_history_linear`): MAE 2021 = {cur.iloc[0]:.2f} pp, 2024 = {cur.iloc[1]:.2f} pp.

## Resultados

| Modelo | MAE 2021 (pp) | MAE 2024 (pp) | Elegible (regla 09) | Mejor que el actual en ambos años | IC95% ΔMAE vs. actual (pp) |
|---|---|---|---|---|---|
{chr(10).join(rows)}

ΔMAE negativo = el modelo se equivoca menos que el actual.

## Conclusión

{verdict}

## Archivos

- `01_model_comparison.csv`: métricas por modelo y año.
- `02_bootstrap.csv`: IC95% de ΔMAE frente a la línea base y al modelo actual.
- `03_candidate_summary.csv`: aplicación de la regla de selección.
- `04_xgb_feature_importance.csv`: importancia (gain) de las variables en XGBoost.
- `05_feature_manifest.csv`: cómo se calcula cada variable nueva.

## Limitaciones

- Vecinos y densidad usan la cartografía DIC-2025 también para 2015–2021.
- Sólo hay 2 años de prueba; una mejora pequeña puede no repetirse en 2027.
- Faltan variables externas (elecciones locales concurrentes, censo).
"""
    (OUT_REPORT / "FASE2_REPORT.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
