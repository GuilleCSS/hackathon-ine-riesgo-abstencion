"""Prueba de humo de la API contra un servidor corriendo (sólo biblioteca estándar).

    docker compose up -d api && python api/test_api.py            # o API_URL=http://... python api/test_api.py
"""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("API_URL", "http://localhost:8000")


def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def data(path):
    status, _, body = get(path)
    assert status == 200, (path, status, body[:200])
    return json.loads(body)


def main():
    # Universo del semáforo con geometría: 54,448 de 73,268 secciones cartográficas (74.3%).
    r = data("/api/resumen")
    k = r["kpis"]
    assert k["secciones"] == 54448, k
    assert k["cobertura"] == {"cartografia": 73268, "con_estimacion": 54448, "ns_alto": 9087}, k["cobertura"]
    assert sum(e["secciones"] for e in r["entidades"]) == 54448
    assert len(r["municipios"]) == 30 and len(r["bbox"]) == 4

    niveles = sum(data(f"/api/resumen?nivel={n}")["kpis"]["secciones"] for n in ("BAJO", "MEDIO", "ALTO"))
    assert niveles == 54448, niveles
    assert data("/api/resumen?nivel=ALTO")["kpis"]["alto"] == k["alto"]
    # Con umbrales congelados, bajar 5 pp a las ALTO deja menos secciones en ALTO.
    assert data("/api/resumen?escenario=S3")["kpis"]["alto"] < k["alto"]

    cdmx = data("/api/resumen?edo=9")
    assert cdmx["kpis"]["secciones"] < k["secciones"] and cdmx["entidades"][0]["edo"] == 9

    s = data("/api/secciones/09-4882")
    assert s["estimacion"]["pred"] == 46.7 and s["estimacion"]["nivel"] == "MEDIO", s["estimacion"]
    assert [h["abstencion"] for h in s["historia"]] == [67.8, 39.4, 66.4, 40.2, 52.1, 37.0]
    assert len(s["escenarios"]) == 4

    # Validación de entradas: nada llega a SQL sin pasar por los tipos.
    for bad in ["/api/resumen?escenario=S9", "/api/resumen?edo=40", "/api/resumen?nivel=X",
                "/api/secciones/09-4882'--", "/api/entidades/0/municipios"]:
        assert get(bad)[0] in (404, 422), bad
    assert get("/api/secciones/99-9999")[0] == 404

    status, headers, body = get("/tiles/secciones.pmtiles", {"Range": "bytes=0-126"})
    assert status == 206 and body[:7] == b"PMTiles", status

    _, headers, _ = get("/api/salud")
    csp = headers["content-security-policy"]
    assert "default-src 'self'" in csp and "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp, csp
    assert headers["x-content-type-options"] == "nosniff"
    print("API OK")


if __name__ == "__main__":
    main()
