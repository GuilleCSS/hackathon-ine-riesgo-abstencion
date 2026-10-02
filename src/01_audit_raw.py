from pathlib import Path
from collections import Counter
import time
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "reports" / "audit"
OUT.mkdir(parents=True, exist_ok=True)

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
COLS = [
    "AELEC", "FELECCION", "EDOCVE", "EDONOM", "MPIOCVE", "MPIONOM",
    "SECCION", "TIPOSEC", "DEF", "DEL", "SEXO", "EDAD", "LN", "SV", "NV", "NS"
]
NUMERIC = ["AELEC", "EDOCVE", "MPIOCVE", "SECCION", "DEF", "DEL", "SEXO", "EDAD", "LN", "SV", "NV", "NS"]


def zip_path(year: int) -> Path:
    return RAW / f"DatosAbiertos_DECEyEC_ConteosCensales{year}.zip"


def safe_ratio(num, den):
    return float(num / den) if den else np.nan


def markdown_table(df: pd.DataFrame) -> str:
    # Evita depender del paquete tabulate.
    cols = list(df.columns)
    widths = {c: max(len(str(c)), *(len(str(v)) for v in df[c].astype(str).tolist())) for c in cols}
    header = "| " + " | ".join(str(c).ljust(widths[c]) for c in cols) + " |"
    sep = "| " + " | ".join("-" * widths[c] for c in cols) + " |"
    rows = [
        "| " + " | ".join(str(row[c]).ljust(widths[c]) for c in cols) + " |"
        for _, row in df.iterrows()
    ]
    return "\n".join([header, sep, *rows])


def main() -> None:
    year_rows = []
    file_rows = []
    missing_rows = []
    geo_parts = []

    print("\n=== 01 · Auditoría RAW CCPC 2009–2024 ===\n")

    for year in YEARS:
        zpath = zip_path(year)
        if not zpath.exists():
            raise FileNotFoundError(f"No se encontró: {zpath}")

        t0 = time.time()
        print(f"[{year}] Abriendo {zpath.name}")

        raw_rows = 0
        entities = set()
        municipalities = set()
        sections = set()
        sexes = set()
        ages = set()
        section_types = set()
        totals = Counter({"LN": 0, "SV": 0, "NV": 0, "NS": 0})
        missing = Counter({c: 0 for c in COLS})
        balance_error_rows = 0
        negative_rows = 0
        zero_sv_nv_rows = 0
        geo_year_parts = []

        with zipfile.ZipFile(zpath) as zf:
            csvs = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
            if len(csvs) != 32:
                raise RuntimeError(f"{year}: se esperaban 32 CSV y hay {len(csvs)}")

            for idx, name in enumerate(csvs, start=1):
                file_t0 = time.time()
                with zf.open(name) as fh:
                    df = pd.read_csv(fh, encoding="utf-8-sig", low_memory=False)

                df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
                missing_cols = sorted(set(COLS) - set(df.columns))
                if missing_cols:
                    raise RuntimeError(f"{year} · {name}: faltan columnas {missing_cols}")

                # Mantener sólo columnas oficiales de interés.
                df = df[COLS].copy()
                for col in NUMERIC:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                n = len(df)
                raw_rows += n

                file_missing = int(df.isna().sum().sum())
                for col in COLS:
                    missing[col] += int(df[col].isna().sum())

                entity_values = df["EDOCVE"].dropna().astype(int).unique()
                entities.update(entity_values.tolist())

                mp = df[["EDOCVE", "MPIOCVE"]].dropna().drop_duplicates().astype(int)
                municipalities.update(map(tuple, mp.to_numpy()))

                sec = df[["EDOCVE", "SECCION"]].dropna().drop_duplicates().astype(int)
                sections.update(map(tuple, sec.to_numpy()))

                sexes.update(df["SEXO"].dropna().astype(int).unique().tolist())
                ages.update(df["EDAD"].dropna().astype(int).unique().tolist())
                section_types.update(df["TIPOSEC"].dropna().astype(str).str.strip().unique().tolist())

                for col in ["LN", "SV", "NV", "NS"]:
                    totals[col] += int(df[col].fillna(0).sum())

                file_balance = int((df["LN"].fillna(-1) != (df["SV"].fillna(0) + df["NV"].fillna(0) + df["NS"].fillna(0))).sum())
                file_negative = int((df[["LN", "SV", "NV", "NS"]] < 0).any(axis=1).sum())
                file_zero = int(((df["SV"].fillna(0) + df["NV"].fillna(0)) == 0).sum())

                balance_error_rows += file_balance
                negative_rows += file_negative
                zero_sv_nv_rows += file_zero

                geo = df[["AELEC", "EDOCVE", "EDONOM", "MPIOCVE", "MPIONOM", "SECCION", "TIPOSEC", "DEF", "DEL"]].drop_duplicates()
                geo_year_parts.append(geo)

                file_rows.append({
                    "year": year,
                    "file": Path(name).name,
                    "rows": n,
                    "municipalities": len(mp),
                    "sections": len(sec),
                    "missing_cells": file_missing,
                    "balance_error_rows": file_balance,
                    "negative_rows": file_negative,
                    "seconds": round(time.time() - file_t0, 2),
                })

                if idx % 8 == 0 or idx == len(csvs):
                    print(f"    {idx:02d}/{len(csvs)} CSV procesados")

                del df

        geo_year = pd.concat(geo_year_parts, ignore_index=True).drop_duplicates()
        geo_parts.append(geo_year)
        multi_geo = int((geo_year.groupby(["EDOCVE", "SECCION"], dropna=False).size() > 1).sum())

        denom = totals["SV"] + totals["NV"]
        year_rows.append({
            "year": year,
            "raw_rows": raw_rows,
            "entities": len(entities),
            "municipalities": len(municipalities),
            "sections_unique": len(sections),
            "section_geo_records": len(geo_year),
            "sections_multi_geo_same_year": multi_geo,
            "sex_values": "|".join(map(str, sorted(sexes))),
            "age_min": min(ages) if ages else np.nan,
            "age_max": max(ages) if ages else np.nan,
            "tipo_seccion_values": "|".join(sorted(section_types)),
            "LN_total": totals["LN"],
            "SV_total": totals["SV"],
            "NV_total": totals["NV"],
            "NS_total": totals["NS"],
            "pct_participacion": safe_ratio(totals["SV"], denom),
            "pct_abstencion": safe_ratio(totals["NV"], denom),
            "pct_ns_ln": safe_ratio(totals["NS"], totals["LN"]),
            "balance_error_rows": balance_error_rows,
            "negative_rows": negative_rows,
            "zero_sv_nv_rows": zero_sv_nv_rows,
            "missing_cells": sum(missing.values()),
            "seconds": round(time.time() - t0, 1),
        })
        missing_rows.append({"year": year, **missing})
        print(f"[{year}] Listo en {time.time() - t0:.1f} s · {raw_rows:,} filas · {len(sections):,} secciones\n")

    # Presencia longitudinal y estabilidad geográfica simple.
    all_geo = pd.concat(geo_parts, ignore_index=True).drop_duplicates()
    presence = (
        all_geo.groupby(["EDOCVE", "SECCION"], dropna=False)
        .agg(
            n_years=("AELEC", "nunique"),
            years_present=("AELEC", lambda x: "|".join(map(str, sorted(set(map(int, x)))))),
            n_mpios=("MPIOCVE", "nunique"),
            n_types=("TIPOSEC", "nunique"),
        )
        .reset_index()
    )

    year_sets = {
        year: set(map(tuple, all_geo.loc[all_geo["AELEC"] == year, ["EDOCVE", "SECCION"]].drop_duplicates().astype(int).to_numpy()))
        for year in YEARS
    }

    presence_idx = presence.set_index(["EDOCVE", "SECCION"])
    cohort_specs = [
        ("Intermedias 2009-2015-2021", [2009, 2015, 2021]),
        ("Presidenciales 2012-2018-2024", [2012, 2018, 2024]),
        ("Los seis procesos", YEARS),
    ]
    cohort_rows = []
    for label, years in cohort_specs:
        cohort = set.intersection(*(year_sets[y] for y in years))
        sub = presence_idx.loc[list(cohort)] if cohort else presence_idx.iloc[0:0]
        cohort_rows.append({
            "cohort": label,
            "years": "|".join(map(str, years)),
            "sections_present_all": len(cohort),
            "stable_municipality": int((sub["n_mpios"] == 1).sum()) if len(sub) else 0,
            "stable_tipo_seccion": int((sub["n_types"] == 1).sum()) if len(sub) else 0,
            "stable_both": int(((sub["n_mpios"] == 1) & (sub["n_types"] == 1)).sum()) if len(sub) else 0,
        })

    year_df = pd.DataFrame(year_rows)
    file_df = pd.DataFrame(file_rows)
    missing_df = pd.DataFrame(missing_rows)
    cohort_df = pd.DataFrame(cohort_rows)

    year_df.to_csv(OUT / "audit_year_summary.csv", index=False)
    file_df.to_csv(OUT / "audit_file_summary.csv", index=False)
    missing_df.to_csv(OUT / "audit_missing_by_year.csv", index=False)
    presence.to_csv(OUT / "section_presence_audit.csv", index=False)
    cohort_df.to_csv(OUT / "cohort_summary.csv", index=False)

    report = []
    report.append("# Auditoría reproducible CCPC 2009–2024\n")
    report.append("Este reporte se genera automáticamente desde los seis ZIP originales del INE.\n")
    report.append("## Resumen por año\n")
    pretty_year = year_df.copy()
    for c in ["pct_participacion", "pct_abstencion", "pct_ns_ln"]:
        pretty_year[c] = pretty_year[c].map(lambda v: f"{v:.6f}" if pd.notna(v) else "NA")
    report.append(markdown_table(pretty_year))
    report.append("\n\n## Cohortes longitudinales\n")
    report.append(markdown_table(cohort_df))
    report.append("\n\n## Valores faltantes por año\n")
    report.append(markdown_table(missing_df))
    report.append("\n")

    (OUT / "AUDIT_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    print("=== Auditoría terminada ===")
    print(f"Resultados: {OUT.relative_to(ROOT)}")
    print("  - AUDIT_REPORT.md")
    print("  - audit_year_summary.csv")
    print("  - audit_file_summary.csv")
    print("  - audit_missing_by_year.csv")
    print("  - section_presence_audit.csv")
    print("  - cohort_summary.csv")


if __name__ == "__main__":
    main()
