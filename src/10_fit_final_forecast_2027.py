from pathlib import Path
import json
import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


ROOT = Path(__file__).resolve().parents[1]

MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
DUAL_DIR = ROOT / "data" / "processed" / "dual_history"
LOCK_PATH = ROOT / "reports" / "model_selection" / "selected_architecture.json"
PRED_DIR = ROOT / "reports" / "dual_history" / "predictions"

OUT_DATA = ROOT / "data" / "processed" / "forecast_2027"
OUT_REPORT = ROOT / "reports" / "forecast_2027"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)

TARGET_YEAR = 2027
SAME_YEAR = 2021
RECENT_YEAR = 2024

MODEL_FEATURES = [
    "SAME_PCT_ABSTENCION",
    "RECENT_PCT_ABSTENCION",
]

TRAIN_TARGET_YEARS = [2015, 2018, 2021, 2024]


def check_lock():
    if not LOCK_PATH.exists():
        raise FileNotFoundError(
            f"No existe {LOCK_PATH}. Ejecuta primero src/09_select_architecture.py"
        )

    config = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    selected = config.get("selected_model")

    if selected != "two_history_linear":
        raise RuntimeError(
            "Este script implementa el lock 'two_history_linear', pero "
            f"selected_architecture.json contiene: {selected!r}"
        )

    return config


def regression_metrics(y, pred):
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)

    return {
        "n": int(len(y)),
        "mae_pp": float(mean_absolute_error(y, pred) * 100),
        "rmse_pp": float(np.sqrt(mean_squared_error(y, pred)) * 100),
        "r2_in_sample": float(r2_score(y, pred)),
        "bias_pp": float(np.mean(pred - y) * 100),
    }


def load_training():
    frames = []

    for year in TRAIN_TARGET_YEARS:
        path = DUAL_DIR / f"dual_history_target_{year}_clean10.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"No existe {path}. Ejecuta primero src/07_dual_history_backtest.py"
            )

        df = pd.read_parquet(path)

        required = set(MODEL_FEATURES + ["Y_ABSTENCION", "TARGET_YEAR"])
        missing = sorted(required - set(df.columns))
        if missing:
            raise RuntimeError(f"Faltan columnas en {path.name}: {missing}")

        df = df.dropna(subset=MODEL_FEATURES + ["Y_ABSTENCION"]).copy()
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def load_oos_residuals():
    """
    Residuales fuera de muestra de los dos backtests temporales.
    Para 2027, el intervalo primario usa 2021 por ser el backtest
    intermedio comparable. El pooled 2021+2024 se conserva como sensibilidad.
    """
    rows = []

    files = {
        2021: PRED_DIR / "predictions_2021_temporal_dual.parquet",
        2024: PRED_DIR / "predictions_2024_temporal_dual.parquet",
    }

    residual_frames = {}

    for year, path in files.items():
        if not path.exists():
            raise FileNotFoundError(
                f"No existe {path}. Ejecuta primero src/07_dual_history_backtest.py"
            )

        df = pd.read_parquet(path)

        required = {"Y_ABSTENCION", "PRED_two_history_linear"}
        missing = sorted(required - set(df.columns))
        if missing:
            raise RuntimeError(f"Faltan columnas en {path.name}: {missing}")

        d = df[["Y_ABSTENCION", "PRED_two_history_linear"]].dropna().copy()
        d["residual"] = d["Y_ABSTENCION"] - d["PRED_two_history_linear"]
        d["abs_error"] = d["residual"].abs()
        residual_frames[year] = d

        rows.append({
            "source": str(year),
            "n": len(d),
            "signed_q05_pp": d["residual"].quantile(0.05) * 100,
            "signed_q50_pp": d["residual"].quantile(0.50) * 100,
            "signed_q95_pp": d["residual"].quantile(0.95) * 100,
            "abs_error_q50_pp": d["abs_error"].quantile(0.50) * 100,
            "abs_error_q80_pp": d["abs_error"].quantile(0.80) * 100,
            "abs_error_q90_pp": d["abs_error"].quantile(0.90) * 100,
            "abs_error_q95_pp": d["abs_error"].quantile(0.95) * 100,
        })

    pooled = pd.concat(
        [residual_frames[2021], residual_frames[2024]],
        ignore_index=True
    )

    rows.append({
        "source": "pooled_2021_2024",
        "n": len(pooled),
        "signed_q05_pp": pooled["residual"].quantile(0.05) * 100,
        "signed_q50_pp": pooled["residual"].quantile(0.50) * 100,
        "signed_q95_pp": pooled["residual"].quantile(0.95) * 100,
        "abs_error_q50_pp": pooled["abs_error"].quantile(0.50) * 100,
        "abs_error_q80_pp": pooled["abs_error"].quantile(0.80) * 100,
        "abs_error_q90_pp": pooled["abs_error"].quantile(0.90) * 100,
        "abs_error_q95_pp": pooled["abs_error"].quantile(0.95) * 100,
    })

    calibration = pd.DataFrame(rows)
    return residual_frames, calibration


def build_projection_universe(master):
    cols = [
        "AELEC",
        "EDOCVE",
        "EDONOM",
        "MPIOCVE",
        "MPIONOM",
        "SECCION",
        "TIPOSEC",
        "LN",
        "PCT_ABSTENCION",
        "PCT_NS_LN",
    ]

    same = master.loc[master["AELEC"].eq(SAME_YEAR), cols].copy()
    recent = master.loc[master["AELEC"].eq(RECENT_YEAR), cols].copy()

    for d in [same, recent]:
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
        "LN": "SAME_LN",
        "PCT_ABSTENCION": "SAME_PCT_ABSTENCION",
        "PCT_NS_LN": "SAME_PCT_NS_LN",
    })

    recent = recent.rename(columns={
        "EDONOM": "RECENT_EDONOM",
        "MPIOCVE": "RECENT_MPIOCVE",
        "MPIONOM": "RECENT_MPIONOM",
        "SECCION": "RECENT_SECCION",
        "TIPOSEC": "RECENT_TIPOSEC",
        "LN": "RECENT_LN",
        "PCT_ABSTENCION": "RECENT_PCT_ABSTENCION",
        "PCT_NS_LN": "RECENT_PCT_NS_LN",
    })

    out = same.merge(
        recent,
        on=["EDOCVE", "SECTION_KEY"],
        how="inner",
        validate="one_to_one",
    )

    out.insert(0, "TARGET_YEAR", TARGET_YEAR)
    out.insert(1, "SAME_YEAR", SAME_YEAR)
    out.insert(2, "RECENT_YEAR", RECENT_YEAR)

    out["STABLE_MPIO"] = out["SAME_MPIOCVE"].eq(out["RECENT_MPIOCVE"])
    out["STABLE_TIPOSEC"] = out["SAME_TIPOSEC"].eq(out["RECENT_TIPOSEC"])

    out["INPUTS_VALID"] = (
        out["SAME_PCT_ABSTENCION"].notna()
        & out["RECENT_PCT_ABSTENCION"].notna()
    )

    out["NS_CLEAN10"] = (
        out["SAME_PCT_NS_LN"].le(0.10)
        & out["RECENT_PCT_NS_LN"].le(0.10)
    )

    out["PRIMARY_UNIVERSE"] = (
        out["STABLE_MPIO"]
        & out["STABLE_TIPOSEC"]
        & out["INPUTS_VALID"]
        & out["NS_CLEAN10"]
    )

    out["QUALITY_FLAG"] = np.select(
        [
            out["PRIMARY_UNIVERSE"],
            out["STABLE_MPIO"] & out["STABLE_TIPOSEC"] & out["INPUTS_VALID"],
            out["INPUTS_VALID"],
        ],
        [
            "primary_clean10",
            "comparable_high_ns",
            "valid_inputs_low_comparability",
        ],
        default="insufficient_inputs",
    )

    return out


def add_prediction_and_intervals(universe, model, calibration):
    out = universe.copy()

    valid = out["INPUTS_VALID"].copy()
    x = out.loc[valid, MODEL_FEATURES].to_numpy(float)

    pred = np.clip(model.predict(x), 0, 1)
    out.loc[valid, "PRED_ABSTENCION_2027"] = pred

    # Intervalo empírico primario: errores OOS del backtest 2021,
    # por ser el objetivo intermedio comparable a 2027.
    cal_2021 = calibration.loc[calibration["source"].eq("2021")].iloc[0]
    q05 = cal_2021["signed_q05_pp"] / 100
    q95 = cal_2021["signed_q95_pp"] / 100

    out.loc[valid, "PRED_LOWER_90_OOS"] = np.clip(pred + q05, 0, 1)
    out.loc[valid, "PRED_UPPER_90_OOS"] = np.clip(pred + q95, 0, 1)
    out.loc[valid, "INTERVAL_WIDTH_PP"] = (
        out.loc[valid, "PRED_UPPER_90_OOS"]
        - out.loc[valid, "PRED_LOWER_90_OOS"]
    ) * 100

    # Desacuerdo entre las dos memorias: útil luego como señal adicional
    # de inestabilidad, pero todavía NO define el semáforo.
    out["HISTORY_DISAGREEMENT_PP"] = (
        out["RECENT_PCT_ABSTENCION"] - out["SAME_PCT_ABSTENCION"]
    ).abs() * 100

    return out


def state_summary(primary):
    def weighted_mean(g):
        w = pd.to_numeric(g["RECENT_LN"], errors="coerce").fillna(0).to_numpy(float)
        y = pd.to_numeric(g["PRED_ABSTENCION_2027"], errors="coerce").to_numpy(float)
        mask = np.isfinite(w) & np.isfinite(y) & (w > 0)
        if mask.sum() == 0:
            return np.nan
        return np.average(y[mask], weights=w[mask])

    rows = []

    for (edo, nombre), g in primary.groupby(
        ["EDOCVE", "RECENT_EDONOM"],
        dropna=False
    ):
        rows.append({
            "EDOCVE": edo,
            "entidad": nombre,
            "sections": len(g),
            "pred_mean": g["PRED_ABSTENCION_2027"].mean(),
            "pred_median": g["PRED_ABSTENCION_2027"].median(),
            "pred_p25": g["PRED_ABSTENCION_2027"].quantile(0.25),
            "pred_p75": g["PRED_ABSTENCION_2027"].quantile(0.75),
            "pred_weighted_by_2024_LN": weighted_mean(g),
            "history_disagreement_median_pp": g["HISTORY_DISAGREEMENT_PP"].median(),
        })

    return pd.DataFrame(rows).sort_values("EDOCVE")


def main():
    print("\n=== 10 · Ajuste final + proyección territorial 2027 v1 ===")

    lock = check_lock()
    print(f"Arquitectura bloqueada: {lock['selected_model']}")

    if not MASTER_PATH.exists():
        raise FileNotFoundError(MASTER_PATH)

    # --------------------------------------------------------------
    # 1) Reentrenamiento posterior a la selección.
    # --------------------------------------------------------------
    train = load_training()

    x_train = train[MODEL_FEATURES].to_numpy(float)
    y_train = train["Y_ABSTENCION"].to_numpy(float)

    model = LinearRegression()
    model.fit(x_train, y_train)

    pred_train = np.clip(model.predict(x_train), 0, 1)
    train_metrics = regression_metrics(y_train, pred_train)

    coef = pd.DataFrame([
        {
            "term": "intercept",
            "coefficient": float(model.intercept_),
        },
        {
            "term": "SAME_PCT_ABSTENCION",
            "coefficient": float(model.coef_[0]),
        },
        {
            "term": "RECENT_PCT_ABSTENCION",
            "coefficient": float(model.coef_[1]),
        },
    ])
    coef.to_csv(OUT_REPORT / "01_final_model_coefficients.csv", index=False)

    train_summary = pd.DataFrame([{
        **train_metrics,
        "training_target_years": ",".join(map(str, TRAIN_TARGET_YEARS)),
        "selected_architecture": lock["selected_model"],
    }])
    train_summary.to_csv(
        OUT_REPORT / "02_refit_training_summary.csv",
        index=False
    )

    print("\nModelo reentrenado con toda la historia observada:")
    print(
        f"  intercept = {model.intercept_:.6f}\n"
        f"  beta_same = {model.coef_[0]:.6f}\n"
        f"  beta_recent = {model.coef_[1]:.6f}\n"
        f"  n_train = {len(train):,}"
    )

    # --------------------------------------------------------------
    # 2) Calibración empírica de incertidumbre con errores OOS.
    # --------------------------------------------------------------
    _, calibration = load_oos_residuals()
    calibration.to_csv(
        OUT_REPORT / "03_uncertainty_calibration.csv",
        index=False
    )

    cal21 = calibration.loc[calibration["source"].eq("2021")].iloc[0]
    print("\nCalibración OOS primaria (backtest 2021):")
    print(
        f"  residual q05 = {cal21['signed_q05_pp']:.3f} pp\n"
        f"  residual q95 = {cal21['signed_q95_pp']:.3f} pp\n"
        f"  abs error q90 = {cal21['abs_error_q90_pp']:.3f} pp"
    )

    # --------------------------------------------------------------
    # 3) Universo de proyección 2021 + 2024.
    # --------------------------------------------------------------
    master = pd.read_csv(MASTER_PATH, low_memory=False)
    universe = build_projection_universe(master)
    forecast = add_prediction_and_intervals(universe, model, calibration)

    primary = forecast.loc[forecast["PRIMARY_UNIVERSE"]].copy()

    print("\nUniverso de proyección:")
    print(f"  presentes en 2021 y 2024: {len(forecast):,}")
    print(f"  inputs válidos: {int(forecast['INPUTS_VALID'].sum()):,}")
    print(f"  primary clean10: {len(primary):,}")

    # Archivos sección-level: derivados, se mantienen fuera de Git.
    forecast.to_parquet(
        OUT_DATA / "forecast_2027_all_comparable.parquet",
        index=False
    )
    primary.to_parquet(
        OUT_DATA / "forecast_2027_primary_clean10.parquet",
        index=False
    )
    primary.to_csv(
        OUT_DATA / "forecast_2027_primary_clean10.csv.gz",
        index=False,
        compression="gzip"
    )

    # Resúmenes pequeños versionables.
    quality = (
        forecast.groupby("QUALITY_FLAG", dropna=False)
        .size()
        .rename("sections")
        .reset_index()
        .sort_values("sections", ascending=False)
    )
    quality.to_csv(OUT_REPORT / "04_projection_quality_summary.csv", index=False)

    states = state_summary(primary)
    states.to_csv(OUT_REPORT / "05_state_forecast_summary.csv", index=False)

    national = pd.DataFrame([{
        "target_year": TARGET_YEAR,
        "sections_primary": len(primary),
        "mean_pred_abstention": primary["PRED_ABSTENCION_2027"].mean(),
        "median_pred_abstention": primary["PRED_ABSTENCION_2027"].median(),
        "p10_pred_abstention": primary["PRED_ABSTENCION_2027"].quantile(0.10),
        "p90_pred_abstention": primary["PRED_ABSTENCION_2027"].quantile(0.90),
        "median_history_disagreement_pp": primary["HISTORY_DISAGREEMENT_PP"].median(),
        "uncertainty_source": "2021 temporal out-of-sample residual distribution",
        "note": (
            "Projection universe is defined by sections comparable between 2021 and 2024. "
            "It is not yet reconciled with the official 2027 cartographic universe."
        ),
    }])
    national.to_csv(OUT_REPORT / "06_national_forecast_summary.csv", index=False)

    # Guardar configuración legible.
    model_config = {
        "target_year": TARGET_YEAR,
        "architecture": "two_history_linear",
        "features": MODEL_FEATURES,
        "same_family_year": SAME_YEAR,
        "recent_year": RECENT_YEAR,
        "training_target_years": TRAIN_TARGET_YEARS,
        "intercept": float(model.intercept_),
        "coefficients": {
            MODEL_FEATURES[0]: float(model.coef_[0]),
            MODEL_FEATURES[1]: float(model.coef_[1]),
        },
        "uncertainty": {
            "primary_source": "2021_temporal_dual out-of-sample signed residuals",
            "interval": "empirical 90% using q05/q95 signed residuals",
            "warning": (
                "This is an empirical uncertainty band, not a guarantee of future "
                "coverage under structural electoral or cartographic changes."
            ),
        },
        "projection_universe_warning": (
            "The section universe is based on 2021–2024 comparability and must later "
            "be reconciled with official current cartography before operational use."
        ),
    }

    (OUT_REPORT / "forecast_model_config.json").write_text(
        json.dumps(model_config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    method = f"""# Proyección territorial 2027 v1

## Arquitectura

La arquitectura fue bloqueada previamente como `two_history_linear`.

El estimador utiliza dos memorias territoriales:

- abstención 2021: última elección de la misma familia usada por la proyección;
- abstención 2024: elección federal más reciente disponible en CCPC.

La forma del modelo es:

`pred = intercept + beta_same * abst_2021 + beta_recent * abst_2024`

Los coeficientes se reestiman después de la selección utilizando todas las ventanas
históricas clean10 disponibles con targets 2015, 2018, 2021 y 2024.

## Universo

La salida v1 sólo incluye secciones presentes en 2021 y 2024. El universo primario
exige además:

- municipio estable entre ambas observaciones;
- tipo de sección estable;
- abstención calculable en ambas observaciones;
- NS <= 10% en ambas observaciones.

Este universo todavía **no equivale a la cartografía oficial 2027**. La conciliación
cartográfica será una etapa posterior.

## Incertidumbre

El intervalo empírico primario se construye con los residuales fuera de muestra del
backtest temporal 2021, por ser la evaluación intermedia comparable más cercana.

No se interpreta como una garantía probabilística si existen cambios estructurales
fuera de lo observado históricamente.

## Importante

Esta etapa genera una estimación continua y un intervalo de incertidumbre. Todavía
no asigna niveles de semáforo ni simula efectos de intervención.
"""
    (OUT_REPORT / "FORECAST_METHOD.md").write_text(method, encoding="utf-8")

    print("\nResumen nacional v1:")
    print(national.to_string(index=False))

    print("\n=== Proyección v1 terminada ===")
    print(f"Datos sección-level: {OUT_DATA.relative_to(ROOT)}")
    print(f"Reportes: {OUT_REPORT.relative_to(ROOT)}")
    print("\nTodavía NO se ha creado el semáforo de riesgo.")


if __name__ == "__main__":
    main()
