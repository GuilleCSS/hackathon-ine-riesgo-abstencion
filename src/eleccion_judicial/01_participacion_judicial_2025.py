"""Participación en la elección judicial 2024–2025 por sección y su relación con el riesgo 2027.

Datos: Conteos Censales de Participación Ciudadana del Proceso Electoral Extraordinario del Poder
Judicial de la Federación 2024–2025 (DatosAbiertos_DECEyEC_ConteosCensalesPJ2025.zip, publicado en
septiembre de 2026), en data/raw/pj2025/. Misma estructura que los federales (sección × sexo × edad).

Pregunta: ¿las secciones con riesgo ALTO en 2027 también se abstuvieron más en una elección atípica?
La elección judicial de 2027 se aplazó a 2028, así que no coincidirá con la intermedia.

Uso:
    python src/eleccion_judicial/01_participacion_judicial_2025.py
"""
from pathlib import Path
import json
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "data" / "raw" / "pj2025" / "DatosAbiertos_DECEyEC_ConteosCensalesPJ2025.zip"
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
RISK_PATH = ROOT / "data" / "processed" / "sensitivity_2027" / "section_sensitivity_2027.parquet"
OUT = ROOT / "reports" / "eleccion_judicial"
OUT_DATA = ROOT / "data" / "processed" / "eleccion_judicial"


def secciones_2025():
    parts = []
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for name in sorted(n for n in zf.namelist() if n.lower().endswith(".csv")):
            with zf.open(name) as raw:
                d = pd.read_csv(raw, usecols=["EDOCVE", "EDONOM", "SECCION", "LN", "SV", "NV", "NS"], encoding="utf-8-sig")
            parts.append(d.groupby(["EDOCVE", "EDONOM", "SECCION"], as_index=False)[["LN", "SV", "NV", "NS"]].sum())
    s = pd.concat(parts, ignore_index=True)
    s["SECTION_KEY"] = s["EDOCVE"].astype(int).map("{:02d}".format) + "-" + s["SECCION"].astype(int).map("{:04d}".format)
    s["ABST_2025"] = s["NV"] / (s["SV"] + s["NV"]).where(lambda x: x > 0)
    s["NS_2025"] = s["NS"] / s["LN"]
    return s


def main():
    print("\n=== Elección judicial 2025 ===")
    if not ZIP_PATH.exists():
        raise FileNotFoundError(f"No existe {ZIP_PATH.relative_to(ROOT)}. Descárgalo de la plataforma de Conteos Censales del INE")
    OUT.mkdir(parents=True, exist_ok=True)
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    s = secciones_2025()
    s[["SECTION_KEY", "LN", "SV", "NV", "NS", "ABST_2025", "NS_2025"]].to_parquet(OUT_DATA / "secciones_2025.parquet", index=False)

    tot = s[["LN", "SV", "NV", "NS"]].sum()
    nacional = {"secciones": int(len(s)), "lista_nominal": int(tot.LN), "abstencion": float(tot.NV / (tot.SV + tot.NV)),
                "pct_ns": float(tot.NS / tot.LN)}
    ent = s.groupby("EDONOM")[["SV", "NV"]].sum()
    ent = (ent["NV"] / ent.sum(axis=1)).rename("abstencion_2025").sort_values().reset_index()
    ent.to_csv(OUT / "01_abstencion_por_entidad.csv", index=False)

    m = pd.read_csv(MASTER_PATH, usecols=["AELEC", "SECTION_KEY", "PCT_ABSTENCION"], dtype={"SECTION_KEY": str})
    w = m.pivot_table(index="SECTION_KEY", columns="AELEC", values="PCT_ABSTENCION")
    d = s.set_index("SECTION_KEY")[["ABST_2025", "NS_2025", "SV", "NV"]].join(w[[2021, 2024]], how="inner")
    d = d[d["NS_2025"].le(0.10)].dropna()
    corr = {f"abst_{y}": round(float(d["ABST_2025"].corr(d[y], method="spearman")), 3) for y in (2021, 2024)}

    r = pd.read_parquet(RISK_PATH, columns=["SECTION_KEY", "RISK_LEVEL"]).set_index("SECTION_KEY")
    nivel = r.join(d, how="inner").groupby("RISK_LEVEL").apply(
        lambda x: pd.Series({"secciones": len(x), "abstencion_2025": x["NV"].sum() / (x["SV"].sum() + x["NV"].sum()),
                             "abstencion_2021": x[2021].mean()}), include_groups=False).reindex(["BAJO", "MEDIO", "ALTO"])
    nivel.rename_axis("nivel_2027").reset_index().to_csv(OUT / "02_por_nivel_riesgo_2027.csv", index=False)

    summary = {"nacional": nacional, "spearman_con": corr, "secciones_comparadas": int(len(d)),
               "abstencion_por_nivel_2027": nivel["abstencion_2025"].round(4).to_dict()}
    (OUT / "judicial_config.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
