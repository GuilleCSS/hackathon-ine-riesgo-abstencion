from pathlib import Path
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from comun import (
    CompactDeck,
    NATIONAL_VIEW_HELP,
    NATIONAL_VIEWS,
    add_representative_points,
    load_base,
    load_large_shapes,
    make_base_layer,
    map_mode,
    split_layers,
    view_state_from_bounds,
)


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


FORECAST_ALL_PATH = (
    ROOT / "data" / "processed" / "forecast_2027"
    / "forecast_2027_all_comparable.parquet"
)

# Violeta validado contra el semáforo y el gris (dataviz validate_palette.js).
HIGH_NS_COLOR = [74, 58, 167, 175]

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

    return add_representative_points(gdf)


@st.cache_data(show_spinner="Cargando secciones con NS alto...")
def load_high_ns():
    # Secciones comparables con estimación pero NS > 10% en 2021 o 2024:
    # quedan fuera del semáforo (primary_clean10).
    if not FORECAST_ALL_PATH.exists():
        return None

    df = pd.read_parquet(
        FORECAST_ALL_PATH,
        columns=[
            "SECTION_KEY",
            "QUALITY_FLAG",
            "RECENT_EDONOM",
            "RECENT_MPIONOM",
            "PRED_ABSTENCION_2027",
            "PRED_LOWER_90_OOS",
            "PRED_UPPER_90_OOS",
            "SAME_PCT_NS_LN",
            "RECENT_PCT_NS_LN",
        ],
    )
    return df.loc[df["QUALITY_FLAG"].eq("comparable_high_ns")].drop(
        columns="QUALITY_FLAG"
    )


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
    out["QUALITY_LABEL"] = "NS ≤ 10% en 2021 y 2024"

    return out


def high_ns_display(base_scope, high_ns, thresholds):
    # Mismas columnas que la capa de riesgo para reutilizar capa y tooltip.
    out = base_scope.merge(high_ns, on="SECTION_KEY")
    pred = out["PRED_ABSTENCION_2027"]

    out["DISPLAY_SCENARIO"] = "No aplica (fuera del semáforo)"
    out["DISPLAY_PRED_PCT"] = (pred * 100).round(2)
    out["DISPLAY_RISK_LEVEL"] = "Sin semáforo"
    if thresholds:
        # Nivel que tendría con los umbrales congelados; sólo orientativo.
        level = pd.Series(
            np.select(
                [pred.le(thresholds["q50"]), pred.le(thresholds["q80"])],
                ["BAJO", "MEDIO"],
                "ALTO",
            ),
            index=out.index,
        )
        out["DISPLAY_RISK_LEVEL"] = "Sin semáforo · indicativo " + level

    for col in [
        "PRIORITY_LABEL",
        "TARGETED_LABEL",
        "LEVEL_CHANGED_LABEL",
        "HIGH_SENSITIVITY_CLASS",
    ]:
        out[col] = "—"

    out["LOWER_90_PCT"] = (out["PRED_LOWER_90_OOS"] * 100).round(2)
    out["UPPER_90_PCT"] = (out["PRED_UPPER_90_OOS"] * 100).round(2)
    out["QUALITY_LABEL"] = (
        "NS alto, baja confiabilidad (2021: "
        + (out["SAME_PCT_NS_LN"] * 100).round(1).astype(str)
        + "% · 2024: "
        + (out["RECENT_PCT_NS_LN"] * 100).round(1).astype(str)
        + "%)"
    )
    out["FILL_COLOR"] = [HIGH_NS_COLOR] * len(out)
    out["LINE_COLOR"] = [[255, 255, 255, 135]] * len(out)

    return out


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
        "QUALITY_LABEL",
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
        "QUALITY_LABEL",
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


def state_table(df, coverage=None):
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

    if coverage is not None:
        table = table.merge(coverage, on="EDOCVE", how="left")

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
        "cobertura",
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
            "secciones_carto": "Secc. cartografía",
            "cobertura": "Cobertura %",
        }
    )


st.title("Riesgo territorial de abstención electoral")
st.caption(
    "Herramienta exploratoria de priorización territorial · "
    "CCPC 2009–2024 · cartografía provisional MGS DIC-2025"
)

try:
    spatial = load_spatial()
    base = load_base()
    large_shapes = load_large_shapes()
    high_ns = load_high_ns()
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

    national_view = st.radio(
        "Vista nacional",
        NATIONAL_VIEWS,
        horizontal=True,
        disabled=selected_state != "Todas" or large_shapes is None,
        help=NATIONAL_VIEW_HELP,
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

    show_high_ns = st.checkbox(
        "Mostrar secciones con NS alto (violeta)",
        value=True,
        disabled=high_ns is None or base is None,
        help=(
            "Tienen estimación, pero más de 10% de sus registros sin "
            "información (NS) en 2021 o 2024, así que quedan fuera del "
            "semáforo. Los filtros de riesgo no las afectan."
        ),
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

# La capa base sólo se acota por entidad/municipio: los filtros de riesgo no
# cambian qué secciones existen.
base_scope = base
if base is not None and selected_state != "Todas":
    in_state = spatial["RECENT_EDONOM"].eq(selected_state)
    base_scope = base.loc[
        base["CARTO_EDOCVE"].eq(spatial.loc[in_state, "EDOCVE"].iloc[0])
    ]
    if selected_municipality != "Todos":
        mpio = spatial.loc[
            in_state & spatial["RECENT_MPIONOM"].eq(selected_municipality),
            "RECENT_MPIOCVE",
        ].iloc[0]
        base_scope = base_scope.loc[base_scope["CARTO_MPIOCVE"].eq(mpio)]

high_ns_scope = None
if base_scope is not None and high_ns is not None:
    high_ns_scope = high_ns_display(
        base_scope,
        high_ns,
        scenario_cfg.get("classification_thresholds_frozen_from_baseline"),
    )

coverage = None
if base is not None:
    coverage = (
        base.groupby("CARTO_EDOCVE")
        .agg(
            secciones_carto=("SECTION_KEY", "size"),
            cobertura=("HAS_ESTIMATE", "mean"),
        )
        .rename_axis("EDOCVE")
        .reset_index()
    )

k1, k2, k3, k4, k5 = st.columns(5)

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

if base_scope is not None and len(base_scope):
    n_est = int(base_scope["HAS_ESTIMATE"].sum())
    k5.metric(
        "Cobertura predictiva",
        f"{n_est / len(base_scope):.1%}",
        help=(
            "Secciones con estimación entre todas las secciones de la "
            "cartografía. No depende de los filtros de riesgo."
        ),
    )
    n_high_ns = 0 if high_ns_scope is None else len(high_ns_scope)
    k5.caption(
        f"{n_est:,} de {len(base_scope):,} secciones"
        + (f" · {n_high_ns:,} más con NS alto" if n_high_ns else "")
    )

draw_high_ns = (
    show_high_ns and high_ns_scope is not None and len(high_ns_scope) > 0
)

base_legend = (
    '<span><span style="display:inline-block;width:12px;height:12px;'
    'border-radius:50%;background:rgb(189,189,189);vertical-align:-1px;">'
    "</span> Gris = sin estimación o fuera de filtros</span>"
    if base is not None
    else ""
)
if draw_high_ns:
    base_legend += (
        "<span>🟣 Violeta = NS > 10%: estimación de baja confiabilidad, "
        "fuera del semáforo</span>"
    )

st.subheader("Mapa territorial")
st.markdown(
    f"""
    <div style="display:flex;flex-wrap:wrap;gap:18px;align-items:center;margin-bottom:8px;">
      <span><b>Leyenda:</b></span>
      <span>🟢 Bajo</span>
      <span>🟡 Medio</span>
      <span>🔴 Alto</span>
      <span>⬛ borde oscuro = Top10 prioritario</span>
      {base_legend}
    </div>
    """,
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning("No hay secciones con los filtros seleccionados.")
else:
    mode = map_mode(selected_state == "Todas", national_view, large_shapes)
    st.caption({
        "hibrida": "Vista nacional híbrida: las secciones grandes y poco "
                   "pobladas se dibujan como polígono simplificado y las demás "
                   "como punto. Selecciona una entidad para ver los polígonos "
                   "detallados.",
        "puntos": "Vista nacional optimizada: cada sección se representa por "
                  "un punto dentro de su polígono. Selecciona una entidad "
                  "para ver los polígonos seccionales.",
        "poligonos": "Vista detallada: polígonos de sección electoral.",
    }[mode])

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
        <b>Persistencia:</b> {HIGH_SENSITIVITY_CLASS}<br/>
        <b>Calidad:</b> {QUALITY_LABEL}
        """,
        "style": {
            "backgroundColor": "rgba(20,20,20,0.93)",
            "color": "white",
        },
    }

    # De abajo hacia arriba: gris, violeta (NS alto), semáforo; y todos los
    # polígonos debajo de todos los puntos. El gris sólo cubre secciones que
    # no se dibujan en color, para no alterar los colores con transparencia.
    groups = []
    drawn = set(filtered["SECTION_KEY"])
    if draw_high_ns:
        drawn |= set(high_ns_scope["SECTION_KEY"])
    if base_scope is not None:
        groups.append((
            base_scope.loc[~base_scope["SECTION_KEY"].isin(drawn)],
            lambda d: make_base_layer(d, as_points=True),
            lambda d: make_base_layer(d, as_points=False),
        ))
    if draw_high_ns:
        groups.append((high_ns_scope, make_point_layer, make_polygon_layer))
    groups.append((filtered, make_point_layer, make_polygon_layer))

    polygon_layers, point_layers = [], []
    for df, point_layer, polygon_layer in groups:
        polys, points = split_layers(
            df, mode, large_shapes, point_layer, polygon_layer
        )
        polygon_layers += polys
        point_layers += points
    layers = polygon_layers + point_layers

    deck = CompactDeck(
        layers=layers,
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
    state_df = state_table(filtered, coverage)
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

        **Capa gris:** todas las secciones de la cartografía. Las que no se
        colorean no tienen estimación (no forman parte del universo
        `primary_clean10` o no se conciliaron con la cartografía) o quedaron
        fuera de los filtros. La cobertura predictiva es la proporción de
        secciones cartográficas con estimación.

        **Capa violeta:** secciones comparables entre 2021 y 2024 con
        estimación, pero con más de 10% de registros sin información (NS) en
        alguno de los dos años. No entran al semáforo ni a los escenarios; el
        tooltip muestra su nivel indicativo con los umbrales congelados y su
        NS por año. Los filtros de riesgo no las afectan.
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
