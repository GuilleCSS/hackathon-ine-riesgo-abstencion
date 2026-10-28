from pathlib import Path
import json
import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]

CARTO_DIR = ROOT / "data" / "raw" / "cartography_2027"
EXTRACT_DIR = ROOT / "data" / "interim" / "cartography_extract"

RISK_PATH = (
    ROOT / "data" / "processed" / "sensitivity_2027"
    / "section_sensitivity_2027.parquet"
)

OUT_DATA = ROOT / "data" / "processed" / "spatial_2027"
OUT_REPORT = ROOT / "reports" / "spatial_2027"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)

ENTITY_ALIASES = [
    "EDOCVE", "CVE_ENT", "CVEENT", "ENTIDAD", "ENTIDAD_ID",
    "ENT", "ID_ENT", "ID_ENTIDAD", "ENTIDAD_CVE",
]

SECTION_ALIASES = [
    "SECCION", "SECC", "SECCION_ID", "ID_SECCION",
    "CVE_SECC", "CVE_SECCION", "SECCION_CVE",
]

MUNICIPALITY_ALIASES = [
    "MPIOCVE", "MUNICIPIO", "CVE_MUN", "CVEMUN", "CVE_MPIO",
    "MPIO", "ID_MUN", "ID_MPIO", "MUNICIPIO_ID",
]

TYPE_ALIASES = [
    "TIPOSEC", "TIPO", "TIPO_SEC", "TIPOSECC", "TIPO_SECCION",
]

# Mapeo observado en la auditoría 14B.
TYPE_CODE_MAP = {
    "2": "U",
    "3": "M",
    "4": "R",
}


def upper_map(columns):
    return {str(c).strip().upper(): c for c in columns}


def detect_column(columns, aliases, required=True):
    mapping = upper_map(columns)
    for alias in aliases:
        if alias.upper() in mapping:
            return mapping[alias.upper()]

    if required:
        raise RuntimeError(
            f"No se encontró columna requerida. Aliases={aliases}; "
            f"columnas={list(columns)}"
        )
    return None


def as_int_series(s):
    return pd.to_numeric(s, errors="coerce").astype("Int64")


def make_key(entity, section):
    ent = as_int_series(entity)
    sec = as_int_series(section)
    return (
        ent.astype("string").str.zfill(2)
        + "-"
        + sec.astype("string").str.zfill(4)
    )


def extract_zip_find_shapefile(zip_path):
    extract_root = EXTRACT_DIR / zip_path.stem
    extract_root.mkdir(parents=True, exist_ok=True)

    marker = extract_root / ".extracted_ok"

    if not marker.exists():
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_root)
        marker.write_text("ok", encoding="utf-8")

    shp_files = sorted(extract_root.rglob("*.shp"))
    if not shp_files:
        raise RuntimeError(f"No se encontró .shp dentro de {zip_path.name}")

    # Preferir nombres seccionales si hay múltiples.
    preferred = [
        p for p in shp_files
        if any(tok in p.stem.lower() for tok in ["secc", "seccion", "mgs"])
    ]
    if preferred:
        shp_files = preferred

    if len(shp_files) > 1:
        print(
            f"[aviso] {zip_path.name}: {len(shp_files)} SHP; "
            f"se usará {shp_files[0].name}"
        )

    return shp_files[0]


def read_state_layer(zip_path):
    shp = extract_zip_find_shapefile(zip_path)
    geo = gpd.read_file(shp, engine="pyogrio")

    entity_col = detect_column(geo.columns, ENTITY_ALIASES)
    section_col = detect_column(geo.columns, SECTION_ALIASES)
    municipality_col = detect_column(
        geo.columns, MUNICIPALITY_ALIASES, required=False
    )
    type_col = detect_column(
        geo.columns, TYPE_ALIASES, required=False
    )

    keep = gpd.GeoDataFrame(
        geometry=geo.geometry,
        crs=geo.crs,
    )

    keep["CARTO_EDOCVE"] = as_int_series(geo[entity_col])
    keep["CARTO_SECCION"] = as_int_series(geo[section_col])
    keep["SECTION_KEY"] = make_key(
        keep["CARTO_EDOCVE"],
        keep["CARTO_SECCION"],
    )

    if municipality_col is not None:
        keep["CARTO_MPIOCVE"] = as_int_series(geo[municipality_col])
    else:
        keep["CARTO_MPIOCVE"] = pd.array(
            [pd.NA] * len(keep), dtype="Int64"
        )

    if type_col is not None:
        raw_type = (
            geo[type_col].astype("string").str.strip().str.upper()
        )
        keep["CARTO_TIPOSEC_RAW"] = raw_type
        keep["CARTO_TIPOSEC_STD"] = (
            raw_type.map(TYPE_CODE_MAP).fillna(raw_type)
        )
    else:
        keep["CARTO_TIPOSEC_RAW"] = pd.NA
        keep["CARTO_TIPOSEC_STD"] = pd.NA

    keep["SOURCE_FILE"] = zip_path.name

    if keep.crs is None:
        raise RuntimeError(
            f"{zip_path.name} no tiene CRS definido; no se puede reproyectar de forma segura."
        )

    # Dashboard / GeoJSON necesita un CRS común.
    keep = keep.to_crs(epsg=4326)

    return keep


def geometry_audit(gdf):
    geom = gdf.geometry
    return {
        "rows": len(gdf),
        "null_geometry": int(geom.isna().sum()),
        "empty_geometry": int(geom.is_empty.sum()),
        "invalid_geometry": int((~geom.is_valid).sum()),
        "geometry_types": (
            geom.geom_type.value_counts(dropna=False).to_dict()
        ),
    }


def main():
    print("\n=== 15 · Construcción de capa espacial provisional ===")

    if not RISK_PATH.exists():
        raise FileNotFoundError(
            f"No existe {RISK_PATH}. Ejecuta primero src/13_sensitivity_prioritization.py"
        )

    zips = sorted(CARTO_DIR.glob("*.zip"))
    if len(zips) != 32:
        raise RuntimeError(
            f"Se esperaban 32 ZIP estatales y se encontraron {len(zips)}."
        )

    pieces = []
    source_rows = []

    for i, z in enumerate(zips, 1):
        print(f"[{i}/32] {z.name}")
        g = read_state_layer(z)
        pieces.append(g)
        source_rows.append({
            "source_file": z.name,
            "rows": len(g),
            "crs_output": "EPSG:4326",
        })

    carto = gpd.GeoDataFrame(
        pd.concat(pieces, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )

    audit_before = geometry_audit(carto)

    # No debe haber duplicados por EDOCVE+SECCION en esta fuente.
    dup = carto["SECTION_KEY"].duplicated(keep=False)
    duplicate_keys = (
        carto.loc[dup, ["SECTION_KEY", "SOURCE_FILE"]]
        .sort_values("SECTION_KEY")
    )
    duplicate_keys.to_csv(
        OUT_REPORT / "01_duplicate_section_keys.csv",
        index=False,
    )

    carto = carto.drop_duplicates(
        "SECTION_KEY",
        keep="first",
    ).copy()

    risk = pd.read_parquet(RISK_PATH).copy()
    risk["SECTION_KEY"] = risk["SECTION_KEY"].astype(str)

    # Selección deliberada de variables útiles para mapa/dashboard.
    risk_cols = [
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_EDONOM",
        "RECENT_MPIOCVE",
        "RECENT_MPIONOM",
        "RECENT_TIPOSEC",
        "PRED_ABSTENCION_2027",
        "PRED_LOWER_90_OOS",
        "PRED_UPPER_90_OOS",
        "INTERVAL_WIDTH_PP",
        "HISTORY_DISAGREEMENT_PP",
        "RISK_PERCENTILE",
        "RISK_LEVEL",
        "PRIORITY_TOP10",
        "HIGH_SENSITIVITY_CLASS",
        "GAP_TO_EXIT_HIGH_PP",
        "GAP_TO_EXIT_PRIORITY_PP",
        "INTERVAL_POSITION_VS_HIGH",
    ]

    missing = sorted(set(risk_cols) - set(risk.columns))
    if missing:
        raise RuntimeError(
            f"Faltan columnas requeridas en sensibilidad: {missing}"
        )

    joined = carto.merge(
        risk[risk_cols],
        on="SECTION_KEY",
        how="inner",
        validate="one_to_one",
    )

    joined["TYPE_MATCH_STD"] = (
        joined["CARTO_TIPOSEC_STD"]
        .astype("string")
        .str.upper()
        .eq(
            joined["RECENT_TIPOSEC"]
            .astype("string")
            .str.upper()
        )
    )

    joined["MUNICIPALITY_MATCH"] = (
        joined["CARTO_MPIOCVE"]
        .astype("Int64")
        .eq(
            joined["RECENT_MPIOCVE"]
            .astype("Int64")
        )
    )

    # Documentar mismatches reales tras normalizar tipo de sección.
    mismatch = joined.loc[
        (~joined["TYPE_MATCH_STD"])
        | (~joined["MUNICIPALITY_MATCH"])
    ].copy()

    mismatch.drop(columns="geometry").to_csv(
        OUT_REPORT / "02_post_normalization_mismatches.csv",
        index=False,
    )

    # Geometrías inválidas: reparar únicamente con make_valid.
    invalid = ~joined.geometry.is_valid
    if invalid.any():
        joined.loc[invalid, "geometry"] = (
            joined.loc[invalid, "geometry"].make_valid()
        )

    audit_after = geometry_audit(joined)

    # Salida maestra espacial.
    gpkg_path = OUT_DATA / "risk_2027_provisional.gpkg"
    joined.to_file(
        gpkg_path,
        layer="section_risk_2027",
        driver="GPKG",
        engine="pyogrio",
    )

    # GeoJSON completo para interoperabilidad. Puede ser grande.
    geojson_path = OUT_DATA / "risk_2027_provisional.geojson"
    joined.to_file(
        geojson_path,
        driver="GeoJSON",
        engine="pyogrio",
    )

    # Versión simplificada para dashboard web.
    # Simplificación en un CRS métrico, preservando topología.
    web = joined.to_crs(epsg=6372).copy()
    web["geometry"] = web.geometry.simplify(
        tolerance=75,
        preserve_topology=True,
    )
    web = web.to_crs(epsg=4326)

    web_path = OUT_DATA / "risk_2027_dashboard_simplified.geojson"
    web.to_file(
        web_path,
        driver="GeoJSON",
        engine="pyogrio",
    )

    # Capa base para el dashboard: todas las secciones cartográficas, con o sin
    # estimación, para distinguir "sin estimación" de "sin territorio".
    base = carto[
        ["SECTION_KEY", "CARTO_EDOCVE", "CARTO_MPIOCVE", "geometry"]
    ].to_crs(epsg=6372)
    base["HAS_ESTIMATE"] = base["SECTION_KEY"].isin(joined["SECTION_KEY"])
    base["geometry"] = base.geometry.simplify(
        tolerance=75,
        preserve_topology=True,
    )
    base_path = OUT_DATA / "cartography_base_2027.parquet"
    base.to_crs(epsg=4326).to_parquet(base_path, index=False)

    coverage = pd.DataFrame([
        {
            "metric": "risk_primary_sections",
            "value": int(len(risk)),
        },
        {
            "metric": "spatial_matched_sections",
            "value": int(len(joined)),
        },
        {
            "metric": "spatial_match_rate",
            "value": float(len(joined) / len(risk)),
        },
        {
            "metric": "post_normalization_type_mismatches",
            "value": int((~joined["TYPE_MATCH_STD"]).sum()),
        },
        {
            "metric": "municipality_mismatches",
            "value": int((~joined["MUNICIPALITY_MATCH"]).sum()),
        },
    ])
    coverage.to_csv(
        OUT_REPORT / "03_spatial_coverage_summary.csv",
        index=False,
    )

    state = (
        joined.groupby(
            ["EDOCVE", "RECENT_EDONOM"],
            dropna=False,
        )
        .agg(
            mapped_sections=("SECTION_KEY", "size"),
            high_sections=(
                "RISK_LEVEL",
                lambda s: int((s == "ALTO").sum()),
            ),
            priority_top10_sections=(
                "PRIORITY_TOP10",
                lambda s: int(pd.Series(s).fillna(False).astype(bool).sum()),
            ),
            persistent_high_gt5pp=(
                "HIGH_SENSITIVITY_CLASS",
                lambda s: int((s == "ALTO_PERSISTENTE_MAS_5PP").sum()),
            ),
            pred_mean=("PRED_ABSTENCION_2027", "mean"),
        )
        .reset_index()
    )
    state.to_csv(
        OUT_REPORT / "04_spatial_state_summary.csv",
        index=False,
    )

    source_summary = pd.DataFrame(source_rows)
    source_summary.to_csv(
        OUT_REPORT / "05_spatial_source_files.csv",
        index=False,
    )

    metadata = {
        "status": "PROVISIONAL_CARTOGRAPHY_DIC_2025",
        "cartography_source": "MGS por entidad federativa, corte DIC 2025",
        "output_crs": "EPSG:4326",
        "type_code_mapping": TYPE_CODE_MAP,
        "geometry_audit_before_join": audit_before,
        "geometry_audit_after_join": audit_after,
        "outputs": {
            "gpkg": str(gpkg_path.relative_to(ROOT)),
            "geojson_full": str(geojson_path.relative_to(ROOT)),
            "geojson_dashboard_simplified": str(web_path.relative_to(ROOT)),
        },
        "warning": (
            "Esta entrega usa MGS DIC-2025. El MGE 2026-2027 ya fue aprobado "
            "por el INE, pero el SIGE anuncia la publicación de sus productos "
            "descargables para el 12 de noviembre de 2026, después del cierre "
            "del Hackathon. La capa debe regenerarse cuando estén disponibles."
        ),
    }

    (OUT_REPORT / "spatial_layer_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    method = """# Capa espacial provisional 2027

## Estado

**PROVISIONAL**

La geometría utilizada corresponde al MGS por entidad federativa con corte
DIC-2025. El MGE 2026-2027 ya fue aprobado por el INE, pero el SIGE anuncia
la publicación de sus productos descargables para el 12 de noviembre de 2026,
después del cierre del Hackathon. La capa deberá regenerarse cuando estén disponibles.

## Unión

La llave espacial es:

`SECTION_KEY = EDOCVE + "-" + SECCION`

Sólo se cartografían secciones del universo `primary_clean10` que tienen una
geometría equivalente en la fuente provisional.

## TIPOSEC

La auditoría 14B mostró el siguiente mapeo dominante:

- `2 -> U`
- `3 -> M`
- `4 -> R`

La capa espacial conserva tanto el código original cartográfico como el valor
normalizado.

## Productos

- GeoPackage: análisis en QGIS / interoperabilidad.
- GeoJSON completo: intercambio.
- GeoJSON simplificado: dashboard web.

## Limitación

No se asignan predicciones a secciones cartográficas sin historia comparable.
Las secciones no emparejadas se mantienen documentadas en la auditoría del
paso 14.
"""
    (OUT_REPORT / "SPATIAL_LAYER_METHOD.md").write_text(
        method,
        encoding="utf-8",
    )

    print("\nCobertura espacial:")
    print(coverage.to_string(index=False))

    print("\nAuditoría geométrica después del join:")
    print(json.dumps(audit_after, ensure_ascii=False, indent=2))

    print("\nArchivos:")
    print(f"  GPKG: {gpkg_path.relative_to(ROOT)}")
    print(f"  GeoJSON: {geojson_path.relative_to(ROOT)}")
    print(f"  Dashboard: {web_path.relative_to(ROOT)}")
    print(f"  Capa base: {base_path.relative_to(ROOT)}")

    print("\n=== Capa espacial provisional terminada ===")


if __name__ == "__main__":
    main()
