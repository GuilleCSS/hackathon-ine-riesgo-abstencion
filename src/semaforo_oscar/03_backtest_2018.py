"""Backtest del modelo oficial en 2018, el año que Oscar probó y el pipeline no.

La etapa 07 sólo evalúa 2021 y 2024. Aquí se reutilizan sus ventanas, su filtro
clean10 y su `run_experiment` (importados, sin modificarla) para entrenar con la
ventana 2009 + 2012 → 2015 y probar en 2012 + 2015 → 2018.

2015 no se puede evaluar: su ventana necesita 2009 y 2012, y no hay una elección
anterior con la cual entrenar. Para 2015 sólo se reporta la persistencia, que no
se entrena.

Uso:
    python src/semaforo_oscar/03_backtest_2018.py
"""
from pathlib import Path
import importlib.util

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "semaforo_oscar"
OFFICIAL = ROOT / "reports" / "dual_history" / "dual_history_model_comparison_compact.csv"
MODELS = ["two_history_linear", "baseline_same_family"]


def load_stage07():
    spec = importlib.util.spec_from_file_location("stage07", ROOT / "src" / "07_dual_history_backtest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    print("\n=== Backtest del modelo oficial en 2018 ===")
    s07 = load_stage07()
    if not s07.MASTER_PATH.exists():
        raise FileNotFoundError(f"No existe {s07.MASTER_PATH}. Ejecuta primero 02_build_master.py")
    master = pd.read_csv(s07.MASTER_PATH, low_memory=False)
    clean = {}
    for year in (2015, 2018):
        w = s07.build_window(master, year)
        clean[year] = w.loc[w["ELIGIBLE_CLEAN10"]].copy()

    results = []
    s07.run_experiment("2018_temporal_dual", clean[2015], clean[2018], results, {}, [])
    s07.add_result(results, "2015_sin_entrenamiento", "baseline_same_family",
                   clean[2015]["Y_ABSTENCION"].to_numpy(float),
                   clean[2015]["SAME_PCT_ABSTENCION"].to_numpy(float),
                   note="2015 no tiene ventana anterior para entrenar")
    new = pd.DataFrame(results)
    new.to_csv(REPORT / "05_backtest_2018_todos.csv", index=False)

    previous = pd.read_csv(OFFICIAL)
    previous = previous[previous["experiment"].isin(["2021_temporal_dual", "2024_temporal_dual"])]
    table = pd.concat([new, previous], ignore_index=True)
    table = table[table["model"].isin(MODELS)]
    table["anio"] = table["experiment"].str[:4].astype(int)
    table = table.pivot(index="anio", columns="model", values="mae_pp").reindex(columns=MODELS)
    table["gana"] = (table["two_history_linear"] < table["baseline_same_family"]).map(
        {True: "modelo oficial", False: "persistencia"}).where(table["two_history_linear"].notna(), "sin dato")
    table.round(3).to_csv(REPORT / "05_backtest_oficial_vs_persistencia.csv")
    print("\nMAE (pp), universo clean10:")
    print(table.round(3).to_string())
    print(f"\nSalida: {REPORT.relative_to(ROOT)}/05_*.csv")


if __name__ == "__main__":
    main()
