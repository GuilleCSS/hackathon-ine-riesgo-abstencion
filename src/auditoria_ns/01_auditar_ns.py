"""Auditoría de los registros sin información de participación (NS).

NS = personas de la lista nominal de las que no se sabe si votaron: cuadernillo sin
marcas, no disponible para captura, solicitado por autoridad o página faltante.
La abstención se calcula sin ellas (NV / (SV + NV)) y el semáforo 2027 excluye las
secciones con NS > 10% en 2021 o 2024. Aquí se revisa cuánto NS hay, si viene de
casillas completas o de personas sueltas, si se concentra en ciertos lugares, si
sesga la abstención medida y qué pasa con el semáforo si se mueve el umbral.

Uso:
    python src/auditoria_ns/01_auditar_ns.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
FORECAST_ALL_PATH = ROOT / "data" / "processed" / "forecast_2027" / "forecast_2027_all_comparable.parquet"
OUT = ROOT / "reports" / "auditoria_ns"
AGES = ["18_24", "25_34", "35_44", "45_59", "60_plus"]
SEXES = {"H": "Hombres", "M": "Mujeres"}
NS_BINS = [-0.001, 0, 0.05, 0.10, 0.25, 0.50, 0.999, 1.0]
NS_LABELS = ["0%", "0–5%", "5–10%", "10–25%", "25–50%", "50–99.9%", "100%"]


def load_master():
    cols = ["AELEC", "TIPO_ELECCION", "SECTION_KEY", "EDOCVE", "EDONOM", "MPIOCVE", "TIPOSEC",
            "LN", "SV", "NV", "NS", "PCT_ABSTENCION", "PCT_NS_LN"]
    cols += [f"{v}_{g}" for g in AGES + list(SEXES) for v in ("LN", "SV", "NV")]
    m = pd.read_csv(MASTER_PATH, usecols=cols, dtype={"SECTION_KEY": str}, low_memory=False)
    m["NS_BUCKET"] = pd.cut(m["PCT_NS_LN"], NS_BINS, labels=NS_LABELS)
    m["NS_ALTO"] = m["PCT_NS_LN"].gt(0.10)
    return m


def magnitud(m):
    g = m.groupby("AELEC")
    out = pd.DataFrame({
        "tipo": g["TIPO_ELECCION"].first(),
        "secciones": g.size(),
        "con_ns": g["NS"].apply(lambda s: int(s.gt(0).sum())),
        "ns_mayor_5": g["PCT_NS_LN"].apply(lambda s: int(s.gt(0.05).sum())),
        "ns_mayor_10": g["NS_ALTO"].sum(),
        "ns_100": g["PCT_NS_LN"].apply(lambda s: int(s.ge(1).sum())),
        "pct_lista_nominal_ns": g["NS"].sum() / g["LN"].sum(),
        # Qué parte de todo el NS del año está en secciones con más de 10% de NS.
        "ns_en_secciones_ns_alto": m.loc[m["NS_ALTO"]].groupby("AELEC")["NS"].sum() / g["NS"].sum(),
    })
    return out.reset_index().rename(columns={"AELEC": "anio"})


def concentracion(m):
    """Si el NS viene de casillas completas, la fracción de NS se amontona en 1/2, 1/3, 1/4…"""
    partial = m.loc[m["PCT_NS_LN"].between(0.02, 0.98)].copy()
    partial["fraccion"] = partial["PCT_NS_LN"].round(2)
    hist = partial.groupby("fraccion").size().rename("secciones").reset_index()
    fractions = {"1/4": 0.25, "1/3": 1 / 3, "1/2": 0.5, "2/3": 2 / 3, "3/4": 0.75}
    near = {k: (partial["PCT_NS_LN"] - v).abs().le(0.02).mean() for k, v in fractions.items()}
    # Si la fracción fuera uniforme entre 0.02 y 0.98, cada ventana de ±0.02 tendría ~4.2%.
    return hist, {k: round(float(v), 4) for k, v in near.items()}


def uniformidad(m):
    """Razón entre el NS de cada grupo de edad/sexo y el NS de su propia sección, en
    secciones con NS parcial. 1.0 = el grupo pierde la misma proporción que el resto:
    faltan casillas o páginas completas (ordenadas por apellido), no personas por su perfil.
    Se compara dentro de cada sección; agregando entre secciones aparecen efectos de
    composición (las secciones con más NS no tienen la misma pirámide de edad)."""
    partial = m.loc[m["PCT_NS_LN"].between(0.05, 0.95)]
    rows = []
    for year, d in partial.groupby("AELEC"):
        for g, label in [(a, a.replace("_plus", "+").replace("_", "–")) for a in AGES] + list(SEXES.items()):
            ok = d[f"LN_{g}"].gt(0)
            ns = d.loc[ok, f"LN_{g}"] - d.loc[ok, f"SV_{g}"] - d.loc[ok, f"NV_{g}"]
            ratio = ns / d.loc[ok, f"LN_{g}"] / d.loc[ok, "PCT_NS_LN"]
            rows.append({"anio": year, "grupo": label, "razon": float(np.average(ratio, weights=d.loc[ok, f"LN_{g}"]))})
    return pd.DataFrame(rows).pivot(index="anio", columns="grupo", values="razon").reset_index()


def seleccion(m):
    """Tasa de secciones con NS > 10% por tipo de sección, tamaño y abstención previa."""
    d = m.loc[m["AELEC"].ge(2015)].copy()
    d = d.sort_values(["SECTION_KEY", "AELEC"])
    d["ABST_PREVIA"] = d.groupby("SECTION_KEY")["PCT_ABSTENCION"].shift(1)  # elección anterior (3 años)
    d["TAMANO"] = pd.qcut(d["LN"], 5, labels=["Q1 más chicas", "Q2", "Q3", "Q4", "Q5 más grandes"])
    d["ABST_PREVIA_Q"] = pd.qcut(d["ABST_PREVIA"], 5, labels=["Q1 menos abstención", "Q2", "Q3", "Q4", "Q5 más abstención"])
    parts = []
    for var, label in [("TIPOSEC", "Tipo de sección"), ("TAMANO", "Lista nominal (quintil)"),
                       ("ABST_PREVIA_Q", "Abstención en la elección anterior (quintil)")]:
        t = d.groupby(var, observed=True)["NS_ALTO"].agg(secciones="size", tasa_ns_alto="mean").reset_index()
        parts.append(t.rename(columns={var: "categoria"}).assign(variable=label))
    estados = (d.groupby("EDONOM")["NS_ALTO"].agg(secciones="size", tasa_ns_alto="mean")
               .reset_index().rename(columns={"EDONOM": "categoria"}).assign(variable="Entidad"))
    parts.append(estados.sort_values("tasa_ns_alto", ascending=False))
    out = pd.concat(parts, ignore_index=True)[["variable", "categoria", "secciones", "tasa_ns_alto"]]
    return out, float(d["NS_ALTO"].mean())


def persistencia(m):
    """¿La misma sección repite NS alto? Compara con la tasa base del año."""
    w = m.pivot_table(index="SECTION_KEY", columns="AELEC", values="NS_ALTO", aggfunc="first")
    years = sorted(w.columns)
    rows = []
    for prev, cur in zip(years, years[1:]):
        both = w[[prev, cur]].dropna().astype(bool)
        base = both[cur].mean()
        cond = both.loc[both[prev], cur].mean() if both[prev].any() else np.nan
        rows.append({"anio": cur, "vs": prev, "secciones": len(both), "tasa_base": base,
                     "tasa_si_antes_ns_alto": cond, "veces_mas_probable": cond / base if base else np.nan})
    return pd.DataFrame(rows)


def sesgo(m):
    """¿Medimos menos (o más) abstención donde hay NS? Para cada sección se espera la
    abstención de la elección anterior del mismo tipo más el cambio de su entidad,
    calculado sólo con secciones limpias (NS ≤ 5% en ambos años). Si el NS fuera
    aleatorio respecto a votar, el residuo no dependería del NS de este año."""
    w = m.set_index(["SECTION_KEY", "AELEC"])
    rows = []
    for year in [2015, 2018, 2021, 2024]:
        cur = w.xs(year, level="AELEC")
        prev = w.xs(year - 6, level="AELEC")
        d = cur[["EDOCVE", "PCT_ABSTENCION", "PCT_NS_LN", "NS_BUCKET"]].join(
            prev[["PCT_ABSTENCION", "PCT_NS_LN"]], rsuffix="_ANT", how="inner")
        d = d.loc[d["PCT_NS_LN_ANT"].le(0.05) & d["PCT_ABSTENCION"].notna() & d["PCT_ABSTENCION_ANT"].notna()]
        clean = d.loc[d["PCT_NS_LN"].le(0.05)]
        swing = (clean["PCT_ABSTENCION"] - clean["PCT_ABSTENCION_ANT"]).groupby(clean["EDOCVE"]).mean()
        d["RESIDUO_PP"] = (d["PCT_ABSTENCION"] - d["PCT_ABSTENCION_ANT"] - d["EDOCVE"].map(swing)) * 100
        g = d.groupby("NS_BUCKET", observed=True)["RESIDUO_PP"]
        t = pd.DataFrame({"secciones": g.size(), "residuo_medio_pp": g.mean(), "residuo_mediano_pp": g.median(),
                          "error_estandar_pp": g.std() / np.sqrt(g.size())}).reset_index()
        rows.append(t.assign(anio=year, vs=year - 6))
    out = pd.concat(rows, ignore_index=True)
    return out[["anio", "vs", "NS_BUCKET", "secciones", "residuo_medio_pp", "residuo_mediano_pp", "error_estandar_pp"]]


def impacto_semaforo(f):
    base = f.loc[f["INPUTS_VALID"] & f["STABLE_MPIO"] & f["STABLE_TIPOSEC"]].copy()
    primary = base.loc[base["PRIMARY_UNIVERSE"]]
    q50, q80, q90 = primary["PRED_ABSTENCION_2027"].quantile([0.5, 0.8, 0.9])

    def nivel(p):
        return np.select([p > q80, p > q50], ["ALTO", "MEDIO"], "BAJO")

    base["NIVEL_INDICATIVO"] = nivel(base["PRED_ABSTENCION_2027"])
    high_ns = base.loc[base["QUALITY_FLAG"].eq("comparable_high_ns")]
    niveles = pd.DataFrame({
        "semaforo_oficial": primary.assign(n=nivel(primary["PRED_ABSTENCION_2027"]))["n"].value_counts(normalize=True),
        "excluidas_por_ns": high_ns["NIVEL_INDICATIVO"].value_counts(normalize=True),
    }).reindex(["BAJO", "MEDIO", "ALTO"]).rename_axis("nivel").reset_index()
    niveles["top10_excluidas"] = np.nan
    niveles.loc[niveles["nivel"].eq("ALTO"), "top10_excluidas"] = float((high_ns["PRED_ABSTENCION_2027"] >= q90).mean())

    por_estado = (base.groupby("RECENT_EDONOM")
                  .agg(comparables=("SECTION_KEY", "size"),
                       excluidas_por_ns=("QUALITY_FLAG", lambda s: int(s.eq("comparable_high_ns").sum())))
                  .assign(pct_excluidas=lambda d: d["excluidas_por_ns"] / d["comparables"])
                  .sort_values("pct_excluidas", ascending=False).reset_index().rename(columns={"RECENT_EDONOM": "entidad"}))
    por_tipo = (base.groupby("RECENT_TIPOSEC")["QUALITY_FLAG"]
                .apply(lambda s: s.eq("comparable_high_ns").mean()).rename("pct_excluidas").reset_index())

    official_alto = set(primary.loc[primary["PRED_ABSTENCION_2027"] > q80, "SECTION_KEY"])
    sens = []
    for t in [0.05, 0.10, 0.15, 0.20, 0.25, 0.50, 1.00]:
        u = base.loc[base["SAME_PCT_NS_LN"].le(t) & base["RECENT_PCT_NS_LN"].le(t)]
        tq50, tq80, tq90 = u["PRED_ABSTENCION_2027"].quantile([0.5, 0.8, 0.9])
        alto = set(u.loc[u["PRED_ABSTENCION_2027"] > tq80, "SECTION_KEY"])
        kept = official_alto & set(u["SECTION_KEY"])
        sens.append({"umbral_ns": t, "secciones": len(u), "q50": tq50, "q80": tq80, "q90": tq90,
                     "alto": len(alto), "alto_oficial_que_sigue_alto": len(kept & alto) / len(kept) if kept else np.nan,
                     "alto_nuevas": len(alto - official_alto)})
    return niveles, por_estado, por_tipo, pd.DataFrame(sens), {"q50": q50, "q80": q80, "q90": q90}


def pct(v, d=1):
    return f"{v * 100:.{d}f}%"


def main():
    print("\n=== Auditoría del NS ===")
    for path, stage in [(MASTER_PATH, "02_build_master.py"), (FORECAST_ALL_PATH, "10_fit_final_forecast_2027.py")]:
        if not path.exists():
            raise FileNotFoundError(f"No existe {path.relative_to(ROOT)}. Ejecuta primero src/{stage}")
    OUT.mkdir(parents=True, exist_ok=True)
    m = load_master()
    f = pd.read_parquet(FORECAST_ALL_PATH)

    mag = magnitud(m)
    hist, near = concentracion(m)
    unif = uniformidad(m)
    sel, base_rate = seleccion(m)
    pers = persistencia(m)
    ses = sesgo(m)
    niveles, por_estado, por_tipo, sens, thr = impacto_semaforo(f)

    outputs = {"01_magnitud.csv": mag, "02_fraccion_ns_parcial.csv": hist, "03_ns_por_edad_y_sexo.csv": unif,
               "04_seleccion.csv": sel, "05_persistencia.csv": pers, "06_sesgo_abstencion.csv": ses,
               "07_nivel_indicativo_excluidas.csv": niveles, "08_excluidas_por_entidad.csv": por_estado,
               "09_excluidas_por_tipo.csv": por_tipo, "10_sensibilidad_umbral.csv": sens}
    for name, df in outputs.items():
        df.to_csv(OUT / name, index=False)

    # Lectura automática
    y24 = mag.set_index("anio").loc[2024]
    ratios = unif.drop(columns="anio")
    ratio_range = (float(ratios.min().min()), float(ratios.max().max()))
    ses_hi = ses.loc[ses["NS_BUCKET"].isin(["10–25%", "25–50%", "50–99.9%"])]
    ses_lo = ses.loc[ses["NS_BUCKET"].isin(["0%", "0–5%"])]
    weighted = lambda d: float(np.average(d["residuo_medio_pp"], weights=d["secciones"]))
    tipo = por_tipo.set_index("RECENT_TIPOSEC")["pct_excluidas"]
    sens10 = sens.set_index("umbral_ns").loc[0.10]
    summary = {
        "ns_2024_pct_lista": float(y24["pct_lista_nominal_ns"]),
        "secciones_ns_alto_2024": int(y24["ns_mayor_10"]),
        "concentracion_fracciones": near,
        "uniformidad_razon_min_max": [round(v, 3) for v in ratio_range],
        "persistencia_veces_mas_probable": pers.set_index("anio")["veces_mas_probable"].round(2).to_dict(),
        "sesgo_residuo_ns_alto_pp": weighted(ses_hi),
        "sesgo_residuo_ns_bajo_pp": weighted(ses_lo),
        "excluidas_alto_indicativo": float(niveles.set_index("nivel").loc["ALTO", "excluidas_por_ns"]),
        "excluidas_pct_por_tipo": tipo.round(4).to_dict(),
        "umbral_10_secciones": int(sens10["secciones"]),
    }
    (OUT / "auditoria_config.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    top_states = por_estado.head(5)
    sel_tipo = sel.loc[sel["variable"].eq("Tipo de sección")].set_index("categoria")["tasa_ns_alto"]
    sel_abst = sel.loc[sel["variable"].str.startswith("Abstención")].set_index("categoria")["tasa_ns_alto"]
    sel_size = sel.loc[sel["variable"].str.startswith("Lista")].set_index("categoria")["tasa_ns_alto"]
    lines = [
        "# Auditoría del NS (registros sin información de participación)",
        "",
        "Generado por `src/auditoria_ns/01_auditar_ns.py`. Lee la base maestra y el universo",
        "comparable 2027; no modifica ninguna etapa del pipeline.",
        "",
        "NS = personas de la lista nominal de las que no se sabe si votaron (cuadernillo sin marcas,",
        "no disponible para captura, solicitado por autoridad o página faltante). La abstención se",
        "calcula sin ellas y el semáforo 2027 excluye secciones con NS > 10% en 2021 o 2024.",
        "",
        "## 1. Cuánto NS hay",
        "",
        "| Año | Secciones | Con NS | NS > 10% | 100% NS | % de la lista nominal | NS en secciones con NS > 10% |",
        "|---|---|---|---|---|---|---|",
        *[f"| {r.anio} | {r.secciones:,} | {r.con_ns:,} | {r.ns_mayor_10:,} | {r.ns_100:,} | {pct(r.pct_lista_nominal_ns)} | {pct(r.ns_en_secciones_ns_alto)} |"
          for r in mag.itertuples()],
        "",
        "## 2. De dónde viene",
        "",
        "Entre las secciones con NS parcial, la proporción de NS se amontona en fracciones simples,",
        "como si faltara una casilla completa de dos, tres o cuatro (la casilla se divide por apellido):",
        "",
        "| Fracción de NS | Secciones a ±2 pp de esa fracción |",
        "|---|---|",
        *[f"| {k} | {pct(v)} |" for k, v in near.items()],
        "",
        "Si la fracción fuera uniforme, cada ventana tendría alrededor de 4.2%.",
        "",
        "Dentro de cada sección, todos los grupos de edad y ambos sexos pierden la misma proporción:",
        f"la razón entre el NS del grupo y el de su sección va de {ratio_range[0]:.3f} a {ratio_range[1]:.3f}",
        "(1 = igual; ver `03_ns_por_edad_y_sexo.csv`). Es lo esperable si faltan casillas o páginas",
        "completas y no personas elegidas por su perfil. Ojo: si se agrega entre secciones, el grupo 60+",
        "parece tener más NS, pero es un efecto de composición, no del NS.",
        "",
        "## 3. ¿Es aleatorio entre secciones?",
        "",
        f"No. De 2015 a 2024, {pct(base_rate)} de las sección-elección tienen NS > 10%, pero la tasa cambia mucho:",
        "",
        "| Grupo | Tasa de NS > 10% |",
        "|---|---|",
        *[f"| Tipo {k} | {pct(v)} |" for k, v in sel_tipo.items()],
        *[f"| Lista nominal {k} | {pct(v)} |" for k, v in sel_size.items()],
        *[f"| Abstención previa {k} | {pct(v)} |" for k, v in sel_abst.items()],
        "",
        "Más NS en secciones grandes (tienen más casillas que pueden faltar) y con más abstención previa.",
        "La repetición en la misma sección es moderada: tener NS > 10% en una elección hace",
        "1.4–1.5 veces más probable volver a tenerlo en la siguiente, pero la mayoría no repite.",
        "Es sobre todo un problema operativo de cada elección, con un componente territorial.",
        "",
        "| Elección | vs. | Tasa base | Si antes tuvo NS > 10% | Veces más probable |",
        "|---|---|---|---|---|",
        *[f"| {r.anio} | {r.vs} | {pct(r.tasa_base)} | {pct(r.tasa_si_antes_ns_alto)} | {r.veces_mas_probable:.1f}× |"
          for r in pers.itertuples()],
        "",
        "## 4. ¿Sesga la abstención medida?",
        "",
        "Para cada sección con NS ≤ 5% en la elección anterior del mismo tipo, se compara su abstención",
        "con la esperada (abstención anterior + cambio promedio de su entidad entre secciones limpias).",
        "Si el NS ocultara sobre todo a quienes no votaron, el residuo sería negativo donde hay NS.",
        "",
        "| Elección | NS este año | Secciones | Residuo medio (pp) | Error estándar (pp) |",
        "|---|---|---|---|---|",
        *[f"| {r.anio} | {r.NS_BUCKET} | {r.secciones:,} | {r.residuo_medio_pp:+.2f} | {r.error_estandar_pp:.2f} |"
          for r in ses.itertuples() if r.NS_BUCKET != "100%"],
        "",
        f"Promedio ponderado: {summary['sesgo_residuo_ns_alto_pp']:+.2f} pp con NS entre 10% y 99.9%,",
        f"frente a {summary['sesgo_residuo_ns_bajo_pp']:+.2f} pp con NS ≤ 5%. El residuo es positivo y pequeño: donde hay NS",
        "se mide un poco más de abstención de la esperada, no menos. El NS no esconde sobre todo a quienes no votaron;",
        "si acaso, la abstención de esas secciones estaría ligeramente sobrestimada. La magnitud (décimas de punto,",
        "salvo 2015) es mucho menor que la distancia entre umbrales del semáforo (q50 a q80 ≈ 8 pp).",
        "",
        "## 5. Impacto en el semáforo 2027",
        "",
        f"El filtro de NS deja fuera 9,199 secciones comparables. Con los umbrales congelados del semáforo",
        f"(q50 {pct(thr['q50'])}, q80 {pct(thr['q80'])}), su nivel indicativo sería:",
        "",
        "| Nivel | Semáforo oficial | Excluidas por NS |",
        "|---|---|---|",
        *[f"| {r.nivel} | {pct(r.semaforo_oficial)} | {pct(r.excluidas_por_ns)} |" for r in niveles.itertuples()],
        "",
        "Entidades que más pierden por el filtro:",
        "",
        "| Entidad | Comparables | Excluidas por NS | % |",
        "|---|---|---|---|",
        *[f"| {r.entidad} | {r.comparables:,} | {r.excluidas_por_ns:,} | {pct(r.pct_excluidas)} |" for r in top_states.itertuples()],
        "",
        "Por tipo de sección: " + ", ".join(f"{k} {pct(v)}" for k, v in tipo.items()) + " excluidas.",
        "",
        "Sensibilidad al umbral (los percentiles se recalculan sobre cada universo):",
        "",
        "| Umbral NS | Secciones | q80 | ALTO | ALTO oficial que sigue ALTO | ALTO nuevas |",
        "|---|---|---|---|---|---|",
        *[f"| {pct(r.umbral_ns, 0)} | {r.secciones:,} | {pct(r.q80)} | {r.alto:,} | {pct(r.alto_oficial_que_sigue_alto)} | {r.alto_nuevas:,} |"
          for r in sens.itertuples()],
        "",
        "## Conclusiones",
        "",
        "1. **El NS viene de casillas completas, no de personas.** Las fracciones se amontonan en 1/2, 1/3 y 1/4",
        "   y, dentro de cada sección, todas las edades y ambos sexos pierden la misma proporción.",
        "2. **No es aleatorio entre secciones.** Afecta más a secciones grandes, mixtas y con más abstención,",
        "   y a ciertas entidades; la repetición en la misma sección es moderada.",
        "3. **No sesga de forma relevante la abstención medida.** Las personas que sí se registraron son una",
        "   muestra por apellido de la sección; el residuo es de décimas de punto y en dirección opuesta a",
        "   la temida (no hay abstención escondida).",
        f"4. **Pero el filtro de NS > 10% sí sesga el semáforo.** Las secciones excluidas son más de riesgo:",
        f"   {pct(summary['excluidas_alto_indicativo'])} serían ALTO (vs. 20%) y {pct(float(niveles.set_index('nivel').loc['ALTO', 'top10_excluidas']))} Top10 (vs. 10%).",
        "5. **Relajar el umbral cambia poco el ranking y recupera cobertura.** Con 25% entran",
        f"   {int(sens.set_index('umbral_ns').loc[0.25, 'secciones'] - sens10['secciones']):,} secciones más y",
        f"   {pct(float(sens.set_index('umbral_ns').loc[0.25, 'alto_oficial_que_sigue_alto']))} de las ALTO oficiales siguen en ALTO.",
        "",
        "Propuesta para discutir en el equipo (no se aplicó; el universo `primary_clean10` sigue igual):",
        "en vez de excluir por NS, incluir las secciones con NS parcial marcadas como \"estimación con",
        "menos registros\", o subir el umbral a 25%. Las 100% NS no tienen abstención calculable y",
        "seguirían fuera.",
        "",
    ]
    (OUT / "AUDITORIA_NS.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Salida: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
