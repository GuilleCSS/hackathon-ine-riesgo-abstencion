"""Entregable del Reto 2: mapa de escenarios con y sin intervención + base de datos empleada.

Salida en data/processed/entregables/mapa_escenarios/ (no versionada; se reconstruye):
- mapa_escenarios_2027.gpkg   Capas 'secciones' (nivel sin intervención y con cada escenario)
                              y 'distritos' (resumen por distrito federal), con estilo de QGIS.
                              Versión completa, para compartir por enlace.
- mapa_escenarios_2027_ligero.gpkg  Igual, más simplificada y sólo con las columnas de escenarios,
                              para que quepa en el zip del correo.
- base_secciones_2027.csv     Base anonimizada: datos agregados por sección del universo
                              comparable 2027 (sin datos personales).
- resumen_entidades.csv, resumen_distritos.csv, resumen_municipios.csv
- mapa_sin_vs_con_intervencion.png
- LEEME.md                    Qué es cada archivo, columnas, escenarios y cómo abrirlo.

Necesita las salidas de las etapas 10, 12, 13, 15 y 21.

Uso:
    python src/entregables/01_exportar_mapa_escenarios.py
"""
from pathlib import Path
import importlib.util
import json
import sqlite3

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
GEOM_PATH = ROOT / "data" / "processed" / "spatial_2027" / "risk_2027_provisional.gpkg"
TABLE_PATH = ROOT / "data" / "processed" / "web" / "secciones.parquet"
FORECAST_ALL_PATH = ROOT / "data" / "processed" / "forecast_2027" / "forecast_2027_all_comparable.parquet"
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
SCENARIO_CONFIG = ROOT / "reports" / "scenarios_2027" / "scenario_config.json"
OUT = ROOT / "data" / "processed" / "entregables" / "mapa_escenarios"

SIMPLIFY_M = 20  # versión completa: mantiene el detalle urbano (para compartir por enlace)
SIMPLIFY_LIGERO_M = 100  # versión ligera para el zip del correo (~15 MB comprimida)
COLS_LIGERO = ["CLAVE", "ENTIDAD", "MUNICIPIO"] + [f"{v}_{k}" for k in ["S0", "S1", "S2", "S3"] for v in ("PRED", "NIVEL", "TOP10")]
SCEN = ["S0", "S1", "S2", "S3"]
COLORS = {"BAJO": "#34c27a", "MEDIO": "#f29b00", "ALTO": "#d4122e"}  # los del sitio (validados)
TIPOS = {"U": "Urbana", "M": "Mixta", "R": "Rural"}
SENS = {"NO_ALTO": "No está en ALTO", "ALTO_SENSIBLE_2PP": "ALTO, a 2 pp o menos de salir",
        "ALTO_SENSIBLE_5PP": "ALTO, a más de 2 y hasta 5 pp", "ALTO_PERSISTENTE_MAS_5PP": "ALTO persistente (más de 5 pp)"}
FLAGS = {"primary_clean10": "En el semáforo", "comparable_high_ns": "Excluida: NS > 10% en 2021 o 2024",
         "insufficient_inputs": "Excluida: sin abstención calculable", "valid_inputs_low_comparability": "Excluida: cambió de municipio o tipo"}


def distritos_geo(distritos):
    """Polígonos de distrito federal desde toda la cartografía (no sólo las secciones del semáforo, que dejarían
    huecos) con el distrito de 2024. Se quitan huecos y fragmentos de menos de 1 km² (errores de la cartografía)."""
    spec = importlib.util.spec_from_file_location("e21", ROOT / "src" / "21_export_web.py")
    e21 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e21)
    carto = e21.load_geometry().to_crs(6372)
    carto["DISTRITO_FED"] = carto["SECTION_KEY"].map(distritos)
    d = carto.dropna(subset=["DISTRITO_FED"]).dissolve(by=["CARTO_EDOCVE", "DISTRITO_FED"]).reset_index()

    def limpiar(g, minimo=1e6):
        partes = [p for p in getattr(g, "geoms", [g]) if p.area >= minimo]
        return shapely.MultiPolygon([shapely.Polygon(p.exterior, [r for r in p.interiors if shapely.Polygon(r).area >= minimo])
                                     for p in partes])

    d["geometry"] = d.geometry.apply(limpiar).simplify(150, preserve_topology=True)
    d["DISTRITO_FED"] = d["DISTRITO_FED"].astype(int)
    return d.rename(columns={"CARTO_EDOCVE": "ENTIDAD_CVE"})[["ENTIDAD_CVE", "DISTRITO_FED", "geometry"]]


def pct(s):
    return (s * 100).round(2)


def tabla_secciones(t, distritos):
    """Una fila por sección del semáforo, con el resultado de cada escenario."""
    s = t[t["CAPA"].eq("semaforo")].copy()
    out = pd.DataFrame({
        "CLAVE": s["SECTION_KEY"], "ENTIDAD_CVE": s["EDOCVE"], "ENTIDAD": s["EDONOM"],
        "DISTRITO_FED": s["SECTION_KEY"].map(distritos).astype("Int64"),
        "MUNICIPIO_CVE": s["MPIOCVE"], "MUNICIPIO": s["MPIONOM"], "SECCION": s["SECCION"],
        "TIPO": s["TIPOSEC"].map(TIPOS),
        "ABST_2021": pct(s["ABST_2021"]), "ABST_2024": pct(s["ABST_2024"]),
        "NS_2021": pct(s["NS_2021"]), "NS_2024": pct(s["NS_2024"]),
        "PRED_S0": pct(s["PRED_ABSTENCION_2027"]), "INTERVALO_INF": pct(s["PRED_LOWER_90_OOS"]),
        "INTERVALO_SUP": pct(s["PRED_UPPER_90_OOS"]), "PERCENTIL": pct(s["RISK_PERCENTILE"]),
        "NIVEL_S0": s["RISK_LEVEL"], "TOP10_S0": s["PRIORITY_TOP10"].astype(bool),
    })
    for k in SCEN[1:]:
        out[f"PRED_{k}"] = pct(s[f"PRED_ABSTENCION_{k}"])
        out[f"NIVEL_{k}"] = s[f"RISK_LEVEL_{k}"]
        out[f"TOP10_{k}"] = s[f"PRIORITY_TOP10_{k}"].astype(bool)
        out[f"CAMBIA_{k}"] = s[f"RISK_LEVEL_{k}"].ne(s["RISK_LEVEL"])
    out["PERSISTENCIA"] = s["HIGH_SENSITIVITY_CLASS"].map(SENS)
    out["PP_SOBRE_UMBRAL_ALTO"] = s["GAP_TO_EXIT_HIGH_PP"].round(2)
    return out


def resumen(d, by):
    g = d.groupby(by, dropna=False)
    out = g.size().rename("secciones").to_frame()
    for k in SCEN:
        out[f"ALTO_{k}"] = g[f"NIVEL_{k}"].apply(lambda x: int(x.eq("ALTO").sum()))
        out[f"TOP10_{k}"] = g[f"TOP10_{k}"].sum().astype(int)
        out[f"PRED_MEDIA_{k}"] = g[f"PRED_{k}"].mean().round(2)
    out["PCT_ALTO_S0"] = (out["ALTO_S0"] / out["secciones"] * 100).round(1)
    out["SALEN_DE_ALTO_S3"] = out["ALTO_S0"] - out["ALTO_S3"]
    return out.reset_index().sort_values(["TOP10_S0", "ALTO_S0"], ascending=False)


def estilo_qgis(gpkg, layer, attr):
    """Estilo categorizado por nivel guardado en la tabla layer_styles: QGIS lo aplica al abrir."""
    cats = "".join(f'<category symbol="{i}" value="{n}" label="{n}" render="true"/>' for i, n in enumerate(COLORS))
    syms = "".join(
        f'<symbol type="fill" name="{i}" alpha="1" clip_to_extent="1" force_rhr="0"><layer class="SimpleFill" enabled="1" pass="0" locked="0">'
        f'<Option type="Map"><Option name="color" type="QString" value="{int(c[1:3], 16)},{int(c[3:5], 16)},{int(c[5:7], 16)},255"/>'
        '<Option name="outline_color" type="QString" value="255,255,255,255"/><Option name="outline_width" type="QString" value="0.06"/>'
        '<Option name="outline_width_unit" type="QString" value="MM"/><Option name="style" type="QString" value="solid"/>'
        '<Option name="outline_style" type="QString" value="solid"/></Option></layer></symbol>'
        for i, c in enumerate(COLORS.values()))
    qml = (f"<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'><qgis version=\"3.34\" styleCategories=\"Symbology\">"
           f'<renderer-v2 type="categorizedSymbol" attr="{attr}" symbollevels="0" enableorderby="0" forceraster="0">'
           f"<categories>{cats}</categories><symbols>{syms}</symbols></renderer-v2></qgis>")
    with sqlite3.connect(gpkg) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT,
            f_table_schema TEXT, f_table_name TEXT, f_geometry_column TEXT, styleName TEXT, styleQML TEXT, styleSLD TEXT,
            useAsDefault BOOLEAN, description TEXT, owner TEXT, ui TEXT, update_time DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("""INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, styleName,
            styleQML, styleSLD, useAsDefault, description) VALUES ('', '', ?, 'geom', ?, ?, '', 1, ?)""",
                    (layer, f"Nivel {attr}", qml, f"Semáforo por {attr}"))


def mapa_png(g, base, path):
    """S0 vs. S3. La base gris (toda la cartografía) evita que las secciones sin estimación parezcan vacías."""
    fig, axes = plt.subplots(1, 2, figsize=(20, 7.5), dpi=200)
    for ax, (k, titulo) in zip(axes, [("S0", "Sin intervención (S0)"), ("S3", "Con intervención hipotética: ALTO −5 pp (S3)")]):
        base.plot(ax=ax, color="#d6dbe1", linewidth=0)
        g.plot(ax=ax, color=g[f"NIVEL_{k}"].map(COLORS), linewidth=0)
        n = g[f"NIVEL_{k}"].value_counts()
        ax.set_title(f"{titulo}\nALTO: {n.get('ALTO', 0):,} secciones en el mapa", fontsize=14)
        ax.set_axis_off()
    fig.legend(handles=[Patch(color=c, label=n) for n, c in COLORS.items()] + [Patch(color="#d6dbe1", label="Sin estimación")],
               loc="lower center", ncol=4, frameon=False, fontsize=12, bbox_to_anchor=(0.5, 0.04))
    fig.text(0.5, 0.012, "Semáforo de riesgo de abstención 2027 por sección (umbrales congelados). Fuente: INE, Conteos Censales de "
             "Participación Ciudadana 2009–2024; cartografía MGS DIC-2025 (provisional).", ha="center", fontsize=9, color="#374151")
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(path, facecolor="white", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def main():
    print("\n=== Entregable: mapa de escenarios ===")
    for path, stage in [(GEOM_PATH, "15_build_spatial_layer.py"), (TABLE_PATH, "21_export_web.py"),
                        (FORECAST_ALL_PATH, "10_fit_final_forecast_2027.py")]:
        if not path.exists():
            raise FileNotFoundError(f"No existe {path.relative_to(ROOT)}. Ejecuta primero src/{stage}")
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(SCENARIO_CONFIG.read_text())
    t = pd.read_parquet(TABLE_PATH)
    m = pd.read_csv(MASTER_PATH, usecols=["AELEC", "SECTION_KEY", "DEF"], dtype={"SECTION_KEY": str})
    distritos = m[m["AELEC"].eq(2024)].set_index("SECTION_KEY")["DEF"]

    secc = tabla_secciones(t, distritos)
    original = gpd.read_file(GEOM_PATH, columns=["SECTION_KEY"], engine="pyogrio").rename(columns={"SECTION_KEY": "CLAVE"}).to_crs(6372)

    def simplificada(tol):
        g = original.copy()
        g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
        return g

    capa = simplificada(SIMPLIFY_M).merge(secc, on="CLAVE", how="inner").to_crs(4326)
    print(f"  secciones con polígono: {len(capa):,} de {len(secc):,}")

    gpkg = OUT / "mapa_escenarios_2027.gpkg"
    gpkg.unlink(missing_ok=True)
    capa.to_file(gpkg, layer="secciones", driver="GPKG", engine="pyogrio")
    dist = distritos_geo(distritos).merge(resumen(secc, ["ENTIDAD_CVE", "ENTIDAD", "DISTRITO_FED"]),
                                          on=["ENTIDAD_CVE", "DISTRITO_FED"], how="left").to_crs(4326)
    dist.to_file(gpkg, layer="distritos", driver="GPKG", engine="pyogrio")
    estilo_qgis(gpkg, "secciones", "NIVEL_S0")
    ligero = OUT / "mapa_escenarios_2027_ligero.gpkg"
    ligero.unlink(missing_ok=True)
    capa_ligera = simplificada(SIMPLIFY_LIGERO_M).merge(secc, on="CLAVE", how="inner")
    capa_ligera[COLS_LIGERO + ["geometry"]].to_crs(4326).to_file(ligero, layer="secciones", driver="GPKG", engine="pyogrio")
    dist.to_file(ligero, layer="distritos", driver="GPKG", engine="pyogrio")
    estilo_qgis(ligero, "secciones", "NIVEL_S0")

    # Base de datos empleada: universo comparable 2027 (incluye las excluidas y el motivo).
    f = pd.read_parquet(FORECAST_ALL_PATH, columns=[
        "SECTION_KEY", "EDOCVE", "RECENT_EDONOM", "RECENT_MPIOCVE", "RECENT_MPIONOM", "RECENT_TIPOSEC",
        "SAME_LN", "SAME_PCT_ABSTENCION", "SAME_PCT_NS_LN", "RECENT_LN", "RECENT_PCT_ABSTENCION", "RECENT_PCT_NS_LN", "QUALITY_FLAG"])
    base = pd.DataFrame({
        "CLAVE": f["SECTION_KEY"], "ENTIDAD_CVE": f["EDOCVE"], "ENTIDAD": f["RECENT_EDONOM"],
        "DISTRITO_FED": f["SECTION_KEY"].map(distritos).astype("Int64"), "MUNICIPIO_CVE": f["RECENT_MPIOCVE"],
        "MUNICIPIO": f["RECENT_MPIONOM"], "TIPO": f["RECENT_TIPOSEC"].map(TIPOS),
        "LISTA_NOMINAL_2021": f["SAME_LN"], "ABST_2021": pct(f["SAME_PCT_ABSTENCION"]), "NS_2021": pct(f["SAME_PCT_NS_LN"]),
        "LISTA_NOMINAL_2024": f["RECENT_LN"], "ABST_2024": pct(f["RECENT_PCT_ABSTENCION"]), "NS_2024": pct(f["RECENT_PCT_NS_LN"]),
        "SITUACION": f["QUALITY_FLAG"].map(FLAGS),
    }).merge(secc.drop(columns=["ENTIDAD_CVE", "ENTIDAD", "DISTRITO_FED", "MUNICIPIO_CVE", "MUNICIPIO", "SECCION", "TIPO",
                                "ABST_2021", "ABST_2024", "NS_2021", "NS_2024"]), on="CLAVE", how="left")
    base["CON_POLIGONO"] = base["CLAVE"].isin(capa["CLAVE"])
    base.to_csv(OUT / "base_secciones_2027.csv", index=False, encoding="utf-8-sig")

    ent = resumen(secc, ["ENTIDAD_CVE", "ENTIDAD"])
    ent.to_csv(OUT / "resumen_entidades.csv", index=False, encoding="utf-8-sig")
    resumen(secc, ["ENTIDAD_CVE", "ENTIDAD", "DISTRITO_FED"]).to_csv(OUT / "resumen_distritos.csv", index=False, encoding="utf-8-sig")
    resumen(secc, ["ENTIDAD_CVE", "ENTIDAD", "MUNICIPIO_CVE", "MUNICIPIO"]).to_csv(OUT / "resumen_municipios.csv", index=False, encoding="utf-8-sig")
    mapa_png(capa, dist, OUT / "mapa_sin_vs_con_intervencion.png")

    nac = {k: int(secc[f"NIVEL_{k}"].eq("ALTO").sum()) for k in SCEN}
    labels = {s["scenario_id"][:2]: s for s in cfg["scenarios"]}
    q = cfg["classification_thresholds_frozen_from_baseline"]
    escenarios = "\n".join(f"| {k} | {labels[k]['label']} | {labels[k]['description']} | {nac[k]:,} |" for k in SCEN)
    sizes = "\n".join(f"| `{p.name}` | {p.stat().st_size / 1e6:.1f} MB |" for p in sorted(OUT.iterdir()) if p.suffix != ".md")
    (OUT / "LEEME.md").write_text(f"""# Mapa de escenarios 2027 y base de datos

Entregable del Reto 2 (Predicción y escenarios de riesgo de abstención). Generado por
`src/entregables/01_exportar_mapa_escenarios.py`.

## Archivos

| Archivo | Tamaño |
|---|---|
{sizes}

- **`mapa_escenarios_2027.gpkg`**: GeoPackage (EPSG:4326). Se abre en QGIS arrastrándolo a la ventana; la
  capa `secciones` ya viene coloreada por `NIVEL_S0` (sin intervención). Para ver un escenario, cambiar el
  campo del estilo a `NIVEL_S1`, `NIVEL_S2` o `NIVEL_S3`. La capa `distritos` resume por distrito federal.
  Polígonos simplificados a {SIMPLIFY_M} m. Es la versión completa: por su tamaño se comparte por enlace.
- **`mapa_escenarios_2027_ligero.gpkg`**: la misma información de escenarios (nivel, Top10 y abstención
  estimada en S0–S3) con polígonos simplificados a {SIMPLIFY_LIGERO_M} m, para el zip del correo. Las demás
  columnas están en `base_secciones_2027.csv` (se unen por `CLAVE`).
- **`base_secciones_2027.csv`**: base anonimizada empleada (UTF-8; se abre en Excel). Una fila por sección del
  universo comparable 2021–2024 ({len(base):,} secciones), con el motivo de exclusión de las que no entran al
  semáforo. Son datos agregados por sección publicados por el INE: no contiene datos personales.
- **`resumen_*.csv`**: conteos por entidad, distrito federal y municipio para priorizar recursos.
- **`mapa_sin_vs_con_intervencion.png`**: mapa nacional S0 vs. S3 (200 dpi).

## Escenarios

Los umbrales del semáforo se congelan en los del escenario base (BAJO ≤ {q['q50'] * 100:.2f}%, MEDIO ≤ {q['q80'] * 100:.2f}%,
ALTO > {q['q80'] * 100:.2f}%, Top10 ≥ {q['q90'] * 100:.2f}%) para que las secciones puedan cambiar de nivel. Las reducciones son
supuestos de sensibilidad, no efectos causales estimados.

| Escenario | Nombre | Supuesto | Secciones ALTO |
|---|---|---|---|
{escenarios}

## Columnas

| Columna | Descripción |
|---|---|
| CLAVE | Entidad-sección (`EE-SSSS`) |
| ENTIDAD_CVE, ENTIDAD, DISTRITO_FED, MUNICIPIO_CVE, MUNICIPIO, SECCION, TIPO | Ubicación (distrito federal de 2024) |
| LISTA_NOMINAL_2021/2024 | Lista nominal de la sección (sólo en la base CSV) |
| ABST_2021, ABST_2024 | Abstención observada (%) = no votaron / (votaron + no votaron) |
| NS_2021, NS_2024 | Registros sin información de participación (% de la lista nominal) |
| PRED_S0 | Abstención estimada 2027 sin intervención (%) |
| INTERVALO_INF, INTERVALO_SUP | Intervalo empírico al 90% (errores fuera de muestra de 2021) |
| PERCENTIL | Percentil de riesgo dentro del semáforo |
| NIVEL_Sx, TOP10_Sx | Nivel (BAJO/MEDIO/ALTO) y bandera Top10 en cada escenario |
| PRED_Sx | Abstención estimada con la intervención supuesta (%) |
| CAMBIA_Sx | Verdadero si el nivel cambia frente a S0 |
| PERSISTENCIA, PP_SOBRE_UMBRAL_ALTO | Qué tanto le falta para salir de ALTO |
| SITUACION, CON_POLIGONO | En el semáforo o motivo de exclusión; si tiene polígono en la cartografía |

Cartografía provisional MGS DIC-2025: debe sustituirse por el Marco Geográfico Electoral 2026–2027 oficial.
""", encoding="utf-8")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}: {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
