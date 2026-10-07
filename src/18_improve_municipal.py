"""Isolated municipal RF/ExtraTrees/boosting backtests; no production writes."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rf_previous', ROOT / 'src/17_improve_random_forest.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
base = old.base
OUT = ROOT / 'reports/experiment_municipal_improved'
DATA = ROOT / 'data/processed/experiment_municipal_improved'
KEYS = ['EDOCVE', 'MPIOCVE']


def municipal_sources(master):
    """Full source-year records only; no future cohort membership in summaries."""
    result = {}
    for year, d in master.groupby('AELEC'):
        d = d.copy()
        d['A'] = base.divide(d.NV, d.SV + d.NV)
        d['A_LN'] = d.A * d.LN
        d['LN2'] = d.LN ** 2
        d['URBAN_LN'] = d.LN * d.TIPOSEC.eq('U')
        d['RURAL_LN'] = d.LN * d.TIPOSEC.eq('R')
        g = d.groupby(KEYS)
        a = g.agg(M_LOG_N=('SECCION', 'size'), M_LOG_TOTAL_LN=('LN', 'sum'),
                  M_A_STD=('A', 'std'), M_A_MIN=('A', 'min'), M_A_MAX=('A', 'max'),
                  M_A_MEAN=('A', 'mean'), M_LN_MAX=('LN', 'max'), M_LN2=('LN2', 'sum'),
                  M_WEIGHTED_A=('A_LN', 'sum'), M_PROP_U=('URBAN_LN', 'sum'),
                  M_PROP_R=('RURAL_LN', 'sum'), M_AGE_STD=('EDAD_PROM_LN', 'std'))
        total = a.M_LOG_TOTAL_LN.copy()
        a['M_SIZE_CONCENTRATION'] = a.M_LN2 / total ** 2
        a['M_MAX_SECTION_SHARE'] = a.M_LN_MAX / total
        for c in ['M_WEIGHTED_A', 'M_PROP_U', 'M_PROP_R']:
            a[c] /= total
        a = a.drop(columns=['M_LN_MAX', 'M_LN2'])
        for q, label in [(.1, '10'), (.25, '25'), (.5, '50'), (.75, '75'), (.9, '90')]:
            a['M_A_Q' + label] = g.A.quantile(q)
        a['M_A_IQR'] = a.M_A_Q75 - a.M_A_Q25
        a['M_A_90_10'] = a.M_A_Q90 - a.M_A_Q10
        a['M_MIXED_SHARE'] = 1 - a.M_PROP_U - a.M_PROP_R
        for c in ['M_LOG_N', 'M_LOG_TOTAL_LN']:
            a[c] = np.log1p(a[c])
        result[int(year)] = a.reset_index()
    return result


def attach(frame, mapping, sources, year, level):
    f = frame.copy()
    if level == 'seccion':
        f = f.merge(mapping[['EDOCVE', 'SECCION', 'MPIOCVE']], on=['EDOCVE', 'SECCION'], validate='one_to_one')
    for prefix, source_year in [('SAME_', year - 6), ('RECENT_', year - 3)]:
        source = sources[source_year]
        f = f.merge(source.rename(columns={c: prefix + c for c in source if c not in KEYS}), on=KEYS, validate='many_to_one')
        f[prefix + 'M_LOCAL_GAP'] = f[prefix + 'PCT_ABSTENCION'] - f[prefix + 'M_WEIGHTED_A']
    for c in ['M_A_MEAN', 'M_A_STD', 'M_WEIGHTED_A', 'M_LOG_N', 'M_LOG_TOTAL_LN', 'M_PROP_U', 'M_PROP_R']:
        f['CHANGE_' + c] = f['RECENT_' + c] - f['SAME_' + c]
    return f


def observed_municipal_sources(master):
    """Separate observed electoral coverage from conditional weighted rate."""
    result = {}
    for year, d in master.groupby('AELEC'):
        d = d.copy()
        a = base.divide(d.NV, d.SV + d.NV)
        d['VALID_LN'] = d.LN.where(a.notna(), 0)
        d['WEIGHTED_A'] = a.fillna(0) * d.LN
        d['OBSERVED_D'] = d.SV + d.NV
        totals = d.groupby(KEYS)[['LN', 'VALID_LN', 'WEIGHTED_A', 'OBSERVED_D']].sum()
        totals['M_Z_VALID_LN_SHARE'] = base.divide(totals.VALID_LN, totals.LN)
        totals['M_Z_KNOWN_ELECTOR_SHARE'] = base.divide(totals.OBSERVED_D, totals.LN)
        totals['M_Z_OBSERVED_WEIGHTED_A'] = base.divide(totals.WEIGHTED_A, totals.VALID_LN)
        result[int(year)] = totals[['M_Z_VALID_LN_SHARE', 'M_Z_KNOWN_ELECTOR_SHARE', 'M_Z_OBSERVED_WEIGHTED_A']].reset_index()
    return result


def configurations(extra, extended=False):
    v = old.variants()
    logs = [c for c in v['R01_logs_grupos']['features'] if 'X_LOG_' in c]
    blocks = base.feature_sets()
    sets = {'logs': v['R01_logs_grupos']['features'], 'long': v['R05_historia_larga']['features'],
            'municipal': list(dict.fromkeys(v['R01_logs_grupos']['features'] + extra)),
            'compact': list(dict.fromkeys(blocks['B2_demografia_grupos'] + logs + extra))}
    trials = [
        ('M01_rf_municipal', 'rf', 'municipal', 'rate', 'uniform', 'broad'),
        ('M02_rf_balance', 'rf', 'logs', 'rate', 'municipal', 'broad'),
        ('M03_rf_long_balance', 'rf', 'long', 'rate', 'municipal', 'broad'),
        ('M04_extra_logs', 'extra', 'logs', 'rate', 'uniform', 'broad'),
        ('M05_extra_municipal_balance', 'extra', 'municipal', 'rate', 'municipal', 'broad'),
        ('M06_gb_logs', 'gb', 'logs', 'rate', 'uniform', 'regular'),
        ('M07_gb_long', 'gb', 'long', 'rate', 'uniform', 'regular'),
        ('M08_gb_municipal', 'gb', 'municipal', 'rate', 'uniform', 'regular'),
        ('M09_gb_compact', 'gb', 'compact', 'rate', 'uniform', 'regular'),
        ('M10_gb_logs_balance', 'gb', 'logs', 'rate', 'municipal', 'regular'),
        ('M11_gb_municipal_balance', 'gb', 'municipal', 'rate', 'municipal', 'regular'),
        ('M12_gb_logs_absolute', 'gb', 'logs', 'rate', 'municipal', 'absolute'),
        ('M13_gb_municipal_absolute', 'gb', 'municipal', 'rate', 'municipal', 'absolute'),
        ('M14_gb_change_logs', 'gb', 'logs', 'delta_same', 'municipal', 'regular'),
        ('M15_gb_change_long', 'gb', 'long', 'delta_same', 'municipal', 'regular'),
        ('M16_gb_municipal_shallow', 'gb', 'municipal', 'rate', 'municipal', 'shallow'),
    ]
    if extended:
        history = [c for c in v['R05_historia_larga']['features'] if 'X_HIST_' in c]
        core = [c for c in extra if c.endswith(('M_LOG_N', 'M_LOG_TOTAL_LN', 'M_A_STD', 'M_SIZE_CONCENTRATION', 'M_PROP_R', 'M_AGE_STD'))]
        sets['logs_history'] = list(dict.fromkeys(sets['logs'] + history))
        proper_support = [p + c for p in ['SAME_', 'RECENT_'] for c in ['M_Z_VALID_LN_SHARE', 'M_Z_KNOWN_ELECTOR_SHARE', 'M_Z_OBSERVED_WEIGHTED_A']]
        proper_support += ['CHANGE_M_Z_OBSERVED_WEIGHTED_A', 'CHANGE_M_Z_KNOWN_ELECTOR_SHARE']
        sets['municipal_core'] = list(dict.fromkeys(sets['logs'] + core + proper_support))
        sets['no_state'] = [c for c in sets['logs'] if c != 'EDOCVE']
        sets['ridge_compact'] = blocks['B1_historia_demografia'] + ['DELTA_ABST', 'DELTA_LOG_LN', 'DELTA_AGE']
        trials.extend([
            ('M17_rf_logs_history', 'rf', 'logs_history', 'rate', 'uniform', 'baseline'),
            ('M18_rf_municipal_core', 'rf', 'municipal_core', 'rate', 'uniform', 'baseline'),
            ('M19_rf_without_state', 'rf', 'no_state', 'rate', 'uniform', 'baseline'),
            ('M20_gb_logs_history_absolute', 'gb', 'logs_history', 'rate', 'municipal', 'absolute'),
            ('M21_gb_change_logs_history', 'gb', 'logs_history', 'delta_same', 'municipal', 'regular'),
            ('M22_ridge_compact', 'ridge', 'ridge_compact', 'rate', 'municipal', 'scaled100'),
            ('M23_ridge_logs', 'ridge', 'logs', 'rate', 'municipal', 'scaled100'),
            ('M24_ridge_change_logs', 'ridge', 'logs', 'delta_same', 'municipal', 'scaled1000'),
            ('M25_rf_more_trees', 'rf', 'logs', 'rate', 'uniform', 'more_trees'),
            ('M26_rf_smoother', 'rf', 'logs', 'rate', 'uniform', 'smoother'),
        ])
    return {name: dict(kind=kind, features=sets[block], block=block, target=target, weighting=weight, profile=profile)
            for name, kind, block, target, weight, profile in trials}


def model_for(config, level):
    kind = config['kind']
    model = base.make_model('gradient_boosting' if kind == 'gb' else 'random_forest', config['features'], level)
    if kind == 'ridge':
        model = Pipeline([('prep', model.named_steps['prep']), ('scale', StandardScaler()),
                          ('model', Ridge(alpha=1000. if config['profile'] == 'scaled1000' else 100., solver='lsqr'))])
    elif kind == 'gb':
        pars = dict(max_iter=240, learning_rate=.04, max_leaf_nodes=15,
                    min_samples_leaf=80 if level == 'seccion' else 20,
                    l2_regularization=15., early_stopping=False, random_state=42)
        if config['profile'] == 'absolute':
            pars.update(loss='absolute_error', max_iter=220)
        if config['profile'] == 'shallow':
            pars.update(max_leaf_nodes=7, max_iter=320, l2_regularization=30.)
        model.named_steps['model'].set_params(**pars)
    elif kind == 'extra':
        model.set_params(model=ExtraTreesRegressor(n_estimators=96, max_depth=16,
                          min_samples_leaf=15 if level == 'seccion' else 4,
                          max_features=.7, n_jobs=2, random_state=42))
    else:
        model.named_steps['model'].set_params(n_estimators=96, max_depth=14,
                  min_samples_leaf=15 if level == 'seccion' else 4, max_features='sqrt', max_samples=.85)
        if config['profile'] in ['baseline', 'more_trees', 'smoother']:
            model.named_steps['model'].set_params(n_estimators=64, max_depth=12,
                          min_samples_leaf=25 if level == 'seccion' else 8, max_samples=.8)
            if config['profile'] == 'more_trees':
                model.named_steps['model'].set_params(n_estimators=128)
            if config['profile'] == 'smoother':
                model.named_steps['model'].set_params(max_depth=10, min_samples_leaf=60 if level == 'seccion' else 15)
    return model


def fit_weights(train, config, level):
    if config['weighting'] == 'uniform' or level == 'municipio':
        return None
    # Each municipality-election has equal total mass, distributed by source LN.
    den = train.groupby(['TARGET_YEAR'] + KEYS).RECENT_LN.transform('sum')
    w = train.RECENT_LN / den
    return (w / w.mean()).to_numpy()


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def review_results():
    """Additional error slices, using stored predictions only; zero fits."""
    registry = json.loads((OUT / 'registro_pruebas.json').read_text(encoding='utf-8'))
    prior_info = json.loads((old.PREVIOUS / 'configuracion.json').read_text(encoding='utf-8'))
    old_keys = set(json.loads((old.OUT / 'registro_pruebas.json').read_text(encoding='utf-8')))
    for year in [2021, 2024]:
        for level in ['seccion', 'municipio']:
            for kind in ['random_forest', 'gradient_boosting']:
                for cols in prior_info['features'].values():
                    old_keys.add(old.trial_key(cols, prior_info['model_parameters'][kind][level], 'rate', year, level, prior_info['source_sha256']))
    cached_info = json.loads((old.OUT / 'configuracion.json').read_text(encoding='utf-8'))
    cached_folder = old.DATA / 'cache' / cached_info['cache_id']
    truths = {(year, level): pd.read_parquet(cached_folder / f'{year}_{level}.parquet')
              for year in [2021, 2024] for level in ['seccion', 'municipio']}
    for key, trial in registry.items():
        config = trial['config']
        level, year = trial['level'], trial['year']
        payload = dict(features=sorted(config['features']), parameters=trial['parameters'], target=config['target'],
            weighting=config['weighting'] if level == 'seccion' else 'uniform', year=year, level=level,
            data_hash=trial['data_sha256'], feature_definition=trial['feature_definition'], training_policy='all_prior_clean10_v16')
        if config['kind'] == 'ridge':
            payload['preprocessing'] = 'median_indicators_onehot_v16_then_standard_scaler_v1'
        if any('_M_Z_' in c for c in config['features']):
            payload['support_definition'] = old.fingerprint(__import__('inspect').getsource(observed_municipal_sources))
            payload['support_change_definition'] = 'recent_minus_same_v1'
        assert key == old.fingerprint(payload) and trial['status'] == 'complete'
        if config['weighting'] == 'uniform' or level == 'municipio':
            assert old.trial_key(config['features'], trial['parameters'], config['target'], year, level, trial['data_sha256']) not in old_keys
        pred = pd.read_parquet(DATA / f'prediction_{key}.parquet')
        truth = truths[(year, level)]
        keys = ['EDOCVE', 'SECCION'] if level == 'seccion' else KEYS
        assert np.array_equal(pred[keys].to_numpy(), truth[keys].to_numpy())
        assert np.allclose(pred.Y, truth.Y) and np.allclose(pred.TARGET_D, truth.TARGET_D)
        assert pred.PRED.between(0, 1).all()
    verification = f'PASSED: {len(registry)} unique complete signatures including retained pilot; zero exact previous unweighted fits; native prediction keys/truth/bounds verified. No training.\n'
    (OUT / '12_VERIFICACION.txt').write_text(verification, encoding='utf-8')
    # Targeted fixed ensembles of the two NEW history models, no refitting or learned weights.
    scores = pd.read_csv(OUT / '02_metricas_con_mezclas.csv')
    hybrid_rows = []
    for year in [2021, 2024]:
        truth = truths[(year, 'municipio')]
        direct = pd.read_parquet(DATA / ('municipal_' + old.fingerprint((year, 'directo', 'M17_rf_logs_history', 'none')) + '.parquet'))
        for weight in ['RECENT_LN', 'RECENT_D']:
            agg = pd.read_parquet(DATA / ('municipal_' + old.fingerprint((year, 'agregado', 'M17_rf_logs_history', weight)) + '.parquet'))
            pair = agg.merge(direct[KEYS + ['PRED']], on=KEYS, suffixes=('_AGG', '_DIRECT'), validate='one_to_one')
            for alpha in [.25, .5, .75]:
                name = f'H01_historia_ambos_a{alpha}'
                frame = truth.merge(pair[KEYS + ['PRED_AGG', 'PRED_DIRECT']], on=KEYS, validate='one_to_one')
                pred = alpha * frame.PRED_DIRECT + (1 - alpha) * frame.PRED_AGG
                key = (year, 'hibrido_historia', name, weight)
                saved = frame[KEYS + ['Y', 'TARGET_D', 'TARGET_LN']].assign(PRED=pred)
                path = DATA / ('municipal_' + old.fingerprint(key) + '.parquet')
                saved.to_parquet(path, index=False)
                reloaded = pd.read_parquet(path)
                metric = base.metrics(reloaded.Y, reloaded.PRED, reloaded.TARGET_D)
                hybrid_rows.append(dict(year=year, level='municipio', approach='hibrido_historia', variant=name,
                    weight=weight, fit_seconds=0., signature=old.fingerprint(key), **metric,
                    full_reference_mae_pp=np.mean(abs(pred - frame.Y_FULL_REFERENCE)) * 100))
    hybrids = pd.DataFrame(hybrid_rows)
    hybrids.to_csv(OUT / '13_metricas_hibridos_historia.csv', index=False)
    scores = pd.concat([scores.loc[scores.approach.ne('hibrido_historia')], hybrids], ignore_index=True)
    assert not scores.duplicated(['year', 'approach', 'variant', 'weight']).any()
    scores.to_csv(OUT / '02_metricas_con_mezclas.csv', index=False)
    ref_scores = scores.loc[scores.variant.eq('PREV_R01_logs_grupos') & scores.approach.eq('agregado')
        & scores.weight.eq('RECENT_LN'), ['year', 'mae_pp']].rename(columns={'mae_pp': 'reference_mae_pp'})
    compare = scores.merge(ref_scores, on='year', validate='many_to_one')
    compare['delta_mae_pp'] = compare.mae_pp - compare.reference_mae_pp
    compare['ratio'] = compare.mae_pp / compare.reference_mae_pp
    updated = compare.groupby(['approach', 'variant', 'weight']).agg(years=('year', 'nunique'),
        mean_mae_pp=('mae_pp', 'mean'), worst_ratio=('ratio', 'max'), mean_rmse_pp=('rmse_pp', 'mean'),
        mean_wmae_pp=('wmae_pp', 'mean'), mean_top20=('top20', 'mean')).reset_index()
    updated = updated.loc[updated.years.eq(2)].sort_values('mean_mae_pp')
    updated.to_csv(OUT / '03_ranking.csv', index=False)
    updated_winners = updated.groupby('approach', sort=False).head(1)
    updated_winners.to_csv(OUT / '04_mejores_por_enfoque.csv', index=False)
    compare.merge(updated_winners[['approach', 'variant', 'weight']], on=['approach', 'variant', 'weight'],
                  validate='many_to_one').to_csv(OUT / '05_metricas_seleccionadas.csv', index=False)
    ranking = pd.read_csv(OUT / '03_ranking.csv')
    candidate = ranking.iloc[0]
    info = json.loads((old.OUT / 'configuracion.json').read_text())
    folder = old.DATA / 'cache' / info['cache_id']
    rows, changes, intervals = [], [], []
    for year in [2021, 2024]:
        new_key = (year, candidate.approach, candidate.variant, candidate.weight)
        ref_key = (year, 'agregado', 'PREV_R01_logs_grupos', 'RECENT_LN')
        new = pd.read_parquet(DATA / ('municipal_' + old.fingerprint(new_key) + '.parquet'))
        ref = pd.read_parquet(DATA / ('municipal_' + old.fingerprint(ref_key) + '.parquet'))
        inputs = pd.read_parquet(folder / f'{year}_municipio.parquet')
        pair = new.merge(ref[KEYS + ['Y', 'PRED']], on=KEYS, suffixes=('_NEW', '_OLD'), validate='one_to_one')
        assert np.allclose(pair.Y_NEW, pair.Y_OLD)
        pair['Y'] = pair.Y_NEW
        pair = pair.merge(inputs[KEYS + ['RECENT_LOG_LN', 'RECENT_PROP_U', 'RECENT_PROP_R']], on=KEYS, validate='one_to_one')
        pair['SIZE'] = pd.qcut(pair.RECENT_LOG_LN, 4, labels=['Q1_small', 'Q2', 'Q3', 'Q4_large'])
        pair['COMPOSITION'] = np.select([pair.RECENT_PROP_U.ge(.8), pair.RECENT_PROP_R.ge(.8)],
                                       ['>=80%_urban', '>=80%_rural'], default='other_mix')
        pair['ERROR_NEW'] = abs(pair.PRED_NEW - pair.Y) * 100
        pair['ERROR_OLD'] = abs(pair.PRED_OLD - pair.Y) * 100
        for dimension in ['SIZE', 'COMPOSITION', 'EDOCVE']:
            for group, g in pair.groupby(dimension, observed=True):
                rows.append(dict(year=year, dimension=dimension, group=str(group), n=len(g),
                    new_mae_pp=g.ERROR_NEW.mean(), old_mae_pp=g.ERROR_OLD.mean(),
                    delta_mae_pp=(g.ERROR_NEW - g.ERROR_OLD).mean()))
        intervals.append(dict(year=year, approach=candidate.approach, variant=candidate.variant,
                              weight=candidate.weight, **old.bootstrap(pair, ['EDOCVE'])))
        changes.append(dict(year=year, improved_municipalities=int((pair.ERROR_NEW < pair.ERROR_OLD).sum()),
                            worsened_municipalities=int((pair.ERROR_NEW > pair.ERROR_OLD).sum()), n=len(pair)))
    pd.DataFrame(rows).to_csv(OUT / '07_diagnostico_por_tamano_composicion_entidad.csv', index=False)
    pd.DataFrame(changes).to_csv(OUT / '08_municipios_mejorados.csv', index=False)
    pd.DataFrame(intervals).to_csv(OUT / '09_bootstrap_ganador_global.csv', index=False)
    robust = ranking.sort_values(['worst_ratio', 'mean_mae_pp']).head(12)
    robust.to_csv(OUT / '10_ranking_estabilidad.csv', index=False)
    with (OUT / 'RESULTADOS_MUNICIPALES.txt').open('a', encoding='utf-8') as f:
        f.write('\n' + verification)
        f.write('\nHÍBRIDOS NUEVOS: alpha*RF M17 directo + (1-alpha)*RF M17 agregado; pesos fijos, cero ajustes.\n')
        f.write(hybrids.to_string(index=False))
        f.write('\nGANADORES ACTUALIZADOS\n' + updated_winners.to_string(index=False))
        f.write('\n\nREVISIÓN ADICIONAL SIN ENTRENAR\n' + pd.DataFrame(rows).to_string(index=False))
        f.write('\nMUNICIPIOS MEJORADOS\n' + pd.DataFrame(changes).to_string(index=False))
        f.write('\nBOOTSTRAP GANADOR GLOBAL\n' + pd.DataFrame(intervals).to_string(index=False))
        f.write('\nRANKING DE ESTABILIDAD\n' + robust.to_string(index=False))
    print('ADDITIONAL REVIEW PASSED; no training', flush=True)
    print(pd.DataFrame(intervals).to_string(index=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--status', action='store_true', help='Read experiment process and checkpoint status only')
    parser.add_argument('--stop-experiment', action='store_true', help='Interrupt only another running instance of this experiment')
    parser.add_argument('--review-only', action='store_true', help='Municipal error slices from stored predictions, no training')
    parser.add_argument('--extend', action='store_true', help='Targeted ablations and Ridge controls; reuse all completed initial trials')
    parser.add_argument('--audit-inputs', action='store_true', help='Read source support counts only, no training')
    parser.add_argument('--focus', action='store_true', help='Prune redundant costly sectional GB variants after >25% worse MAE in 2021')
    args = parser.parse_args()
    if args.audit_inputs:
        d = pd.read_csv(base.MASTER, usecols=['AELEC', 'LN', 'SV', 'NV'])
        d['ZERO_D_POSITIVE_LN'] = ((d.SV + d.NV).le(0) & d.LN.gt(0)).astype(int)
        print(d.groupby('AELEC').ZERO_D_POSITIVE_LN.sum().to_string())
        return
    if args.review_only:
        review_results()
        return
    if args.status or args.stop_experiment:
        for folder in Path('/proc').glob('[0-9]*'):
            try:
                cmdline = (folder / 'cmdline').read_bytes().replace(b'\0', b' ').decode()
                if 'python src/18_improve_municipal.py' in cmdline and '--status' not in cmdline and '--stop-experiment' not in cmdline:
                    stat = (folder / 'stat').read_text().split()
                    status = (folder / 'status').read_text().splitlines()
                    print(dict(pid=folder.name, cpu_ticks=int(stat[13]) + int(stat[14]),
                               memory=[v for v in status if v.startswith(('VmRSS:', 'Threads:'))]), flush=True)
                    if args.stop_experiment:
                        import signal
                        os.kill(int(folder.name), signal.SIGINT)
                        print('Sent SIGINT to municipal experiment only', flush=True)
            except (OSError, UnicodeError, IndexError):
                continue
        reg = OUT / 'registro_pruebas.json'
        print('Completed unique trials:', len(json.loads(reg.read_text())) if reg.exists() else 0)
        return
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    previous_info = json.loads((old.OUT / 'configuracion.json').read_text(encoding='utf-8'))
    data_hash = hashlib.sha256(base.MASTER.read_bytes()).hexdigest()
    assert data_hash == previous_info['data_sha256']
    folder = old.DATA / 'cache' / previous_info['cache_id']
    frames, mappings = {}, {}
    master = pd.read_csv(base.MASTER, low_memory=False)
    sources = municipal_sources(master)
    observed_sources = observed_municipal_sources(master) if args.extend else None
    # Strong chronological check: changing all outcomes at/after target leaves inputs intact.
    for year in [2021, 2024]:
        changed = master.copy()
        mask = changed.AELEC.ge(year)
        changed.loc[mask, ['SV', 'NV']] = changed.loc[mask, ['NV', 'SV']].to_numpy()
        perturbed = municipal_sources(changed)
        for y in sources:
            if y < year:
                pd.testing.assert_frame_equal(sources[y], perturbed[y])
        if args.extend:
            observed_perturbed = observed_municipal_sources(changed)
            for y in observed_sources:
                if y < year:
                    pd.testing.assert_frame_equal(observed_sources[y], observed_perturbed[y])
    for year in [2015, 2018, 2021, 2024]:
        mappings[year] = pd.read_parquet(folder / f'{year}_mapping.parquet')
        frames[year] = {level: attach(pd.read_parquet(folder / f'{year}_{level}.parquet'), mappings[year], sources, year, level)
                        for level in ['seccion', 'municipio']}
        if args.extend:
            for level in frames[year]:
                f = frames[year][level]
                for prefix, source_year in [('SAME_', year - 6), ('RECENT_', year - 3)]:
                    s = observed_sources[source_year]
                    f = f.merge(s.rename(columns={c: prefix + c for c in s if c not in KEYS}), on=KEYS, validate='many_to_one')
                for c in ['M_Z_OBSERVED_WEIGHTED_A', 'M_Z_KNOWN_ELECTOR_SHARE']:
                    f['CHANGE_' + c] = f['RECENT_' + c] - f['SAME_' + c]
                frames[year][level] = f
    # Preserve original feature sets/signatures when extending; new support fields belong only to M18.
    extra = [c for c in frames[2024]['seccion'] if c.startswith(('SAME_M_', 'RECENT_M_', 'CHANGE_M_')) and '_M_Z_' not in c]
    configs = configurations(extra, extended=args.extend)
    feature_definition = old.fingerprint([__import__('inspect').getsource(f) for f in [municipal_sources, attach, fit_weights]])
    previous_registry = json.loads((old.OUT / 'registro_pruebas.json').read_text(encoding='utf-8'))
    previous_signatures = set(previous_registry)
    old_config = json.loads((old.PREVIOUS / 'configuracion.json').read_text(encoding='utf-8'))
    for year in [2021, 2024]:
        for level in ['seccion', 'municipio']:
            for kind in ['random_forest', 'gradient_boosting']:
                for cols in old_config['features'].values():
                    previous_signatures.add(old.trial_key(cols, old_config['model_parameters'][kind][level], 'rate', year, level, data_hash))
    plan = []
    checkpoint_path = OUT / 'registro_pruebas.json'
    completed_before_plan = json.loads(checkpoint_path.read_text(encoding='utf-8')) if checkpoint_path.exists() else {}
    staged_scores_path = OUT / '01_metricas_modelos.csv'
    staged_scores = pd.read_csv(staged_scores_path) if args.focus and staged_scores_path.exists() else None
    pruned = []
    for year in [2021, 2024]:
        for level in ['seccion', 'municipio']:
            for name, config in configs.items():
                model = model_for(config, level)
                params = model.named_steps['model'].get_params()
                for f in frames.values():
                    assert set(config['features']).issubset(f[level].columns)
                assert not any(c.startswith(('Y', 'TARGET', 'FULL')) for c in config['features'])
                # No added features: standard signature comparison suffices to reject previous runs.
                if config['block'] in ['logs', 'long'] and (level == 'municipio' or config['weighting'] == 'uniform'):
                    assert old.trial_key(config['features'], params, config['target'], year, level, data_hash) not in previous_signatures
                signature_payload = dict(features=sorted(config['features']), parameters=params, target=config['target'],
                    weighting=config['weighting'] if level == 'seccion' else 'uniform', year=year, level=level,
                    data_hash=data_hash, feature_definition=feature_definition, training_policy='all_prior_clean10_v16')
                if config['kind'] == 'ridge':
                    signature_payload['preprocessing'] = 'median_indicators_onehot_v16_then_standard_scaler_v1'
                if any('_M_Z_' in c for c in config['features']):
                    signature_payload['support_definition'] = old.fingerprint(__import__('inspect').getsource(observed_municipal_sources))
                    signature_payload['support_change_definition'] = 'recent_minus_same_v1'
                signature = old.fingerprint(signature_payload)
                if args.focus and year == 2024 and level == 'seccion' and name in [
                    'M11_gb_municipal_balance', 'M13_gb_municipal_absolute', 'M15_gb_change_long', 'M16_gb_municipal_shallow']:
                    if signature not in completed_before_plan:
                        assert staged_scores is not None
                        early = staged_scores.loc[staged_scores.year.eq(2021) & staged_scores.approach.eq('agregado')
                            & staged_scores.variant.eq(name) & staged_scores.weight.eq('RECENT_LN')].iloc[0]
                        ref = staged_scores.loc[staged_scores.year.eq(2021) & staged_scores.approach.eq('agregado')
                            & staged_scores.variant.eq('PREV_R01_logs_grupos') & staged_scores.weight.eq('RECENT_LN')].iloc[0]
                        assert early.mae_pp / ref.mae_pp > 1.25
                        pruned.append(dict(year=year, level=level, variant=name, ratio_2021=early.mae_pp / ref.mae_pp,
                            reason='Redundant GB variant >25% worse than RF R01 in 2021; representative loss/target/weight variants retained'))
                        continue
                plan.append((year, level, name, config, signature, params))
    expected_fits = (100 if args.extend else 60) - len(pruned)
    assert len({p[4] for p in plan}) == expected_fits
    save_json(OUT / 'plan_pruebas.json', {name: config for name, config in configs.items()})
    pd.DataFrame([dict(variant=name, feature=c) for name, config in configs.items() for c in config['features']]).to_csv(OUT / 'variables_por_variante.csv', index=False)
    if pruned:
        pd.DataFrame(pruned).to_csv(OUT / 'PODAS_BUSQUEDA.csv', index=False)
    print(f'CHECKS PASSED: {expected_fits} unique fits; 4 equivalent direct-level aliases reuse results; historical full-source inputs', flush=True)
    if args.smoke:
        return
    registry_path = OUT / 'registro_pruebas.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
    rows, predictions = [], {}
    fresh = reused = 0

    def record(year, approach, name, weight, frame, pred, seconds=0, signature='reused_prior'):
        row = dict(year=year, level='municipio', approach=approach, variant=name, weight=weight,
                   fit_seconds=seconds, signature=signature, **base.metrics(frame.Y, pred, frame.TARGET_D))
        row['full_reference_mae_pp'] = np.mean(abs(np.asarray(pred) - frame.Y_FULL_REFERENCE)) * 100
        rows.append(row)
        predictions[(year, approach, name, weight)] = frame[KEYS + ['Y', 'TARGET_D', 'TARGET_LN']].assign(PRED=np.asarray(pred))
        return row

    # Reuse ALL previous municipal results, not just previously selected winners.
    refs = []
    for report_dir, file in [(old.PREVIOUS, '01_metricas_todas.csv'), (old.OUT, '01_metricas_nuevas.csv')]:
        table = pd.read_csv(report_dir / file)
        table = table.loc[table.level.eq('municipio') & table.weight.ne('TARGET_D')].copy()
        table['source'] = report_dir.name
        refs.append(table)
    references = pd.concat(refs, ignore_index=True)
    references.to_csv(OUT / '00_referencias_previas.csv', index=False)
    # Section reference predictions available from the checkpointed RF R01 and R05.
    for year in [2021, 2024]:
        for name in ['R01_logs_grupos', 'R05_historia_larga']:
            for level in ['seccion', 'municipio']:
                key = next(k for k, r in previous_registry.items() if r['year'] == year and r['level'] == level and r['variant'] == name)
                p = pd.read_parquet(old.DATA / f'prediction_{key}.parquet')
                test = frames[year][level]
                assert np.allclose(test.Y, p.Y)
                if level == 'municipio':
                    record(year, 'directo', 'PREV_' + name, 'none', test, p.PRED)
                else:
                    for weight in ['RECENT_LN', 'RECENT_D']:
                        agg = base.aggregate_predictions(test, mappings[year], 'municipio', p.PRED, weight)
                        merged = frames[year]['municipio'].merge(agg, on=KEYS, validate='one_to_one')
                        record(year, 'agregado', 'PREV_' + name, weight, merged, merged.PRED)
    for year, level, name, config, signature, params in plan:
        train = pd.concat([frames[y][level] for y in [2015, 2018, 2021] if y < year], ignore_index=True)
        test = frames[year][level]
        assert train.TARGET_YEAR.max() < year
        path = DATA / f'prediction_{signature}.parquet'
        if signature in registry and path.exists():
            saved = pd.read_parquet(path)
            assert np.allclose(saved.Y, test.Y) and len(saved) == len(test)
            p = saved.PRED.to_numpy()
            seconds = registry[signature]['fit_seconds']
            reused += 1
        else:
            model = model_for(config, level)
            ytrain = train.Y - train.SAME_PCT_ABSTENCION if config['target'] == 'delta_same' else train.Y
            weights = fit_weights(train, config, level)
            kwargs = {} if weights is None else {'model__sample_weight': weights}
            t0 = time.time()
            model.fit(train[config['features']], ytrain, **kwargs)
            p = model.predict(test[config['features']])
            if config['target'] == 'delta_same':
                p += test.SAME_PCT_ABSTENCION.to_numpy()
            p = np.clip(p, 0, 1)
            seconds = time.time() - t0
            keys = ['EDOCVE', 'SECCION'] if level == 'seccion' else KEYS
            test[keys + ['Y', 'TARGET_D']].assign(PRED=p).to_parquet(path, index=False)
            registry[signature] = dict(year=year, level=level, variant=name, parameters=params,
                config=config, data_sha256=data_hash, feature_definition=feature_definition,
                fit_seconds=seconds, status='complete')
            save_json(registry_path, registry)
            fresh += 1
        # Independently recalculate prediction bounds / truth correspondence on disk.
        saved = pd.read_parquet(path)
        assert saved.PRED.between(0, 1).all() and np.allclose(saved.Y, test.Y)
        if level == 'municipio':
            row = record(year, 'directo', name, 'none', test, p, seconds, signature)
        else:
            for weight in ['RECENT_LN', 'RECENT_D']:
                agg = base.aggregate_predictions(test, mappings[year], 'municipio', p, weight)
                merged = frames[year]['municipio'].merge(agg, on=KEYS, validate='one_to_one')
                row = record(year, 'agregado', name, weight, merged, merged.PRED, seconds, signature)
        print(f'{year} {level} {name}: municipal MAE={row["mae_pp"]:.3f}, {seconds:.1f}s', flush=True)
        pd.DataFrame(rows).to_csv(OUT / '01_metricas_modelos.csv', index=False)

    # Fixed mixtures: no fitted weight or test-truth input. All mixtures documented.
    new_names = list(configs)
    for year in [2021, 2024]:
        for name in new_names:
            for approach, weight in [('agregado', 'RECENT_LN'), ('agregado', 'RECENT_D'), ('directo', 'none')]:
                if (year, approach, name, weight) not in predictions:
                    continue
                new = predictions[(year, approach, name, weight)]
                ref = predictions[(year, 'agregado', 'PREV_R01_logs_grupos', 'RECENT_LN')]
                pair = new.merge(ref[KEYS + ['PRED']], on=KEYS, suffixes=('', '_REF'), validate='one_to_one')
                for alpha in [.25, .5, .75]:
                    mix = alpha * pair.PRED + (1 - alpha) * pair.PRED_REF
                    record(year, 'mixto_' + approach, f'{name}_a{alpha}', weight, frames[year]['municipio'], mix)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / '02_metricas_con_mezclas.csv', index=False)
    # Baseline best mean RF from last round: R01 aggregation with LN.
    ref_scores = result.loc[result.variant.eq('PREV_R01_logs_grupos') & result.approach.eq('agregado') & result.weight.eq('RECENT_LN'), ['year', 'mae_pp']].rename(columns={'mae_pp': 'reference_mae_pp'})
    compare = result.merge(ref_scores, on='year', validate='many_to_one')
    compare['delta_mae_pp'] = compare.mae_pp - compare.reference_mae_pp
    compare['ratio'] = compare.mae_pp / compare.reference_mae_pp
    ranking = compare.groupby(['approach', 'variant', 'weight']).agg(years=('year', 'nunique'),
        mean_mae_pp=('mae_pp', 'mean'), worst_ratio=('ratio', 'max'), mean_rmse_pp=('rmse_pp', 'mean'),
        mean_wmae_pp=('wmae_pp', 'mean'), mean_top20=('top20', 'mean')).reset_index().sort_values('mean_mae_pp')
    ranking.loc[ranking.years.ne(2)].to_csv(OUT / '11_resultados_parciales_excluidos_ranking.csv', index=False)
    ranking = ranking.loc[ranking.years.eq(2)].copy()
    assert ranking.years.eq(2).all()
    ranking.to_csv(OUT / '03_ranking.csv', index=False)
    winners = ranking.groupby('approach', sort=False).head(1)
    winners.to_csv(OUT / '04_mejores_por_enfoque.csv', index=False)
    selected = compare.merge(winners[['approach', 'variant', 'weight']], on=['approach', 'variant', 'weight'], validate='many_to_one')
    selected.to_csv(OUT / '05_metricas_seleccionadas.csv', index=False)
    intervals = []
    for _, winner in winners.iterrows():
        for year in [2021, 2024]:
            new = predictions[(year, winner.approach, winner.variant, winner.weight)]
            ref = predictions[(year, 'agregado', 'PREV_R01_logs_grupos', 'RECENT_LN')]
            pair = new.merge(ref[KEYS + ['Y', 'PRED']], on=KEYS, suffixes=('_NEW', '_OLD'), validate='one_to_one')
            assert np.allclose(pair.Y_NEW, pair.Y_OLD)
            pair['Y'] = pair.Y_NEW
            intervals.append(dict(year=year, approach=winner.approach, variant=winner.variant, weight=winner.weight,
                                  **old.bootstrap(pair, ['EDOCVE'])))
    pd.DataFrame(intervals).to_csv(OUT / '06_bootstrap.csv', index=False)
    # Recompute every municipal score from saved independent prediction artifacts.
    for key, p in predictions.items():
        year, approach, name, weight = key
        path = DATA / ('municipal_' + old.fingerprint(key) + '.parquet')
        p.to_parquet(path, index=False)
        reloaded = pd.read_parquet(path)
        score = base.metrics(reloaded.Y, reloaded.PRED, reloaded.TARGET_D)
        row = result.loc[result.year.eq(year) & result.approach.eq(approach) & result.variant.eq(name) & result.weight.eq(weight)].iloc[0]
        for col in ['mae_pp', 'rmse_pp', 'r2', 'wmae_pp', 'top20']:
            assert np.isclose(score[col], row[col], atol=1e-9)
    info = dict(data_sha256=data_hash, feature_definition=feature_definition,
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                fresh_fits=fresh, reused_fits=reused, unique_fits=len(registry),
                elapsed_seconds=time.time() - started, metrics=len(result), verification='PASSED',
                planned_unique_fits=expected_fits, complete_planned_fits=len({p[4] for p in plan} & set(registry)),
                retained_pilot_fits=len(set(registry) - {p[4] for p in plan}), pruned=pruned,
                completed_before_run=len(completed_before_plan), command_flags=dict(extend=args.extend, focus=args.focus))
    save_json(OUT / 'configuracion.json', info)
    method = '''PRUEBAS MUNICIPALES AISLADAS
Ronda inicial: 60 ajustes únicos nuevos (16 configuraciones x 2 niveles x 2 años menos 4 equivalencias).
Extensión opcional: 40 ajustes adicionales (cinco combinaciones dirigidas, tres controles Ridge,
dos RF que aíslan más árboles y mayor regularización).
Todos los ajustes completos de la ronda inicial se reutilizan.
Con --focus se podan antes de ampliar a 2024 variantes seccionales GB redundantes >25% peores en 2021.
Las variantes representativas de pérdidas/objetivos/pesos permanecen; todos los modelos directos se completan.
Los resultados con un solo año se documentan, pero se excluyen del ranking de dos años.
Cuatro variantes de pesos coinciden al entrenar directamente y reutilizan resultados sin ajuste repetido.
RF, ExtraTrees y HistGradientBoosting; pérdidas cuadrática/absoluta y objetivo tasa/cambio.
Controles Ridge: regresión lineal regularizada, escalado aprendido exclusivamente en entrenamiento.
Se agregan secciones con LN o D previos; también se entrena directamente por municipio.
Pesos de entrenamiento municipal: masa igual por municipio-año, distribuida por LN previa.
En entrenamiento directo los pesos son uniformes: cada municipio es una observación.
Variables adicionales: dispersión/cuantiles de abstención seccional, concentración de LN,
composición urbana/rural, tamaño y evolución municipal, calculadas sobre TODO el año fuente.
M_WEIGHTED_A inicial es aporte observado sum(LN*A observado)/LN total, no tasa condicional.
Secciones sin soporte aportan cero al numerador; este descriptor mezcla cobertura y participación.
M18 separa M_Z_VALID_LN_SHARE y M_Z_OBSERVED_WEIGHTED_A: tasa ponderada sólo sobre LN con A observada.
También añade M_Z_KNOWN_ELECTOR_SHARE=sum(SV+NV)/sum(LN) y cambios recientes de tasa/cobertura.
Entrenamiento 2021: objetivos 2015/2018. Entrenamiento 2024: objetivos 2015/2018/2021.
Sin resultados del objetivo en entradas; invariancia temporal comprobada.
Objetivo abstención NV/(SV+NV); NS separado. Mismos municipios/cohortes que rondas anteriores.
Se reutilizan predicciones anteriores; ninguna configuración anterior se reentrena.
Mezclas con pesos FIJOS .25/.5/.75; evaluación exhaustiva exploratoria, sin ajuste de pesos.
Ranking: MAE medio municipal no ponderado entre 2021/2024; se incluye worst_ratio por estabilidad.
Bootstrap agrupado por entidad, condicionado al candidato; sin corrección por selección múltiple.
Selección y evaluación usan los mismos dos backtests: NO es confirmación independiente futura.
Cobertura nacional parcial (~64% LN2021/~60%2024), filtros retrospectivos heredados.
No se escribe en página, servicios ni pronósticos productivos.
'''
    (OUT / 'RESULTADOS_MUNICIPALES.txt').write_text('\n'.join([method, json.dumps(info, indent=2),
        '\nCONFIGURACIONES\n', json.dumps(configs, ensure_ascii=False, indent=2),
        '\nGANADORES POR ENFOQUE\n', winners.to_string(index=False),
        '\nMÉTRICAS GANADORES\n', selected.to_string(index=False),
        '\nBOOTSTRAP\n', pd.DataFrame(intervals).to_string(index=False),
        '\nRANKING COMPLETO\n', ranking.to_string(index=False),
        '\nTODAS LAS MÉTRICAS\n', result.to_string(index=False),
        '\nREFERENCIAS PREVIAS SIN REENTRENAR\n', references.to_string(index=False),
        '\nVERIFICACIÓN: firmas únicas, disponibilidad temporal y métricas desde archivos: PASSED']), encoding='utf-8')
    print(winners.to_string(index=False), flush=True)
    print(f'DONE: {fresh} new fits, {reused} reused, {len(result)} metrics, {time.time()-started:.1f}s', flush=True)


if __name__ == '__main__':
    main()
