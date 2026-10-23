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
TILES_PATH = WEB_DATA / "secciones.pmtiles"
SCENARIO_CONFIG = ROOT / "reports" / "scenarios_2027" / "scenario_config.json"
DIST = ROOT / "web" / "dist"

for path in (TABLE_PATH, TILES_PATH, SCENARIO_CONFIG):
    if not path.exists():
        raise FileNotFoundError(f"No existe {path.relative_to(ROOT)}. Ejecuta primero src/21_export_web.py")

Escenario = Literal["S0", "S1", "S2", "S3"]
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


def scope_filter(edo, mun):
    cond, params = ["EN_CARTOGRAFIA"], []
    if edo is not None:
        cond.append("EDOCVE = ?"); params.append(edo)
    if mun is not None:
        cond.append("MPIOCVE = ?"); params.append(mun)
    return cond, params


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


@app.get("/tiles/secciones.pmtiles")
def tiles():
    return FileResponse(TILES_PATH, media_type="application/octet-stream")


# Al final, para que no tape /api ni /tiles. Sin build de Astro, sólo responde la API.
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
