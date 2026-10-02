from pathlib import Path
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
OUT = ROOT / "reports" / "eda"
FIG = OUT / "figures"

OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
INTERMEDIAS = [2009, 2015, 2021]
PRESIDENCIALES = [2012, 2018, 2024]

AGE_LABELS = ["18_24", "25_34", "35_44", "45_59", "60_plus"]
SEX_LABELS = ["H", "M"]


def safe_div(num, den):
    den = np.asarray(den, dtype=float)
    num = np.asarray(num, dtype=float)
    out = np.full_like(num, np.nan, dtype=float)
    mask = den != 0
    out[mask] = num[mask] / den[mask]
    return out


def weighted_rate(df, num_col, den_cols):
    den = sum(df[c].sum() for c in den_cols)
    if den == 0:
        return np.nan
    return df[num_col].sum() / den


def regression_metrics(y_true, y_pred):
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = np.asarray(y_true, dtype=float)[mask]
    y_pred = np.asarray(y_pred, dtype=float)[mask]

    if len(y_true) == 0:
        return {
            "n": 0, "mae": np.nan, "rmse": np.nan,
            "r2": np.nan, "pearson_r": np.nan
        }

    err = y_true - y_pred
    mae = np.mean(np.abs(err))
    rmse = np.sqrt(np.mean(err ** 2))
    denom = np.sum((y_true - y_true.mean()) ** 2)
    r2 = 1 - np.sum(err ** 2) / denom if denom > 0 else np.nan
    pearson = np.corrcoef(y_true, y_pred)[0, 1] if len(y_true) > 1 else np.nan

    return {
        "n": int(len(y_true)),
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2),
        "pearson_r": float(pearson),
    }


def valid_pair_filter(df, ns_threshold=None):
    mask = (
        df["PREV_PCT_ABSTENCION"].notna()
        & df["PCT_ABSTENCION"].notna()
        & ~df["FLAG_DENOM_ZERO"].fillna(False)
    )

    if "STABLE_MUNICIPALITY_ALL_YEARS" in df.columns:
        mask &= df["STABLE_MUNICIPALITY_ALL_YEARS"].fillna(False)

    if "STABLE_TIPO_ALL_YEARS" in df.columns:
        mask &= df["STABLE_TIPO_ALL_YEARS"].fillna(False)

    if ns_threshold is not None:
        mask &= df["PCT_NS_LN"].le(ns_threshold)
        mask &= df["PREV_PCT_NS_LN"].le(ns_threshold)

    return mask


def save_line_plot(df, x, y, title, ylabel, filename):
    plt.figure(figsize=(8, 5))
    plt.plot(df[x], df[y], marker="o")
    plt.title(title)
    plt.xlabel("Año electoral")
    plt.ylabel(ylabel)
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(FIG / filename, dpi=180)
    plt.close()


def save_scatter(df, x, y, title, xlabel, ylabel, filename):
    d = df[[x, y]].dropna()
    if len(d) == 0:
        return
    plt.figure(figsize=(7, 6))
    plt.hexbin(d[x], d[y], gridsize=55, mincnt=1)
    lo = min(d[x].min(), d[y].min())
    hi = max(d[x].max(), d[y].max())
    plt.plot([lo, hi], [lo, hi], linestyle="--")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(FIG / filename, dpi=180)
    plt.close()


def main():
    if not MASTER.exists():
        raise FileNotFoundError(
            f"No existe {MASTER}. Ejecuta primero src/02_build_master.py"
        )

    print("\n=== 03 · Análisis exploratorio CCPC ===")
    print(f"Leyendo: {MASTER.relative_to(ROOT)}")
    df = pd.read_csv(MASTER, low_memory=False)

    print(f"Filas: {len(df):,}")
    print(f"Columnas: {df.shape[1]}")

    # ------------------------------------------------------------------
    # 1) Resumen nacional ponderado por año
    # ------------------------------------------------------------------
    national_rows = []
    for year in YEARS:
        d = df[df["AELEC"] == year]
        denom = d["SV"].sum() + d["NV"].sum()
        national_rows.append({
            "AELEC": year,
            "sections": len(d),
            "LN": d["LN"].sum(),
            "SV": d["SV"].sum(),
            "NV": d["NV"].sum(),
            "NS": d["NS"].sum(),
            "PCT_PARTICIPACION": d["SV"].sum() / denom if denom else np.nan,
            "PCT_ABSTENCION": d["NV"].sum() / denom if denom else np.nan,
            "PCT_NS_LN": d["NS"].sum() / d["LN"].sum() if d["LN"].sum() else np.nan,
        })
    national = pd.DataFrame(national_rows)
    national.to_csv(OUT / "01_national_summary.csv", index=False)

    # ------------------------------------------------------------------
    # 2) Distribución a nivel sección
    # ------------------------------------------------------------------
    dist_rows = []
    for year in YEARS:
        d = df[df["AELEC"] == year]
        for col in ["PCT_ABSTENCION", "PCT_NS_LN", "LN", "EDAD_PROM_LN"]:
            s = pd.to_numeric(d[col], errors="coerce").dropna()
            if s.empty:
                continue
            dist_rows.append({
                "AELEC": year,
                "variable": col,
                "n": len(s),
                "mean": s.mean(),
                "std": s.std(),
                "min": s.min(),
                "p05": s.quantile(0.05),
                "p25": s.quantile(0.25),
                "median": s.median(),
                "p75": s.quantile(0.75),
                "p95": s.quantile(0.95),
                "max": s.max(),
            })
    pd.DataFrame(dist_rows).to_csv(OUT / "02_section_distributions.csv", index=False)

    # ------------------------------------------------------------------
    # 3) Calidad NS por año
    # ------------------------------------------------------------------
    ns_rows = []
    for year in YEARS:
        d = df[df["AELEC"] == year]
        ns_rows.append({
            "AELEC": year,
            "sections": len(d),
            "denom_zero": int(d["FLAG_DENOM_ZERO"].fillna(False).sum()),
            "ns_gt_05": int(d["PCT_NS_LN"].gt(0.05).sum()),
            "ns_gt_10": int(d["PCT_NS_LN"].gt(0.10).sum()),
            "ns_gt_25": int(d["PCT_NS_LN"].gt(0.25).sum()),
            "ns_gt_50": int(d["PCT_NS_LN"].gt(0.50).sum()),
            "pct_sections_ns_gt_10": d["PCT_NS_LN"].gt(0.10).mean(),
        })
    pd.DataFrame(ns_rows).to_csv(OUT / "03_ns_quality.csv", index=False)

    # ------------------------------------------------------------------
    # 4) Tipo de sección: tasas ponderadas
    # ------------------------------------------------------------------
    tipo_rows = []
    for (year, tipo), d in df.groupby(["AELEC", "TIPOSEC"], dropna=False):
        denom = d["SV"].sum() + d["NV"].sum()
        tipo_rows.append({
            "AELEC": int(year),
            "TIPOSEC": tipo,
            "sections": len(d),
            "LN": d["LN"].sum(),
            "PCT_PARTICIPACION": d["SV"].sum() / denom if denom else np.nan,
            "PCT_ABSTENCION": d["NV"].sum() / denom if denom else np.nan,
            "PCT_NS_LN": d["NS"].sum() / d["LN"].sum() if d["LN"].sum() else np.nan,
        })
    pd.DataFrame(tipo_rows).to_csv(OUT / "04_by_section_type.csv", index=False)

    # ------------------------------------------------------------------
    # 5) Participación y composición por etapa de vida
    # ------------------------------------------------------------------
    age_rows = []
    for year in YEARS:
        d = df[df["AELEC"] == year]
        for label in AGE_LABELS:
            sv = d[f"SV_{label}"].sum()
            nv = d[f"NV_{label}"].sum()
            ln = d[f"LN_{label}"].sum()
            age_rows.append({
                "AELEC": year,
                "grupo_edad": label,
                "LN": ln,
                "PCT_LN": ln / d["LN"].sum() if d["LN"].sum() else np.nan,
                "PCT_PARTICIPACION": sv / (sv + nv) if (sv + nv) else np.nan,
                "PCT_ABSTENCION": nv / (sv + nv) if (sv + nv) else np.nan,
            })
    age_summary = pd.DataFrame(age_rows)
    age_summary.to_csv(OUT / "05_age_summary.csv", index=False)

    # ------------------------------------------------------------------
    # 6) Participación por sexo
    # ------------------------------------------------------------------
    sex_rows = []
    for year in YEARS:
        d = df[df["AELEC"] == year]
        for label in SEX_LABELS:
            sv = d[f"SV_{label}"].sum()
            nv = d[f"NV_{label}"].sum()
            ln = d[f"LN_{label}"].sum()
            sex_rows.append({
                "AELEC": year,
                "sexo": label,
                "LN": ln,
                "PCT_LN": ln / d["LN"].sum() if d["LN"].sum() else np.nan,
                "PCT_PARTICIPACION": sv / (sv + nv) if (sv + nv) else np.nan,
                "PCT_ABSTENCION": nv / (sv + nv) if (sv + nv) else np.nan,
            })
    pd.DataFrame(sex_rows).to_csv(OUT / "06_sex_summary.csv", index=False)

    # ------------------------------------------------------------------
    # 7) Baseline de persistencia: abstención anterior = predicción
    # ------------------------------------------------------------------
    baseline_rows = []
    target_years = [2015, 2018, 2021, 2024]

    for year in target_years:
        d = df[df["AELEC"] == year].copy()
        mask = valid_pair_filter(d, ns_threshold=None)
        m = regression_metrics(
            d.loc[mask, "PCT_ABSTENCION"].to_numpy(),
            d.loc[mask, "PREV_PCT_ABSTENCION"].to_numpy(),
        )
        baseline_rows.append({
            "target_year": year,
            "tipo_eleccion": d["TIPO_ELECCION"].dropna().iloc[0] if len(d) else "",
            "ns_filter": "none",
            **m,
        })

    baseline = pd.DataFrame(baseline_rows)
    baseline.to_csv(OUT / "07_persistence_baseline.csv", index=False)

    # ------------------------------------------------------------------
    # 8) Sensibilidad del baseline al filtro de NS
    # ------------------------------------------------------------------
    sens_rows = []
    thresholds = [
        ("none", None),
        ("25pct", 0.25),
        ("10pct", 0.10),
        ("05pct", 0.05),
    ]

    for year in target_years:
        d = df[df["AELEC"] == year].copy()
        for label, threshold in thresholds:
            mask = valid_pair_filter(d, ns_threshold=threshold)
            m = regression_metrics(
                d.loc[mask, "PCT_ABSTENCION"].to_numpy(),
                d.loc[mask, "PREV_PCT_ABSTENCION"].to_numpy(),
            )
            sens_rows.append({
                "target_year": year,
                "tipo_eleccion": d["TIPO_ELECCION"].dropna().iloc[0] if len(d) else "",
                "ns_filter": label,
                **m,
            })

    sensitivity = pd.DataFrame(sens_rows)
    sensitivity.to_csv(OUT / "08_ns_sensitivity_baseline.csv", index=False)

    # ------------------------------------------------------------------
    # 9) Cambios longitudinales pareados
    # ------------------------------------------------------------------
    change_rows = []
    for year in target_years:
        d = df[df["AELEC"] == year].copy()
        mask = valid_pair_filter(d, ns_threshold=0.10)
        vals = d.loc[mask, "DELTA_ABST_VS_PREV"].dropna()

        change_rows.append({
            "target_year": year,
            "tipo_eleccion": d["TIPO_ELECCION"].dropna().iloc[0] if len(d) else "",
            "n": len(vals),
            "mean_delta": vals.mean(),
            "median_delta": vals.median(),
            "p25_delta": vals.quantile(0.25),
            "p75_delta": vals.quantile(0.75),
            "share_increase": (vals > 0).mean(),
            "share_decrease": (vals < 0).mean(),
        })
    pd.DataFrame(change_rows).to_csv(OUT / "09_longitudinal_changes.csv", index=False)

    # ------------------------------------------------------------------
    # 10) Correlaciones exploratorias SOLO con variables potencialmente
    #     disponibles antes de conocer el resultado actual.
    # ------------------------------------------------------------------
    safe_candidate_cols = [
        "PREV_PCT_ABSTENCION",
        "PREV_PCT_PARTICIPACION",
        "PREV_LN",
        "PREV_PCT_NS_LN",
        "PREV_EDAD_PROM_LN",
        "PREV_PROP_LN_18_24",
        "PREV_PROP_LN_25_34",
        "PREV_PROP_LN_60_plus",
        "TREND_ABST_2_INTERVALS",
    ]

    corr_rows = []
    for year in [2021, 2024]:
        d = df[df["AELEC"] == year].copy()
        mask = valid_pair_filter(d, ns_threshold=0.10)
        d = d.loc[mask]

        for col in safe_candidate_cols:
            if col not in d.columns:
                continue
            pair = d[["PCT_ABSTENCION", col]].dropna()
            if len(pair) < 2:
                continue
            corr_rows.append({
                "target_year": year,
                "variable": col,
                "n": len(pair),
                "pearson_r": pair["PCT_ABSTENCION"].corr(pair[col], method="pearson"),
                "spearman_r": pair["PCT_ABSTENCION"].corr(pair[col], method="spearman"),
            })

    pd.DataFrame(corr_rows).to_csv(OUT / "10_safe_feature_correlations.csv", index=False)

    # ------------------------------------------------------------------
    # 11) Figuras
    # ------------------------------------------------------------------
    inter = national[national["AELEC"].isin(INTERMEDIAS)].copy()
    pres = national[national["AELEC"].isin(PRESIDENCIALES)].copy()

    save_line_plot(
        inter, "AELEC", "PCT_ABSTENCION",
        "Abstención nacional · elecciones intermedias",
        "Proporción de abstención",
        "abstention_intermedias.png",
    )

    save_line_plot(
        pres, "AELEC", "PCT_ABSTENCION",
        "Abstención nacional · elecciones presidenciales",
        "Proporción de abstención",
        "abstention_presidenciales.png",
    )

    for year in [2021, 2024]:
        d = df[df["AELEC"] == year].copy()
        mask = valid_pair_filter(d, ns_threshold=0.10)
        save_scatter(
            d.loc[mask],
            "PREV_PCT_ABSTENCION",
            "PCT_ABSTENCION",
            f"Baseline de persistencia · {year}",
            "Abstención en elección comparable anterior",
            f"Abstención observada {year}",
            f"baseline_scatter_{year}.png",
        )

    # ------------------------------------------------------------------
    # 12) Reporte textual compacto
    # ------------------------------------------------------------------
    report = []
    report.append("# EDA CCPC 2009–2024\n")
    report.append(f"- Filas de la base maestra: **{len(df):,}**")
    report.append(f"- Columnas: **{df.shape[1]}**\n")

    report.append("## Baseline de persistencia\n")
    for _, r in baseline.iterrows():
        report.append(
            f"- {int(r['target_year'])}: n={int(r['n']):,}, "
            f"MAE={r['mae']:.4f}, RMSE={r['rmse']:.4f}, "
            f"R²={r['r2']:.4f}, r={r['pearson_r']:.4f}"
        )

    report.append("\n## Archivos generados\n")
    for name in [
        "01_national_summary.csv",
        "02_section_distributions.csv",
        "03_ns_quality.csv",
        "04_by_section_type.csv",
        "05_age_summary.csv",
        "06_sex_summary.csv",
        "07_persistence_baseline.csv",
        "08_ns_sensitivity_baseline.csv",
        "09_longitudinal_changes.csv",
        "10_safe_feature_correlations.csv",
    ]:
        report.append(f"- `{name}`")

    (OUT / "EDA_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    print("\n=== EDA terminada ===")
    print(f"Resultados: {OUT.relative_to(ROOT)}")
    print("\nBaseline de persistencia:")
    print(baseline.to_string(index=False))
    print("\nSensibilidad NS:")
    print(sensitivity.to_string(index=False))
    print("\nSiguiente control recomendado:")
    print("python -c \"import pandas as pd; print(pd.read_csv('reports/eda/07_persistence_baseline.csv').to_string(index=False))\"")


if __name__ == "__main__":
    main()
