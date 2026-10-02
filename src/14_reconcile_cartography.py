from pathlib import Path
import argparse
import json
import zipfile

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
except ImportError as exc:
    raise SystemExit(
        "Falta geopandas. Instálalo dentro del venv con:\n"
        "  pip install geopandas pyogrio\n"
        "y vuelve a ejecutar este script."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]

RISK_PATH = (
    ROOT / "data" / "processed" / "sensitivity_2027"
    / "section_sensitivity_2027.parquet"
)

DEFAULT_CARTO_DIR = ROOT / "data" / "raw" / "cartography_2027"

OUT_DATA = ROOT / "data" / "processed" / "cartography_2027"
OUT_REPORT = ROOT / "reports" / "cartography_2027"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_REPORT.mkdir(parents=True, exist_ok=True)

SUPPORTED = {".shp", ".gpkg", ".geojson", ".json", ".zip"}

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


def upper_map(columns):
    return {str(c).strip().upper(): c for c in columns}


def detect_column(columns, aliases, required=True):
    mapping = upper_map(columns)
    for alias in aliases:
        if alias.upper() in mapping:
            return mapping[alias.upper()]

    if required:
        raise RuntimeError(
            "No pude detectar una columna requerida.\n"
            f"Aliases buscados: {aliases}\n"
            f"Columnas disponibles: {list(columns)}"
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


def discover_files(path_arg=None):
    if path_arg:
        p = Path(path_arg).expanduser().resolve()
    else:
        p = DEFAULT_CARTO_DIR

    if not p.exists():
        raise FileNotFoundError(f"No existe: {p}")

    if p.is_file():
        if p.suffix.lower() not in SUPPORTED:
            raise RuntimeError(f"Formato no soportado: {p.suffix}")
        return [p]

    files = []
    for f in p.rglob("*"):
        if not f.is_file():
            continue
        if f.name.upper() == "SOURCE_METADATA.JSON":
            continue
        if f.suffix.lower() in SUPPORTED:
            files.append(f)

    # Si hay .shp extraídos y también sus .zip originales, preferir SHP
    # para evitar contar dos veces la misma fuente cuando los nombres coinciden.
    shp_stems = {f.stem.lower() for f in files if f.suffix.lower() == ".shp"}

    filtered = []
    for f in files:
        if f.suffix.lower() == ".zip" and f.stem.lower() in shp_stems:
            continue
        filtered.append(f)

    # Sólo una capa por entidad es lo esperado.
    return sorted(filtered, key=lambda x: str(x))


def _extract_zip_find_shapefile(zip_path):
    """
    Extrae de forma robusta un ZIP del portal INE y localiza el .shp,
    aunque venga dentro de subcarpetas.

    Se usa un cache reproducible dentro de data/interim para evitar depender
    de /vsizip, que puede fallar en Windows/OneDrive con algunos ZIP.
    """
    extract_root = (
        ROOT / "data" / "interim" / "cartography_extract" / zip_path.stem
    )
    extract_root.mkdir(parents=True, exist_ok=True)

    marker = extract_root / ".extracted_ok"

    if not marker.exists():
        # Limpiar restos parciales de una extracción fallida previa.
        for p in sorted(extract_root.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    pass

        with zipfile.ZipFile(zip_path, "r") as z:
            members = z.namelist()

            # Diagnóstico temprano: algunos portales envuelven un ZIP dentro de otro.
            nested_zips = [m for m in members if m.lower().endswith(".zip")]
            shp_members = [m for m in members if m.lower().endswith(".shp")]

            z.extractall(extract_root)

        # Si no había SHP directo pero sí ZIP interno, extraer también.
        if not shp_members and nested_zips:
            for nested in nested_zips:
                nested_path = extract_root / nested
                if nested_path.exists():
                    nested_dir = nested_path.parent / f"{nested_path.stem}_nested"
                    nested_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(nested_path, "r") as nz:
                        nz.extractall(nested_dir)

        marker.write_text("ok", encoding="utf-8")

    shp_files = sorted(extract_root.rglob("*.shp"))

    if not shp_files:
        # Guardar inventario para facilitar diagnóstico.
        inventory = "\n".join(
            str(p.relative_to(extract_root))
            for p in sorted(extract_root.rglob("*"))
            if p.is_file()
        )
        raise RuntimeError(
            f"El ZIP {zip_path.name} no contiene ningún .shp reconocible.\n"
            "Contenido extraído:\n"
            + inventory[:5000]
        )

    if len(shp_files) > 1:
        # Preferir archivos cuyo nombre sugiera capa seccional.
        preferred = [
            p for p in shp_files
            if any(
                token in p.stem.lower()
                for token in ["seccion", "secc", "mgs"]
            )
        ]
        if preferred:
            shp_files = preferred

    if len(shp_files) > 1:
        print(
            f"    [aviso] {zip_path.name} contiene {len(shp_files)} SHP; "
            f"se usará: {shp_files[0].name}"
        )

    return shp_files[0]


def read_geodata(path):
    if path.suffix.lower() == ".zip":
        shp_path = _extract_zip_find_shapefile(path)
        return gpd.read_file(shp_path, engine="pyogrio")

    return gpd.read_file(path, engine="pyogrio")


def read_metadata():
    metadata_path = DEFAULT_CARTO_DIR / "SOURCE_METADATA.json"
    if not metadata_path.exists():
        return {
            "metadata_present": False,
            "warning": (
                "No existe SOURCE_METADATA.json. La auditoría puede ejecutarse, "
                "pero la procedencia/vigencia queda incompleta."
            ),
        }

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    data["metadata_present"] = True
    return data


def normalize_source(path):
    geo = read_geodata(path)

    entity_col = detect_column(geo.columns, ENTITY_ALIASES)
    section_col = detect_column(geo.columns, SECTION_ALIASES)
    municipality_col = detect_column(
        geo.columns, MUNICIPALITY_ALIASES, required=False
    )
    type_col = detect_column(
        geo.columns, TYPE_ALIASES, required=False
    )

    out = pd.DataFrame({
        "CARTO_EDOCVE": as_int_series(geo[entity_col]),
        "CARTO_SECCION": as_int_series(geo[section_col]),
    })

    out["SECTION_KEY"] = make_key(
        out["CARTO_EDOCVE"],
        out["CARTO_SECCION"],
    )

    if municipality_col is not None:
        out["CARTO_MPIOCVE"] = as_int_series(geo[municipality_col])
    else:
        out["CARTO_MPIOCVE"] = pd.array(
            [pd.NA] * len(out), dtype="Int64"
        )

    if type_col is not None:
        out["CARTO_TIPOSEC"] = (
            geo[type_col].astype("string").str.strip().str.upper()
        )
    else:
        out["CARTO_TIPOSEC"] = pd.NA

    out["SOURCE_FILE"] = str(path)
    out["SOURCE_CRS"] = str(geo.crs)
    out["GEOMETRY_TYPE"] = (
        geo.geometry.geom_type.astype("string")
        if "geometry" in geo.columns
        else pd.NA
    )

    schema = pd.DataFrame({
        "source_file": str(path),
        "column": [str(c) for c in geo.columns],
        "dtype": [str(geo[c].dtype) for c in geo.columns],
    })

    source_summary = {
        "source_file": str(path),
        "rows": len(geo),
        "crs": str(geo.crs),
        "entity_column": str(entity_col),
        "section_column": str(section_col),
        "municipality_column": (
            str(municipality_col) if municipality_col is not None else None
        ),
        "type_column": str(type_col) if type_col is not None else None,
        "valid_section_keys": int(out["SECTION_KEY"].notna().sum()),
        "unique_section_keys": int(out["SECTION_KEY"].nunique(dropna=True)),
    }

    return out, schema, source_summary


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Concilia una o varias capas MGS estatales/nacionales con "
            "el universo de riesgo 2027."
        )
    )
    parser.add_argument(
        "--cartography",
        default=None,
        help=(
            "Ruta a un archivo geográfico o a una carpeta con múltiples "
            "SHP/ZIP. Si se omite usa data/raw/cartography_2027/."
        ),
    )
    args = parser.parse_args()

    print("\n=== 14 · Conciliación cartográfica ===")

    if not RISK_PATH.exists():
        raise FileNotFoundError(
            f"No existe {RISK_PATH}. Ejecuta primero src/13_sensitivity_prioritization.py"
        )

    files = discover_files(args.cartography)
    if not files:
        raise FileNotFoundError(
            "No encontré capas .shp/.gpkg/.geojson/.zip."
        )

    print(f"Fuentes cartográficas encontradas: {len(files)}")

    normalized = []
    schemas = []
    source_summaries = []

    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name}")
        try:
            n, schema, summary = normalize_source(path)
        except Exception as exc:
            raise RuntimeError(
                f"Error leyendo/normalizando {path}:\n{exc}"
            ) from exc

        normalized.append(n)
        schemas.append(schema)
        source_summaries.append(summary)

    carto = pd.concat(normalized, ignore_index=True)
    schema_all = pd.concat(schemas, ignore_index=True)
    source_summary = pd.DataFrame(source_summaries)

    schema_all.to_csv(
        OUT_REPORT / "01_cartography_schema.csv",
        index=False,
    )
    source_summary.to_csv(
        OUT_REPORT / "02_cartography_source_summary.csv",
        index=False,
    )

    invalid_key = carto["SECTION_KEY"].isna()

    duplicate_mask = (
        carto["SECTION_KEY"].duplicated(keep=False)
        & carto["SECTION_KEY"].notna()
    )

    duplicate_keys = (
        carto.loc[duplicate_mask]
        .groupby("SECTION_KEY", dropna=False)
        .agg(
            geometry_rows=("SECTION_KEY", "size"),
            source_files=("SOURCE_FILE", lambda s: " | ".join(sorted(set(s)))),
        )
        .reset_index()
    )
    duplicate_keys.to_csv(
        OUT_REPORT / "03_duplicate_cartography_keys.csv",
        index=False,
    )

    carto_unique = (
        carto.loc[carto["SECTION_KEY"].notna()]
        .drop_duplicates("SECTION_KEY", keep="first")
        .copy()
    )

    risk = pd.read_parquet(RISK_PATH).copy()
    required_risk = {
        "SECTION_KEY",
        "EDOCVE",
        "RECENT_MPIOCVE",
        "RECENT_TIPOSEC",
        "RECENT_EDONOM",
        "RECENT_MPIONOM",
        "RISK_LEVEL",
        "PRIORITY_TOP10",
        "HIGH_SENSITIVITY_CLASS",
        "PRED_ABSTENCION_2027",
    }
    missing = sorted(required_risk - set(risk.columns))
    if missing:
        raise RuntimeError(f"Faltan columnas en riesgo: {missing}")

    risk["SECTION_KEY"] = risk["SECTION_KEY"].astype(str)

    carto_keys = set(carto_unique["SECTION_KEY"].astype(str))
    risk_keys = set(risk["SECTION_KEY"].astype(str))

    matched = risk_keys & carto_keys
    risk_only = risk_keys - carto_keys
    carto_only = carto_keys - risk_keys

    risk_match = risk.merge(
        carto_unique[
            [
                "SECTION_KEY",
                "CARTO_EDOCVE",
                "CARTO_MPIOCVE",
                "CARTO_TIPOSEC",
                "SOURCE_FILE",
                "SOURCE_CRS",
                "GEOMETRY_TYPE",
            ]
        ],
        on="SECTION_KEY",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    risk_match["HAS_GEOMETRY"] = risk_match["_merge"].eq("both")

    risk_match["MUNICIPALITY_MATCH"] = np.where(
        risk_match["HAS_GEOMETRY"] & risk_match["CARTO_MPIOCVE"].notna(),
        risk_match["RECENT_MPIOCVE"].astype("Int64").eq(
            risk_match["CARTO_MPIOCVE"].astype("Int64")
        ),
        pd.NA,
    )

    risk_match["TYPE_MATCH"] = np.where(
        risk_match["HAS_GEOMETRY"] & risk_match["CARTO_TIPOSEC"].notna(),
        risk_match["RECENT_TIPOSEC"]
        .astype("string").str.strip().str.upper()
        .eq(
            risk_match["CARTO_TIPOSEC"]
            .astype("string").str.strip().str.upper()
        ),
        pd.NA,
    )

    risk_match = risk_match.drop(columns=["_merge"])

    summary = pd.DataFrame([
        {"metric": "cartography_source_files", "value": len(files)},
        {"metric": "cartography_rows", "value": len(carto)},
        {
            "metric": "cartography_unique_section_keys",
            "value": len(carto_keys),
        },
        {
            "metric": "cartography_invalid_key_rows",
            "value": int(invalid_key.sum()),
        },
        {
            "metric": "cartography_duplicate_section_keys",
            "value": int(len(duplicate_keys)),
        },
        {"metric": "risk_primary_sections", "value": len(risk_keys)},
        {"metric": "matched_sections", "value": len(matched)},
        {
            "metric": "risk_sections_without_geometry",
            "value": len(risk_only),
        },
        {
            "metric": "geometry_sections_without_risk",
            "value": len(carto_only),
        },
        {
            "metric": "risk_match_rate",
            "value": len(matched) / len(risk_keys) if risk_keys else np.nan,
        },
    ])
    summary.to_csv(
        OUT_REPORT / "04_reconciliation_summary.csv",
        index=False,
    )

    state = (
        risk_match.groupby(
            ["EDOCVE", "RECENT_EDONOM"], dropna=False
        )
        .agg(
            risk_sections=("SECTION_KEY", "size"),
            matched=("HAS_GEOMETRY", "sum"),
            municipality_mismatches=(
                "MUNICIPALITY_MATCH",
                lambda s: int((s == False).sum()),  # noqa
            ),
            type_mismatches=(
                "TYPE_MATCH",
                lambda s: int((s == False).sum()),  # noqa
            ),
        )
        .reset_index()
    )
    state["match_rate"] = state["matched"] / state["risk_sections"]
    state.to_csv(
        OUT_REPORT / "05_state_reconciliation.csv",
        index=False,
    )

    risk_match.loc[
        ~risk_match["HAS_GEOMETRY"]
    ].to_csv(
        OUT_REPORT / "06_unmatched_risk_sections.csv",
        index=False,
    )

    carto_unique.loc[
        carto_unique["SECTION_KEY"].astype(str).isin(carto_only)
    ].to_csv(
        OUT_REPORT / "07_cartography_sections_without_risk.csv",
        index=False,
    )

    risk_match.loc[
        risk_match["HAS_GEOMETRY"]
        & (
            risk_match["MUNICIPALITY_MATCH"].eq(False)
            | risk_match["TYPE_MATCH"].eq(False)
        )
    ].to_csv(
        OUT_REPORT / "08_attribute_mismatches.csv",
        index=False,
    )

    risk_match.to_parquet(
        OUT_DATA / "risk_cartography_key_audit.parquet",
        index=False,
    )

    metadata = read_metadata()
    metadata["source_files_count"] = len(files)
    metadata["source_files"] = [str(x) for x in files]

    (OUT_REPORT / "cartography_source_audit.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    match_rate = len(matched) / len(risk_keys) if risk_keys else 0.0

    report = f"""# Conciliación cartográfica

## Estado de la capa

Esta ejecución puede utilizar una capa provisional. La vigencia exacta queda
registrada en `SOURCE_METADATA.json`.

## Resultados

- Fuentes cartográficas: {len(files)}
- Secciones de riesgo: {len(risk_keys):,}
- Secciones cartográficas únicas: {len(carto_keys):,}
- Coincidencias: {len(matched):,}
- Riesgo sin geometría: {len(risk_only):,}
- Geometría sin riesgo: {len(carto_only):,}
- Tasa de cobertura: {match_rate:.4%}

## Llave

`SECTION_KEY = EDOCVE + "-" + SECCION`

## Restricción

Una sección cartográfica sin historia comparable no recibe predicción por
interpolación automática. Cualquier correspondencia entre secciones antiguas y
nuevas debe documentarse explícitamente.

## Uso

Si esta corrida usa MGS DIC-2025, los resultados son de validación provisional.
Antes de la entrega final deberá repetirse con la capa oficial del MGE
2026-2027 cuando esté disponible para descarga.
"""
    (OUT_REPORT / "CARTOGRAPHY_RECONCILIATION.md").write_text(
        report, encoding="utf-8"
    )

    print("\nResumen:")
    print(summary.to_string(index=False))

    print("\nCobertura por entidad:")
    print(
        state.to_string(
            index=False,
            float_format=lambda x: f"{x:.4f}",
        )
    )

    print("\n=== Conciliación terminada ===")
    print(f"Tasa de cobertura: {match_rate:.2%}")

    if match_rate >= 0.95:
        print("[OK] Cobertura >= 95%. Revisar mismatches antes de construir la capa final.")
    else:
        print("[ATENCIÓN] Cobertura < 95%. Revisar no emparejados antes del paso espacial final.")


if __name__ == "__main__":
    main()
