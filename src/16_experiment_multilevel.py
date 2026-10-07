"""Isolated temporal experiment: section aggregation versus direct territories.

Run from the project root: python src/16_experiment_multilevel.py
No dashboard, locked architecture or production forecast is modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import signal
import time
from datetime import datetime, timezone

# Bound native threads before importing numpy/sklearn.
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data/processed/section_election_master_v1.csv.gz"
OUT = ROOT / "reports/experiment_multilevel"
DATA = ROOT / "data/processed/experiment_multilevel"
AGES = ["18_24", "25_34", "35_44", "45_59", "60_plus"]
GROUPS = ["H", "M"] + AGES
LEVELS = {
    "entidad": ["EDOCVE"],
    "municipio": ["EDOCVE", "MPIOCVE"],
    "distrito_federal": ["EDOCVE", "DEF"],
    "distrito_local": ["EDOCVE", "DEL"],
}
RAW_SUM = ["LN", "SV", "NV", "NS", "AGE_LN_SUM", "AGE_SV_SUM"]
RAW_SUM += [f"{c}_{g}" for g in GROUPS for c in ["LN", "SV", "NV"]]
BASE = ["PCT_ABSTENCION"]
DEMO = ["LOG_LN", "EDAD_PROM_LN", "PROP_LN_M", "PROP_U", "PROP_R"]
DEMO += [f"PROP_LN_{g}" for g in AGES]
BEHAVIOR = [f"PCT_ABST_{g}" for g in GROUPS]
BEHAVIOR += ["BRECHA_M_H", "BRECHA_JOVEN_MAYOR", "EDAD_VOTANTE_MENOS_LN"]
CONTEXT = ["MUN_ABST", "STATE_ABST", "NATIONAL_ABST", "GAP_MUN", "GAP_STATE",
           "WEIGHT_MUN", "WEIGHT_STATE", "WEIGHT_NATIONAL", "QUALITY_NS"]
EXPECTED = ["EXPECTED_MUN_AGE", "EXPECTED_STATE_AGE", "EXCESS_MUN_AGE", "EXCESS_STATE_AGE"]
TREND = ["TREND_FAMILY", "PREV_FAMILY_ABST", "GROWTH_LN_FAMILY", "DELTA_AGE_FAMILY"]
CAT = ["EDOCVE", "TIPO_ELECCION"]


def divide(n, d):
    return n / d.where(d > 0)


def derive(d):
    d = d.copy()
    den = d.SV + d.NV
    d["D"] = den
    d["PCT_ABSTENCION"] = divide(d.NV, den)
    d["LOG_LN"] = np.log1p(d.LN)
    d["EDAD_PROM_LN"] = divide(d.AGE_LN_SUM, d.LN)
    d["QUALITY_NS"] = divide(d.NS, d.LN)
    for g in GROUPS:
        d[f"PROP_LN_{g}"] = divide(d[f"LN_{g}"], d.LN)
        d[f"PCT_ABST_{g}"] = divide(d[f"NV_{g}"], d[f"SV_{g}"] + d[f"NV_{g}"])
    d["BRECHA_M_H"] = d.PCT_ABST_H - d.PCT_ABST_M
    d["BRECHA_JOVEN_MAYOR"] = d.PCT_ABST_60_plus - d.PCT_ABST_18_24
    d["EDAD_VOTANTE_MENOS_LN"] = divide(d.AGE_SV_SUM, d.SV) - d.EDAD_PROM_LN
    return d


def reference(d, keys, prefix):
    grouped = d.groupby(keys, dropna=False)[RAW_SUM].sum().reset_index()
    grouped = derive(grouped)
    keep = keys + ["LN", "PCT_ABSTENCION"] + [f"PCT_ABST_{g}" for g in AGES]
    return grouped[keep].rename(columns={c: f"{prefix}_{c}" for c in keep if c not in keys})


def prepare_history(master):
    """All context uses source-year full records, never future outcomes."""
    years = {}
    for year, original in master.groupby("AELEC"):
        d = derive(original)
        assert not d.duplicated(["EDOCVE", "SECCION"]).any()
        d["PROP_U"] = d.TIPOSEC.eq("U").astype(float)
        d["PROP_R"] = d.TIPOSEC.eq("R").astype(float)
        d = d.merge(reference(d, ["EDOCVE", "MPIOCVE"], "MUN"), on=["EDOCVE", "MPIOCVE"], validate="many_to_one")
        d = d.merge(reference(d, ["EDOCVE"], "STATE"), on="EDOCVE", validate="many_to_one")
        d["MUN_ABST"] = d.MUN_PCT_ABSTENCION
        d["STATE_ABST"] = d.STATE_PCT_ABSTENCION
        d["NATIONAL_ABST"] = d.NV.sum() / d.D.sum()
        for scope in ["MUN", "STATE"]:
            d[f"EXPECTED_{scope}_AGE"] = sum(
                d[f"PROP_LN_{g}"] * d[f"{scope}_PCT_ABST_{g}"] for g in AGES
            )
        d["NATIONAL_LN"] = d.LN.sum()
        # PREV_* are true within-family shifts, not ALL_YEARS availability flags.
        d["TREND_FAMILY"] = d.PCT_ABSTENCION - d.PREV_PCT_ABSTENCION
        d["PREV_FAMILY_ABST"] = d.PREV_PCT_ABSTENCION
        d["GROWTH_LN_FAMILY"] = divide(d.LN - d.PREV_LN, d.PREV_LN)
        d["DELTA_AGE_FAMILY"] = d.EDAD_PROM_LN - d.PREV_EDAD_PROM_LN
        years[int(year)] = d
    return years


def territorial_source(source, mapping, level):
    keys = ["EDOCVE", "SECCION"] if level == "seccion" else LEVELS[level]
    # All history is grouped on RECENT geography, not target district assignments.
    d = source.drop(columns=["MPIOCVE", "DEF", "DEL"])
    d = d.merge(mapping, on=["EDOCVE", "SECCION"], validate="one_to_one")
    if level == "seccion":
        out = d.copy()
    else:
        out = derive(d.groupby(keys, dropna=False)[RAW_SUM].sum().reset_index())
        weight_cols = ["PROP_U", "PROP_R", "MUN_ABST", "STATE_ABST", "NATIONAL_ABST",
                       "EXPECTED_MUN_AGE", "EXPECTED_STATE_AGE"] + TREND
        weighted = d[keys].copy()
        for col in weight_cols:
            weighted[col] = d[col] * d.LN
            weighted[f"DEN_{col}"] = d.LN.where(d[col].notna(), 0)
        sums = weighted.groupby(keys, dropna=False).sum().reset_index()
        for col in weight_cols:
            sums[col] = divide(sums[col], sums[f"DEN_{col}"])
        out = out.merge(sums[keys + weight_cols], on=keys, validate="one_to_one")
        counts = d.groupby(keys, dropna=False).agg(N_SECTIONS=("SECCION", "size")).reset_index()
        out = out.merge(counts, on=keys, validate="one_to_one")
        # Reference denominators sum once for entity; within other levels municipality
        # weight is the sum of each constituent section's municipal share.
        weights = d[keys].copy()
        for scope in ["MUN", "STATE", "NATIONAL"]:
            weights[f"WEIGHT_{scope}"] = divide(d.LN, d[f"{scope}_LN"])
        weights = weights.groupby(keys, dropna=False).sum().reset_index()
        out = out.merge(weights, on=keys, validate="one_to_one")
    if level == "seccion":
        out["N_SECTIONS"] = 1
        for scope in ["MUN", "STATE", "NATIONAL"]:
            out[f"WEIGHT_{scope}"] = divide(out.LN, out[f"{scope}_LN"])
    for scope in ["MUN", "STATE"]:
        out[f"GAP_{scope}"] = out.PCT_ABSTENCION - out[f"{scope}_ABST"]
        out[f"EXCESS_{scope}_AGE"] = out.PCT_ABSTENCION - out[f"EXPECTED_{scope}_AGE"]
    return out[keys + list(dict.fromkeys(RAW_SUM + BASE + DEMO + BEHAVIOR + CONTEXT + EXPECTED + TREND + ["D", "N_SECTIONS"]))]


def build_window(years, target):
    same_year, recent_year = target - 6, target - 3
    keys = ["EDOCVE", "SECCION"]
    s, r, t = [years[y].set_index(keys) for y in [same_year, recent_year, target]]
    idx = s.index.intersection(r.index).intersection(t.index)
    s, r, t = [d.loc[idx] for d in [s, r, t]]
    mask = (s.MPIOCVE.eq(r.MPIOCVE) & r.MPIOCVE.eq(t.MPIOCVE)
            & s.TIPOSEC.eq(r.TIPOSEC) & r.TIPOSEC.eq(t.TIPOSEC))
    for d in [s, r, t]:
        mask &= d.PCT_ABSTENCION.notna() & d.QUALITY_NS.le(.10)
    idx = idx[mask]
    s, r, t = [d.loc[idx].reset_index() for d in [s, r, t]]
    mapping = r[keys + ["MPIOCVE", "DEF", "DEL"]]
    if mapping[["MPIOCVE", "DEF", "DEL"]].isna().any().any():
        raise ValueError("Missing geography in shared cohort")
    frames = {}
    coverage = []
    for level in ["seccion"] + list(LEVELS):
        group_keys = keys if level == "seccion" else LEVELS[level]
        a = territorial_source(s, mapping, level)
        b = territorial_source(r, mapping, level)
        a = a.rename(columns={c: "SAME_" + c for c in a if c not in group_keys})
        b = b.rename(columns={c: "RECENT_" + c for c in b if c not in group_keys})
        frame = a.merge(b, on=group_keys, validate="one_to_one")
        target_counts = t[keys + ["LN", "NV", "D"]].merge(mapping, on=keys, validate="one_to_one")
        target_counts = target_counts.groupby(group_keys, dropna=False).agg(
            TARGET_NV=("NV", "sum"), TARGET_D=("D", "sum"), TARGET_LN=("LN", "sum"),
            N_SECTIONS=("SECCION", "size") if level != "seccion" else ("LN", "size")
        ).reset_index()
        frame = frame.merge(target_counts, on=group_keys, validate="one_to_one")
        frame["Y"] = divide(frame.TARGET_NV, frame.TARGET_D)
        frame["TIPO_ELECCION"] = "intermedia" if target in [2015, 2021] else "presidencial"
        frame["TARGET_YEAR"] = target
        frame["DELTA_ABST"] = frame.RECENT_PCT_ABSTENCION - frame.SAME_PCT_ABSTENCION
        frame["DELTA_LOG_LN"] = frame.RECENT_LOG_LN - frame.SAME_LOG_LN
        frame["DELTA_AGE"] = frame.RECENT_EDAD_PROM_LN - frame.SAME_EDAD_PROM_LN
        for g in AGES + ["M"]:
            frame[f"DELTA_PROP_{g}"] = frame[f"RECENT_PROP_LN_{g}"] - frame[f"SAME_PROP_LN_{g}"]
        frames[level] = frame
        coverage.append({"year": target, "level": level, "sections": len(t), "territories": len(frame),
                         "cohort_target_ln": t.LN.sum(), "all_target_ln": years[target].LN.sum(),
                         "cohort_ln_share_national": t.LN.sum() / years[target].LN.sum(),
                         "district_reference_year": recent_year})
    # District coverage/full targets are on RECENT frame; new unmapped sections stay outside.
    ref_map = years[recent_year][keys + ["MPIOCVE", "DEF", "DEL"]]
    full = years[target].drop(columns=["MPIOCVE", "DEF", "DEL"]).merge(ref_map, on=keys, how="inner", validate="one_to_one")
    for level, group_keys in LEVELS.items():
        all_counts = full.groupby(group_keys, dropna=False).agg(
            FULL_NV=("NV", "sum"), FULL_D=("D", "sum"), FULL_LN=("LN", "sum"),
            FULL_SECTIONS=("SECCION", "size")
        ).reset_index()
        all_counts["Y_FULL_REFERENCE"] = divide(all_counts.FULL_NV, all_counts.FULL_D)
        frame = frames[level].merge(all_counts, on=group_keys, validate="one_to_one")
        frame["COVERAGE_LN"] = divide(frame.TARGET_LN, frame.FULL_LN)
        frames[level] = frame
    return frames, mapping, coverage


def feature_sets():
    hist = ["SAME_PCT_ABSTENCION", "RECENT_PCT_ABSTENCION"] + CAT
    prefixes = lambda cols: [p + c for p in ["SAME_", "RECENT_"] for c in cols]
    demo = prefixes(DEMO)
    behavior = prefixes(BEHAVIOR)
    trend = prefixes(TREND) + ["DELTA_ABST", "DELTA_LOG_LN", "DELTA_AGE"] + [f"DELTA_PROP_{g}" for g in AGES + ["M"]]
    ctx = prefixes(CONTEXT)
    expected = prefixes(EXPECTED)
    return {
        "B0_historia": hist,
        "B1_historia_demografia": hist + demo,
        "B2_demografia_grupos": hist + demo + behavior,
        "B3_demografia_tendencias": hist + demo + trend,
        "B4_demografia_contexto": hist + demo + ctx,
        "B5_completo": hist + demo + behavior + trend + ctx,
        "B6_completo_esperado": hist + demo + behavior + trend + ctx + expected,
    }


def make_model(kind, columns, level):
    cat = [c for c in columns if c in CAT]
    num = [c for c in columns if c not in cat]
    prep = ColumnTransformer([
        ("num", SimpleImputer(strategy="median", keep_empty_features=True, add_indicator=True), num),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
    ])
    if kind == "random_forest":
        model = RandomForestRegressor(n_estimators=64, max_depth=12,
            min_samples_leaf=25 if level == "seccion" else (3 if level == "entidad" else 8),
            max_features="sqrt", max_samples=.8, n_jobs=2, random_state=42)
    elif kind == "gradient_boosting":
        model = HistGradientBoostingRegressor(max_iter=180, learning_rate=.06,
            max_leaf_nodes=15, min_samples_leaf=30 if level == "seccion" else (5 if level == "entidad" else 12),
            l2_regularization=5., early_stopping=False, random_state=42)
    else:
        model = LinearRegression()
    return Pipeline([("prep", prep), ("model", model)])


def metrics(y, p, w):
    y, p, w = [np.asarray(a, dtype=float) for a in [y, p, w]]
    assert np.isfinite(y).all() and np.isfinite(p).all() and (w > 0).all()
    e = p - y
    den = np.sum((y - y.mean()) ** 2)
    def top(frac):
        k = max(1, int(np.ceil(len(y) * frac)))
        return len(set(np.argsort(y)[-k:]) & set(np.argsort(p)[-k:])) / k
    return {"n": len(y), "mae_pp": float(np.mean(abs(e)) * 100),
            "rmse_pp": float(np.sqrt(np.mean(e ** 2)) * 100),
            "r2": float(1 - np.sum(e ** 2) / den) if den > 0 else np.nan,
            "bias_pp": float(e.mean() * 100), "wmae_pp": float(np.average(abs(e), weights=w) * 100),
            "wrmse_pp": float(np.sqrt(np.average(e ** 2, weights=w)) * 100),
            "spearman": pd.Series(y).corr(pd.Series(p), method="spearman"),
            "top10": top(.1), "top20": top(.2)}


def aggregate_predictions(section_frame, mapping, level, pred, weight):
    d = section_frame[["EDOCVE", "SECCION", weight]].merge(mapping, on=["EDOCVE", "SECCION"], validate="one_to_one")
    d["WP"] = np.asarray(pred) * d[weight]
    keys = LEVELS[level]
    d = d.groupby(keys, dropna=False)[["WP", weight]].sum().reset_index()
    d["PRED"] = divide(d.WP, d[weight])
    return d[keys + ["PRED"]]


def paired_bootstrap(a, b, level):
    keys = LEVELS[level]
    pair = a[keys + ["Y", "PRED"]].merge(b[keys + ["PRED"]], on=keys, suffixes=("_A", "_B"), validate="one_to_one")
    diff = (abs(pair.PRED_A - pair.Y) - abs(pair.PRED_B - pair.Y)) * 100
    pair["DIFF"] = diff
    # State bootstrap for municipalities/districts, row bootstrap for states.
    clusters = pair.groupby("EDOCVE").agg(SUM=("DIFF", "sum"), N=("DIFF", "size"))
    rng = np.random.default_rng(42)
    estimates = []
    for _ in range(500):
        sampled = clusters.iloc[rng.integers(0, len(clusters), len(clusters))]
        estimates.append(sampled.SUM.sum() / sampled.N.sum())
    return {"delta_mae_A_minus_B_pp": diff.mean(), "ci95_low": np.quantile(estimates, .025),
            "ci95_high": np.quantile(estimates, .975), "clusters": len(clusters)}


METHOD = """EXPERIMENTO EXPLORATORIO MULTINIVEL: metodología y límites
Objetivo: NV/(SV+NV). NS separado. Tasas en [0,1], métricas de error en puntos porcentuales.
Evaluación temporal: 2021 entrena objetivos 2015+2018; 2024 entrena 2015+2018+2021.
Dos historias por objetivo: SAME=t-6, RECENT=t-3. Sin split aleatorio de elecciones.
Variables: historia, demografía, comportamiento por sexo/edad, tendencias, contexto y expectativa etaria.
Contexto histórico calculado antes del filtro sobre todas las secciones del año fuente.
No se usa LN/composición/NS/votación del objetivo como predictor.
Target NS <=10%, municipio y tipo estables en las tres fechas: condiciones de EVALUACIÓN.
Estas condiciones miran la disponibilidad del objetivo; resultados condicionados a la cohorte evaluable.
No entran flags ALL_YEARS ni identificadores de municipio/distrito como magnitudes numéricas.
Entrenamiento directo: sumar conteos de secciones de la misma cohorte y recalcular tasas/composición.
Contexto y tendencia directa: medias descriptivas ponderadas por LN fuente de secciones de la cohorte.
WEIGHT_MUN directo = suma de participaciones electorales seccionales en sus municipios fuente;
en distritos es un índice de concentración municipal, no una única proporción de población.
Expectativa por edad: composición LN fuente por tasas etarias municipales/estatales fuente.
Supone que composición LN aproxima la composición de participación conocida; no es efecto causal.
Agregado operativo: ponderación RECENT_LN (principal) y RECENT_D (sensibilidad).
Agregado TARGET_D: ORÁCULO diagnóstico, nunca seleccionable ni desplegable; aísla error de ponderación.
MAE territorial da igual peso a territorios; WMAE usa D observado exclusivamente para evaluar.
Todos los enfoques comparados por nivel/año comparten llaves, conteos objetivo y universo.
FULL_REFERENCE es sensibilidad respecto de todas las secciones objetivo mapeables al marco RECENT;
incluye observaciones NS altas, no es un target nacional completo ni sustituye la comparación principal.
Geografía: municipio/distritos congelados a códigos de RECENT. No se usa asignación distrital del objetivo.
Diccionarios RAW anteriores refieren DERFE2021 y 2024 DERFE2023: interpretación retrospectiva,
NO disponibilidad cartográfica histórica certificada ni evaluación del marco distrital 2027.
Modelos: Random Forest y HistGradientBoosting; hiperparámetros fijados antes de mirar errores.
Piloto de recursos RF100/depth14/features0.65 interrumpido por tiempo de cómputo;
se conserva aparte y no entra al ranking. La corrida completa fija RF64/depth12/sqrt en todos los bloques.
Ese cambio responde al costo de cómputo y no a optimización de métricas en test.
Regularización de hojas depende del nivel por diferencia de tamaño muestral; no se optimiza en test.
Referencia lineal: arquitectura de dos tasas reentrenada con las mismas filas y cortes, no coeficientes finales2027.
Selección descriptiva: menor peor razón MAE/lineal entre ambos años, también media por año.
Todos los bloques y candidatos se examinan en los dos años; no hay holdout nuevo e independiente.
Bootstrap 500 por entidad (o filas entidad): intervalos EXPLORATORIOS de diferencias pareadas,
condicionados a selección de candidatos; no corrigen selección múltiple ni escasez de ciclos temporales.
Solo 32 entidades por año: modelos estatales directos tienen pocos ejemplos.
No se regeneran cruces sexo×edad RAW, cuantiles exactos ni variables externas/espaciales en esta versión.
No se cambia arquitectura productiva, forecast2027, escenarios, semáforo ni dashboard.
"""


def summarize(rows, predictions):
    results = pd.DataFrame(rows)
    results.to_csv(OUT / "01_metricas_todas.csv", index=False)
    operational = results.loc[results.weight.ne("TARGET_D")].copy()
    yearly_best = operational.loc[operational.groupby(["year", "level", "approach"]).mae_pp.idxmin()]
    yearly_best.to_csv(OUT / "02_mejores_por_ano_enfoque.csv", index=False)
    bases = results.loc[(results.model.eq("linear_reference")) & results.approach.eq("directo"), ["year", "level", "mae_pp"]]
    # Section linear is the reference for section; direct territorial linear for other levels.
    op = operational.merge(bases.rename(columns={"mae_pp": "reference_mae_pp"}), on=["year", "level"], validate="many_to_one")
    op["ratio"] = op.mae_pp / op.reference_mae_pp
    rank = op.groupby(["level", "approach", "model", "block", "weight"]).agg(
        years=("year", "nunique"), mean_mae_pp=("mae_pp", "mean"), worst_ratio=("ratio", "max"),
        mean_wmae_pp=("wmae_pp", "mean"), mean_rmse_pp=("rmse_pp", "mean")
    ).reset_index()
    rank = rank.loc[rank.years.eq(2)].sort_values(["level", "worst_ratio", "mean_mae_pp"])
    rank.to_csv(OUT / "03_ranking_dos_anos.csv", index=False)
    winners = rank.groupby(["level", "approach"], sort=False).head(1)
    winners.to_csv(OUT / "04_comparacion_enfoques.csv", index=False)
    model_winners = rank.loc[rank.model.isin(["random_forest", "gradient_boosting"])].groupby(["level", "approach", "model"], sort=False).head(1)
    model_winners.to_csv(OUT / "05_mejores_por_modelo.csv", index=False)
    effect_keys = ["year", "level", "approach", "model", "weight"]
    b0 = operational.loc[operational.block.eq("B0_historia"), effect_keys + ["mae_pp"]]
    effects = operational.loc[operational.block.str.startswith("B")].merge(
        b0.rename(columns={"mae_pp": "history_only_mae_pp"}), on=effect_keys, validate="many_to_one")
    effects["delta_mae_vs_history_pp"] = effects.mae_pp - effects.history_only_mae_pp
    effects.to_csv(OUT / "08_efecto_bloques_variables.csv", index=False)
    weight_keys = ["year", "level", "model", "block"]
    weight_sensitivity = results.loc[results.approach.eq("agregado")].pivot(
        index=weight_keys, columns="weight", values="mae_pp").reset_index()
    weight_sensitivity["oracle_minus_operational_pp"] = weight_sensitivity.TARGET_D - weight_sensitivity.RECENT_LN
    weight_sensitivity.to_csv(OUT / "09_sensibilidad_ponderacion.csv", index=False)
    contrasts = []
    for level in LEVELS:
        for year in [2021, 2024]:
            choices = []
            for approach in ["directo", "agregado"]:
                choice = winners.loc[winners.level.eq(level) & winners.approach.eq(approach)].iloc[0]
                key = (year, level, approach, choice.model, choice.block, choice.weight)
                choices.append((choice, predictions[key]))
            direct, aggregate = choices
            contrasts.append({"year": year, "level": level, "A": "directo", "B": "agregado",
                              "A_model": direct[0].model, "A_block": direct[0].block,
                              "B_model": aggregate[0].model, "B_block": aggregate[0].block,
                              **paired_bootstrap(direct[1], aggregate[1], level)})
    pd.DataFrame(contrasts).to_csv(OUT / "06_bootstrap_pareado.csv", index=False)
    chosen = []
    for _, c in winners.iterrows():
        for year in [2021, 2024]:
            chosen.append(predictions[(year, c.level, c.approach, c.model, c.block, c.weight)].assign(
                year=year, level=c.level, approach=c.approach, model=c.model, block=c.block, weight=c.weight))
    pd.concat(chosen, ignore_index=True).to_csv(OUT / "07_predicciones_candidatos_seleccionados.csv.gz", index=False, compression="gzip")
    lines = [METHOD, "\nMEJORES CONFIGURACIONES POR ENFOQUE (minimax dos años)\n", winners.to_string(index=False),
             "\n\nMEJORES CONFIGURACIONES POR ALGORITMO\n", model_winners.to_string(index=False),
             "\n\nDIFERENCIAS PAREADAS DIRECTO - AGREGADO (negativo favorece directo)\n", pd.DataFrame(contrasts).to_string(index=False),
             "\n\nTODAS LAS PRUEBAS Y MÉTRICAS\n", results.to_string(index=False),
             "\n\nRANKING COMPLETO DOS AÑOS\n", rank.to_string(index=False),
             "\n\nEFECTO DE CADA BLOQUE FRENTE A HISTORIA SOLA\n", effects.to_string(index=False),
             "\n\nSENSIBILIDAD DE PONDERACIÓN (TARGET_D es oráculo)\n", weight_sensitivity.to_string(index=False)]
    (OUT / "RESULTADOS_EXPERIMENTO_MULTINIVEL.txt").write_text("\n".join(lines), encoding="utf-8")
    return winners


def verify_results():
    """Independent artifact checks and paired section comparison to prior pipeline."""
    scores = pd.read_csv(OUT / "01_metricas_todas.csv")
    config = json.loads((OUT / "configuracion.json").read_text(encoding="utf-8"))
    rank = pd.read_csv(OUT / "03_ranking_dos_anos.csv")
    saved = pd.read_csv(OUT / "07_predicciones_candidatos_seleccionados.csv.gz")
    id_cols = ["year", "level", "approach", "model", "block", "weight"]
    assert len(scores) == config["metric_rows"] == 544
    assert config["trained_models"] == 150
    assert not scores.duplicated(id_cols).any()
    assert set(scores.level) == {"seccion", *LEVELS}
    assert set(scores.year) == {2021, 2024}
    assert not rank.weight.eq("TARGET_D").any()
    assert saved.PRED.between(0, 1).all() and saved.Y.between(0, 1).all()
    assert saved.TARGET_D.gt(0).all()
    for key, frame in saved.groupby(id_cols):
        mask = np.ones(len(scores), dtype=bool)
        for col, value in zip(id_cols, key):
            mask &= scores[col].eq(value)
        expected = scores.loc[mask].iloc[0]
        recalculated = metrics(frame.Y, frame.PRED, frame.TARGET_D)
        assert len(frame) == expected.n
        for col in ["mae_pp", "rmse_pp", "r2", "bias_pp", "wmae_pp", "wrmse_pp"]:
            assert np.isclose(recalculated[col], expected[col], atol=1e-9), (key, col)
    contrasts = []
    for year, expected_n in [(2021, 48885), (2024, 47741)]:
        selected = saved.loc[saved.year.eq(year) & saved.level.eq("seccion")].copy()
        assert len(selected) == expected_n
        prior_file = ROOT / f"reports/dual_history/predictions/predictions_{year}_temporal_dual.parquet"
        if not prior_file.exists():
            continue
        reference = pd.read_parquet(prior_file)[["EDOCVE", "TGT_SECCION", "TGT_MPIOCVE", "Y_ABSTENCION", "PRED_two_history_linear"]]
        reference = reference.rename(columns={"TGT_SECCION": "SECCION"})
        pair = selected.merge(reference, on=["EDOCVE", "SECCION"], validate="one_to_one")
        assert len(pair) == expected_n
        assert np.allclose(pair.Y, pair.Y_ABSTENCION)
        baseline_mae = np.mean(abs(pair.PRED_two_history_linear - pair.Y)) * 100
        current_ref = scores.loc[scores.year.eq(year) & scores.level.eq("seccion") & scores.model.eq("linear_reference")].iloc[0]
        assert np.isclose(baseline_mae, current_ref.mae_pp, atol=1e-9)
        pair["DIFF"] = (abs(pair.PRED - pair.Y) - abs(pair.PRED_two_history_linear - pair.Y)) * 100
        for scope, keys in [("municipio", ["EDOCVE", "TGT_MPIOCVE"]), ("entidad", ["EDOCVE"])]:
            grouped = pair.groupby(keys).agg(SUM=("DIFF", "sum"), N=("DIFF", "size"))
            rng = np.random.default_rng(42)
            idx = rng.integers(0, len(grouped), size=(500, len(grouped)))
            values = grouped.SUM.to_numpy()[idx].sum(axis=1) / grouped.N.to_numpy()[idx].sum(axis=1)
            contrasts.append({"year": year, "selected_model": selected.model.iloc[0],
                              "selected_block": selected.block.iloc[0], "cluster": scope,
                              "clusters": len(grouped), "delta_mae_model_minus_linear_pp": pair.DIFF.mean(),
                              "ci95_low": np.quantile(values, .025), "ci95_high": np.quantile(values, .975)})
    check_text = (
        "VERIFICACIÓN COMPLETA: 544 filas únicas, 150 ajustes, dos años y cinco niveles.\n"
        "Pesos futuros excluidos del ranking; predicciones [0,1]; denominadores positivos.\n"
        "Métricas de TODOS los candidatos seleccionados recalculadas desde predicciones guardadas.\n"
        "Cohortes seccionales 48,885/47,741 y objetivos cotejados con el pipeline previo.\n"
        "La referencia lineal coincide con las métricas previas dentro de tolerancia 1e-9.\n"
        "Bootstrap seccional condicionado al candidato seleccionado: exploratorio, sin corrección por selección.\n"
    )
    (OUT / "10_VERIFICACION.txt").write_text(check_text, encoding="utf-8")
    pd.DataFrame(contrasts).to_csv(OUT / "11_bootstrap_seccion_vs_lineal.csv", index=False)
    with (OUT / "RESULTADOS_EXPERIMENTO_MULTINIVEL.txt").open("a", encoding="utf-8") as fh:
        fh.write("\n\n" + check_text + "\n" + pd.DataFrame(contrasts).to_string(index=False))
    config["verification_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    config["artifact_verification"] = "passed"
    (OUT / "configuracion.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(check_text + pd.DataFrame(contrasts).to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Only construction checks, no model fitting")
    parser.add_argument("--report-only", action="store_true", help="Refresh summaries from completed predictions and metrics")
    parser.add_argument("--resource-info", action="store_true", help="Read container CPU/memory limits without training")
    parser.add_argument("--interrupt-experiment", action="store_true", help="SIGINT only this experiment's flag-free Python process")
    parser.add_argument("--verify-results", action="store_true", help="Recalculate saved metrics and compare selected section model to prior linear")
    args = parser.parse_args()
    if args.interrupt_experiment:
        for proc in Path("/proc").glob("[0-9]*"):
            try:
                parts = (proc / "cmdline").read_bytes().split(b"\0")
                parts = [part.decode() for part in parts if part]
                if int(proc.name) != os.getpid() and len(parts) == 2 and parts[1] == "src/16_experiment_multilevel.py":
                    os.kill(int(proc.name), signal.SIGINT)
                    print(f"Interrupted experiment PID {proc.name}", flush=True)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        return
    if args.resource_info:
        for name in ["memory.max", "memory.current", "memory.events", "cpu.max", "cpu.stat"]:
            path = Path("/sys/fs/cgroup") / name
            if path.exists():
                print(name + ": " + path.read_text().strip(), flush=True)
        return
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    if args.verify_results:
        verify_results()
        return
    if args.report_only:
        rows = pd.read_csv(OUT / "01_metricas_todas.csv").to_dict("records")
        saved = pd.read_csv(OUT / "07_predicciones_candidatos_seleccionados.csv.gz")
        predictions = {}
        for key, frame in saved.groupby(["year", "level", "approach", "model", "block", "weight"]):
            predictions[key] = frame
        summarize(rows, predictions)
        config = json.loads((OUT / "configuracion.json").read_text(encoding="utf-8"))
        config["report_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (OUT / "configuracion.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        with (OUT / "RESULTADOS_EXPERIMENTO_MULTINIVEL.txt").open("a", encoding="utf-8") as fh:
            fh.write("\n\nCONFIGURACIÓN Y VARIABLES\n" + json.dumps(config, ensure_ascii=False, indent=2))
            fh.write("\n\nCOBERTURA\n" + (OUT / "00_cobertura.csv").read_text(encoding="utf-8"))
        print("Reports refreshed without retraining", flush=True)
        return
    print("Loading master and historical context", flush=True)
    master = pd.read_csv(MASTER, low_memory=False)
    histories = prepare_history(master)
    windows, mappings, coverage = {}, {}, []
    for year in [2015, 2018, 2021, 2024]:
        windows[year], mappings[year], cov = build_window(histories, year)
        coverage.extend(cov)
        print(f"Window {year}: {len(windows[year]['seccion']):,} sections", flush=True)
    pd.DataFrame(coverage).to_csv(OUT / "00_cobertura.csv", index=False)
    blocks = feature_sets()
    for frames in windows.values():
        for frame in frames.values():
            assert frame.Y.between(0, 1).all()
            assert np.allclose(frame.Y, frame.TARGET_NV / frame.TARGET_D)
            assert all(c in frame for c in blocks["B6_completo_esperado"])
    # Verify exact aggregation against target, and invariance of predictors under target perturbation.
    for year in [2021, 2024]:
        sec = windows[year]["seccion"]
        for level in LEVELS:
            actual = aggregate_predictions(sec, mappings[year], level, sec.Y, "TARGET_D")
            checked = windows[year][level].merge(actual, on=LEVELS[level], validate="one_to_one")
            assert np.allclose(checked.Y, checked.PRED)
        altered = dict(histories)
        altered[year] = histories[year].copy()
        altered[year][["NV", "SV"]] = histories[year][["SV", "NV"]].to_numpy()
        altered[year]["PCT_ABSTENCION"] = 1 - histories[year].PCT_ABSTENCION
        # Change future district IDs too: assignments must come from RECENT, not target.
        altered[year]["DEF"] = 999
        altered[year]["DEL"] = 999
        changed, _, _ = build_window(altered, year)
        for level in windows[year]:
            pd.testing.assert_frame_equal(
                windows[year][level][blocks["B6_completo_esperado"]],
                changed[level][blocks["B6_completo_esperado"]],
            )
            assert np.allclose(changed[level].Y, 1 - windows[year][level].Y)
    print("Checks passed: shared cohorts, feature availability, rates and oracle aggregation", flush=True)
    if args.smoke:
        return
    del histories, master, altered, changed
    config = {"created_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "sklearn": sklearn.__version__, "pandas": pd.__version__, "seed": 42,
              "source_sha256": hashlib.sha256(MASTER.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "features": blocks, "test_years": [2021, 2024], "levels": LEVELS,
              "method": METHOD,
              "model_parameters": {kind: {level: make_model(kind, blocks['B0_historia'], level).named_steps['model'].get_params()
                                         for level in ['seccion'] + list(LEVELS)}
                                   for kind in ['random_forest', 'gradient_boosting']}}
    (OUT / "configuracion.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([{"block": b, "column": c, "categorical": c in CAT} for b, cols in blocks.items() for c in cols]).to_csv(OUT / "variables_por_bloque.csv", index=False)
    rows, predictions = [], {}

    def record(year, level, approach, model, block, weight, frame, pred, seconds):
        pred = np.clip(np.asarray(pred), 0, 1)
        row = {"year": year, "level": level, "approach": approach, "model": model, "block": block,
               "weight": weight, "features": len(blocks[block]) if block in blocks else 2,
               "fit_seconds": seconds, **metrics(frame.Y, pred, frame.TARGET_D)}
        if level != "seccion":
            row["full_reference_mae_pp"] = np.mean(abs(pred - frame.Y_FULL_REFERENCE)) * 100
            row["median_coverage_ln"] = frame.COVERAGE_LN.median()
            keys = LEVELS[level]
        else:
            keys = ["EDOCVE", "SECCION"]
        cols = keys + ["Y", "TARGET_D", "TARGET_LN", "N_SECTIONS"]
        if level != "seccion":
            cols += ["Y_FULL_REFERENCE", "COVERAGE_LN", "FULL_SECTIONS"]
        predictions[(year, level, approach, model, block, weight)] = frame[cols].assign(PRED=pred)
        rows.append(row)

    for year in [2021, 2024]:
        prior_years = [y for y in windows if y < year]
        train_sec = pd.concat([windows[y]["seccion"] for y in prior_years], ignore_index=True)
        test_sec = windows[year]["seccion"]
        configs = [("persistence", "REFERENCE"), ("linear_reference", "REFERENCE")]
        configs += [(kind, block) for block in blocks for kind in ["random_forest", "gradient_boosting"]]
        for kind, block in configs:
            cols = blocks[block] if block in blocks else ["SAME_PCT_ABSTENCION", "RECENT_PCT_ABSTENCION"]
            t0 = time.time()
            if kind == "persistence":
                pred = test_sec.SAME_PCT_ABSTENCION.to_numpy()
            else:
                model = make_model(kind, cols, "seccion")
                model.fit(train_sec[cols], train_sec.Y)
                pred = np.clip(model.predict(test_sec[cols]), 0, 1)
            seconds = time.time() - t0
            record(year, "seccion", "directo", kind, block, "none", test_sec, pred, seconds)
            for level, keys in LEVELS.items():
                frame = windows[year][level]
                for weight in ["RECENT_LN", "RECENT_D", "TARGET_D"]:
                    agg = aggregate_predictions(test_sec, mappings[year], level, pred, weight)
                    merged = frame.merge(agg, on=keys, validate="one_to_one")
                    assert len(merged) == len(frame)
                    record(year, level, "agregado", kind, block, weight, merged, merged.PRED, seconds)
            print(f"{year} SECTION {kind} {block}: MAE={rows[-13]['mae_pp']:.3f} pp, {seconds:.1f}s", flush=True)
            pd.DataFrame(rows).to_csv(OUT / "01_metricas_todas.csv", index=False)
        for level in LEVELS:
            train = pd.concat([windows[y][level] for y in prior_years], ignore_index=True)
            test = windows[year][level]
            for kind, block in configs:
                cols = blocks[block] if block in blocks else ["SAME_PCT_ABSTENCION", "RECENT_PCT_ABSTENCION"]
                t0 = time.time()
                if kind == "persistence":
                    pred = test.SAME_PCT_ABSTENCION.to_numpy()
                else:
                    model = make_model(kind, cols, level)
                    model.fit(train[cols], train.Y)
                    pred = model.predict(test[cols])
                record(year, level, "directo", kind, block, "none", test, pred, time.time() - t0)
            print(f"{year} DIRECT {level}: {len(train)} training rows, {len(test)} test rows", flush=True)
            pd.DataFrame(rows).to_csv(OUT / "01_metricas_todas.csv", index=False)
    winners = summarize(rows, predictions)
    config["elapsed_seconds"] = time.time() - started
    config["metric_rows"] = len(rows)
    config["trained_models"] = 2 * 5 * (1 + 2 * len(blocks))
    (OUT / "configuracion.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "RESULTADOS_EXPERIMENTO_MULTINIVEL.txt").open("a", encoding="utf-8") as fh:
        fh.write("\n\nCONFIGURACIÓN Y VARIABLES\n" + json.dumps(config, ensure_ascii=False, indent=2))
        fh.write("\n\nCOBERTURA POR AÑO Y NIVEL\n" + pd.DataFrame(coverage).to_string(index=False))
    print(winners.to_string(index=False), flush=True)
    print(f"DONE: {len(rows)} metric rows; {time.time()-started:.1f}s; {OUT}", flush=True)


if __name__ == "__main__":
    main()
