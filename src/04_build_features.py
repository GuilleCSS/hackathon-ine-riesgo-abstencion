from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "processed" / "section_election_master_v1.csv.gz"
OUT = ROOT / "data" / "processed" / "modeling"
REPORTS = ROOT / "reports" / "modeling"

OUT.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

TRANSITIONS = [
    (2009, 2015, "intermedia"),
    (2012, 2018, "presidencial"),
    (2015, 2021, "intermedia"),
    (2018, 2024, "presidencial"),
]

# Variables que sí pertenecen a la elección origen. Es decir, ya serían
# conocidas antes de intentar anticipar la siguiente elección comparable.
SOURCE_FEATURES = [
    "PCT_ABSTENCION",
    "PCT_PARTICIPACION",
    "PCT_NS_LN",
    "LN",
    "EDAD_PROM_LN",
    "PROP_LN_H",
    "PROP_LN_M",
    "PROP_LN_18_24",
    "PROP_LN_25_34",
    "PROP_LN_35_44",
    "PROP_LN_45_59",
    "PROP_LN_60_plus",
    "PCT_ABST_H",
    "PCT_ABST_M",
    "PCT_ABST_18_24",
    "PCT_ABST_25_34",
    "PCT_ABST_35_44",
    "PCT_ABST_45_59",
    "PCT_ABST_60_plus",
    "BRECHA_PART_MENOS_H",
]

KEYS = [
    "EDOCVE",
    "EDONOM",
    "MPIOCVE",
    "MPIONOM",
    "SECCION",
    "TIPOSEC",
    "DEF",
    "DEL",
]

TARGET_KEEP = [
    "PCT_ABSTENCION",
    "PCT_PARTICIPACION",
    "PCT_NS_LN",
    "LN",
    "MPIOCVE",
    "TIPOSEC",
]


def check_columns(df: pd.DataFrame) -> None:
    needed = set(KEYS + SOURCE_FEATURES + ["AELEC"] + TARGET_KEEP)
    missing = sorted(c for c in needed if c not in df.columns)
    if missing:
        raise RuntimeError(
            "La base maestra no contiene las columnas esperadas:\n  - "
            + "\n  - ".join(missing)
        )


def build_transition(
    master: pd.DataFrame,
    source_year: int,
    target_year: int,
    election_type: str,
) -> pd.DataFrame:
    src_cols = list(dict.fromkeys(KEYS + SOURCE_FEATURES))
    src = master.loc[master["AELEC"].eq(source_year), src_cols].copy()

    # La llave longitudinal es entidad + sección. Municipio y tipo se conservan
    # además para verificar estabilidad entre ambas elecciones.
    src = src.rename(
        columns={
            "MPIOCVE": "MPIOCVE_SRC",
            "MPIONOM": "MPIONOM_SRC",
            "TIPOSEC": "TIPOSEC_SRC",
            "DEF": "DEF_SRC",
            "DEL": "DEL_SRC",
            **{c: f"SRC_{c}" for c in SOURCE_FEATURES},
        }
    )

    tgt = master.loc[
        master["AELEC"].eq(target_year),
        ["EDOCVE", "SECCION"] + TARGET_KEEP,
    ].copy()

    tgt = tgt.rename(
        columns={
            "MPIOCVE": "MPIOCVE_TGT",
            "TIPOSEC": "TIPOSEC_TGT",
            "PCT_ABSTENCION": "Y_ABSTENCION",
            "PCT_PARTICIPACION": "TGT_PCT_PARTICIPACION",
            "PCT_NS_LN": "TGT_PCT_NS_LN",
            "LN": "TGT_LN",
        }
    )

    tr = src.merge(
        tgt,
        on=["EDOCVE", "SECCION"],
        how="inner",
        validate="one_to_one",
    )

    tr.insert(0, "SOURCE_YEAR", source_year)
    tr.insert(1, "TARGET_YEAR", target_year)
    tr.insert(2, "TIPO_ELECCION", election_type)

    tr["SECTION_KEY"] = (
        tr["EDOCVE"].astype("Int64").astype(str).str.zfill(2)
        + "-"
        + tr["SECCION"].astype("Int64").astype(str).str.zfill(4)
    )

    # Target alternativo: cuánto cambió la abstención respecto a la elección
    # comparable anterior.
    tr["Y_DELTA_ABSTENCION"] = (
        tr["Y_ABSTENCION"] - tr["SRC_PCT_ABSTENCION"]
    )

    # Transformación útil para modelos, sin alterar el valor original.
    tr["SRC_LOG1P_LN"] = np.log1p(tr["SRC_LN"].clip(lower=0))

    # Flags longitudinales. No borramos silenciosamente observaciones.
    tr["PAIR_SAME_MPIO"] = tr["MPIOCVE_SRC"].eq(tr["MPIOCVE_TGT"])
    tr["PAIR_SAME_TIPOSEC"] = tr["TIPOSEC_SRC"].eq(tr["TIPOSEC_TGT"])

    tr["SRC_DENOM_VALID"] = tr["SRC_PCT_ABSTENCION"].notna()
    tr["TGT_DENOM_VALID"] = tr["Y_ABSTENCION"].notna()

    tr["SRC_NS_LE_05"] = tr["SRC_PCT_NS_LN"].le(0.05)
    tr["SRC_NS_LE_10"] = tr["SRC_PCT_NS_LN"].le(0.10)
    tr["SRC_NS_LE_25"] = tr["SRC_PCT_NS_LN"].le(0.25)

    tr["TGT_NS_LE_05"] = tr["TGT_PCT_NS_LN"].le(0.05)
    tr["TGT_NS_LE_10"] = tr["TGT_PCT_NS_LN"].le(0.10)
    tr["TGT_NS_LE_25"] = tr["TGT_PCT_NS_LN"].le(0.25)

    # Conjunto principal recomendado para el primer backtest.
    # El 10 % se usa como filtro operativo conservador, pero mantendremos
    # datasets alternativos para análisis de sensibilidad.
    tr["ELIGIBLE_CLEAN10"] = (
        tr["PAIR_SAME_MPIO"]
        & tr["PAIR_SAME_TIPOSEC"]
        & tr["SRC_DENOM_VALID"]
        & tr["TGT_DENOM_VALID"]
        & tr["SRC_NS_LE_10"]
        & tr["TGT_NS_LE_10"]
    )

    # Versión menos restrictiva: sólo comparabilidad territorial y target válido.
    tr["ELIGIBLE_ALL"] = (
        tr["PAIR_SAME_MPIO"]
        & tr["PAIR_SAME_TIPOSEC"]
        & tr["SRC_DENOM_VALID"]
        & tr["TGT_DENOM_VALID"]
    )

    return tr


def write_manifest() -> None:
    rows = [
        {
            "column": "EDOCVE",
            "role": "feature_categorical",
            "available_before_target": True,
            "description": "Entidad de la sección en la elección origen.",
        },
        {
            "column": "TIPOSEC_SRC",
            "role": "feature_categorical",
            "available_before_target": True,
            "description": "Tipo de sección observado en la elección origen.",
        },
        {
            "column": "TIPO_ELECCION",
            "role": "feature_categorical",
            "available_before_target": True,
            "description": "Familia electoral: intermedia o presidencial.",
        },
        {
            "column": "SRC_LOG1P_LN",
            "role": "feature_numeric",
            "available_before_target": True,
            "description": "Logaritmo de la lista nominal de la elección origen.",
        },
    ]

    descriptions = {
        "PCT_ABSTENCION": "Abstención histórica de la elección comparable anterior.",
        "PCT_PARTICIPACION": "Participación histórica de la elección origen.",
        "PCT_NS_LN": "Proporción de registros no especificados en la elección origen.",
        "LN": "Lista nominal de la elección origen.",
        "EDAD_PROM_LN": "Edad media ponderada de la lista nominal de origen.",
        "PROP_LN_H": "Proporción de hombres en lista nominal de origen.",
        "PROP_LN_M": "Proporción de mujeres en lista nominal de origen.",
        "PROP_LN_18_24": "Proporción de lista nominal de 18 a 24 años.",
        "PROP_LN_25_34": "Proporción de lista nominal de 25 a 34 años.",
        "PROP_LN_35_44": "Proporción de lista nominal de 35 a 44 años.",
        "PROP_LN_45_59": "Proporción de lista nominal de 45 a 59 años.",
        "PROP_LN_60_plus": "Proporción de lista nominal de 60 años o más.",
        "PCT_ABST_H": "Abstención histórica entre hombres.",
        "PCT_ABST_M": "Abstención histórica entre mujeres.",
        "PCT_ABST_18_24": "Abstención histórica del grupo de 18 a 24 años.",
        "PCT_ABST_25_34": "Abstención histórica del grupo de 25 a 34 años.",
        "PCT_ABST_35_44": "Abstención histórica del grupo de 35 a 44 años.",
        "PCT_ABST_45_59": "Abstención histórica del grupo de 45 a 59 años.",
        "PCT_ABST_60_plus": "Abstención histórica del grupo de 60 años o más.",
        "BRECHA_PART_MENOS_H": "Brecha histórica de participación mujeres menos hombres.",
    }

    for c in SOURCE_FEATURES:
        rows.append({
            "column": f"SRC_{c}",
            "role": "feature_numeric",
            "available_before_target": True,
            "description": descriptions[c],
        })

    rows.extend([
        {
            "column": "Y_ABSTENCION",
            "role": "target",
            "available_before_target": False,
            "description": "Abstención observada en la elección objetivo.",
        },
        {
            "column": "Y_DELTA_ABSTENCION",
            "role": "target_alternative",
            "available_before_target": False,
            "description": "Cambio observado de abstención frente a la elección comparable anterior.",
        },
        {
            "column": "TGT_PCT_NS_LN",
            "role": "evaluation_quality_only",
            "available_before_target": False,
            "description": "Se usa únicamente para evaluar calidad del target; nunca como predictor.",
        },
        {
            "column": "TGT_LN",
            "role": "metadata_target",
            "available_before_target": False,
            "description": "Se conserva para análisis, pero no entra al modelo estricto.",
        },
    ])

    pd.DataFrame(rows).drop_duplicates("column").to_csv(
        REPORTS / "feature_manifest.csv", index=False
    )


def save_split(df: pd.DataFrame, name: str) -> None:
    df.to_parquet(OUT / f"{name}.parquet", index=False)


def main():
    if not MASTER.exists():
        raise FileNotFoundError(
            f"No existe {MASTER}. Ejecuta primero src/02_build_master.py"
        )

    print("\n=== 04 · Construcción de features y backtests ===")
    print(f"Leyendo: {MASTER.relative_to(ROOT)}")
    master = pd.read_csv(MASTER, low_memory=False)
    check_columns(master)

    transitions = []
    summary_rows = []

    for source_year, target_year, election_type in TRANSITIONS:
        print(f"\n{source_year} → {target_year} ({election_type})")
        tr = build_transition(master, source_year, target_year, election_type)

        print(f"  Parejas encontradas: {len(tr):,}")
        print(f"  Elegibles sin filtro NS: {int(tr['ELIGIBLE_ALL'].sum()):,}")
        print(f"  Elegibles clean10: {int(tr['ELIGIBLE_CLEAN10'].sum()):,}")

        save_split(tr, f"transition_{source_year}_{target_year}_all")
        save_split(
            tr.loc[tr["ELIGIBLE_CLEAN10"]].copy(),
            f"transition_{source_year}_{target_year}_clean10",
        )

        transitions.append(tr)

        summary_rows.append({
            "source_year": source_year,
            "target_year": target_year,
            "tipo_eleccion": election_type,
            "pairs_total": len(tr),
            "eligible_all": int(tr["ELIGIBLE_ALL"].sum()),
            "eligible_clean10": int(tr["ELIGIBLE_CLEAN10"].sum()),
            "same_mpio": int(tr["PAIR_SAME_MPIO"].sum()),
            "same_tiposec": int(tr["PAIR_SAME_TIPOSEC"].sum()),
            "src_ns_le_10": int(tr["SRC_NS_LE_10"].sum()),
            "tgt_ns_le_10": int(tr["TGT_NS_LE_10"].sum()),
        })

    all_transitions = pd.concat(transitions, ignore_index=True)
    save_split(all_transitions, "transitions_all")
    save_split(
        all_transitions.loc[all_transitions["ELIGIBLE_CLEAN10"]].copy(),
        "transitions_clean10",
    )

    # --------------------------------------------------------------
    # Backtest 2021
    # Sólo usamos transiciones cuyo target ocurrió antes de 2021 para
    # entrenar. El test es 2015→2021.
    # --------------------------------------------------------------
    bt21_train = all_transitions[
        (all_transitions["TARGET_YEAR"] < 2021)
        & all_transitions["ELIGIBLE_CLEAN10"]
    ].copy()

    bt21_test = all_transitions[
        (all_transitions["SOURCE_YEAR"] == 2015)
        & (all_transitions["TARGET_YEAR"] == 2021)
        & all_transitions["ELIGIBLE_CLEAN10"]
    ].copy()

    save_split(bt21_train, "backtest_2021_train_clean10")
    save_split(bt21_test, "backtest_2021_test_clean10")

    # Entrenamiento alternativo exclusivamente de la misma familia.
    bt21_family_train = all_transitions[
        (all_transitions["SOURCE_YEAR"] == 2009)
        & (all_transitions["TARGET_YEAR"] == 2015)
        & all_transitions["ELIGIBLE_CLEAN10"]
    ].copy()
    save_split(bt21_family_train, "backtest_2021_family_train_clean10")

    # --------------------------------------------------------------
    # Backtest 2024
    # Entrenamiento estrictamente temporal: targets anteriores a 2024.
    # El test es 2018→2024.
    # --------------------------------------------------------------
    bt24_train = all_transitions[
        (all_transitions["TARGET_YEAR"] < 2024)
        & all_transitions["ELIGIBLE_CLEAN10"]
    ].copy()

    bt24_test = all_transitions[
        (all_transitions["SOURCE_YEAR"] == 2018)
        & (all_transitions["TARGET_YEAR"] == 2024)
        & all_transitions["ELIGIBLE_CLEAN10"]
    ].copy()

    save_split(bt24_train, "backtest_2024_train_clean10")
    save_split(bt24_test, "backtest_2024_test_clean10")

    bt24_family_train = all_transitions[
        (all_transitions["SOURCE_YEAR"] == 2012)
        & (all_transitions["TARGET_YEAR"] == 2018)
        & all_transitions["ELIGIBLE_CLEAN10"]
    ].copy()
    save_split(bt24_family_train, "backtest_2024_family_train_clean10")

    # Lista cerrada de features para que el modelado no tome columnas
    # objetivo por accidente.
    feature_cols = [
        "EDOCVE",
        "TIPOSEC_SRC",
        "TIPO_ELECCION",
        "SRC_LOG1P_LN",
        "SRC_PCT_ABSTENCION",
        "SRC_PCT_NS_LN",
        "SRC_EDAD_PROM_LN",
        "SRC_PROP_LN_H",
        "SRC_PROP_LN_M",
        "SRC_PROP_LN_18_24",
        "SRC_PROP_LN_25_34",
        "SRC_PROP_LN_35_44",
        "SRC_PROP_LN_45_59",
        "SRC_PROP_LN_60_plus",
        "SRC_PCT_ABST_H",
        "SRC_PCT_ABST_M",
        "SRC_PCT_ABST_18_24",
        "SRC_PCT_ABST_25_34",
        "SRC_PCT_ABST_35_44",
        "SRC_PCT_ABST_45_59",
        "SRC_PCT_ABST_60_plus",
        "SRC_BRECHA_PART_MENOS_H",
    ]

    (REPORTS / "model_feature_columns.txt").write_text(
        "\n".join(feature_cols) + "\n",
        encoding="utf-8",
    )

    write_manifest()

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(REPORTS / "transition_summary.csv", index=False)

    split_summary = pd.DataFrame([
        {"split": "backtest_2021_train_clean10", "rows": len(bt21_train)},
        {"split": "backtest_2021_family_train_clean10", "rows": len(bt21_family_train)},
        {"split": "backtest_2021_test_clean10", "rows": len(bt21_test)},
        {"split": "backtest_2024_train_clean10", "rows": len(bt24_train)},
        {"split": "backtest_2024_family_train_clean10", "rows": len(bt24_family_train)},
        {"split": "backtest_2024_test_clean10", "rows": len(bt24_test)},
    ])
    split_summary.to_csv(REPORTS / "backtest_split_summary.csv", index=False)

    # Controles anti-leakage.
    forbidden = [
        c for c in feature_cols
        if c.startswith("TGT_") or c.startswith("Y_")
    ]
    if forbidden:
        raise RuntimeError(
            f"Se detectaron features con posible fuga de información: {forbidden}"
        )

    print("\n=== Features terminadas ===")
    print(f"Salida de datasets: {OUT.relative_to(ROOT)}")
    print(f"Reportes: {REPORTS.relative_to(ROOT)}")
    print("\nResumen de transiciones:")
    print(summary.to_string(index=False))
    print("\nResumen de splits:")
    print(split_summary.to_string(index=False))
    print("\n[OK] Ninguna columna objetivo/target está incluida en model_feature_columns.txt")


if __name__ == "__main__":
    main()
