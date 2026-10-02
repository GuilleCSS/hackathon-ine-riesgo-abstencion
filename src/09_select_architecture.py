from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ROBUST = ROOT / "reports" / "robustness"
OUT = ROOT / "reports" / "model_selection"
OUT.mkdir(parents=True, exist_ok=True)

EVIDENCE_PATH = ROBUST / "05_selection_evidence.csv"
ENTITY_PATH = ROBUST / "03_entity_metrics.csv"

TEMPORAL_EXPERIMENTS = [
    "2021_temporal_dual",
    "2024_temporal_dual",
]

BASELINE = "baseline_same_family"


def pct(x):
    return float(x) * 100.0



def df_to_markdown(df: pd.DataFrame) -> str:
    """Convierte un DataFrame pequeño a tabla Markdown sin depender de tabulate."""
    if df.empty:
        return "_Sin datos._"

    work = df.copy()

    def fmt(v):
        if pd.isna(v):
            return ""
        if isinstance(v, (float, np.floating)):
            return f"{float(v):.4f}"
        return str(v)

    headers = [str(c) for c in work.columns]
    rows = [[fmt(v) for v in row] for row in work.itertuples(index=False, name=None)]

    def esc(s):
        return str(s).replace("|", r"\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(esc(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(esc(v) for v in row) + " |")
    return "\n".join(lines)

def main():
    print("\n=== 09 · Selección formal de arquitectura ===")

    if not EVIDENCE_PATH.exists():
        raise FileNotFoundError(
            f"No existe {EVIDENCE_PATH}. Ejecuta primero src/08_robustness_model_selection.py"
        )
    if not ENTITY_PATH.exists():
        raise FileNotFoundError(
            f"No existe {ENTITY_PATH}. Ejecuta primero src/08_robustness_model_selection.py"
        )

    evidence = pd.read_csv(EVIDENCE_PATH)
    entity = pd.read_csv(ENTITY_PATH)

    ev = evidence[
        evidence["experiment"].isin(TEMPORAL_EXPERIMENTS)
    ].copy()

    # --------------------------------------------------------------
    # 1) Métricas relativas al baseline de misma familia.
    # --------------------------------------------------------------
    baseline = ev[
        ev["model"].eq(BASELINE)
    ][
        [
            "experiment",
            "mae_pp",
            "rmse_pp",
            "r2",
            "top20_overlap",
            "top10_overlap",
            "bias_pp",
        ]
    ].rename(
        columns={
            "mae_pp": "baseline_mae_pp",
            "rmse_pp": "baseline_rmse_pp",
            "r2": "baseline_r2",
            "top20_overlap": "baseline_top20",
            "top10_overlap": "baseline_top10",
            "bias_pp": "baseline_bias_pp",
        }
    )

    ev = ev.merge(baseline, on="experiment", how="left", validate="many_to_one")

    ev["mae_ratio_vs_baseline"] = ev["mae_pp"] / ev["baseline_mae_pp"]
    ev["mae_improvement_pp"] = ev["baseline_mae_pp"] - ev["mae_pp"]
    ev["mae_improvement_pct"] = (
        ev["mae_improvement_pp"] / ev["baseline_mae_pp"] * 100
    )
    ev["r2_gain"] = ev["r2"] - ev["baseline_r2"]
    ev["top20_gain"] = ev["top20_overlap"] - ev["baseline_top20"]
    ev["top10_gain"] = ev["top10_overlap"] - ev["baseline_top10"]

    ev.to_csv(OUT / "01_temporal_evidence_relative.csv", index=False)

    # --------------------------------------------------------------
    # 2) Regla de elegibilidad.
    #
    # Un método sólo puede considerarse candidato principal si:
    # - supera al baseline en MAE en ambos backtests temporales, y
    # - el IC95% bootstrap de ΔMAE está completamente por debajo de 0
    #   en ambos años.
    #
    # Después se usa un criterio minimax:
    # minimizar el peor cociente MAE_modelo / MAE_baseline entre 2021 y 2024.
    # Esto evita seleccionar un método excelente en un año pero frágil en otro.
    # --------------------------------------------------------------
    candidate_rows = []

    for model, g in ev.groupby("model"):
        g = g[g["experiment"].isin(TEMPORAL_EXPERIMENTS)].copy()

        if len(g) != len(TEMPORAL_EXPERIMENTS):
            continue

        improved_each_year = bool((g["mae_pp"] < g["baseline_mae_pp"]).all())
        robust_each_year = bool(
            g["mae_improvement_supported_95pct"].fillna(False).astype(bool).all()
        )

        candidate_rows.append({
            "model": model,
            "years_evaluated": len(g),
            "improved_mae_both_years": improved_each_year,
            "bootstrap_improvement_95pct_both_years": robust_each_year,
            "eligible_primary": bool(improved_each_year and robust_each_year),
            "max_mae_ratio_vs_baseline": g["mae_ratio_vs_baseline"].max(),
            "mean_mae_ratio_vs_baseline": g["mae_ratio_vs_baseline"].mean(),
            "mean_mae_improvement_pct": g["mae_improvement_pct"].mean(),
            "worst_mae_improvement_pct": g["mae_improvement_pct"].min(),
            "mean_r2": g["r2"].mean(),
            "worst_r2": g["r2"].min(),
            "mean_top20": g["top20_overlap"].mean(),
            "worst_top20": g["top20_overlap"].min(),
            "mean_top10": g["top10_overlap"].mean(),
            "max_abs_bias_pp": g["bias_pp"].abs().max(),
        })

    candidates = pd.DataFrame(candidate_rows)

    # El baseline no puede seleccionarse como "mejora" de sí mismo.
    candidates.loc[
        candidates["model"].eq(BASELINE),
        ["eligible_primary"]
    ] = False

    candidates = candidates.sort_values(
        by=[
            "eligible_primary",
            "max_mae_ratio_vs_baseline",
            "mean_mae_ratio_vs_baseline",
            "mean_top20",
        ],
        ascending=[False, True, True, False],
    ).reset_index(drop=True)

    candidates.to_csv(OUT / "02_candidate_summary.csv", index=False)

    eligible = candidates[candidates["eligible_primary"]].copy()

    if eligible.empty:
        selected_model = BASELINE
        selection_status = "fallback_baseline"
        selection_reason = (
            "Ningún candidato logró una mejora robusta de MAE frente al baseline "
            "en ambos backtests temporales. Se conserva la persistencia de misma familia."
        )
    else:
        # Minimax de error relativo. En caso de empate: menor error medio y
        # posteriormente mayor capacidad media de priorización Top20.
        eligible = eligible.sort_values(
            by=[
                "max_mae_ratio_vs_baseline",
                "mean_mae_ratio_vs_baseline",
                "mean_top20",
            ],
            ascending=[True, True, False],
        )
        selected_model = eligible.iloc[0]["model"]
        selection_status = "selected_by_predefined_rule"
        selection_reason = (
            "El modelo fue elegible por mejorar el MAE del baseline con soporte "
            "bootstrap al 95% en 2021 y 2024. Entre los elegibles, minimizó el peor "
            "cociente MAE_modelo/MAE_baseline entre ambos backtests."
        )

    print(f"\nArquitectura seleccionada por la regla: {selected_model}")

    # --------------------------------------------------------------
    # 3) Estabilidad por entidad: comparar cada candidato con baseline.
    # --------------------------------------------------------------
    ent = entity[
        entity["experiment"].isin(TEMPORAL_EXPERIMENTS)
    ].copy()

    ent_base = ent[
        ent["model"].eq(BASELINE)
    ][
        [
            "experiment",
            "EDOCVE",
            "entidad",
            "mae_pp",
            "r2",
            "top20_overlap",
        ]
    ].rename(
        columns={
            "mae_pp": "baseline_entity_mae_pp",
            "r2": "baseline_entity_r2",
            "top20_overlap": "baseline_entity_top20",
        }
    )

    ent_compare = ent.merge(
        ent_base,
        on=["experiment", "EDOCVE", "entidad"],
        how="left",
        validate="many_to_one",
    )

    ent_compare["delta_entity_mae_pp"] = (
        ent_compare["mae_pp"] - ent_compare["baseline_entity_mae_pp"]
    )
    ent_compare["delta_entity_r2"] = (
        ent_compare["r2"] - ent_compare["baseline_entity_r2"]
    )
    ent_compare["delta_entity_top20"] = (
        ent_compare["top20_overlap"] - ent_compare["baseline_entity_top20"]
    )

    ent_compare.to_csv(OUT / "03_entity_comparison_vs_baseline.csv", index=False)

    geo_rows = []

    for (experiment, model), g in ent_compare.groupby(["experiment", "model"]):
        geo_rows.append({
            "experiment": experiment,
            "model": model,
            "entities": g["EDOCVE"].nunique(),
            "entities_lower_mae_than_baseline": int((g["delta_entity_mae_pp"] < 0).sum()),
            "share_entities_lower_mae": float((g["delta_entity_mae_pp"] < 0).mean()),
            "median_delta_entity_mae_pp": g["delta_entity_mae_pp"].median(),
            "p90_delta_entity_mae_pp": g["delta_entity_mae_pp"].quantile(0.90),
            "max_delta_entity_mae_pp": g["delta_entity_mae_pp"].max(),
            "median_delta_entity_top20": g["delta_entity_top20"].median(),
        })

    geo_summary = pd.DataFrame(geo_rows)
    geo_summary.to_csv(OUT / "04_entity_stability_summary.csv", index=False)

    # --------------------------------------------------------------
    # 4) Reporte de selección.
    # --------------------------------------------------------------
    selected_ev = ev[ev["model"].eq(selected_model)].copy()
    selected_geo = geo_summary[geo_summary["model"].eq(selected_model)].copy()

    selected_entity = ent_compare[
        ent_compare["model"].eq(selected_model)
    ].copy()

    worst_state_tables = {}
    for experiment in TEMPORAL_EXPERIMENTS:
        w = selected_entity[
            selected_entity["experiment"].eq(experiment)
        ].sort_values(
            "delta_entity_mae_pp",
            ascending=False,
        ).head(8)

        worst_state_tables[experiment] = w[
            [
                "EDOCVE",
                "entidad",
                "mae_pp",
                "baseline_entity_mae_pp",
                "delta_entity_mae_pp",
                "top20_overlap",
                "baseline_entity_top20",
            ]
        ]

    report = []
    report.append("# Selección formal de arquitectura")
    report.append("")
    report.append("## Regla de selección")
    report.append("")
    report.append(
        "1. El método debe mejorar el MAE frente a `baseline_same_family` "
        "en los backtests temporales 2021 y 2024."
    )
    report.append(
        "2. La mejora debe conservarse con bootstrap agrupado por municipio: "
        "el límite superior del IC95% de ΔMAE debe permanecer por debajo de cero."
    )
    report.append(
        "3. Entre los métodos elegibles se minimiza el peor cociente "
        "`MAE_modelo / MAE_baseline` observado entre ambos años (criterio minimax)."
    )
    report.append(
        "4. La estabilidad por entidad se reporta como diagnóstico adicional; "
        "no se usa para escoger retrospectivamente un modelo distinto por estado."
    )
    report.append("")
    report.append("## Resultado")
    report.append("")
    report.append(f"**Arquitectura seleccionada:** `{selected_model}`")
    report.append("")
    report.append(f"**Estado:** `{selection_status}`")
    report.append("")
    report.append(selection_reason)
    report.append("")
    report.append("## Desempeño temporal de la arquitectura seleccionada")
    report.append("")

    display_cols = [
        "experiment",
        "n",
        "mae_pp",
        "rmse_pp",
        "r2",
        "spearman_r",
        "top20_overlap",
        "top10_overlap",
        "bias_pp",
        "mae_improvement_pct",
        "delta_mae_vs_same_family_ci_low",
        "delta_mae_vs_same_family_ci_high",
    ]

    report.append(
        df_to_markdown(
            selected_ev[display_cols].round(4)
        )
    )
    report.append("")
    report.append("## Estabilidad geográfica")
    report.append("")

    if not selected_geo.empty:
        geo_display = selected_geo.copy()
        geo_display["share_entities_lower_mae"] = (
            geo_display["share_entities_lower_mae"] * 100
        )
        report.append(
            df_to_markdown(
                geo_display[
                    [
                        "experiment",
                        "entities",
                        "entities_lower_mae_than_baseline",
                        "share_entities_lower_mae",
                        "median_delta_entity_mae_pp",
                        "p90_delta_entity_mae_pp",
                        "max_delta_entity_mae_pp",
                    ]
                ].round(4)
            )
        )

    report.append("")
    report.append(
        "Un ΔMAE por entidad negativo indica que la arquitectura seleccionada "
        "tiene menor error que la persistencia de misma familia."
    )
    report.append("")

    for experiment, table in worst_state_tables.items():
        report.append(f"### Entidades con mayor degradación relativa · {experiment}")
        report.append("")
        if table.empty:
            report.append("Sin datos.")
        else:
            report.append(df_to_markdown(table.round(4)))
        report.append("")

    report.append("## Uso metodológico")
    report.append("")
    report.append(
        "La arquitectura seleccionada se utilizará como estimador puntual primario "
        "en la siguiente fase. Los baselines se conservarán como referencias de "
        "auditoría. La selección no se modifica posteriormente en función del "
        "resultado futuro que se desea estimar."
    )
    report.append("")
    report.append(
        "La incertidumbre futura se estimará por separado a partir de errores "
        "fuera de muestra de los backtests temporales; no debe interpretarse como "
        "una garantía probabilística bajo cambios estructurales no observados."
    )

    report_path = OUT / "ARCHITECTURE_SELECTION_REPORT.md"
    report_path.write_text("\n".join(report), encoding="utf-8")

    # --------------------------------------------------------------
    # 5) Lock de arquitectura para que los siguientes scripts no cambien
    # silenciosamente de estimador.
    # --------------------------------------------------------------
    selected_row = candidates[
        candidates["model"].eq(selected_model)
    ].iloc[0].to_dict()

    config = {
        "selected_model": selected_model,
        "selection_status": selection_status,
        "selection_rule": {
            "required_temporal_backtests": TEMPORAL_EXPERIMENTS,
            "baseline": BASELINE,
            "require_mae_improvement_each_year": True,
            "require_bootstrap_95pct_improvement_each_year": True,
            "primary_criterion": "minimize_max_mae_ratio_vs_baseline",
            "tie_breakers": [
                "minimize_mean_mae_ratio_vs_baseline",
                "maximize_mean_top20_overlap",
            ],
        },
        "selected_summary": {
            k: (bool(v) if isinstance(v, (np.bool_, bool))
                else float(v) if isinstance(v, (np.floating, float))
                else int(v) if isinstance(v, (np.integer, int))
                else v)
            for k, v in selected_row.items()
            if not pd.isna(v)
        },
        "note": (
            "Archivo generado por 09_select_architecture.py. "
            "Los scripts posteriores deben leer este lock en lugar de escoger "
            "retrospectivamente un modelo."
        ),
    }

    with (OUT / "selected_architecture.json").open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print("\nCandidatos:")
    print(
        candidates[
            [
                "model",
                "eligible_primary",
                "max_mae_ratio_vs_baseline",
                "mean_mae_improvement_pct",
                "mean_top20",
                "max_abs_bias_pp",
            ]
        ].to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nEstabilidad geográfica del seleccionado:")
    if selected_geo.empty:
        print("Sin datos.")
    else:
        print(
            selected_geo.to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )

    print("\n=== Selección terminada ===")
    print(f"Modelo bloqueado: {selected_model}")
    print(f"Reporte: {report_path.relative_to(ROOT)}")
    print("Lock: reports/model_selection/selected_architecture.json")


if __name__ == "__main__":
    main()
