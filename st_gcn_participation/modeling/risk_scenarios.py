from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import ParameterSampler
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from run_models import (
    CATEGORICAL,
    MODEL_OUT,
    NUMERIC,
    OUT,
    create_examples,
    create_future_examples,
    prepare_xy,
    scores,
)


YEARS_TO_BACKTEST = [2015, 2018, 2021, 2024]
SEARCH_SEED = 417
HGB_SEARCH_ITERATIONS = 12
MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


def ensure_panel() -> pd.DataFrame:
    path = OUT / "section_year_panel.csv"
    panel = pd.read_csv(path) if path.exists() else None
    if panel is None or "poblacion_mostrar_share" not in panel.columns:
        from run_models import build_section_panel

        panel = build_section_panel()
    return panel


def make_estimator(model_name: str, params: dict):
    if model_name == "ridge":
        return Ridge(**params)
    if model_name == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(random_state=SEARCH_SEED, early_stopping=False, **params)
    raise ValueError(model_name)


def parameter_candidates(model_name: str) -> list[dict]:
    if model_name == "ridge":
        return [{"alpha": a} for a in [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]]
    space = {
        "max_iter": [60, 100, 160, 240],
        "max_leaf_nodes": [7, 15, 31, 63],
        "learning_rate": [0.03, 0.06, 0.1, 0.15],
        "l2_regularization": [0.0, 0.1, 1.0, 10.0],
        "min_samples_leaf": [20, 50, 100],
    }
    return list(ParameterSampler(space, n_iter=HGB_SEARCH_ITERATIONS, random_state=SEARCH_SEED))


def tune_temporally(train: pd.DataFrame, model_name: str, candidate_years: list[int]) -> tuple[dict, list[dict]]:
    folds = [
        year for year in candidate_years
        if year in set(train["target_year"])
        and train["target_year"].lt(year).any()
    ]
    if not folds:
        default = {"alpha": 10.0} if model_name == "ridge" else {
            "max_iter": 120, "max_leaf_nodes": 15, "learning_rate": 0.08,
            "l2_regularization": 2.0, "min_samples_leaf": 50,
        }
        return default, [{"model": model_name, "params": json.dumps(default), "selected": True, "mean_inner_mae_pp": np.nan, "folds": 0, "note": "insufficient prior years; fixed conservative default"}]

    rows = []
    for params in parameter_candidates(model_name):
        fold_scores = []
        for year in folds:
            inner_train = train[train["target_year"].lt(year)]
            inner_valid = train[train["target_year"].eq(year)]
            x_train, x_valid = prepare_xy(inner_train, inner_valid)
            estimator = make_estimator(model_name, params)
            estimator.fit(x_train, inner_train["y"].to_numpy())
            pred = np.clip(estimator.predict(x_valid), 0, 1)
            fold_scores.append(mean_absolute_error(inner_valid["y"], pred) * 100)
        rows.append({
            "model": model_name,
            "params": json.dumps(params, sort_keys=True),
            "mean_inner_mae_pp": float(np.mean(fold_scores)),
            "fold_scores_pp": json.dumps([round(float(x), 5) for x in fold_scores]),
            "fold_years": json.dumps(folds),
            "folds": len(folds),
        })
    ranked = sorted(rows, key=lambda x: x["mean_inner_mae_pp"])
    for i, row in enumerate(ranked):
        row["selected"] = i == 0
    return json.loads(ranked[0]["params"]), ranked


def backtest(examples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    results, search_rows = [], []
    for year in YEARS_TO_BACKTEST:
        train = examples[examples["target_year"].lt(year)].copy()
        test = examples[examples["target_year"].eq(year)].copy()
        if train.empty or test.empty:
            continue
        # For 2015/2018 there are too few distinct temporal folds to search safely.
        inner_years = [x for x in [2015, 2018, 2021] if x < year]
        fitted = {}
        for model_name in ["ridge", "hist_gradient_boosting"]:
            params, rows = tune_temporally(train, model_name, inner_years)
            for row in rows:
                search_rows.append({"outer_target_year": year, **row})
            x_train, x_test = prepare_xy(train, test)
            estimator = make_estimator(model_name, params)
            estimator.fit(x_train, train["y"].to_numpy())
            fitted[model_name] = (estimator, x_test)
            pred = np.clip(estimator.predict(x_test), 0, 1)
            results.append({"target_year": year, "model": model_name, "params": json.dumps(params, sort_keys=True), **scores(test["y"].to_numpy(), pred)})

        mlp = make_pipeline(StandardScaler(), MLPRegressor(
            hidden_layer_sizes=(24, 12), alpha=0.05, learning_rate_init=0.001,
            max_iter=80, early_stopping=True, validation_fraction=0.1,
            n_iter_no_change=8, random_state=SEARCH_SEED,
        ))
        x_train, x_test = prepare_xy(train, test)
        mlp.fit(x_train, train["y"].to_numpy())
        mlp_pred = np.clip(mlp.predict(x_test), 0, 1)
        results.append({"target_year": year, "model": "mlp_small_cpu", "params": "{24,12}; alpha=0.05", **scores(test["y"].to_numpy(), mlp_pred)})
        for name, pred in [
            ("baseline_same_family", test["abst_same_family"].to_numpy()),
            ("baseline_recent", test["abst_recent"].to_numpy()),
        ]:
            results.append({"target_year": year, "model": name, "params": "none", **scores(test["y"].to_numpy(), pred)})
    return pd.DataFrame(results), pd.DataFrame(search_rows)


def fit_final(examples: pd.DataFrame, panel: pd.DataFrame) -> tuple[pd.DataFrame, str, dict, dict]:
    future = create_future_examples(panel, 2027, target_family="intermediate")
    train = examples.copy()
    x_future = None
    tuned = {}
    params_all = {}
    preprocessor = ColumnTransformer(
        [("num", StandardScaler(), NUMERIC), ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL)],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    x_train = pd.DataFrame(preprocessor.fit_transform(train), columns=preprocessor.get_feature_names_out())
    x_future = pd.DataFrame(preprocessor.transform(future), columns=preprocessor.get_feature_names_out())
    # Hyperparameters for a 2027 forecast are selected only from temporal folds ending by 2024.
    for name in ["ridge", "hist_gradient_boosting"]:
        params, rows = tune_temporally(train, name, [2015, 2018, 2021, 2024])
        tuned[name] = rows
        model = make_estimator(name, params)
        model.fit(x_train, train["y"].to_numpy())
        future[name] = np.clip(model.predict(x_future), 0, 1)
        params_all[name] = params
        joblib.dump({"preprocessor": preprocessor, "model": model, "features": NUMERIC + CATEGORICAL, "target": "abstention"}, MODEL_DIR / f"{name}_2027.joblib")

    mlp = make_pipeline(StandardScaler(), MLPRegressor(
        hidden_layer_sizes=(24, 12), alpha=0.05, learning_rate_init=0.001,
        max_iter=80, early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=8, random_state=SEARCH_SEED,
    ))
    mlp.fit(x_train, train["y"].to_numpy())
    future["mlp_small_cpu"] = np.clip(mlp.predict(x_future), 0, 1)
    joblib.dump({"preprocessor": preprocessor, "model": mlp, "features": NUMERIC + CATEGORICAL, "target": "abstention"}, MODEL_DIR / "mlp_small_cpu_2027.joblib")
    future["baseline_same_family"] = future["abst_same_family"]
    future["baseline_recent"] = future["abst_recent"]

    backtest_mean = (
        pd.read_csv(MODEL_OUT / "tuned_backtest_metrics.csv")
        .groupby("model")["mae_pp"].mean()
    )
    classic = {name: float(backtest_mean[name]) for name in ["ridge", "hist_gradient_boosting"] if name in backtest_mean}
    base = float(backtest_mean["baseline_same_family"])
    eligible = [name for name, mae in classic.items() if mae < base]
    selected = min(eligible, key=lambda name: classic[name]) if eligible else "baseline_same_family"
    # Keep the persistent same-family baseline unless a tuned classic beats it in the historical mean.
    future["selected_abstention"] = future[selected]
    return future, selected, params_all, tuned


def classify(score: pd.Series, thresholds: dict) -> tuple[np.ndarray, np.ndarray]:
    values = pd.to_numeric(score, errors="coerce")
    level = np.select(
        [values.le(thresholds["q50"]), values.le(thresholds["q80"])],
        ["BAJO", "MEDIO"], default="ALTO",
    )
    priority = values.ge(thresholds["q90"])
    return level, priority


def risk_outputs(future: pd.DataFrame, selected: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    risk = future[["target_year", "node", "state", "selected_abstention"]].copy()
    risk = risk.rename(columns={"selected_abstention": "predicted_abstention"})
    thresholds = {
        "q50": float(risk["predicted_abstention"].quantile(0.50)),
        "q80": float(risk["predicted_abstention"].quantile(0.80)),
        "q90": float(risk["predicted_abstention"].quantile(0.90)),
    }
    risk["risk_percentile"] = risk["predicted_abstention"].rank(pct=True)
    risk["risk_level"], risk["priority_top10"] = classify(risk["predicted_abstention"], thresholds)
    candidate_columns = [c for c in ["ridge", "hist_gradient_boosting", "mlp_small_cpu", "baseline_same_family", "baseline_recent"] if c in future]
    risk["model_disagreement_pp"] = future[candidate_columns].std(axis=1) * 100
    risk["selected_model"] = selected

    scenarios = []
    specs = [
        ("S0_NONE", "Sin intervención", "none", 0.0),
        ("S1_HIGH_MINUS2", "Hipotético: −2 pp en riesgo alto", "high", 2.0),
        ("S2_PRIORITY_MINUS5", "Sensibilidad: −5 pp en Top 10%", "top10", 5.0),
    ]
    for sid, label, target, delta in specs:
        frame = risk.copy()
        if target == "high":
            targeted = frame["risk_level"].eq("ALTO")
        elif target == "top10":
            targeted = frame["priority_top10"]
        else:
            targeted = pd.Series(False, index=frame.index)
        frame["scenario_id"] = sid
        frame["scenario_label"] = label
        frame["scenario_targeted"] = targeted
        frame["assumed_reduction_pp"] = np.where(targeted, delta, 0.0)
        frame["scenario_abstention"] = np.clip(frame["predicted_abstention"] - frame["assumed_reduction_pp"] / 100, 0, 1)
        frame["scenario_risk_level"], frame["scenario_priority_top10"] = classify(frame["scenario_abstention"], thresholds)
        scenarios.append(frame)
    scenario_rows = pd.concat(scenarios, ignore_index=True)
    # Frozen baseline thresholds let us see zones exit a band after the hypothetical reduction.
    summary = scenario_rows.groupby(["scenario_id", "scenario_label"], as_index=False).agg(
        sections=("node", "size"),
        targeted_sections=("scenario_targeted", "sum"),
        baseline_mean_abstention=("predicted_abstention", "mean"),
        scenario_mean_abstention=("scenario_abstention", "mean"),
        high_sections=("risk_level", lambda x: int(x.eq("ALTO").sum())),
        high_after=("scenario_risk_level", lambda x: int(x.eq("ALTO").sum())),
        priority_sections=("priority_top10", "sum"),
        priority_after=("scenario_priority_top10", "sum"),
    )
    summary["mean_change_pp"] = (summary["scenario_mean_abstention"] - summary["baseline_mean_abstention"]) * 100
    summary["high_sections_change"] = summary["high_after"] - summary["high_sections"]
    summary["priority_sections_change"] = summary["priority_after"] - summary["priority_sections"]
    state = risk.groupby(["state", "risk_level"], as_index=False).agg(sections=("node", "size"), mean_abstention=("predicted_abstention", "mean"), priority_sections=("priority_top10", "sum"))
    state_scenarios = scenario_rows.groupby(["state", "scenario_id", "scenario_label"], as_index=False).agg(
        sections=("node", "size"), targeted_sections=("scenario_targeted", "sum"),
        baseline_mean_abstention=("predicted_abstention", "mean"),
        scenario_mean_abstention=("scenario_abstention", "mean"),
        high_before=("risk_level", lambda x: int(x.eq("ALTO").sum())),
        high_after=("scenario_risk_level", lambda x: int(x.eq("ALTO").sum())),
        priority_before=("priority_top10", "sum"), priority_after=("scenario_priority_top10", "sum"),
    )
    state_scenarios["mean_change_pp"] = (state_scenarios["scenario_mean_abstention"] - state_scenarios["baseline_mean_abstention"]) * 100
    return risk, scenario_rows, summary.merge(pd.DataFrame([thresholds]), how="cross"), state, state_scenarios


def main() -> None:
    panel = ensure_panel()
    examples = create_examples(panel)
    examples.to_csv(MODEL_OUT / "temporal_examples.csv", index=False)
    metrics, search = backtest(examples)
    metrics.to_csv(MODEL_OUT / "tuned_backtest_metrics.csv", index=False)
    search.to_csv(MODEL_OUT / "hyperparameter_search.csv", index=False)
    future, selected, final_params, final_search = fit_final(examples, panel)
    future.to_csv(MODEL_OUT / "candidate_predictions_2027.csv", index=False)
    for model, rows in final_search.items():
        pd.DataFrame(rows).assign(forecast_model=model).to_csv(MODEL_OUT / f"forecast_search_{model}.csv", index=False)
    risk, scenario_rows, scenario_summary, state, state_scenarios = risk_outputs(future, selected)
    risk.to_csv(MODEL_OUT / "risk_2027_sections.csv", index=False)
    scenario_rows.to_csv(MODEL_OUT / "scenario_2027_sections.csv", index=False)
    scenario_summary.to_csv(MODEL_OUT / "scenario_2027_summary.csv", index=False)
    state.to_csv(MODEL_OUT / "risk_2027_by_state.csv", index=False)
    state_scenarios.to_csv(MODEL_OUT / "scenario_2027_by_state.csv", index=False)
    tuning = pd.concat([pd.DataFrame(rows).assign(forecast_model=model) for model, rows in final_search.items()], ignore_index=True)
    summary = {
        "target": "aggregate abstention rate by electoral section; hypothetical 2027 target family explicitly set to intermediate",
        "selected_risk_score_model": selected,
        "selection_rule": "select a tuned classic only if its mean temporal backtest MAE is below same-family persistence; otherwise retain baseline",
        "final_hyperparameters": final_params,
        "risk_thresholds": scenario_summary[["q50", "q80", "q90"]].iloc[0].to_dict(),
        "scenario_effects_are_causal": False,
        "intervention_assumption": "assumed reductions of 2 pp in high-risk sections and 5 pp in priority Top 10%; sensitivity only",
        "sociodemographic_features": ["aggregated sex-specific abstention", "section type", "share of vote counts from rows marked Mostrar in Población ind/afro (label proxy, not population prevalence)"],
        "personal_data_used": False,
        "spatial_graph_available": False,
        "tuned_search_rows": int(len(search)),
        "forecast_search_rows": int(len(tuning)),
        "serialized_models": ["modeling/models/ridge_2027.joblib", "modeling/models/hist_gradient_boosting_2027.joblib", "modeling/models/mlp_small_cpu_2027.joblib"],
    }
    (MODEL_OUT / "risk_pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(metrics.groupby("model")["mae_pp"].mean().sort_values().to_string())
    print(f"Selected score: {selected}")
    print(scenario_summary.to_string(index=False))


if __name__ == "__main__":
    main()
