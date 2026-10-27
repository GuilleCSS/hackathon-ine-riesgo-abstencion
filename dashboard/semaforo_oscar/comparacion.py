from pathlib import Path
import json

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
COMPARISON_PATH = ROOT / "data" / "processed" / "semaforo_oscar" / "comparacion_secciones.parquet"
REPORT = ROOT / "reports" / "semaforo_oscar"

LEVELS = ["BAJO", "MEDIO", "ALTO"]
# Mismos colores que el semáforo del mapa de riesgo.
RISK_COLORS = {"BAJO": [46, 125, 50, 175], "MEDIO": [251, 192, 45, 190], "ALTO": [198, 40, 40, 200]}
# Se distinguen entre sí en el mapa, también con daltonismo.
DIFF_COLORS = {
    "coincide": ("#8f8f8c", "Mismo nivel"),
    "oscar_mas_alto": ("#a82a29", "Oscar más alto"),
    "oscar_mas_bajo": ("#184f95", "Oscar más bajo"),
    "solo_oscar": ("#eda100", "Sólo en el de Oscar"),
    "solo_oficial": ("#eda100", "Sólo en el oficial"),
}
OUTSIDE_COLOR = [220, 220, 218, 170]
MODES = ["Diferencias", "Semáforo oficial", "Semáforo de Oscar"]
COUNT = st.column_config.NumberColumn(format="localized")
PCT = st.column_config.NumberColumn(format="percent")


@st.cache_data(show_spinner="Cargando comparación...")
def load_comparison(mtime):
    config = json.loads((REPORT / "comparacion_config.json").read_text(encoding="utf-8"))
    return pd.read_parquet(COMPARISON_PATH), config


def hex_rgba(h, alpha=215):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)] + [alpha]


def pct_txt(v):
    return "—" if pd.isna(v) else f"{v * 100:.1f}%"


def map_frame(df, mode):
    out = df.copy()
    if mode == "Diferencias":
        out["FILL_COLOR"] = out["COMPARACION"].map(lambda c: hex_rgba(DIFF_COLORS.get(c, ("#8f8f8c", ""))[0]))
    else:
        level = out["NIVEL_OFICIAL" if mode == "Semáforo oficial" else "NIVEL_OSCAR"]
        out = out.loc[level.notna()]
        out["FILL_COLOR"] = out[level.name].map(RISK_COLORS)
    out["OFICIAL_TXT"] = out["NIVEL_OFICIAL"].fillna("fuera del universo") + " · " + out["PRED_OFICIAL"].map(pct_txt)
    out["OSCAR_TXT"] = out["NIVEL_OSCAR"].fillna("fuera del universo") + " · " + out["PRED_OSCAR"].map(pct_txt)
    out["DIF_TXT"] = out["DIF_PP"].map(lambda v: "—" if pd.isna(v) else f"{v:+.1f} pp")
    out["COMP_TXT"] = out["COMPARACION"].map(lambda c: DIFF_COLORS.get(c, ("", c))[1])
    return out


TOOLTIP_COLS = ["SECTION_KEY", "ESTADO", "MUNICIPIO", "OFICIAL_TXT", "OSCAR_TXT", "DIF_TXT",
                "COMP_TXT", "QUALITY_FLAG", "FILL_COLOR"]


def point_layer(df):
    return pdk.Layer(
        "ScatterplotLayer", data=df[["_LON", "_LAT"] + TOOLTIP_COLS],
        get_position="[_LON, _LAT]", get_fill_color="FILL_COLOR",
        radius_min_pixels=1.7, radius_max_pixels=7, get_radius=1800,
        pickable=True, auto_highlight=True,
    )


def polygon_layer(df):
    return pdk.Layer(
        "GeoJsonLayer", data=df[["geometry"] + TOOLTIP_COLS].__geo_interface__,
        stroked=True, filled=True, get_fill_color="properties.FILL_COLOR",
        get_line_color=[255, 255, 255, 135], line_width_min_pixels=0.6,
        pickable=True, auto_highlight=True,
    )


def swatch(color, label):
    return (f'<span><span style="display:inline-block;width:12px;height:12px;border-radius:50%;'
            f'background:{color};vertical-align:-1px;"></span> {label}</span>')


st.title("Semáforo alternativo (Oscar)")
st.caption(
    "Compara el semáforo 2027 oficial con el de Oscar (`st_gcn_participation/`). "
    "Ninguno se modifica: se cruzan sección por sección para ver dónde y por qué difieren."
)

if not COMPARISON_PATH.exists():
    st.info(
        "Todavía no hay comparación. Genera los datos de Oscar y compáralos con:\n\n"
        "`python src/semaforo_oscar/01_generar_csv_oscar.py` → los tres scripts de "
        "`st_gcn_participation/` con `OSCAR_DATA_DIR=data/interim/oscar_tableau` → "
        "`python src/semaforo_oscar/02_comparar_semaforos.py`."
    )
    st.stop()

data, config = load_comparison(COMPARISON_PATH.stat().st_mtime)

with st.expander("Qué diferencia a los dos semáforos", expanded=True):
    to, tc = config["umbrales_oficial"], config["umbrales_oscar"]
    st.dataframe(
        pd.DataFrame({
            "": ["Estimación 2027", "Universo", "Secciones", "BAJO hasta", "MEDIO hasta", "Top10 desde"],
            "Oficial": ["Regresión de dos historias (2021 y 2024)", "NS ≤ 10%, sin cambios de municipio ni tipo",
                        f"{int(data['PRED_OFICIAL'].notna().sum()):,}", f"{to['q50']:.1%}", f"{to['q80']:.1%}", f"{to['q90']:.1%}"],
            "Oscar": ["Persistencia: abstención 2021", "Todas las secciones con historia comparable",
                      f"{int(data['PRED_OSCAR'].notna().sum()):,}", f"{tc['q50']:.1%}", f"{tc['q80']:.1%}", f"{tc['q90']:.1%}"],
        }),
        hide_index=True, width="stretch",
    )
    st.caption(
        "Los dos usan la misma regla relativa: BAJO hasta el percentil 50, MEDIO hasta el 80, "
        "ALTO arriba y Top10 desde el 90, cada uno sobre su propio universo. Error medio en "
        "backtests, regresión vs. persistencia: 2021, 7.69 vs. 9.91 pp; 2024, 4.36 vs. 4.72 pp; "
        "2018, 11.35 vs. 4.77 pp (ahí la regresión sólo pudo entrenarse con una intermedia)."
    )

states = data.dropna(subset=["ESTADO"]).drop_duplicates("EDOCVE").set_index("EDOCVE")["ESTADO"].sort_values()
f1, f2, f3 = st.columns([1, 1.6, 1.4])
choice = f1.selectbox("Entidad", ["Nacional"] + states.tolist())
mode = f2.radio("Mostrar en el mapa", MODES, horizontal=True)
edocve = None if choice == "Nacional" else states.index[states.eq(choice)][0]
scope = data if edocve is None else data.loc[data["EDOCVE"].eq(edocve)]
both = scope.loc[scope["COMPARACION"].isin(["coincide", "oscar_mas_alto", "oscar_mas_bajo"])]

base = load_base()
large_shapes = load_large_shapes()
national_view = f3.radio(
    "Vista nacional", NATIONAL_VIEWS, horizontal=True,
    disabled=edocve is not None or large_shapes is None, help=NATIONAL_VIEW_HELP,
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Secciones en ambos", f"{len(both):,}")
k2.metric(
    "Mismo nivel", f"{both['COMPARACION'].eq('coincide').mean():.1%}" if len(both) else "—",
    help=f"Nacional: si los niveles fueran independientes coincidirían {config['coincidencia_esperada_al_azar']:.1%}.",
)
k3.metric("Oscar − oficial", f"{both['DIF_PP'].mean():+.1f} pp" if len(both) else "—",
          help="Diferencia media de la abstención estimada 2027.")
k4.metric("Sólo en el de Oscar", f"{int(scope['COMPARACION'].eq('solo_oscar').sum()):,}",
          help="Secciones que el oficial excluye por sus filtros de calidad (ver motivos abajo).")

st.subheader("Mapa")
if mode == "Diferencias":
    present = [c for c in DIFF_COLORS if scope["COMPARACION"].eq(c).any()]
    legend = "".join(swatch(*DIFF_COLORS[c]) for c in present)
else:
    legend = "".join(swatch(f"rgb({c[0]},{c[1]},{c[2]})", lvl.capitalize()) for lvl, c in RISK_COLORS.items())
legend += swatch("rgb(220,220,218)", "Fuera de este semáforo")
st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:18px;align-items:center;margin-bottom:8px;">{legend}</div>',
            unsafe_allow_html=True)

if base is None:
    st.warning("Falta data/processed/spatial_2027/cartography_base_2027.parquet. Ejecuta src/15_build_spatial_layer.py")
else:
    base_scope = base if edocve is None else base.loc[base["CARTO_EDOCVE"].eq(edocve)]
    view_mode = map_mode(edocve is None, national_view, large_shapes)
    shown = map_frame(base_scope.merge(scope, on="SECTION_KEY"), mode)
    others = base_scope.loc[~base_scope["SECTION_KEY"].isin(shown["SECTION_KEY"])]
    bp, bpt = split_layers(others, view_mode, large_shapes,
                           lambda d: make_base_layer(d, True, OUTSIDE_COLOR),
                           lambda d: make_base_layer(d, False, OUTSIDE_COLOR))
    sp, spt = split_layers(shown, view_mode, large_shapes, point_layer, polygon_layer)
    st.pydeck_chart(
        CompactDeck(
            layers=bp + sp + bpt + spt,
            initial_view_state=view_state_from_bounds(base_scope),
            tooltip={
                "html": """
                <b>Sección:</b> {SECTION_KEY}<br/>
                <b>Entidad:</b> {ESTADO} · <b>Municipio:</b> {MUNICIPIO}<br/>
                <b>Oficial:</b> {OFICIAL_TXT}<br/>
                <b>Oscar:</b> {OSCAR_TXT}<br/>
                <b>Oscar − oficial:</b> {DIF_TXT} · <b>Nivel:</b> {COMP_TXT}<br/>
                <b>Calidad (oficial):</b> {QUALITY_FLAG}
                """,
                "style": {"backgroundColor": "rgba(20,20,20,0.93)", "color": "white"},
            },
            map_style="light",
        ),
        width="stretch",
    )

left, right = st.columns(2)
with left:
    st.subheader("Niveles: oficial (filas) vs. Oscar (columnas)")
    if len(both):
        matrix = pd.crosstab(both["NIVEL_OFICIAL"], both["NIVEL_OSCAR"]).reindex(index=LEVELS, columns=LEVELS, fill_value=0)
        share = matrix.div(matrix.sum(axis=1), axis=0)
        st.dataframe(
            matrix.rename_axis("Oficial").reset_index(),
            hide_index=True, width="stretch",
            column_config={lvl: COUNT for lvl in LEVELS},
        )
        st.caption("Proporción por fila (de cada nivel oficial, qué nivel le da Oscar):")
        st.dataframe(share.rename_axis("Oficial").reset_index(), hide_index=True, width="stretch",
                     column_config={lvl: PCT for lvl in LEVELS})
with right:
    st.subheader("Por qué hay secciones sólo en el de Oscar")
    motives = scope.loc[scope["COMPARACION"].eq("solo_oscar"), "QUALITY_FLAG"].value_counts()
    names = {
        "comparable_high_ns": "NS > 10% en 2021 o 2024",
        "insufficient_inputs": "Sin abstención calculable (100% NS)",
        "valid_inputs_low_comparability": "Cambió de municipio o tipo",
        "sin_dato_comparable": "No está en 2021 y 2024 a la vez",
    }
    st.dataframe(
        motives.rename(index=lambda k: names.get(k, k)).rename_axis("Motivo").rename("Secciones").reset_index(),
        hide_index=True, width="stretch", column_config={"Secciones": COUNT},
    )

unit, unit_label = ("ESTADO", "Estado") if edocve is None else ("MUNICIPIO", "Municipio")
st.subheader(f"Coincidencia por {unit_label.lower()}")
table = (
    both.groupby(unit)
    .agg(
        secciones=("SECTION_KEY", "size"),
        mismo_nivel=("COMPARACION", lambda c: c.eq("coincide").mean()),
        oscar_mas_alto=("COMPARACION", lambda c: c.eq("oscar_mas_alto").mean()),
        oscar_mas_bajo=("COMPARACION", lambda c: c.eq("oscar_mas_bajo").mean()),
        dif_pp=("DIF_PP", "mean"),
        alto_oficial=("NIVEL_OFICIAL", lambda n: int(n.eq("ALTO").sum())),
        alto_oscar=("NIVEL_OSCAR", lambda n: int(n.eq("ALTO").sum())),
    )
    .reset_index()
    .sort_values("mismo_nivel")
)
st.caption("Ordenado de menor a mayor coincidencia.")
st.dataframe(
    table.rename(columns={unit: unit_label, "secciones": "Secciones en ambos", "mismo_nivel": "Mismo nivel",
                          "oscar_mas_alto": "Oscar más alto", "oscar_mas_bajo": "Oscar más bajo",
                          "dif_pp": "Oscar − oficial (pp)", "alto_oficial": "ALTO oficial", "alto_oscar": "ALTO Oscar"}),
    hide_index=True, width="stretch",
    column_config={"Secciones en ambos": COUNT, "Mismo nivel": PCT, "Oscar más alto": PCT, "Oscar más bajo": PCT,
                   "Oscar − oficial (pp)": st.column_config.NumberColumn(format="%+.1f"),
                   "ALTO oficial": COUNT, "ALTO Oscar": COUNT},
)
st.caption("Detalle y método: `reports/semaforo_oscar/COMPARACION.md` y `REPLICA.md`.")
