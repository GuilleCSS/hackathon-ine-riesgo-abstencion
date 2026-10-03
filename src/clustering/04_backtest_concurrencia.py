"""Fase 3 · ¿Mejora el modelo con el calendario de elecciones locales concurrentes?

Mismo protocolo que la fase 2 (ventanas clean10 de la etapa 07, métricas,
bootstrap por municipio de la etapa 08 y regla de selección de la etapa 09) y
mismas variables territoriales; agrega si hubo elección local y gubernatura el
mismo día en la elección objetivo y en las dos historias. El calendario se fija
por ley antes de cada elección, así que no hay fuga de información.

Requiere: data/external/calendario_concurrente.csv
(src/clustering/03_build_calendario_concurrente.py).

Uso: python src/clustering/04_backtest_concurrencia.py
"""
from pathlib import Path
import importlib.util
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fase2", ROOT / "src" / "clustering" / "02_backtest_fase2.py")
F2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F2)

CALENDAR_PATH = ROOT / "data" / "external" / "calendario_concurrente.csv"
OUT_DATA = ROOT / "data" / "processed" / "clustering" / "fase3"
OUT_REPORT = ROOT / "reports" / "clustering" / "fase3"

BASELINE, CURRENT = F2.BASELINE, F2.CURRENT
CONC = [f"{kind}_{when}" for kind in ["LOCAL", "GOB"] for when in ["TGT", "SAME", "RECENT"]]

MODELS = [BASELINE, CURRENT, "linear_concurrencia", "linear_concurrencia_vecinos",
          "xgb_concurrencia", "xgb_concurrencia_sin_estado"]
MODEL_NOTES = {
    BASELINE: F2.MODEL_NOTES[BASELINE],
    CURRENT: F2.MODEL_NOTES[CURRENT],
    "linear_concurrencia": "Modelo actual + elección local y gubernatura concurrentes (objetivo y dos historias).",
    "linear_concurrencia_vecinos": "Lo anterior + abstención de las secciones vecinas.",
    "xgb_concurrencia": "XGBoost de la fase 2 + concurrencia.",
    "xgb_concurrencia_sin_estado": "XGBoost de la fase 2 + concurrencia, sin la clave de estado (para que no memorice estados).",
}


def add_calendar(w, cal):
    w = w.copy()
    for when, col in [("TGT", "TARGET_YEAR"), ("SAME", "SAME_YEAR"), ("RECENT", "RECENT_YEAR")]:
        c = cal.rename(columns={"ANIO": col, "LOCAL_CONCURRENTE": f"LOCAL_{when}", "GUBERNATURA_CONCURRENTE": f"GOB_{when}"})
        w = w.merge(c[[col, "EDOCVE", f"LOCAL_{when}", f"GOB_{when}"]], on=[col, "EDOCVE"], how="left")
    if w[CONC].isna().any().any():
        raise RuntimeError("Hay estado-año sin dato en el calendario.")
    return w


def fit_predict(name, train, test):
    if name in (BASELINE, CURRENT):
        return F2.fit_predict(name, train, test)
    y = train["Y_ABSTENCION"].to_numpy(float)
    if name.startswith("linear"):
        num = F2.TWO + CONC + (["NB_SAME_ABST", "NB_RECENT_ABST"] if name.endswith("vecinos") else [])
        model = LinearRegression().fit(F2.prepare(train, num, []), y)
        return np.clip(model.predict(F2.prepare(test, num, [])), 0, 1), None
    cats = [c for c in F2.CATS if not (name.endswith("sin_estado") and c == "EDOCVE")]
    num = F2.BOOST_NUM + CONC
    prep = F2.tree_preprocessor(num, cats)
    x_train = prep.fit_transform(F2.prepare(train, num, cats))
    x_test = prep.transform(F2.prepare(test, num, cats))
    model = XGBRegressor(**F2.XGB_PARAMS).fit(x_train, y)
    gain = model.get_booster().get_score(importance_type="gain")
    names = list(prep.get_feature_names_out())
    imp = pd.DataFrame({"feature": names, "gain": [gain.get(f"f{i}", 0.0) for i in range(len(names))]})
    return np.clip(model.predict(x_test), 0, 1), imp


def concurrency_effect(master, cal):
    # Descriptivo: abstención agregada por año según hubo gubernatura concurrente.
    st = master.groupby(["AELEC", "EDOCVE"])[["SV", "NV"]].sum().reset_index()
    st = st.merge(cal.rename(columns={"ANIO": "AELEC"}), on=["AELEC", "EDOCVE"])
    rows = []
    for (year, gob), g in st.groupby(["AELEC", "GUBERNATURA_CONCURRENTE"]):
        rows.append({"anio": year, "gubernatura_concurrente": int(gob), "estados": len(g),
                     "abstencion": g["NV"].sum() / (g["SV"].sum() + g["NV"].sum())})
    return pd.DataFrame(rows)


def main():
    print("\n=== Clustering · Fase 3: elecciones locales concurrentes ===")
    if not CALENDAR_PATH.exists():
        raise FileNotFoundError(f"No existe {CALENDAR_PATH}. Corre 03_build_calendario_concurrente.py")
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)
    cal = pd.read_csv(CALENDAR_PATH)

    master = pd.read_csv(
        F2.MASTER_PATH,
        usecols=["AELEC", "SECTION_KEY", "EDOCVE", "MPIOCVE", "SV", "NV", "PCT_ABSTENCION"],
        low_memory=False,
    )
    effect = concurrency_effect(master, cal)
    effect.to_csv(OUT_REPORT / "00_abstencion_por_concurrencia.csv", index=False)

    rel = F2.relative_abstention(master)
    pairs, area = F2.neighbors_and_area()
    nb, mun, area_s = F2.territory_features(master, pairs, area)
    windows = {}
    for t in [2015, 2018, 2021, 2024]:
        w = pd.read_parquet(F2.WINDOWS_DIR / f"dual_history_target_{t}_clean10.parquet")
        windows[t] = add_calendar(F2.enrich(w, F2.history_features(rel, t), nb, mun, area_s), cal)

    results, boots, importances = [], [], []
    for exp, cfg in F2.EXPERIMENTS.items():
        train = pd.concat([windows[t] for t in cfg["train"]], ignore_index=True)
        test = windows[cfg["test"]].reset_index(drop=True)
        print(f"\n{exp}: train {len(train):,} · test {len(test):,} · "
              f"estados con gubernatura en el objetivo: {test.loc[test['GOB_TGT'].eq(1), 'EDOCVE'].nunique()}")
        frame = test[["SECTION_KEY", "EDOCVE", "TGT_MPIOCVE", "Y_ABSTENCION", "GOB_TGT"]].copy()
        for name in MODELS:
            t0 = time.perf_counter()
            pred, imp = fit_predict(name, train, test)
            frame[f"PRED_{name}"] = pred
            m = F2.S07.metrics(test["Y_ABSTENCION"], pred)
            results.append({"experiment": exp, "model": name, **m,
                            "fit_seconds": round(time.perf_counter() - t0, 1), "note": MODEL_NOTES[name]})
            print(f"  {name:<28} MAE {m['mae_pp']:.3f} pp · Top20 {m['top20_overlap']:.3f} · sesgo {m['bias_pp']:+.2f}")
            if imp is not None:
                importances.append(imp.assign(experiment=exp, model=name))
        frame.to_parquet(OUT_DATA / f"predictions_{exp}.parquet", index=False)
        for name in MODELS[1:]:
            for ref in [BASELINE, CURRENT]:
                if name == ref:
                    continue
                b = F2.S08.cluster_bootstrap(frame, f"PRED_{name}", f"PRED_{ref}")
                lo, med, hi = F2.S08.qci(b["delta_mae_vs_same_family_pp"])
                boots.append({"experiment": exp, "model": name, "reference": ref,
                              "delta_mae_pp_ci_low": lo, "delta_mae_pp_median": med,
                              "delta_mae_pp_ci_high": hi, "improvement_supported_95pct": bool(hi < 0)})

    res, boot = pd.DataFrame(results), pd.DataFrame(boots)
    res.to_csv(OUT_REPORT / "01_model_comparison.csv", index=False)
    boot.to_csv(OUT_REPORT / "02_bootstrap.csv", index=False)
    imp = pd.concat(importances)
    imp["gain_share"] = imp["gain"] / imp.groupby(["experiment", "model"])["gain"].transform("sum")
    imp.sort_values(["experiment", "model", "gain_share"], ascending=[True, True, False]).to_csv(
        OUT_REPORT / "04_xgb_feature_importance.csv", index=False)

    base = res.loc[res["model"].eq(BASELINE), ["experiment", "mae_pp"]].rename(columns={"mae_pp": "baseline_mae_pp"})
    cur = res.loc[res["model"].eq(CURRENT), ["experiment", "mae_pp"]].rename(columns={"mae_pp": "current_mae_pp"})
    sup = boot.pivot_table(index=["experiment", "model"], columns="reference",
                           values="improvement_supported_95pct", aggfunc="first").reset_index()
    ev = res.merge(base, on="experiment").merge(cur, on="experiment").merge(sup, on=["experiment", "model"], how="left")
    ev["mae_ratio_vs_baseline"] = ev["mae_pp"] / ev["baseline_mae_pp"]
    cand = []
    for model, g in ev.groupby("model", sort=False):
        vs_base = bool(g[BASELINE].eq(True).all()) if BASELINE in g else False
        cand.append({
            "model": model, "nota": MODEL_NOTES[model],
            "mae_2021_pp": g.loc[g["experiment"].str.startswith("2021"), "mae_pp"].iloc[0],
            "mae_2024_pp": g.loc[g["experiment"].str.startswith("2024"), "mae_pp"].iloc[0],
            "eligible_primary": model != BASELINE and bool((g["mae_pp"] < g["baseline_mae_pp"]).all()) and vs_base,
            "max_mae_ratio_vs_baseline": g["mae_ratio_vs_baseline"].max(),
            "mean_mae_ratio_vs_baseline": g["mae_ratio_vs_baseline"].mean(),
            "mean_top20": g["top20_overlap"].mean(),
            "beats_current_both_years": model != CURRENT and bool((g["mae_pp"] < g["current_mae_pp"]).all()),
            "bootstrap_vs_current_both_years": model != CURRENT and CURRENT in g and bool(g[CURRENT].eq(True).all()),
        })
    cand = pd.DataFrame(cand).sort_values(
        ["eligible_primary", "max_mae_ratio_vs_baseline", "mean_mae_ratio_vs_baseline", "mean_top20"],
        ascending=[False, True, True, False])
    cand.to_csv(OUT_REPORT / "03_candidate_summary.csv", index=False)
    write_report(res, boot, cand, effect, imp)
    print("\nResumen (regla de la etapa 09):")
    print(cand[["model", "mae_2021_pp", "mae_2024_pp", "eligible_primary", "beats_current_both_years",
                "bootstrap_vs_current_both_years"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"\nReportes: {OUT_REPORT.relative_to(ROOT)}")


def write_report(res, boot, cand, effect, imp):
    cur = res.loc[res["model"].eq(CURRENT)].set_index("experiment")
    bias = res.pivot(index="model", columns="experiment", values="bias_pp")
    rows = []
    for r in cand.itertuples():
        g = boot.loc[boot["model"].eq(r.model) & boot["reference"].eq(CURRENT)]
        ci = "; ".join(f"{e[:4]}: [{a:+.2f}, {b:+.2f}]" for e, a, b in
                       zip(g["experiment"], g["delta_mae_pp_ci_low"], g["delta_mae_pp_ci_high"])) or "—"
        rows.append(f"| `{r.model}` | {r.mae_2021_pp:.2f} | {r.mae_2024_pp:.2f} | "
                    f"{bias.loc[r.model].iloc[0]:+.2f} / {bias.loc[r.model].iloc[1]:+.2f} | "
                    f"{'sí' if r.eligible_primary else 'no'} | {ci} |")
    eff = effect.pivot(index="anio", columns="gubernatura_concurrente", values="abstencion")
    eff_rows = "\n".join(
        f"| {y} | {eff.loc[y].get(1, float('nan')):.1%} | {eff.loc[y].get(0, float('nan')):.1%} |" for y in eff.index)
    conc_imp = (imp.loc[imp["model"].eq("xgb_concurrencia") & imp["feature"].str.contains("LOCAL_|GOB_")]
                .groupby("experiment")["gain_share"].sum())
    better = cand.loc[cand["beats_current_both_years"] & cand["bootstrap_vs_current_both_years"], "model"].tolist()
    winners = cand.loc[cand["eligible_primary"]]
    best = winners.iloc[0]["model"] if len(winners) else BASELINE
    verdict = (f"Con la regla de la etapa 09, el mejor candidato es `{best}`. "
               + ("Ningún modelo con concurrencia mejora al actual de forma robusta en ambos años."
                  if not better else
                  f"Mejoran al modelo actual de forma robusta en 2021 y 2024: {', '.join(f'`{m}`' for m in better)}."))
    text = f"""# Fase 3 · Elecciones locales concurrentes

Generado por `src/clustering/04_backtest_concurrencia.py`. Experimento aparte: no
cambia `selected_architecture.json` ni las salidas del modelo actual.

## Datos

`data/external/calendario_concurrente.csv` (de `03_build_calendario_concurrente.py`,
fuente Wikipedia, **pendiente de validar** contra INE y OPLEs): para cada estado y
elección federal 2009–2027, si hubo elección local y gubernatura el mismo día.

Variables nuevas por fila: `LOCAL_*` y `GOB_*` para la elección objetivo (`TGT`),
la historia del mismo tipo (`SAME`) y la reciente (`RECENT`). El calendario se fija
por ley antes de cada elección: no hay fuga de información.

Abstención agregada por año según hubo gubernatura concurrente:

| Año | Con gubernatura | Sin gubernatura |
|---|---|---|
{eff_rows}

## Resultados (mismo protocolo que la fase 2)

Modelo actual: MAE 2021 = {cur.loc['2021_temporal_dual', 'mae_pp']:.2f} pp, 2024 = {cur.loc['2024_temporal_dual', 'mae_pp']:.2f} pp.

| Modelo | MAE 2021 (pp) | MAE 2024 (pp) | Sesgo 2021 / 2024 (pp) | Elegible (regla 09) | IC95% ΔMAE vs. actual (pp) |
|---|---|---|---|---|---|
{chr(10).join(rows)}

ΔMAE negativo = el modelo se equivoca menos que el actual. Peso de las variables de
concurrencia en `xgb_concurrencia` (gain): {', '.join(f"{e[:4]}: {v:.1%}" for e, v in conc_imp.items())}.

## Conclusión

{verdict}

## Limitaciones

- En 2021 y 2024 los 32 estados tuvieron elección local: en los años de prueba sólo
  varía la gubernatura (15 y 9 estados), y la variable local sólo varía en la historia.
- 32 estados × 4 ventanas de entrenamiento: poca variación para aprender el efecto.
- El calendario no distingue qué cargos locales (congreso, ayuntamientos) ni su
  competitividad.
"""
    (OUT_REPORT / "FASE3_REPORT.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
