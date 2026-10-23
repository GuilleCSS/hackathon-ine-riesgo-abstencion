"""API de sólo lectura del sitio web.

Consulta con DuckDB la tabla de src/21_export_web.py y sirve, desde el mismo
proceso, las teselas (PMTiles, con HTTP Range) y el build estático de Astro.
No hay escritura ni sesiones: todo es GET con parámetros validados.

    uvicorn api.main:app --port 8000
"""
from pathlib import Path
import base64
import hashlib
import json
import math
import re
from typing import Annotated, Literal

import duckdb
from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "data" / "processed" / "web"
TABLE_PATH = WEB_DATA / "secciones.parquet"
HISTORY_PATH = WEB_DATA / "historico.parquet"
GROUPS_PATH = WEB_DATA / "grupos.parquet"  # opcional: sólo si se corrió el clustering
TILES_PATH = WEB_DATA / "secciones.pmtiles"
SCENARIO_CONFIG = ROOT / "reports" / "scenarios_2027" / "scenario_config.json"
CLUSTER_CONFIG = ROOT / "reports" / "clustering" / "clustering_config.json"
K_SELECTION = ROOT / "reports" / "clustering" / "01_k_selection.csv"
OSCAR_CONFIG = ROOT / "reports" / "semaforo_oscar" / "comparacion_config.json"
DIST = ROOT / "web" / "dist"

for path in (TABLE_PATH, HISTORY_PATH, TILES_PATH, SCENARIO_CONFIG):
    if not path.exists():
        raise FileNotFoundError(f"No existe {path.relative_to(ROOT)}. Ejecuta primero src/21_export_web.py")

Escenario = Literal["S0", "S1", "S2", "S3"]
TipoEleccion = Literal["intermedia", "presidencial"]
Nivel = Literal["BAJO", "MEDIO", "ALTO"]
Sensibilidad = Literal["NO_ALTO", "ALTO_SENSIBLE_2PP", "ALTO_SENSIBLE_5PP", "ALTO_PERSISTENTE_MAS_5PP"]
SCENARIO_IDS = {"S0": "S0_BASELINE", "S1": "S1_TOP10_MINUS2", "S2": "S2_HIGH_MINUS2", "S3": "S3_HIGH_MINUS5"}
# (nivel, top10, abstención) de cada escenario; los nombres salen de esta lista, nunca del usuario.
COLS = {"S0": ("RISK_LEVEL", "PRIORITY_TOP10", "PRED_ABSTENCION_2027")} | {
    s: (f"RISK_LEVEL_{s}", f"PRIORITY_TOP10_{s}", f"PRED_ABSTENCION_{s}") for s in ("S1", "S2", "S3")}
YEARS = {2009: "intermedia", 2012: "presidencial", 2015: "intermedia",
         2018: "presidencial", 2021: "intermedia", 2024: "presidencial"}

scenario_cfg = json.loads(SCENARIO_CONFIG.read_text())
THRESHOLDS = scenario_cfg["classification_thresholds_frozen_from_baseline"]
con = duckdb.connect()
con.execute("CREATE TABLE s AS SELECT * FROM read_parquet(?)", [str(TABLE_PATH)])
con.execute("CREATE TABLE h AS SELECT * FROM read_parquet(?)", [str(HISTORY_PATH)])
HAS_GROUPS = GROUPS_PATH.exists() and CLUSTER_CONFIG.exists()
if HAS_GROUPS:
    con.execute("CREATE TABLE g AS SELECT * FROM read_parquet(?)", [str(GROUPS_PATH)])
# ponytail: la tabla se carga al arrancar; reiniciar la API después de correr src/21.


def rows(sql, params=()):
    cur = con.cursor()  # un cursor por petición: DuckDB no comparte conexiones entre hilos
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    clean = lambda v: None if isinstance(v, float) and math.isnan(v) else v
    return [{c: clean(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def inline_hashes(tag):
    """Hashes de los <script>/<style> en línea del build de Astro, para una CSP sin 'unsafe-inline'."""
    hashes = set()
    for html in DIST.rglob("*.html") if DIST.exists() else []:
        for body in re.findall(rf"<{tag}(?![^>]*\bsrc=)[^>]*>(.*?)</{tag}>", html.read_text(), re.S):
            hashes.add("'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'")
    return " ".join(sorted(hashes))


# ponytail: los hashes se calculan al arrancar; reiniciar la API después de cada pnpm build.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        f"default-src 'self'; script-src 'self' {inline_hashes('script')}; style-src 'self' {inline_hashes('style')}; "
        "img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

app = FastAPI(title="Riesgo territorial de abstención 2027", version="0.1.0",
              description="API de sólo lectura sobre las salidas del pipeline.")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


def scope_filter(edo, mun, alias=""):
    cond, params = [f"{alias}EN_CARTOGRAFIA"], []
    if edo is not None:
        cond.append(f"{alias}EDOCVE = ?"); params.append(edo)
    if mun is not None:
        cond.append(f"{alias}MPIOCVE = ?"); params.append(mun)
    return cond, params


def bbox(edo, mun=None):
    cond, params = scope_filter(edo, mun)
    r = rows(f"""SELECT min(BBOX_MINX) AS a, min(BBOX_MINY) AS b, max(BBOX_MAXX) AS c, max(BBOX_MAXY) AS d
                 FROM s WHERE {' AND '.join(cond)}""", params)[0]
    return [r["a"], r["b"], r["c"], r["d"]]


Edo = Annotated[int | None, Query(ge=1, le=32)]


@app.get("/api/salud")
def salud():
    return {"ok": True, "secciones": rows("SELECT count(*) AS n FROM s")[0]["n"],
            "datos": TABLE_PATH.stat().st_mtime}


@app.get("/api/config")
def config():
    labels = {s["scenario_id"]: s for s in scenario_cfg["scenarios"]}
    return {
        "escenarios": [{"id": k, "etiqueta": labels[v]["label"], "delta_pp": labels[v]["delta_pp"],
                        "descripcion": labels[v]["description"]} for k, v in SCENARIO_IDS.items()],
        "umbrales": {k: round(v * 100, 2) for k, v in THRESHOLDS.items()},
    }


@app.get("/api/entidades")
def entidades():
    return rows("""
        SELECT EDOCVE::INT AS edo, mode(EDONOM) AS nombre, count(*) FILTER (EN_CARTOGRAFIA) AS secciones
        FROM s WHERE EDOCVE IS NOT NULL GROUP BY 1 ORDER BY 1""")


@app.get("/api/entidades/{edo}/municipios")
def municipios(edo: Annotated[int, PathParam(ge=1, le=32)]):
    return rows("""
        SELECT MPIOCVE::INT AS mun, mode(MPIONOM) AS nombre
        FROM s WHERE EDOCVE = ? AND MPIONOM IS NOT NULL GROUP BY 1 ORDER BY 2""", [edo])


@app.get("/api/resumen")
def resumen(
    escenario: Escenario = "S0",
    edo: Annotated[int | None, Query(ge=1, le=32)] = None,
    mun: Annotated[int | None, Query(ge=0, le=999)] = None,
    nivel: Annotated[list[Nivel], Query()] = ["BAJO", "MEDIO", "ALTO"],
    top10: bool = False,
    sensibilidad: Sensibilidad | None = None,
):
    """KPIs y tablas del mapa con los mismos filtros que se aplican a las teselas."""
    level, top, pred = COLS[escenario]
    scope, scope_params = scope_filter(edo, mun)
    cond = scope + ["CAPA = 'semaforo'", f"{level} IN ({', '.join('?' * len(nivel)) or 'NULL'})"]
    params = scope_params + list(nivel)
    if top10:
        cond.append(top)
    if sensibilidad:
        cond.append("HIGH_SENSITIVITY_CLASS = ?"); params.append(sensibilidad)
    where = " AND ".join(cond)
    metrics = f"""count(*) AS secciones, avg({pred}) * 100 AS abstencion_media,
        count(*) FILTER ({level} = 'ALTO') AS alto, count(*) FILTER ({top}) AS top10"""

    kpis = rows(f"SELECT {metrics} FROM s WHERE {where}", params)[0]
    scope_where = " AND ".join(scope)
    coverage = rows(f"""
        SELECT count(*) AS cartografia, count(*) FILTER (CAPA = 'semaforo') AS con_estimacion,
               count(*) FILTER (CAPA = 'ns_alto') AS ns_alto,
               min(BBOX_MINX) AS minx, min(BBOX_MINY) AS miny, max(BBOX_MAXX) AS maxx, max(BBOX_MAXY) AS maxy
        FROM s WHERE {scope_where}""", scope_params)[0]
    states = rows(f"""
        WITH f AS (SELECT EDOCVE, mode(EDONOM) AS nombre, {metrics} FROM s WHERE {where} GROUP BY EDOCVE),
             c AS (SELECT EDOCVE, avg((CAPA = 'semaforo')::INT) AS cobertura FROM s WHERE EN_CARTOGRAFIA GROUP BY EDOCVE)
        SELECT f.EDOCVE::INT AS edo, nombre, secciones, alto, top10, abstencion_media,
               alto / secciones AS share_alto, top10 / secciones AS share_top10, cobertura
        FROM f JOIN c USING (EDOCVE) ORDER BY share_alto DESC, top10 DESC""", params)
    munis = rows(f"""
        SELECT EDOCVE::INT AS edo, mode(EDONOM) AS entidad, MPIOCVE::INT AS mun, mode(MPIONOM) AS nombre, {metrics},
               alto / count(*) AS share_alto, top10 / count(*) AS share_top10
        FROM s WHERE {where} GROUP BY EDOCVE, MPIOCVE
        ORDER BY top10 DESC, alto DESC, share_alto DESC, abstencion_media DESC LIMIT 30""", params)
    bbox = [coverage.pop(k) for k in ("minx", "miny", "maxx", "maxy")]
    return {"kpis": kpis | {"cobertura": coverage}, "bbox": bbox, "entidades": states, "municipios": munis}


@app.get("/api/secciones/{clave}")
def seccion(clave: Annotated[str, PathParam(pattern=r"^\d{2}-\d{4}$")]):
    found = rows("SELECT * FROM s WHERE SECTION_KEY = ?", [clave])
    if not found:
        raise HTTPException(404, f"No existe la sección {clave}")
    r = found[0]
    pred = r["PRED_ABSTENCION_2027"]
    indicative = None
    if r["CAPA"] == "ns_alto" and pred is not None:
        # Nivel sólo indicativo: con NS alto la sección queda fuera del semáforo.
        indicative = "BAJO" if pred <= THRESHOLDS["q50"] else "MEDIO" if pred <= THRESHOLDS["q80"] else "ALTO"
    pct = lambda v: None if v is None else round(v * 100, 1)
    labels = {s["scenario_id"]: s["label"] for s in scenario_cfg["scenarios"]}
    return {
        "clave": clave,
        "entidad": {"edo": r["EDOCVE"], "nombre": r["EDONOM"]},
        "municipio": {"mun": r["MPIOCVE"], "nombre": r["MPIONOM"]},
        "seccion": r["SECCION"], "tipo": r["TIPOSEC"], "capa": r["CAPA"], "en_cartografia": r["EN_CARTOGRAFIA"],
        "estimacion": {
            "pred": pct(pred), "inferior_90": pct(r["PRED_LOWER_90_OOS"]), "superior_90": pct(r["PRED_UPPER_90_OOS"]),
            "percentil": pct(r["RISK_PERCENTILE"]), "nivel": r["RISK_LEVEL"], "top10": r["PRIORITY_TOP10"],
            "nivel_indicativo": indicative,
        },
        "ns": {"2021": pct(r["SAME_PCT_NS_LN"]), "2024": pct(r["RECENT_PCT_NS_LN"])},
        "sensibilidad": {"clase": r["HIGH_SENSITIVITY_CLASS"],
                         "para_salir_de_alto_pp": None if r["GAP_TO_EXIT_HIGH_PP"] is None else round(r["GAP_TO_EXIT_HIGH_PP"], 1),
                         "para_salir_de_top10_pp": None if r["GAP_TO_EXIT_PRIORITY_PP"] is None else round(r["GAP_TO_EXIT_PRIORITY_PP"], 1)},
        "escenarios": [{"id": s, "etiqueta": labels[SCENARIO_IDS[s]], "nivel": r[c[0]], "top10": r[c[1]],
                        "pred": pct(r[c[2]])} for s, c in COLS.items()] if r["CAPA"] == "semaforo" else [],
        "historia": [{"anio": y, "tipo": t, "abstencion": pct(r[f"ABST_{y}"]), "ns": pct(r[f"NS_{y}"])}
                     for y, t in YEARS.items()],
        "grupo": {"id": r["GRUPO"], "nombre": r["GRUPO_NOMBRE"]},
        "oscar": {"nivel": r["NIVEL_OSCAR"], "pred": pct(r["PRED_OSCAR"]), "comparacion": r["COMPARACION_OSCAR"]},
    }


@app.get("/api/historico")
def historico(edo: Edo = None, tipo: TipoEleccion | None = None):
    """Series 2009–2024, secciones por rango de NS y cambios de secciones entre elecciones."""
    cond, params = ["TRUE"], []
    if edo is not None:
        cond.append("EDOCVE = ?"); params.append(edo)
    if tipo:
        cond.append("TIPO_ELECCION = ?"); params.append(tipo)
    where = " AND ".join(cond)
    anios = rows(f"""
        SELECT AELEC AS anio, any_value(TIPO_ELECCION) AS tipo, count(*) AS secciones,
               sum(LN) AS ln, sum(SV) AS sv, sum(NV) AS nv, sum(NS) AS ns,
               sum(NV) / (sum(SV) + sum(NV)) AS abstencion, sum(NS) / sum(LN) AS pct_ns,
               count(*) FILTER (SECTION_KEY IN (SELECT SECTION_KEY FROM s WHERE EN_CARTOGRAFIA)) AS en_cartografia
        FROM h WHERE {where} GROUP BY AELEC ORDER BY AELEC""", params)
    # Mismos cortes que dashboard/datos_anuales.py; las secciones sin lista nominal cuentan como ≤5%.
    rangos = rows(f"""
        SELECT AELEC AS anio, CASE
            WHEN NS / nullif(LN, 0) >= 1 THEN '100%' WHEN NS / nullif(LN, 0) > 0.5 THEN '50–99%'
            WHEN NS / nullif(LN, 0) > 0.25 THEN '25–50%' WHEN NS / nullif(LN, 0) > 0.10 THEN '10–25%'
            WHEN NS / nullif(LN, 0) > 0.05 THEN '5–10%' ELSE '≤5%' END AS rango,
          count(*) AS secciones
        FROM h WHERE {where} GROUP BY ALL ORDER BY 1""", params)
    cambios = rows(f"""
        WITH f AS (SELECT SECTION_KEY, AELEC, MPIOCVE, TIPOSEC FROM h WHERE {where}),
        y AS (SELECT AELEC AS actual, lag(AELEC) OVER (ORDER BY AELEC) AS previa FROM (SELECT DISTINCT AELEC FROM f)),
        a AS (SELECT y.actual, y.previa, f.* FROM y JOIN f ON f.AELEC = y.actual WHERE y.previa IS NOT NULL),
        b AS (SELECT y.actual, y.previa, f.* FROM y JOIN f ON f.AELEC = y.previa WHERE y.previa IS NOT NULL)
        SELECT coalesce(a.actual, b.actual) AS anio, coalesce(a.previa, b.previa) AS comparada_con,
               count(a.SECTION_KEY) AS secciones, count(*) FILTER (b.SECTION_KEY IS NULL) AS nuevas,
               count(*) FILTER (a.SECTION_KEY IS NULL) AS desaparecidas,
               count(*) FILTER (a.MPIOCVE <> b.MPIOCVE) AS cambio_municipio,
               count(*) FILTER (a.TIPOSEC <> b.TIPOSEC) AS cambio_tipo
        FROM a FULL JOIN b ON a.actual = b.actual AND a.SECTION_KEY = b.SECTION_KEY
        GROUP BY 1, 2 ORDER BY 1""", params)
    return {"anios": anios, "ns_rangos": rangos, "cambios": cambios, "bbox": bbox(edo)}


@app.get("/api/grupos")
def grupos(edo: Edo = None, tipo: TipoEleccion | None = None):
    """Perfil, trayectorias y composición de los grupos del clustering (fase 1, descriptivo)."""
    if not HAS_GROUPS:
        raise HTTPException(404, "No hay grupos: corre src/clustering/01_build_section_clusters.py y src/21_export_web.py")
    cfg = json.loads(CLUSTER_CONFIG.read_text())
    where, params = ("s.EDOCVE = ?", [edo]) if edo is not None else ("TRUE", [])
    scope = f"g JOIN s USING (SECTION_KEY) WHERE {where}"
    carto_cond, carto_params = scope_filter(edo, None)
    agrupadas = rows(f"SELECT count(*) AS n, count(*) FILTER (s.EN_CARTOGRAFIA) AS en_carto FROM {scope}", params)[0]
    cartografia = rows(f"SELECT count(*) AS n FROM s WHERE {' AND '.join(carto_cond)}", carto_params)[0]["n"]
    perfil = rows(f"""
        SELECT g.GRUPO AS grupo, any_value(g.GRUPO_NOMBRE) AS nombre, count(*) AS secciones,
               avg(nivel_intermedia) AS intermedias, avg(nivel_presidencial) AS presidenciales,
               avg(tendencia) AS tendencia, avg(volatilidad) AS volatilidad,
               avg((g.TIPOSEC = 'U')::INT) AS urbana, avg((g.TIPOSEC = 'R')::INT) AS rural,
               median(g.LN) AS ln_mediana, avg(PROP_LN_18_24) AS jovenes
        FROM {scope} GROUP BY 1 ORDER BY 1""", params)
    total = sum(p["secciones"] for p in perfil) or 1
    for p in perfil:
        p["pct"] = p["secciones"] / total
    years_cond = "" if tipo is None else "AND h.TIPO_ELECCION = ?"
    trayectorias = rows(f"""
        WITH x AS (SELECT g.GRUPO, h.AELEC, h.TIPO_ELECCION, h.SV, h.NV
                   FROM g JOIN s USING (SECTION_KEY) JOIN h USING (SECTION_KEY) WHERE {where} {years_cond})
        SELECT GRUPO AS grupo, AELEC AS anio, any_value(TIPO_ELECCION) AS tipo, sum(NV) / (sum(SV) + sum(NV)) AS abstencion
        FROM x GROUP BY 1, 2
        UNION ALL
        SELECT NULL, AELEC, any_value(TIPO_ELECCION), sum(NV) / (sum(SV) + sum(NV)) FROM x GROUP BY AELEC
        ORDER BY 1 NULLS LAST, 2""", params + ([tipo] if tipo else []))
    # Por entidad a nivel nacional; por municipio (los 30 con más secciones) dentro de una entidad.
    clave, nombre = ("s.EDOCVE", "s.EDONOM") if edo is None else ("s.MPIOCVE", "s.MPIONOM")
    composicion = rows(f"""
        WITH c AS (SELECT {clave} AS clave, any_value({nombre}) AS nombre, g.GRUPO AS grupo, count(*) AS secciones
                   FROM {scope} GROUP BY {clave}, g.GRUPO),
             t AS (SELECT clave, sum(secciones) AS total FROM c GROUP BY 1 ORDER BY 2 DESC {'' if edo is None else 'LIMIT 30'})
        SELECT c.clave::INT AS clave, c.nombre, c.grupo, c.secciones, c.secciones / t.total AS pct, t.total
        FROM c JOIN t USING (clave) ORDER BY t.total DESC, c.grupo""", params)
    k_sel = [dict(zip(["k", "silhouette", "tamanos"], line.split(",")))
             for line in K_SELECTION.read_text().splitlines()[1:]] if K_SELECTION.exists() else []
    return {
        "config": {k: cfg[k] for k in ("k", "silhouette_k", "sections_clustered", "max_ns", "naming_rules_pp", "groups")},
        "k_seleccion": k_sel,
        "kpis": {"agrupadas": agrupadas["n"], "agrupadas_en_cartografia": agrupadas["en_carto"], "cartografia": cartografia},
        "perfil": perfil, "trayectorias": trayectorias, "composicion": composicion, "bbox": bbox(edo),
    }


@app.get("/api/oscar")
def oscar(edo: Edo = None):
    """Semáforo oficial frente al alternativo de Oscar (st_gcn_participation), sección por sección."""
    cond, params = ["COMPARACION_OSCAR IS NOT NULL"], []
    if edo is not None:
        cond.append("EDOCVE = ?"); params.append(edo)
    where = " AND ".join(cond)
    ambos = "COMPARACION_OSCAR IN ('coincide', 'oscar_mas_alto', 'oscar_mas_bajo')"
    kpis = rows(f"""
        SELECT count(*) FILTER ({ambos}) AS ambos,
               count(*) FILTER (COMPARACION_OSCAR = 'coincide') / nullif(count(*) FILTER ({ambos}), 0) AS mismo_nivel,
               avg((PRED_OSCAR - PRED_ABSTENCION_2027) * 100) FILTER ({ambos}) AS dif_media_pp,
               count(*) FILTER (COMPARACION_OSCAR = 'solo_oscar') AS solo_oscar,
               count(*) FILTER (COMPARACION_OSCAR = 'solo_oficial') AS solo_oficial
        FROM s WHERE {where}""", params)[0]
    matriz = rows(f"""
        SELECT RISK_LEVEL AS oficial, NIVEL_OSCAR AS oscar, count(*) AS secciones
        FROM s WHERE {where} AND {ambos} GROUP BY ALL""", params)
    motivos = rows(f"""
        SELECT MOTIVO_SOLO_OSCAR AS motivo, count(*) AS secciones
        FROM s WHERE {where} AND COMPARACION_OSCAR = 'solo_oscar' GROUP BY 1 ORDER BY 2 DESC""", params)
    unidad = ("EDOCVE", "EDONOM") if edo is None else ("MPIOCVE", "MPIONOM")
    por_unidad = rows(f"""
        SELECT {unidad[0]}::INT AS clave, mode({unidad[1]}) AS nombre, count(*) FILTER ({ambos}) AS ambos,
               count(*) FILTER (COMPARACION_OSCAR = 'coincide') / nullif(count(*) FILTER ({ambos}), 0) AS mismo_nivel,
               avg((PRED_OSCAR - PRED_ABSTENCION_2027) * 100) FILTER ({ambos}) AS dif_media_pp,
               count(*) FILTER (RISK_LEVEL = 'ALTO') AS alto_oficial, count(*) FILTER (NIVEL_OSCAR = 'ALTO') AS alto_oscar,
               count(*) FILTER (COMPARACION_OSCAR = 'solo_oscar') AS solo_oscar
        FROM s WHERE {where} AND {unidad[0]} IS NOT NULL GROUP BY 1 HAVING ambos > 0
        ORDER BY mismo_nivel, ambos DESC""", params)
    cfg = json.loads(OSCAR_CONFIG.read_text()) if OSCAR_CONFIG.exists() else {}
    umbrales = {k: {q: round(v * 100, 2) for q, v in cfg.get(f"umbrales_{k}", {}).items()} for k in ("oficial", "oscar")}
    return {"kpis": kpis, "matriz": matriz, "motivos": motivos, "por_unidad": por_unidad, "umbrales": umbrales,
            "nacional": {k: cfg.get(k) for k in ("coincidencia_esperada_al_azar", "coincidencia_top10", "spearman_estimaciones")},
            "bbox": bbox(edo)}


@app.get("/tiles/secciones.pmtiles")
def tiles():
    return FileResponse(TILES_PATH, media_type="application/octet-stream")


# Al final, para que no tape /api ni /tiles. Sin build de Astro, sólo responde la API.
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
