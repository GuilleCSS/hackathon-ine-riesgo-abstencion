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

MODEL_DATA = ROOT / "data" / "processed" / "modeling"
FEATURE_FILE = ROOT / "reports" / "modeling" / "model_feature_columns.txt"

OUT = ROOT / "reports" / "backtesting"
PRED_OUT = OUT / "predictions"
OUT.mkdir(parents=True, exist_ok=True)
PRED_OUT.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42

CATEGORICAL_FEATURES = [
    "EDOCVE",
    "TIPOSEC_SRC",
    "TIPO_ELECCION",
]

EXPERIMENTS = [
    {
        "name": "2021_temporal_all",
        "target_year": 2021,
        "train": "backtest_2021_train_clean10.parquet",
        "test": "backtest_2021_test_clean10.parquet",
    },
    {
        "name": "2021_same_family",
        "target_year": 2021,
        "train": "backtest_2021_family_train_clean10.parquet",
        "test": "backtest_2021_test_clean10.parquet",
    },
    {
        "name": "2024_temporal_all",
        "target_year": 2024,
        "train": "backtest_2024_train_clean10.parquet",
        "test": "backtest_2024_test_clean10.parquet",
    },
    {
        "name": "2024_same_family",
        "target_year": 2024,
        "train": "backtest_2024_family_train_clean10.parquet",
        "test": "backtest_2024_test_clean10.parquet",
    },
]


def load_feature_columns():
    if not FEATURE_FILE.exists():
        raise FileNotFoundError(
            f"No existe {FEATURE_FILE}. Ejecuta primero src/04_build_features.py"
        )

    features = [
        line.strip()
        for line in FEATURE_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    forbidden = [
        c for c in features
        if c.startswith("Y_") or c.startswith("TGT_")
    ]
    if forbidden:
        raise RuntimeError(
            "Se detectaron columnas objetivo entre las features: "
            + ", ".join(forbidden)
        )

    return features


def prepare_x(df, features):
    x = df[features].copy()

    for col in CATEGORICAL_FEATURES:
        if col in x.columns:
            x[col] = x[col].astype("string").fillna("MISSING").astype(str)

    for col in features:
        if col not in CATEGORICAL_FEATURES:
            x[col] = pd.to_numeric(x[col], errors="coerce")

    return x


def make_linear_preprocessor(features):
    numeric = [c for c in features if c not in CATEGORICAL_FEATURES]
    categorical = [c for c in CATEGORICAL_FEATURES if c in features]

    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_pipe = Pipeline([
        (
            "onehot",
            OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=False,
            ),
        ),
    ])

    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric),
            ("cat", categorical_pipe, categorical),
        ],
        remainder="drop",
    )


def make_tree_preprocessor(features):
    numeric = [c for c in features if c not in CATEGORICAL_FEATURES]
    categorical = [c for c in CATEGORICAL_FEATURES if c in features]

    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])

    categorical_pipe = Pipeline([
        (
            "onehot",
            OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=False,
            ),
        ),
    ])

    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, numeric),
            ("cat", categorical_pipe, categorical),
        ],
        remainder="drop",
    )


def make_models(features):
    return {
        "ridge": Pipeline([
            ("prep", make_linear_preprocessor(features)),
            ("model", Ridge(alpha=1.0)),
        ]),
        "random_forest": Pipeline([
            ("prep", make_tree_preprocessor(features)),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=140,
                    max_depth=18,
                    min_samples_leaf=8,
                    max_features=0.70,
                    n_jobs=-1,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("prep", make_tree_preprocessor(features)),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=0.05,
                    max_iter=250,
                    max_leaf_nodes=31,
                    min_samples_leaf=20,
                    l2_regularization=1.0,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]),
    }


def top_overlap(y_true, y_pred, fraction):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    n = len(y_true)
    if n == 0:
        return np.nan

    k = max(1, int(np.ceil(n * fraction)))

    actual_idx = np.argpartition(y_true, -k)[-k:]
    pred_idx = np.argpartition(y_pred, -k)[-k:]

    return len(np.intersect1d(actual_idx, pred_idx)) / k


def metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]

    if len(y_true) == 0:
        return {
            "n": 0,
            "mae": np.nan,
            "mae_pp": np.nan,
            "rmse": np.nan,
            "rmse_pp": np.nan,
            "r2": np.nan,
            "pearson_r": np.nan,
            "spearman_r": np.nan,
            "bias": np.nan,
            "bias_pp": np.nan,
            "top20_overlap": np.nan,
            "top10_overlap": np.nan,
        }

    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)

    pearson = (
        np.corrcoef(y_true, y_pred)[0, 1]
        if len(y_true) > 1
        else np.nan
    )

    spearman = (
        pd.Series(y_true).corr(pd.Series(y_pred), method="spearman")
        if len(y_true) > 1
        else np.nan
    )

    bias = np.mean(y_pred - y_true)

    return {
        "n": int(len(y_true)),
        "mae": float(mae),
        "mae_pp": float(mae * 100),
        "rmse": float(rmse),
        "rmse_pp": float(rmse * 100),
        "r2": float(r2),
        "pearson_r": float(pearson),
        "spearman_r": float(spearman),
        "bias": float(bias),
        "bias_pp": float(bias * 100),
        "top20_overlap": float(top_overlap(y_true, y_pred, 0.20)),
        "top10_overlap": float(top_overlap(y_true, y_pred, 0.10)),
    }


def family_shift_value(train, test):
    test_family = test["TIPO_ELECCION"].dropna().astype(str).unique()

    if len(test_family) == 1:
        same_family = train[
            train["TIPO_ELECCION"].astype(str).eq(test_family[0])
        ]
        if len(same_family) > 0:
            return float(same_family["Y_DELTA_ABSTENCION"].mean())

    return float(train["Y_DELTA_ABSTENCION"].mean())


def add_result(
    rows,
    experiment,
    train_scope,
    model_name,
    y_true,
    y_pred,
    fit_seconds=0.0,
    predict_seconds=0.0,
    note="",
):
    row = {
        "experiment": experiment,
        "train_scope": train_scope,
        "model": model_name,
        **metrics(y_true, y_pred),
        "fit_seconds": float(fit_seconds),
        "predict_seconds": float(predict_seconds),
        "note": note,
    }
    rows.append(row)


def main():
    print("\n=== 05 · Backtesting temporal de modelos ===")

    features = load_feature_columns()
    print(f"Features autorizadas: {len(features)}")

    print("Features categóricas:")
    for c in CATEGORICAL_FEATURES:
        print(f"  - {c}")

    results = []
    shift_rows = []

    for exp in EXPERIMENTS:
        name = exp["name"]
        train_path = MODEL_DATA / exp["train"]
        test_path = MODEL_DATA / exp["test"]

        if not train_path.exists():
            raise FileNotFoundError(f"No existe {train_path}")
        if not test_path.exists():
            raise FileNotFoundError(f"No existe {test_path}")

        print("\n" + "=" * 72)
        print(f"Experimento: {name}")
        print("=" * 72)

        train = pd.read_parquet(train_path)
        test = pd.read_parquet(test_path)

        print(f"Train: {len(train):,}")
        print(f"Test : {len(test):,}")

        missing_features = sorted(
            set(features) - set(train.columns)
        )
        if missing_features:
            raise RuntimeError(
                f"Faltan features en {train_path.name}: {missing_features}"
            )

        x_train = prepare_x(train, features)
        x_test = prepare_x(test, features)

        y_train = pd.to_numeric(
            train["Y_ABSTENCION"], errors="coerce"
        ).to_numpy(dtype=float)

        y_test = pd.to_numeric(
            test["Y_ABSTENCION"], errors="coerce"
        ).to_numpy(dtype=float)

        train_scope = (
            "same_family"
            if "same_family" in name
            else "temporal_all"
        )

        # ----------------------------------------------------------
        # Baseline 1: persistencia pura
        # ----------------------------------------------------------
        pred_persistence = pd.to_numeric(
            test["SRC_PCT_ABSTENCION"], errors="coerce"
        ).to_numpy(dtype=float)

        pred_persistence = np.clip(pred_persistence, 0, 1)

        add_result(
            results,
            name,
            train_scope,
            "baseline_persistence",
            y_test,
            pred_persistence,
            note="Predice la misma abstención observada en la elección comparable anterior.",
        )

        # ----------------------------------------------------------
        # Baseline 2: persistencia + cambio medio histórico
        # Se estima sólo con datos de entrenamiento.
        # ----------------------------------------------------------
        shift = family_shift_value(train, test)
        pred_shift = np.clip(pred_persistence + shift, 0, 1)

        shift_rows.append({
            "experiment": name,
            "train_scope": train_scope,
            "historical_mean_shift": shift,
            "historical_mean_shift_pp": shift * 100,
        })

        add_result(
            results,
            name,
            train_scope,
            "baseline_family_shift",
            y_test,
            pred_shift,
            note=(
                "Persistencia ajustada por el cambio medio histórico de la misma familia electoral "
                "estimado exclusivamente con el conjunto de entrenamiento."
            ),
        )

        # ----------------------------------------------------------
        # Modelos de ML
        # ----------------------------------------------------------
        models = make_models(features)
        predictions = pd.DataFrame({
            "SECTION_KEY": test["SECTION_KEY"].astype(str),
            "EDOCVE": test["EDOCVE"],
            "EDONOM": test["EDONOM"],
            "MPIOCVE_SRC": test["MPIOCVE_SRC"],
            "MPIONOM_SRC": test["MPIONOM_SRC"],
            "SECCION": test["SECCION"],
            "SOURCE_YEAR": test["SOURCE_YEAR"],
            "TARGET_YEAR": test["TARGET_YEAR"],
            "TIPO_ELECCION": test["TIPO_ELECCION"],
            "Y_ABSTENCION": y_test,
            "PRED_baseline_persistence": pred_persistence,
            "PRED_baseline_family_shift": pred_shift,
        })

        for model_name, model in models.items():
            print(f"\nEntrenando: {model_name}")

            t0 = time.perf_counter()
            model.fit(x_train, y_train)
            fit_seconds = time.perf_counter() - t0

            t1 = time.perf_counter()
            pred = model.predict(x_test)
            predict_seconds = time.perf_counter() - t1

            pred = np.clip(
                np.asarray(pred, dtype=float),
                0,
                1,
            )

            add_result(
                results,
                name,
                train_scope,
                model_name,
                y_test,
                pred,
                fit_seconds=fit_seconds,
                predict_seconds=predict_seconds,
            )

            m = metrics(y_test, pred)
            print(
                f"  MAE={m['mae_pp']:.3f} pp · "
                f"RMSE={m['rmse_pp']:.3f} pp · "
                f"R²={m['r2']:.4f} · "
                f"Spearman={m['spearman_r']:.4f} · "
                f"Top20={m['top20_overlap']:.3f} · "
                f"fit={fit_seconds:.1f}s"
            )

            predictions[f"PRED_{model_name}"] = pred

            del model
            gc.collect()

        predictions.to_parquet(
            PRED_OUT / f"predictions_{name}.parquet",
            index=False,
        )

        del train, test, x_train, x_test, predictions
        gc.collect()

    results_df = pd.DataFrame(results)
    results_df.to_csv(
        OUT / "model_comparison.csv",
        index=False,
    )

    pd.DataFrame(shift_rows).to_csv(
        OUT / "baseline_shift_values.csv",
        index=False,
    )

    # Tabla compacta para lectura rápida.
    compact_cols = [
        "experiment",
        "train_scope",
        "model",
        "n",
        "mae_pp",
        "rmse_pp",
        "r2",
        "spearman_r",
        "top20_overlap",
        "top10_overlap",
        "bias_pp",
        "fit_seconds",
    ]

    compact = results_df[compact_cols].copy()
    compact.to_csv(
        OUT / "model_comparison_compact.csv",
        index=False,
    )

    print("\n" + "=" * 72)
    print("=== Backtesting terminado ===")
    print("=" * 72)
    print(f"Resultados: {OUT.relative_to(ROOT)}")
    print("\nComparación completa:")
    print(
        compact.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nArchivos principales:")
    print("  - reports/backtesting/model_comparison.csv")
    print("  - reports/backtesting/model_comparison_compact.csv")
    print("  - reports/backtesting/baseline_shift_values.csv")
    print("  - reports/backtesting/predictions/*.parquet")


if __name__ == "__main__":
    main()
