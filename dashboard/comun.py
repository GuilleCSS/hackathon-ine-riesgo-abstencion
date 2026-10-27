from pathlib import Path
import json
import math

import geopandas as gpd
import pandas as pd
import pydeck as pdk
from pydeck.bindings.json_tools import default_serialize
import streamlit as st


# Piezas de mapa compartidas por las páginas del dashboard. Viven aquí para que
# la cartografía base se cargue una sola vez en el caché de Streamlit.

ROOT = Path(__file__).resolve().parents[1]

BASE_PATH = (
    ROOT / "data" / "processed" / "spatial_2027"
    / "cartography_base_2027.parquet"
)

BASE_COLOR = [189, 189, 189, 150]

# Vista nacional híbrida: las secciones de más de 100 km² (5% de las secciones,
# ~69% del territorio) se dibujan como polígono con el contorno simplificado a
# 500 m (~6 MB en el navegador); las demás, como punto.
HYBRID_MIN_KM2 = 100
HYBRID_TOLERANCE_M = 500

NATIONAL_VIEWS = ["Híbrida", "Puntos"]
NATIONAL_VIEW_HELP = (
    f"Híbrida: las secciones de más de {HYBRID_MIN_KM2} km² se dibujan como "
    "polígono (contorno simplificado) y las demás como punto, para que las "
    "zonas poco pobladas no se vean vacías. Puntos: un punto por sección. "
    "Al elegir una entidad siempre se ven los polígonos detallados."
)


class CompactDeck(pdk.Deck):
    # pydeck serializa con indent=2 y Streamlit lo manda tal cual al navegador;
    # en coordenadas anidadas eso multiplica el tamaño. Mismo JSON, sin espacios.
    def to_json(self):
        return json.dumps(
            self,
            sort_keys=True,
            default=default_serialize,
            separators=(",", ":"),
        )


def add_representative_points(gdf):
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


@st.cache_data(show_spinner="Cargando cartografía base...")
def load_base():
    # Opcional: salidas de 15_build_spatial_layer.py anteriores a la capa
    # base no la incluyen; el mapa funciona igual sin ella.
    if not BASE_PATH.exists():
        return None

    return add_representative_points(gpd.read_parquet(BASE_PATH))


@st.cache_data(show_spinner="Preparando secciones grandes...")
def load_large_shapes():
    base = load_base()
    if base is None:
        return None

    projected = base[["SECTION_KEY", "geometry"]].to_crs(epsg=6372)
    large = projected.loc[projected.area > HYBRID_MIN_KM2 * 1e6].copy()
    large["geometry"] = large.geometry.simplify(
        HYBRID_TOLERANCE_M,
        preserve_topology=True,
    )
    large = large.to_crs(epsg=4326)
    # Con 4 decimales (~11 m) alcanza a escala nacional y el JSON pesa menos.
    large["geometry"] = large.geometry.set_precision(1e-4)
    return large


def map_mode(national, national_view, large_shapes):
    if not national:
        return "poligonos"
    if national_view == "Híbrida" and large_shapes is not None:
        return "hibrida"
    return "puntos"


def split_layers(df, mode, large_shapes, point_layer, polygon_layer):
    # Devuelve (capas de polígonos, capas de puntos) para dibujar todos los
    # polígonos debajo de todos los puntos.
    if mode == "poligonos":
        return [polygon_layer(df)], []
    if mode == "puntos":
        return [], [point_layer(df)]

    is_large = df["SECTION_KEY"].isin(large_shapes["SECTION_KEY"])
    props = pd.DataFrame(df.loc[is_large]).drop(columns="geometry", errors="ignore")
    polygons = large_shapes.merge(props, on="SECTION_KEY")
    points = df.loc[~is_large]
    return (
        [polygon_layer(polygons)] if len(polygons) else [],
        [point_layer(points)] if len(points) else [],
    )


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


def make_base_layer(base, as_points, color=BASE_COLOR):
    # Contexto gris debajo de la capa de datos: sólo geometría, sin tooltip.
    if as_points:
        return pdk.Layer(
            "ScatterplotLayer",
            data=base[["_LON", "_LAT"]],
            get_position="[_LON, _LAT]",
            get_fill_color=color,
            radius_min_pixels=1.7,
            radius_max_pixels=7,
            get_radius=1800,
        )

    return pdk.Layer(
        "GeoJsonLayer",
        data=base[["geometry"]].__geo_interface__,
        stroked=True,
        filled=True,
        get_fill_color=color,
        get_line_color=[255, 255, 255, 135],
        line_width_min_pixels=0.6,
    )
