from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

RISK_PATH = (
    ROOT / "data" / "processed" / "risk_2027"
    / "section_risk_2027_primary.parquet"
)
TRAFFIC_CONFIG_PATH = (
    ROOT / "reports" / "risk_2027"
    / "traffic_light_config.json"
)

OUT_DATA = ROOT / "data" / "processed" / "scenarios_2027"
OUT_REPORT = ROOT / "reports" / "scenarios_2027"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# ESCENARIOS DE SENSIBILIDAD
#
# IMPORTANTE:
# Los valores de -2 pp y -5 pp NO son efectos causales estimados.
# Son supuestos transparentes para análisis de sensibilidad / planeación.
# ------------------------------------------------------------------
SCENARIOS = [
    {
        "scenario_id": "S0_BASELINE",
        "label": "Sin intervención",
        "target": "none",
        "delta_pp": 0.0,
        "description": (
            "Escenario base: conserva la estimación territorial 2027."
        ),
    },
    {
        "scenario_id": "S1_TOP10_MINUS2",
        "label": "Intervención focal Top10 · -2 pp",
        "target": "top10",
        "delta_pp": 2.0,
        "description": (
            "Supuesto de sensibilidad: reducción de 2 puntos porcentuales "
            "únicamente en las secciones PRIORITY_TOP10."
        ),
    },
    {
        "scenario_id": "S2_HIGH_MINUS2",
        "label": "Intervención focal ALTO · -2 pp",
        "target": "high",
        "delta_pp": 2.0,
        "description": (
            "Supuesto de sensibilidad: reducción de 2 puntos porcentuales "
            "en todas las secciones clasificadas como ALTO en el escenario base."
        ),
    },
    {
        "scenario_id": "S3_HIGH_MINUS5",
        "label": "Intervención focal ALTO · -5 pp",
        "target": "high",
        "delta_pp": 5.0,
        "description": (
            "Supuesto de sensibilidad más intenso: reducción de 5 puntos porcentuales "
            "en todas las secciones clasificadas como ALTO en el escenario base."
        ),
    },
]


def load_thresholds():
    if not TRAFFIC_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"No existe {TRAFFIC_CONFIG_PATH}. "
            "Ejecuta primero src/11_calibrate_traffic_light.py"
        )

    cfg = json.loads(TRAFFIC_CONFIG_PATH.read_text(encoding="utf-8"))
    th = cfg["2027_thresholds"]

    return {
        "q50": float(th["q50"]),
        "q80": float(th["q80"]),
        "q90": float(th["q90"]),
    }


def classify_fixed(score: pd.Series, thresholds):
    """
    Clasifica usando umbrales ABSOLUTOS congelados del escenario base.

    Esto es deliberado: si recalculáramos percentiles después de cada escenario,
    siempre habría 20% de secciones ALTO y no podríamos observar cambios de nivel.
    """
    s = pd.to_numeric(score, errors="coerce")

    level = np.select(
        [
            s.le(thresholds["q50"]),
            s.gt(thresholds["q50"]) & s.le(thresholds["q80"]),
            s.gt(thresholds["q80"]),
        ],
        [
            "BAJO",
            "MEDIO",
            "ALTO",
        ],
        default="SIN_CLASIFICAR",
    )

    priority = s.ge(thresholds["q90"])

    return level, priority


def scenario_mask(df, target):
    if target == "none":
        return pd.Series(False, index=df.index)

    if target == "top10":
        return df["PRIORITY_TOP10"].fillna(False).astype(bool)

    if target == "high":
        return df["RISK_LEVEL"].eq("ALTO")

    raise ValueError(f"Target de escenario no reconocido: {target}")


def weighted_mean(values, weights):
    v = pd.to_numeric(values, errors="coerce").to_numpy(float)
    w = pd.to_numeric(weights, errors="coerce").to_numpy(float)

    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if mask.sum() == 0:
        return np.nan

    return float(np.average(v[mask], weights=w[mask]))


def build_scenario(base, spec, thresholds):
    out = base.copy()

    out["SCENARIO_ID"] = spec["scenario_id"]
    out["SCENARIO_LABEL"] = spec["label"]
    out["SCENARIO_ASSUMED_DELTA_PP"] = spec["delta_pp"]

    targeted = scenario_mask(out, spec["target"])
    out["SCENARIO_TARGETED"] = targeted

    baseline = pd.to_numeric(
        out["PRED_ABSTENCION_2027"],
        errors="coerce",
    )

    reduction = np.where(
        targeted,
        spec["delta_pp"] / 100.0,
        0.0,
    )

    out["SCENARIO_REDUCTION_PP"] = reduction * 100.0

    out["SCENARIO_PRED_ABSTENCION"] = np.clip(
        baseline - reduction,
        0,
        1,
    )

    level, priority = classify_fixed(
        out["SCENARIO_PRED_ABSTENCION"],
        thresholds,
    )

    out["SCENARIO_RISK_LEVEL"] = level
    out["SCENARIO_PRIORITY_TOP10"] = priority

    out["BASELINE_RISK_LEVEL"] = out["RISK_LEVEL"].astype(str)
    out["BASELINE_PRIORITY_TOP10"] = (
        out["PRIORITY_TOP10"].fillna(False).astype(bool)
    )

    out["RISK_LEVEL_CHANGED"] = (
        out["SCENARIO_RISK_LEVEL"] != out["BASELINE_RISK_LEVEL"]
    )
    out["PRIORITY_CHANGED"] = (
        out["SCENARIO_PRIORITY_TOP10"]
        != out["BASELINE_PRIORITY_TOP10"]
    )

    return out


def summarize_scenario(df):
    baseline_mean = df["PRED_ABSTENCION_2027"].mean()
    scenario_mean = df["SCENARIO_PRED_ABSTENCION"].mean()

    baseline_weighted = weighted_mean(
        df["PRED_ABSTENCION_2027"],
        df["RECENT_LN"],
    )
    scenario_weighted = weighted_mean(
        df["SCENARIO_PRED_ABSTENCION"],
        df["RECENT_LN"],
    )

    baseline_high = int(df["BASELINE_RISK_LEVEL"].eq("ALTO").sum())
    scenario_high = int(df["SCENARIO_RISK_LEVEL"].eq("ALTO").sum())

    baseline_priority = int(df["BASELINE_PRIORITY_TOP10"].sum())
    scenario_priority = int(df["SCENARIO_PRIORITY_TOP10"].sum())

    return {
        "scenario_id": df["SCENARIO_ID"].iloc[0],
        "scenario_label": df["SCENARIO_LABEL"].iloc[0],
        "sections": len(df),
        "targeted_sections": int(df["SCENARIO_TARGETED"].sum()),
        "targeted_share": float(df["SCENARIO_TARGETED"].mean()),
        "assumed_delta_pp_targeted": float(
            df["SCENARIO_ASSUMED_DELTA_PP"].iloc[0]
        ),
        "baseline_mean_pred": float(baseline_mean),
        "scenario_mean_pred": float(scenario_mean),
        "mean_change_pp": float(
            (scenario_mean - baseline_mean) * 100
        ),
        "baseline_weighted_by_2024_ln": baseline_weighted,
        "scenario_weighted_by_2024_ln": scenario_weighted,
        "weighted_change_pp": float(
            (scenario_weighted - baseline_weighted) * 100
        ),
        "baseline_high_sections": baseline_high,
        "scenario_high_sections": scenario_high,
        "high_sections_change": scenario_high - baseline_high,
        "baseline_priority_top10_sections": baseline_priority,
        "scenario_priority_top10_sections": scenario_priority,
        "priority_sections_change": (
            scenario_priority - baseline_priority
        ),
        "sections_changed_level": int(
            df["RISK_LEVEL_CHANGED"].sum()
        ),
        "sections_changed_priority": int(
            df["PRIORITY_CHANGED"].sum()
        ),
    }


def transition_matrix(df):
    t = (
        df.groupby(
            ["BASELINE_RISK_LEVEL", "SCENARIO_RISK_LEVEL"],
            dropna=False,
        )
        .size()
        .rename("sections")
        .reset_index()
    )

    t["scenario_id"] = df["SCENARIO_ID"].iloc[0]
    t["scenario_label"] = df["SCENARIO_LABEL"].iloc[0]

    return t[
        [
            "scenario_id",
            "scenario_label",
            "BASELINE_RISK_LEVEL",
            "SCENARIO_RISK_LEVEL",
            "sections",
        ]
    ]


def state_summary(df):
    rows = []

    group_cols = ["EDOCVE", "RECENT_EDONOM"]

    for (edo, nombre), g in df.groupby(
        group_cols,
        dropna=False,
    ):
        rows.append({
            "scenario_id": g["SCENARIO_ID"].iloc[0],
            "scenario_label": g["SCENARIO_LABEL"].iloc[0],
            "EDOCVE": edo,
            "entidad": nombre,
            "sections": len(g),
            "targeted_sections": int(g["SCENARIO_TARGETED"].sum()),
            "baseline_mean_pred": g["PRED_ABSTENCION_2027"].mean(),
            "scenario_mean_pred": g["SCENARIO_PRED_ABSTENCION"].mean(),
            "mean_change_pp": (
                g["SCENARIO_PRED_ABSTENCION"].mean()
                - g["PRED_ABSTENCION_2027"].mean()
            ) * 100,
            "baseline_high_sections": int(
                g["BASELINE_RISK_LEVEL"].eq("ALTO").sum()
            ),
            "scenario_high_sections": int(
                g["SCENARIO_RISK_LEVEL"].eq("ALTO").sum()
            ),
            "baseline_priority_sections": int(
                g["BASELINE_PRIORITY_TOP10"].sum()
            ),
            "scenario_priority_sections": int(
                g["SCENARIO_PRIORITY_TOP10"].sum()
            ),
            "sections_changed_level": int(
                g["RISK_LEVEL_CHANGED"].sum()
            ),
        })

    return pd.DataFrame(rows)


def municipality_summary(df):
    rows = []

    group_cols = [
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
    ]

    for keys, g in df.groupby(group_cols, dropna=False):
        edo, edonom, mpio, mpionom = keys

        rows.append({
            "scenario_id": g["SCENARIO_ID"].iloc[0],
            "scenario_label": g["SCENARIO_LABEL"].iloc[0],
            "EDOCVE": edo,
            "entidad": edonom,
            "MPIOCVE": mpio,
            "municipio": mpionom,
            "sections": len(g),
            "targeted_sections": int(g["SCENARIO_TARGETED"].sum()),
            "baseline_mean_pred": g["PRED_ABSTENCION_2027"].mean(),
            "scenario_mean_pred": g["SCENARIO_PRED_ABSTENCION"].mean(),
            "mean_change_pp": (
                g["SCENARIO_PRED_ABSTENCION"].mean()
                - g["PRED_ABSTENCION_2027"].mean()
            ) * 100,
            "baseline_high_sections": int(
                g["BASELINE_RISK_LEVEL"].eq("ALTO").sum()
            ),
            "scenario_high_sections": int(
                g["SCENARIO_RISK_LEVEL"].eq("ALTO").sum()
            ),
            "sections_changed_level": int(
                g["RISK_LEVEL_CHANGED"].sum()
            ),
        })

    return pd.DataFrame(rows)


def main():
    print("\n=== 12 · Escenarios hipotéticos de intervención ===")

    if not RISK_PATH.exists():
        raise FileNotFoundError(
            f"No existe {RISK_PATH}. "
            "Ejecuta primero src/11_calibrate_traffic_light.py"
        )

    thresholds = load_thresholds()

    print(
        "Umbrales congelados del escenario base:\n"
        f"  BAJO <= {thresholds['q50']*100:.3f}%\n"
        f"  MEDIO <= {thresholds['q80']*100:.3f}%\n"
        f"  PRIORITY_TOP10 >= {thresholds['q90']*100:.3f}%"
    )

    base = pd.read_parquet(RISK_PATH)

    required = {
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
        "RECENT_LN",
        "PRED_ABSTENCION_2027",
        "RISK_LEVEL",
        "PRIORITY_TOP10",
    }
    missing = sorted(required - set(base.columns))
    if missing:
        raise RuntimeError(
            f"Faltan columnas en el semáforo: {missing}"
        )

    all_frames = []
    summary_rows = []
    transitions = []
    states = []
    municipalities = []

    for spec in SCENARIOS:
        scenario = build_scenario(
            base,
            spec,
            thresholds,
        )

        all_frames.append(scenario)
        summary_rows.append(summarize_scenario(scenario))
        transitions.append(transition_matrix(scenario))
        states.append(state_summary(scenario))
        municipalities.append(municipality_summary(scenario))

        s = summary_rows[-1]

        print(f"\n{spec['scenario_id']} · {spec['label']}")
        print(
            f"  objetivo: {s['targeted_sections']:,} secciones\n"
            f"  cambio medio global: {s['mean_change_pp']:.3f} pp\n"
            f"  ALTO: {s['baseline_high_sections']:,} → "
            f"{s['scenario_high_sections']:,}\n"
            f"  PRIORITY_TOP10: {s['baseline_priority_top10_sections']:,} → "
            f"{s['scenario_priority_top10_sections']:,}\n"
            f"  cambian de nivel: {s['sections_changed_level']:,}"
        )

    all_scenarios = pd.concat(
        all_frames,
        ignore_index=True,
    )

    summary = pd.DataFrame(summary_rows)
    transition_df = pd.concat(
        transitions,
        ignore_index=True,
    )
    state_df = pd.concat(
        states,
        ignore_index=True,
    )
    municipality_df = pd.concat(
        municipalities,
        ignore_index=True,
    )

    # Resultados pequeños versionables.
    summary.to_csv(
        OUT_REPORT / "01_scenario_summary.csv",
        index=False,
    )
    transition_df.to_csv(
        OUT_REPORT / "02_risk_level_transitions.csv",
        index=False,
    )
    state_df.to_csv(
        OUT_REPORT / "03_state_scenario_summary.csv",
        index=False,
    )

    # Resultados territoriales grandes: data/processed.
    all_scenarios.to_parquet(
        OUT_DATA / "section_scenarios_2027.parquet",
        index=False,
    )
    all_scenarios.to_csv(
        OUT_DATA / "section_scenarios_2027.csv.gz",
        index=False,
        compression="gzip",
    )
    municipality_df.to_parquet(
        OUT_DATA / "municipality_scenarios_2027.parquet",
        index=False,
    )

    # Configuración reproducible.
    config = {
        "classification_thresholds_frozen_from_baseline": thresholds,
        "scenarios": SCENARIOS,
        "interpretation": (
            "Scenario deltas are planning assumptions for sensitivity analysis. "
            "They are not causal estimates of any specific intervention."
        ),
        "important_design_choice": (
            "Risk thresholds remain fixed at baseline 2027 levels so that "
            "territories can move between categories under a scenario. "
            "Re-ranking each scenario would force 20% to remain ALTO."
        ),
    }

    (OUT_REPORT / "scenario_config.json").write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    method = """# Escenarios hipotéticos de intervención · metodología

## Objetivo

Los escenarios permiten explorar cómo cambiaría la priorización territorial bajo
supuestos explícitos de reducción de abstención estimada.

**No son estimaciones causales de efectividad de una política específica.**

## Escenario base

`S0_BASELINE` conserva la proyección territorial generada por el modelo bloqueado.

## Escenarios de sensibilidad

- `S1_TOP10_MINUS2`: supuesto de -2 pp únicamente en el Top10 prioritario.
- `S2_HIGH_MINUS2`: supuesto de -2 pp en todas las secciones ALTO.
- `S3_HIGH_MINUS5`: supuesto de -5 pp en todas las secciones ALTO.

Los valores 2 pp y 5 pp son parámetros de sensibilidad, no efectos históricos
atribuidos a una intervención real.

## Umbrales congelados

Los cortes del semáforo se mantienen fijos en los valores derivados del escenario
base 2027.

Esto es fundamental: si los percentiles se recalcularan dentro de cada escenario,
siempre habría un 20% de secciones clasificadas como ALTO, incluso después de una
mejora general. Con umbrales fijos es posible observar cuántas secciones cruzan de
ALTO a MEDIO o de MEDIO a BAJO.

## Lectura institucional

Los escenarios deben leerse como preguntas de planeación:

> "Si en los territorios priorizados se alcanzara una reducción de X puntos
> porcentuales respecto de la estimación base, ¿cómo cambiaría el mapa de riesgo?"

No deben leerse como:

> "La intervención causará una reducción de X puntos porcentuales."

## Próxima etapa

Estos escenarios deberán vincularse posteriormente con la cartografía oficial y
el dashboard, conservando siempre la diferencia entre:

- predicción histórica;
- nivel de riesgo relativo;
- incertidumbre;
- supuesto de escenario.
"""

    (OUT_REPORT / "SCENARIO_METHOD.md").write_text(
        method,
        encoding="utf-8",
    )

    print("\nResumen de escenarios:")
    print(
        summary[
            [
                "scenario_id",
                "targeted_sections",
                "mean_change_pp",
                "baseline_high_sections",
                "scenario_high_sections",
                "priority_sections_change",
                "sections_changed_level",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\n=== Escenarios terminados ===")
    print(f"Datos: {OUT_DATA.relative_to(ROOT)}")
    print(f"Reportes: {OUT_REPORT.relative_to(ROOT)}")
    print(
        "\nRecordatorio: los deltas de intervención son supuestos de sensibilidad, "
        "no efectos causales estimados."
    )


if __name__ == "__main__":
    main()
