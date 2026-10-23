"""Compara el semáforo 2027 oficial con el semáforo alternativo de Oscar.

- Oficial: regresión de dos historias sobre el universo primary_clean10
  (data/processed/sensitivity_2027/section_sensitivity_2027.parquet).
- Oscar: persistencia de la misma familia (abstención 2021) sobre todas las
  secciones con historia, sin filtro de NS
  (st_gcn_participation/modeling/outputs/risk_2027_sections.csv, que se genera
  al reproducir su trabajo; ver 01_generar_csv_oscar.py).

Ninguno de los dos se modifica: sólo se cruzan por sección.

Uso: python src/semaforo_oscar/02_comparar_semaforos.py
"""
from pathlib import Path
import importlib.util
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_PATH = ROOT / "data" / "processed" / "sensitivity_2027" / "section_sensitivity_2027.parquet"
QUALITY_PATH = ROOT / "data" / "processed" / "forecast_2027" / "forecast_2027_all_comparable.parquet"
OSCAR_PATH = ROOT / "st_gcn_participation" / "modeling" / "outputs" / "risk_2027_sections.csv"
OUT_DATA = ROOT / "data" / "processed" / "semaforo_oscar"
OUT_REPORT = ROOT / "reports" / "semaforo_oscar"

spec = importlib.util.spec_from_file_location("gen", Path(__file__).with_name("01_generar_csv_oscar.py"))
GEN = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GEN)
EDONOM_TO_CODE = {name: code for code, (name, _) in GEN.STATES.items()}

LEVELS = ["BAJO", "MEDIO", "ALTO"]
RANK = {lvl: i for i, lvl in enumerate(LEVELS)}


def load_oscar():
    risk = pd.read_csv(OSCAR_PATH)
    parts = risk["node"].str.rsplit(":", n=1, expand=True)
    state, section = parts[0], parts[1]
    risk["EDOCVE"] = state.map(EDONOM_TO_CODE)
    if risk["EDOCVE"].isna().any():
        raise RuntimeError(f"Estados sin clave: {sorted(state[risk['EDOCVE'].isna()].unique())}")
    risk["SECTION_KEY"] = (
        risk["EDOCVE"].astype(int).astype(str).str.zfill(2) + "-" + section.astype(int).astype(str).str.zfill(4)
    )
    return risk.rename(columns={
        "predicted_abstention": "PRED_OSCAR",
        "risk_level": "NIVEL_OSCAR",
        "priority_top10": "TOP10_OSCAR",
        "risk_percentile": "PERCENTIL_OSCAR",
    })[["SECTION_KEY", "EDOCVE", "PRED_OSCAR", "NIVEL_OSCAR", "TOP10_OSCAR", "PERCENTIL_OSCAR"]]


def load_official():
    off = pd.read_parquet(OFFICIAL_PATH)
    return off.rename(columns={
        "PRED_ABSTENCION_2027": "PRED_OFICIAL",
        "RISK_LEVEL": "NIVEL_OFICIAL",
        "PRIORITY_TOP10": "TOP10_OFICIAL",
        "RISK_PERCENTILE": "PERCENTIL_OFICIAL",
        "RECENT_EDONOM": "ESTADO",
        "RECENT_MPIONOM": "MUNICIPIO",
    })[["SECTION_KEY", "EDOCVE", "ESTADO", "MUNICIPIO", "PRED_OFICIAL", "NIVEL_OFICIAL",
        "TOP10_OFICIAL", "PERCENTIL_OFICIAL", "SAME_PCT_ABSTENCION"]]


def thresholds(pred):
    return {q: float(pred.quantile(v)) for q, v in [("q50", 0.5), ("q80", 0.8), ("q90", 0.9)]}


def main():
    print("\n=== Comparación de semáforos: oficial vs. Oscar ===")
    for p in [OFFICIAL_PATH, OSCAR_PATH]:
        if not p.exists():
            raise FileNotFoundError(f"No existe {p}")
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)

    off, osc = load_official(), load_oscar()
    both = off.merge(osc, on=["SECTION_KEY", "EDOCVE"], how="outer", indicator=True)
    both["UNIVERSO"] = both["_merge"].map({"both": "ambos", "left_only": "solo_oficial", "right_only": "solo_oscar"})
    both = both.drop(columns="_merge")

    # Por qué una sección está sólo en el semáforo de Oscar: filtros del oficial.
    if QUALITY_PATH.exists():
        q = pd.read_parquet(QUALITY_PATH, columns=["SECTION_KEY", "QUALITY_FLAG", "RECENT_EDONOM", "RECENT_MPIONOM"])
        both = both.merge(q, on="SECTION_KEY", how="left")
        both["ESTADO"] = both["ESTADO"].fillna(both["RECENT_EDONOM"])
        both["MUNICIPIO"] = both["MUNICIPIO"].fillna(both["RECENT_MPIONOM"])
        both = both.drop(columns=["RECENT_EDONOM", "RECENT_MPIONOM"])
    both["QUALITY_FLAG"] = both.get("QUALITY_FLAG", pd.Series(index=both.index, dtype=object)).fillna("sin_dato_comparable")
    both["ESTADO"] = both["ESTADO"].fillna(both["EDOCVE"].map(lambda c: GEN.STATES[int(c)][0]))

    m = both["UNIVERSO"].eq("ambos")
    both["DIF_PP"] = (both["PRED_OSCAR"] - both["PRED_OFICIAL"]) * 100
    step = both["NIVEL_OSCAR"].map(RANK) - both["NIVEL_OFICIAL"].map(RANK)
    both["COMPARACION"] = np.select(
        [~m, step.eq(0), step.gt(0), step.lt(0)],
        [both["UNIVERSO"], "coincide", "oscar_mas_alto", "oscar_mas_bajo"],
        default="sin_dato",
    )
    both.to_parquet(OUT_DATA / "comparacion_secciones.parquet", index=False)

    th_off = thresholds(both.loc[both["PRED_OFICIAL"].notna(), "PRED_OFICIAL"])
    th_osc = thresholds(both.loc[both["PRED_OSCAR"].notna(), "PRED_OSCAR"])
    pd.DataFrame([
        {"semaforo": "oficial", "secciones": int(both["PRED_OFICIAL"].notna().sum()),
         "abstencion_media": float(both["PRED_OFICIAL"].mean()), **th_off},
        {"semaforo": "oscar", "secciones": int(both["PRED_OSCAR"].notna().sum()),
         "abstencion_media": float(both["PRED_OSCAR"].mean()), **th_osc},
    ]).to_csv(OUT_REPORT / "01_umbrales_y_universos.csv", index=False)

    matrix = pd.crosstab(both.loc[m, "NIVEL_OFICIAL"], both.loc[m, "NIVEL_OSCAR"]).reindex(index=LEVELS, columns=LEVELS, fill_value=0)
    matrix.to_csv(OUT_REPORT / "02_matriz_niveles.csv")

    by_state = (
        both.groupby(["EDOCVE", "ESTADO"])
        .agg(
            secciones_ambos=("UNIVERSO", lambda u: int(u.eq("ambos").sum())),
            solo_oscar=("UNIVERSO", lambda u: int(u.eq("solo_oscar").sum())),
            solo_oficial=("UNIVERSO", lambda u: int(u.eq("solo_oficial").sum())),
            coincide=("COMPARACION", lambda c: int(c.eq("coincide").sum())),
            alto_oficial=("NIVEL_OFICIAL", lambda n: int(n.eq("ALTO").sum())),
            alto_oscar=("NIVEL_OSCAR", lambda n: int(n.eq("ALTO").sum())),
            dif_media_pp=("DIF_PP", "mean"),
        )
        .reset_index()
    )
    by_state["pct_coincide"] = by_state["coincide"] / by_state["secciones_ambos"].replace(0, np.nan)
    by_state.sort_values("pct_coincide").to_csv(OUT_REPORT / "03_por_estado.csv", index=False)

    only_osc = both.loc[both["UNIVERSO"].eq("solo_oscar"), "QUALITY_FLAG"].value_counts()
    only_osc.rename_axis("motivo").rename("secciones").to_csv(OUT_REPORT / "04_motivos_solo_oscar.csv")

    agree = float(both.loc[m, "COMPARACION"].eq("coincide").mean())
    top_agree = float((both.loc[m, "TOP10_OFICIAL"].astype(bool) == both.loc[m, "TOP10_OSCAR"].astype(bool)).mean())
    # Coincidencia esperada si los niveles fueran independientes (con los mismos tamaños).
    p_off = both.loc[m, "NIVEL_OFICIAL"].value_counts(normalize=True)
    p_osc = both.loc[m, "NIVEL_OSCAR"].value_counts(normalize=True)
    chance = float(sum(p_off.get(l, 0) * p_osc.get(l, 0) for l in LEVELS))
    corr = float(both.loc[m, ["PRED_OFICIAL", "PRED_OSCAR"]].corr(method="spearman").iloc[0, 1])
    summary = {
        "secciones_ambos": int(m.sum()),
        "solo_oscar": int(both["UNIVERSO"].eq("solo_oscar").sum()),
        "solo_oficial": int(both["UNIVERSO"].eq("solo_oficial").sum()),
        "coincidencia_nivel": agree,
        "coincidencia_esperada_al_azar": chance,
        "coincidencia_top10": top_agree,
        "spearman_estimaciones": corr,
        "dif_media_pp": float(both.loc[m, "DIF_PP"].mean()),
        "umbrales_oficial": th_off,
        "umbrales_oscar": th_osc,
        "comparacion": both.loc[m, "COMPARACION"].value_counts().to_dict(),
        "motivos_solo_oscar": only_osc.to_dict(),
    }
    (OUT_REPORT / "comparacion_config.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary, matrix, by_state)

    print(f"  En ambos: {summary['secciones_ambos']:,} · sólo Oscar: {summary['solo_oscar']:,} · sólo oficial: {summary['solo_oficial']:,}")
    print(f"  Mismo nivel: {agree:.1%} (al azar: {chance:.1%}) · mismo Top10: {top_agree:.1%} · Spearman {corr:.3f}")
    print(f"  Oscar − oficial: {summary['dif_media_pp']:+.2f} pp en promedio")
    print(f"Salida: {(OUT_DATA / 'comparacion_secciones.parquet').relative_to(ROOT)} · {OUT_REPORT.relative_to(ROOT)}")


def write_report(s, matrix, by_state):
    def pct(x):
        return f"{x:.1%}"

    mrows = "\n".join(
        f"| {lvl} | " + " | ".join(f"{int(matrix.loc[lvl, c]):,}" for c in LEVELS) + " |" for lvl in LEVELS
    )
    worst = by_state.dropna(subset=["pct_coincide"]).nsmallest(5, "pct_coincide")
    wrows = "\n".join(
        f"| {r.ESTADO} | {r.secciones_ambos:,} | {pct(r.pct_coincide)} | {r.dif_media_pp:+.1f} | {r.alto_oficial:,} / {r.alto_oscar:,} |"
        for r in worst.itertuples()
    )
    motives = "\n".join(f"| `{k}` | {v:,} |" for k, v in s["motivos_solo_oscar"].items())
    to, tc = s["umbrales_oficial"], s["umbrales_oscar"]
    text = f"""# Semáforo 2027: oficial vs. alternativo de Oscar

Generado por `src/semaforo_oscar/02_comparar_semaforos.py`. Ninguno de los dos
semáforos se modifica; sólo se cruzan por sección.

## Qué compara

| | Oficial | Oscar |
|---|---|---|
| Estimación | `two_history_linear`: 0.048 + 0.677 × abst. 2021 + 0.180 × abst. 2024 | Persistencia: abstención 2021 (misma familia) |
| Universo | `primary_clean10`: NS ≤ 10% y sin cambios de municipio/tipo | Todas las secciones con historia comparable |
| Umbrales BAJO / MEDIO / Top10 | ≤ {to['q50']:.1%} / ≤ {to['q80']:.1%} / ≥ {to['q90']:.1%} | ≤ {tc['q50']:.1%} / ≤ {tc['q80']:.1%} / ≥ {tc['q90']:.1%} |

Los dos usan la misma regla relativa (percentiles 50, 80 y 90 de su propio universo).

## Resultados

- Secciones en ambos: {s['secciones_ambos']:,}. Sólo en el de Oscar: {s['solo_oscar']:,}. Sólo en el oficial: {s['solo_oficial']:,}.
- **Mismo nivel: {pct(s['coincidencia_nivel'])}** (si fueran independientes coincidirían {pct(s['coincidencia_esperada_al_azar'])}).
- Misma marca Top10: {pct(s['coincidencia_top10'])}. Correlación de Spearman entre estimaciones: {s['spearman_estimaciones']:.3f}.
- La estimación de Oscar es en promedio {s['dif_media_pp']:+.2f} pp distinta de la oficial
  (persistencia de 2021, una intermedia con más abstención, sin el ajuste hacia 2024).

Niveles (filas = oficial, columnas = Oscar):

| Oficial \\ Oscar | BAJO | MEDIO | ALTO |
|---|---|---|---|
{mrows}

Estados con menor coincidencia:

| Estado | Secciones en ambos | Mismo nivel | Oscar − oficial (pp) | ALTO oficial / Oscar |
|---|---|---|---|---|
{wrows}

Por qué hay secciones sólo en el semáforo de Oscar (filtro de calidad del oficial):

| Motivo | Secciones |
|---|---|
{motives}

## Lectura

Las diferencias vienen de dos decisiones, no de errores: Oscar no aplica el filtro
de NS ni de estabilidad (por eso cubre más secciones, incluidas las de NS alto que
el dashboard oficial muestra en violeta), y usa persistencia en lugar de la
regresión.

En los backtests, la regresión de dos historias tiene menor error que la
persistencia en 2021 y 2024 (7.69 vs. 9.91 pp y 4.36 vs. 4.72 pp). En 2018 pierde
(11.35 vs. 4.77 pp; `03_backtest_2018.py`). Ahí sólo puede entrenarse con la
ventana de 2015, una intermedia, y sobreestima la abstención de una presidencial
por +10.9 pp. 2015 no se puede evaluar porque no hay ventana anterior.
"""
    (OUT_REPORT / "COMPARACION.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
