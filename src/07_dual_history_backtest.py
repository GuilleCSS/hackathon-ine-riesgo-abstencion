from pathlib import Path
import gc
import time

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"

OUT_DATA = ROOT / "data" / "processed" / "dual_history"
OUT_REPORT = ROOT / "reports" / "dual_history"
OUT_PRED = OUT_REPORT / "predictions"

OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)
OUT_PRED.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42

# Cada target usa:
# - SAME: la elección comparable de la misma familia, seis años antes.
# - RECENT: la elección federal más reciente, tres años antes.
WINDOWS = {
    2015: {"same": 2009, "recent": 2012, "type": "intermedia"},
    2018: {"same": 2012, "recent": 2015, "type": "presidencial"},
    2021: {"same": 2015, "recent": 2018, "type": "intermedia"},
    2024: {"same": 2018, "recent": 2021, "type": "presidencial"},
}

BASE_FEATURES = [
    "PCT_ABSTENCION",
    "PCT_NS_LN",
    "LN",
    "EDAD_PROM_LN",
    "PROP_LN_H",
    "PROP_LN_M",
    "PROP_LN_18_24",
    "PROP_LN_25_34",
    "PROP_LN_35_44",
    "PROP_LN_45_59",
    "PROP_LN_60_plus",
    "PCT_ABST_H",
    "PCT_ABST_M",
    "PCT_ABST_18_24",
    "PCT_ABST_25_34",
    "PCT_ABST_35_44",
    "PCT_ABST_45_59",
    "PCT_ABST_60_plus",
    "BRECHA_PART_MENOS_H",
]

ID_COLS = [
    "EDOCVE",
    "EDONOM",
    "MPIOCVE",
    "MPIONOM",
    "SECCION",
    "TIPOSEC",
]

CATEGORICAL = [
    "EDOCVE",
    "TIPO_ELECCION",
    "SAME_TIPOSEC",
    "RECENT_TIPOSEC",
]


def top_overlap(y_true, y_pred, fraction):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    k = max(1, int(np.ceil(len(y_true) * fraction)))
    actual_idx = np.argpartition(y_true, -k)[-k:]
    pred_idx = np.argpartition(y_pred, -k)[-k:]
    return len(np.intersect1d(actual_idx, pred_idx)) / k


def metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    pearson = np.corrcoef(y_true, y_pred)[0, 1]
    spearman = pd.Series(y_true).corr(pd.Series(y_pred), method="spearman")
    bias = np.mean(y_pred - y_true)

    return {
        "n": int(len(y_true)),
        "mae_pp": float(mae * 100),
        "rmse_pp": float(rmse * 100),
        "r2": float(r2),
        "pearson_r": float(pearson),
        "spearman_r": float(spearman),
        "top20_overlap": float(top_overlap(y_true, y_pred, 0.20)),
        "top10_overlap": float(top_overlap(y_true, y_pred, 0.10)),
        "bias_pp": float(bias * 100),
    }


def build_window(master, target_year):
    cfg = WINDOWS[target_year]
    same_year = cfg["same"]
    recent_year = cfg["recent"]

    same = master.loc[
        master["AELEC"].eq(same_year),
        ID_COLS + BASE_FEATURES
    ].copy()

    recent = master.loc[
        master["AELEC"].eq(recent_year),
        ID_COLS + BASE_FEATURES
    ].copy()

    target = master.loc[
        master["AELEC"].eq(target_year),
        ID_COLS + ["PCT_ABSTENCION", "PCT_NS_LN"]
    ].copy()

    # Llave territorial básica.
    for d in [same, recent, target]:
        d["SECTION_KEY"] = (
            d["EDOCVE"].astype("Int64").astype(str).str.zfill(2)
            + "-"
            + d["SECCION"].astype("Int64").astype(str).str.zfill(4)
        )

    same = same.rename(columns={
        "EDONOM": "SAME_EDONOM",
        "MPIOCVE": "SAME_MPIOCVE",
        "MPIONOM": "SAME_MPIONOM",
        "SECCION": "SAME_SECCION",
        "TIPOSEC": "SAME_TIPOSEC",
        **{c: f"SAME_{c}" for c in BASE_FEATURES},
    })

    recent = recent.rename(columns={
        "EDONOM": "RECENT_EDONOM",
        "MPIOCVE": "RECENT_MPIOCVE",
        "MPIONOM": "RECENT_MPIONOM",
        "SECCION": "RECENT_SECCION",
        "TIPOSEC": "RECENT_TIPOSEC",
        **{c: f"RECENT_{c}" for c in BASE_FEATURES},
    })

    target = target.rename(columns={
        "EDONOM": "TGT_EDONOM",
        "MPIOCVE": "TGT_MPIOCVE",
        "MPIONOM": "TGT_MPIONOM",
        "SECCION": "TGT_SECCION",
        "TIPOSEC": "TGT_TIPOSEC",
        "PCT_ABSTENCION": "Y_ABSTENCION",
        "PCT_NS_LN": "TGT_PCT_NS_LN",
    })

    window = (
        same
        .merge(
            recent,
            on=["EDOCVE", "SECTION_KEY"],
            how="inner",
            validate="one_to_one",
        )
        .merge(
            target,
            on=["EDOCVE", "SECTION_KEY"],
            how="inner",
            validate="one_to_one",
        )
    )

    window.insert(0, "TARGET_YEAR", target_year)
    window.insert(1, "SAME_YEAR", same_year)
    window.insert(2, "RECENT_YEAR", recent_year)
    window.insert(3, "TIPO_ELECCION", cfg["type"])

    # Estabilidad territorial entre las tres observaciones.
    window["STABLE_MPIO_3Y"] = (
        window["SAME_MPIOCVE"].eq(window["RECENT_MPIOCVE"])
        & window["RECENT_MPIOCVE"].eq(window["TGT_MPIOCVE"])
    )

    window["STABLE_TIPOSEC_3Y"] = (
        window["SAME_TIPOSEC"].eq(window["RECENT_TIPOSEC"])
        & window["RECENT_TIPOSEC"].eq(window["TGT_TIPOSEC"])
    )

    # Filtro de calidad principal: los inputs y el target evaluable tienen NS <= 10%.
    # El NS del target sólo se usa para decidir si el ground truth es confiable;
    # nunca entra como predictor.
    window["ELIGIBLE_CLEAN10"] = (
        window["STABLE_MPIO_3Y"]
        & window["STABLE_TIPOSEC_3Y"]
        & window["SAME_PCT_ABSTENCION"].notna()
        & window["RECENT_PCT_ABSTENCION"].notna()
        & window["Y_ABSTENCION"].notna()
        & window["SAME_PCT_NS_LN"].le(0.10)
        & window["RECENT_PCT_NS_LN"].le(0.10)
        & window["TGT_PCT_NS_LN"].le(0.10)
    )

    # Features derivadas conocidas antes de la elección objetivo.
    window["SAME_LOG1P_LN"] = np.log1p(
        pd.to_numeric(window["SAME_LN"], errors="coerce").clip(lower=0)
    )
    window["RECENT_LOG1P_LN"] = np.log1p(
        pd.to_numeric(window["RECENT_LN"], errors="coerce").clip(lower=0)
    )

    window["DELTA_RECENT_MINUS_SAME_ABST"] = (
        window["RECENT_PCT_ABSTENCION"] - window["SAME_PCT_ABSTENCION"]
    )

    window["DELTA_RECENT_MINUS_SAME_LOG_LN"] = (
        window["RECENT_LOG1P_LN"] - window["SAME_LOG1P_LN"]
    )

    window["DELTA_RECENT_MINUS_SAME_EDAD"] = (
        window["RECENT_EDAD_PROM_LN"] - window["SAME_EDAD_PROM_LN"]
    )

    for group in ["18_24", "25_34", "35_44", "45_59", "60_plus"]:
        window[f"DELTA_RECENT_MINUS_SAME_PROP_{group}"] = (
            window[f"RECENT_PROP_LN_{group}"]
            - window[f"SAME_PROP_LN_{group}"]
        )

    return window


def enriched_features():
    cols = [
        "EDOCVE",
        "TIPO_ELECCION",
        "SAME_TIPOSEC",
        "RECENT_TIPOSEC",
        "SAME_LOG1P_LN",
        "RECENT_LOG1P_LN",
        "DELTA_RECENT_MINUS_SAME_ABST",
        "DELTA_RECENT_MINUS_SAME_LOG_LN",
        "DELTA_RECENT_MINUS_SAME_EDAD",
        "DELTA_RECENT_MINUS_SAME_PROP_18_24",
        "DELTA_RECENT_MINUS_SAME_PROP_25_34",
        "DELTA_RECENT_MINUS_SAME_PROP_35_44",
        "DELTA_RECENT_MINUS_SAME_PROP_45_59",
        "DELTA_RECENT_MINUS_SAME_PROP_60_plus",
    ]

    # Añadimos las características históricas de ambas elecciones previas.
    for prefix in ["SAME_", "RECENT_"]:
        for c in BASE_FEATURES:
            if c == "LN":
                continue
            cols.append(prefix + c)

    # Deduplicar conservando orden.
    return list(dict.fromkeys(cols))


def two_history_features():
    # Modelo deliberadamente simple e interpretable:
    # sólo usa las dos tasas históricas de abstención.
    return [
        "SAME_PCT_ABSTENCION",
        "RECENT_PCT_ABSTENCION",
    ]


def prepare_x(df, features):
    x = df[features].copy()

    for c in features:
        if c in CATEGORICAL:
            x[c] = x[c].astype("string").fillna("MISSING").astype(str)
        else:
            x[c] = pd.to_numeric(x[c], errors="coerce")

    return x


def make_preprocessor(features, scale):
    categorical = [c for c in features if c in CATEGORICAL]
    numeric = [c for c in features if c not in categorical]

    num_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scale", StandardScaler()))

    transformers = [
        ("num", Pipeline(num_steps), numeric),
    ]

    if categorical:
        transformers.append(
            (
                "cat",
                Pipeline([
                    (
                        "onehot",
                        OneHotEncoder(
                            handle_unknown="ignore",
                            sparse_output=False,
                        ),
                    )
                ]),
                categorical,
            )
        )

    return ColumnTransformer(transformers, remainder="drop")


def learn_blend_alpha(train, objective="rmse"):
    # alpha=1 -> sólo same-family
    # alpha=0 -> sólo elección reciente
    y = train["Y_ABSTENCION"].to_numpy(float)
    same = train["SAME_PCT_ABSTENCION"].to_numpy(float)
    recent = train["RECENT_PCT_ABSTENCION"].to_numpy(float)

    best_alpha = None
    best_value = np.inf

    for alpha in np.linspace(0, 1, 101):
        pred = alpha * same + (1 - alpha) * recent

        if objective == "mae":
            value = mean_absolute_error(y, pred)
        else:
            value = np.sqrt(mean_squared_error(y, pred))

        if value < best_value:
            best_value = value
            best_alpha = float(alpha)

    return best_alpha, float(best_value)


def add_result(rows, experiment, model, y_true, y_pred, fit_seconds=0.0, note=""):
    rows.append({
        "experiment": experiment,
        "model": model,
        **metrics(y_true, y_pred),
        "fit_seconds": float(fit_seconds),
        "note": note,
    })


def run_experiment(name, train, test, results, prediction_frames, alpha_rows):
    print("\n" + "=" * 78)
    print(f"Experimento: {name}")
    print("=" * 78)
    print(f"Train: {len(train):,}")
    print(f"Test : {len(test):,}")

    y_train = train["Y_ABSTENCION"].to_numpy(float)
    y_test = test["Y_ABSTENCION"].to_numpy(float)

    same_test = test["SAME_PCT_ABSTENCION"].to_numpy(float)
    recent_test = test["RECENT_PCT_ABSTENCION"].to_numpy(float)

    pred_frame = pd.DataFrame({
        "SECTION_KEY": test["SECTION_KEY"].astype(str),
        "EDOCVE": test["EDOCVE"],
        "TGT_EDONOM": test["TGT_EDONOM"],
        "TGT_MPIOCVE": test["TGT_MPIOCVE"],
        "TGT_MPIONOM": test["TGT_MPIONOM"],
        "TGT_SECCION": test["TGT_SECCION"],
        "TARGET_YEAR": test["TARGET_YEAR"],
        "TIPO_ELECCION": test["TIPO_ELECCION"],
        "Y_ABSTENCION": y_test,
    })

    # --------------------------------------------------------------
    # Baselines transparentes
    # --------------------------------------------------------------
    pred_same = np.clip(same_test, 0, 1)
    add_result(
        results, name, "baseline_same_family",
        y_test, pred_same,
        note="Usa la abstención de la última elección de la misma familia."
    )
    pred_frame["PRED_baseline_same_family"] = pred_same

    pred_recent = np.clip(recent_test, 0, 1)
    add_result(
        results, name, "baseline_recent_election",
        y_test, pred_recent,
        note="Usa la abstención de la elección federal más reciente."
    )
    pred_frame["PRED_baseline_recent_election"] = pred_recent

    pred_equal = np.clip((same_test + recent_test) / 2.0, 0, 1)
    add_result(
        results, name, "baseline_equal_blend",
        y_test, pred_equal,
        note="Promedio simple 50/50 de ambas historias."
    )
    pred_frame["PRED_baseline_equal_blend"] = pred_equal

    # Peso aprendido únicamente con train.
    alpha_rmse, train_rmse = learn_blend_alpha(train, objective="rmse")
    pred_weighted = np.clip(
        alpha_rmse * same_test + (1 - alpha_rmse) * recent_test,
        0, 1,
    )
    add_result(
        results, name, "baseline_weighted_blend",
        y_test, pred_weighted,
        note=f"Peso alpha={alpha_rmse:.2f} aprendido sólo con train minimizando RMSE."
    )
    pred_frame["PRED_baseline_weighted_blend"] = pred_weighted

    alpha_rows.append({
        "experiment": name,
        "alpha_same_family": alpha_rmse,
        "weight_recent": 1 - alpha_rmse,
        "train_rmse": train_rmse,
    })

    # --------------------------------------------------------------
    # Modelo lineal interpretable con las dos abstenciones previas.
    # --------------------------------------------------------------
    simple_features = two_history_features()
    x_train_simple = prepare_x(train, simple_features)
    x_test_simple = prepare_x(test, simple_features)

    simple_model = Pipeline([
        ("prep", make_preprocessor(simple_features, scale=False)),
        ("model", LinearRegression()),
    ])

    t0 = time.perf_counter()
    simple_model.fit(x_train_simple, y_train)
    fit_sec = time.perf_counter() - t0
    pred_simple = np.clip(simple_model.predict(x_test_simple), 0, 1)

    add_result(
        results, name, "two_history_linear",
        y_test, pred_simple, fit_seconds=fit_sec,
        note="Regresión lineal con abstención de la elección same-family y de la elección reciente."
    )
    pred_frame["PRED_two_history_linear"] = pred_simple

    # --------------------------------------------------------------
    # Modelo enriquecido para comprobar si la sociodemografía histórica
    # añade valor real sobre las dos tasas de abstención.
    # --------------------------------------------------------------
    rich_features = enriched_features()
    x_train_rich = prepare_x(train, rich_features)
    x_test_rich = prepare_x(test, rich_features)

    ridge = Pipeline([
        ("prep", make_preprocessor(rich_features, scale=True)),
        ("model", Ridge(alpha=2.0)),
    ])

    t0 = time.perf_counter()
    ridge.fit(x_train_rich, y_train)
    fit_sec = time.perf_counter() - t0
    pred_ridge = np.clip(ridge.predict(x_test_rich), 0, 1)

    m = metrics(y_test, pred_ridge)
    print(
        f"\nDual-history Ridge: MAE={m['mae_pp']:.3f} pp · "
        f"R²={m['r2']:.4f} · Top20={m['top20_overlap']:.3f}"
    )

    add_result(
        results, name, "dual_history_ridge",
        y_test, pred_ridge, fit_seconds=fit_sec
    )
    pred_frame["PRED_dual_history_ridge"] = pred_ridge

    hgb = Pipeline([
        ("prep", make_preprocessor(rich_features, scale=False)),
        (
            "model",
            HistGradientBoostingRegressor(
                learning_rate=0.05,
                max_iter=250,
                max_leaf_nodes=31,
                min_samples_leaf=25,
                l2_regularization=2.0,
                random_state=RANDOM_STATE,
            ),
        ),
    ])

    t0 = time.perf_counter()
    hgb.fit(x_train_rich, y_train)
    fit_sec = time.perf_counter() - t0
    pred_hgb = np.clip(hgb.predict(x_test_rich), 0, 1)

    m = metrics(y_test, pred_hgb)
    print(
        f"Dual-history HGB:   MAE={m['mae_pp']:.3f} pp · "
        f"R²={m['r2']:.4f} · Top20={m['top20_overlap']:.3f}"
    )

    add_result(
        results, name, "dual_history_hgb",
        y_test, pred_hgb, fit_seconds=fit_sec
    )
    pred_frame["PRED_dual_history_hgb"] = pred_hgb

    prediction_frames[name] = pred_frame

    del (
        x_train_simple, x_test_simple,
        x_train_rich, x_test_rich,
        simple_model, ridge, hgb
    )
    gc.collect()


def main():
    print("\n=== 07 · Backtesting de doble historia electoral ===")

    if not MASTER_PATH.exists():
        raise FileNotFoundError(
            f"No existe {MASTER_PATH}. Ejecuta primero 02_build_master.py"
        )

    master = pd.read_csv(MASTER_PATH, low_memory=False)

    windows = {}
    summary_rows = []

    for target_year in WINDOWS:
        w = build_window(master, target_year)
        windows[target_year] = w

        clean = w.loc[w["ELIGIBLE_CLEAN10"]].copy()
        clean.to_parquet(
            OUT_DATA / f"dual_history_target_{target_year}_clean10.parquet",
            index=False,
        )

        summary_rows.append({
            "target_year": target_year,
            "same_year": WINDOWS[target_year]["same"],
            "recent_year": WINDOWS[target_year]["recent"],
            "tipo_eleccion": WINDOWS[target_year]["type"],
            "pairs_total": len(w),
            "eligible_clean10": int(w["ELIGIBLE_CLEAN10"].sum()),
        })

        print(
            f"{WINDOWS[target_year]['same']} + "
            f"{WINDOWS[target_year]['recent']} → {target_year}: "
            f"{len(w):,} parejas · "
            f"{int(w['ELIGIBLE_CLEAN10'].sum()):,} clean10"
        )

    pd.DataFrame(summary_rows).to_csv(
        OUT_REPORT / "dual_history_window_summary.csv",
        index=False,
    )

    clean = {
        y: windows[y].loc[windows[y]["ELIGIBLE_CLEAN10"]].copy()
        for y in windows
    }

    results = []
    pred_frames = {}
    alpha_rows = []

    # 2021: sólo se entrena con targets anteriores.
    train_2021 = pd.concat([clean[2015], clean[2018]], ignore_index=True)
    test_2021 = clean[2021]

    run_experiment(
        "2021_temporal_dual",
        train_2021,
        test_2021,
        results,
        pred_frames,
        alpha_rows,
    )

    # 2021 misma familia: sólo 2015.
    run_experiment(
        "2021_same_family_dual",
        clean[2015],
        test_2021,
        results,
        pred_frames,
        alpha_rows,
    )

    # 2024: se entrena con todos los targets anteriores.
    train_2024 = pd.concat(
        [clean[2015], clean[2018], clean[2021]],
        ignore_index=True,
    )
    test_2024 = clean[2024]

    run_experiment(
        "2024_temporal_dual",
        train_2024,
        test_2024,
        results,
        pred_frames,
        alpha_rows,
    )

    # 2024 misma familia: sólo 2018.
    run_experiment(
        "2024_same_family_dual",
        clean[2018],
        test_2024,
        results,
        pred_frames,
        alpha_rows,
    )

    for name, pred in pred_frames.items():
        pred.to_parquet(
            OUT_PRED / f"predictions_{name}.parquet",
            index=False,
        )

    results_df = pd.DataFrame(results)
    results_df.to_csv(
        OUT_REPORT / "dual_history_model_comparison.csv",
        index=False,
    )

    compact_cols = [
        "experiment",
        "model",
        "n",
        "mae_pp",
        "rmse_pp",
        "r2",
        "pearson_r",
        "spearman_r",
        "top20_overlap",
        "top10_overlap",
        "bias_pp",
        "fit_seconds",
    ]

    compact = results_df[compact_cols].copy()
    compact.to_csv(
        OUT_REPORT / "dual_history_model_comparison_compact.csv",
        index=False,
    )

    pd.DataFrame(alpha_rows).to_csv(
        OUT_REPORT / "blend_weights.csv",
        index=False,
    )

    # Manifiesto anti-leakage.
    manifest_rows = []
    for c in enriched_features():
        manifest_rows.append({
            "column": c,
            "role": "feature",
            "available_before_target": True,
        })

    manifest_rows.extend([
        {
            "column": "Y_ABSTENCION",
            "role": "target",
            "available_before_target": False,
        },
        {
            "column": "TGT_PCT_NS_LN",
            "role": "evaluation_quality_only",
            "available_before_target": False,
        },
    ])

    pd.DataFrame(manifest_rows).to_csv(
        OUT_REPORT / "dual_history_feature_manifest.csv",
        index=False,
    )

    print("\n" + "=" * 78)
    print("=== Dual-history terminado ===")
    print("=" * 78)

    print(
        compact.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nPesos aprendidos para el blend:")
    print(
        pd.DataFrame(alpha_rows).to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nArchivos principales:")
    print("  - reports/dual_history/dual_history_model_comparison_compact.csv")
    print("  - reports/dual_history/blend_weights.csv")
    print("  - reports/dual_history/predictions/*.parquet")


if __name__ == "__main__":
    main()
