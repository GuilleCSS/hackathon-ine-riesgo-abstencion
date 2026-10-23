from __future__ import annotations

import json
import time
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
# OSCAR_DATA_DIR permite apuntar a los CSV regenerados desde los ZIP oficiales
# (src/semaforo_oscar/01_generar_csv_oscar.py); sin ella se usa ../Data como antes.
DATA = Path(os.environ.get("OSCAR_DATA_DIR", ROOT.parent / "Data"))
OUT = ROOT / "outputs"
MODEL_OUT = ROOT / "modeling" / "outputs"
MODEL_OUT.mkdir(parents=True, exist_ok=True)
CHUNKSIZE = 500_000
YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
INTERMEDIATE = {2009, 2015, 2021}
NUMERIC = ["abst_recent", "abst_same_family", "log_total_recent", "male_abst_recent", "female_abst_recent", "poblacion_mostrar_share"]
CATEGORICAL = ["state", "tipo_recent", "target_family"]


def build_section_panel() -> pd.DataFrame:
    # Raw records repeat section keys; sum vote counts before deriving rates.
    keys = ["Año", "Edonom", "Sección numérica"]
    votes_parts, sex_parts, type_parts, ind_parts = [], [], [], []
    files = sorted(DATA.glob("Participación_Datos completos_data_*.csv"))
    if not files:
        raise FileNotFoundError(f"No election CSV files under {DATA}")

    for path in files:
        for chunk in pd.read_csv(
            path,
            usecols=keys + ["Estado", "Sexo", "Tiposec", "Población ind/afro", "Sí votaron", "No votaron"],
            chunksize=CHUNKSIZE,
            low_memory=False,
        ):
            chunk = chunk.dropna(subset=["Edonom", "Sección numérica"])
            chunk["Sección numérica"] = pd.to_numeric(chunk["Sección numérica"], errors="coerce")
            chunk["Sí votaron"] = pd.to_numeric(chunk["Sí votaron"], errors="coerce").fillna(0)
            chunk["No votaron"] = pd.to_numeric(chunk["No votaron"], errors="coerce").fillna(0)
            chunk = chunk.dropna(subset=["Sección numérica"])
            chunk["Año"] = chunk["Año"].astype(int)
            votes_parts.append(chunk.groupby(keys, observed=True)[["Sí votaron", "No votaron"]].sum().reset_index())

            sex = chunk[chunk["Sexo"].isin(["Hombre", "Mujer"])].groupby(
                keys + ["Sexo"], observed=True
            )[["Sí votaron", "No votaron"]].sum().reset_index()
            sex_parts.append(sex)

            typ = chunk.groupby(keys + ["Tiposec"], observed=True)[["Sí votaron", "No votaron"]].sum().reset_index()
            typ["type_total"] = typ["Sí votaron"] + typ["No votaron"]
            type_parts.append(typ)

            chunk["ind_show_total"] = np.where(
                chunk["Población ind/afro"].astype(str).str.strip().str.casefold().eq("mostrar"),
                chunk["Sí votaron"] + chunk["No votaron"],
                0,
            )
            chunk["ind_all_total"] = chunk["Sí votaron"] + chunk["No votaron"]
            ind_parts.append(chunk.groupby(keys, observed=True)[["ind_show_total", "ind_all_total"]].sum().reset_index())

    panel = pd.concat(votes_parts, ignore_index=True).groupby(keys, as_index=False, observed=True)[["Sí votaron", "No votaron"]].sum()
    panel["total"] = panel["Sí votaron"] + panel["No votaron"]
    panel["abstention"] = np.where(panel["total"] > 0, panel["No votaron"] / panel["total"], np.nan)
    panel["state"] = panel["Edonom"].astype(str).str.strip().str.upper()

    sex = pd.concat(sex_parts, ignore_index=True).groupby(keys + ["Sexo"], as_index=False, observed=True)[["Sí votaron", "No votaron"]].sum()
    sex["sex_total"] = sex["Sí votaron"] + sex["No votaron"]
    sex["sex_abst"] = np.where(sex["sex_total"] > 0, sex["No votaron"] / sex["sex_total"], np.nan)
    sex_wide = sex.pivot(index=keys, columns="Sexo", values="sex_abst").reset_index()
    sex_wide = sex_wide.rename(columns={"Hombre": "male_abst", "Mujer": "female_abst"})

    typ = pd.concat(type_parts, ignore_index=True).groupby(keys + ["Tiposec"], as_index=False, observed=True)["type_total"].sum()
    typ = typ.sort_values("type_total").drop_duplicates(keys, keep="last").rename(columns={"Tiposec": "tipo"})[keys + ["tipo"]]
    ind = pd.concat(ind_parts, ignore_index=True).groupby(keys, as_index=False, observed=True)[["ind_show_total", "ind_all_total"]].sum()
    ind["poblacion_mostrar_share"] = np.where(ind["ind_all_total"] > 0, ind["ind_show_total"] / ind["ind_all_total"], 0)
    panel = panel.merge(sex_wide, on=keys, how="left").merge(typ, on=keys, how="left").merge(ind[keys + ["poblacion_mostrar_share"]], on=keys, how="left")
    panel = panel.sort_values(["Edonom", "Sección numérica", "Año"]).reset_index(drop=True)
    panel.to_csv(OUT / "section_year_panel.csv", index=False)
    return panel


def create_examples(panel: pd.DataFrame) -> pd.DataFrame:
    groups = {(state, section): g.set_index("Año") for (state, section), g in panel.groupby(["Edonom", "Sección numérica"], sort=False)}
    rows = []
    for (state, section), history in groups.items():
        years = sorted(history.index.tolist())
        for target_year in years[1:]:
            if target_year not in YEARS:
                continue
            available = [year for year in years if year < target_year and pd.notna(history.loc[year, "abstention"])]
            if not available or pd.isna(history.loc[target_year, "abstention"]):
                continue
            recent_year = available[-1]
            family_years = [year for year in available if (year in INTERMEDIATE) == (target_year in INTERMEDIATE)]
            same_year = family_years[-1] if family_years else recent_year
            recent = history.loc[recent_year]
            same = history.loc[same_year]
            rows.append({
                "target_year": target_year,
                "node": f"{state}:{int(section)}",
                "state": state,
                "tipo_recent": str(recent.get("tipo", "Unknown")).strip(),
                "target_family": "intermediate" if target_year in INTERMEDIATE else "presidential",
                "abst_recent": float(recent["abstention"]),
                "abst_same_family": float(same["abstention"]),
                "log_total_recent": float(np.log1p(recent["total"])),
                "male_abst_recent": float(recent["male_abst"]) if pd.notna(recent["male_abst"]) else float(recent["abstention"]),
                "female_abst_recent": float(recent["female_abst"]) if pd.notna(recent["female_abst"]) else float(recent["abstention"]),
                "poblacion_mostrar_share": float(recent["poblacion_mostrar_share"]) if pd.notna(recent["poblacion_mostrar_share"]) else 0.0,
                "y": float(history.loc[target_year, "abstention"]),
            })
    return pd.DataFrame(rows)


def create_future_examples(panel: pd.DataFrame, target_year: int, target_family: str = "intermediate") -> pd.DataFrame:
    if target_family not in {"intermediate", "presidential"}:
        raise ValueError(f"Unknown target family: {target_family}")
    family_years = INTERMEDIATE if target_family == "intermediate" else set(YEARS) - INTERMEDIATE
    rows = []
    for (state, section), history in panel.groupby(["Edonom", "Sección numérica"], sort=False):
        history = history[history["Año"].lt(target_year)].sort_values("Año")
        history = history[history["abstention"].notna()]
        if history.empty:
            continue
        recent = history.iloc[-1]
        family_history = history[history["Año"].isin(family_years)]
        same = family_history.iloc[-1] if not family_history.empty else recent
        rows.append({
            "target_year": target_year,
            "node": f"{state}:{int(section)}",
            "state": str(state).strip().upper(),
            "tipo_recent": str(recent.get("tipo", "Unknown")).strip(),
            "target_family": target_family,
            "abst_recent": float(recent["abstention"]),
            "abst_same_family": float(same["abstention"]),
            "log_total_recent": float(np.log1p(recent["total"])),
            "male_abst_recent": float(recent["male_abst"]) if pd.notna(recent["male_abst"]) else float(recent["abstention"]),
            "female_abst_recent": float(recent["female_abst"]) if pd.notna(recent["female_abst"]) else float(recent["abstention"]),
            "poblacion_mostrar_share": float(recent["poblacion_mostrar_share"]) if pd.notna(recent["poblacion_mostrar_share"]) else 0.0,
        })
    return pd.DataFrame(rows)


def scores(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    mask = np.isfinite(y) & np.isfinite(pred)
    y, pred = y[mask], pred[mask]
    if not len(y):
        return {"n": 0, "mae_pp": np.nan, "rmse_pp": np.nan, "bias_pp": np.nan, "r2": np.nan, "spearman": np.nan, "top10_recall": np.nan}
    from scipy.stats import spearmanr
    threshold = np.quantile(y, 0.9)
    actual_top = y >= threshold
    predicted_top = pred >= np.quantile(pred, 0.9)
    return {
        "n": int(len(y)),
        "mae_pp": float(mean_absolute_error(y, pred) * 100),
        "rmse_pp": float(np.sqrt(mean_squared_error(y, pred)) * 100),
        "bias_pp": float(np.mean(pred - y) * 100),
        "r2": float(r2_score(y, pred)),
        "spearman": float(spearmanr(y, pred).statistic),
        "top10_recall": float(np.sum(actual_top & predicted_top) / max(1, np.sum(actual_top))),
    }


def prepare_xy(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Categories are learned from the past fold only. Unknown future categories are ignored.
    transformer = ColumnTransformer(
        [("num", StandardScaler(), NUMERIC), ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL)],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    x_train = transformer.fit_transform(train)
    x_test = transformer.transform(test)
    names = transformer.get_feature_names_out()
    return pd.DataFrame(x_train, columns=names), pd.DataFrame(x_test, columns=names)


def run_backtests(examples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    results, predictions, importances = [], [], []
    for target_year in [2015, 2018, 2021, 2024]:
        test = examples[examples["target_year"].eq(target_year)].copy()
        train = examples[examples["target_year"].lt(target_year)].copy()
        if len(train) == 0 or len(test) == 0:
            continue
        X_train, X_test = prepare_xy(train, test)
        y_train, y_test = train["y"].to_numpy(), test["y"].to_numpy()
        family_base = test["abst_same_family"].to_numpy()
        recent_base = test["abst_recent"].to_numpy()

        fold_predictions = {
            "baseline_same_family": family_base,
            "baseline_recent": recent_base,
        }
        models = {
            "ridge": Ridge(alpha=10.0),
            "hist_gradient_boosting": HistGradientBoostingRegressor(
                max_iter=120, max_leaf_nodes=15, learning_rate=0.08, l2_regularization=2.0,
                early_stopping=True, random_state=42,
            ),
            "mlp_small": make_pipeline(
                StandardScaler(),
                MLPRegressor(hidden_layer_sizes=(32, 16), alpha=0.01, learning_rate_init=0.001,
                             max_iter=100, early_stopping=True, validation_fraction=0.1,
                             n_iter_no_change=8, random_state=42),
            ),
        }
        for name, pred in fold_predictions.items():
            metrics = scores(y_test, pred)
            results.append({"target_year": target_year, "model": name, "train_rows": len(train), **metrics})
            predictions.extend({"target_year": target_year, "model": name, "node": node, "actual": float(y), "predicted": float(p)} for node, y, p in zip(test["node"], y_test, pred))

        for name, model in models.items():
            start = time.perf_counter()
            model.fit(X_train, y_train)
            pred = np.clip(model.predict(X_test), 0, 1)
            elapsed = time.perf_counter() - start
            metrics = scores(y_test, pred)
            results.append({"target_year": target_year, "model": name, "train_rows": len(train), "fit_seconds": elapsed, **metrics})
            predictions.extend({"target_year": target_year, "model": name, "node": node, "actual": float(y), "predicted": float(p)} for node, y, p in zip(test["node"], y_test, pred))

            if target_year == 2024 and name == "ridge":
                for feature, coef in zip(X_train.columns, model.coef_):
                    importances.append({"target_year": target_year, "model": name, "feature": feature, "importance": abs(float(coef)), "coefficient": float(coef)})
            if target_year == 2024 and name == "hist_gradient_boosting":
                # Small deterministic subsample keeps permutation importance practical.
                sample = np.random.default_rng(42).choice(len(X_test), min(10_000, len(X_test)), replace=False)
                perm = permutation_importance(model, X_test.iloc[sample], y_test[sample], n_repeats=2, random_state=42, scoring="neg_mean_absolute_error")
                for feature, value in zip(X_train.columns, perm.importances_mean):
                    importances.append({"target_year": target_year, "model": name, "feature": feature, "importance": float(value), "coefficient": np.nan})
            if target_year == 2024 and name == "mlp_small":
                # Permutation importance on the encoded inputs, likewise on a fixed subset.
                sample = np.random.default_rng(42).choice(len(X_test), min(10_000, len(X_test)), replace=False)
                perm = permutation_importance(model, X_test.iloc[sample], y_test[sample], n_repeats=2, random_state=42, scoring="neg_mean_absolute_error")
                for feature, value in zip(X_train.columns, perm.importances_mean):
                    importances.append({"target_year": target_year, "model": name, "feature": feature, "importance": float(value), "coefficient": np.nan})

    return pd.DataFrame(results), pd.DataFrame(predictions), pd.DataFrame(importances)


def forecast_future(examples: pd.DataFrame, panel: pd.DataFrame, target_year: int = 2027, target_family: str = "intermediate") -> pd.DataFrame:
    train = examples.copy()
    future = create_future_examples(panel, target_year, target_family)
    X_train, X_future = prepare_xy(train, future)
    rows = []
    for model_name, model in {
        "ridge": Ridge(alpha=10.0),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            max_iter=120, max_leaf_nodes=15, learning_rate=0.08, l2_regularization=2.0,
            early_stopping=True, random_state=42,
        ),
        "mlp_small": make_pipeline(
            StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(32, 16), alpha=0.01, learning_rate_init=0.001,
                         max_iter=100, early_stopping=True, validation_fraction=0.1,
                         n_iter_no_change=8, random_state=42),
        ),
    }.items():
        model.fit(X_train, train["y"].to_numpy())
        pred = np.clip(model.predict(X_future), 0, 1)
        rows.extend({"target_year": target_year, "model": model_name, "node": node, "predicted_abstention": float(value)} for node, value in zip(future["node"], pred))
    rows.extend({"target_year": target_year, "model": "baseline_same_family", "node": node, "predicted_abstention": float(value)} for node, value in zip(future["node"], future["abst_same_family"]))
    rows.extend({"target_year": target_year, "model": "baseline_recent", "node": node, "predicted_abstention": float(value)} for node, value in zip(future["node"], future["abst_recent"]))
    return pd.DataFrame(rows)


def main() -> None:
    panel_path = OUT / "section_year_panel.csv"
    panel = pd.read_csv(panel_path) if panel_path.exists() else None
    if panel is None or "poblacion_mostrar_share" not in panel.columns:
        panel = build_section_panel()
    examples = create_examples(panel)
    examples.to_csv(MODEL_OUT / "temporal_examples.csv", index=False)
    results, predictions, importances = run_backtests(examples)
    future = forecast_future(examples, panel)
    results.to_csv(MODEL_OUT / "backtest_metrics.csv", index=False)
    predictions.to_csv(MODEL_OUT / "predictions.csv", index=False)
    future.to_csv(MODEL_OUT / "forecast_2027.csv", index=False)
    importances.sort_values("importance", ascending=False).to_csv(MODEL_OUT / "feature_importance.csv", index=False)
    summary = {
        "panel_rows": int(len(panel)), "nodes": int(panel[["Edonom", "Sección numérica"]].drop_duplicates().shape[0]),
        "examples": int(len(examples)), "years": sorted(map(int, panel["Año"].unique())),
        "cuda_torch_available": False,
        "neural_model": "sklearn MLPRegressor (CPU); PyTorch unavailable in current environment",
        "target": "section abstention = No votaron / (Sí votaron + No votaron)",
        "identity_note": "Node identifier is normalized entity name + section number; no official section crosswalk was present.",
    }
    (MODEL_OUT / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(results.to_string(index=False))
    print(f"\nResults: {MODEL_OUT}")


if __name__ == "__main__":
    main()
