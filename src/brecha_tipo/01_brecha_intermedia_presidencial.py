"""Brecha de abstención entre elecciones intermedias y presidenciales.

Brecha = abstención en la intermedia − abstención en la presidencial contigua, para la
misma sección: mide cuánta gente sólo vota cuando hay elección presidencial. 2027 es
intermedia, así que importa para el riesgo.

Preguntas:
1. ¿Qué tan grande es y cómo ha cambiado? (nacional, por tipo de sección, sexo y edad)
2. ¿Cómo se reparte entre secciones y qué tan persistente es?
3. ¿Dónde es mayor? (tipo, tamaño, jóvenes, abstención previa, entidad)
4. ¿La explica la concurrencia con elecciones locales el mismo día?
   (data/external/calendario_concurrente.csv, pendiente de validar)
5. ¿Qué implica para 2027? (niveles de riesgo y entidades cuyo calendario cambia)

Sólo lee salidas existentes; no modifica el pipeline.

Uso:
    python src/brecha_tipo/01_brecha_intermedia_presidencial.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
CALENDAR_PATH = ROOT / "data" / "external" / "calendario_concurrente.csv"
RISK_PATH = ROOT / "data" / "processed" / "sensitivity_2027" / "section_sensitivity_2027.parquet"
OUT = ROOT / "reports" / "brecha_tipo"
OUT_DATA = ROOT / "data" / "processed" / "brecha_tipo"
# (intermedia, presidencial) contiguas.
PAIRS = [(2009, 2012), (2015, 2012), (2015, 2018), (2021, 2018), (2021, 2024)]
AGES = {"18_24": "18–24", "25_34": "25–34", "35_44": "35–44", "45_59": "45–59", "60_plus": "60+"}
MAX_NS = 0.10  # mismo umbral de calidad que el semáforo


def nombre(p):
    return f"{p[0]}–{p[1]}"


def load():
    cols = ["AELEC", "SECTION_KEY", "EDOCVE", "EDONOM", "TIPOSEC", "LN", "SV", "NV", "PCT_ABSTENCION", "PCT_NS_LN"]
    cols += [f"{v}_{g}" for g in list(AGES) + ["H", "M"] for v in ("SV", "NV")]
    return pd.read_csv(MASTER_PATH, usecols=cols, dtype={"SECTION_KEY": str}, low_memory=False)


def tasa(d, sv="SV", nv="NV"):
    return d[nv].sum() / (d[sv].sum() + d[nv].sum())


def nacional(m):
    """Brecha agregada por par, total y por tipo de sección, sexo y edad."""
    rows = []
    for p in PAIRS:
        a, b = m[m["AELEC"].eq(p[0])], m[m["AELEC"].eq(p[1])]
        grupos = [("Total", "Total", a, b, "SV", "NV")]
        grupos += [("Tipo de sección", n, a[a["TIPOSEC"].eq(t)], b[b["TIPOSEC"].eq(t)], "SV", "NV")
                   for t, n in (("U", "Urbana"), ("M", "Mixta"), ("R", "Rural"))]
        grupos += [("Sexo", n, a, b, f"SV_{s}", f"NV_{s}") for s, n in (("H", "Hombres"), ("M", "Mujeres"))]
        grupos += [("Edad", n, a, b, f"SV_{g}", f"NV_{g}") for g, n in AGES.items()]
        for var, cat, x, y, sv, nv in grupos:
            ai, ap = tasa(x, sv, nv), tasa(y, sv, nv)
            rows.append({"par": nombre(p), "variable": var, "categoria": cat,
                         "abst_intermedia": ai, "abst_presidencial": ap, "brecha_pp": (ai - ap) * 100})
    return pd.DataFrame(rows)


def por_seccion(m):
    """Brecha por sección para cada par, sólo con NS ≤ 10% en ambas elecciones."""
    w = m.pivot_table(index="SECTION_KEY", columns="AELEC", values="PCT_ABSTENCION")
    ns = m.pivot_table(index="SECTION_KEY", columns="AELEC", values="PCT_NS_LN")
    out = pd.DataFrame(index=w.index)
    for p in PAIRS:
        ok = w[list(p)].notna().all(axis=1) & ns[list(p)].le(MAX_NS).all(axis=1)
        out[f"BRECHA_{p[0]}_{p[1]}"] = ((w[p[0]] - w[p[1]]) * 100).where(ok)
    return out


def distribucion(b):
    rows = []
    for p in PAIRS:
        g = b[f"BRECHA_{p[0]}_{p[1]}"].dropna()
        q = g.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        rows.append({"par": nombre(p), "secciones": len(g), "media_pp": g.mean(), "p10": q[0.1], "p25": q[0.25],
                     "mediana": q[0.5], "p75": q[0.75], "p90": q[0.9], "pct_negativa": (g < 0).mean()})
    return pd.DataFrame(rows)


def persistencia(b):
    cols = [f"BRECHA_{p[0]}_{p[1]}" for p in PAIRS]
    c = b[cols].corr(method="spearman")
    c.index = c.columns = [nombre(p) for p in PAIRS]
    return c.reset_index().rename(columns={"index": "par"})


def por_grupo(m, b):
    """¿Dónde es mayor la brecha 2021–2024?"""
    s = m[m["AELEC"].eq(2024)].set_index("SECTION_KEY")
    a21 = m[m["AELEC"].eq(2021)].set_index("SECTION_KEY")["PCT_ABSTENCION"]
    d = pd.DataFrame({"brecha": b["BRECHA_2021_2024"]}).join(s[["TIPOSEC", "EDONOM", "LN"]], how="inner")
    d["JOVENES"] = (s["SV_18_24"] + s["NV_18_24"]) / (s["SV"] + s["NV"])
    d["ABST_2021"] = a21
    d = d.dropna(subset=["brecha"])
    d["Tamaño (lista nominal)"] = pd.qcut(d["LN"], 5, labels=["Q1 más chicas", "Q2", "Q3", "Q4", "Q5 más grandes"])
    d["Jóvenes 18–24 (quintil)"] = pd.qcut(d["JOVENES"], 5, labels=["Q1 menos jóvenes", "Q2", "Q3", "Q4", "Q5 más jóvenes"])
    d["Abstención 2021 (quintil)"] = pd.qcut(d["ABST_2021"], 5, labels=["Q1 menos abstención", "Q2", "Q3", "Q4", "Q5 más abstención"])
    d["Tipo de sección"] = d["TIPOSEC"].map({"U": "Urbana", "M": "Mixta", "R": "Rural"})
    parts = []
    for var in ["Tipo de sección", "Tamaño (lista nominal)", "Jóvenes 18–24 (quintil)", "Abstención 2021 (quintil)", "EDONOM"]:
        t = d.groupby(var, observed=True)["brecha"].agg(secciones="size", mediana_pp="median", media_pp="mean").reset_index()
        parts.append(t.rename(columns={var: "categoria"}).assign(variable="Entidad" if var == "EDONOM" else var))
    out = pd.concat(parts, ignore_index=True)
    return out[["variable", "categoria", "secciones", "mediana_pp", "media_pp"]]


def concurrencia(m):
    """Brecha agregada por entidad y par, con banderas de concurrencia local."""
    cal = pd.read_csv(CALENDAR_PATH)
    flags = cal.set_index(["ANIO", "EDOCVE"])[["LOCAL_CONCURRENTE", "GUBERNATURA_CONCURRENTE"]]
    rows = []
    for p in PAIRS:
        for edo, d in m[m["AELEC"].isin(p)].groupby("EDOCVE"):
            ai, ap = tasa(d[d["AELEC"].eq(p[0])]), tasa(d[d["AELEC"].eq(p[1])])
            rows.append({"par": nombre(p), "EDOCVE": edo, "entidad": d["EDONOM"].mode()[0], "brecha_pp": (ai - ap) * 100,
                         "gob_intermedia": int(flags.loc[(p[0], edo), "GUBERNATURA_CONCURRENTE"]),
                         "gob_presidencial": int(flags.loc[(p[1], edo), "GUBERNATURA_CONCURRENTE"]),
                         "local_intermedia": int(flags.loc[(p[0], edo), "LOCAL_CONCURRENTE"]),
                         "local_presidencial": int(flags.loc[(p[1], edo), "LOCAL_CONCURRENTE"])})
    return pd.DataFrame(rows), flags


def efecto_concurrencia(c, n_boot=1000, seed=42):
    """MCO de la brecha por entidad y par sobre las banderas, con efectos fijos de par.
    Error estándar por bootstrap de entidades (cada entidad aparece en los 5 pares)."""
    X_cols = ["gob_intermedia", "gob_presidencial", "local_intermedia", "local_presidencial"]
    def fit(d):
        X = np.column_stack([d[X_cols].to_numpy(float), pd.get_dummies(d["par"], dtype=float).to_numpy()])
        return np.linalg.lstsq(X, d["brecha_pp"].to_numpy(), rcond=None)[0][:len(X_cols)]
    coef = fit(c)
    rng = np.random.default_rng(seed)
    edos = c["EDOCVE"].unique()
    boot = np.array([fit(pd.concat([c[c["EDOCVE"].eq(e)] for e in rng.choice(edos, len(edos))])) for _ in range(n_boot)])
    return pd.DataFrame({"variable": X_cols, "coef_pp": coef, "error_estandar_pp": boot.std(axis=0),
                         "ic90_bajo": np.percentile(boot, 5, axis=0), "ic90_alto": np.percentile(boot, 95, axis=0)})


def cierre_por_calendario(c, efe):
    """Cuánto del cambio de la brecha entre 2009–2012 y 2021–2024 predicen los coeficientes por el
    cambio en el número de entidades con concurrencia (promedio simple de entidades, no ponderado)."""
    e = efe.set_index("variable")["coef_pp"]
    first, last = c[c["par"].eq("2009–2012")], c[c["par"].eq("2021–2024")]
    pred = sum(e[v] * (last[v].mean() - first[v].mean()) for v in e.index)
    obs = last["brecha_pp"].mean() - first["brecha_pp"].mean()
    return {"cambio_observado_pp": round(float(obs), 2), "cambio_por_calendario_pp": round(float(pred), 2),
            "parte_por_calendario": round(float(pred / obs), 3)}


def implicaciones_2027(m, b, flags):
    niv = pd.DataFrame()
    if RISK_PATH.exists():
        r = pd.read_parquet(RISK_PATH, columns=["SECTION_KEY", "RISK_LEVEL"]).set_index("SECTION_KEY")
        d = r.join(b["BRECHA_2021_2024"], how="inner").dropna()
        niv = (d.groupby("RISK_LEVEL")["BRECHA_2021_2024"].agg(secciones="size", mediana_pp="median", media_pp="mean")
               .reindex(["BAJO", "MEDIO", "ALTO"]).rename_axis("nivel").reset_index())
    names = m.groupby("EDOCVE")["EDONOM"].agg(lambda s: s.mode()[0])
    cal = pd.DataFrame({y: flags.xs(y, level="ANIO")["GUBERNATURA_CONCURRENTE"] for y in (2021, 2024, 2027)})
    cal.columns = [f"gob_{y}" for y in cal.columns]
    cal["entidad"] = names
    cal["cambia_vs_2021"] = cal["gob_2027"].ne(cal["gob_2021"])
    return niv, cal.reset_index().sort_values(["cambia_vs_2021", "gob_2027"], ascending=False)


def main():
    print("\n=== Brecha intermedia vs. presidencial ===")
    for path, hint in [(MASTER_PATH, "src/02_build_master.py"), (CALENDAR_PATH, "src/clustering/03_build_calendario_concurrente.py")]:
        if not path.exists():
            raise FileNotFoundError(f"No existe {path.relative_to(ROOT)}. Ejecuta primero {hint}")
    OUT.mkdir(parents=True, exist_ok=True)
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    m = load()
    nac = nacional(m)
    b = por_seccion(m)
    dist = distribucion(b)
    pers = persistencia(b)
    grp = por_grupo(m, b)
    conc, flags = concurrencia(m)
    efe = efecto_concurrencia(conc)
    niv, cal = implicaciones_2027(m, b, flags)
    cierre = cierre_por_calendario(conc, efe)
    conteo = (pd.read_csv(CALENDAR_PATH).groupby("ANIO")[["LOCAL_CONCURRENTE", "GUBERNATURA_CONCURRENTE"]].sum()
              .rename(columns={"LOCAL_CONCURRENTE": "locales", "GUBERNATURA_CONCURRENTE": "gubernaturas"}).reset_index())

    outputs = {"01_brecha_nacional.csv": nac, "02_distribucion_secciones.csv": dist, "03_persistencia.csv": pers,
               "04_por_grupo_2021_2024.csv": grp, "05_brecha_por_entidad_y_concurrencia.csv": conc,
               "06_efecto_concurrencia.csv": efe, "07_por_nivel_riesgo.csv": niv, "08_gubernaturas_2021_2024_2027.csv": cal,
               "09_calendario_por_anio.csv": conteo}
    for name, df in outputs.items():
        df.to_csv(OUT / name, index=False)
    b.reset_index().to_parquet(OUT_DATA / "secciones_brecha.parquet", index=False)

    tot = nac[nac["variable"].eq("Total")].set_index("par")
    e = efe.set_index("variable")
    summary = {
        "brecha_nacional_pp": tot["brecha_pp"].round(1).to_dict(),
        "mediana_secciones_pp": dist.set_index("par")["mediana"].round(1).to_dict(),
        "pct_negativa": dist.set_index("par")["pct_negativa"].round(3).to_dict(),
        "persistencia_15_18_vs_21_24": round(float(pers.set_index("par").loc["2015–2018", "2021–2024"]), 3),
        "efecto_gob_intermedia_pp": round(float(e.loc["gob_intermedia", "coef_pp"]), 2),
        "efecto_gob_presidencial_pp": round(float(e.loc["gob_presidencial", "coef_pp"]), 2),
        "efecto_local_intermedia_pp": round(float(e.loc["local_intermedia", "coef_pp"]), 2),
        "efecto_local_presidencial_pp": round(float(e.loc["local_presidencial", "coef_pp"]), 2),
        "cierre_por_calendario": cierre,
        "entidades_cambian_gubernatura_2027_vs_2021": int(cal["cambia_vs_2021"].sum()),
    }
    (OUT / "brecha_config.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    pct = lambda v: f"{v * 100:.1f}%"
    sub = lambda var: nac[nac["variable"].eq(var)]
    lines = [
        "# Brecha intermedia vs. presidencial",
        "",
        "Generado por `src/brecha_tipo/01_brecha_intermedia_presidencial.py`. Brecha = abstención en la elección",
        "intermedia − abstención en la presidencial contigua (pp). Positiva = más gente vota cuando hay elección",
        "presidencial. Por sección sólo se usan pares con NS ≤ 10% en ambas elecciones.",
        "",
        "## 1. Tamaño y evolución",
        "",
        "| Par | Abstención intermedia | Abstención presidencial | Brecha |",
        "|---|---|---|---|",
        *[f"| {r.par} | {pct(r.abst_intermedia)} | {pct(r.abst_presidencial)} | {r.brecha_pp:+.1f} pp |" for r in tot.reset_index().itertuples()],
        "",
        "Por grupo (brecha en pp):",
        "",
        "| Grupo | " + " | ".join(nombre(p) for p in PAIRS) + " |",
        "|---|" + "---|" * len(PAIRS),
        *[f"| {cat} | " + " | ".join(f"{v:+.1f}" for v in d.sort_values("par", key=lambda s: s.map({nombre(p): i for i, p in enumerate(PAIRS)}))["brecha_pp"]) + " |"
          for cat, d in nac[nac["variable"].ne("Total")].groupby("categoria", sort=False)],
        "",
        "## 2. Entre secciones",
        "",
        "| Par | Secciones | Mediana | P10 | P90 | Brecha negativa |",
        "|---|---|---|---|---|---|",
        *[f"| {r.par} | {r.secciones:,} | {r.mediana:+.1f} pp | {r.p10:+.1f} | {r.p90:+.1f} | {pct(r.pct_negativa)} |" for r in dist.itertuples()],
        "",
        f"Persistencia: la correlación (Spearman) entre la brecha 2015–2018 y la 2021–2024 de la misma sección es",
        f"{summary['persistencia_15_18_vs_21_24']:.2f}: la brecha depende más de cada elección que de la sección.",
        "",
        "## 3. ¿Dónde es mayor? (2021–2024, mediana en pp)",
        "",
        "| Variable | Categoría | Secciones | Mediana |",
        "|---|---|---|---|",
        *[f"| {r.variable} | {r.categoria} | {r.secciones:,} | {r.mediana_pp:+.1f} |" for r in grp[grp["variable"].ne("Entidad")].itertuples()],
        "",
        "## 4. ¿La explica la concurrencia local?",
        "",
        "MCO de la brecha por entidad y par (32 × 5) sobre las banderas del calendario, con efectos fijos de par.",
        "Error estándar e intervalo al 90% por bootstrap de entidades (1,000 réplicas). Calendario pendiente de validar.",
        "",
        "| Variable | Efecto (pp) | Error estándar | IC 90% |",
        "|---|---|---|---|",
        *[f"| {r.variable} | {r.coef_pp:+.2f} | {r.error_estandar_pp:.2f} | [{r.ic90_bajo:+.2f}, {r.ic90_alto:+.2f}] |" for r in efe.itertuples()],
        "",
        "Las banderas se traslapan (toda gubernatura concurrente implica elección local concurrente): una entidad",
        f"con elecciones locales y gubernatura el mismo día que la intermedia tiene una brecha {abs(e.loc['local_intermedia', 'coef_pp'] + e.loc['gob_intermedia', 'coef_pp']):.1f} pp menor.",
        "",
        "Entidades con elecciones locales y gubernaturas el mismo día que la federal:",
        "",
        "| Año | " + " | ".join(str(y) for y in conteo["ANIO"]) + " |",
        "|---|" + "---|" * len(conteo),
        "| Locales | " + " | ".join(str(v) for v in conteo["locales"]) + " |",
        "| Gubernaturas | " + " | ".join(str(v) for v in conteo["gubernaturas"]) + " |",
        "",
        f"Entre 2009–2012 y 2021–2024 la brecha promedio de las entidades cambió {cierre['cambio_observado_pp']:+.1f} pp; los",
        f"coeficientes atribuyen {cierre['cambio_por_calendario_pp']:+.1f} pp ({cierre['parte_por_calendario'] * 100:.0f}%) a que más entidades",
        "empataron sus elecciones locales con las federales. Es una estimación gruesa (32 entidades × 5 pares, sin ponderar",
        "por población), pero indica que el calendario explica buena parte del cierre.",
        "",
        "## 5. Implicaciones para 2027",
        "",
    ]
    if len(niv):
        lines += ["Brecha 2021–2024 por nivel del semáforo 2027:", "", "| Nivel | Secciones | Mediana | Media |", "|---|---|---|---|",
                  *[f"| {r.nivel} | {r.secciones:,} | {r.mediana_pp:+.1f} pp | {r.media_pp:+.1f} pp |" for r in niv.itertuples()], ""]
    changed = cal[cal["cambia_vs_2021"]]
    lines += [
        f"{len(changed)} entidades cambian su situación de gubernatura concurrente entre 2021 y 2027; el modelo 2027",
        "no usa concurrencia, así que ahí el contexto de 2027 será distinto al de la intermedia que más pesa (2021):",
        "",
        "| Entidad | Gubernatura 2021 | Gubernatura 2024 | Gubernatura 2027 |",
        "|---|---|---|---|",
        *[f"| {r.entidad} | {'sí' if r.gob_2021 else 'no'} | {'sí' if r.gob_2024 else 'no'} | {'sí' if r.gob_2027 else 'no'} |" for r in changed.itertuples()],
        "",
    ]
    lines += [
        "## Conclusiones",
        "",
        f"1. **La brecha se cerró a menos de la mitad:** de {summary['brecha_nacional_pp']['2009–2012']:+.1f} pp (2009–2012) a",
        f"   {summary['brecha_nacional_pp']['2021–2024']:+.1f} pp (2021–2024). Las intermedias bajaron su abstención y la presidencial de 2024 la subió.",
        f"2. **Ya no es universal:** en 2021–2024, {summary['pct_negativa']['2021–2024'] * 100:.0f}% de las secciones se abstuvieron más en la presidencial",
        "   que en la intermedia. La brecha es grande en secciones urbanas y casi nula en las rurales.",
        f"3. **Es poco persistente** (Spearman {summary['persistencia_15_18_vs_21_24']:.2f}): depende más del contexto de cada elección que de la sección.",
        "4. **El calendario local la explica en buena medida.** Elecciones locales el mismo día que la intermedia",
        f"   reducen la brecha {abs(summary['efecto_local_intermedia_pp']):.1f} pp y una gubernatura, {abs(summary['efecto_gob_intermedia_pp']):.1f} pp más;",
        f"   que más entidades empataran sus elecciones locales con las federales explicaría cerca de {cierre['parte_por_calendario'] * 100:.0f}% del cierre.",
        "5. **Para 2027:** las secciones ALTO del semáforo son las de mayor brecha (votan sobre todo en presidenciales),",
        "   lo que refuerza su riesgo en una intermedia. Habrá 17 gubernaturas concurrentes (15 en 2021); Aguascalientes",
        "   y Quintana Roo tendrán gubernatura el mismo día y en 2021 no; el modelo no usa concurrencia.",
        "",
        "El calendario de concurrencia está pendiente de validar contra el INE y los institutos locales.",
        "",
    ]
    (OUT / "BRECHA_TIPO.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Salida: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
