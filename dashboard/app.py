from pathlib import Path
import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]

SPATIAL_PATH = (
    ROOT / "data" / "processed" / "spatial_2027"
    / "risk_2027_dashboard_simplified.geojson"
)

SCENARIOS_PATH = (
    ROOT / "data" / "processed" / "scenarios_2027"
    / "section_scenarios_2027.parquet"
)

SCENARIO_CONFIG_PATH = (
    ROOT / "reports" / "scenarios_2027"
    / "scenario_config.json"
)

SPATIAL_METADATA_PATH = (
    ROOT / "reports" / "spatial_2027"
    / "spatial_layer_metadata.json"
)

RISK_COLORS = {
    "BAJO": [46, 125, 50, 165],
    "MEDIO": [251, 192, 45, 180],
    "ALTO": [198, 40, 40, 190],
    "SIN_CLASIFICAR": [120, 120, 120, 130],
}

SCENARIO_ORDER = [
    "S0_BASELINE",
    "S1_TOP10_MINUS2",
    "S2_HIGH_MINUS2",
    "S3_HIGH_MINUS5",
]

st.set_page_config(
    page_title="Riesgo territorial de abstención",
    page_icon="🗺️",
    layout="wide",
)


@st.cache_data(show_spinner="Cargando capa espacial...")
def load_spatial():
    if not SPATIAL_PATH.exists():
        raise FileNotFoundError(
            f"No existe {SPATIAL_PATH}. Ejecuta primero src/15_build_spatial_layer.py"
        )

    gdf = gpd.read_file(SPATIAL_PATH, engine="pyogrio")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    elif str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs(epsg=4326)

    # Punto representativo para la vista nacional.
    # Lo calculamos en un CRS métrico y luego regresamos a WGS84.
    projected = gdf.to_crs(epsg=6372)
    points = gpd.GeoSeries(
        projected.geometry.representative_point(),
        crs=projected.crs,
    ).to_crs(epsg=4326)

    gdf["_LON"] = points.x.to_numpy()
    gdf["_LAT"] = points.y.to_numpy()

    return gdf


@st.cache_data(show_spinner="Cargando escenarios...")
def load_scenarios():
    if not SCENARIOS_PATH.exists():
        return None

    df = pd.read_parquet(SCENARIOS_PATH)

    keep = [
        "SECTION_KEY",
        "SCENARIO_ID",
        "SCENARIO_LABEL",
        "SCENARIO_TARGETED",
        "SCENARIO_ASSUMED_DELTA_PP",
        "SCENARIO_PRED_ABSTENCION",
        "SCENARIO_RISK_LEVEL",
        "SCENARIO_PRIORITY_TOP10",
        "RISK_LEVEL_CHANGED",
        "PRIORITY_CHANGED",
    ]

    missing = sorted(set(keep) - set(df.columns))
    if missing:
        raise RuntimeError(
            f"Faltan columnas en escenarios: {missing}"
        )

    return df[keep].copy()


@st.cache_data
def load_scenario_config():
    if not SCENARIO_CONFIG_PATH.exists():
        return {}
    return json.loads(
        SCENARIO_CONFIG_PATH.read_text(encoding="utf-8")
    )


@st.cache_data
def load_spatial_metadata():
    if not SPATIAL_METADATA_PATH.exists():
        return {}
    return json.loads(
        SPATIAL_METADATA_PATH.read_text(encoding="utf-8")
    )


def scenario_labels(scenario_df):
    if scenario_df is None or scenario_df.empty:
        return {"S0_BASELINE": "Sin intervención"}

    lookup = (
        scenario_df[["SCENARIO_ID", "SCENARIO_LABEL"]]
        .drop_duplicates()
        .set_index("SCENARIO_ID")["SCENARIO_LABEL"]
        .to_dict()
    )

    return {
        sid: lookup.get(sid, sid)
        for sid in SCENARIO_ORDER
        if sid in lookup
    }


def prepare_scenario_view(spatial, scenarios, scenario_id):
    gdf = spatial.copy()

    if scenario_id == "S0_BASELINE" or scenarios is None:
        gdf["DISPLAY_PRED"] = gdf["PRED_ABSTENCION_2027"]
        gdf["DISPLAY_RISK_LEVEL"] = gdf["RISK_LEVEL"]
        gdf["DISPLAY_PRIORITY"] = (
            gdf["PRIORITY_TOP10"].fillna(False).astype(bool)
        )
        gdf["DISPLAY_TARGETED"] = False
        gdf["DISPLAY_LEVEL_CHANGED"] = False
        gdf["DISPLAY_PRIORITY_CHANGED"] = False
        gdf["DISPLAY_SCENARIO"] = "Sin intervención"
        return gdf

    scenario = scenarios.loc[
        scenarios["SCENARIO_ID"].eq(scenario_id)
    ].copy()

    if scenario.empty:
        raise RuntimeError(
            f"No hay filas para el escenario {scenario_id}"
        )

    gdf = gdf.merge(
        scenario,
        on="SECTION_KEY",
        how="left",
        validate="one_to_one",
    )

    gdf["DISPLAY_PRED"] = gdf["SCENARIO_PRED_ABSTENCION"]
    gdf["DISPLAY_RISK_LEVEL"] = gdf["SCENARIO_RISK_LEVEL"]
    gdf["DISPLAY_PRIORITY"] = (
        gdf["SCENARIO_PRIORITY_TOP10"]
        .fillna(False)
        .astype(bool)
    )
    gdf["DISPLAY_TARGETED"] = (
        gdf["SCENARIO_TARGETED"]
        .fillna(False)
        .astype(bool)
    )
    gdf["DISPLAY_LEVEL_CHANGED"] = (
        gdf["RISK_LEVEL_CHANGED"]
        .fillna(False)
        .astype(bool)
    )
    gdf["DISPLAY_PRIORITY_CHANGED"] = (
        gdf["PRIORITY_CHANGED"]
        .fillna(False)
        .astype(bool)
    )
    gdf["DISPLAY_SCENARIO"] = gdf["SCENARIO_LABEL"]

    return gdf


def add_display_fields(gdf):
    out = gdf.copy()

    out["FILL_COLOR"] = out["DISPLAY_RISK_LEVEL"].map(
        RISK_COLORS
    )
    out["FILL_COLOR"] = out["FILL_COLOR"].apply(
        lambda x: x if isinstance(x, list)
        else RISK_COLORS["SIN_CLASIFICAR"]
    )

    out["LINE_COLOR"] = np.where(
        out["DISPLAY_PRIORITY"].to_numpy()[:, None],
        np.array([[25, 25, 25, 255]]),
        np.array([[255, 255, 255, 135]]),
    ).tolist()

    out["DISPLAY_PRED_PCT"] = (
        pd.to_numeric(out["DISPLAY_PRED"], errors="coerce") * 100
    ).round(2)

    out["BASELINE_PRED_PCT"] = (
        pd.to_numeric(out["PRED_ABSTENCION_2027"], errors="coerce") * 100
    ).round(2)

    out["LOWER_90_PCT"] = (
        pd.to_numeric(out["PRED_LOWER_90_OOS"], errors="coerce") * 100
    ).round(2)

    out["UPPER_90_PCT"] = (
        pd.to_numeric(out["PRED_UPPER_90_OOS"], errors="coerce") * 100
    ).round(2)

    out["PRIORITY_LABEL"] = out["DISPLAY_PRIORITY"].map(
        {True: "Sí", False: "No"}
    )
    out["TARGETED_LABEL"] = out["DISPLAY_TARGETED"].map(
        {True: "Sí", False: "No"}
    )
    out["LEVEL_CHANGED_LABEL"] = out["DISPLAY_LEVEL_CHANGED"].map(
        {True: "Sí", False: "No"}
    )

    return out


def view_state_from_bounds(gdf):
    if gdf.empty:
        return pdk.ViewState(
            latitude=23.6,
            longitude=-102.5,
            zoom=4.0,
        )

    minx, miny, maxx, maxy = gdf.total_bounds
    lon = (minx + maxx) / 2
    lat = (miny + maxy) / 2

    span = max(maxx - minx, maxy - miny)
    if span <= 0:
        zoom = 10
    else:
        zoom = max(
            3.0,
            min(11.0, 8.5 - math.log(span + 0.01, 2)),
        )

    return pdk.ViewState(
        latitude=float(lat),
        longitude=float(lon),
        zoom=float(zoom),
        min_zoom=3,
        max_zoom=14,
    )


def make_point_layer(df):
    # IMPORTANT: send only a small table to the browser.
    cols = [
        "_LON",
        "_LAT",
        "SECTION_KEY",
        "RECENT_EDONOM",
        "RECENT_MPIONOM",
        "DISPLAY_SCENARIO",
        "DISPLAY_PRED_PCT",
        "DISPLAY_RISK_LEVEL",
        "PRIORITY_LABEL",
        "TARGETED_LABEL",
        "LEVEL_CHANGED_LABEL",
        "LOWER_90_PCT",
        "UPPER_90_PCT",
        "HIGH_SENSITIVITY_CLASS",
        "FILL_COLOR",
        "LINE_COLOR",
    ]
    points = df[cols].copy()

    return pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position="[_LON, _LAT]",
        get_fill_color="FILL_COLOR",
        get_line_color="LINE_COLOR",
        stroked=True,
        filled=True,
        radius_min_pixels=1.7,
        radius_max_pixels=7,
        get_radius=1800,
        line_width_min_pixels=0.5,
        pickable=True,
        auto_highlight=True,
    )


def make_polygon_layer(df):
    # IMPORTANT: strip the GeoJSON to only the properties needed by the map.
    cols = [
        "geometry",
        "SECTION_KEY",
        "RECENT_EDONOM",
        "RECENT_MPIONOM",
        "DISPLAY_SCENARIO",
        "DISPLAY_PRED_PCT",
        "DISPLAY_RISK_LEVEL",
        "PRIORITY_LABEL",
        "TARGETED_LABEL",
        "LEVEL_CHANGED_LABEL",
        "LOWER_90_PCT",
        "UPPER_90_PCT",
        "HIGH_SENSITIVITY_CLASS",
        "FILL_COLOR",
        "LINE_COLOR",
    ]
    map_gdf = gpd.GeoDataFrame(
        df[cols].copy(),
        geometry="geometry",
        crs=df.crs,
    )

    return pdk.Layer(
        "GeoJsonLayer",
        data=map_gdf.__geo_interface__,
        pickable=True,
        stroked=True,
        filled=True,
        get_fill_color="properties.FILL_COLOR",
        get_line_color="properties.LINE_COLOR",
        get_line_width=18,
        line_width_min_pixels=0.6,
        auto_highlight=True,
    )


def municipality_table(df):
    if df.empty:
        return pd.DataFrame()

    table = (
        df.groupby(
            [
                "EDOCVE",
                "RECENT_EDONOM",
                "RECENT_MPIOCVE",
                "RECENT_MPIONOM",
            ],
            dropna=False,
        )
        .agg(
            secciones=("SECTION_KEY", "size"),
            riesgo_alto=(
                "DISPLAY_RISK_LEVEL",
                lambda s: int((s == "ALTO").sum()),
            ),
            top10=(
                "DISPLAY_PRIORITY",
                lambda s: int(pd.Series(s).fillna(False).sum()),
            ),
            abstencion_estimada=("DISPLAY_PRED", "mean"),
        )
        .reset_index()
    )

    table["share_alto"] = (
        table["riesgo_alto"] / table["secciones"]
    )
    table["share_top10"] = (
        table["top10"] / table["secciones"]
    )

    return table.sort_values(
        [
            "top10",
            "riesgo_alto",
            "share_alto",
            "abstencion_estimada",
        ],
        ascending=False,
    )


def state_table(df):
    if df.empty:
        return pd.DataFrame()

    table = (
        df.groupby(
            ["EDOCVE", "RECENT_EDONOM"],
            dropna=False,
        )
        .agg(
            secciones=("SECTION_KEY", "size"),
            riesgo_alto=(
                "DISPLAY_RISK_LEVEL",
                lambda s: int((s == "ALTO").sum()),
            ),
            top10=(
                "DISPLAY_PRIORITY",
                lambda s: int(pd.Series(s).fillna(False).sum()),
            ),
            abstencion_estimada=("DISPLAY_PRED", "mean"),
        )
        .reset_index()
    )

    table["share_alto"] = (
        table["riesgo_alto"] / table["secciones"]
    )
    table["share_top10"] = (
        table["top10"] / table["secciones"]
    )

    return table.sort_values(
        ["share_alto", "top10"],
        ascending=False,
    )


def format_table(df):
    out = df.copy()

    for col in [
        "abstencion_estimada",
        "share_alto",
        "share_top10",
    ]:
        if col in out.columns:
            out[col] = (out[col] * 100).round(2)

    return out.rename(
        columns={
            "RECENT_EDONOM": "Entidad",
            "RECENT_MPIONOM": "Municipio",
            "secciones": "Secciones",
            "riesgo_alto": "Alto",
            "top10": "Top10",
            "abstencion_estimada": "Abst. estimada %",
            "share_alto": "% secciones Alto",
            "share_top10": "% secciones Top10",
        }
    )


selected_model = st.sidebar.selectbox(
    "Modelo predictivo",
    ["Modelo actual · dos historias lineales", "Random Forest M17 · multinivel"],
    key="predictive_model",
)
if selected_model == "Random Forest M17 · multinivel":
    from rf_dashboard import render
    render(ROOT)
    st.stop()

st.title("Riesgo territorial de abstención electoral")
st.caption(
    "Herramienta exploratoria de priorización territorial · "
    "CCPC 2009–2024 · cartografía provisional MGS DIC-2025"
)

try:
    spatial = load_spatial()
    scenarios = load_scenarios()
    scenario_cfg = load_scenario_config()
    spatial_meta = load_spatial_metadata()
except Exception as exc:
    st.error(str(exc))
    st.stop()

labels = scenario_labels(scenarios)

with st.sidebar:
    st.header("Controles")

    selected_scenario = st.selectbox(
        "Escenario",
        options=list(labels.keys()),
        format_func=lambda x: f"{x} · {labels[x]}",
    )

    state_options = ["Todas"] + sorted(
        spatial["RECENT_EDONOM"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    selected_state = st.selectbox(
        "Entidad",
        state_options,
    )

    if selected_state == "Todas":
        municipality_options = ["Todos"]
    else:
        municipality_options = ["Todos"] + sorted(
            spatial.loc[
                spatial["RECENT_EDONOM"].eq(selected_state),
                "RECENT_MPIONOM",
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

    selected_municipality = st.selectbox(
        "Municipio",
        municipality_options,
    )

    selected_levels = st.multiselect(
        "Nivel de riesgo",
        ["BAJO", "MEDIO", "ALTO"],
        default=["BAJO", "MEDIO", "ALTO"],
    )

    priority_only = st.checkbox(
        "Sólo Top10 prioritario",
        value=False,
    )

    sensitivity_options = [
        "Todas",
        "NO_ALTO",
        "ALTO_SENSIBLE_2PP",
        "ALTO_SENSIBLE_5PP",
        "ALTO_PERSISTENTE_MAS_5PP",
    ]
    selected_sensitivity = st.selectbox(
        "Persistencia / sensibilidad",
        sensitivity_options,
    )

view = prepare_scenario_view(
    spatial,
    scenarios,
    selected_scenario,
)

filtered = view.copy()

if selected_state != "Todas":
    filtered = filtered.loc[
        filtered["RECENT_EDONOM"].eq(selected_state)
    ]

if selected_municipality != "Todos":
    filtered = filtered.loc[
        filtered["RECENT_MPIONOM"].eq(selected_municipality)
    ]

if selected_levels:
    filtered = filtered.loc[
        filtered["DISPLAY_RISK_LEVEL"].isin(selected_levels)
    ]
else:
    filtered = filtered.iloc[0:0]

if priority_only:
    filtered = filtered.loc[
        filtered["DISPLAY_PRIORITY"]
    ]

if selected_sensitivity != "Todas":
    filtered = filtered.loc[
        filtered["HIGH_SENSITIVITY_CLASS"]
        .eq(selected_sensitivity)
    ]

filtered = add_display_fields(filtered)

k1, k2, k3, k4 = st.columns(4)

k1.metric("Secciones mostradas", f"{len(filtered):,}")

mean_pred = (
    filtered["DISPLAY_PRED"].mean() * 100
    if len(filtered)
    else float("nan")
)
k2.metric(
    "Abstención estimada media",
    "—" if pd.isna(mean_pred) else f"{mean_pred:.1f}%",
)

high_n = int(
    filtered["DISPLAY_RISK_LEVEL"].eq("ALTO").sum()
)
k3.metric("Riesgo ALTO", f"{high_n:,}")

priority_n = int(filtered["DISPLAY_PRIORITY"].sum())
k4.metric("Top10 prioritario", f"{priority_n:,}")

st.subheader("Mapa territorial")
st.markdown(
    """
    <div style="display:flex;gap:18px;align-items:center;margin-bottom:8px;">
      <span><b>Leyenda:</b></span>
      <span>🟢 Bajo</span>
      <span>🟡 Medio</span>
      <span>🔴 Alto</span>
      <span>⬛ borde oscuro = Top10 prioritario</span>
    </div>
    """,
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning("No hay secciones con los filtros seleccionados.")
else:
    # National view: points only. State/municipality: polygons.
    if selected_state == "Todas":
        st.caption(
            "Vista nacional optimizada: cada sección se representa por un "
            "punto dentro de su polígono. Selecciona una entidad para ver "
            "los polígonos seccionales."
        )
        layer = make_point_layer(filtered)
    else:
        st.caption(
            "Vista detallada: polígonos de sección electoral."
        )
        layer = make_polygon_layer(filtered)

    tooltip = {
        "html": """
        <b>Sección:</b> {SECTION_KEY}<br/>
        <b>Entidad:</b> {RECENT_EDONOM}<br/>
        <b>Municipio:</b> {RECENT_MPIONOM}<br/>
        <b>Escenario:</b> {DISPLAY_SCENARIO}<br/>
        <b>Abstención estimada:</b> {DISPLAY_PRED_PCT}%<br/>
        <b>Riesgo:</b> {DISPLAY_RISK_LEVEL}<br/>
        <b>Top10:</b> {PRIORITY_LABEL}<br/>
        <b>Objetivo del escenario:</b> {TARGETED_LABEL}<br/>
        <b>Cambió de nivel:</b> {LEVEL_CHANGED_LABEL}<br/>
        <b>Intervalo empírico 90%:</b> {LOWER_90_PCT}% – {UPPER_90_PCT}%<br/>
        <b>Persistencia:</b> {HIGH_SENSITIVITY_CLASS}
        """,
        "style": {
            "backgroundColor": "rgba(20,20,20,0.93)",
            "color": "white",
        },
    }

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state_from_bounds(filtered),
        tooltip=tooltip,
        map_style="light",
    )

    st.pydeck_chart(
        deck,
        width="stretch",
    )

st.subheader("Lectura del escenario")

if selected_scenario == "S0_BASELINE":
    st.info(
        "Escenario base: conserva la estimación territorial 2027. "
        "No representa una intervención."
    )
else:
    selected_rows = scenarios.loc[
        scenarios["SCENARIO_ID"].eq(selected_scenario)
    ]

    assumed_delta = (
        selected_rows["SCENARIO_ASSUMED_DELTA_PP"].iloc[0]
        if not selected_rows.empty
        else None
    )

    st.warning(
        f"El escenario seleccionado utiliza un supuesto de sensibilidad de "
        f"{assumed_delta:.1f} puntos porcentuales en los territorios objetivo. "
        "No es una estimación causal del efecto de una política específica."
    )

left, right = st.columns(2)

with left:
    st.subheader("Resumen por entidad")
    state_df = state_table(filtered)
    if state_df.empty:
        st.caption("Sin datos.")
    else:
        st.dataframe(
            format_table(state_df).drop(
                columns=["EDOCVE"],
                errors="ignore",
            ),
            width="stretch",
            hide_index=True,
        )

with right:
    st.subheader("Municipios con mayor concentración")
    mun_df = municipality_table(filtered)
    if mun_df.empty:
        st.caption("Sin datos.")
    else:
        st.dataframe(
            format_table(
                mun_df.head(30)
            ).drop(
                columns=[
                    "EDOCVE",
                    "RECENT_MPIOCVE",
                ],
                errors="ignore",
            ),
            width="stretch",
            hide_index=True,
        )

with st.expander("Metodología y limitaciones"):
    st.markdown(
        """
        **Arquitectura predictiva:** `two_history_linear`.

        La estimación territorial combina dos memorias electorales:
        la última elección de la misma familia y la elección federal más
        reciente. La arquitectura fue seleccionada mediante backtesting
        temporal y análisis de robustez por municipio.

        **Semáforo:** es una priorización territorial relativa, no una
        probabilidad individual de abstención.

        - Bajo: percentil ≤ 50.
        - Medio: percentiles 50–80.
        - Alto: percentil > 80.
        - Top10: bandera adicional para el 10% superior.

        **Escenarios:** los cambios de 2 o 5 puntos porcentuales son supuestos
        de sensibilidad. No representan efectos causales estimados de una
        intervención concreta.

        **Incertidumbre:** los intervalos mostrados son empíricos y proceden de
        errores fuera de muestra. No garantizan cobertura ante cambios
        estructurales futuros.

        **Cartografía:** esta versión utiliza MGS por entidad federativa con
        corte DIC-2025 y es provisional. Debe sustituirse por la cartografía
        oficial 2026–2027 antes de la entrega final.
        """
    )

    if spatial_meta:
        st.caption(
            f"Estado cartográfico registrado: "
            f"{spatial_meta.get('status', 'sin metadata')}"
        )

    if scenario_cfg:
        st.caption(
            "Los umbrales del semáforo permanecen congelados entre escenarios "
            "para poder observar cambios reales de categoría."
        )
