"""Exporta los datos del sitio web (Astro + API): teselas vectoriales y tabla por sección.

Salidas en data/processed/web/:
- secciones.pmtiles: todas las secciones de la cartografía, geometría completa,
  con los atributos que el mapa necesita para colorear y filtrar sin servidor.
- secciones.parquet: una fila por sección (cartografía ∪ semáforo ∪ NS alto),
  sin geometría. Es la tabla que leerá la API.

La geometría se lee de los ZIP del MGS con el mismo lector de la etapa 15, así
que cambiar al Marco Geográfico Electoral oficial sigue siendo cambiar la ruta.
El contrato de atributos de las teselas está en reports/web_export/WEB_EXPORT_METHOD.md.

Uso:
    python src/21_export_web.py
"""
from pathlib import Path
import importlib.util
import json
import subprocess
import time

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
RISK_PATH = ROOT / "data" / "processed" / "sensitivity_2027" / "section_sensitivity_2027.parquet"
SCENARIOS_PATH = ROOT / "data" / "processed" / "scenarios_2027" / "section_scenarios_2027.parquet"
FORECAST_ALL_PATH = ROOT / "data" / "processed" / "forecast_2027" / "forecast_2027_all_comparable.parquet"
CLUSTERS_PATH = ROOT / "data" / "processed" / "clustering" / "section_clusters.parquet"
OSCAR_PATH = ROOT / "data" / "processed" / "semaforo_oscar" / "comparacion_secciones.parquet"

OUT_DATA = ROOT / "data" / "processed" / "web"
OUT_REPORT = ROOT / "reports" / "web_export"
YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
SCENARIOS = {"S1_TOP10_MINUS2": "S1", "S2_HIGH_MINUS2": "S2", "S3_HIGH_MINUS5": "S3"}


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "src" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_geometry():
    s15 = load_module("15_build_spatial_layer")
    zips = sorted(s15.CARTO_DIR.glob("*.zip"))
    if len(zips) != 32:
        raise RuntimeError(f"Se esperaban 32 ZIP estatales en {s15.CARTO_DIR} y hay {len(zips)}.")
    carto = pd.concat([s15.read_state_layer(z) for z in zips], ignore_index=True)
    carto = gpd.GeoDataFrame(carto, geometry="geometry", crs="EPSG:4326")
    return carto.drop_duplicates("SECTION_KEY")[
        ["SECTION_KEY", "CARTO_EDOCVE", "CARTO_MPIOCVE", "CARTO_SECCION", "geometry"]
    ]


HISTORY_COLS = ["SECTION_KEY", "AELEC", "TIPO_ELECCION", "EDOCVE", "MPIOCVE", "TIPOSEC", "LN", "SV", "NV", "NS"]
CLUSTER_COLS = ["SECTION_KEY", "GRUPO", "GRUPO_NOMBRE", "nivel_intermedia", "nivel_presidencial",
                "tendencia", "volatilidad", "TIPOSEC", "LN", "PROP_LN_18_24"]


def load_master():
    cols = ["AELEC", "TIPO_ELECCION", "SECTION_KEY", "EDOCVE", "EDONOM", "MPIOCVE", "MPIONOM",
            "SECCION", "TIPOSEC", "LN", "SV", "NV", "NS", "PCT_ABSTENCION", "PCT_NS_LN"]
    return pd.read_csv(MASTER_PATH, usecols=cols, dtype={"SECTION_KEY": str}, low_memory=False)


def load_history(master):
    names = (master.sort_values("AELEC").drop_duplicates("SECTION_KEY", keep="last")
             .set_index("SECTION_KEY")[["EDOCVE", "EDONOM", "MPIOCVE", "MPIONOM", "SECCION", "TIPOSEC"]])
    wide = master.pivot_table(index="SECTION_KEY", columns="AELEC",
                              values=["PCT_ABSTENCION", "PCT_NS_LN"], aggfunc="first")
    wide.columns = [f"{'ABST' if v == 'PCT_ABSTENCION' else 'NS'}_{y}" for v, y in wide.columns]
    return names.join(wide)


def load_attributes():
    for path, stage in [(MASTER_PATH, "02_build_master.py"), (RISK_PATH, "13_sensitivity_prioritization.py"),
                        (SCENARIOS_PATH, "12_build_scenarios.py"), (FORECAST_ALL_PATH, "10_fit_final_forecast_2027.py")]:
        if not path.exists():
            raise FileNotFoundError(f"No existe {path.relative_to(ROOT)}. Ejecuta primero src/{stage}")

    risk = pd.read_parquet(RISK_PATH, columns=[
        "SECTION_KEY", "PRED_ABSTENCION_2027", "PRED_LOWER_90_OOS", "PRED_UPPER_90_OOS",
        "RISK_PERCENTILE", "RISK_LEVEL", "PRIORITY_TOP10", "HIGH_SENSITIVITY_CLASS",
        "GAP_TO_EXIT_HIGH_PP", "GAP_TO_EXIT_PRIORITY_PP"]).set_index("SECTION_KEY")
    risk["CAPA"] = "semaforo"

    scen = pd.read_parquet(SCENARIOS_PATH, columns=[
        "SECTION_KEY", "SCENARIO_ID", "SCENARIO_PRED_ABSTENCION", "SCENARIO_RISK_LEVEL", "SCENARIO_PRIORITY_TOP10"])
    scen = scen[scen["SCENARIO_ID"].isin(SCENARIOS)]
    scen = scen.assign(S=scen["SCENARIO_ID"].map(SCENARIOS)).pivot(
        index="SECTION_KEY", columns="S",
        values=["SCENARIO_PRED_ABSTENCION", "SCENARIO_RISK_LEVEL", "SCENARIO_PRIORITY_TOP10"])
    scen.columns = [f"{v.replace('SCENARIO_', '')}_{s}" for v, s in scen.columns]

    ns = pd.read_parquet(FORECAST_ALL_PATH, columns=[
        "SECTION_KEY", "QUALITY_FLAG", "PRED_ABSTENCION_2027", "PRED_LOWER_90_OOS",
        "PRED_UPPER_90_OOS", "SAME_PCT_NS_LN", "RECENT_PCT_NS_LN"]).set_index("SECTION_KEY")
    ns_alto = ns[ns["QUALITY_FLAG"].eq("comparable_high_ns")].drop(columns="QUALITY_FLAG")
    ns_alto = ns_alto[~ns_alto.index.isin(risk.index)].assign(CAPA="ns_alto")

    table = pd.concat([risk, ns_alto[[c for c in ns_alto if c in risk.columns]]])
    table = table.join(ns[["SAME_PCT_NS_LN", "RECENT_PCT_NS_LN"]]).join(scen)

    # Opcionales: si su etapa no se ha corrido, la columna queda vacía.
    if CLUSTERS_PATH.exists():
        table = table.join(pd.read_parquet(CLUSTERS_PATH, columns=["SECTION_KEY", "GRUPO", "GRUPO_NOMBRE"])
                           .set_index("SECTION_KEY"), how="outer")
    if OSCAR_PATH.exists():
        oscar = pd.read_parquet(OSCAR_PATH, columns=["SECTION_KEY", "NIVEL_OSCAR", "PRED_OSCAR", "COMPARACION", "QUALITY_FLAG"])
        # El motivo sólo importa para las secciones que el filtro oficial excluye.
        oscar["MOTIVO_SOLO_OSCAR"] = oscar["QUALITY_FLAG"].where(oscar["COMPARACION"].eq("solo_oscar"))
        table = table.join(oscar.drop(columns="QUALITY_FLAG").set_index("SECTION_KEY")
                           .rename(columns={"COMPARACION": "COMPARACION_OSCAR"}), how="outer")
    return table


def build_table(carto, history, attrs):
    keys = pd.Index(carto["SECTION_KEY"]).union(attrs.index)
    carto_idx = carto.drop(columns="geometry").set_index("SECTION_KEY")
    # Caja de cada sección: la API la agrega para hacer zoom a una entidad o municipio.
    carto_idx[["BBOX_MINX", "BBOX_MINY", "BBOX_MAXX", "BBOX_MAXY"]] = carto.geometry.bounds.round(5).to_numpy()
    table = pd.DataFrame(index=keys).join(history).join(attrs).join(carto_idx)
    table.index.name = "SECTION_KEY"
    table["EN_CARTOGRAFIA"] = table.index.isin(carto["SECTION_KEY"])
    table["CAPA"] = table["CAPA"].fillna("sin_estimacion")
    # Secciones nuevas en la cartografía no tienen historia: se completan con sus claves.
    table["EDOCVE"] = table["EDOCVE"].fillna(table["CARTO_EDOCVE"])
    table["SECCION"] = table["SECCION"].fillna(table["CARTO_SECCION"])
    table["MPIOCVE"] = table["MPIOCVE"].fillna(table["CARTO_MPIOCVE"])
    # Tipos limpios para la API: los joins externos dejan claves como float y banderas como object.
    for col in ["EDOCVE", "MPIOCVE", "SECCION", "GRUPO"]:
        table[col] = table[col].astype("Int64")
    for col in [c for c in table if c.startswith("PRIORITY_TOP10")]:
        table[col] = table[col].astype("boolean")
    return table.reset_index()


def pct(s):
    return (s * 100).round(1)


def tile_properties(table):
    """Atributos compactos de las teselas: nombres cortos, porcentajes con un decimal."""
    t = table
    props = pd.DataFrame({
        "clave": t["SECTION_KEY"],
        "edo": t["EDOCVE"].astype("Int64"),
        "mun": t["MPIOCVE"].astype("Int64"),
        "capa": t["CAPA"],
        "nivel": t["RISK_LEVEL"],
        "top10": t["PRIORITY_TOP10"].astype("boolean"),
        "pred": pct(t["PRED_ABSTENCION_2027"]),
        "sensibilidad": t["HIGH_SENSITIVITY_CLASS"],
        "grupo": t["GRUPO"].astype("Int64"),
        "nivel_oscar": t["NIVEL_OSCAR"],
        "comp_oscar": t["COMPARACION_OSCAR"],
    })
    for s in SCENARIOS.values():
        props[f"nivel_{s.lower()}"] = t[f"RISK_LEVEL_{s}"]
        props[f"top10_{s.lower()}"] = t[f"PRIORITY_TOP10_{s}"].astype("boolean")
    for y in YEARS:
        props[f"abst_{y}"] = pct(t[f"ABST_{y}"])
        props[f"ns_{y}"] = pct(t[f"NS_{y}"])
    return props


def write_outlines(carto, out_dir):
    """Contornos de entidades y municipios (no hay mapa base de terceros)."""
    paths = {}
    g = carto[["CARTO_EDOCVE", "CARTO_MPIOCVE", "geometry"]].rename(
        columns={"CARTO_EDOCVE": "edo", "CARTO_MPIOCVE": "mun"})
    for name, by in [("estados", ["edo"]), ("municipios", ["edo", "mun"])]:
        # method="coverage" sería más rápido, pero falla con las geometrías inválidas del MGS.
        outline = g.dissolve(by=by).reset_index()[by + ["geometry"]]
        paths[name] = out_dir / f"{name}.geojsonl"
        outline.to_file(paths[name], driver="GeoJSONSeq", engine="pyogrio")
    return paths


def run_tippecanoe(seq_path, out_path, outlines):
    # Sin límite de tamaño: con el de 500 KB, a zoom 5 sólo quedaba el 16% de las
    # secciones (huecos en las ciudades). Así queda el 76%; el resto mide menos de
    # un píxel y tippecanoe lo dibuja como "polvo". La vista nacional pesa ~3 MB.
    # ponytail: atributos dentro de la tesela; si crecen mucho, dejar sólo geometría
    # + clave y unir los datos de la API con feature-state (probado: ~1.7 MB a z5).
    cmd = [
        "tippecanoe", "-o", str(out_path), "--force",
        "-n", "Secciones electorales 2027",
        "-A", "INE: Conteos Censales 2009–2024 · MGS DIC-2025 (provisional)",
        "-Z3", "-z12", "--read-parallel", "--detect-shared-borders",
        "--no-tile-size-limit", "--quiet",
        "-L", f"secciones:{seq_path}",
        *[arg for name, path in outlines.items() for arg in ("-L", f"{name}:{path}")],
    ]
    subprocess.run(cmd, check=True)


def main():
    print("\n=== 21 · Exportación para el sitio web ===")
    t0 = time.time()
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)

    carto = load_geometry()
    print(f"Cartografía: {len(carto):,} secciones · {time.time() - t0:.0f} s")
    master = load_master()
    table = build_table(carto, load_history(master), load_attributes())
    table.to_parquet(OUT_DATA / "secciones.parquet", index=False)
    # Sección × elección para las series y tablas de "Datos por año".
    master[HISTORY_COLS].to_parquet(OUT_DATA / "historico.parquet", index=False)
    grupos_path = OUT_DATA / "grupos.parquet"
    if CLUSTERS_PATH.exists():
        pd.read_parquet(CLUSTERS_PATH, columns=CLUSTER_COLS).to_parquet(grupos_path, index=False)
    else:
        grupos_path.unlink(missing_ok=True)

    geo = carto[["SECTION_KEY", "geometry"]].merge(
        tile_properties(table), left_on="SECTION_KEY", right_on="clave").drop(columns="SECTION_KEY")
    seq_path = OUT_DATA / "secciones.geojsonl"
    gpd.GeoDataFrame(geo, geometry="geometry", crs="EPSG:4326").to_file(
        seq_path, driver="GeoJSONSeq", engine="pyogrio")
    outlines = write_outlines(carto, OUT_DATA)
    pmtiles_path = OUT_DATA / "secciones.pmtiles"
    run_tippecanoe(seq_path, pmtiles_path, outlines)
    for path in [seq_path, *outlines.values()]:
        path.unlink()

    # El municipio sale de la historia (CCPC) y, si no hay, de la cartografía.
    both = table.dropna(subset=["CARTO_MPIOCVE"]).loc[lambda d: d["CAPA"].ne("sin_estimacion")]
    summary = {
        "secciones_tabla": len(table),
        "secciones_teselas": len(geo),
        "por_capa_tabla": table["CAPA"].value_counts().to_dict(),
        "por_capa_teselas": geo["capa"].value_counts().to_dict(),
        "semaforo_sin_geometria": int((table["CAPA"].eq("semaforo") & ~table["EN_CARTOGRAFIA"]).sum()),
        "municipio_ccpc_igual_a_mgs": round(float((both["MPIOCVE"] == both["CARTO_MPIOCVE"]).mean()), 4),
        "pmtiles_mb": round(pmtiles_path.stat().st_size / 1e6, 1),
        "parquet_mb": round((OUT_DATA / "secciones.parquet").stat().st_size / 1e6, 1),
        "segundos": round(time.time() - t0),
    }
    (OUT_REPORT / "export_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"Salida: {OUT_DATA.relative_to(ROOT)}/secciones.pmtiles · secciones.parquet")


if __name__ == "__main__":
    main()
