from pathlib import Path
import time
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
AUDIT = ROOT / "reports" / "audit"

INTERIM.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
GEO = ["AELEC", "EDOCVE", "EDONOM", "MPIOCVE", "MPIONOM", "SECCION", "TIPOSEC", "DEF", "DEL"]
USECOLS = GEO + ["SEXO", "EDAD", "LN", "SV", "NV", "NS"]
AGE_GROUPS = [
    ("18_24", 18, 24),
    ("25_34", 25, 34),
    ("35_44", 35, 44),
    ("45_59", 45, 59),
    ("60_plus", 60, None),
]
SEXES = [(0, "H"), (1, "M"), (2, "NB")]


def zpath(year: int) -> Path:
    return RAW / f"DatosAbiertos_DECEyEC_ConteosCensales{year}.zip"


def safe_divide(num: pd.Series, den: pd.Series) -> pd.Series:
    return num.div(den.where(den != 0))


def build_year(year: int) -> pd.DataFrame:
    path = zpath(year)
    if not path.exists():
        raise FileNotFoundError(path)

    parts = []
    t0 = time.time()
    print(f"\n[{year}] Construyendo agregado sección × elección")

    with zipfile.ZipFile(path) as zf:
        csvs = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
        if len(csvs) != 32:
            raise RuntimeError(f"{year}: se esperaban 32 CSV y hay {len(csvs)}")

        for idx, name in enumerate(csvs, start=1):
            with zf.open(name) as fh:
                df = pd.read_csv(
                    fh,
                    usecols=USECOLS,
                    encoding="utf-8-sig",
                    low_memory=False,
                )

            df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
            for col in ["AELEC", "EDOCVE", "MPIOCVE", "SECCION", "DEF", "DEL", "SEXO", "EDAD", "LN", "SV", "NV", "NS"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Acumuladores ponderados de edad.
            df["AGE_LN_SUM"] = df["EDAD"].fillna(0) * df["LN"].fillna(0)
            df["AGE_SV_SUM"] = df["EDAD"].fillna(0) * df["SV"].fillna(0)

            # Sexo: 0 hombre, 1 mujer y 2 no binario (este último aparece en 2024).
            for sex_value, label in SEXES:
                mask = df["SEXO"].eq(sex_value)
                for col in ["LN", "SV", "NV"]:
                    df[f"{col}_{label}"] = np.where(mask, df[col].fillna(0), 0)

            # Etapas de vida usadas por el INE.
            for label, low, high in AGE_GROUPS:
                mask = df["EDAD"].ge(low) if high is None else df["EDAD"].between(low, high)
                for col in ["LN", "SV", "NV"]:
                    df[f"{col}_{label}"] = np.where(mask, df[col].fillna(0), 0)

            sumcols = ["LN", "SV", "NV", "NS", "AGE_LN_SUM", "AGE_SV_SUM"]
            sumcols += [f"{col}_{label}" for _, label in SEXES for col in ["LN", "SV", "NV"]]
            sumcols += [f"{col}_{label}" for label, _, _ in AGE_GROUPS for col in ["LN", "SV", "NV"]]

            agg = (
                df.groupby(GEO, dropna=False, sort=False)[sumcols]
                .sum()
                .reset_index()
            )
            parts.append(agg)

            if idx % 8 == 0 or idx == len(csvs):
                print(f"    {idx:02d}/{len(csvs)} CSV agregados")

            del df, agg

    master = pd.concat(parts, ignore_index=True)

    # Indicadores oficiales y derivados.
    denom = master["SV"] + master["NV"]
    master["PCT_PARTICIPACION"] = safe_divide(master["SV"], denom)
    master["PCT_ABSTENCION"] = safe_divide(master["NV"], denom)
    master["PCT_NS_LN"] = safe_divide(master["NS"], master["LN"])
    master["EDAD_PROM_LN"] = safe_divide(master["AGE_LN_SUM"], master["LN"])
    master["EDAD_PROM_VOTANTES"] = safe_divide(master["AGE_SV_SUM"], master["SV"])

    for _, label in SEXES:
        d = master[f"SV_{label}"] + master[f"NV_{label}"]
        master[f"PCT_PART_{label}"] = safe_divide(master[f"SV_{label}"], d)
        master[f"PCT_ABST_{label}"] = safe_divide(master[f"NV_{label}"], d)
        master[f"PROP_LN_{label}"] = safe_divide(master[f"LN_{label}"], master["LN"])

    for label, _, _ in AGE_GROUPS:
        d = master[f"SV_{label}"] + master[f"NV_{label}"]
        master[f"PCT_PART_{label}"] = safe_divide(master[f"SV_{label}"], d)
        master[f"PCT_ABST_{label}"] = safe_divide(master[f"NV_{label}"], d)
        master[f"PROP_LN_{label}"] = safe_divide(master[f"LN_{label}"], master["LN"])

    master["BRECHA_PART_MENOS_H"] = master["PCT_PART_M"] - master["PCT_PART_H"]
    master["TIPO_ELECCION"] = np.where(master["AELEC"].isin([2009, 2015, 2021]), "intermedia", "presidencial")
    master["SECTION_KEY"] = (
        master["EDOCVE"].astype("Int64").astype(str).str.zfill(2)
        + "-"
        + master["SECCION"].astype("Int64").astype(str).str.zfill(4)
    )

    out = INTERIM / f"section_election_{year}.parquet"
    master.to_parquet(out, index=False)
    print(f"[{year}] {len(master):,} secciones · guardado en {out.relative_to(ROOT)} · {time.time() - t0:.1f} s")
    return master


def build_master() -> pd.DataFrame:
    year_frames = []
    for year in YEARS:
        # Siempre reconstruimos desde RAW para garantizar reproducibilidad.
        year_frames.append(build_year(year))

    master = pd.concat(year_frames, ignore_index=True)

    # Presencia longitudinal / estabilidad.
    presence_path = AUDIT / "section_presence_audit.csv"
    if presence_path.exists():
        presence = pd.read_csv(presence_path)
    else:
        presence = (
            master.groupby(["EDOCVE", "SECCION"])
            .agg(
                n_years=("AELEC", "nunique"),
                n_mpios=("MPIOCVE", "nunique"),
                n_types=("TIPOSEC", "nunique"),
            )
            .reset_index()
        )

    keep_presence = [c for c in ["EDOCVE", "SECCION", "n_years", "n_mpios", "n_types"] if c in presence.columns]
    master = master.merge(presence[keep_presence], on=["EDOCVE", "SECCION"], how="left")
    master["STABLE_MUNICIPALITY_ALL_YEARS"] = master["n_mpios"].eq(1)
    master["STABLE_TIPO_ALL_YEARS"] = master["n_types"].eq(1)

    # Presencia dentro de cada familia electoral.
    for family, years in [
        ("INTERMEDIA", [2009, 2015, 2021]),
        ("PRESIDENCIAL", [2012, 2018, 2024]),
    ]:
        fam = (
            master.loc[master["AELEC"].isin(years)]
            .groupby(["EDOCVE", "SECCION"])["AELEC"]
            .nunique()
            .rename(f"N_{family}")
            .reset_index()
        )
        master = master.merge(fam, on=["EDOCVE", "SECCION"], how="left")

    # Orden temporal dentro de la familia correcta.
    master = master.sort_values(["EDOCVE", "SECCION", "TIPO_ELECCION", "AELEC"]).reset_index(drop=True)
    g = master.groupby(["EDOCVE", "SECCION", "TIPO_ELECCION"], sort=False)

    master["PREV_YEAR"] = g["AELEC"].shift(1)
    prev_cols = [
        "PCT_ABSTENCION", "PCT_PARTICIPACION", "LN", "PCT_NS_LN", "EDAD_PROM_LN",
        "PROP_LN_18_24", "PROP_LN_25_34", "PROP_LN_60_plus",
    ]
    for col in prev_cols:
        master[f"PREV_{col}"] = g[col].shift(1)

    master["PREV2_PCT_ABSTENCION"] = g["PCT_ABSTENCION"].shift(2)
    master["DELTA_ABST_VS_PREV"] = master["PCT_ABSTENCION"] - master["PREV_PCT_ABSTENCION"]
    master["DELTA_LN_PCT_VS_PREV"] = safe_divide(master["LN"] - master["PREV_LN"], master["PREV_LN"])
    master["TREND_ABST_2_INTERVALS"] = master["PREV_PCT_ABSTENCION"] - master["PREV2_PCT_ABSTENCION"]

    # Banderas de calidad: no borramos todavía nada.
    master["FLAG_DENOM_ZERO"] = (master["SV"] + master["NV"]).eq(0)
    master["FLAG_NS_GT_05PCT"] = master["PCT_NS_LN"].gt(0.05)
    master["FLAG_NS_GT_10PCT"] = master["PCT_NS_LN"].gt(0.10)
    master["FLAG_NS_GT_25PCT"] = master["PCT_NS_LN"].gt(0.25)

    out = PROCESSED / "section_election_master_v1.csv.gz"
    master.to_csv(out, index=False, compression="gzip")

    # Resumen de calidad a nivel sección.
    quality_rows = []
    for year, d in master.groupby("AELEC"):
        quality_rows.append({
            "year": int(year),
            "sections": len(d),
            "denom_zero_sections": int(d["FLAG_DENOM_ZERO"].sum()),
            "ns_gt_5pct": int((d["PCT_NS_LN"] > 0.05).sum()),
            "ns_gt_10pct": int((d["PCT_NS_LN"] > 0.10).sum()),
            "ns_gt_25pct": int((d["PCT_NS_LN"] > 0.25).sum()),
            "ns_gt_50pct": int((d["PCT_NS_LN"] > 0.50).sum()),
            "ns_median": float(d["PCT_NS_LN"].median()),
            "ns_p95": float(d["PCT_NS_LN"].quantile(0.95)),
            "ns_max": float(d["PCT_NS_LN"].max()),
            "abst_median": float(d["PCT_ABSTENCION"].median()),
            "abst_p25": float(d["PCT_ABSTENCION"].quantile(0.25)),
            "abst_p75": float(d["PCT_ABSTENCION"].quantile(0.75)),
        })
    quality = pd.DataFrame(quality_rows)
    quality.to_csv(PROCESSED / "section_quality_summary.csv", index=False)

    # Controles auxiliares.
    national = master.groupby("AELEC")[["LN", "SV", "NV", "NS"]].sum()
    national["PCT_PARTICIPACION"] = national["SV"] / (national["SV"] + national["NV"])
    national["PCT_ABSTENCION"] = national["NV"] / (national["SV"] + national["NV"])
    national.to_csv(PROCESSED / "national_totals_check.csv")

    nb_2024 = master.loc[master["AELEC"] == 2024, ["LN_NB", "SV_NB", "NV_NB"]].sum()
    nb_2024.to_csv(PROCESSED / "nonbinary_2024_summary.csv")

    with (PROCESSED / "build_master_log.txt").open("w", encoding="utf-8") as fh:
        fh.write(f"MASTER SHAPE: {master.shape}\n\n")
        fh.write("QUALITY BY YEAR\n")
        fh.write(quality.to_string(index=False))
        fh.write("\n\nNATIONAL TOTALS\n")
        fh.write(national.to_string())
        fh.write("\n\nNONBINARY 2024\n")
        fh.write(nb_2024.to_string())

    print("\n=== Base maestra terminada ===")
    print(f"Filas: {len(master):,}")
    print(f"Columnas: {master.shape[1]}")
    print(f"Archivo principal: {out.relative_to(ROOT)}")
    print(f"Control de calidad: {(PROCESSED / 'section_quality_summary.csv').relative_to(ROOT)}")
    return master


if __name__ == "__main__":
    build_master()
