from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PRED_DIR = ROOT / "reports" / "dual_history" / "predictions"
OUT = ROOT / "reports" / "robustness"
OUT.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42
N_BOOT = 400

EXPERIMENTS = {
    "2021_temporal_dual": PRED_DIR / "predictions_2021_temporal_dual.parquet",
    "2024_temporal_dual": PRED_DIR / "predictions_2024_temporal_dual.parquet",
}

PREDICTION_COLUMNS = {
    "baseline_same_family": "PRED_baseline_same_family",
    "baseline_recent_election": "PRED_baseline_recent_election",
    "baseline_equal_blend": "PRED_baseline_equal_blend",
    "baseline_weighted_blend": "PRED_baseline_weighted_blend",
    "two_history_linear": "PRED_two_history_linear",
    "dual_history_ridge": "PRED_dual_history_ridge",
    "dual_history_hgb": "PRED_dual_history_hgb",
}


def metrics(y, p):
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    mask = np.isfinite(y) & np.isfinite(p)
    y = y[mask]
    p = p[mask]

    err = p - y
    mae = np.mean(np.abs(err))
    rmse = np.sqrt(np.mean(err ** 2))
    denom = np.sum((y - y.mean()) ** 2)
    r2 = 1 - np.sum(err ** 2) / denom if denom > 0 else np.nan
    spearman = pd.Series(y).corr(pd.Series(p), method="spearman")
    bias = np.mean(err)

    def overlap(frac):
        k = max(1, int(np.ceil(len(y) * frac)))
        actual = np.argpartition(y, -k)[-k:]
        pred = np.argpartition(p, -k)[-k:]
        return len(np.intersect1d(actual, pred)) / k

    return {
        "n": len(y),
        "mae_pp": mae * 100,
        "rmse_pp": rmse * 100,
        "r2": r2,
        "spearman_r": spearman,
        "top20_overlap": overlap(0.20),
        "top10_overlap": overlap(0.10),
        "bias_pp": bias * 100,
    }


def cluster_bootstrap(df, pred_col, baseline_col):
    """
    Bootstrap por municipio para conservar parcialmente la dependencia espacial.
    Reporta intervalos para métricas del modelo y para la diferencia de MAE
    frente al baseline_same_family:
        delta_mae_pp = MAE(modelo) - MAE(baseline)
    Valores negativos favorecen al modelo.
    """
    rng = np.random.default_rng(RANDOM_STATE)

    # Evitar columnas duplicadas cuando pred_col == baseline_col
    # (por ejemplo, al evaluar baseline_same_family contra sí mismo).
    selected_cols = list(dict.fromkeys([
        "Y_ABSTENCION",
        pred_col,
        baseline_col,
        "EDOCVE",
        "TGT_MPIOCVE",
    ]))
    work = df[selected_cols].copy()

    work["CLUSTER"] = (
        work["EDOCVE"].astype("Int64").astype(str)
        + "-"
        + work["TGT_MPIOCVE"].astype("Int64").astype(str)
    )

    groups = {
        k: g.index.to_numpy()
        for k, g in work.groupby("CLUSTER", sort=False)
    }
    cluster_ids = np.array(list(groups.keys()), dtype=object)

    rows = []
    for _ in range(N_BOOT):
        sampled = rng.choice(cluster_ids, size=len(cluster_ids), replace=True)
        idx = np.concatenate([groups[c] for c in sampled])

        boot = work.loc[idx]
        y = boot["Y_ABSTENCION"].to_numpy(float)
        p = boot[pred_col].to_numpy(float)
        b = boot[baseline_col].to_numpy(float)

        m = metrics(y, p)
        mae_model = np.mean(np.abs(p - y)) * 100
        mae_base = np.mean(np.abs(b - y)) * 100

        rows.append({
            "mae_pp": m["mae_pp"],
            "rmse_pp": m["rmse_pp"],
            "r2": m["r2"],
            "top20_overlap": m["top20_overlap"],
            "delta_mae_vs_same_family_pp": mae_model - mae_base,
        })

    return pd.DataFrame(rows)


def qci(s):
    s = pd.Series(s).dropna()
    return (
        float(s.quantile(0.025)),
        float(s.median()),
        float(s.quantile(0.975)),
    )


def main():
    print("\n=== 08 · Robustez y selección metodológica ===")
    print(f"Bootstrap por municipio: {N_BOOT} réplicas")

    summary_rows = []
    bootstrap_rows = []
    entity_rows = []

    for experiment, path in EXPERIMENTS.items():
        if not path.exists():
            raise FileNotFoundError(
                f"No existe {path}. Ejecuta primero src/07_dual_history_backtest.py"
            )

        df = pd.read_parquet(path)
        print(f"\n{experiment}: {len(df):,} secciones")

        required = {
            "Y_ABSTENCION", "EDOCVE", "TGT_EDONOM", "TGT_MPIOCVE",
            *PREDICTION_COLUMNS.values()
        }
        missing = sorted(required - set(df.columns))
        if missing:
            raise RuntimeError(f"Faltan columnas en {path.name}: {missing}")

        y = df["Y_ABSTENCION"].to_numpy(float)
        base_col = PREDICTION_COLUMNS["baseline_same_family"]

        for model, pred_col in PREDICTION_COLUMNS.items():
            p = df[pred_col].to_numpy(float)
            m = metrics(y, p)

            summary_rows.append({
                "experiment": experiment,
                "model": model,
                **m,
            })

            boot = cluster_bootstrap(df, pred_col, base_col)

            mae_lo, mae_med, mae_hi = qci(boot["mae_pp"])
            rmse_lo, rmse_med, rmse_hi = qci(boot["rmse_pp"])
            r2_lo, r2_med, r2_hi = qci(boot["r2"])
            top_lo, top_med, top_hi = qci(boot["top20_overlap"])
            d_lo, d_med, d_hi = qci(boot["delta_mae_vs_same_family_pp"])

            bootstrap_rows.append({
                "experiment": experiment,
                "model": model,
                "mae_pp_ci_low": mae_lo,
                "mae_pp_median": mae_med,
                "mae_pp_ci_high": mae_hi,
                "rmse_pp_ci_low": rmse_lo,
                "rmse_pp_median": rmse_med,
                "rmse_pp_ci_high": rmse_hi,
                "r2_ci_low": r2_lo,
                "r2_median": r2_med,
                "r2_ci_high": r2_hi,
                "top20_ci_low": top_lo,
                "top20_median": top_med,
                "top20_ci_high": top_hi,
                "delta_mae_vs_same_family_ci_low": d_lo,
                "delta_mae_vs_same_family_median": d_med,
                "delta_mae_vs_same_family_ci_high": d_hi,
                "mae_improvement_supported_95pct": bool(d_hi < 0),
            })

            # Desempeño por entidad para detectar degradación geográfica.
            for (edo, nombre), g in df.groupby(["EDOCVE", "TGT_EDONOM"], dropna=False):
                gm = metrics(
                    g["Y_ABSTENCION"].to_numpy(float),
                    g[pred_col].to_numpy(float)
                )
                entity_rows.append({
                    "experiment": experiment,
                    "model": model,
                    "EDOCVE": edo,
                    "entidad": nombre,
                    **gm,
                })

            print(
                f"  {model:<26} "
                f"MAE={m['mae_pp']:.3f} pp · "
                f"R²={m['r2']:.3f} · "
                f"Top20={m['top20_overlap']:.3f} · "
                f"ΔMAE95%=[{d_lo:.3f}, {d_hi:.3f}]"
            )

    summary = pd.DataFrame(summary_rows)
    boot_summary = pd.DataFrame(bootstrap_rows)
    entity = pd.DataFrame(entity_rows)

    summary.to_csv(OUT / "01_overall_metrics.csv", index=False)
    boot_summary.to_csv(OUT / "02_cluster_bootstrap.csv", index=False)
    entity.to_csv(OUT / "03_entity_metrics.csv", index=False)

    # Resumen de estabilidad geográfica.
    geo_rows = []
    for (experiment, model), g in entity.groupby(["experiment", "model"]):
        geo_rows.append({
            "experiment": experiment,
            "model": model,
            "entities": g["EDOCVE"].nunique(),
            "entity_mae_median_pp": g["mae_pp"].median(),
            "entity_mae_p90_pp": g["mae_pp"].quantile(0.90),
            "entity_mae_max_pp": g["mae_pp"].max(),
            "entity_r2_median": g["r2"].median(),
            "entity_top20_median": g["top20_overlap"].median(),
        })
    geo = pd.DataFrame(geo_rows)
    geo.to_csv(OUT / "04_geographic_stability.csv", index=False)

    # Tabla de evidencia unificada. No "elige" automáticamente un modelo:
    # deja la decisión documentada para la siguiente etapa.
    evidence = summary.merge(
        boot_summary,
        on=["experiment", "model"],
        how="left"
    ).merge(
        geo,
        on=["experiment", "model"],
        how="left"
    )
    evidence.to_csv(OUT / "05_selection_evidence.csv", index=False)

    print("\n=== Robustez terminada ===")
    print(f"Resultados: {OUT.relative_to(ROOT)}")
    print("\nArchivos:")
    print("  - reports/robustness/01_overall_metrics.csv")
    print("  - reports/robustness/02_cluster_bootstrap.csv")
    print("  - reports/robustness/03_entity_metrics.csv")
    print("  - reports/robustness/04_geographic_stability.csv")
    print("  - reports/robustness/05_selection_evidence.csv")


if __name__ == "__main__":
    main()
