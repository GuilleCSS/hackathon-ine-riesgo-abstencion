from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from comun import (
    CompactDeck,
    NATIONAL_VIEW_HELP,
    NATIONAL_VIEWS,
    load_base,
    load_large_shapes,
    make_base_layer,
    map_mode,
    split_layers,
    view_state_from_bounds,
)


ROOT = Path(__file__).resolve().parents[1]

MASTER_PATH = (
    ROOT / "data" / "processed"
    / "section_election_master_v1.csv.gz"
)

COLS = [
    "AELEC",
    "TIPO_ELECCION",
    "EDOCVE",
    "EDONOM",
    "MPIOCVE",
    "MPIONOM",
    "TIPOSEC",
    "SECTION_KEY",
    "LN",
    "SV",
    "NV",
    "NS",
    "PCT_ABSTENCION",
    "PCT_NS_LN",
    "PREV_YEAR",
    "DELTA_ABST_VS_PREV",
]

# De menor a mayor NS. Las secciones con NS <= 5% no se grafican.
NS_BUCKETS = ["5–10%", "10–25%", "25–50%", "50–99%", "100% (sin información)"]

# Rampas ordinales validadas por modo (dataviz validate_palette.js --ordinal).
NS_RAMP = {
    "light": ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"],
    "dark": ["#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"],
}
LINE_COLOR = {"light": "#2a78d6", "dark": "#3987e5"}
SURFACE = {"light": "#ffffff", "dark": "#0e1117"}

COUNT = st.column_config.NumberColumn(format="localized")

# Mapa por año (fondo claro de CARTO en ambos modos). Rampa y gris validados
# contra ese fondo y entre sí (dataviz validate_palette.js).
MAP_RAMP = ["#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
NO_RECORD_COLOR = [208, 208, 206, 200]

# Divergente: azul = bajó la abstención, rojo = subió. Sin clase central gris
# porque el gris ya significa "sin dato"; brazos con la misma claridad.
DELTA_RAMP = ["#184f95", "#5598e7", "#e8706d", "#a82a29"]

# Rangos fijos para comparar entre años:
# (campo, cortes, etiquetas, right, rampa).
MAP_VARIABLES = {
    "Abstención": (
        "PCT_ABSTENCION",
        [0.35, 0.45, 0.55, 0.65],
        ["< 35%", "35–45%", "45–55%", "55–65%", "≥ 65%"],
        False,
        MAP_RAMP,
    ),
    "Registros sin información (NS)": (
        "PCT_NS_LN",
        [0.05, 0.10, 0.25, 0.50],
        ["≤ 5%", "5–10%", "10–25%", "25–50%", "> 50%"],
        True,
        MAP_RAMP,
    ),
    "Cambio vs. elección anterior del mismo tipo": (
        "DELTA_ABST_VS_PREV",
        [-0.05, 0.0, 0.05],
        ["bajó más de 5 pp", "bajó hasta 5 pp", "subió hasta 5 pp", "subió más de 5 pp"],
        False,
        DELTA_RAMP,
    ),
}

ELECTION_TYPES = {
    "Todas": None,
    "Intermedias": "intermedia",
    "Presidenciales": "presidencial",
}


@st.cache_data(show_spinner="Cargando base maestra...")
def load_master(cols):
    # cols como argumento: el caché se invalida si cambia la lista de columnas.
    if not MASTER_PATH.exists():
        return None
    return pd.read_csv(MASTER_PATH, usecols=list(cols))


def yearly_summary(df):
    out = (
        df.groupby("AELEC")
        .agg(
            tipo=("TIPO_ELECCION", "first"),
            secciones=("SECTION_KEY", "size"),
            LN=("LN", "sum"),
            SV=("SV", "sum"),
            NV=("NV", "sum"),
            NS=("NS", "sum"),
        )
        .reset_index()
    )
    out["abstencion"] = out["NV"] / (out["SV"] + out["NV"])
    out["pct_ns"] = out["NS"] / out["LN"]
    return out


def ns_buckets(df):
    pct = df["NS"] / df["LN"]
    bucket = np.select(
        [
            pct.ge(1),
            pct.gt(0.50),
            pct.gt(0.25),
            pct.gt(0.10),
            pct.gt(0.05),
        ],
        NS_BUCKETS[::-1],
        "≤5%",
    )
    counts = (
        df.assign(rango=bucket)
        .groupby(["AELEC", "rango"])
        .size()
        .rename("secciones")
        .reset_index()
    )
    counts["pct_anio"] = counts["secciones"] / counts.groupby("AELEC")[
        "secciones"
    ].transform("sum")
    return counts


def changes_vs_previous(df):
    years = sorted(df["AELEC"].unique())
    rows = []
    for prev, cur in zip(years, years[1:]):
        cols = ["SECTION_KEY", "MPIOCVE", "TIPOSEC"]
        a = df.loc[df["AELEC"].eq(prev), cols]
        b = df.loc[df["AELEC"].eq(cur), cols]
        both = a.merge(b, on="SECTION_KEY", suffixes=("_a", "_b"))
        rows.append({
            "Elección": str(cur),
            "Comparada con": str(prev),
            "Secciones": len(b),
            "Nuevas": len(b) - len(both),
            "Desaparecidas": len(a) - len(both),
            "Cambió de municipio": int(
                both["MPIOCVE_a"].ne(both["MPIOCVE_b"]).sum()
            ),
            "Cambió de tipo": int(
                both["TIPOSEC_a"].ne(both["TIPOSEC_b"]).sum()
            ),
        })
    return pd.DataFrame(rows)


def line_chart(data, field, title, color, surface):
    base = alt.Chart(data).encode(
        x=alt.X("AELEC:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(
            f"{field}:Q",
            title=None,
            axis=alt.Axis(format="%"),
            scale=alt.Scale(zero=True),
        ),
        tooltip=[
            alt.Tooltip("AELEC:O", title="Año"),
            alt.Tooltip("tipo:N", title="Elección"),
            alt.Tooltip(f"{field}:Q", title=title, format=".1%"),
        ],
    )
    line = base.mark_line(color=color, strokeWidth=2)
    points = base.mark_point(
        color=color,
        filled=True,
        opacity=1,
        size=90,
        stroke=surface,
        strokeWidth=2,
    )
    return (line + points).properties(title=title, height=260)


def fmt(values, pattern):
    return values.map(lambda v: "—" if pd.isna(v) else pattern.format(v))


def year_map_frame(year_map, field, edges, right, ramp):
    colors = [
        [int(h[i:i + 2], 16) for i in (1, 3, 5)] + [215] for h in ramp
    ]
    values = year_map[field].to_numpy(float)
    idx = np.digitize(values, edges, right=right)

    out = year_map.copy()
    out["FILL_COLOR"] = [
        NO_RECORD_COLOR if np.isnan(v) else colors[i]
        for v, i in zip(values, idx)
    ]
    out["ABST_TXT"] = fmt(out["PCT_ABSTENCION"] * 100, "{:.1f}%")
    out["NS_PCT_TXT"] = fmt(out["PCT_NS_LN"] * 100, "{:.1f}%")
    out["DELTA_TXT"] = fmt(out["DELTA_ABST_VS_PREV"] * 100, "{:+.1f} pp")
    out["PREV_TXT"] = fmt(out["PREV_YEAR"], "{:.0f}")
    for col in ["LN", "SV", "NV", "NS"]:
        out[f"{col}_TXT"] = fmt(out[col], "{:,.0f}")
    return out


YEAR_MAP_COLS = [
    "SECTION_KEY", "MPIONOM", "AELEC", "ABST_TXT", "NS_PCT_TXT",
    "DELTA_TXT", "PREV_TXT", "LN_TXT", "SV_TXT", "NV_TXT", "NS_TXT",
    "FILL_COLOR",
]


def year_point_layer(df):
    return pdk.Layer(
        "ScatterplotLayer",
        data=df[["_LON", "_LAT"] + YEAR_MAP_COLS],
        get_position="[_LON, _LAT]",
        get_fill_color="FILL_COLOR",
        radius_min_pixels=1.7,
        radius_max_pixels=7,
        get_radius=1800,
        pickable=True,
        auto_highlight=True,
    )


def year_polygon_layer(df):
    return pdk.Layer(
        "GeoJsonLayer",
        data=df[["geometry"] + YEAR_MAP_COLS].__geo_interface__,
        stroked=True,
        filled=True,
        get_fill_color="properties.FILL_COLOR",
        get_line_color=[255, 255, 255, 135],
        line_width_min_pixels=0.6,
        pickable=True,
        auto_highlight=True,
    )


st.title("Datos por año")
st.caption(
    "Conteos Censales de Participación Ciudadana 2009–2024 agregados por "
    "sección. Muestra cómo cambian los registros entre elecciones, para "
    "valorar las restricciones del modelo."
)

master = load_master(tuple(COLS))
if master is None:
    st.error(
        f"No existe {MASTER_PATH.relative_to(ROOT)}. "
        "Ejecuta primero src/02_build_master.py"
    )
    st.stop()

mode = "dark" if st.context.theme.type == "dark" else "light"

states = (
    master.loc[master["AELEC"].eq(master["AELEC"].max())]
    .drop_duplicates("EDOCVE")
    .set_index("EDOCVE")["EDONOM"]
    .sort_values()
)

filter_col, type_col, _ = st.columns([1, 1.4, 1.6])
choice = filter_col.selectbox("Entidad", ["Nacional"] + states.tolist())
election_type = type_col.radio(
    "Tipo de elección",
    list(ELECTION_TYPES),
    horizontal=True,
    help=(
        "Las intermedias (sólo diputados) tienen mucha más abstención que las "
        "presidenciales. Para ver tendencias reales conviene comparar dentro "
        "del mismo tipo, como hace el modelo."
    ),
)

edocve = None if choice == "Nacional" else states.index[states.eq(choice)][0]
df = master if edocve is None else master.loc[master["EDOCVE"].eq(edocve)]
if ELECTION_TYPES[election_type]:
    df = df.loc[df["TIPO_ELECCION"].eq(ELECTION_TYPES[election_type])]

st.info(
    "Restricciones actuales del modelo 2027: la sección debe existir en "
    "2021 y 2024, no cambiar de municipio ni de tipo entre ambas, y tener "
    "NS ≤ 10% de su lista nominal en los dos años."
)

summary = yearly_summary(df)

st.subheader("Abstención y registros sin información")
st.caption(
    "Intermedias: 2009, 2015 y 2021 · Presidenciales: 2012, 2018 y 2024. "
    "Abstención = NV / (SV + NV); NS = registros sin información de "
    "participación, como % de la lista nominal."
)
left, right = st.columns(2)
left.altair_chart(
    line_chart(
        summary, "abstencion", "Abstención",
        LINE_COLOR[mode], SURFACE[mode],
    ),
    width="stretch",
)
right.altair_chart(
    line_chart(
        summary, "pct_ns", "Registros sin información (NS)",
        LINE_COLOR[mode], SURFACE[mode],
    ),
    width="stretch",
)

st.dataframe(
    summary.assign(AELEC=summary["AELEC"].astype(str)).rename(columns={
        "AELEC": "Año",
        "tipo": "Elección",
        "secciones": "Secciones",
        "LN": "Lista nominal",
        "SV": "Votaron (SV)",
        "NV": "No votaron (NV)",
        "NS": "Sin información (NS)",
        "abstencion": "Abstención",
        "pct_ns": "% NS",
    }),
    hide_index=True,
    width="stretch",
    column_config={
        "Secciones": st.column_config.NumberColumn(format="localized"),
        "Lista nominal": st.column_config.NumberColumn(format="localized"),
        "Votaron (SV)": st.column_config.NumberColumn(format="localized"),
        "No votaron (NV)": st.column_config.NumberColumn(format="localized"),
        "Sin información (NS)": st.column_config.NumberColumn(
            format="localized"
        ),
        "Abstención": st.column_config.NumberColumn(format="percent"),
        "% NS": st.column_config.NumberColumn(format="percent"),
    },
)

st.subheader("Mapa por año")
st.caption(
    "Valor de cada sección en la elección elegida, dibujado sobre la "
    "cartografía DIC-2025. Los rangos son fijos para comparar entre años."
)

base = load_base()
large_shapes = load_large_shapes()

year_col, var_col, view_col = st.columns([2, 2.6, 1.4])
var_label = var_col.radio("Variable", list(MAP_VARIABLES), horizontal=True)
field, edges, labels, right, ramp = MAP_VARIABLES[var_label]
# El cambio necesita una elección anterior del mismo tipo (no existe en 2009 ni 2012).
years = sorted(df.loc[df[field].notna(), "AELEC"].unique().tolist())
year = year_col.select_slider(
    "Año",
    years,
    value=years[-1],
    key="anio_" + "_".join(map(str, years)),
)
national_view = view_col.radio(
    "Vista nacional",
    NATIONAL_VIEWS,
    horizontal=True,
    disabled=edocve is not None or large_shapes is None,
    help=NATIONAL_VIEW_HELP,
)

if base is None:
    st.warning(
        "Falta data/processed/spatial_2027/cartography_base_2027.parquet. "
        "Ejecuta src/15_build_spatial_layer.py"
    )
else:
    base_scope = (
        base if edocve is None else base.loc[base["CARTO_EDOCVE"].eq(edocve)]
    )
    rows = df.loc[df["AELEC"].eq(year)]
    year_map = year_map_frame(
        base_scope.merge(rows, on="SECTION_KEY"), field, edges, right, ramp
    )
    view_mode = map_mode(edocve is None, national_view, large_shapes)

    swatches = "".join(
        f'<span><span style="display:inline-block;width:12px;height:12px;'
        f'border-radius:50%;background:{color};vertical-align:-1px;"></span> '
        f"{label}</span>"
        for color, label in zip(ramp, labels)
    )
    st.markdown(
        f"""
        <div style="display:flex;flex-wrap:wrap;gap:18px;align-items:center;margin-bottom:8px;">
          <span><b>{var_label}:</b></span>
          {swatches}
          <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb(208,208,206);vertical-align:-1px;"></span> Sin registro en {year} o sin dato</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"{len(year_map):,} de {len(rows):,} secciones de {year} tienen "
        "polígono en la cartografía DIC-2025; las demás ya no existen con esa "
        "clave. "
        + {
            "hibrida": "Vista nacional híbrida: secciones grandes como "
                       "polígono simplificado y las demás como punto; elige "
                       "una entidad para ver los polígonos detallados.",
            "puntos": "Vista nacional con un punto por sección; elige una "
                      "entidad para ver polígonos.",
            "poligonos": "",
        }[view_mode]
    )

    # Todos los polígonos debajo de todos los puntos; el gris sólo donde no
    # hay registro del año.
    no_record = base_scope.loc[
        ~base_scope["SECTION_KEY"].isin(year_map["SECTION_KEY"])
    ]
    base_polys, base_points = split_layers(
        no_record, view_mode, large_shapes,
        lambda d: make_base_layer(d, True, NO_RECORD_COLOR),
        lambda d: make_base_layer(d, False, NO_RECORD_COLOR),
    )
    year_polys, year_points = split_layers(
        year_map, view_mode, large_shapes, year_point_layer, year_polygon_layer
    )

    st.pydeck_chart(
        CompactDeck(
            layers=base_polys + year_polys + base_points + year_points,
            initial_view_state=view_state_from_bounds(base_scope),
            tooltip={
                "html": """
                <b>Sección:</b> {SECTION_KEY}<br/>
                <b>Municipio:</b> {MPIONOM}<br/>
                <b>Año:</b> {AELEC}<br/>
                <b>Abstención:</b> {ABST_TXT}<br/>
                <b>Sin información (NS):</b> {NS_PCT_TXT}<br/>
                <b>Cambio vs. {PREV_TXT}:</b> {DELTA_TXT}<br/>
                <b>Lista nominal:</b> {LN_TXT}<br/>
                <b>Votaron (SV):</b> {SV_TXT} · <b>No votaron (NV):</b> {NV_TXT}
                · <b>NS:</b> {NS_TXT}
                """,
                "style": {
                    "backgroundColor": "rgba(20,20,20,0.93)",
                    "color": "white",
                },
            },
            map_style="light",
        ),
        width="stretch",
    )

st.subheader("Secciones según su proporción de registros sin información")
st.caption(
    "Cada barra cuenta las secciones de ese año con más de 5% de NS. Con el "
    "umbral actual (10%), todo lo que está debajo de la franja superior "
    "(5–10%) queda fuera del modelo si ocurre en 2021 o 2024."
)

buckets = ns_buckets(df)
plotted = buckets.loc[buckets["rango"].isin(NS_BUCKETS)].assign(
    orden=lambda d: d["rango"].map({b: i for i, b in enumerate(NS_BUCKETS)})
)
bars = (
    alt.Chart(plotted)
    .mark_bar(size=34, stroke=SURFACE[mode], strokeWidth=2)
    .encode(
        x=alt.X("AELEC:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("secciones:Q", title="Secciones"),
        color=alt.Color(
            "rango:N",
            title="NS de la sección",
            scale=alt.Scale(domain=NS_BUCKETS, range=NS_RAMP[mode]),
            legend=alt.Legend(orient="top"),
        ),
        order=alt.Order("orden:Q", sort="descending"),
        tooltip=[
            alt.Tooltip("AELEC:O", title="Año"),
            alt.Tooltip("rango:N", title="NS de la sección"),
            alt.Tooltip("secciones:Q", title="Secciones", format=","),
            alt.Tooltip("pct_anio:Q", title="% de las secciones del año", format=".1%"),
        ],
    )
    .properties(height=320)
)
st.altair_chart(bars, width="stretch")

bucket_table = (
    buckets.pivot(index="AELEC", columns="rango", values="secciones")
    .reindex(columns=["≤5%"] + NS_BUCKETS)
    .fillna(0)
    .astype(int)
)
bucket_table["% con NS > 10%"] = (
    bucket_table[NS_BUCKETS[1:]].sum(axis=1) / bucket_table.sum(axis=1)
)
st.dataframe(
    bucket_table.reset_index()
    .assign(AELEC=lambda d: d["AELEC"].astype(str))
    .rename(columns={"AELEC": "Año"}),
    hide_index=True,
    width="stretch",
    column_config={
        **{c: COUNT for c in ["≤5%"] + NS_BUCKETS},
        "% con NS > 10%": st.column_config.NumberColumn(format="percent"),
    },
)

st.subheader(
    "Cambios respecto a la elección anterior"
    + ("" if election_type == "Todas" else " del mismo tipo")
)
st.caption(
    "Secciones nuevas o desaparecidas por la actualización de la "
    "cartografía, y secciones que conservan su clave pero cambian de "
    "municipio o de tipo (urbana, mixta, rural)."
)
st.dataframe(
    changes_vs_previous(df),
    hide_index=True,
    width="stretch",
    column_config={
        c: COUNT
        for c in [
            "Secciones",
            "Nuevas",
            "Desaparecidas",
            "Cambió de municipio",
            "Cambió de tipo",
        ]
    },
)
