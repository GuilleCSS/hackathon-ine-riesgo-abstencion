"""Fase 1 · Grupos de secciones por trayectoria de abstención (descriptivo).

Agrupa las secciones por su comportamiento 2009–2024 frente al promedio
nacional de cada elección y describe cada grupo por su contexto. No forma
parte del pipeline del modelo 2027 ni modifica sus salidas.

Uso: python src/clustering/01_build_section_clusters.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
MASTER_PATH = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
OUT_DATA = ROOT / "data" / "processed" / "clustering"
OUT_REPORT = ROOT / "reports" / "clustering"

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
INTERMEDIAS = [2009, 2015, 2021]
PRESIDENCIALES = [2012, 2018, 2024]

# Sólo secciones con abstención calculable en las 6 elecciones y NS <= 25% en
# todas: con más NS la abstención observada deja de ser confiable.
MAX_NS = 0.25

FEATURES = ["nivel_intermedia", "nivel_presidencial", "tendencia", "volatilidad"]

# k fijo para que los grupos sean estables entre corridas. Se eligió por el
# máximo local del silhouette entre 4 y 8 grupos (ver 01_k_selection.csv).
K = 5
K_RANGE = range(3, 9)
RANDOM_STATE = 42
SILHOUETTE_SAMPLE = 15000

# Reglas de nombre sobre los centroides (pp frente al promedio nacional).
TREND_PP = 5.0
LEVEL_PP = 5.0
NAME_ORDER = [
    "Abstención baja persistente",
    "En el promedio",
    "Abstención alta persistente",
    "Mejorando",
    "Empeorando",
]

MASTER_COLS = [
    "AELEC", "SECTION_KEY", "EDOCVE", "EDONOM", "MPIONOM", "TIPOSEC",
    "LN", "SV", "NV", "PCT_ABSTENCION", "PCT_NS_LN", "PROP_LN_18_24",
]


def name_cluster(c):
    if c["tendencia"] > TREND_PP:
        return "Empeorando"
    if c["tendencia"] < -TREND_PP:
        return "Mejorando"
    level = (c["nivel_intermedia"] + c["nivel_presidencial"]) / 2
    if level > LEVEL_PP:
        return "Abstención alta persistente"
    if level < -LEVEL_PP:
        return "Abstención baja persistente"
    return "En el promedio"


def pooled_abstention(df):
    return df["NV"].sum() / (df["SV"].sum() + df["NV"].sum())


def main():
    print("\n=== Clustering · grupos de secciones por trayectoria ===")
    if not MASTER_PATH.exists():
        raise FileNotFoundError(
            f"No existe {MASTER_PATH}. Ejecuta primero src/02_build_master.py"
        )
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.mkdir(parents=True, exist_ok=True)

    m = pd.read_csv(MASTER_PATH, usecols=MASTER_COLS, low_memory=False)
    national = m.groupby("AELEC").apply(pooled_abstention, include_groups=False)
    m["REL_PP"] = (m["PCT_ABSTENCION"] - m["AELEC"].map(national)) * 100

    rel = m.pivot(index="SECTION_KEY", columns="AELEC", values="REL_PP")
    ns = m.pivot(index="SECTION_KEY", columns="AELEC", values="PCT_NS_LN")
    eligible = rel.notna().all(axis=1) & ns.max(axis=1).le(MAX_NS)
    rel = rel.loc[eligible]
    print(f"Secciones agrupables: {len(rel):,} de {len(eligible):,}")

    feats = pd.DataFrame({
        "nivel_intermedia": rel[INTERMEDIAS].mean(axis=1),
        "nivel_presidencial": rel[PRESIDENCIALES].mean(axis=1),
        # Cambio del promedio de las dos últimas elecciones frente a las dos primeras.
        "tendencia": rel[[2021, 2024]].mean(axis=1) - rel[[2009, 2012]].mean(axis=1),
        "volatilidad": rel.sub(rel.mean(axis=1), axis=0).abs().mean(axis=1),
    })
    z = StandardScaler().fit_transform(feats[FEATURES])

    sample = np.random.default_rng(RANDOM_STATE).choice(
        len(z), size=min(SILHOUETTE_SAMPLE, len(z)), replace=False
    )
    k_rows, models = [], {}
    for k in K_RANGE:
        km = KMeans(k, n_init=10, random_state=RANDOM_STATE).fit(z)
        models[k] = km
        k_rows.append({
            "k": k,
            "silhouette": float(silhouette_score(z[sample], km.labels_[sample])),
            "tamaños": "|".join(str(x) for x in sorted(np.bincount(km.labels_), reverse=True)),
        })
    k_sel = pd.DataFrame(k_rows)
    k_sel.to_csv(OUT_REPORT / "01_k_selection.csv", index=False)

    feats["raw"] = models[K].labels_
    centroids = feats.groupby("raw")[FEATURES].mean()
    names = {c: name_cluster(row) for c, row in centroids.iterrows()}
    # Orden estable: por tipo de nombre y, dentro del mismo tipo, por nivel.
    order = sorted(
        names,
        key=lambda c: (
            NAME_ORDER.index(names[c]),
            centroids.loc[c, ["nivel_intermedia", "nivel_presidencial"]].mean(),
        ),
    )
    seen = {}
    labels = {}
    for c in order:
        seen[names[c]] = seen.get(names[c], 0) + 1
        labels[c] = names[c] + (f" ({seen[names[c]]})" if seen[names[c]] > 1 else "")
    group_id = {c: i + 1 for i, c in enumerate(order)}
    feats["GRUPO"] = feats["raw"].map(group_id)
    feats["GRUPO_NOMBRE"] = feats["raw"].map(labels)
    feats = feats.drop(columns="raw")

    # Contexto 2024 para describir los grupos (no se usa para formarlos).
    ctx = m.loc[m["AELEC"].eq(2024)].set_index("SECTION_KEY")[
        ["EDOCVE", "EDONOM", "MPIONOM", "TIPOSEC", "LN", "PROP_LN_18_24"]
    ]
    abst = m.pivot(index="SECTION_KEY", columns="AELEC", values="PCT_ABSTENCION")
    abst.columns = [f"ABST_{y}" for y in abst.columns]
    # SV/NV por año para que el dashboard calcule abstención agregada por territorio.
    counts = m.pivot(index="SECTION_KEY", columns="AELEC", values=["SV", "NV"])
    counts.columns = [f"{c}_{y}" for c, y in counts.columns]
    sections = (
        feats.join(ctx)
        .join(abst)
        .join(counts)
        .join(ns.max(axis=1).rename("NS_MAX"))
        .reset_index()
        .rename(columns={"index": "SECTION_KEY"})
    )
    sections.to_parquet(OUT_DATA / "section_clusters.parquet", index=False)

    profiles = (
        sections.groupby(["GRUPO", "GRUPO_NOMBRE"])
        .agg(
            secciones=("SECTION_KEY", "size"),
            nivel_intermedia_pp=("nivel_intermedia", "mean"),
            nivel_presidencial_pp=("nivel_presidencial", "mean"),
            tendencia_pp=("tendencia", "mean"),
            volatilidad_pp=("volatilidad", "mean"),
            pct_urbana=("TIPOSEC", lambda t: t.eq("U").mean()),
            pct_mixta=("TIPOSEC", lambda t: t.eq("M").mean()),
            pct_rural=("TIPOSEC", lambda t: t.eq("R").mean()),
            ln_mediana_2024=("LN", "median"),
            pct_18_24_2024=("PROP_LN_18_24", "mean"),
            ns_max_medio=("NS_MAX", "mean"),
        )
        .reset_index()
    )
    profiles["pct_secciones"] = profiles["secciones"] / profiles["secciones"].sum()
    profiles.to_csv(OUT_REPORT / "02_cluster_profiles.csv", index=False)

    tr = m.merge(sections[["SECTION_KEY", "GRUPO", "GRUPO_NOMBRE"]], on="SECTION_KEY")
    trajectories = (
        tr.groupby(["GRUPO", "GRUPO_NOMBRE", "AELEC"])
        .apply(pooled_abstention, include_groups=False)
        .rename("abstencion")
        .reset_index()
    )
    nat_rows = national.rename("abstencion").reset_index().assign(GRUPO=0, GRUPO_NOMBRE="Nacional (todas las secciones)")
    trajectories = pd.concat([trajectories, nat_rows], ignore_index=True)
    trajectories["tipo_eleccion"] = np.where(trajectories["AELEC"].isin(INTERMEDIAS), "intermedia", "presidencial")
    trajectories.to_csv(OUT_REPORT / "03_cluster_trajectories.csv", index=False)

    comp = (
        sections.groupby(["EDOCVE", "EDONOM", "GRUPO", "GRUPO_NOMBRE"])
        .size()
        .rename("secciones")
        .reset_index()
    )
    comp["pct_estado"] = comp["secciones"] / comp.groupby("EDOCVE")["secciones"].transform("sum")
    comp.to_csv(OUT_REPORT / "04_state_composition.csv", index=False)

    silhouette_k = float(k_sel.loc[k_sel["k"].eq(K), "silhouette"].iloc[0])
    config = {
        "status": "FASE_1_DESCRIPTIVA",
        "k": K,
        "silhouette_k": silhouette_k,
        "features": FEATURES,
        "max_ns": MAX_NS,
        "random_state": RANDOM_STATE,
        "sections_clustered": int(len(sections)),
        "sections_in_master": int(m["SECTION_KEY"].nunique()),
        "naming_rules_pp": {"trend": TREND_PP, "level": LEVEL_PP},
        "groups": {int(r.GRUPO): r.GRUPO_NOMBRE for r in profiles.itertuples()},
        "warning": (
            "Grupos descriptivos construidos con 2009–2024. Para usarlos en "
            "backtests del modelo hay que reconstruirlos sólo con elecciones "
            "anteriores a la elección objetivo."
        ),
    }
    (OUT_REPORT / "clustering_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    write_method(profiles, k_sel, config)

    print(f"Grupos (k={K}, silhouette={silhouette_k:.3f}):")
    for r in profiles.itertuples():
        print(f"  G{r.GRUPO} {r.GRUPO_NOMBRE}: {r.secciones:,} secciones")
    print(f"Salida: {(OUT_DATA / 'section_clusters.parquet').relative_to(ROOT)}")
    print(f"Reportes: {OUT_REPORT.relative_to(ROOT)}")


def write_method(profiles, k_sel, config):
    def pp(x):
        return f"{x:+.1f}"

    rows = "\n".join(
        f"| G{r.GRUPO} | {r.GRUPO_NOMBRE} | {r.secciones:,} ({r.pct_secciones:.0%}) | "
        f"{pp(r.nivel_intermedia_pp)} | {pp(r.nivel_presidencial_pp)} | {pp(r.tendencia_pp)} | "
        f"{r.volatilidad_pp:.1f} | {r.pct_urbana:.0%} / {r.pct_rural:.0%} | {r.ln_mediana_2024:,.0f} |"
        for r in profiles.itertuples()
    )
    ks = "\n".join(f"| {r.k} | {r.silhouette:.3f} | {r.tamaños.replace('|', ', ')} |" for r in k_sel.itertuples())
    text = f"""# Grupos de secciones por trayectoria (fase 1, descriptiva)

Generado por `src/clustering/01_build_section_clusters.py`. No modifica el
pipeline del modelo 2027.

## Idea

Agrupar las secciones por **cómo se comportan** frente al promedio nacional de
cada elección, para analizar territorios parecidos de forma separada. El
contexto (tipo de sección, tamaño, edad) se usa sólo para **describir** los
grupos, no para formarlos.

## Variables (pp frente a la abstención nacional de cada elección)

- `nivel_intermedia`: promedio en 2009, 2015 y 2021.
- `nivel_presidencial`: promedio en 2012, 2018 y 2024.
- `tendencia`: promedio de 2021 y 2024 menos promedio de 2009 y 2012.
- `volatilidad`: desviación media de cada elección frente al promedio de la sección.

Se estandarizan y se agrupan con k-means (k = {config['k']}, `random_state` = {config['random_state']}).

## Universo

{config['sections_clustered']:,} de {config['sections_in_master']:,} secciones de la base maestra:
las que tienen abstención calculable en las 6 elecciones y NS ≤ {config['max_ns']:.0%} en todas.
Quedan fuera las secciones nuevas o renumeradas y las de datos poco confiables.

## Grupos

Nombres asignados por reglas sobre los centroides: tendencia mayor a ±{TREND_PP:.0f} pp
→ "Empeorando"/"Mejorando"; si no, nivel medio mayor a ±{LEVEL_PP:.0f} pp → "alta"/"baja"
persistente; si no, "En el promedio".

| Grupo | Nombre | Secciones | Intermedias (pp) | Presidenciales (pp) | Tendencia (pp) | Volatilidad (pp) | Urbana / rural | LN mediana 2024 |
|---|---|---|---|---|---|---|---|---|
{rows}

## Elección de k

| k | Silhouette | Tamaños |
|---|---|---|
{ks}

El silhouette es moderado (≈0.25) para cualquier k: las secciones forman un
continuo más que grupos bien separados. Los grupos son una **tipología útil para
segmentar**, con fronteras difusas; secciones cerca de la frontera podrían caer en
el grupo vecino con otra configuración.

## Limitaciones

- Descriptivo: usa 2009–2024 completo. Para usar los grupos en el modelo, hay que
  reconstruirlos sólo con elecciones anteriores a la que se predice.
- Comparar grupos no es causalidad; sirve para comparaciones controladas entre
  territorios parecidos.
- La cartografía para el mapa es la provisional DIC-2025.

## Salidas

- `data/processed/clustering/section_clusters.parquet`: grupo y variables por sección.
- `reports/clustering/01_k_selection.csv`: silhouette por k.
- `reports/clustering/02_cluster_profiles.csv`: perfil de cada grupo.
- `reports/clustering/03_cluster_trajectories.csv`: abstención por grupo y elección.
- `reports/clustering/04_state_composition.csv`: composición de grupos por estado.
- `reports/clustering/clustering_config.json`: parámetros y resumen.
"""
    (OUT_REPORT / "CLUSTER_METHOD.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
