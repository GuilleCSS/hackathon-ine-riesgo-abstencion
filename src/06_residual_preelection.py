from pathlib import Path
import gc
import time

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
MODEL_DIR = ROOT / "data" / "processed" / "modeling"
OUT = ROOT / "reports" / "backtesting_residual"
PRED_OUT = OUT / "predictions"

OUT.mkdir(parents=True, exist_ok=True)
PRED_OUT.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42

EXPERIMENTS = [
    {
        "name": "2021_temporal_all",
        "train": "backtest_2021_train_clean10.parquet",
        "test": "backtest_2021_test_clean10.parquet",
    },
    {
        "name": "2021_same_family",
        "train": "backtest_2021_family_train_clean10.parquet",
        "test": "backtest_2021_test_clean10.parquet",
    },
    {
        "name": "2024_temporal_all",
        "train": "backtest_2024_train_clean10.parquet",
        "test": "backtest_2024_test_clean10.parquet",
    },
    {
        "name": "2024_same_family",
        "train": "backtest_2024_family_train_clean10.parquet",
        "test": "backtest_2024_test_clean10.parquet",
    },
]

# Variables de la elección objetivo que dependen exclusivamente de lista nominal /
# composición registral, no del comportamiento de votación.
TARGET_PRE_ELECTION_COLS = [
    "LN",
    "EDAD_PROM_LN",
    "PROP_LN_H",
    "PROP_LN_M",
    "PROP_LN_18_24",
    "PROP_LN_25_34",
    "PROP_LN_35_44",
    "PROP_LN_45_59",
    "PROP_LN_60_plus",
]

SOURCE_BASE_COLS = [
    "SRC_PCT_ABSTENCION",
    "SRC_PCT_NS_LN",
    "SRC_EDAD_PROM_LN",
    "SRC_PROP_LN_H",
    "SRC_PROP_LN_M",
    "SRC_PROP_LN_18_24",
    "SRC_PROP_LN_25_34",
    "SRC_PROP_LN_35_44",
    "SRC_PROP_LN_45_59",
    "SRC_PROP_LN_60_plus",
    "SRC_PCT_ABST_H",
    "SRC_PCT_ABST_M",
    "SRC_PCT_ABST_18_24",
    "SRC_PCT_ABST_25_34",
    "SRC_PCT_ABST_35_44",
    "SRC_PCT_ABST_45_59",
    "SRC_PCT_ABST_60_plus",
    "SRC_BRECHA_PART_MENOS_H",
]

CATEGORICAL = [
    "EDOCVE",
    "TIPOSEC_TGT_PRE",
    "TIPO_ELECCION",
]


def metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    if len(y_true) == 0:
        return {
            "n": 0, "mae_pp": np.nan, "rmse_pp": np.nan,
            "r2": np.nan, "pearson_r": np.nan, "spearman_r": np.nan,
            "bias_pp": np.nan, "top20_overlap": np.nan, "top10_overlap": np.nan,
        }

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    pearson = np.corrcoef(y_true, y_pred)[0, 1] if len(y_true) > 1 else np.nan
    spearman = pd.Series(y_true).corr(pd.Series(y_pred), method="spearman")
    bias = np.mean(y_pred - y_true)

    def overlap(frac):
        n = len(y_true)
        k = max(1, int(np.ceil(n * frac)))
        a = np.argpartition(y_true, -k)[-k:]
        p = np.argpartition(y_pred, -k)[-k:]
        return len(np.intersect1d(a, p)) / k

    return {
        "n": int(len(y_true)),
        "mae_pp": float(mae * 100),
        "rmse_pp": float(rmse * 100),
        "r2": float(r2),
        "pearson_r": float(pearson),
        "spearman_r": float(spearman),
        "bias_pp": float(bias * 100),
        "top20_overlap": float(overlap(0.20)),
        "top10_overlap": float(overlap(0.10)),
    }


def attach_target_preelection_features(split, master):
    # Conservamos sólo variables basadas en lista nominal/composición
    # de la elección objetivo y el tipo de sección.
    cols = [
        "AELEC", "EDOCVE", "SECCION", "TIPOSEC",
        *TARGET_PRE_ELECTION_COLS,
    ]
    tgt = master[cols].copy()

    rename = {
        "TIPOSEC": "TIPOSEC_TGT_PRE",
        "LN": "TGT_PRE_LN",
        "EDAD_PROM_LN": "TGT_PRE_EDAD_PROM_LN",
        "PROP_LN_H": "TGT_PRE_PROP_LN_H",
        "PROP_LN_M": "TGT_PRE_PROP_LN_M",
        "PROP_LN_18_24": "TGT_PRE_PROP_LN_18_24",
        "PROP_LN_25_34": "TGT_PRE_PROP_LN_25_34",
        "PROP_LN_35_44": "TGT_PRE_PROP_LN_35_44",
        "PROP_LN_45_59": "TGT_PRE_PROP_LN_45_59",
        "PROP_LN_60_plus": "TGT_PRE_PROP_LN_60_plus",
    }
    tgt = tgt.rename(columns=rename)

    out = split.merge(
        tgt,
        left_on=["TARGET_YEAR", "EDOCVE", "SECCION"],
        right_on=["AELEC", "EDOCVE", "SECCION"],
        how="left",
        validate="many_to_one",
    ).drop(columns=["AELEC"])

    out["TGT_PRE_LOG1P_LN"] = np.log1p(
        pd.to_numeric(out["TGT_PRE_LN"], errors="coerce").clip(lower=0)
    )

    # Cambios registrales entre la elección previa y la elección objetivo.
    out["DELTA_LOG_LN_PRE"] = (
        out["TGT_PRE_LOG1P_LN"] - out["SRC_LOG1P_LN"]
    )

    out["DELTA_EDAD_PROM_LN_PRE"] = (
        out["TGT_PRE_EDAD_PROM_LN"] - out["SRC_EDAD_PROM_LN"]
    )

    for group in ["18_24", "25_34", "35_44", "45_59", "60_plus"]:
        out[f"DELTA_PROP_LN_{group}_PRE"] = (
            out[f"TGT_PRE_PROP_LN_{group}"]
            - out[f"SRC_PROP_LN_{group}"]
        )

    out["DELTA_PROP_LN_H_PRE"] = (
        out["TGT_PRE_PROP_LN_H"] - out["SRC_PROP_LN_H"]
    )
    out["DELTA_PROP_LN_M_PRE"] = (
        out["TGT_PRE_PROP_LN_M"] - out["SRC_PROP_LN_M"]
    )

    return out


def feature_columns():
    return [
        "EDOCVE",
        "TIPOSEC_TGT_PRE",
        "TIPO_ELECCION",
        *SOURCE_BASE_COLS,
        "SRC_LOG1P_LN",
        "TGT_PRE_LOG1P_LN",
        "TGT_PRE_EDAD_PROM_LN",
        "TGT_PRE_PROP_LN_H",
        "TGT_PRE_PROP_LN_M",
        "TGT_PRE_PROP_LN_18_24",
        "TGT_PRE_PROP_LN_25_34",
        "TGT_PRE_PROP_LN_35_44",
        "TGT_PRE_PROP_LN_45_59",
        "TGT_PRE_PROP_LN_60_plus",
        "DELTA_LOG_LN_PRE",
        "DELTA_EDAD_PROM_LN_PRE",
        "DELTA_PROP_LN_H_PRE",
        "DELTA_PROP_LN_M_PRE",
        "DELTA_PROP_LN_18_24_PRE",
        "DELTA_PROP_LN_25_34_PRE",
        "DELTA_PROP_LN_35_44_PRE",
        "DELTA_PROP_LN_45_59_PRE",
        "DELTA_PROP_LN_60_plus_PRE",
    ]


def prepare_x(df, features):
    x = df[features].copy()
    for col in CATEGORICAL:
        x[col] = x[col].astype("string").fillna("MISSING").astype(str)

    for col in features:
        if col not in CATEGORICAL:
            x[col] = pd.to_numeric(x[col], errors="coerce")
    return x


def preprocess(features, scale=False):
    num = [c for c in features if c not in CATEGORICAL]
    cat = [c for c in CATEGORICAL if c in features]

    num_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scaler", StandardScaler()))

    return ColumnTransformer([
        ("num", Pipeline(num_steps), num),
        (
            "cat",
            Pipeline([
                (
                    "onehot",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                )
            ]),
            cat,
        ),
    ])


def models(features):
    return {
        "residual_ridge": Pipeline([
            ("prep", preprocess(features, scale=True)),
            ("model", Ridge(alpha=2.0)),
        ]),
        "residual_random_forest": Pipeline([
            ("prep", preprocess(features, scale=False)),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=140,
                    max_depth=16,
                    min_samples_leaf=10,
                    max_features=0.65,
                    n_jobs=-1,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]),
        "residual_hist_gradient_boosting": Pipeline([
            ("prep", preprocess(features, scale=False)),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=0.04,
                    max_iter=300,
                    max_leaf_nodes=31,
                    min_samples_leaf=25,
                    l2_regularization=2.0,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]),
    }


def main():
    print("\n=== 06 · Residual modeling + variables preelectorales ===")

    if not MASTER_PATH.exists():
        raise FileNotFoundError(MASTER_PATH)

    master = pd.read_csv(MASTER_PATH, low_memory=False)
    features = feature_columns()

    # Comprobación anti-leakage por nombre.
    forbidden_tokens = ["Y_", "SV", "NV", "PCT_PARTICIPACION_TGT"]
    suspicious = [
        c for c in features
        if c.startswith("Y_")
        or c.startswith("TGT_PCT_")
        or c.startswith("TGT_SV")
        or c.startswith("TGT_NV")
    ]
    if suspicious:
        raise RuntimeError(f"Posible leakage en features: {suspicious}")

    (OUT / "residual_feature_columns.txt").write_text(
        "\n".join(features) + "\n",
        encoding="utf-8",
    )

    results = []

    for exp in EXPERIMENTS:
        print("\n" + "=" * 76)
        print(f"Experimento: {exp['name']}")
        print("=" * 76)

        train = pd.read_parquet(MODEL_DIR / exp["train"])
        test = pd.read_parquet(MODEL_DIR / exp["test"])

        train = attach_target_preelection_features(train, master)
        test = attach_target_preelection_features(test, master)

        print(f"Train: {len(train):,}")
        print(f"Test : {len(test):,}")

        # Target residual: cuánto cambia la abstención frente a la elección previa.
        y_train_delta = pd.to_numeric(
            train["Y_DELTA_ABSTENCION"], errors="coerce"
        ).to_numpy(float)

        y_test = pd.to_numeric(
            test["Y_ABSTENCION"], errors="coerce"
        ).to_numpy(float)

        source_test = pd.to_numeric(
            test["SRC_PCT_ABSTENCION"], errors="coerce"
        ).to_numpy(float)

        # Baseline persistencia
        pred_persist = np.clip(source_test, 0, 1)
        results.append({
            "experiment": exp["name"],
            "model": "baseline_persistence",
            **metrics(y_test, pred_persist),
            "fit_seconds": 0.0,
        })

        # Baseline cambio medio aprendido en train
        mean_delta = np.nanmean(y_train_delta)
        pred_mean_delta = np.clip(source_test + mean_delta, 0, 1)
        results.append({
            "experiment": exp["name"],
            "model": "baseline_mean_delta",
            **metrics(y_test, pred_mean_delta),
            "fit_seconds": 0.0,
        })

        x_train = prepare_x(train, features)
        x_test = prepare_x(test, features)

        pred_frame = pd.DataFrame({
            "SECTION_KEY": test["SECTION_KEY"].astype(str),
            "EDOCVE": test["EDOCVE"],
            "EDONOM": test["EDONOM"],
            "MPIOCVE_SRC": test["MPIOCVE_SRC"],
            "MPIONOM_SRC": test["MPIONOM_SRC"],
            "SECCION": test["SECCION"],
            "SOURCE_YEAR": test["SOURCE_YEAR"],
            "TARGET_YEAR": test["TARGET_YEAR"],
            "Y_ABSTENCION": y_test,
            "SRC_PCT_ABSTENCION": source_test,
            "PRED_baseline_persistence": pred_persist,
            "PRED_baseline_mean_delta": pred_mean_delta,
        })

        for model_name, model in models(features).items():
            print(f"\nEntrenando: {model_name}")
            t0 = time.perf_counter()
            model.fit(x_train, y_train_delta)
            fit_sec = time.perf_counter() - t0

            pred_delta = model.predict(x_test)
            pred = np.clip(source_test + pred_delta, 0, 1)

            m = metrics(y_test, pred)
            results.append({
                "experiment": exp["name"],
                "model": model_name,
                **m,
                "fit_seconds": fit_sec,
            })

            print(
                f"  MAE={m['mae_pp']:.3f} pp · "
                f"RMSE={m['rmse_pp']:.3f} pp · "
                f"R²={m['r2']:.4f} · "
                f"Spearman={m['spearman_r']:.4f} · "
                f"Top20={m['top20_overlap']:.3f} · "
                f"fit={fit_sec:.1f}s"
            )

            pred_frame[f"PRED_{model_name}"] = pred
            pred_frame[f"DELTA_{model_name}"] = pred_delta

            del model
            gc.collect()

        pred_frame.to_parquet(
            PRED_OUT / f"predictions_{exp['name']}.parquet",
            index=False,
        )

        del train, test, x_train, x_test, pred_frame
        gc.collect()

    results_df = pd.DataFrame(results)
    results_df.to_csv(OUT / "residual_model_comparison.csv", index=False)

    cols = [
        "experiment", "model", "n", "mae_pp", "rmse_pp", "r2",
        "pearson_r", "spearman_r", "top20_overlap", "top10_overlap",
        "bias_pp", "fit_seconds",
    ]
    compact = results_df[cols].copy()
    compact.to_csv(OUT / "residual_model_comparison_compact.csv", index=False)

    print("\n" + "=" * 76)
    print("=== Residual backtesting terminado ===")
    print("=" * 76)
    print(
        compact.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )
    print("\nArchivos:")
    print("  - reports/backtesting_residual/residual_model_comparison.csv")
    print("  - reports/backtesting_residual/residual_model_comparison_compact.csv")
    print("  - reports/backtesting_residual/residual_feature_columns.txt")
    print("  - reports/backtesting_residual/predictions/*.parquet")


if __name__ == "__main__":
    main()
