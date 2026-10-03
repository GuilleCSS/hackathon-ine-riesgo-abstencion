from pathlib import Path
import json

import altair as alt
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


ROOT = Path(__file__).resolve().parents[2]
CLUSTERS_PATH = ROOT / "data" / "processed" / "clustering" / "section_clusters.parquet"
REPORT = ROOT / "reports" / "clustering"

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
ELECTION_TYPES = {
    "Todas": YEARS,
    "Intermedias": [2009, 2015, 2021],
    "Presidenciales": [2012, 2018, 2024],
}

# Paleta categórica de referencia en orden fijo (dataviz): pasa en pares
# adyacentes (líneas y barras apiladas) en ambos modos. En el mapa no pasa con
# los 5 colores a la vez, por eso ahí se muestra un grupo por vez.
GROUP_COLORS = {
    "light": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
    "dark": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
}
REFERENCE_COLOR = {"light": "#52514e", "dark": "#c3c2b7"}
SURFACE = {"light": "#ffffff", "dark": "#0e1117"}
COUNT = st.column_config.NumberColumn(format="localized")
PCT = st.column_config.NumberColumn(format="percent")


@st.cache_data(show_spinner="Cargando grupos...")
def load_clusters(mtime):
    # mtime en la llave: si se vuelve a correr el script, el caché se renueva.
    config = json.loads((REPORT / "clustering_config.json").read_text(encoding="utf-8"))
    k_sel = pd.read_csv(REPORT / "01_k_selection.csv")
    return pd.read_parquet(CLUSTERS_PATH), config, k_sel


def pooled(df, years):
    rows = []
    for y in years:
        sv, nv = df[f"SV_{y}"].sum(), df[f"NV_{y}"].sum()
        rows.append({"AELEC": y, "abstencion": nv / (sv + nv) if sv + nv else None})
    return pd.DataFrame(rows)


def hex_rgba(h, alpha=220):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)] + [alpha]


def group_frame(df, color):
    out = df.copy()
    out["FILL_COLOR"] = [hex_rgba(color)] * len(out)
    out["TRAY_TXT"] = out[[f"ABST_{y}" for y in YEARS]].apply(
        lambda r: " · ".join(f"{y}: {v * 100:.0f}%" for y, v in zip(YEARS, r)), axis=1
    )
    for col, name in [("nivel_intermedia", "INT_TXT"), ("nivel_presidencial", "PRE_TXT"), ("tendencia", "TEND_TXT")]:
        out[name] = out[col].map(lambda v: f"{v:+.1f} pp")
    return out


TOOLTIP_COLS = ["SECTION_KEY", "MPIONOM", "GRUPO_NOMBRE", "TRAY_TXT", "INT_TXT", "PRE_TXT", "TEND_TXT", "FILL_COLOR"]


def group_point_layer(df):
    return pdk.Layer(
        "ScatterplotLayer",
        data=df[["_LON", "_LAT"] + TOOLTIP_COLS],
        get_position="[_LON, _LAT]",
        get_fill_color="FILL_COLOR",
        radius_min_pixels=1.7,
        radius_max_pixels=7,
        get_radius=1800,
        pickable=True,
        auto_highlight=True,
    )


def group_polygon_layer(df):
    return pdk.Layer(
        "GeoJsonLayer",
        data=df[["geometry"] + TOOLTIP_COLS].__geo_interface__,
        stroked=True,
        filled=True,
        get_fill_color="properties.FILL_COLOR",
        get_line_color=[255, 255, 255, 135],
        line_width_min_pixels=0.6,
        pickable=True,
        auto_highlight=True,
    )


st.title("Grupos de secciones")
st.caption(
    "Fase 1, descriptiva. Las secciones se agrupan por cómo se comportan frente "
    "al promedio nacional de cada elección 2009–2024 (nivel en intermedias y en "
    "presidenciales, tendencia y volatilidad). El contexto (urbana/rural, tamaño, "
    "edad) sólo describe los grupos."
)

if not CLUSTERS_PATH.exists():
    st.info(
        "Todavía no hay grupos. Genéralos con "
        "`python src/clustering/01_build_section_clusters.py` "
        "(requiere la base maestra de `src/02_build_master.py`)."
    )
    st.stop()

sections, config, k_sel = load_clusters(CLUSTERS_PATH.stat().st_mtime)
mode = "dark" if st.context.theme.type == "dark" else "light"
names = sections.drop_duplicates("GRUPO").sort_values("GRUPO")["GRUPO_NOMBRE"].tolist()
colors = dict(zip(names, GROUP_COLORS[mode]))
map_colors = dict(zip(names, GROUP_COLORS["light"]))  # el mapa siempre usa fondo claro

states = (
    sections.drop_duplicates("EDOCVE").set_index("EDOCVE")["EDONOM"].sort_values()
)
f1, f2, _ = st.columns([1, 1.4, 1.6])
choice = f1.selectbox("Entidad", ["Nacional"] + states.tolist())
election_type = f2.radio("Tipo de elección", list(ELECTION_TYPES), horizontal=True)
edocve = None if choice == "Nacional" else states.index[states.eq(choice)][0]
scope = sections if edocve is None else sections.loc[sections["EDOCVE"].eq(edocve)]

base = load_base()
large_shapes = load_large_shapes()
base_scope = None
if base is not None:
    base_scope = base if edocve is None else base.loc[base["CARTO_EDOCVE"].eq(edocve)]

k1, k2, k3 = st.columns(3)
k1.metric("Secciones agrupadas", f"{len(scope):,}")
if base_scope is not None and len(base_scope):
    k2.metric(
        "Del total de secciones",
        f"{base_scope['SECTION_KEY'].isin(scope['SECTION_KEY']).mean():.1%}",
        help=(
            "Sólo se agrupan secciones con abstención calculable en las 6 "
            f"elecciones y NS ≤ {config['max_ns']:.0%} en todas."
        ),
    )
k3.metric(
    "Separación entre grupos (silhouette)",
    f"{config['silhouette_k']:.2f}",
    help=(
        "De −1 a 1. Alrededor de 0.25 indica estructura moderada: los grupos "
        "son una tipología útil, pero con fronteras difusas."
    ),
)

# ---------------------------------------------------------------- Perfiles
st.subheader("Perfil de los grupos")
profile = (
    scope.groupby(["GRUPO", "GRUPO_NOMBRE"])
    .agg(
        Secciones=("SECTION_KEY", "size"),
        intermedias=("nivel_intermedia", "mean"),
        presidenciales=("nivel_presidencial", "mean"),
        tendencia=("tendencia", "mean"),
        volatilidad=("volatilidad", "mean"),
        urbana=("TIPOSEC", lambda t: t.eq("U").mean()),
        rural=("TIPOSEC", lambda t: t.eq("R").mean()),
        ln=("LN", "median"),
        jovenes=("PROP_LN_18_24", "mean"),
    )
    .reset_index()
)
profile.insert(3, "% de las secciones", profile["Secciones"] / profile["Secciones"].sum())
st.caption(
    "Nivel, tendencia y volatilidad en puntos porcentuales frente a la abstención "
    "nacional de cada elección (negativo = votan más que el promedio). Tendencia = "
    "promedio 2021–2024 menos promedio 2009–2012."
)
st.dataframe(
    profile.drop(columns="GRUPO").rename(columns={
        "GRUPO_NOMBRE": "Grupo",
        "intermedias": "Intermedias (pp)",
        "presidenciales": "Presidenciales (pp)",
        "tendencia": "Tendencia (pp)",
        "volatilidad": "Volatilidad (pp)",
        "urbana": "% urbana",
        "rural": "% rural",
        "ln": "Lista nominal mediana 2024",
        "jovenes": "% 18–24 años",
    }),
    hide_index=True,
    width="stretch",
    column_config={
        "Secciones": COUNT,
        "% de las secciones": PCT,
        "Intermedias (pp)": st.column_config.NumberColumn(format="%+.1f"),
        "Presidenciales (pp)": st.column_config.NumberColumn(format="%+.1f"),
        "Tendencia (pp)": st.column_config.NumberColumn(format="%+.1f"),
        "Volatilidad (pp)": st.column_config.NumberColumn(format="%.1f"),
        "% urbana": PCT,
        "% rural": PCT,
        "Lista nominal mediana 2024": COUNT,
        "% 18–24 años": PCT,
    },
)

# ---------------------------------------------------------------- Trayectorias
st.subheader("Abstención de cada grupo en el tiempo")
years = ELECTION_TYPES[election_type]
traj = pd.concat(
    [pooled(g, years).assign(grupo=name) for name, g in scope.groupby("GRUPO_NOMBRE")]
    + [pooled(scope, years).assign(grupo="Todas las secciones agrupadas")],
    ignore_index=True,
)
traj["tipo"] = traj["AELEC"].map(lambda y: "intermedia" if y in ELECTION_TYPES["Intermedias"] else "presidencial")
st.caption(
    "Abstención agregada (no votaron / votaron + no votaron) de las secciones de "
    "cada grupo. La línea punteada es el total de las secciones agrupadas del "
    "territorio elegido."
    + (" Con \"Todas\" la línea alterna entre intermedias (más abstención) y "
       "presidenciales." if election_type == "Todas" else "")
)
x = alt.X("AELEC:O", title=None, axis=alt.Axis(labelAngle=0))
y = alt.Y("abstencion:Q", title=None, axis=alt.Axis(format="%"), scale=alt.Scale(zero=True))
tooltip = [
    alt.Tooltip("grupo:N", title="Grupo"),
    alt.Tooltip("AELEC:O", title="Año"),
    alt.Tooltip("tipo:N", title="Elección"),
    alt.Tooltip("abstencion:Q", title="Abstención", format=".1%"),
]
groups_only = traj.loc[traj["grupo"].isin(names)]
lines = alt.Chart(groups_only).encode(
    x=x, y=y, tooltip=tooltip,
    color=alt.Color(
        "grupo:N", title=None,
        scale=alt.Scale(domain=names, range=[colors[n] for n in names]),
        legend=alt.Legend(orient="top", columns=3, labelLimit=260),
    ),
)
reference = alt.Chart(traj.loc[~traj["grupo"].isin(names)]).encode(x=x, y=y, tooltip=tooltip)
st.altair_chart(
    (
        reference.mark_line(color=REFERENCE_COLOR[mode], strokeDash=[4, 4], strokeWidth=2)
        + lines.mark_line(strokeWidth=2)
        + lines.mark_point(filled=True, opacity=1, size=80, stroke=SURFACE[mode], strokeWidth=2)
    ).properties(height=340),
    width="stretch",
)

# ---------------------------------------------------------------- Mapa
st.subheader("Dónde está cada grupo")
m1, m2, _ = st.columns([2, 1.4, 1.6])
selected = m1.selectbox(
    "Grupo en el mapa",
    names,
    index=names.index("Abstención alta persistente") if "Abstención alta persistente" in names else 0,
    help=(
        "Se muestra un grupo a la vez: con los 5 colores juntos, algunos pares "
        "no se distinguen bien en un mapa."
    ),
)
national_view = m2.radio(
    "Vista nacional",
    NATIONAL_VIEWS,
    horizontal=True,
    disabled=edocve is not None or large_shapes is None,
    help=NATIONAL_VIEW_HELP,
)

if base_scope is None:
    st.warning(
        "Falta data/processed/spatial_2027/cartography_base_2027.parquet. "
        "Ejecuta src/15_build_spatial_layer.py"
    )
else:
    view_mode = map_mode(edocve is None, national_view, large_shapes)
    chosen = scope.loc[scope["GRUPO_NOMBRE"].eq(selected)]
    chosen_map = group_frame(base_scope.merge(chosen, on="SECTION_KEY"), map_colors[selected])
    others = base_scope.loc[~base_scope["SECTION_KEY"].isin(chosen_map["SECTION_KEY"])]
    st.markdown(
        f"""
        <div style="display:flex;flex-wrap:wrap;gap:18px;align-items:center;margin-bottom:8px;">
          <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{map_colors[selected]};vertical-align:-1px;"></span> {selected} ({len(chosen_map):,} secciones)</span>
          <span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb(189,189,189);vertical-align:-1px;"></span> Otros grupos o sin grupo</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    base_polys, base_points = split_layers(
        others, view_mode, large_shapes,
        lambda d: make_base_layer(d, True),
        lambda d: make_base_layer(d, False),
    )
    group_polys, group_points = split_layers(
        chosen_map, view_mode, large_shapes, group_point_layer, group_polygon_layer
    )
    st.pydeck_chart(
        CompactDeck(
            layers=base_polys + group_polys + base_points + group_points,
            initial_view_state=view_state_from_bounds(base_scope),
            tooltip={
                "html": """
                <b>Sección:</b> {SECTION_KEY}<br/>
                <b>Municipio:</b> {MPIONOM}<br/>
                <b>Grupo:</b> {GRUPO_NOMBRE}<br/>
                <b>Abstención:</b> {TRAY_TXT}<br/>
                <b>Frente al promedio nacional:</b> intermedias {INT_TXT} · presidenciales {PRE_TXT}<br/>
                <b>Tendencia:</b> {TEND_TXT}
                """,
                "style": {"backgroundColor": "rgba(20,20,20,0.93)", "color": "white"},
            },
            map_style="light",
        ),
        width="stretch",
    )

# ---------------------------------------------------------------- Composición
unit, unit_label = ("EDONOM", "Estado") if edocve is None else ("MPIONOM", "Municipio")
st.subheader(f"Composición por {unit_label.lower()}")
comp = scope.groupby([unit, "GRUPO_NOMBRE"]).size().rename("secciones").reset_index()
comp["pct"] = comp["secciones"] / comp.groupby(unit)["secciones"].transform("sum")
totals = comp.groupby(unit)["secciones"].sum()
if edocve is not None:
    keep = totals.sort_values(ascending=False).head(30).index
    comp = comp.loc[comp[unit].isin(keep)]
    st.caption("Los 30 municipios con más secciones agrupadas.")
sort_order = (
    comp.loc[comp["GRUPO_NOMBRE"].eq(selected)]
    .sort_values("pct", ascending=False)[unit]
    .tolist()
)
sort_order += [u for u in comp[unit].unique() if u not in sort_order]
st.caption(f"Ordenado por la proporción de \"{selected}\" (el grupo elegido para el mapa).")
st.altair_chart(
    alt.Chart(comp.assign(orden=comp["GRUPO_NOMBRE"].map({n: i for i, n in enumerate(names)})))
    .mark_bar(stroke=SURFACE[mode], strokeWidth=2)
    .encode(
        y=alt.Y(f"{unit}:N", title=None, sort=sort_order, axis=alt.Axis(labelLimit=220)),
        x=alt.X("pct:Q", title=None, axis=alt.Axis(format="%"), stack="normalize"),
        color=alt.Color(
            "GRUPO_NOMBRE:N", title=None,
            scale=alt.Scale(domain=names, range=[colors[n] for n in names]),
            legend=alt.Legend(orient="top", columns=3, labelLimit=260),
        ),
        order=alt.Order("orden:Q"),
        tooltip=[
            alt.Tooltip(f"{unit}:N", title=unit_label),
            alt.Tooltip("GRUPO_NOMBRE:N", title="Grupo"),
            alt.Tooltip("secciones:Q", title="Secciones", format=","),
            alt.Tooltip("pct:Q", title="Proporción", format=".1%"),
        ],
    )
    # Altura por barra (no total) para que no se oculten etiquetas.
    .properties(height=alt.Step(24)),
    width="stretch",
)
with st.expander("Ver como tabla"):
    table = comp.pivot(index=unit, columns="GRUPO_NOMBRE", values="pct").reindex(columns=names).fillna(0)
    table.insert(0, "Secciones", totals.reindex(table.index))
    st.dataframe(
        table.loc[sort_order].reset_index().rename(columns={unit: unit_label}),
        hide_index=True,
        width="stretch",
        column_config={"Secciones": COUNT, **{n: PCT for n in names}},
    )

with st.expander("Cómo se formaron los grupos y limitaciones"):
    st.markdown(
        f"""
        - **Universo:** {config['sections_clustered']:,} secciones con abstención
          calculable en las 6 elecciones y NS ≤ {config['max_ns']:.0%} en todas.
          Las secciones nuevas o renumeradas no tienen grupo.
        - **Variables** (pp frente a la abstención nacional de cada elección):
          nivel en intermedias, nivel en presidenciales, tendencia (2021–2024 vs.
          2009–2012) y volatilidad. Se estandarizan y se agrupan con k-means
          (k = {config['k']}).
        - **Nombres:** reglas sobre el promedio de cada grupo: tendencia mayor a
          ±{config['naming_rules_pp']['trend']:.0f} pp → Mejorando / Empeorando; si no,
          nivel mayor a ±{config['naming_rules_pp']['level']:.0f} pp → alta / baja
          persistente; si no, En el promedio.
        - **Separación:** silhouette {config['silhouette_k']:.2f}. Las secciones forman
          un continuo; los grupos son una tipología con fronteras difusas.
        - **Uso:** descriptivo. Para usar los grupos en el modelo hay que
          reconstruirlos sólo con elecciones anteriores a la que se predice.
        - Detalle completo en `reports/clustering/CLUSTER_METHOD.md`.
        """
    )
    st.dataframe(
        k_sel.rename(columns={"k": "k (grupos)", "silhouette": "Silhouette", "tamaños": "Tamaños"}),
        hide_index=True,
    )
