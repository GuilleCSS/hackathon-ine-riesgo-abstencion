"""New RF trials with historical features, logs, residual targets and deduplication.

Previous experiment metrics are reused, never refitted. New completed fits are
checkpointed and reused on subsequent executions. No production files change.
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import sklearn

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("multilevel_base", ROOT / "src/16_experiment_multilevel.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
PREVIOUS = ROOT / "reports/experiment_multilevel"
OUT = ROOT / "reports/experiment_rf_improved"
DATA = ROOT / "data/processed/experiment_rf_improved"
PREFIXES = ["SAME_", "RECENT_"]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def extra_source(master):
    """Source-year-only peers and chronological expanding histories, no all-years flags."""
    d = master.sort_values(["EDOCVE", "SECCION", "AELEC"]).copy()
    d["A"] = base.divide(d.NV, d.SV + d.NV)
    d["A2"] = d.A ** 2
    d["VALID"] = d.A.notna().astype(int)
    d["L"] = np.log1p(d.LN)
    all_keys = ["EDOCVE", "SECCION"]
    fam_keys = all_keys + ["TIPO_ELECCION"]
    extra = {}
    for name, keys in [("ALL", all_keys), ("FAMILY", fam_keys)]:
        grouped = d.groupby(keys, sort=False)
        count = grouped.VALID.cumsum()
        mean = base.divide(grouped.A.cumsum(), count)
        extra[f"X_HIST_{name}_N"] = count
        extra[f"X_HIST_{name}_MEAN"] = mean
        extra[f"X_HIST_{name}_STD"] = np.sqrt((base.divide(grouped.A2.cumsum(), count) - mean ** 2).clip(lower=0))
        extra[f"X_HIST_{name}_MIN"] = grouped.A.cummin()
        extra[f"X_HIST_{name}_MAX"] = grouped.A.cummax()
        extra[f"X_HIST_{name}_LAST_CHANGE"] = d.A - grouped.A.shift(1)
    extra["X_HIST_LOG_LN_CHANGE"] = d.L - d.groupby(all_keys).L.shift(1)
    extra["X_HIST_AGE_CHANGE"] = d.EDAD_PROM_LN - d.groupby(all_keys).EDAD_PROM_LN.shift(1)
    extra = pd.DataFrame(extra, index=d.index)
    d = pd.concat([d, extra], axis=1)
    years = {}
    for year, source in d.groupby("AELEC"):
        source = source.copy()
        source["D"] = source.SV + source.NV
        source["LOG_LN"] = np.log1p(source.LN)
        for g in base.GROUPS:
            source[f"D_{g}"] = source[f"SV_{g}"] + source[f"NV_{g}"]
        totals = ["LN", "NV", "D"] + [c for g in base.GROUPS for c in [f"NV_{g}", f"D_{g}"]]
        mun = source.groupby(["EDOCVE", "MPIOCVE"])[totals].transform("sum")
        state = source.groupby("EDOCVE")[totals].transform("sum")
        new = {}
        new["X_PEER_MUN_A"] = base.divide(mun.NV - source.NV, mun.D - source.D)
        new["X_PEER_STATE_A"] = base.divide(state.NV - source.NV, state.D - source.D)
        new["X_MUN_A_STD"] = source.groupby(["EDOCVE", "MPIOCVE"]).A.transform("std")
        new["X_MUN_LN_RANK"] = source.groupby(["EDOCVE", "MPIOCVE"]).LN.rank(pct=True)
        new["X_MUN_A_RANK"] = source.groupby(["EDOCVE", "MPIOCVE"]).A.rank(pct=True)
        new["X_LOG_SIZE_REL_MUN"] = np.log((source.LN + 1) / (mun.LN + 1))
        new["X_PEER_MUN_GAP"] = source.A - new["X_PEER_MUN_A"]
        for g in base.GROUPS:
            den = source[f"D_{g}"]
            peer = base.divide(mun[f"NV_{g}"] - source[f"NV_{g}"], mun[f"D_{g}"] - den)
            fallback = base.divide(state[f"NV_{g}"] - source[f"NV_{g}"], state[f"D_{g}"] - den)
            national = source[f"NV_{g}"].sum() / source[f"D_{g}"].sum()
            peer = peer.fillna(fallback).fillna(national)
            new[f"X_SHRUNK_A_{g}"] = (source[f"NV_{g}"] + 100 * peer) / (den + 100)
            new[f"X_GROUP_PEER_GAP_{g}"] = base.divide(source[f"NV_{g}"], den) - peer
            new[f"X_NS_{g}"] = base.divide(source[f"LN_{g}"] - den, source[f"LN_{g}"])
            assert (source[f"LN_{g}"] - den).ge(0).all()
            new[f"PEER_{g}"] = peer
        new["X_EXPECTED_PEER_AGE"] = sum(base.divide(source[f"D_{g}"], source.D) * new[f"PEER_{g}"] for g in base.AGES)
        sex_d = source.D_H + source.D_M
        new["X_EXPECTED_PEER_SEX"] = sum(base.divide(source[f"D_{g}"], sex_d) * new[f"PEER_{g}"] for g in ["H", "M"])
        new["X_EXCESS_PEER_AGE"] = source.A - new["X_EXPECTED_PEER_AGE"]
        new["X_EXCESS_PEER_SEX"] = source.A - new["X_EXPECTED_PEER_SEX"]
        new = {key: value for key, value in new.items() if key.startswith("X_")}
        result = pd.concat([source[["EDOCVE", "SECCION", "LN"] + list(extra.columns)], pd.DataFrame(new, index=source.index)], axis=1)
        assert not result.duplicated(["EDOCVE", "SECCION"]).any()
        years[int(year)] = result.reset_index(drop=True)
    return years


def attach_extra(frame, sources, mapping, year, level):
    keys = ["EDOCVE", "SECCION"] if level == "seccion" else base.LEVELS[level]
    for prefix, source_year in [("SAME_", year - 6), ("RECENT_", year - 3)]:
        d = sources[source_year].merge(mapping, on=["EDOCVE", "SECCION"], validate="one_to_one")
        cols = [c for c in d if c.startswith("X_")]
        if level == "seccion":
            out = d[keys + cols]
        else:
            values = d[keys].copy()
            for col in cols:
                values[col] = d[col] * d.LN
                values["DEN_" + col] = d.LN.where(d[col].notna(), 0)
            out = values.groupby(keys).sum().reset_index()
            for col in cols:
                out[col] = base.divide(out[col], out["DEN_" + col])
            out = out[keys + cols]
        frame = frame.merge(out.rename(columns={c: prefix + c for c in cols}), on=keys, validate="one_to_one")
    return add_shapes_and_logs(frame)


def add_shapes_and_logs(frame):
    new = {}
    for p in PREFIXES:
        for g in base.GROUPS:
            den = frame[p + "SV_" + g] + frame[p + "NV_" + g]
            new[p + "X_LOG_LN_" + g] = np.log1p(frame[p + "LN_" + g])
            new[p + "X_LOG_D_" + g] = np.log1p(den)
        for c in ["D", "SV", "NV", "NS"]:
            new[p + "X_LOG_" + c] = np.log1p(frame[p + c])
        probs = frame[[p + "PROP_LN_" + g for g in base.AGES]].to_numpy()
        new[p + "X_AGE_ENTROPY"] = -np.sum(probs * np.log(np.clip(probs, 1e-12, 1)), axis=1)
        new[p + "X_YOUNG_SHARE"] = frame[p + "PROP_LN_18_24"] + frame[p + "PROP_LN_25_34"]
        new[p + "X_OLD_YOUNG_RATIO"] = base.divide(frame[p + "LN_60_plus"], frame[p + "LN_18_24"] + frame[p + "LN_25_34"])
        new[p + "X_LOG_SEX_RATIO"] = np.log((frame[p + "LN_M"] + 1) / (frame[p + "LN_H"] + 1))
        rates = frame[[p + "PCT_ABST_" + g for g in base.AGES]]
        new[p + "X_AGE_RATE_RANGE"] = rates.max(axis=1) - rates.min(axis=1)
        new[p + "X_AGE_RATE_STD"] = rates.std(axis=1)
        new[p + "X_YOUNG_NV_SHARE"] = base.divide(frame[p + "NV_18_24"] + frame[p + "NV_25_34"], frame[p + "NV"])
        new[p + "X_OLDER_NV_SHARE"] = base.divide(frame[p + "NV_60_plus"], frame[p + "NV"])
    return pd.concat([frame, pd.DataFrame(new, index=frame.index)], axis=1)


def variants():
    blocks = base.feature_sets()
    logs = [p + "X_LOG_" + c for p in PREFIXES for c in ["D", "SV", "NV", "NS"] + [s + g for g in base.GROUPS for s in ["LN_", "D_"]]]
    shape_names = ["AGE_ENTROPY", "YOUNG_SHARE", "OLD_YOUNG_RATIO", "LOG_SEX_RATIO", "AGE_RATE_RANGE", "AGE_RATE_STD", "YOUNG_NV_SHARE", "OLDER_NV_SHARE"]
    shapes = [p + "X_" + c for p in PREFIXES for c in shape_names]
    context_names = ["PEER_MUN_A", "PEER_STATE_A", "MUN_A_STD", "MUN_LN_RANK", "MUN_A_RANK", "LOG_SIZE_REL_MUN", "PEER_MUN_GAP", "EXPECTED_PEER_AGE", "EXPECTED_PEER_SEX", "EXCESS_PEER_AGE", "EXCESS_PEER_SEX"]
    ctx = [p + "X_" + c for p in PREFIXES for c in context_names]
    support = [p + "X_" + c + g for p in PREFIXES for g in base.GROUPS for c in ["SHRUNK_A_", "GROUP_PEER_GAP_", "NS_"]]
    history_names = ["HIST_" + kind + "_" + stat for kind in ["ALL", "FAMILY"] for stat in ["N", "MEAN", "STD", "MIN", "MAX", "LAST_CHANGE"]] + ["HIST_LOG_LN_CHANGE", "HIST_AGE_CHANGE"]
    history = [p + "X_" + c for p in PREFIXES for c in history_names]
    broad = list(dict.fromkeys(blocks["B6_completo_esperado"] + logs + shapes + ctx + support))
    compact = list(dict.fromkeys(blocks["B3_demografia_tendencias"] + logs + shapes))
    configs = [
        ("R01_logs_grupos", blocks["B5_completo"] + logs, "rate", "standard", "B5 + log1p conteos históricos por sexo/edad y participación"),
        ("R02_pares_soporte", blocks["B6_completo_esperado"] + ctx + support, "rate", "standard", "B6 + municipio sin propia sección + suavizado por grupo + NS grupal"),
        ("R03_compacto_log", compact, "rate", "standard", "Historia/demografía/tendencias + logs y formas demográficas; sin contexto original completo"),
        ("R04_combinado", broad, "rate", "standard", "Logs + formas + referencias de pares + soporte junto a B6"),
        ("R05_historia_larga", broad + history, "rate", "standard", "R04 + resúmenes acumulados as-of de toda la historia y por familia"),
        ("R06_cambio_compacto", compact, "delta_same", "standard", "Mismas variables nuevas de R03, aprende Y menos SAME y reconstruye tasa"),
        ("R07_mayor_detalle", broad, "rate", "detailed", "R04 con 96 árboles, profundidad 16 y hojas menores"),
        ("R08_cambio_historia", broad + history, "delta_same", "standard", "Mismas variables nuevas de R05, aprende cambio respecto de SAME"),
    ]
    return {name: {"features": list(dict.fromkeys(cols)), "target": target, "profile": profile, "description": desc}
            for name, cols, target, profile, desc in configs}


def model_for(config, level):
    model = base.make_model("random_forest", config["features"], level)
    if config["profile"] == "detailed":
        model.named_steps["model"].set_params(n_estimators=96, max_depth=16,
            min_samples_leaf=15 if level == "seccion" else (2 if level == "entidad" else 5))
    return model


def trial_key(cols, params, target, year, level, data_hash):
    return fingerprint({"features": sorted(cols), "parameters": params, "target": target,
                        "year": year, "level": level, "data_sha": data_hash,
                        "train_years": [y for y in [2015, 2018, 2021] if y < year],
                        "preprocessing": "median_indicators_onehot_v16", "cohort": "clean10_stable_mpio_type_v16"})


def make_frames(data_hash):
    feature_hash = fingerprint([inspect.getsource(f) for f in [extra_source, attach_extra, add_shapes_and_logs,
        base.prepare_history, base.build_window, base.territorial_source, base.derive]])
    cache_id = fingerprint({"data": data_hash, "features": feature_hash})
    folder = DATA / "cache" / cache_id
    manifest = folder / "manifest.json"
    frames, mappings = {}, {}
    if manifest.exists():
        for year in [2015, 2018, 2021, 2024]:
            frames[year] = {level: pd.read_parquet(folder / f"{year}_{level}.parquet") for level in ["seccion"] + list(base.LEVELS)}
            mappings[year] = pd.read_parquet(folder / f"{year}_mapping.parquet")
        print("Reusing feature cache (same data and feature definitions)", flush=True)
        return frames, mappings, cache_id
    folder.mkdir(parents=True, exist_ok=True)
    print("Building historical features; previous model fits are not rerun", flush=True)
    master = pd.read_csv(base.MASTER, low_memory=False)
    sources = extra_source(master)
    # Genuine chronological leakage check: altering a future result cannot change past inputs.
    for cutoff in [2021, 2024]:
        changed = master.copy()
        mask = changed.AELEC.ge(cutoff)
        changed.loc[mask, ["SV", "NV"]] = changed.loc[mask, ["NV", "SV"]].to_numpy()
        changed.loc[mask, "EDAD_PROM_LN"] = 999
        perturbed = extra_source(changed)
        for year in sources:
            if year < cutoff:
                pd.testing.assert_frame_equal(sources[year], perturbed[year])
    del changed, perturbed
    histories = base.prepare_history(master)
    coverage = []
    for year in [2015, 2018, 2021, 2024]:
        frames[year], mappings[year], cov = base.build_window(histories, year)
        coverage.extend(cov)
        for level in frames[year]:
            frames[year][level] = attach_extra(frames[year][level], sources, mappings[year], year, level)
            frame = frames[year][level]
            for config in variants().values():
                assert set(config["features"]).issubset(frame.columns)
                assert not any(c.startswith(("TARGET", "TGT", "FULL", "Y")) for c in config["features"])
                assert {"SAME_LOG_LN", "RECENT_LOG_LN"}.issubset(config["features"])
            assert np.allclose(frame.SAME_LOG_LN, np.log1p(frame.SAME_LN))
            assert np.allclose(frame.RECENT_X_LOG_D, np.log1p(frame.RECENT_D))
            assert np.allclose(frame.Y, frame.TARGET_NV / frame.TARGET_D)
            frame.to_parquet(folder / f"{year}_{level}.parquet", index=False)
        mappings[year].to_parquet(folder / f"{year}_mapping.parquet", index=False)
        print(f"Cached {year}: {len(frames[year]['seccion']):,} sections; new log features checked", flush=True)
    pd.DataFrame(coverage).to_csv(OUT / "00_cobertura.csv", index=False)
    manifest.write_text(json.dumps({"cache_id": cache_id, "feature_hash": feature_hash, "data_hash": data_hash,
                                   "checks": "logs, rates, source chronology and feature availability passed"}, indent=2), encoding="utf-8")
    return frames, mappings, cache_id


METHOD = """SEGUNDA RONDA RANDOM FOREST: exclusivamente configuraciones nuevas
Se reutilizan las métricas previas; no se reentrena B0-B6 ni el piloto.
Todos los modelos usan SAME_LOG_LN y RECENT_LOG_LN = log1p(LN), ya presentes en ronda1.
Nuevos logs: conteos LN/D por sexo/edad, SV/NV/NS/D y log relación de tamaño respecto del municipio.
Un log monotónico no añade información por sí solo a un árbol; se prueba como representación
y junto a conteos e interacciones derivados. No se atribuye causalmente una mejora al log.
Nuevas variables: entropía/forma etaria, proporción joven, razón mayores/jóvenes,
referencias municipales/estatales excluyendo propia sección, rangos municipales,
tasas grupales suavizadas con k=100 registros (fijado), NS por grupo y expectativas por edad/sexo.
Historia acumulada ALL/FAMILY usa solo observaciones hasta la elección fuente, inclusive.
NS de grupo = LN_g-SV_g-NV_g, tras verificar no negatividad.
En territorios directos, nuevas referencias e historias son descriptores seccionales
ponderados por LN fuente de la misma cohorte; conteos/tasas principales se recalculan agregados.
R06/R08 aprenden Y-SAME; predicción = SAME + cambio aprendido, limitada a [0,1].
Cohortes, cortes temporales, tipos de elección y marcos geográficos idénticos a ronda1.
Entrenamiento objetivos <2021 o <2024; ningún resultado/composición del objetivo como input.
Registro de firma: datos + variables + parámetros + objetivo + nivel + año + política de entrenamiento.
Firmas previas y nuevas se cotejan antes de entrenar. Checkpoints reutilizan pruebas nuevas completas.
Dos enfoques: predicción seccional agregada con pesos previos LN o D y entrenamiento territorial directo.
No se utiliza ponderación oráculo futura en esta ronda.
Ranking robusto: menor peor razón de MAE frente al RF anterior elegido en cada nivel/enfoque.
También se reporta media MAE y Top20; no se cambia de candidato por elección retrospectivamente.
Selección y bootstrap son EXPLORATORIOS sobre los mismos dos backtests, sin holdout independiente.
Cobertura seccional ~64% LN2021 y ~60% LN2024; no equivale al universo electoral completo.
Distritos retrospectivos en marco de elección previa; no certifica distritos2027.
No se usan fuentes externas, geometría nueva ni cruces RAW sexo×edad en esta ronda.
No se modifica dashboard, arquitectura bloqueada ni estimaciones productivas2027.
"""


def save_predictions(frame, pred, key):
    cols = [c for c in ["EDOCVE", "SECCION", "MPIOCVE", "DEF", "DEL", "Y", "TARGET_D", "TARGET_LN", "N_SECTIONS",
        "Y_FULL_REFERENCE", "COVERAGE_LN"] if c in frame]
    frame[cols].assign(PRED=np.asarray(pred)).to_parquet(DATA / f"prediction_{key}.parquet", index=False)


def record(rows, year, level, approach, name, config, weight, frame, pred, seconds, key):
    pred = np.clip(np.asarray(pred), 0, 1)
    row = {"year": year, "level": level, "approach": approach, "model": "random_forest", "variant": name,
           "weight": weight, "features": len(config["features"]), "target_kind": config["target"],
           "profile": config["profile"], "trial_signature": key, "fit_seconds": seconds,
           **base.metrics(frame.Y, pred, frame.TARGET_D)}
    if level != "seccion":
        row["full_reference_mae_pp"] = np.mean(abs(pred - frame.Y_FULL_REFERENCE)) * 100
    rows.append(row)
    return row


def bootstrap(pair, cluster):
    pair = pair.copy()
    pair["DIFF"] = (abs(pair.PRED_NEW - pair.Y) - abs(pair.PRED_OLD - pair.Y)) * 100
    group = pair.groupby(cluster).agg(SUM=("DIFF", "sum"), N=("DIFF", "size"))
    rng = np.random.default_rng(42)
    idx = rng.integers(0, len(group), (500, len(group)))
    values = group.SUM.to_numpy()[idx].sum(axis=1) / group.N.to_numpy()[idx].sum(axis=1)
    return {"delta_mae_new_minus_old_pp": pair.DIFF.mean(), "ci95_low": np.quantile(values, .025),
            "ci95_high": np.quantile(values, .975), "clusters": len(group)}


def report(rows, predictions, frames, previous_config, run_info):
    results = pd.DataFrame(rows)
    assert len(results) == 208
    assert not results.duplicated(["year", "level", "approach", "variant", "weight"]).any()
    results.to_csv(OUT / "01_metricas_nuevas.csv", index=False)
    old_scores = pd.read_csv(PREVIOUS / "01_metricas_todas.csv")
    old_winners = pd.read_csv(PREVIOUS / "04_comparacion_enfoques.csv")
    references = []
    for _, w in old_winners.iterrows():
        refs = old_scores.loc[old_scores.level.eq(w.level) & old_scores.approach.eq(w.approach)
            & old_scores.model.eq(w.model) & old_scores.block.eq(w.block) & old_scores.weight.eq(w.weight)].copy()
        refs["variant"] = "PREV_" + w.block
        references.append(refs)
    refs = pd.concat(references, ignore_index=True)
    comparison = results.merge(refs[["year", "level", "approach", "mae_pp", "top20"]].rename(
        columns={"mae_pp": "previous_mae_pp", "top20": "previous_top20"}), on=["year", "level", "approach"], validate="many_to_one")
    comparison["delta_mae_pp"] = comparison.mae_pp - comparison.previous_mae_pp
    comparison["delta_top20_pp"] = (comparison.top20 - comparison.previous_top20) * 100
    comparison["ratio"] = comparison.mae_pp / comparison.previous_mae_pp
    comparison.to_csv(OUT / "02_comparacion_con_rf_previo.csv", index=False)
    ranking = comparison.groupby(["level", "approach", "variant", "weight"]).agg(
        years=("year", "nunique"), mean_mae_pp=("mae_pp", "mean"), worst_ratio=("ratio", "max"),
        mean_rmse_pp=("rmse_pp", "mean"), mean_top20=("top20", "mean"),
        mean_delta_mae_pp=("delta_mae_pp", "mean"), mean_delta_top20_pp=("delta_top20_pp", "mean")
    ).reset_index().sort_values(["level", "worst_ratio", "mean_mae_pp"])
    assert ranking.years.eq(2).all()
    ranking.to_csv(OUT / "03_ranking_nuevos.csv", index=False)
    robust = ranking.groupby(["level", "approach"], sort=False).head(1)
    robust.to_csv(OUT / "04_mejores_nuevos_por_enfoque.csv", index=False)
    average = ranking.sort_values("mean_mae_pp").groupby(["level", "approach"], sort=False).head(1)
    average.to_csv(OUT / "05_mejores_por_media.csv", index=False)
    # Include old winner as a no-fit option, so a worse new model is never mislabeled improvement.
    retain = []
    contrasts = []
    old_preds = pd.read_csv(PREVIOUS / "07_predicciones_candidatos_seleccionados.csv.gz")
    old_sec = old_preds.loc[old_preds.level.eq("seccion")].copy()
    for _, choice in robust.iterrows():
        retain.append({**choice.to_dict(), "improves_both_years": bool(choice.worst_ratio < 1),
                       "decision": "new_candidate" if choice.worst_ratio < 1 else "keep_previous"})
        for year in [2021, 2024]:
            new = predictions[(year, choice.level, choice.approach, choice.variant, choice.weight)]
            old = old_preds.loc[old_preds.year.eq(year) & old_preds.level.eq(choice.level) & old_preds.approach.eq(choice.approach)]
            keys = ["EDOCVE", "SECCION"] if choice.level == "seccion" else base.LEVELS[choice.level]
            pair = new[keys + ["Y", "PRED"]].merge(old[keys + ["Y", "PRED"]], on=keys, suffixes=("_NEW", "_OLD"), validate="one_to_one")
            assert len(pair) == len(old) and np.allclose(pair.Y_NEW, pair.Y_OLD)
            pair["Y"] = pair.Y_NEW
            contrasts.append({"year": year, "level": choice.level, "approach": choice.approach,
                "variant": choice.variant, "weight": choice.weight, "cluster": "entidad", **bootstrap(pair, ["EDOCVE"])})
            if choice.level == "seccion":
                mapping = frames[year]["mapping"][["EDOCVE", "SECCION", "MPIOCVE"]]
                pair = pair.merge(mapping, on=keys, validate="one_to_one")
                contrasts.append({"year": year, "level": choice.level, "approach": choice.approach,
                    "variant": choice.variant, "weight": choice.weight, "cluster": "municipio", **bootstrap(pair, ["EDOCVE", "MPIOCVE"])})
    decisions = pd.DataFrame(retain)
    decisions.to_csv(OUT / "06_decisiones_vs_previo.csv", index=False)
    pd.DataFrame(contrasts).to_csv(OUT / "07_bootstrap_vs_rf_previo.csv", index=False)
    selected_scores = comparison.merge(robust[["level", "approach", "variant", "weight"]], on=["level", "approach", "variant", "weight"], validate="many_to_one")
    selected_scores.to_csv(OUT / "08_metricas_seleccionadas.csv", index=False)
    # Recompute all chosen scores from independent saved predictions.
    for _, row in selected_scores.iterrows():
        saved = predictions[(row.year, row.level, row.approach, row.variant, row.weight)]
        actual = base.metrics(saved.Y, saved.PRED, saved.TARGET_D)
        for c in ["mae_pp", "rmse_pp", "r2", "bias_pp", "wmae_pp", "wrmse_pp"]:
            assert np.isclose(actual[c], row[c], atol=1e-9)
    # Isolated comparisons: count logs, peers, long history, residual formulation and detail.
    pairs = [("R01_logs_grupos", "PREV_B5_completo"), ("R02_pares_soporte", "PREV_B6_completo_esperado"),
             ("R05_historia_larga", "R04_combinado"), ("R06_cambio_compacto", "R03_compacto_log"),
             ("R07_mayor_detalle", "R04_combinado"), ("R08_cambio_historia", "R05_historia_larga")]
    effects = []
    for a, b in pairs:
        for year in [2021, 2024]:
            arow = results.loc[results.year.eq(year) & results.level.eq("seccion") & results.variant.eq(a)].iloc[0]
            if b.startswith("PREV_"):
                brow = old_scores.loc[old_scores.year.eq(year) & old_scores.level.eq("seccion")
                    & old_scores.model.eq("random_forest") & old_scores.block.eq(b.removeprefix("PREV_"))].iloc[0]
            else:
                brow = results.loc[results.year.eq(year) & results.level.eq("seccion") & results.variant.eq(b)].iloc[0]
            effects.append({"year": year, "A": a, "B": b, "delta_mae_A_minus_B_pp": arow.mae_pp - brow.mae_pp,
                            "delta_top20_A_minus_B_pp": (arow.top20 - brow.top20) * 100})
    pd.DataFrame(effects).to_csv(OUT / "09_efectos_aislados.csv", index=False)
    log = [METHOD, "\nREGISTRO DE EJECUCIÓN\n", json.dumps(run_info, ensure_ascii=False, indent=2),
           "\nCONFIGURACIONES NUEVAS\n", json.dumps(variants(), ensure_ascii=False, indent=2),
           "\nRANKING COMPLETO\n", ranking.to_string(index=False),
           "\nDECISIONES VS RF PREVIO\n", decisions.to_string(index=False),
           "\nMÉTRICAS DE CANDIDATOS NUEVOS SELECCIONADOS\n", selected_scores.to_string(index=False),
           "\nMEJORES POR MEDIA (no minimax)\n", average.to_string(index=False),
           "\nBOOTSTRAP EXPLORATORIO\n", pd.DataFrame(contrasts).to_string(index=False),
           "\nEFECTOS AISLADOS\n", pd.DataFrame(effects).to_string(index=False),
           "\nTODAS LAS PRUEBAS NUEVAS\n", results.to_string(index=False),
           "\nREFERENCIAS PREVIAS REUTILIZADAS SIN ENTRENAR\n", refs.to_string(index=False),
           "\nVERIFICACIÓN: 208 filas únicas, métricas recalculadas, log1p presente en todas las variantes,\n"
           "invariancia temporal de extras y firmas contra pruebas previas: PASSED.\n"]
    (OUT / "RESULTADOS_RF_MEJORADO.txt").write_text("\n".join(log), encoding="utf-8")
    print(decisions.to_string(index=False), flush=True)
    return decisions


def review_completed():
    """No fitting: validate dedup records and contrast the compact log candidate."""
    registry = json.loads((OUT / "registro_pruebas.json").read_text(encoding="utf-8"))
    info = json.loads((OUT / "configuracion.json").read_text(encoding="utf-8"))
    previous = json.loads((PREVIOUS / "configuracion.json").read_text(encoding="utf-8"))
    scores = pd.read_csv(OUT / "01_metricas_nuevas.csv")
    assert len(registry) == 80 and len(scores) == 208
    prior_signatures = {trial_key(cols, previous["model_parameters"]["random_forest"][level], "rate", year, level, previous["source_sha256"])
                        for year in [2021, 2024] for level in ["seccion"] + list(base.LEVELS) for cols in previous["features"].values()}
    for key, trial in registry.items():
        assert trial["status"] == "complete" and key not in prior_signatures
        assert key == trial_key(trial["features"], trial["parameters"], trial["target"], trial["year"], trial["level"], trial["data_sha256"])
        assert {"SAME_LOG_LN", "RECENT_LOG_LN"}.issubset(trial["features"])
        pred = pd.read_parquet(DATA / f"prediction_{key}.parquet")
        row = scores.loc[scores.year.eq(trial["year"]) & scores.level.eq(trial["level"])
                         & scores.approach.eq("directo") & scores.variant.eq(trial["variant"])].iloc[0]
        actual = base.metrics(pred.Y, pred.PRED, pred.TARGET_D)
        assert pred.PRED.between(0, 1).all() and len(pred) == row.n
        for col in ["mae_pp", "rmse_pp", "r2", "bias_pp", "wmae_pp"]:
            assert np.isclose(actual[col], row[col], atol=1e-9)
    old_preds = pd.read_csv(PREVIOUS / "07_predicciones_candidatos_seleccionados.csv.gz")
    comparisons = []
    for year in [2021, 2024]:
        key = next(key for key, value in registry.items() if value["year"] == year
                   and value["level"] == "seccion" and value["variant"] == "R01_logs_grupos")
        new = pd.read_parquet(DATA / f"prediction_{key}.parquet")
        old = old_preds.loc[old_preds.year.eq(year) & old_preds.level.eq("seccion")]
        pair = new[["EDOCVE", "SECCION", "Y", "PRED"]].merge(old[["EDOCVE", "SECCION", "Y", "PRED"]],
            on=["EDOCVE", "SECCION"], suffixes=("_NEW", "_OLD"), validate="one_to_one")
        assert len(pair) == len(old) and np.allclose(pair.Y_NEW, pair.Y_OLD)
        pair["Y"] = pair.Y_NEW
        mapping = pd.read_parquet(DATA / "cache" / info["cache_id"] / f"{year}_mapping.parquet")
        pair = pair.merge(mapping[["EDOCVE", "SECCION", "MPIOCVE"]], on=["EDOCVE", "SECCION"], validate="one_to_one")
        for scope, columns in [("municipio", ["EDOCVE", "MPIOCVE"]), ("entidad", ["EDOCVE"])]:
            comparisons.append({"year": year, "variant": "R01_logs_grupos", "cluster": scope, **bootstrap(pair, columns)})
    comparisons = pd.DataFrame(comparisons)
    comparisons.to_csv(OUT / "11_bootstrap_logs_vs_rf_previo.csv", index=False)
    check = "VERIFICACIÓN INDEPENDIENTE: 80 firmas completas únicas, cero coincidencias con ronda previa,\nlog1p(LN) en todos los ajustes y métricas de 80 predicciones directas recalculadas: PASSED.\nNo se ejecutó ningún entrenamiento durante esta revisión.\n"
    (OUT / "12_VERIFICACION.txt").write_text(check, encoding="utf-8")
    with (OUT / "RESULTADOS_RF_MEJORADO.txt").open("a", encoding="utf-8") as fh:
        fh.write("\n\n" + check + "\nBOOTSTRAP R01 LOGS FRENTE A RF PREVIO\n" + comparisons.to_string(index=False)
                 + "\nIntervalos exploratorios condicionados a selección; no corrigen selección múltiple.\n")
    info["artifact_verification"] = "passed_80_native_predictions_and_signatures"
    info["review_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT / "configuracion.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(check + comparisons.to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--review-only", action="store_true", help="Validate completed trials and compare R01; never fits")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    if args.review_only:
        review_completed()
        return
    started = time.time()
    previous = json.loads((PREVIOUS / "configuracion.json").read_text(encoding="utf-8"))
    data_hash = hashlib.sha256(base.MASTER.read_bytes()).hexdigest()
    assert data_hash == previous["source_sha256"], "Data changed: prior metrics cannot be compared as matched cohorts"
    configs = variants()
    frames, mappings, cache_id = make_frames(data_hash)
    for year in [2021, 2024]:
        old = pd.read_parquet(ROOT / f"reports/dual_history/predictions/predictions_{year}_temporal_dual.parquet")
        current = frames[year]["seccion"].merge(old[["EDOCVE", "TGT_SECCION", "Y_ABSTENCION"]].rename(
            columns={"TGT_SECCION": "SECCION"}), on=["EDOCVE", "SECCION"], validate="one_to_one")
        assert len(current) == len(old) and np.allclose(current.Y, current.Y_ABSTENCION)
    old_signatures = set()
    for year in [2021, 2024]:
        for level in ["seccion"] + list(base.LEVELS):
            for columns in previous["features"].values():
                old_signatures.add(trial_key(columns, previous["model_parameters"]["random_forest"][level], "rate", year, level, data_hash))
    signatures = []
    for year in [2021, 2024]:
        for level in ["seccion"] + list(base.LEVELS):
            for config in configs.values():
                key = trial_key(config["features"], model_for(config, level).named_steps["model"].get_params(), config["target"], year, level, data_hash)
                assert key not in old_signatures, "Refusing to repeat a previous fit"
                signatures.append(key)
    assert len(signatures) == len(set(signatures)) == 80
    print("Checks passed: 80 unique NEW fits; zero repeated previous configurations; logs and temporal inputs verified", flush=True)
    if args.smoke:
        return
    registry_path = OUT / "registro_pruebas.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    rows, predictions, importances = [], {}, []
    run_info = {"created_utc": datetime.now(timezone.utc).isoformat(), "data_sha256": data_hash,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "cache_id": cache_id,
                "sklearn": sklearn.__version__, "seed": 42, "planned_unique_fits": 80,
                "repeated_prior_fits": 0, "completed_new_fits": 0, "reused_new_fits": 0}
    manifest = [{"variant": name, "column": col, "description": config["description"]}
                for name, config in configs.items() for col in config["features"]]
    pd.DataFrame(manifest).to_csv(OUT / "variables_por_variante.csv", index=False)
    for year in [2021, 2024]:
        for level in ["seccion"] + list(base.LEVELS):
            train = pd.concat([frames[y][level] for y in [2015, 2018, 2021] if y < year], ignore_index=True)
            test = frames[year][level]
            assert train.TARGET_YEAR.max() < year
            for name, config in configs.items():
                model = model_for(config, level)
                params = model.named_steps["model"].get_params()
                key = trial_key(config["features"], params, config["target"], year, level, data_hash)
                assert key not in old_signatures
                old = registry.get(key)
                path = DATA / f"prediction_{key}.parquet"
                if old and old["status"] == "complete" and path.exists():
                    assert old["cache_id"] == cache_id, "Feature definitions changed; completed cache cannot be silently reused"
                    cached = pd.read_parquet(path)
                    assert np.allclose(cached.Y, test.Y) and len(cached) == len(test)
                    pred = cached.PRED.to_numpy()
                    seconds = old["fit_seconds"]
                    run_info["reused_new_fits"] += 1
                    print(f"REUSE {year} {level} {name}: completed signature", flush=True)
                else:
                    t0 = time.time()
                    ytrain = train.Y - train.SAME_PCT_ABSTENCION if config["target"] == "delta_same" else train.Y
                    model.fit(train[config["features"]], ytrain)
                    pred = model.predict(test[config["features"]])
                    if config["target"] == "delta_same":
                        pred += test.SAME_PCT_ABSTENCION.to_numpy()
                    pred = np.clip(pred, 0, 1)
                    seconds = time.time() - t0
                    save_predictions(test, pred, key)
                    registry[key] = {"status": "complete", "variant": name, "year": year, "level": level,
                        "target": config["target"], "features": config["features"], "parameters": params,
                        "fit_seconds": seconds, "data_sha256": data_hash, "cache_id": cache_id}
                    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
                    feature_names = model.named_steps["prep"].get_feature_names_out()
                    importances.extend({"year": year, "level": level, "variant": name, "feature": col,
                        "training_impurity_importance": float(value)} for col, value in zip(feature_names, model.named_steps["model"].feature_importances_))
                    run_info["completed_new_fits"] += 1
                row = record(rows, year, level, "directo", name, config, "none", test, pred, seconds, key)
                predictions[(year, level, "directo", name, "none")] = pd.read_parquet(path)
                if level == "seccion":
                    for target_level, keys in base.LEVELS.items():
                        for weight in ["RECENT_LN", "RECENT_D"]:
                            agg = base.aggregate_predictions(test, mappings[year], target_level, pred, weight)
                            merged = frames[year][target_level].merge(agg, on=keys, validate="one_to_one")
                            record(rows, year, target_level, "agregado", name, config, weight, merged, merged.PRED, seconds, key)
                            predictions[(year, target_level, "agregado", name, weight)] = merged[keys + ["Y", "TARGET_D", "TARGET_LN", "N_SECTIONS"]].assign(PRED=merged.PRED)
                print(f"{year} {level} {name}: MAE={row['mae_pp']:.3f}, RMSE={row['rmse_pp']:.3f}, Top20={row['top20']:.3f}, {seconds:.1f}s", flush=True)
                pd.DataFrame(rows).to_csv(OUT / "01_metricas_nuevas.csv", index=False)
    for year in frames:
        frames[year]["mapping"] = mappings[year]
    if importances:
        path = OUT / "10_importancias_entrenamiento.csv"
        new = pd.DataFrame(importances)
        if path.exists():
            new = pd.concat([pd.read_csv(path), new]).drop_duplicates(["year", "level", "variant", "feature"], keep="last")
        new.to_csv(path, index=False)
    run_info["elapsed_seconds"] = time.time() - started
    run_info["parameters"] = {name: {level: model_for(config, level).named_steps["model"].get_params()
                                    for level in ["seccion"] + list(base.LEVELS)} for name, config in configs.items()}
    run_info["variants"] = configs
    (OUT / "configuracion.json").write_text(json.dumps(run_info, ensure_ascii=False, indent=2), encoding="utf-8")
    report(rows, predictions, frames, previous, run_info)
    print(f"DONE: {len(rows)} metrics; {run_info['completed_new_fits']} new fits; {run_info['reused_new_fits']} reused; {time.time()-started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
