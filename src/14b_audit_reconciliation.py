from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

AUDIT_PATH = (
    ROOT / "data" / "processed" / "cartography_2027"
    / "risk_cartography_key_audit.parquet"
)

OUT = ROOT / "reports" / "cartography_2027"
OUT.mkdir(parents=True, exist_ok=True)


def safe_rate(num, den):
    return float(num / den) if den else np.nan


def main():
    print("\n=== 14B · Auditoría fina de conciliación cartográfica ===")

    if not AUDIT_PATH.exists():
        raise FileNotFoundError(
            f"No existe {AUDIT_PATH}. Ejecuta primero src/14_reconcile_cartography.py"
        )

    df = pd.read_parquet(AUDIT_PATH)

    required = {
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
        "RECENT_TIPOSEC",
        "RISK_LEVEL",
        "PRIORITY_TOP10",
        "HIGH_SENSITIVITY_CLASS",
        "PRED_ABSTENCION_2027",
        "HAS_GEOMETRY",
        "CARTO_MPIOCVE",
        "CARTO_TIPOSEC",
        "MUNICIPALITY_MATCH",
        "TYPE_MATCH",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"Faltan columnas esperadas: {missing}")

    matched = df.loc[df["HAS_GEOMETRY"]].copy()
    unmatched = df.loc[~df["HAS_GEOMETRY"]].copy()

    # --------------------------------------------------------------
    # 1) Diagnóstico de tipo de sección
    # --------------------------------------------------------------
    type_source = (
        matched["RECENT_TIPOSEC"]
        .astype("string")
        .str.strip()
        .str.upper()
    )
    type_carto = (
        matched["CARTO_TIPOSEC"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    type_pairs = pd.DataFrame({
        "RECENT_TIPOSEC": type_source,
        "CARTO_TIPOSEC": type_carto,
    })

    type_cross = (
        type_pairs.groupby(
            ["RECENT_TIPOSEC", "CARTO_TIPOSEC"],
            dropna=False,
        )
        .size()
        .rename("sections")
        .reset_index()
        .sort_values("sections", ascending=False)
    )

    type_cross.to_csv(
        OUT / "09_type_code_crosswalk_diagnostic.csv",
        index=False,
    )

    source_counts = (
        type_source.value_counts(dropna=False)
        .rename_axis("RECENT_TIPOSEC")
        .rename("sections")
        .reset_index()
    )
    source_counts.to_csv(
        OUT / "10_recent_tiposec_values.csv",
        index=False,
    )

    carto_counts = (
        type_carto.value_counts(dropna=False)
        .rename_axis("CARTO_TIPOSEC")
        .rename("sections")
        .reset_index()
    )
    carto_counts.to_csv(
        OUT / "11_cartography_tiposec_values.csv",
        index=False,
    )

    # Dominant mapping from historical -> cartographic code.
    dominant_rows = []
    for src, g in type_cross.groupby("RECENT_TIPOSEC", dropna=False):
        total = g["sections"].sum()
        top = g.iloc[0]
        dominant_rows.append({
            "RECENT_TIPOSEC": src,
            "dominant_CARTO_TIPOSEC": top["CARTO_TIPOSEC"],
            "dominant_sections": int(top["sections"]),
            "total_sections": int(total),
            "purity": safe_rate(top["sections"], total),
        })

    dominant = pd.DataFrame(dominant_rows)
    dominant.to_csv(
        OUT / "12_type_dominant_mapping.csv",
        index=False,
    )

    # Heuristic only: if every historical category maps overwhelmingly to one
    # cartographic code and those dominant codes are distinct, likely a code-set
    # mismatch rather than a true territorial mismatch.
    likely_code_mapping = False
    if not dominant.empty:
        purity_ok = bool((dominant["purity"] >= 0.95).all())
        unique_targets = (
            dominant["dominant_CARTO_TIPOSEC"].nunique(dropna=False)
            == len(dominant)
        )
        likely_code_mapping = purity_ok and unique_targets

    # --------------------------------------------------------------
    # 2) Municipality mismatches
    # --------------------------------------------------------------
    mun_mismatch = matched.loc[
        matched["MUNICIPALITY_MATCH"].eq(False)
    ].copy()

    mun_cols = [
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
        "CARTO_MPIOCVE",
        "RISK_LEVEL",
        "PRIORITY_TOP10",
        "PRED_ABSTENCION_2027",
    ]
    mun_mismatch[mun_cols].to_csv(
        OUT / "13_municipality_mismatches_detail.csv",
        index=False,
    )

    # --------------------------------------------------------------
    # 3) Unmatched sections: where and how important are they?
    # --------------------------------------------------------------
    unmatched_state = (
        unmatched.groupby(
            ["EDOCVE", "RECENT_EDONOM"],
            dropna=False,
        )
        .agg(
            unmatched_sections=("SECTION_KEY", "size"),
            high_sections=(
                "RISK_LEVEL",
                lambda s: int((s == "ALTO").sum()),
            ),
            priority_top10_sections=(
                "PRIORITY_TOP10",
                lambda s: int(pd.Series(s).fillna(False).astype(bool).sum()),
            ),
            persistent_high_gt5pp=(
                "HIGH_SENSITIVITY_CLASS",
                lambda s: int((s == "ALTO_PERSISTENTE_MAS_5PP").sum()),
            ),
            pred_mean=("PRED_ABSTENCION_2027", "mean"),
            pred_max=("PRED_ABSTENCION_2027", "max"),
        )
        .reset_index()
        .sort_values(
            ["unmatched_sections", "priority_top10_sections"],
            ascending=False,
        )
    )

    unmatched_state.to_csv(
        OUT / "14_unmatched_by_state_and_risk.csv",
        index=False,
    )

    risk_order = pd.CategoricalDtype(
        ["BAJO", "MEDIO", "ALTO"],
        ordered=True,
    )
    unmatched["RISK_LEVEL_ORDERED"] = unmatched["RISK_LEVEL"].astype(risk_order)

    unmatched_detail = unmatched[
        [
            "SECTION_KEY",
            "EDOCVE",
            "RECENT_EDONOM",
            "RECENT_MPIOCVE",
            "RECENT_MPIONOM",
            "RECENT_TIPOSEC",
            "RISK_LEVEL",
            "PRIORITY_TOP10",
            "HIGH_SENSITIVITY_CLASS",
            "PRED_ABSTENCION_2027",
        ]
    ].sort_values(
        ["PRIORITY_TOP10", "PRED_ABSTENCION_2027"],
        ascending=[False, False],
    )

    unmatched_detail.to_csv(
        OUT / "15_unmatched_sections_prioritized.csv",
        index=False,
    )

    # --------------------------------------------------------------
    # 4) Coverage diagnostics by risk class
    # --------------------------------------------------------------
    coverage_risk = (
        df.groupby("RISK_LEVEL", dropna=False)
        .agg(
            sections=("SECTION_KEY", "size"),
            matched=("HAS_GEOMETRY", "sum"),
        )
        .reset_index()
    )
    coverage_risk["match_rate"] = (
        coverage_risk["matched"] / coverage_risk["sections"]
    )
    coverage_risk.to_csv(
        OUT / "16_match_rate_by_risk_level.csv",
        index=False,
    )

    coverage_priority = (
        df.assign(
            PRIORITY_LABEL=np.where(
                df["PRIORITY_TOP10"].fillna(False).astype(bool),
                "TOP10",
                "NO_TOP10",
            )
        )
        .groupby("PRIORITY_LABEL", dropna=False)
        .agg(
            sections=("SECTION_KEY", "size"),
            matched=("HAS_GEOMETRY", "sum"),
        )
        .reset_index()
    )
    coverage_priority["match_rate"] = (
        coverage_priority["matched"]
        / coverage_priority["sections"]
    )
    coverage_priority.to_csv(
        OUT / "17_match_rate_by_priority.csv",
        index=False,
    )

    # --------------------------------------------------------------
    # 5) Machine-readable decision aid
    # --------------------------------------------------------------
    summary = {
        "matched_sections": int(len(matched)),
        "unmatched_sections": int(len(unmatched)),
        "overall_match_rate": safe_rate(len(matched), len(df)),
        "municipality_mismatches": int(len(mun_mismatch)),
        "recent_tiposec_unique_values": [
            None if pd.isna(x) else str(x)
            for x in source_counts["RECENT_TIPOSEC"].tolist()
        ],
        "cartography_tiposec_unique_values": [
            None if pd.isna(x) else str(x)
            for x in carto_counts["CARTO_TIPOSEC"].tolist()
        ],
        "likely_tiposec_code_mapping_issue": bool(likely_code_mapping),
        "unmatched_high_sections": int(
            unmatched["RISK_LEVEL"].eq("ALTO").sum()
        ),
        "unmatched_priority_top10_sections": int(
            unmatched["PRIORITY_TOP10"].fillna(False).astype(bool).sum()
        ),
        "unmatched_persistent_high_gt5pp": int(
            unmatched["HIGH_SENSITIVITY_CLASS"]
            .eq("ALTO_PERSISTENTE_MAS_5PP")
            .sum()
        ),
    }

    (OUT / "14b_diagnostic_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --------------------------------------------------------------
    # Terminal output
    # --------------------------------------------------------------
    print("\nValores TIPOSEC históricos:")
    print(source_counts.to_string(index=False))

    print("\nValores TIPOSEC cartográficos:")
    print(carto_counts.to_string(index=False))

    print("\nCruce TIPOSEC histórico ↔ cartográfico (principales):")
    print(type_cross.head(20).to_string(index=False))

    print("\nMapeo dominante:")
    print(
        dominant.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    if likely_code_mapping:
        print(
            "\n[DIAGNÓSTICO] Los mismatches de TIPOSEC parecen deberse "
            "principalmente a sistemas de codificación diferentes, no a "
            "54 mil cambios territoriales reales."
        )
    else:
        print(
            "\n[DIAGNÓSTICO] El patrón TIPOSEC no permite inferir todavía "
            "un simple cambio de códigos. Hay que revisar el campo detectado."
        )

    print("\nMismatches de municipio:")
    if mun_mismatch.empty:
        print("  Ninguno.")
    else:
        print(
            mun_mismatch[mun_cols].to_string(
                index=False,
                float_format=lambda x: f"{x:.4f}",
            )
        )

    print("\nSecciones sin geometría por entidad:")
    print(
        unmatched_state.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nCobertura por nivel de riesgo:")
    print(
        coverage_risk.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\nCobertura Top10:")
    print(
        coverage_priority.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\n=== Auditoría 14B terminada ===")
    print(f"Reportes: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
