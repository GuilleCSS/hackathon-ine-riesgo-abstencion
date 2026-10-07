"""M17 map explorer: light national overview, detailed regional maps on demand."""
import hashlib
import json
import html
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import streamlit as st

LEVELS = {'entidad': 'Estatal', 'municipio': 'Municipal', 'distrito_federal': 'Distrito federal', 'distrito_local': 'Distrito local'}
COLORS = {'BAJO': [46, 125, 50, 190], 'MEDIO': [251, 192, 45, 200], 'ALTO': [198, 40, 40, 210]}
SCENARIOS = ['Sin intervención', 'Intervención hipotética: −2 pp en riesgo alto', 'Intervención hipotética: −5 pp en riesgo alto']


def revision(path):
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


@st.cache_data(show_spinner=False)
def load_tables(folder, stamp):
    return pd.read_parquet(folder / 'territories.parquet'), json.loads((folder / 'metadata.json').read_text())


@st.cache_data(show_spinner=False)
def read_geo(path, stamp):
    return gpd.read_parquet(path) if path.suffix == '.parquet' else gpd.read_file(path, engine='pyogrio')


@st.cache_data(show_spinner=False)
def read_index(path, stamp):
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def pack_valid(source, stamp, manifest, manifest_stamp):
    info = json.loads(manifest.read_text())
    return hashlib.sha256(source.read_bytes()).hexdigest() == info['source_sha256']


def map_pack(folder, year, level):
    pack = folder / 'maps_fast' / f'{year}_{level}'
    source = folder / f'boundaries_{year}_{level}.geojson'
    manifest = pack / 'manifest.json'
    if manifest.exists() and (pack / 'index.parquet').exists() and pack_valid(source, revision(source), manifest, revision(manifest)):
        return pack
    return None


def load_boundaries(folder, year, level, state=None, overview=False):
    pack = map_pack(folder, year, level)
    if pack and overview and level == 'entidad':
        path = pack / 'overview.geojson'
        return read_geo(path, revision(path))
    if pack and state is not None:
        path = pack / f'state_{int(state)}.parquet'
        if path.exists():
            return read_geo(path, revision(path))
        return gpd.GeoDataFrame({'ID': []}, geometry=[], crs=4326)
    path = folder / f'boundaries_{year}_{level}.geojson'
    frame = read_geo(path, revision(path))
    if state is not None:
        frame = frame.loc[frame.ID.str.split(':').str[1].eq(str(int(state)))]
    return frame


def selected_id(event):
    if not event:
        return None
    layers = event.get('selection', {}).get('objects', {})
    objects = layers.get('rf_territories', [])
    if not objects:
        objects = [obj for layer, picked in layers.items() if layer.startswith('rf_territories') for obj in picked]
    return objects[0].get('properties', objects[0]).get('ID') if objects else None


def scenario_view(data, delta, thresholds):
    data = data.copy()
    data['BASE_PRED'] = data.PRED
    data['PRED'] = (data.PRED - delta * data.RISK.eq('ALTO')).clip(0, 1)
    lo, hi = thresholds
    data['RISK'] = np.select([data.PRED.le(lo), data.PRED.le(hi)], ['BAJO', 'MEDIO'], default='ALTO')
    data['EST_NV'] = data.PRED * data.D_BASE
    data['EST_SV'] = (1 - data.PRED) * data.D_BASE
    return data


def decorate(data):
    data = data.copy()
    data['COLOR'] = data.RISK.map(COLORS)
    data['ABST_LABEL'] = data.PRED.mul(100).round(2).astype(str)
    data['PART_LABEL'] = (1 - data.PRED).mul(100).round(2).astype(str)
    data['NAME_LABEL'] = data.NAME.map(lambda x: html.escape(str(x)))
    data['STATE_LABEL'] = data.STATE_NAME.map(lambda x: html.escape(str(x)))
    return data


def make_deck(folder, year, level, data, state, territory):
    """Only display fields travel to the browser; no full national municipal polygons."""
    pack = map_pack(folder, year, level)
    local_state = state
    if territory is not None:
        local_state = int(data.EDOCVE.iloc[0])
    points = level != 'entidad' and local_state is None
    display = decorate(data)
    fields = ['ID', 'NAME_LABEL', 'STATE_LABEL', 'YEAR', 'RISK', 'COLOR', 'ABST_LABEL', 'PART_LABEL']
    if points:
        if pack:
            path = pack / 'index.parquet'
            positions = read_index(path, revision(path))
        else:
            frame = load_boundaries(folder, year, level)
            coords = frame.to_crs(6372).representative_point().to_crs(4326)
            positions = frame[['ID']].copy()
            positions['LON'], positions['LAT'] = coords.x, coords.y
        mapped = display.merge(positions[['ID','LON','LAT']], on='ID', validate='one_to_one')
        mapped = mapped.loc[np.isfinite(mapped.LON) & np.isfinite(mapped.LAT)]
        if mapped.empty:
            return None, 0, points
        records = mapped[fields + ['LON','LAT']].to_dict('records')
        layer = pdk.Layer('ScatterplotLayer', records, id='rf_territories', get_position='[LON, LAT]', get_fill_color='COLOR', radius_min_pixels=3, radius_max_pixels=7, get_radius=1500, pickable=True, auto_highlight=True)
        bounds = [mapped.LON.min(), mapped.LAT.min(), mapped.LON.max(), mapped.LAT.max()]
    else:
        geo = load_boundaries(folder, year, level, local_state, overview=local_state is None)
        mapped = geo.merge(display, on='ID', validate='one_to_one')
        mapped = mapped.loc[mapped.geometry.notna() & ~mapped.geometry.is_empty]
        if mapped.empty:
            return None, 0, points
        payload = json.loads(mapped[fields + ['geometry']].to_json())
        layer = pdk.Layer('GeoJsonLayer', payload, id='rf_territories', pickable=True, auto_highlight=True, filled=True, stroked=True, get_fill_color='properties.COLOR', get_line_color=[255,255,255,210], line_width_min_pixels=1)
        bounds = mapped.total_bounds
    west, south, east, north = bounds
    span = max(east-west, north-south, .01)
    deck = pdk.Deck(layers=[layer], initial_view_state=pdk.ViewState(latitude=(south+north)/2, longitude=(west+east)/2, zoom=float(np.clip(np.log2(360/span)-1, 3, 12))), map_style='light', tooltip={'html': '<b>{NAME_LABEL}</b><br/>{STATE_LABEL} · {YEAR}<br/>Abstención: {ABST_LABEL}%<br/>Participación: {PART_LABEL}%<br/>Riesgo: {RISK}'})
    return deck, len(mapped), points


def export_geojson(folder, year, level, data):
    frames = [load_boundaries(folder, year, level, int(state)) for state in sorted(data.EDOCVE.unique())]
    geo = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry='geometry', crs=4326)
    geo = geo.merge(data, on='ID', validate='one_to_one')
    return geo.to_json().encode('utf-8')


def detail_panel(row, year):
    st.subheader(str(row.NAME))
    st.caption(f'{row.STATE_NAME} · {year}')
    a, b = st.columns(2)
    a.metric('Abstención', f'{row.PRED*100:.1f}%', help='Tasa estimada de abstención entre personas con estado de votación conocido.')
    b.metric('Participación', f'{(1-row.PRED)*100:.1f}%', help='Tasa estimada de participación, complementaria a la abstención.')
    st.metric('Semáforo', row.RISK)
    st.caption(f'Cobertura electoral: {row.COVERAGE*100:.1f}% · cobertura cartográfica: {row.MAP_COVERAGE*100:.1f}%')
    st.markdown(f'**Base electoral: {int(row.BASE_YEAR)}**')
    st.metric('Lista nominal modelada', f'{row.LN_BASE:,.0f}')
    st.write(f'Votarían: **{row.EST_SV:,.0f}** · No votarían: **{row.EST_NV:,.0f}**')
    st.caption('Conteos orientativos con denominador histórico; no son votos observados futuros.')
    with st.expander('Más datos del territorio'):
        details = {'Año electoral': year, 'Año de base electoral': int(row.BASE_YEAR), 'Lista nominal histórica total': f'{row.FULL_LN_BASE:,.0f}', 'Estado de votación conocido en la base': f'{row.D_BASE:,.0f}', 'Estado de votación desconocido en la base': f'{row.NS_BASE:,.0f}', 'Secciones modeladas': int(row.N_SECTIONS)}
        if year != 2027:
            details.update({'Abstención observada': f'{row.Y*100:.2f}%', 'Participación observada': f'{(1-row.Y)*100:.2f}%', 'Lista nominal observada en prueba': f'{row.TARGET_LN:,.0f}', 'Votaron en la cohorte de prueba': f'{(1-row.Y)*row.TARGET_D:,.0f}', 'No votaron en la cohorte de prueba': f'{row.Y*row.TARGET_D:,.0f}'})
        st.table(pd.DataFrame([(key, str(value)) for key, value in details.items()], columns=['Dato','Valor']))


def render(root):
    folder = root / 'data/processed/rf_dashboard'
    st.title('Explora el riesgo de abstención')
    st.caption('Random Forest M17 · elige un periodo, explora el territorio y consulta sus cifras')
    if not (folder / 'metadata.json').exists():
        st.info('El modelo se está preparando. Actualiza la página cuando termine la generación.')
        return
    try:
        table, metadata = load_tables(folder, (revision(folder/'territories.parquet'), revision(folder/'metadata.json')))
    except (OSError, ValueError) as exc:
        st.error(f'No se pudieron cargar las predicciones. Intenta actualizar la página. Detalle: {exc}')
        return
    with st.sidebar:
        st.header('Periodo y territorio')
        year = st.selectbox('Año', [2027, 2024, 2021], format_func=lambda y: f'{y} · ' + ('Pronóstico' if y == 2027 else 'Prueba histórica'), key='rf_year')
        level = st.selectbox('Nivel territorial', list(LEVELS), format_func=LEVELS.get, key='rf_level')
        data = table.loc[table.YEAR.eq(year) & table.LEVEL.eq(level)].copy()
        states = dict(table.loc[table.YEAR.eq(2027) & table.LEVEL.eq('entidad'), ['EDOCVE','STATE_NAME']].sort_values('STATE_NAME').itertuples(index=False, name=None))
        state = st.selectbox('Entidad', [None]+list(states), format_func=lambda x: 'Todo México' if x is None else states[x], key='rf_state')
        if state is not None:
            data = data.loc[data.EDOCVE.eq(state)]
        labels = dict(zip(data.ID, data.NAME + ' · ' + data.STATE_NAME))
        territory = st.selectbox('Buscar un territorio', [None]+list(labels), format_func=lambda x: 'Todos los territorios' if x is None else labels[x], key=f'rf_territory_{year}_{level}_{state}', help='Escribe su nombre para buscar. También puedes seleccionarlo en el mapa.')
        with st.expander('Comparar escenarios', expanded=True):
            scenario = st.selectbox('Escenario', SCENARIOS, key='rf_scenario', help='La reducción se aplica únicamente a territorios de riesgo alto en el escenario base.')
        with st.expander('Filtrar por riesgo'):
            risks = st.multiselect('Semáforo', ['BAJO','MEDIO','ALTO'], default=['BAJO','MEDIO','ALTO'], key='rf_risks')
    if territory is not None:
        data = data.loc[data.ID.eq(territory)]
    lo, hi = metadata['thresholds'][level]
    delta = 0 if scenario == SCENARIOS[0] else (.02 if scenario == SCENARIOS[1] else .05)
    data = scenario_view(data, delta, (lo, hi))
    data = data.loc[data.RISK.isin(risks)]
    scope = states[state] if state is not None else 'México'
    st.subheader(f'{scope} · {LEVELS[level]} · {year}')
    if year != 2027:
        st.caption('Prueba histórica: el modelo no entrenó con los resultados de este año.')
    if delta:
        st.info(f'Escenario hipotético: −{delta*100:.0f} puntos porcentuales en territorios de riesgo alto. No representa un efecto causal demostrado.')
    if data.empty:
        st.warning('No hay territorios con estos filtros. Selecciona otro riesgo o territorio.')
        return
    a,b,c,d = st.columns(4)
    a.metric('Territorios', f'{len(data):,}')
    mean = np.average(data.PRED, weights=data.LN_BASE)
    b.metric('Abstención estimada ponderada', f'{mean*100:.1f}%', delta=f'{(mean-np.average(data.BASE_PRED,weights=data.LN_BASE))*100:.1f} pp vs. base' if delta else None, delta_color='inverse', help='Promedio ponderado por lista nominal histórica de las secciones modeladas.')
    c.metric('Participación estimada ponderada', f'{(1-mean)*100:.1f}%')
    d.metric('Territorios de riesgo alto', str(data.RISK.eq('ALTO').sum()))
    st.caption(f'Cobertura electoral: {data.LN_BASE.sum()/data.FULL_LN_BASE.sum()*100:.1f}% · cobertura cartográfica de lo modelado: {(data.LN_BASE*data.MAP_COVERAGE).sum()/data.LN_BASE.sum()*100:.1f}%. Información agregada; cobertura parcial.')
    st.markdown(f'🟢 **Bajo** ≤ {lo*100:.1f}%　 🟡 **Medio** ≤ {hi*100:.1f}%　 🔴 **Alto** > {hi*100:.1f}%')
    st.caption('Cortes fijos de 2027 para este nivel. Filtrar o cambiar de escenario no recalcula los umbrales.')
    boundary_path = folder / f'boundaries_{year}_{level}.geojson'
    geometry_stamp = revision(boundary_path) if boundary_path.exists() else None
    view_key = hashlib.sha256(f'{year}|{level}|{state}|{territory}|{scenario}|{sorted(risks)}|{revision(folder/"territories.parquet")}|{revision(folder/"metadata.json")}|{geometry_stamp}'.encode()).hexdigest()[:16]
    map_column, detail_column = st.columns([2.3,1], gap='large')
    event = None
    with map_column:
        st.subheader('Mapa territorial')
        try:
            with st.spinner('Cargando mapa…'):
                deck, mapped_n, points = make_deck(folder, year, level, data, state, territory)
            if deck is None:
                st.warning('Hay predicciones, pero no hay geometría disponible para esta selección.')
            else:
                if points:
                    st.caption('Vista nacional: un punto por territorio. Selecciona una entidad o busca un territorio para ver sus polígonos.')
                elif state is None and territory is None:
                    st.caption('Vista nacional simplificada. Selecciona una entidad para consultar su geometría detallada.')
                else:
                    st.caption('Polígonos de la selección. Haz clic para consultar el detalle.')
                event = st.pydeck_chart(deck, key=f'rf_map_{view_key}', on_select='rerun', selection_mode='single-object', width='stretch', height=510)
                if mapped_n < len(data):
                    st.caption(f'{mapped_n:,} de {len(data):,} territorios tienen representación cartográfica. Las cifras incluyen todos los territorios seleccionados.')
        except (OSError, ValueError) as exc:
            st.warning('No se pudo cargar el mapa. Puedes consultar la tabla y las cifras de la selección.')
            with st.expander('Detalle del error de carga'):
                st.code(str(exc))
    clicked = selected_id(event)
    chosen = clicked if clicked in set(data.ID) else territory
    with detail_column:
        if chosen is not None:
            detail_panel(data.loc[data.ID.eq(chosen)].iloc[0], year)
        else:
            st.subheader('Detalle del territorio')
            st.info('Haz clic en un punto o polígono, o busca un territorio en los filtros.')
            st.caption('Aquí aparecerán participación, abstención, lista nominal, conteos y cobertura.')
            st.markdown('**Cómo leer el mapa**\n\n1. Elige año y nivel territorial.\n2. Selecciona una entidad para acercarte.\n3. Haz clic para consultar sus datos.')
    ranking = data.sort_values('PRED', ascending=False)
    display = ranking[['NAME','STATE_NAME','PRED','RISK','LN_BASE','COVERAGE','MAP_COVERAGE']].copy()
    for col in ['PRED','COVERAGE','MAP_COVERAGE']:
        display[col] = (display[col]*100).round(2)
    display.columns = ['Territorio','Entidad','Abstención estimada %','Riesgo','Lista nominal base','Cobertura electoral %','Cobertura cartográfica %']
    st.subheader('Territorios para priorización')
    st.caption('Ordenados por abstención estimada, de mayor a menor. Revisa la cobertura antes de asignar recursos.')
    st.dataframe(display, hide_index=True, width='stretch', height=320)
    with st.expander('Descargar datos y mapa'):
        st.download_button('Descargar datos (CSV)', data.to_csv(index=False).encode('utf-8-sig'), f'rf_{year}_{level}.csv', 'text/csv', on_click='ignore')
        st.caption('El GeoJSON conserva los polígonos detallados y sus datos; se prepara únicamente cuando lo solicitas.')
        if st.session_state.get('rf_export', {}).get('key') != view_key:
            st.session_state.pop('rf_export', None)
        if st.button('Preparar mapa GeoJSON', key='rf_prepare_export'):
            try:
                with st.spinner('Preparando archivo de mapa…'):
                    st.session_state['rf_export'] = {'key': view_key, 'bytes': export_geojson(folder, year, level, data)}
            except (OSError, ValueError) as exc:
                st.error(f'No se pudo preparar el archivo: {exc}')
        export = st.session_state.get('rf_export')
        if export and export['key'] == view_key:
            st.download_button('Descargar mapa (GeoJSON)', export['bytes'], f'rf_mapa_{year}_{level}.geojson', 'application/geo+json', on_click='ignore')
    with st.expander('Qué significan las cifras y qué límites tienen'):
        st.markdown('Las tasas se refieren a personas con estado de votación conocido. La lista nominal es histórica y la cobertura es parcial. **Los conteos futuros mantienen constante el denominador histórico; la lista nominal futura no se predice.** No hay datos de votos por partido o candidatura.\n\nCartografía provisional MGS DIC-2025, con asignación territorial del año fuente. La vista nacional simplifica detalles pequeños; las vistas regionales y el archivo GeoJSON conservan la geometría detallada disponible. Requiere validación con cartografía oficial 2026–2027.\n\nEl semáforo es relativo dentro de cada nivel, con cortes de los percentiles 50 y 80 del pronóstico 2027. No es una probabilidad individual. Los conteos son aproximaciones al nivel seleccionado y pueden no sumar entre niveles al emplear tasas ponderadas por lista nominal.')
    with st.expander('Resultados del modelo y metodología'):
        metric = pd.read_csv(root / 'reports/rf_dashboard/metricas_multinivel.csv')
        metric = metric.loc[metric.level.eq(level), ['year','n','mae_pp','rmse_pp','r2','top20']]
        st.caption('MAE y RMSE en puntos porcentuales: menor es mejor. Top20 indica la proporción recuperada de los territorios de mayor abstención.')
        st.dataframe(metric.rename(columns={'year':'Año','n':'Territorios','mae_pp':'MAE (pp)','rmse_pp':'RMSE (pp)','r2':'R²','top20':'Recuperación Top20'}), hide_index=True)
        st.markdown('**Random Forest de regresión:** 64 árboles, profundidad 12, 143 variables históricas y demográficas. Predicciones seccionales agregadas por lista nominal de la última elección disponible. Para 2027 se entrena con objetivos 2015, 2018, 2021 y 2024 y fuentes 2021/2024.\n\nSeleccionado por error municipal; no se presenta como ganador demostrado en todos los niveles. La evaluación exige información suficiente, baja proporción de estado de votación desconocido y municipio/tipo de sección estables. La mejora es exploratoria y necesita un nuevo ciclo de evaluación.\n\n**Prevención:** priorizar diagnóstico local y acciones informativas generales en zonas de riesgo alto; verificar cobertura y barreras de acceso antes de asignar recursos.')
