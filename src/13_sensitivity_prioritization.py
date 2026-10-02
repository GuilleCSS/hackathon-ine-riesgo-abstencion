from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

RISK_PATH = (
    ROOT / "data" / "processed" / "risk_2027"
    / "section_risk_2027_primary.parquet"
)
CONFIG_PATH = (
    ROOT / "reports" / "risk_2027"
    / "traffic_light_config.json"
)

OUT_DATA = ROOT / "data" / "processed" / "sensitivity_2027"
OUT_REPORT = ROOT / "reports" / "sensitivity_2027"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)

# Barrido de sensibilidad: 0 a 10 pp, cada 0.5 pp.
REDUCTIONS_PP = np.arange(0.0, 10.0 + 0.0001, 0.5)


def load_thresholds():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"No existe {CONFIG_PATH}. "
            "Ejecuta primero src/11_calibrate_traffic_light.py"
        )

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    th = cfg["2027_thresholds"]

    return {
        "q50": float(th["q50"]),
        "q80": float(th["q80"]),
        "q90": float(th["q90"]),
    }


def classify_fixed(score, th):
    s = pd.to_numeric(score, errors="coerce")

    level = np.select(
        [
            s.le(th["q50"]),
            s.gt(th["q50"]) & s.le(th["q80"]),
            s.gt(th["q80"]),
        ],
        [
            "BAJO",
            "MEDIO",
            "ALTO",
        ],
        default="SIN_CLASIFICAR",
    )

    priority = s.ge(th["q90"])
    return level, priority


def add_section_sensitivity(df, th):
    out = df.copy()

    pred = pd.to_numeric(
        out["PRED_ABSTENCION_2027"],
        errors="coerce",
    )

    # Distancia en puntos porcentuales al límite inferior de ALTO.
    out["GAP_TO_EXIT_HIGH_PP"] = np.where(
        out["RISK_LEVEL"].eq("ALTO"),
        np.maximum((pred - th["q80"]) * 100.0, 0.0),
        0.0,
    )

    # Distancia al umbral Top10. Para quedar estrictamente por debajo del
    # umbral puede requerirse una reducción infinitesimal adicional si cae
    # exactamente en el corte; se usa como distancia descriptiva.
    out["GAP_TO_EXIT_PRIORITY_PP"] = np.where(
        out["PRIORITY_TOP10"].fillna(False).astype(bool),
        np.maximum((pred - th["q90"]) * 100.0, 0.0),
        0.0,
    )

    out["HIGH_SENSITIVITY_CLASS"] = np.select(
        [
            ~out["RISK_LEVEL"].eq("ALTO"),
            out["GAP_TO_EXIT_HIGH_PP"].le(2.0),
            out["GAP_TO_EXIT_HIGH_PP"].gt(2.0)
            & out["GAP_TO_EXIT_HIGH_PP"].le(5.0),
            out["GAP_TO_EXIT_HIGH_PP"].gt(5.0),
        ],
        [
            "NO_ALTO",
            "ALTO_SENSIBLE_2PP",
            "ALTO_SENSIBLE_5PP",
            "ALTO_PERSISTENTE_MAS_5PP",
        ],
        default="SIN_CLASIFICAR",
    )

    # Relación entre intervalo empírico y el umbral ALTO.
    lower = pd.to_numeric(
        out["PRED_LOWER_90_OOS"],
        errors="coerce",
    )
    upper = pd.to_numeric(
        out["PRED_UPPER_90_OOS"],
        errors="coerce",
    )

    out["INTERVAL_POSITION_VS_HIGH"] = np.select(
        [
            upper.le(th["q80"]),
            lower.gt(th["q80"]),
            lower.le(th["q80"]) & upper.gt(th["q80"]),
        ],
        [
            "INTERVAL_BELOW_HIGH",
            "INTERVAL_ENTIRELY_HIGH",
            "INTERVAL_CROSSES_HIGH",
        ],
        default="SIN_DATOS",
    )

    return out


def build_curve(base, th, target_strategy):
    rows = []

    baseline_pred = pd.to_numeric(
        base["PRED_ABSTENCION_2027"],
        errors="coerce",
    ).to_numpy(float)

    baseline_high = base["RISK_LEVEL"].eq("ALTO").to_numpy(bool)
    baseline_priority = (
        base["PRIORITY_TOP10"]
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )

    if target_strategy == "HIGH":
        target_mask = baseline_high
    elif target_strategy == "TOP10":
        target_mask = baseline_priority
    else:
        raise ValueError(target_strategy)

    for delta_pp in REDUCTIONS_PP:
        reduction = np.where(
            target_mask,
            delta_pp / 100.0,
            0.0,
        )

        scenario_pred = np.clip(
            baseline_pred - reduction,
            0,
            1,
        )

        level, priority = classify_fixed(
            pd.Series(scenario_pred),
            th,
        )

        level = np.asarray(level)
        priority = np.asarray(priority, dtype=bool)

        high_remaining = int((level == "ALTO").sum())
        priority_remaining = int(priority.sum())

        rows.append({
            "target_strategy": target_strategy,
            "assumed_reduction_pp": float(delta_pp),
            "targeted_sections": int(target_mask.sum()),
            "mean_change_pp": float(
                np.mean(scenario_pred - baseline_pred) * 100.0
            ),
            "baseline_high_sections": int(baseline_high.sum()),
            "high_remaining": high_remaining,
            "high_exited": int(baseline_high.sum()) - high_remaining,
            "share_baseline_high_exited": (
                (int(baseline_high.sum()) - high_remaining)
                / int(baseline_high.sum())
                if baseline_high.sum() > 0
                else np.nan
            ),
            "baseline_priority_sections": int(
                baseline_priority.sum()
            ),
            "priority_remaining": priority_remaining,
            "priority_exited": (
                int(baseline_priority.sum())
                - priority_remaining
            ),
            "share_baseline_priority_exited": (
                (
                    int(baseline_priority.sum())
                    - priority_remaining
                )
                / int(baseline_priority.sum())
                if baseline_priority.sum() > 0
                else np.nan
            ),
        })

    return pd.DataFrame(rows)


def typology_summary(df):
    order = [
        "NO_ALTO",
        "ALTO_SENSIBLE_2PP",
        "ALTO_SENSIBLE_5PP",
        "ALTO_PERSISTENTE_MAS_5PP",
    ]

    rows = []
    for cls in order:
        g = df.loc[
            df["HIGH_SENSITIVITY_CLASS"].eq(cls)
        ]

        rows.append({
            "high_sensitivity_class": cls,
            "n": len(g),
            "share_all_sections": len(g) / len(df),
            "pred_mean": g["PRED_ABSTENCION_2027"].mean(),
            "pred_median": g["PRED_ABSTENCION_2027"].median(),
            "priority_top10_share": (
                g["PRIORITY_TOP10"].mean()
                if len(g) > 0
                else np.nan
            ),
            "history_disagreement_median_pp": (
                g["HISTORY_DISAGREEMENT_PP"].median()
                if len(g) > 0
                else np.nan
            ),
            "gap_to_exit_high_median_pp": (
                g["GAP_TO_EXIT_HIGH_PP"].median()
                if len(g) > 0
                else np.nan
            ),
        })

    return pd.DataFrame(rows)


def interval_summary(df):
    return (
        df.groupby(
            ["RISK_LEVEL", "INTERVAL_POSITION_VS_HIGH"],
            dropna=False,
        )
        .size()
        .rename("sections")
        .reset_index()
    )


def state_summary(df):
    rows = []

    for (edo, nombre), g in df.groupby(
        ["EDOCVE", "RECENT_EDONOM"],
        dropna=False,
    ):
        high = g["RISK_LEVEL"].eq("ALTO")

        rows.append({
            "EDOCVE": edo,
            "entidad": nombre,
            "sections": len(g),
            "high_sections": int(high.sum()),
            "priority_top10_sections": int(
                g["PRIORITY_TOP10"].sum()
            ),
            "alto_sensible_2pp": int(
                g["HIGH_SENSITIVITY_CLASS"]
                .eq("ALTO_SENSIBLE_2PP")
                .sum()
            ),
            "alto_sensible_5pp": int(
                g["HIGH_SENSITIVITY_CLASS"]
                .eq("ALTO_SENSIBLE_5PP")
                .sum()
            ),
            "alto_persistente_mas_5pp": int(
                g["HIGH_SENSITIVITY_CLASS"]
                .eq("ALTO_PERSISTENTE_MAS_5PP")
                .sum()
            ),
            "interval_entirely_high": int(
                g["INTERVAL_POSITION_VS_HIGH"]
                .eq("INTERVAL_ENTIRELY_HIGH")
                .sum()
            ),
            "interval_crosses_high": int(
                g["INTERVAL_POSITION_VS_HIGH"]
                .eq("INTERVAL_CROSSES_HIGH")
                .sum()
            ),
            "pred_mean": g[
                "PRED_ABSTENCION_2027"
            ].mean(),
            "history_disagreement_median_pp": g[
                "HISTORY_DISAGREEMENT_PP"
            ].median(),
        })

    return pd.DataFrame(rows).sort_values(
        ["alto_persistente_mas_5pp", "high_sections"],
        ascending=False,
    )


def municipality_summary(df):
    rows = []

    group_cols = [
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
    ]

    for keys, g in df.groupby(
        group_cols,
        dropna=False,
    ):
        edo, edonom, mpio, mpionom = keys

        rows.append({
            "EDOCVE": edo,
            "entidad": edonom,
            "MPIOCVE": mpio,
            "municipio": mpionom,
            "sections": len(g),
            "high_sections": int(
                g["RISK_LEVEL"].eq("ALTO").sum()
            ),
            "priority_top10_sections": int(
                g["PRIORITY_TOP10"].sum()
            ),
            "alto_sensible_2pp": int(
                g["HIGH_SENSITIVITY_CLASS"]
                .eq("ALTO_SENSIBLE_2PP")
                .sum()
            ),
            "alto_sensible_5pp": int(
                g["HIGH_SENSITIVITY_CLASS"]
                .eq("ALTO_SENSIBLE_5PP")
                .sum()
            ),
            "alto_persistente_mas_5pp": int(
                g["HIGH_SENSITIVITY_CLASS"]
                .eq("ALTO_PERSISTENTE_MAS_5PP")
                .sum()
            ),
            "pred_mean": g[
                "PRED_ABSTENCION_2027"
            ].mean(),
            "history_disagreement_median_pp": g[
                "HISTORY_DISAGREEMENT_PP"
            ].median(),
        })

    out = pd.DataFrame(rows)

    out["high_share"] = (
        out["high_sections"] / out["sections"]
    )
    out["priority_top10_share"] = (
        out["priority_top10_sections"]
        / out["sections"]
    )

    return out.sort_values(
        [
            "alto_persistente_mas_5pp",
            "priority_top10_sections",
            "high_sections",
        ],
        ascending=False,
    )


def main():
    print(
        "\n=== 13 · Sensibilidad y persistencia del riesgo ==="
    )

    if not RISK_PATH.exists():
        raise FileNotFoundError(
            f"No existe {RISK_PATH}. "
            "Ejecuta primero src/11_calibrate_traffic_light.py"
        )

    th = load_thresholds()
    base = pd.read_parquet(RISK_PATH)

    required = {
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
        "PRED_ABSTENCION_2027",
        "PRED_LOWER_90_OOS",
        "PRED_UPPER_90_OOS",
        "RISK_LEVEL",
        "PRIORITY_TOP10",
        "HISTORY_DISAGREEMENT_PP",
    }
    missing = sorted(required - set(base.columns))
    if missing:
        raise RuntimeError(
            f"Faltan columnas requeridas: {missing}"
        )

    section = add_section_sensitivity(base, th)

    curve_high = build_curve(
        section,
        th,
        target_strategy="HIGH",
    )
    curve_top10 = build_curve(
        section,
        th,
        target_strategy="TOP10",
    )
    curves = pd.concat(
        [curve_high, curve_top10],
        ignore_index=True,
    )

    typology = typology_summary(section)
    intervals = interval_summary(section)
    states = state_summary(section)
    municipalities = municipality_summary(section)

    # Archivos grandes.
    section.to_parquet(
        OUT_DATA / "section_sensitivity_2027.parquet",
        index=False,
    )
    municipalities.to_parquet(
        OUT_DATA / "municipality_sensitivity_2027.parquet",
        index=False,
    )

    # Reportes pequeños.
    curves.to_csv(
        OUT_REPORT / "01_reduction_sensitivity_curve.csv",
        index=False,
    )
    typology.to_csv(
        OUT_REPORT / "02_high_risk_typology.csv",
        index=False,
    )
    intervals.to_csv(
        OUT_REPORT / "03_interval_position_summary.csv",
        index=False,
    )
    states.to_csv(
        OUT_REPORT / "04_state_sensitivity_summary.csv",
        index=False,
    )

    # Resumen municipal compacto: sólo municipios con ALTO o PRIORITY_TOP10.
    municipal_compact = municipalities.loc[
        (municipalities["high_sections"] > 0)
        | (municipalities["priority_top10_sections"] > 0)
    ].copy()

    municipal_compact.to_csv(
        OUT_REPORT / "05_municipality_priority_summary.csv",
        index=False,
    )

    # Parámetros de referencia 2 y 5 pp.
    selected_curve = curve_high[
        curve_high["assumed_reduction_pp"].isin(
            [0.0, 2.0, 5.0, 10.0]
        )
    ].copy()
    selected_curve.to_csv(
        OUT_REPORT / "06_selected_sensitivity_points.csv",
        index=False,
    )

    method = """# Sensibilidad y persistencia territorial del riesgo

## Objetivo

Esta etapa no estima efectos causales. Evalúa qué tan lejos se encuentra cada
territorio de los umbrales fijos del semáforo 2027.

## Distancia al umbral ALTO

Para cada sección clasificada como ALTO se calcula:

`GAP_TO_EXIT_HIGH_PP = (predicción - umbral_ALTO) * 100`

Esto permite una tipología descriptiva:

- `ALTO_SENSIBLE_2PP`: está a 2 pp o menos de salir de ALTO.
- `ALTO_SENSIBLE_5PP`: requiere más de 2 y hasta 5 pp.
- `ALTO_PERSISTENTE_MAS_5PP`: se encuentra más de 5 pp sobre el umbral.

La palabra "sensible" significa sensibilidad matemática al supuesto de escenario;
no implica que una intervención real consiga esa reducción.

## Curva de sensibilidad

Se simulan reducciones hipotéticas de 0 a 10 pp, cada 0.5 pp, aplicadas por
separado a:

1. todas las secciones ALTO;
2. únicamente las secciones PRIORITY_TOP10.

Los umbrales permanecen congelados en los valores del escenario base.

## Incertidumbre

También se compara el intervalo empírico OOS de cada sección con el umbral ALTO:

- `INTERVAL_BELOW_HIGH`
- `INTERVAL_CROSSES_HIGH`
- `INTERVAL_ENTIRELY_HIGH`

Esto no transforma el intervalo empírico en una probabilidad posterior. Es una
bandera de estabilidad relativa respecto al corte operativo.

## Uso

La tipología sirve para distinguir entre:

- riesgo alto cercano al umbral;
- riesgo alto que permanece lejos del umbral bajo supuestos moderados;
- territorios con alta incertidumbre alrededor del corte.

No constituye una recomendación automática de intervención.
"""
    (OUT_REPORT / "SENSITIVITY_METHOD.md").write_text(
        method,
        encoding="utf-8",
    )

    config = {
        "high_threshold": th["q80"],
        "priority_threshold": th["q90"],
        "sensitivity_grid_pp": [
            float(x) for x in REDUCTIONS_PP
        ],
        "classes": {
            "ALTO_SENSIBLE_2PP": (
                "baseline ALTO and gap_to_exit_high <= 2 pp"
            ),
            "ALTO_SENSIBLE_5PP": (
                "baseline ALTO and 2 < gap_to_exit_high <= 5 pp"
            ),
            "ALTO_PERSISTENTE_MAS_5PP": (
                "baseline ALTO and gap_to_exit_high > 5 pp"
            ),
        },
        "warning": (
            "Sensitivity classes describe distance to fixed thresholds; "
            "they are not causal intervention-effect estimates."
        ),
    }

    (
        OUT_REPORT / "sensitivity_config.json"
    ).write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nTipología de riesgo ALTO:")
    print(
        typology.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nCurva seleccionada · objetivo ALTO:")
    print(
        selected_curve[
            [
                "assumed_reduction_pp",
                "high_remaining",
                "high_exited",
                "share_baseline_high_exited",
                "priority_remaining",
                "priority_exited",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nPosición de intervalos respecto al umbral ALTO:")
    print(
        intervals.to_string(index=False)
    )

    print("\n=== Sensibilidad terminada ===")
    print(f"Datos: {OUT_DATA.relative_to(ROOT)}")
    print(f"Reportes: {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
