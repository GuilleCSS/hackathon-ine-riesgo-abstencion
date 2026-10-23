"""Descomposición de la abstención por edad (y sexo).

Preguntas:
1. ¿Cómo cambia la participación con la edad? Curva por edad simple (18 a 90+), por
   sexo y por tipo de sección, desde los ZIP originales (sección × sexo × edad).
2. ¿Por qué cambió la abstención entre elecciones del mismo tipo? Descomposición de
   Kitagawa: parte por composición (el electorado envejece) y parte por comportamiento
   (cada grupo de edad vota distinto).
3. ¿Qué tanto explica la estructura de edad las diferencias entre secciones y entidades?
   Abstención esperada si cada grupo votara como el promedio nacional de ese año.
4. ¿Las secciones ALTO del semáforo 2027 son más jóvenes? ¿Qué parte de su brecha con
   las BAJO explica la edad?

Abstención = NV / (SV + NV), como en todo el pipeline: los pesos de cada grupo son su
parte de SV + NV (personas con participación conocida). Sólo lee salidas existentes.

Uso:
    python src/descomposicion_edad/01_descomponer_edad.py
"""
from pathlib import Path
import json
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
RISK_PATH = ROOT / "data" / "processed" / "sensitivity_2027" / "section_sensitivity_2027.parquet"
OUT = ROOT / "reports" / "descomposicion_edad"
OUT_DATA = ROOT / "data" / "processed" / "descomposicion_edad"
YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
TYPE = {2009: "intermedia", 2012: "presidencial", 2015: "intermedia", 2018: "presidencial", 2021: "intermedia", 2024: "presidencial"}
GROUPS = ["18_24", "25_34", "35_44", "45_59", "60_plus"]
LABEL = {"18_24": "18–24", "25_34": "25–34", "35_44": "35–44", "45_59": "45–59", "60_plus": "60+"}
SEXES = {0: "Hombres", 1: "Mujeres", 2: "No binario"}
# Mismo tipo de elección: consecutivas y de largo plazo.
PAIRS = [(2009, 2015), (2015, 2021), (2009, 2021), (2012, 2018), (2018, 2024), (2012, 2024)]
MAX_AGE = 90  # 90 = 90 años o más


def curva_por_edad():
    """Agrega los ZIP originales a año × tipo de sección × sexo × edad simple."""
    parts = []
    for year in YEARS:
        with zipfile.ZipFile(RAW / f"DatosAbiertos_DECEyEC_ConteosCensales{year}.zip") as zf:
            for name in sorted(n for n in zf.namelist() if n.lower().endswith(".csv")):
                with zf.open(name) as raw:
                    d = pd.read_csv(raw, usecols=["TIPOSEC", "SEXO", "EDAD", "LN", "SV", "NV", "NS"],
                                    encoding="utf-8-sig")
                d["EDAD"] = d["EDAD"].clip(upper=MAX_AGE)
                parts.append(d.groupby(["TIPOSEC", "SEXO", "EDAD"], as_index=False).sum().assign(AELEC=year))
        print(f"  {year}: curva por edad lista")
    c = pd.concat(parts).groupby(["AELEC", "TIPOSEC", "SEXO", "EDAD"], as_index=False).sum()
    c["SEXO"] = c["SEXO"].map(SEXES)
    return c


def con_tasa(d):
    d = d.copy()
    d["abstencion"] = d["NV"] / (d["SV"] + d["NV"])
    return d


def tasas_y_pesos(m):
    """Por año y grupo de edad: peso en SV + NV y abstención (nacional)."""
    s = m.groupby("AELEC")[[f"{v}_{g}" for g in GROUPS for v in ("SV", "NV")]].sum()
    rows = []
    for year, r in s.iterrows():
        known = sum(r[f"SV_{g}"] + r[f"NV_{g}"] for g in GROUPS)
        for g in GROUPS:
            k = r[f"SV_{g}"] + r[f"NV_{g}"]
            rows.append({"anio": year, "tipo": TYPE[year], "grupo": LABEL[g], "peso": k / known, "abstencion": r[f"NV_{g}"] / k})
    return pd.DataFrame(rows)


def kitagawa(t, pairs=PAIRS):
    """Cambio de abstención = composición + comportamiento (simétrico y exacto)."""
    rows = []
    for a, b in pairs:
        x, y = t[t["anio"].eq(a)].set_index("grupo"), t[t["anio"].eq(b)].set_index("grupo")
        for g in x.index:
            rows.append({"de": a, "a": b, "tipo": TYPE[a], "grupo": g,
                         "composicion_pp": (y.at[g, "peso"] - x.at[g, "peso"]) * (x.at[g, "abstencion"] + y.at[g, "abstencion"]) / 2 * 100,
                         "comportamiento_pp": (y.at[g, "abstencion"] - x.at[g, "abstencion"]) * (x.at[g, "peso"] + y.at[g, "peso"]) / 2 * 100})
        total_a = (x["peso"] * x["abstencion"]).sum() * 100
        total_b = (y["peso"] * y["abstencion"]).sum() * 100
        rows.append({"de": a, "a": b, "tipo": TYPE[a], "grupo": "Total", "abstencion_de": total_a, "abstencion_a": total_b,
                     "cambio_pp": total_b - total_a})
    d = pd.DataFrame(rows)
    sums = d[d["grupo"].ne("Total")].groupby(["de", "a"])[["composicion_pp", "comportamiento_pp"]].sum()
    tot = d["grupo"].eq("Total")
    d.loc[tot, ["composicion_pp", "comportamiento_pp"]] = sums.loc[list(zip(d.loc[tot, "de"], d.loc[tot, "a"]))].to_numpy()
    assert np.allclose(d.loc[tot, "composicion_pp"] + d.loc[tot, "comportamiento_pp"], d.loc[tot, "cambio_pp"])
    return d


def esperada_por_edad(m, t):
    """Abstención que tendría cada sección si cada grupo votara como el promedio nacional del año."""
    rates = t.pivot(index="anio", columns="grupo", values="abstencion")
    m = m.copy()
    known = sum(m[f"SV_{g}"] + m[f"NV_{g}"] for g in GROUPS)
    m["CONOCIDOS"] = known
    m["ESPERADA"] = sum((m[f"SV_{g}"] + m[f"NV_{g}"]) / known * m["AELEC"].map(rates[LABEL[g]]) for g in GROUPS)
    m["JOVENES"] = (m["SV_18_24"] + m["NV_18_24"]) / known
    m["MAYORES"] = (m["SV_60_plus"] + m["NV_60_plus"]) / known
    return m.loc[known.gt(0) & m["PCT_ABSTENCION"].notna()]


def wvar(x, w):
    mu = np.average(x, weights=w)
    return np.average((x - mu) ** 2, weights=w)


def estandarizacion(s):
    rows = []
    for year, d in s.groupby("AELEC"):
        w = d["CONOCIDOS"]
        cov = np.average((d["PCT_ABSTENCION"] - np.average(d["PCT_ABSTENCION"], weights=w))
                         * (d["ESPERADA"] - np.average(d["ESPERADA"], weights=w)), weights=w)
        r2 = cov ** 2 / (wvar(d["PCT_ABSTENCION"], w) * wvar(d["ESPERADA"], w))
        rows.append({"anio": year, "tipo": TYPE[year], "secciones": len(d),
                     "de_observada_pp": np.sqrt(wvar(d["PCT_ABSTENCION"], w)) * 100,
                     "de_esperada_por_edad_pp": np.sqrt(wvar(d["ESPERADA"], w)) * 100, "r2": r2})
    return pd.DataFrame(rows)


def por_entidad(s, t, years=(2021, 2024)):
    rows = []
    for year in years:
        d = s[s["AELEC"].eq(year)]
        g = d.groupby("EDONOM")
        obs = g["NV"].sum() / (g["SV"].sum() + g["NV"].sum())
        esp = g.apply(lambda x: np.average(x["ESPERADA"], weights=x["CONOCIDOS"]), include_groups=False)
        jov = (g["NV_18_24"].sum() / (g["SV_18_24"].sum() + g["NV_18_24"].sum())
               - g["NV_60_plus"].sum() / (g["SV_60_plus"].sum() + g["NV_60_plus"].sum()))
        part = pd.DataFrame({"anio": year, "observada": obs, "esperada_por_edad": esp, "brecha_jovenes_mayores_pp": jov * 100})
        part["diferencia_no_explicada_pp"] = (part["observada"] - part["esperada_por_edad"]) * 100
        rows.append(part.reset_index().rename(columns={"EDONOM": "entidad"}))
    return pd.concat(rows, ignore_index=True).sort_values(["anio", "diferencia_no_explicada_pp"], ascending=[True, False])


def por_nivel(s):
    if not RISK_PATH.exists():
        return pd.DataFrame(), {}
    risk = pd.read_parquet(RISK_PATH, columns=["SECTION_KEY", "RISK_LEVEL"])
    d = s[s["AELEC"].eq(2021)].merge(risk, on="SECTION_KEY")
    g = d.groupby("RISK_LEVEL")
    out = pd.DataFrame({
        "secciones": g.size(),
        "jovenes_18_24": g.apply(lambda x: np.average(x["JOVENES"], weights=x["CONOCIDOS"]), include_groups=False),
        "mayores_60": g.apply(lambda x: np.average(x["MAYORES"], weights=x["CONOCIDOS"]), include_groups=False),
        "observada_2021": g["NV"].sum() / (g["SV"].sum() + g["NV"].sum()),
        "esperada_por_edad_2021": g.apply(lambda x: np.average(x["ESPERADA"], weights=x["CONOCIDOS"]), include_groups=False),
    }).reindex(["BAJO", "MEDIO", "ALTO"]).rename_axis("nivel").reset_index()
    gap_obs = out.set_index("nivel").loc["ALTO", "observada_2021"] - out.set_index("nivel").loc["BAJO", "observada_2021"]
    gap_esp = out.set_index("nivel").loc["ALTO", "esperada_por_edad_2021"] - out.set_index("nivel").loc["BAJO", "esperada_por_edad_2021"]
    return out, {"brecha_alto_bajo_pp": gap_obs * 100, "brecha_explicada_por_edad_pp": gap_esp * 100,
                 "parte_explicada_por_edad": gap_esp / gap_obs}


def salto_65(total, por_sexo, por_tipo):
    """Cambio de abstención de los 64 a los 65 años frente a la pendiente normal de 61–64 y 67–70."""
    rows = []
    series = [("Total", total)] + [(s, por_sexo[por_sexo["SEXO"].eq(s)]) for s in ("Hombres", "Mujeres")] \
        + [(f"Tipo {k}", por_tipo[por_tipo["TIPOSEC"].eq(k)]) for k in ("U", "M", "R")]
    for name, d in series:
        for year, g in d.groupby("AELEC"):
            v = g.set_index("EDAD")["abstencion"] * 100
            normal = np.mean([v[a] - v[a - 1] for a in [*range(61, 65), *range(67, 71)]])
            rows.append({"anio": year, "grupo": name, "salto_65_pp": v[65] - v[64], "pendiente_normal_pp": normal})
    return pd.DataFrame(rows)


def pct(v, d=1):
    return f"{v * 100:.{d}f}%"


def main():
    print("\n=== Descomposición de la abstención por edad ===")
    if not MASTER_PATH.exists():
        raise FileNotFoundError(f"No existe {MASTER_PATH.relative_to(ROOT)}. Ejecuta primero src/02_build_master.py")
    OUT.mkdir(parents=True, exist_ok=True)
    OUT_DATA.mkdir(parents=True, exist_ok=True)

    curva = curva_por_edad()
    total = con_tasa(curva.groupby(["AELEC", "EDAD"], as_index=False)[["LN", "SV", "NV", "NS"]].sum()).assign(SEXO="Total")
    por_sexo = con_tasa(curva[curva["SEXO"].ne("No binario")].groupby(["AELEC", "SEXO", "EDAD"], as_index=False)[["LN", "SV", "NV", "NS"]].sum())
    por_tipo = con_tasa(curva.groupby(["AELEC", "TIPOSEC", "EDAD"], as_index=False)[["LN", "SV", "NV", "NS"]].sum())
    curva_out = pd.concat([total, por_sexo], ignore_index=True)
    curva_out.insert(1, "tipo", curva_out["AELEC"].map(TYPE))

    cols = ["AELEC", "SECTION_KEY", "EDONOM", "SV", "NV", "PCT_ABSTENCION"] + [f"{v}_{g}" for g in GROUPS for v in ("SV", "NV")]
    m = pd.read_csv(MASTER_PATH, usecols=cols, dtype={"SECTION_KEY": str}, low_memory=False)
    t = tasas_y_pesos(m)
    k = kitagawa(t)
    s = esperada_por_edad(m, t)
    est = estandarizacion(s)
    ent = por_entidad(s, t)
    niv, gap = por_nivel(s)
    s65 = salto_65(total, por_sexo, por_tipo)

    outputs = {"01_curva_por_edad.csv": curva_out, "02_curva_por_tipo_seccion.csv": por_tipo,
               "03_tasas_y_pesos_por_grupo.csv": t, "04_descomposicion_kitagawa.csv": k,
               "05_estandarizacion_secciones.csv": est, "06_por_entidad.csv": ent, "07_por_nivel_riesgo.csv": niv, "08_salto_65.csv": s65}
    for name, df in outputs.items():
        df.to_csv(OUT / name, index=False)
    s.loc[s["AELEC"].isin([2021, 2024]), ["SECTION_KEY", "AELEC", "PCT_ABSTENCION", "ESPERADA", "JOVENES", "MAYORES"]] \
        .to_parquet(OUT_DATA / "secciones_edad.parquet", index=False)

    # ---------------------------------------------------------------- Lectura
    tot = k[k["grupo"].eq("Total")].set_index(["de", "a"])
    pairs_long = [(2009, 2021), (2012, 2024)]
    gap_years = t.pivot(index="anio", columns="grupo", values="abstencion")
    brecha = ((gap_years["18–24"] - gap_years["60+"]) * 100).round(1).to_dict()
    curva_total = total.set_index(["AELEC", "EDAD"])["abstencion"]
    sexo = por_sexo.pivot_table(index=["AELEC", "EDAD"], columns="SEXO", values="abstencion")
    brecha_sexo = (sexo["Hombres"] - sexo["Mujeres"]) * 100  # positivo = los hombres se abstienen más
    nacional_sexo = por_sexo.groupby(["AELEC", "SEXO"])[["SV", "NV"]].sum()
    nacional_sexo = (nacional_sexo["NV"] / (nacional_sexo["SV"] + nacional_sexo["NV"])).unstack()
    edad_min = {y: int(curva_total.loc[y].loc[25:85].idxmin()) for y in YEARS}
    summary = {
        "brecha_18_24_menos_60_pp": brecha,
        "edad_con_menos_abstencion": edad_min,
        "largo_plazo": {f"{a}-{b}": {k2: round(float(tot.loc[(a, b), k2]), 2) for k2 in ("cambio_pp", "composicion_pp", "comportamiento_pp")}
                        for a, b in pairs_long},
        "r2_edad_secciones": est.set_index("anio")["r2"].round(3).to_dict(),
        "brecha_hombres_menos_mujeres_pp": ((nacional_sexo["Hombres"] - nacional_sexo["Mujeres"]) * 100).round(1).to_dict(),
        "salto_65_pp": s65[s65["grupo"].eq("Total")].set_index("anio")["salto_65_pp"].round(1).to_dict(),
        "brecha_sexo_max_2024": {"edad": int(brecha_sexo.loc[2024].idxmax()), "pp": round(float(brecha_sexo.loc[2024].max()), 1)},
        **{k2: round(float(v), 3) for k2, v in gap.items()},
    }
    (OUT / "descomposicion_config.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    def fila_curva(year, ages=(18, 19, 20, 25, 30, 40, 50, 60, 70, 80, 90)):
        return " | ".join(pct(curva_total.loc[(year, a)], 0) for a in ages)

    lines = [
        "# Descomposición de la abstención por edad",
        "",
        "Generado por `src/descomposicion_edad/01_descomponer_edad.py` desde los ZIP originales (curva por",
        "edad simple) y la base maestra (grupos de edad por sección). Abstención = NV / (SV + NV).",
        "",
        "## 1. La curva de participación por edad",
        "",
        "| Año | 18 | 19 | 20 | 25 | 30 | 40 | 50 | 60 | 70 | 80 | 90+ |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
        *[f"| {y} ({TYPE[y][:5]}.) | {fila_curva(y)} |" for y in YEARS],
        "",
        "Abstención por grupo y su peso entre quienes tienen participación conocida:",
        "",
        "| Año | " + " | ".join(LABEL.values()) + " | Brecha 18–24 vs. 60+ |",
        "|---|---|---|---|---|---|---|",
        *[f"| {y} | " + " | ".join(f"{pct(r.abstencion)} ({pct(r.peso, 0)})" for r in t[t['anio'].eq(y)].itertuples())
          + f" | {brecha[y]:+.1f} pp |" for y in YEARS],
        "",
        "## 2. ¿Por qué cambió la abstención? (Kitagawa)",
        "",
        "Composición = efecto de que cambie el peso de cada grupo (el electorado envejece).",
        "Comportamiento = efecto de que cada grupo se abstenga más o menos. Suman el cambio total.",
        "",
        "| Periodo | Tipo | Abstención | Cambio | Composición | Comportamiento |",
        "|---|---|---|---|---|---|",
        *[f"| {a}→{b} | {TYPE[a]} | {r.abstencion_de:.1f}% → {r.abstencion_a:.1f}% | {r.cambio_pp:+.2f} pp | {r.composicion_pp:+.2f} pp | {r.comportamiento_pp:+.2f} pp |"
          for (a, b), r in tot.iterrows()],
        "",
        "Contribución de cada grupo al comportamiento (pp):",
        "",
        "| Periodo | " + " | ".join(LABEL.values()) + " |",
        "|---|---|---|---|---|---|",
        *[f"| {a}→{b} | " + " | ".join(f"{v:+.2f}" for v in k[(k['de'].eq(a)) & (k['a'].eq(b)) & k['grupo'].ne('Total')]['comportamiento_pp'])
          + " |" for a, b in PAIRS],
        "",
        "## 3. ¿Cuánto explica la edad las diferencias entre secciones?",
        "",
        "Abstención esperada de cada sección si cada grupo de edad votara como el promedio nacional del año.",
        "",
        "| Año | Secciones | Desviación de la observada | Desviación de la esperada por edad | R² |",
        "|---|---|---|---|---|",
        *[f"| {r.anio} | {r.secciones:,} | {r.de_observada_pp:.1f} pp | {r.de_esperada_por_edad_pp:.1f} pp | {r.r2:.3f} |" for r in est.itertuples()],
        "",
        "Entidades con más abstención de la que explica su estructura de edad (2024):",
        "",
        "| Entidad | Observada | Esperada por edad | No explicada | Brecha 18–24 vs. 60+ |",
        "|---|---|---|---|---|",
        *[f"| {r.entidad} | {pct(r.observada)} | {pct(r.esperada_por_edad)} | {r.diferencia_no_explicada_pp:+.1f} pp | {r.brecha_jovenes_mayores_pp:+.1f} pp |"
          for r in ent[ent['anio'].eq(2024)].head(8).itertuples()],
        "",
        "Y las de menos:",
        "",
        "| Entidad | Observada | Esperada por edad | No explicada | Brecha 18–24 vs. 60+ |",
        "|---|---|---|---|---|",
        *[f"| {r.entidad} | {pct(r.observada)} | {pct(r.esperada_por_edad)} | {r.diferencia_no_explicada_pp:+.1f} pp | {r.brecha_jovenes_mayores_pp:+.1f} pp |"
          for r in ent[ent['anio'].eq(2024)].tail(5).itertuples()],
        "",
    ]
    if len(niv):
        lines += [
            "## 4. ¿Las secciones ALTO del semáforo 2027 son más jóvenes?",
            "",
            "| Nivel 2027 | Secciones | 18–24 | 60+ | Abstención 2021 | Esperada por edad 2021 |",
            "|---|---|---|---|---|---|",
            *[f"| {r.nivel} | {r.secciones:,} | {pct(r.jovenes_18_24)} | {pct(r.mayores_60)} | {pct(r.observada_2021)} | {pct(r.esperada_por_edad_2021)} |"
              for r in niv.itertuples()],
            "",
            f"La brecha de abstención 2021 entre ALTO y BAJO es de {gap['brecha_alto_bajo_pp']:.1f} pp; la estructura de edad",
            f"explica {gap['brecha_explicada_por_edad_pp']:.1f} pp ({pct(gap['parte_explicada_por_edad'])}).",
            "",
        ]
    ages = [18, 20, 25, 30, 40, 50, 60, 70, 80, 90]
    lines += [
        "## 5. Brecha por sexo",
        "",
        "Abstención de hombres menos la de mujeres (pp; positivo = los hombres se abstienen más):",
        "",
        "| Año | Nacional | " + " | ".join(f"{a}{'+' if a == MAX_AGE else ''}" for a in ages) + " |",
        "|---|---|" + "---|" * len(ages),
        *[f"| {y} | {(nacional_sexo.at[y, 'Hombres'] - nacional_sexo.at[y, 'Mujeres']) * 100:+.1f} | "
          + " | ".join(f"{brecha_sexo.loc[(y, a)]:+.1f}" for a in ages) + " |" for y in YEARS],
        "",
        "## 6. Salto a los 65 años",
        "",
        "Cambio de abstención de los 64 a los 65 años, frente a la pendiente normal entre un año de edad y el",
        "siguiente (promedio de 61–64 y 67–70):",
        "",
        "| Grupo | " + " | ".join(str(y) for y in YEARS) + " |",
        "|---|" + "---|" * len(YEARS),
        *[f"| {g} | " + " | ".join(f"{r.salto_65_pp:+.1f} ({r.pendiente_normal_pp:+.1f})" for r in d.sort_values("anio").itertuples()) + " |"
          for g, d in s65.groupby("grupo", sort=False)],
        "",
        "Entre paréntesis, la pendiente normal. En 2024 la abstención cae 2.5 pp justo a los 65 años, en hombres,",
        "mujeres y en secciones urbanas, mixtas y rurales; de 2009 a 2018 los saltos son pequeños (−0.1 a −0.9 pp).",
        "Coincide con la edad de",
        "acceso a la Pensión para el Bienestar de las Personas Adultas Mayores, que según la prensa se aplica desde",
        "los 65 años a partir de julio de 2021 (reforma constitucional en 2024). En 2021 ya aparece un salto menor",
        "(−1.2 pp), anterior a ese cambio (la elección fue en junio). Es una asociación, no una prueba causal, y",
        "conviene verificar el calendario del programa con fuentes oficiales.",
        "",
        "## Conclusiones",
        "",
        "1. **La curva de edad tiene una forma estable.** Los de 18 años votan más que los de 19 a 30 (efecto del",
        "   primer voto), la abstención llega a su máximo cerca de los 25, baja con la edad hasta su mínimo entre los",
        f"   {min(edad_min.values())} y {max(edad_min.values())} años y vuelve a subir en edades avanzadas.",
        "2. **El electorado envejece y eso baja la abstención, pero poco.** De 2009 a 2021 (intermedias) la",
        f"   composición explica {tot.loc[(2009, 2021), 'composicion_pp']:+.2f} pp de {tot.loc[(2009, 2021), 'cambio_pp']:+.2f} pp; de 2012 a 2024 (presidenciales)",
        f"   {tot.loc[(2012, 2024), 'composicion_pp']:+.2f} pp. Lo demás es comportamiento.",
        f"3. **En presidenciales el comportamiento empeoró más de lo que se ve:** {tot.loc[(2012, 2024), 'comportamiento_pp']:+.2f} pp de 2012 a 2024,",
        "   disimulado por el envejecimiento. De 2018 a 2024 subió la abstención en todos los grupos menos en 60+,",
        f"   y la brecha entre 18–24 y 60+ llegó a {brecha[2024]:+.1f} pp, la mayor del periodo.",
        "4. **Los hombres se abstienen más que las mujeres**, sobre todo entre los 20 y los 50 años",
        f"   (hasta {summary['brecha_sexo_max_2024']['pp']:+.1f} pp a los {summary['brecha_sexo_max_2024']['edad']} en 2024); la brecha se cierra cerca de los 70 y se",
        "   invierte en edades avanzadas.",
        "5. **La edad explica poco las diferencias entre territorios.** La abstención esperada por la estructura de",
        f"   edad varía 1–1.4 pp entre secciones contra 9–13 pp de la observada (R² ≤ {est['r2'].max():.2f}). Entre las secciones",
    ]
    if gap:
        lines += [
            f"   ALTO y BAJO de 2027 hay {gap['brecha_alto_bajo_pp']:.1f} pp de diferencia, y la edad explica {gap['brecha_explicada_por_edad_pp']:.1f} pp. El riesgo",
            "   territorial depende sobre todo del lugar, no de que su población sea joven.",
        ]
    lines += [
        "6. **La abstención cae de golpe a los 65 años desde 2021** (−2.5 pp en 2024; antes, como mucho −0.9 pp),",
        "   la edad de acceso a la pensión universal para adultos mayores. Es una asociación por verificar.",
        "",
        "Implicaciones: (a) la edad no aporta al modelo territorial 2027 (coherente con que la historia de cada",
        "sección domine); (b) sí sirve para explicar cambios nacionales y para focalizar mensajes por grupo: jóvenes",
        "de 19 a 34 años y hombres son quienes más se abstienen en todas las elecciones.",
        "",
    ]
    (OUT / "DESCOMPOSICION_EDAD.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Salida: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
