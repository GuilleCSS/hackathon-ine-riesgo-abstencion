"""Genera, desde los ZIP oficiales, los CSV que leen los scripts de Oscar.

Oscar (`st_gcn_participation/`) usó la descarga "Datos completos" de la
visualización Tableau del INE (tableau.ine.mx, sitio DECEYEC), archivos
`Participación_Datos completos_data_*.csv`. Son los mismos 54,872,712 registros
de los ZIP de Conteos Censales: sus totales por año y estado coinciden
exactamente con los de la base maestra. Este script los reescribe con sus
nombres de columnas y valores para poder reproducir su trabajo sin descargar
nada de Tableau.

Única diferencia: `Población ind/afro` no existe en los ZIP. Se escribe
"Excluir" en todos los renglones; sólo afecta la variable
`poblacion_mostrar_share` de sus modelos Ridge/HGB/MLP. Su semáforo usa
persistencia y no la utiliza.

Uso:
    python src/semaforo_oscar/01_generar_csv_oscar.py
    OSCAR_DATA_DIR=data/interim/oscar_tableau python st_gcn_participation/modeling/run_models.py
"""
from pathlib import Path
import csv
import time
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "interim" / "oscar_tableau"
YEARS = [2009, 2012, 2015, 2018, 2021, 2024]

# Nombres tal como aparecen en los datos de Oscar (verificados contra
# st_gcn_participation/outputs/state.csv emparejando totales por año).
STATES = {
    1: ("AGUASCALIENTES", "Aguascalientes"), 2: ("BAJA CALIFORNIA", "Baja California"),
    3: ("BAJA CALIFORNIA SUR", "Baja California Sur"), 4: ("CAMPECHE", "Campeche"),
    5: ("COAHUILA", "Coahuila"), 6: ("COLIMA", "Colima"), 7: ("CHIAPAS", "Chiapas"),
    8: ("CHIHUAHUA", "Chihuahua"), 9: ("CIUDAD DE MÉXICO", "Ciudad de México"),
    10: ("DURANGO", "Durango"), 11: ("GUANAJUATO", "Guanajuato"), 12: ("GUERRERO", "Guerrero"),
    13: ("HIDALGO", "Hidalgo"), 14: ("JALISCO", "Jalisco"), 15: ("MEXICO", "México"),
    16: ("MICHOACAN", "Michoacán"), 17: ("MORELOS", "Morelos"), 18: ("NAYARIT", "Nayarit"),
    19: ("NUEVO LEON", "Nuevo León"), 20: ("OAXACA", "Oaxaca"), 21: ("PUEBLA", "Puebla"),
    22: ("QUERETARO", "Querétaro"), 23: ("QUINTANA ROO", "Quintana Roo"),
    24: ("SAN LUIS POTOSI", "San Luis Potosí"), 25: ("SINALOA", "Sinaloa"), 26: ("SONORA", "Sonora"),
    27: ("TABASCO", "Tabasco"), 28: ("TAMAULIPAS", "Tamaulipas"), 29: ("TLAXCALA", "Tlaxcala"),
    30: ("VERACRUZ", "Veracruz"), 31: ("YUCATAN", "Yucatán"), 32: ("ZACATECAS", "Zacatecas"),
}
SEXES = {0: "Hombre", 1: "Mujer", 2: "No binario"}
TYPES = {"U": "Urbana", "M": "Mixta", "R": "Rural"}
COLUMNS = ["Año", "Sexo", "Tiposec", "Estado", "Municipio", "Población ind/afro", "DEL",
           "Edonom", "Sección numérica", "% Participación", "No votaron", "Sí votaron"]


def convert(df):
    sv = pd.to_numeric(df["SV"], errors="coerce")
    nv = pd.to_numeric(df["NV"], errors="coerce")
    code = pd.to_numeric(df["EDOCVE"], errors="coerce").astype(int)
    total = sv + nv
    return pd.DataFrame({
        "Año": pd.to_numeric(df["AELEC"]).astype(int),
        "Sexo": pd.to_numeric(df["SEXO"]).map(SEXES),
        "Tiposec": df["TIPOSEC"].map(TYPES),
        "Estado": code.map(lambda c: STATES[c][1]),
        "Municipio": df["MPIONOM"],
        "Población ind/afro": "Excluir",
        "DEL": df["DEL"],
        "Edonom": code.map(lambda c: STATES[c][0]),
        "Sección numérica": pd.to_numeric(df["SECCION"]).astype(int),
        "% Participación": np.where(total > 0, sv / total.where(total > 0), np.nan),
        "No votaron": nv,
        "Sí votaron": sv,
    })[COLUMNS]


def main():
    print("\n=== CSV con el formato de Oscar desde los ZIP oficiales ===")
    OUT.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    for year in YEARS:
        t0 = time.time()
        path = OUT / f"Participación_Datos completos_data_{year}.csv"
        rows = 0
        with zipfile.ZipFile(RAW / f"DatosAbiertos_DECEyEC_ConteosCensales{year}.zip") as zf, \
                path.open("w", newline="", encoding="utf-8") as fh:
            header = True
            for name in sorted(n for n in zf.namelist() if n.lower().endswith(".csv")):
                with zf.open(name) as raw:
                    df = pd.read_csv(raw, dtype=str, encoding="utf-8-sig", keep_default_na=False)
                df.columns = [c.strip().lstrip("﻿") for c in df.columns]
                out = convert(df)
                out.to_csv(fh, index=False, header=header, quoting=csv.QUOTE_MINIMAL)
                header = False
                rows += len(out)
        total_rows += rows
        print(f"  {year}: {rows:,} renglones · {path.stat().st_size / 1e9:.2f} GB · {time.time() - t0:.0f} s")
    print(f"Total: {total_rows:,} renglones en {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
