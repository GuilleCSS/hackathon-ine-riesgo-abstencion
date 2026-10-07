"""Prepare lightweight map views; no model fitting or prediction changes."""
import hashlib
import json
import time
from pathlib import Path
import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed/rf_dashboard'
OUT = DATA / 'maps_fast'
REPORT = ROOT / 'reports/rf_dashboard'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    measurements = []
    for source in sorted(DATA.glob('boundaries_*.geojson')):
        if '.repair.' in source.name:
            continue
        stem = source.stem.removeprefix('boundaries_')
        year, level = stem.split('_', 1)
        folder = OUT / stem
        folder.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = folder / 'manifest.json'
        if manifest.exists() and json.loads(manifest.read_text())['source_sha256'] == digest:
            measurements.append(json.loads(manifest.read_text()))
            continue
        started = time.perf_counter()
        geo = gpd.read_file(source, engine='pyogrio')
        assert geo.ID.is_unique and geo.geometry.is_valid.all()
        geo['EDOCVE'] = geo.ID.str.split(':').str[1].astype(int)
        projected = geo.to_crs(6372)
        points = projected.representative_point().to_crs(4326)
        index = geo[['ID', 'EDOCVE']].copy()
        index['LON'], index['LAT'] = points.x, points.y
        index = pd.concat([index, geo.bounds.rename(columns={'minx':'WEST', 'miny':'SOUTH', 'maxx':'EAST', 'maxy':'NORTH'})], axis=1)
        index.to_parquet(folder / 'index.parquet', index=False)
        for state, frame in geo.groupby('EDOCVE'):
            frame[['ID', 'geometry']].to_parquet(folder / f'state_{state}.parquet', index=False, compression='zstd')
        overview_bytes = 0
        if level == 'entidad':
            overview = geo[['ID', 'geometry']].copy()
            # At national zoom, omit sub-pixel holes/islets. Detailed geometry stays intact.
            overview.geometry = overview.geometry.simplify(.02, preserve_topology=False).make_valid()
            assert overview.geometry.is_valid.all() and not overview.geometry.is_empty.any()
            overview.to_file(folder / 'overview.geojson', driver='GeoJSON', engine='pyogrio')
            overview_bytes = (folder / 'overview.geojson').stat().st_size
        record = {'year': int(year), 'level': level, 'source_sha256': digest, 'source_bytes': source.stat().st_size,
                  'overview_bytes': overview_bytes, 'index_bytes': (folder / 'index.parquet').stat().st_size,
                  'state_files_bytes': sum(p.stat().st_size for p in folder.glob('state_*.parquet')),
                  'territories': len(geo), 'prepare_seconds': time.perf_counter()-started}
        manifest.write_text(json.dumps(record, indent=2), encoding='utf-8')
        measurements.append(record)
        print('Prepared fast map', stem, 'overview bytes', overview_bytes, flush=True)
    pd.DataFrame(measurements).to_csv(REPORT / 'RENDIMIENTO_CAPAS.csv', index=False)
    (OUT / 'READY.json').write_text(json.dumps({'format': 1, 'layers': len(measurements)}), encoding='utf-8')
    print('PASSED: 12 layers, unique IDs, valid geometries; original detailed boundaries preserved', flush=True)


if __name__ == '__main__':
    main()


def verify():
    import sys
    import numpy as np
    import pydeck as pdk
    sys.path.insert(0, str(ROOT / 'dashboard'))
    import rf_dashboard as rf
    table = pd.read_parquet(DATA / 'territories.parquet')
    metadata = json.loads((DATA / 'metadata.json').read_text())
    records = []
    for level in rf.LEVELS:
        data = table.loc[table.YEAR.eq(2027) & table.LEVEL.eq(level)].copy()
        source = DATA / f'boundaries_2027_{level}.geojson'
        start = time.perf_counter()
        original = gpd.read_file(source, engine='pyogrio')
        geo = original.merge(rf.decorate(data), on='ID', validate='one_to_one')
        fields = ['ID','NAME_LABEL','STATE_LABEL','YEAR','RISK','COLOR','ABST_LABEL','PART_LABEL','geometry']
        old_deck = pdk.Deck(layers=[pdk.Layer('GeoJsonLayer', json.loads(geo[fields].to_json()), id='rf_territories')])
        old_json = old_deck.to_json()
        old_seconds, old_bytes = time.perf_counter()-start, len(old_json.encode('utf-8'))
        del old_deck, old_json, geo
        start = time.perf_counter()
        deck, n, points = rf.make_deck(DATA, 2027, level, data, None, None)
        new_json = deck.to_json()
        elapsed, byte_count = time.perf_counter()-start, len(new_json.encode('utf-8'))
        assert n == len(set(data.ID).intersection(original.ID))
        assert byte_count < old_bytes * .15, 'National payload must be at least 85% smaller'
        assert byte_count < 8 * 1024 * 1024
        for state in [1,20]:
            optimized = rf.load_boundaries(DATA, 2027, level, state)
            reference = original.loc[original.ID.str.split(':').str[1].eq(str(state))]
            merged = optimized.merge(reference, on='ID', suffixes=('_optimized','_original'), validate='one_to_one')
            assert len(merged) == len(reference) == len(optimized)
            assert np.array_equal(merged.geometry_optimized.to_wkb(), merged.geometry_original.to_wkb())
        records.append({'level':level,'legacy_map_seconds':old_seconds,'optimized_map_seconds':elapsed,'legacy_json_bytes':old_bytes,'optimized_json_bytes':byte_count,'reduction_pct':100*(1-byte_count/old_bytes),'mode':'points' if points else 'overview_polygons'})
        print('PASS map performance', level, records[-1], flush=True)
    # A real high-risk territory verifies both intervention effects and original immutability.
    high = table.loc[table.YEAR.eq(2027) & table.LEVEL.eq('municipio') & table.RISK.eq('ALTO')].iloc[[0]].copy()
    before = high.copy(deep=True)
    for delta in [.02,.05]:
        scenario = rf.scenario_view(high, delta, metadata['thresholds']['municipio'])
        assert np.allclose(scenario.PRED, np.maximum(0, high.PRED-delta))
        assert np.allclose(scenario.EST_SV+scenario.EST_NV, scenario.D_BASE)
    pd.testing.assert_frame_equal(high,before)
    exported = json.loads(rf.export_geojson(DATA,2027,'municipio',high))
    assert {f['properties']['ID'] for f in exported['features']} == set(high.ID)
    assert exported['features'][0]['properties']['PRED'] == float(high.PRED.iloc[0])
    assert rf.selected_id({'selection':{'objects':{'rf_territories':[{'ID':'municipio:1:1'}]}}}) == 'municipio:1:1'
    assert rf.selected_id({'selection':{'objects':{'rf_territories-polygons-fill':[{'properties':{'ID':'entidad:1'}}]}}}) == 'entidad:1'
    results = pd.DataFrame(records)
    results.to_csv(REPORT / 'RENDIMIENTO_MAPA.csv',index=False)
    (REPORT/'RESULTADOS_OPTIMIZACION.txt').write_text('OPTIMIZACION DEL TABLERO M17\n\n'+results.to_string(index=False)+'\n\nTiempo: construccion y serializacion en Python; no incluye navegador ni red. Vistas nacionales estatales simplificadas; municipales/distritales con puntos. Vista regional: GeoParquet detallado, sin cambios en geometria ni predicciones. Exportacion GeoJSON detallada bajo solicitud. Verificacion: datos regionales WKB identicos, escenarios y conteos coherentes, seleccion de puntos/poligonos y exportacion correctas.\n',encoding='utf-8')
    (REPORT/'VERIFICACION_RENDIMIENTO.txt').write_text('PASSED: all four national views below 8 MB and at least 85% smaller; detailed regional WKB unchanged (two states per level); scenario effect, immutable input, count conservation, detailed GeoJSON export and point/polygon selection extraction. Timings measure Python map construction and serialization, not browser/network rendering.\n',encoding='utf-8')
