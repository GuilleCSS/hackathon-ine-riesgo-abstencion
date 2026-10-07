"""Build isolated M17 dashboard artifacts; never overwrite the original forecast."""
import importlib.util
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import joblib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('municipal_experiment', ROOT / 'src/18_improve_municipal.py')
exp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp)
base, old = exp.base, exp.old
OUT = ROOT / 'data/processed/rf_dashboard'
REPORT = ROOT / 'reports/rf_dashboard'
KEYS = ['EDOCVE', 'SECCION']


def forecast_frame(histories, extra):
    s, r = [histories[y].set_index(KEYS) for y in [2021, 2024]]
    idx = s.index.intersection(r.index)
    s, r = s.loc[idx], r.loc[idx]
    mask = s.MPIOCVE.eq(r.MPIOCVE) & s.TIPOSEC.eq(r.TIPOSEC)
    mask &= r[['MPIOCVE', 'DEF', 'DEL']].notna().all(axis=1)
    for d in [s, r]:
        mask &= d.PCT_ABSTENCION.notna() & d.QUALITY_NS.le(.10) & d.LN.gt(0)
    s, r = s.loc[mask].reset_index(), r.loc[mask].reset_index()
    mapping = r[KEYS + ['MPIOCVE', 'DEF', 'DEL']]
    assert mapping.notna().all().all()
    a, b = [base.territorial_source(d, mapping, 'seccion') for d in [s, r]]
    f = a.rename(columns={c: 'SAME_' + c for c in a if c not in KEYS}).merge(
        b.rename(columns={c: 'RECENT_' + c for c in b if c not in KEYS}), on=KEYS, validate='one_to_one')
    f['TARGET_YEAR'], f['TIPO_ELECCION'] = 2027, 'intermedia'
    for name, col in [('ABST', 'PCT_ABSTENCION'), ('LOG_LN', 'LOG_LN'), ('AGE', 'EDAD_PROM_LN')]:
        f['DELTA_' + name] = f['RECENT_' + col] - f['SAME_' + col]
    for g in base.AGES + ['M']:
        f['DELTA_PROP_' + g] = f['RECENT_PROP_LN_' + g] - f['SAME_PROP_LN_' + g]
    return old.attach_extra(f, extra, mapping, 2027, 'seccion'), mapping


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    master = pd.read_csv(base.MASTER, low_memory=False)
    data_hash = hashlib.sha256(base.MASTER.read_bytes()).hexdigest()
    config = exp.configurations([], extended=True)['M17_rf_logs_history']
    assert len(config['features']) == 143
    assert not any(c.startswith(('TARGET', 'FULL', 'Y')) for c in config['features'])
    frames, mappings, cache_id = old.make_frames(data_hash)
    train = pd.concat([frames[y]['seccion'][config['features'] + ['Y']] for y in [2015, 2018, 2021, 2024]], ignore_index=True)
    train_rows = len(train)
    model_path = OUT / 'model_m17_2027.joblib'
    model_manifest = OUT / 'model_manifest.json'
    signature = old.fingerprint({'data': data_hash, 'cache': cache_id, 'config': config, 'train': [2015, 2018, 2021, 2024]})
    if model_path.exists() and model_manifest.exists() and json.loads(model_manifest.read_text())['signature'] == signature:
        model = joblib.load(model_path)
        print('Reusing final M17 model', flush=True)
    else:
        model = exp.model_for(config, 'seccion')
        print(f'Fitting final M17 on {len(train):,} historical section-election records', flush=True)
        model.fit(train[config['features']], train.Y)
        joblib.dump(model, model_path)
        model_manifest.write_text(json.dumps({'signature': signature, 'features': config['features'], 'train_years': [2015, 2018, 2021, 2024]}, indent=2))
    del train
    future, future_mapping = forecast_frame(base.prepare_history(master), old.extra_source(master))
    future['PRED'] = model.predict(future[config['features']]).clip(0, 1)
    future[KEYS + ['PRED']].to_parquet(OUT / 'sections_2027.parquet', index=False)
    future = future[KEYS + ['RECENT_LN', 'RECENT_D', 'RECENT_NS', 'PRED']].copy()
    for year in frames:
        for level in frames[year]:
            cols = KEYS + ['RECENT_LN', 'RECENT_D', 'RECENT_NS'] if level == 'seccion' else base.LEVELS[level] + ['Y', 'TARGET_D', 'TARGET_LN']
            frames[year][level] = frames[year][level][cols].copy()
    registry = json.loads((exp.OUT / 'registro_pruebas.json').read_text())
    geometry = gpd.read_file(ROOT / 'data/processed/spatial_2027/risk_2027_dashboard_simplified.geojson', columns=['SECTION_KEY'], engine='pyogrio')
    geometry['EDOCVE'] = geometry.SECTION_KEY.str.split('-').str[0].astype(int)
    geometry['SECCION'] = geometry.SECTION_KEY.str.split('-').str[1].astype(int)
    geometry = geometry[KEYS + ['geometry']]
    assert not geometry.duplicated(KEYS).any()
    rows, metrics, coverage = [], [], []
    for year in [2021, 2024, 2027]:
        if year == 2027:
            f, mapping, source_year = future, future_mapping, 2024
        else:
            f, mapping, source_year = frames[year]['seccion'].copy(), mappings[year], year - 3
            matches = [(k, v) for k, v in registry.items() if v['year'] == year and v['level'] == 'seccion' and v['variant'] == 'M17_rf_logs_history']
            assert len(matches) == 1
            p = pd.read_parquet(exp.DATA / f'prediction_{matches[0][0]}.parquet')
            f = f.merge(p[KEYS + ['PRED']], on=KEYS, validate='one_to_one')
        cohort = f[KEYS + ['RECENT_LN', 'RECENT_D', 'RECENT_NS', 'PRED']].merge(mapping, on=KEYS, validate='one_to_one')
        cohort['WP'] = cohort.PRED * cohort.RECENT_LN
        source = master.loc[master.AELEC.eq(source_year)].copy()
        for level, keys in base.LEVELS.items():
            d = cohort.groupby(keys).agg(WP=('WP', 'sum'), LN_BASE=('RECENT_LN', 'sum'), D_BASE=('RECENT_D', 'sum'), NS_BASE=('RECENT_NS', 'sum'), N_SECTIONS=('SECCION', 'size')).reset_index()
            d['PRED'] = d.WP / d.LN_BASE
            full = source.groupby(keys).LN.sum().rename('FULL_LN_BASE').reset_index()
            d = d.merge(full, on=keys, validate='one_to_one')
            d['COVERAGE'] = d.LN_BASE / d.FULL_LN_BASE
            names = source.groupby(keys).EDONOM.first().rename('STATE_NAME').reset_index()
            d = d.merge(names, on=keys, validate='one_to_one')
            if level == 'municipio':
                d = d.merge(source.groupby(keys).MPIONOM.first().rename('NAME').reset_index(), on=keys, validate='one_to_one')
            elif level == 'entidad':
                d['NAME'] = d.STATE_NAME
            else:
                d['NAME'] = ('Distrito federal ' if level == 'distrito_federal' else 'Distrito local ') + d[keys[-1]].astype(int).astype(str)
            d['ID'] = level + ':' + d[keys].astype(int).astype(str).agg(':'.join, axis=1)
            d['YEAR'], d['LEVEL'], d['BASE_YEAR'] = year, level, source_year
            d['EST_NV'] = d.PRED * d.D_BASE
            d['EST_SV'] = (1 - d.PRED) * d.D_BASE
            if year != 2027:
                actual = frames[year][level][keys + ['Y', 'TARGET_D', 'TARGET_LN']]
                d = d.merge(actual, on=keys, validate='one_to_one')
                metrics.append({'year': year, 'level': level, **base.metrics(d.Y, d.PRED, d.TARGET_D)})
            mapped = geometry.merge(source[KEYS + [k for k in keys if k not in KEYS]], on=KEYS, validate='one_to_one')
            mapped = mapped.dropna(subset=keys)
            mapped['ID'] = level + ':' + mapped[keys].astype(int).astype(str).agg(':'.join, axis=1)
            path = OUT / f'boundaries_{year}_{level}.geojson'
            if not path.exists():
                print(f'Building boundaries {year} {level}', flush=True)
                boundaries = mapped[['ID', 'geometry']].dissolve(by='ID').reset_index()
                boundaries.geometry = boundaries.geometry.make_valid().simplify(.003, preserve_topology=True).make_valid().set_precision(.0000001)
                boundaries.to_file(path, driver='GeoJSON', engine='pyogrio')
            mapped_cohort = cohort.merge(geometry[KEYS], on=KEYS, validate='one_to_one')
            map_ln = mapped_cohort.groupby(keys).RECENT_LN.sum().rename('MAPPED_LN').reset_index()
            d = d.merge(map_ln, on=keys, how='left', validate='one_to_one')
            d['MAP_COVERAGE'] = d.MAPPED_LN.fillna(0) / d.LN_BASE
            coverage.append({'year': year, 'level': level, 'territories': len(d), 'sections': len(cohort), 'ln_share_source': d.LN_BASE.sum()/source.LN.sum(), 'mapped_ln_share': d.MAPPED_LN.sum()/d.LN_BASE.sum()})
            rows.append(d.drop(columns=['WP']))
        print(f'Prepared {year}: {len(cohort):,} sections', flush=True)
    table = pd.concat(rows, ignore_index=True)
    for year in [2021, 2024, 2027]:
        totals = table.loc[table.YEAR.eq(year)].groupby('LEVEL').LN_BASE.sum()
        assert np.allclose(totals, totals.iloc[0]), 'Territorial levels must cover the same cohort'
    thresholds = {}
    for level in base.LEVELS:
        values = table.loc[table.YEAR.eq(2027) & table.LEVEL.eq(level), 'PRED']
        thresholds[level] = [float(values.quantile(.5)), float(values.quantile(.8))]
        mask = table.LEVEL.eq(level)
        lo, hi = thresholds[level]
        table.loc[mask, 'RISK'] = np.select([table.loc[mask, 'PRED'].le(lo), table.loc[mask, 'PRED'].le(hi)], ['BAJO', 'MEDIO'], default='ALTO')
    assert table.PRED.between(0, 1).all() and table.COVERAGE.between(0, 1.000001).all()
    assert np.allclose(table.EST_NV + table.EST_SV, table.D_BASE)
    table.to_parquet(OUT / 'territories.parquet', index=False)
    table.to_csv(OUT / 'territories.csv', index=False)
    pd.DataFrame(metrics).to_csv(REPORT / 'metricas_multinivel.csv', index=False)
    pd.DataFrame(coverage).to_csv(REPORT / 'cobertura.csv', index=False)
    metadata = {'model': 'M17_rf_logs_history', 'approach': 'section_predictions_weighted_RECENT_LN', 'data_sha256': data_hash, 'signature': signature, 'features': config['features'], 'thresholds': thresholds, 'geometry': 'MGS DIC-2025 provisional; source-year section assignment; partial geometry', 'checks': 'PASSED: unique joins, 143 source-only features, bounded rates/coverage, conserved assumed counts', 'train_rows': train_rows, 'forecast_sections': len(future)}
    (OUT / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(metadata['checks'], flush=True)


def verify_ui():
    from streamlit.testing.v1 import AppTest
    import sys
    sys.path.insert(0, str(ROOT / 'dashboard'))
    from rf_dashboard import selected_id
    assert selected_id({'selection': {'objects': {'rf_territories': [{'properties': {'ID': 'municipio:1:1'}}]}}}) == 'municipio:1:1'
    assert selected_id({'selection': {'objects': {}}}) is None
    table = pd.read_parquet(OUT / 'territories.parquet')
    assert not table.duplicated(['YEAR', 'LEVEL', 'ID']).any()
    assert np.allclose(table.EST_SV + table.EST_NV, table.D_BASE)
    for year in [2021, 2024, 2027]:
        d = table.loc[table.YEAR.eq(year)]
        mass = d.groupby('LEVEL').LN_BASE.sum()
        assert np.allclose(mass, mass.iloc[0])
        for level in base.LEVELS:
            boundaries = gpd.read_file(OUT / f'boundaries_{year}_{level}.geojson', engine='pyogrio')
            assert boundaries.ID.is_unique and boundaries.crs.to_epsg() == 4326
            assert boundaries.geometry.is_valid.all()
            assert set(d.loc[d.LEVEL.eq(level) & d.MAP_COVERAGE.gt(0), 'ID']).issubset(set(boundaries.ID))
    app = AppTest.from_file(str(ROOT / 'dashboard/app.py'), default_timeout=180).run()
    assert not app.exception, app.exception
    assert app.sidebar.selectbox(key='predictive_model').value.startswith('Modelo actual')
    app.sidebar.selectbox(key='predictive_model').select('Random Forest M17 · multinivel').run()
    assert not app.exception, app.exception
    app.sidebar.selectbox(key='rf_state').select(1).run()
    assert not app.exception, app.exception
    for level in base.LEVELS:
        app.sidebar.selectbox(key='rf_level').select(level).run()
        assert not app.exception, app.exception
        for year in [2021, 2024, 2027]:
            app.sidebar.selectbox(key='rf_year').select(year).run()
            assert not app.exception, app.exception
        def displayed_abstention():
            return float(next(m.value for m in app.metric if m.label == 'Abstención estimada ponderada').rstrip('%'))
        baseline_rate = displayed_abstention()
        app.sidebar.selectbox(key='rf_scenario').select('Intervención hipotética: −2 pp en riesgo alto').run()
        assert not app.exception, app.exception
        two_rate = displayed_abstention()
        app.sidebar.selectbox(key='rf_scenario').select('Intervención hipotética: −5 pp en riesgo alto').run()
        assert not app.exception, app.exception
        assert displayed_abstention() <= two_rate <= baseline_rate
        app.sidebar.selectbox(key='rf_scenario').select('Sin intervención').run()
        assert displayed_abstention() == baseline_rate
        assert app.sidebar.selectbox(key='rf_state').value == 1
        assert not app.exception, app.exception
        territory_key = f'rf_territory_2027_{level}_1'
        territory = table.loc[table.YEAR.eq(2027) & table.LEVEL.eq(level) & table.EDOCVE.eq(1), 'ID'].iloc[0]
        app.sidebar.selectbox(key=territory_key).select(territory).run()
        assert not app.exception, app.exception
        assert any('Semáforo' == m.label for m in app.metric)
        app.sidebar.selectbox(key='rf_scenario').select('Intervención hipotética: −2 pp en riesgo alto').run()
        assert not app.exception, app.exception
        app.sidebar.selectbox(key='rf_scenario').select('Sin intervención').run()
        print('PASSED UI level', level, flush=True)
    app.sidebar.multiselect(key='rf_risks').set_value([]).run()
    assert not app.exception and any('No hay territorios' in w.value for w in app.warning)
    app.sidebar.selectbox(key='predictive_model').select('Modelo actual · dos historias lineales').run()
    assert not app.exception, app.exception
    report = 'PASSED: original default and return; 12 year/level views; four state/territory detail selections; scenarios; empty risk filter; GeoJSON click extraction; unique rows and count conservation.\n'
    (REPORT / 'VERIFICACION_UI.txt').write_text(report, encoding='utf-8')
    model = joblib.load(OUT / 'model_m17_2027.joblib')
    details = json.loads((OUT / 'metadata.json').read_text())
    details['parameters'] = model.named_steps['model'].get_params()
    details['geometry_checks'] = 'All 12 exported layers: valid geometry, unique IDs, EPSG:4326, mapped territories present'
    text_report = ('IMPLEMENTACION RANDOM FOREST M17\n\n' + report + '\nCONFIGURACION\n' +
                   json.dumps(details, ensure_ascii=False, indent=2) + '\n\nMETRICAS FUERA DE MUESTRA\n' +
                   (REPORT / 'metricas_multinivel.csv').read_text() + '\nCOBERTURA\n' +
                   (REPORT / 'cobertura.csv').read_text() + '\nMETODOLOGIA Y LIMITACIONES\n' +
                   (REPORT / 'IMPLEMENTACION.md').read_text())
    (REPORT / 'RESULTADOS_IMPLEMENTACION.txt').write_text(text_report, encoding='utf-8')
    print(report, flush=True)


def repair_geometry():
    """Repair export-rounding artifacts only in this model's new layers."""
    for path in sorted(OUT.glob('boundaries_*.geojson')):
        if path.name.endswith('.repair.geojson'):
            continue
        geo = gpd.read_file(path, engine='pyogrio')
        invalid = ~geo.geometry.is_valid
        bad = int(invalid.sum())
        if bad:
            geo.loc[invalid, 'geometry'] = geo.loc[invalid, 'geometry'].make_valid().set_precision(.0000001)
            temporary = path.with_name(path.stem + '.repair.geojson')
            geo.to_file(temporary, driver='GeoJSON', engine='pyogrio')
            check = gpd.read_file(temporary, engine='pyogrio')
            assert check.geometry.is_valid.all() and check.ID.is_unique
            temporary.replace(path)
        print(path.name, 'repaired', bad, flush=True)


if __name__ == '__main__':
    import sys
    if '--optimize-dashboard' in sys.argv or '--verify-dashboard-performance' in sys.argv:
        optimizer_spec = importlib.util.spec_from_file_location('optimize_maps', ROOT / 'src/20_optimize_dashboard_maps.py')
        optimizer = importlib.util.module_from_spec(optimizer_spec)
        optimizer_spec.loader.exec_module(optimizer)
        optimizer.verify() if '--verify-dashboard-performance' in sys.argv else optimizer.main()
    elif '--status' in sys.argv:
        import os
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                args = (proc / 'cmdline').read_bytes().split(b'\0')
                if int(proc.name) != os.getpid() and args[:2] == [b'python', b'src/19_publish_rf_dashboard.py']:
                    status = (proc / 'status').read_text().splitlines()
                    fields = (proc / 'stat').read_text().split()
                    elapsed = float(Path('/proc/uptime').read_text().split()[0]) - float(fields[21]) / os.sysconf('SC_CLK_TCK')
                    print('PID', proc.name, 'elapsed_seconds', round(elapsed), [line for line in status if line.startswith(('State:', 'VmRSS:'))], flush=True)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass
    elif '--stop-build' in sys.argv:
        import os, signal
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                args = (proc / 'cmdline').read_bytes().split(b'\0')
                if int(proc.name) != os.getpid() and args[:2] == [b'python', b'src/19_publish_rf_dashboard.py'] and b'--stop-build' not in args:
                    os.kill(int(proc.name), signal.SIGTERM)
                    print('Stopped artifact build PID', proc.name)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass
    elif '--repair-geometry' in sys.argv:
        repair_geometry()
    elif '--verify-ui' in sys.argv:
        verify_ui()
    else:
        main()
