from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

LOCK_PATH = ROOT / "reports" / "model_selection" / "selected_architecture.json"
FORECAST_PATH = (
    ROOT / "data" / "processed" / "forecast_2027"
    / "forecast_2027_primary_clean10.parquet"
)
PRED_DIR = ROOT / "reports" / "dual_history" / "predictions"

OUT_DATA = ROOT / "data" / "processed" / "risk_2027"
OUT_REPORT = ROOT / "reports" / "risk_2027"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)

MODEL = "two_history_linear"
PRED_COL = "PRED_two_history_linear"

BACKTESTS = {
    2021: PRED_DIR / "predictions_2021_temporal_dual.parquet",
    2024: PRED_DIR / "predictions_2024_temporal_dual.parquet",
}

# El semáforo se define como priorización RELATIVA:
# - VERDE: 50% inferior de riesgo estimado
# - AMARILLO: percentiles 50–80
# - ROJO: 20% superior
# - PRIORITARIO: bandera adicional para el 10% superior
#
# Top20 y Top10 son precisamente los puntos de operación validados
# durante los backtests previos.
GREEN_MAX = 0.50
YELLOW_MAX = 0.80
PRIORITY_MIN = 0.90


def check_lock():
    if not LOCK_PATH.exists():
        raise FileNotFoundError(
            f"No existe {LOCK_PATH}. Ejecuta primero src/09_select_architecture.py"
        )

    config = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    selected = config.get("selected_model")

    if selected != MODEL:
        raise RuntimeError(
            f"El lock contiene {selected!r}, pero este script espera {MODEL!r}."
        )

    return config


def add_relative_risk(df, score_col, prefix=""):
    out = df.copy()

    score = pd.to_numeric(out[score_col], errors="coerce")
    rank = score.rank(method="average", pct=True)

    rank_col = f"{prefix}RISK_PERCENTILE"
    band_col = f"{prefix}RISK_LEVEL"
    priority_col = f"{prefix}PRIORITY_TOP10"

    out[rank_col] = rank

    out[band_col] = np.select(
        [
            rank.le(GREEN_MAX),
            rank.gt(GREEN_MAX) & rank.le(YELLOW_MAX),
            rank.gt(YELLOW_MAX),
        ],
        [
            "BAJO",
            "MEDIO",
            "ALTO",
        ],
        default="SIN_CLASIFICAR",
    )

    out[priority_col] = rank.ge(PRIORITY_MIN)

    return out


def backtest_validation(year, df):
    required = {
        "SECTION_KEY",
        "EDOCVE",
        "TGT_EDONOM",
        "TGT_MPIOCVE",
        "TGT_MPIONOM",
        "Y_ABSTENCION",
        PRED_COL,
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(
            f"Backtest {year}: faltan columnas {missing}"
        )

    work = df.dropna(subset=["Y_ABSTENCION", PRED_COL]).copy()
    work = add_relative_risk(work, PRED_COL)

    # Ranking observado para poder auditar Top20/Top10.
    actual_rank = (
        pd.to_numeric(work["Y_ABSTENCION"], errors="coerce")
        .rank(method="average", pct=True)
    )
    work["ACTUAL_TOP20"] = actual_rank.gt(YELLOW_MAX)
    work["ACTUAL_TOP10"] = actual_rank.ge(PRIORITY_MIN)

    work["ABS_ERROR_PP"] = (
        work[PRED_COL] - work["Y_ABSTENCION"]
    ).abs() * 100

    rows = []

    order = ["BAJO", "MEDIO", "ALTO"]
    for level in order:
        g = work.loc[work["RISK_LEVEL"].eq(level)]

        rows.append({
            "backtest_year": year,
            "risk_level": level,
            "n": len(g),
            "share_sections": len(g) / len(work),
            "pred_mean": g[PRED_COL].mean(),
            "pred_median": g[PRED_COL].median(),
            "observed_mean": g["Y_ABSTENCION"].mean(),
            "observed_median": g["Y_ABSTENCION"].median(),
            "mae_pp": g["ABS_ERROR_PP"].mean(),
            "actual_top20_rate": g["ACTUAL_TOP20"].mean(),
            "actual_top10_rate": g["ACTUAL_TOP10"].mean(),
        })

    summary = pd.DataFrame(rows)

    priority = work.loc[work["PRIORITY_TOP10"]].copy()

    priority_summary = pd.DataFrame([{
        "backtest_year": year,
        "n_priority": len(priority),
        "share_sections": len(priority) / len(work),
        "pred_mean": priority[PRED_COL].mean(),
        "observed_mean": priority["Y_ABSTENCION"].mean(),
        "actual_top10_rate": priority["ACTUAL_TOP10"].mean(),
        "actual_top20_rate": priority["ACTUAL_TOP20"].mean(),
        "mae_pp": priority["ABS_ERROR_PP"].mean(),
    }])

    # Monotonicidad: el promedio observado debe aumentar de BAJO → MEDIO → ALTO.
    observed_by_level = (
        summary.set_index("risk_level")
        .reindex(order)["observed_mean"]
    )
    monotonic = bool(
        observed_by_level["BAJO"]
        < observed_by_level["MEDIO"]
        < observed_by_level["ALTO"]
    )

    diagnostics = pd.DataFrame([{
        "backtest_year": year,
        "risk_monotonic_observed_means": monotonic,
        "observed_mean_bajo": observed_by_level["BAJO"],
        "observed_mean_medio": observed_by_level["MEDIO"],
        "observed_mean_alto": observed_by_level["ALTO"],
        "red_precision_top20": (
            summary.loc[
                summary["risk_level"].eq("ALTO"),
                "actual_top20_rate"
            ].iloc[0]
        ),
        "priority_precision_top10": priority_summary["actual_top10_rate"].iloc[0],
    }])

    return work, summary, priority_summary, diagnostics


def forecast_summary(risk):
    level_order = ["BAJO", "MEDIO", "ALTO"]

    rows = []
    for level in level_order:
        g = risk.loc[risk["RISK_LEVEL"].eq(level)]
        rows.append({
            "risk_level": level,
            "n": len(g),
            "share_sections": len(g) / len(risk),
            "pred_mean": g["PRED_ABSTENCION_2027"].mean(),
            "pred_median": g["PRED_ABSTENCION_2027"].median(),
            "pred_min": g["PRED_ABSTENCION_2027"].min(),
            "pred_max": g["PRED_ABSTENCION_2027"].max(),
            "interval_width_median_pp": g["INTERVAL_WIDTH_PP"].median(),
            "history_disagreement_median_pp": g["HISTORY_DISAGREEMENT_PP"].median(),
        })

    return pd.DataFrame(rows)


def state_summary(risk):
    counts = (
        risk.groupby(
            ["EDOCVE", "RECENT_EDONOM", "RISK_LEVEL"],
            dropna=False,
        )
        .size()
        .rename("sections")
        .reset_index()
    )

    totals = (
        risk.groupby(
            ["EDOCVE", "RECENT_EDONOM"],
            dropna=False,
        )
        .size()
        .rename("total_sections")
        .reset_index()
    )

    counts = counts.merge(
        totals,
        on=["EDOCVE", "RECENT_EDONOM"],
        how="left",
        validate="many_to_one",
    )
    counts["share_state_sections"] = (
        counts["sections"] / counts["total_sections"]
    )

    priority = (
        risk.loc[risk["PRIORITY_TOP10"]]
        .groupby(["EDOCVE", "RECENT_EDONOM"], dropna=False)
        .size()
        .rename("priority_top10_sections")
        .reset_index()
    )

    state = totals.merge(
        priority,
        on=["EDOCVE", "RECENT_EDONOM"],
        how="left",
    )
    state["priority_top10_sections"] = (
        state["priority_top10_sections"]
        .fillna(0)
        .astype(int)
    )
    state["priority_top10_share"] = (
        state["priority_top10_sections"]
        / state["total_sections"]
    )

    pred_state = (
        risk.groupby(
            ["EDOCVE", "RECENT_EDONOM"],
            dropna=False,
        )
        .agg(
            pred_mean=("PRED_ABSTENCION_2027", "mean"),
            pred_median=("PRED_ABSTENCION_2027", "median"),
            history_disagreement_median_pp=(
                "HISTORY_DISAGREEMENT_PP",
                "median",
            ),
        )
        .reset_index()
    )

    state = state.merge(
        pred_state,
        on=["EDOCVE", "RECENT_EDONOM"],
        how="left",
        validate="one_to_one",
    )

    return counts, state


def municipality_summary(risk):
    g = (
        risk.groupby(
            [
                "EDOCVE",
                "RECENT_EDONOM",
                "RECENT_MPIOCVE",
                "RECENT_MPIONOM",
            ],
            dropna=False,
        )
        .agg(
            sections=("SECTION_KEY", "size"),
            pred_mean=("PRED_ABSTENCION_2027", "mean"),
            pred_median=("PRED_ABSTENCION_2027", "median"),
            red_sections=(
                "RISK_LEVEL",
                lambda s: int((s == "ALTO").sum()),
            ),
            priority_top10_sections=(
                "PRIORITY_TOP10",
                "sum",
            ),
            history_disagreement_median_pp=(
                "HISTORY_DISAGREEMENT_PP",
                "median",
            ),
        )
        .reset_index()
    )

    g["red_share"] = g["red_sections"] / g["sections"]
    g["priority_top10_share"] = (
        g["priority_top10_sections"] / g["sections"]
    )

    return g


def main():
    print("\n=== 11 · Calibración del semáforo territorial ===")

    lock = check_lock()
    print(f"Arquitectura bloqueada: {lock['selected_model']}")

    # --------------------------------------------------------------
    # 1) Validación retrospectiva del semáforo.
    # --------------------------------------------------------------
    bt_summaries = []
    bt_priority = []
    diagnostics = []

    for year, path in BACKTESTS.items():
        if not path.exists():
            raise FileNotFoundError(
                f"No existe {path}. Ejecuta primero src/07_dual_history_backtest.py"
            )

        df = pd.read_parquet(path)
        _, summary, priority, diag = backtest_validation(year, df)

        bt_summaries.append(summary)
        bt_priority.append(priority)
        diagnostics.append(diag)

        print(f"\nBacktest {year}:")
        print(
            summary[
                [
                    "risk_level",
                    "n",
                    "observed_mean",
                    "actual_top20_rate",
                    "actual_top10_rate",
                ]
            ].to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )

        print(
            "  Top10 prioritario · "
            f"precision Top10={priority['actual_top10_rate'].iloc[0]:.4f}"
        )

    bt_summary = pd.concat(bt_summaries, ignore_index=True)
    bt_priority = pd.concat(bt_priority, ignore_index=True)
    diag = pd.concat(diagnostics, ignore_index=True)

    bt_summary.to_csv(
        OUT_REPORT / "01_backtest_risk_levels.csv",
        index=False,
    )
    bt_priority.to_csv(
        OUT_REPORT / "02_backtest_priority_top10.csv",
        index=False,
    )
    diag.to_csv(
        OUT_REPORT / "03_backtest_risk_diagnostics.csv",
        index=False,
    )

    # --------------------------------------------------------------
    # 2) Aplicar la misma regla relativa a la proyección 2027.
    # --------------------------------------------------------------
    if not FORECAST_PATH.exists():
        raise FileNotFoundError(
            f"No existe {FORECAST_PATH}. Ejecuta primero src/10_fit_final_forecast_2027.py"
        )

    forecast = pd.read_parquet(FORECAST_PATH)

    required_forecast = {
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
        "PRED_ABSTENCION_2027",
        "PRED_LOWER_90_OOS",
        "PRED_UPPER_90_OOS",
        "INTERVAL_WIDTH_PP",
        "HISTORY_DISAGREEMENT_PP",
    }
    missing = sorted(required_forecast - set(forecast.columns))
    if missing:
        raise RuntimeError(
            f"Faltan columnas en el forecast: {missing}"
        )

    risk = add_relative_risk(
        forecast,
        "PRED_ABSTENCION_2027",
    )

    # Umbrales absolutos resultantes de la distribución 2027.
    q50 = risk["PRED_ABSTENCION_2027"].quantile(GREEN_MAX)
    q80 = risk["PRED_ABSTENCION_2027"].quantile(YELLOW_MAX)
    q90 = risk["PRED_ABSTENCION_2027"].quantile(PRIORITY_MIN)

    thresholds = pd.DataFrame([
        {
            "rule": "BAJO_MAX",
            "risk_percentile": GREEN_MAX,
            "predicted_abstention_threshold": q50,
        },
        {
            "rule": "MEDIO_MAX",
            "risk_percentile": YELLOW_MAX,
            "predicted_abstention_threshold": q80,
        },
        {
            "rule": "PRIORITY_TOP10_MIN",
            "risk_percentile": PRIORITY_MIN,
            "predicted_abstention_threshold": q90,
        },
    ])
    thresholds.to_csv(
        OUT_REPORT / "04_2027_risk_thresholds.csv",
        index=False,
    )

    risk_summary = forecast_summary(risk)
    risk_summary.to_csv(
        OUT_REPORT / "05_2027_risk_level_summary.csv",
        index=False,
    )

    state_counts, states = state_summary(risk)
    state_counts.to_csv(
        OUT_REPORT / "06_state_risk_level_counts.csv",
        index=False,
    )
    states.to_csv(
        OUT_REPORT / "07_state_priority_summary.csv",
        index=False,
    )

    municipalities = municipality_summary(risk)

    # Los archivos territoriales amplios se mantienen en data/processed.
    risk.to_parquet(
        OUT_DATA / "section_risk_2027_primary.parquet",
        index=False,
    )
    risk.to_csv(
        OUT_DATA / "section_risk_2027_primary.csv.gz",
        index=False,
        compression="gzip",
    )
    municipalities.to_parquet(
        OUT_DATA / "municipality_risk_2027.parquet",
        index=False,
    )

    # --------------------------------------------------------------
    # 3) Documentación metodológica.
    # --------------------------------------------------------------
    method = f"""# Semáforo territorial de riesgo · metodología v1

## Naturaleza del semáforo

El semáforo es una **clasificación relativa de priorización territorial** dentro
del universo `primary_clean10`. No debe interpretarse como una probabilidad
absoluta de que una sección se abstenga.

Se utiliza la estimación continua generada por la arquitectura bloqueada
`two_history_linear`.

## Regla

- **BAJO / verde:** percentil de riesgo <= 50.
- **MEDIO / amarillo:** percentil > 50 y <= 80.
- **ALTO / rojo:** percentil > 80.
- **PRIORITY_TOP10:** bandera adicional para percentil >= 90.

Los puntos Top20 y Top10 se eligieron porque fueron evaluados explícitamente
durante los backtests temporales del proyecto.

## Validación

Antes de aplicarse a 2027, la misma regla se aplica retrospectivamente a los
backtests 2021 y 2024. Para cada nivel se documentan:

- promedio de abstención observado;
- error absoluto medio;
- proporción de secciones que realmente estuvieron en el Top20 observado;
- proporción de secciones que realmente estuvieron en el Top10 observado.

También se verifica que el promedio de abstención observado aumente
monótonamente de BAJO a MEDIO y ALTO.

## Umbrales 2027

Los cortes porcentuales se traducen a valores absolutos usando la distribución
de `PRED_ABSTENCION_2027` del universo primario. Por tanto, el semáforo es
relativo al universo analizado y deberá recalibrarse si cambia la cartografía
o el universo operativo.

## Incertidumbre

El semáforo no elimina la incertidumbre. Cada sección conserva:

- `PRED_LOWER_90_OOS`;
- `PRED_UPPER_90_OOS`;
- `INTERVAL_WIDTH_PP`;
- `HISTORY_DISAGREEMENT_PP`.

Estas columnas deberán mostrarse en el producto final como información
complementaria a la prioridad territorial.

## Limitación

La base aún no ha sido reconciliada con la cartografía oficial vigente del
proceso futuro. Esta conciliación será una etapa independiente antes de la
visualización geográfica final.
"""
    (OUT_REPORT / "TRAFFIC_LIGHT_METHOD.md").write_text(
        method,
        encoding="utf-8",
    )

    config = {
        "architecture": MODEL,
        "score": "PRED_ABSTENCION_2027",
        "classification_type": "relative_territorial_priority",
        "rules": {
            "BAJO": "risk_percentile <= 0.50",
            "MEDIO": "0.50 < risk_percentile <= 0.80",
            "ALTO": "risk_percentile > 0.80",
            "PRIORITY_TOP10": "risk_percentile >= 0.90",
        },
        "2027_thresholds": {
            "q50": float(q50),
            "q80": float(q80),
            "q90": float(q90),
        },
        "warning": (
            "Risk levels are relative to the primary comparable universe "
            "and are not individual-level probabilities."
        ),
    }

    (OUT_REPORT / "traffic_light_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nDiagnóstico de validación:")
    print(
        diag.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nUmbrales resultantes 2027:")
    print(
        thresholds.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nDistribución 2027:")
    print(
        risk_summary.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\n=== Semáforo calibrado ===")
    print(f"Datos territoriales: {OUT_DATA.relative_to(ROOT)}")
    print(f"Reportes: {OUT_REPORT.relative_to(ROOT)}")
    print("\nEl siguiente paso será construir escenarios, no cambiar la arquitectura.")


if __name__ == "__main__":
    main()
