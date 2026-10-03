"""Calendario de elecciones locales concurrentes con las federales (2009–2027).

Para cada estado y elección federal indica si hubo elecciones locales el mismo
día y si entre ellas estaba la gubernatura (o la jefatura de gobierno de la
CDMX). Fuente: Wikipedia en español, leída con su API:

- "Anexo:Elecciones locales de México": estados con elección en la fecha de la
  jornada federal (se excluyen extraordinarias y judiciales).
- La página de cada elección estatal: gubernatura si su ficha o sus secciones
  lo indican (campos `cargo`/`endisputa` o una sección de gubernatura).

Es una fuente secundaria: el resultado queda marcado como pendiente de
validación contra los calendarios del INE y de los institutos locales.

Uso: python src/clustering/03_build_calendario_concurrente.py
"""
from pathlib import Path
import csv
import json
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "external" / "calendario_concurrente.csv"
API = "https://es.wikipedia.org/w/api.php"

FEDERAL_DAYS = {
    2009: "5 de julio", 2012: "1 de julio", 2015: "7 de junio", 2018: "1 de julio",
    2021: "6 de junio", 2024: "2 de junio", 2027: "6 de junio",
}
# Gubernaturas por año según los textos de las elecciones federales y los ciclos
# conocidos; si la extracción no coincide, el script falla en lugar de escribir.
EXPECTED_GOVERNORS = {2009: 6, 2012: 7, 2015: 9, 2018: 9, 2021: 15, 2024: 9, 2027: 17}

STATES = {
    1: "Aguascalientes", 2: "Baja California", 3: "Baja California Sur", 4: "Campeche",
    5: "Coahuila", 6: "Colima", 7: "Chiapas", 8: "Chihuahua", 9: "Ciudad de México",
    10: "Durango", 11: "Guanajuato", 12: "Guerrero", 13: "Hidalgo", 14: "Jalisco",
    15: "Estado de México", 16: "Michoacán", 17: "Morelos", 18: "Nayarit", 19: "Nuevo León",
    20: "Oaxaca", 21: "Puebla", 22: "Querétaro", 23: "Quintana Roo", 24: "San Luis Potosí",
    25: "Sinaloa", 26: "Sonora", 27: "Tabasco", 28: "Tamaulipas", 29: "Tlaxcala",
    30: "Veracruz", 31: "Yucatán", 32: "Zacatecas",
}
ALIASES = {"Distrito Federal": "Ciudad de México"}


def api(params):
    q = urllib.parse.urlencode({**params, "format": "json", "formatversion": 2, "redirects": 1})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "hackathon-ine-calendario/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def strip_refs(text):
    text = re.sub(r"<ref[^>]*/>", "", text)
    return re.sub(r"<ref.*?</ref>", "", text, flags=re.S)


def concurrent_pages():
    annex = api({"action": "parse", "page": "Anexo:Elecciones locales de México", "prop": "wikitext"})
    text = strip_refs(annex["parse"]["wikitext"])
    found = {}
    for year, day in FEDERAL_DAYS.items():
        block = re.search(r"\n\|\s*'''(?:\[\[[^|\]]*\|)?%d(?:\]\])?'''[^\n]*\n(.*?)\n\|-" % year, text, re.S)
        bullets = [l for l in block.group(1).split("\n") if l.lstrip().startswith("*")]
        hit = [l for l in bullets if re.search(r"'''\s*%s\s*:?\s*'''" % re.escape(day), l)]
        if len(hit) != 1:
            raise RuntimeError(f"{year}: no encontré una sola línea para el {day}")
        for target, label in re.findall(r"\[\[([^|\]]+)\|([^\]]+)\]\]", hit[0]):
            if "xtraordinaria" in target or "udicial" in target:
                continue
            found[(year, ALIASES.get(label.strip(), label.strip()))] = target
    return found


def page_texts(titles):
    texts = {}
    titles = sorted(set(titles))
    for i in range(0, len(titles), 40):
        data = api({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                    "titles": "|".join(titles[i:i + 40])})
        redirects = {r["to"]: r["from"] for r in data["query"].get("redirects", [])}
        for p in data["query"]["pages"]:
            texts[redirects.get(p["title"], p["title"])] = p["revisions"][0]["slots"]["main"]["content"]
        time.sleep(1)
    return texts


GOV = r"(gobernador|gubernatura|jefe de gobierno|jefatura de gobierno)"


def has_governor(text):
    t = text.lower()
    return bool(
        re.search(r"\|\s*(cargo|endisputa)\s*=\s*[^\n]*" + GOV, t)
        or re.search(r"\n=+\s*(elecci[oó]n (a|de|para) )?" + GOV, t)
    )


def main():
    print("\n=== Calendario de elecciones locales concurrentes ===")
    pages = concurrent_pages()
    unknown = {s for _, s in pages} - set(STATES.values())
    if unknown:
        raise RuntimeError(f"Estados sin clave INE: {unknown}")
    texts = page_texts(pages.values())

    rows = []
    for year in FEDERAL_DAYS:
        for code, name in STATES.items():
            page = pages.get((year, name))
            rows.append({
                "ANIO": year,
                "EDOCVE": code,
                "ESTADO": name,
                "LOCAL_CONCURRENTE": int(page is not None),
                "GUBERNATURA_CONCURRENTE": int(page is not None and has_governor(texts[page])),
                "FUENTE": f"https://es.wikipedia.org/wiki/{page.replace(' ', '_')}" if page else "Anexo:Elecciones locales de México (sin elección ese día)",
                "VALIDADO": "pendiente",
            })

    for year, expected in EXPECTED_GOVERNORS.items():
        got = sum(r["GUBERNATURA_CONCURRENTE"] for r in rows if r["ANIO"] == year)
        if got != expected:
            raise RuntimeError(f"{year}: {got} gubernaturas detectadas, se esperaban {expected}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    for year in FEDERAL_DAYS:
        y = [r for r in rows if r["ANIO"] == year]
        print(f"  {year}: {sum(r['LOCAL_CONCURRENTE'] for r in y):>2} con elección local · "
              f"{sum(r['GUBERNATURA_CONCURRENTE'] for r in y):>2} con gubernatura")
    print(f"Escrito: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
