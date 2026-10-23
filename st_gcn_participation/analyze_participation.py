from __future__ import annotations

import base64
import html
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "Data"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

FILES = sorted(DATA.glob("Participación_Datos completos_data_*.csv"))
CHUNKSIZE = 500_000
MIN_MUNICIPAL_TOTAL = 10_000

USECOLS = [
    "Año",
    "Sexo",
    "Tiposec",
    "Estado",
    "Municipio",
    "Población ind/afro",
    "DEL",
    "Edonom",
    "Sección numérica",
    "% Participación",
    "No votaron",
    "Sí votaron",
]


def rate(si: pd.Series, no: pd.Series) -> pd.Series:
    total = si + no
    return np.where(total > 0, si / total, np.nan)


def aggregate_sum(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return (
        df.groupby(keys, dropna=False, observed=True)[["Sí votaron", "No votaron"]]
        .sum()
        .reset_index()
    )


def add_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["total"] = df["Sí votaron"] + df["No votaron"]
    df["participacion"] = np.where(df["total"] > 0, df["Sí votaron"] / df["total"], np.nan)
    df["abstencion"] = np.where(df["total"] > 0, df["No votaron"] / df["total"], np.nan)
    return df


def combine(parts: list[pd.DataFrame], keys: list[str]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame(columns=keys + ["Sí votaron", "No votaron", "total", "participacion", "abstencion"])
    df = pd.concat(parts, ignore_index=True)
    df = aggregate_sum(df, keys)
    return add_rates(df)


def fig_to_base64() -> str:
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    return base64.b64encode(buf.getvalue()).decode("ascii")


def line_chart(df: pd.DataFrame, cols: list[str], title: str, ylabel: str) -> str:
    plt.figure(figsize=(8, 4.5))
    for col in cols:
        plt.plot(df["Año"], df[col] * 100, marker="o", label=col)
    plt.title(title)
    plt.xlabel("Año")
    plt.ylabel(ylabel)
    plt.grid(alpha=0.25)
    plt.legend()
    return fig_to_base64()


def grouped_bar(df: pd.DataFrame, key: str, title: str) -> str:
    pivot = df.pivot(index="Año", columns=key, values="participacion").sort_index()
    ax = (pivot * 100).plot(kind="bar", figsize=(9, 4.8))
    ax.set_title(title)
    ax.set_xlabel("Año")
    ax.set_ylabel("Participación (%)")
    ax.grid(axis="y", alpha=0.25)
    return fig_to_base64()


def horizontal_bar(df: pd.DataFrame, label: str, title: str) -> str:
    d = df.copy().sort_values("participacion")
    plt.figure(figsize=(8, 5.5))
    plt.barh(d[label].astype(str), d["participacion"] * 100)
    plt.title(title)
    plt.xlabel("Participación (%)")
    plt.grid(axis="x", alpha=0.25)
    return fig_to_base64()


def heatmap_state_year(df: pd.DataFrame) -> str:
    pivot = df.pivot(index="Edonom", columns="Año", values="participacion").sort_index()
    plt.figure(figsize=(8, 9))
    plt.imshow(pivot * 100, aspect="auto", cmap="viridis")
    plt.colorbar(label="Participación (%)")
    plt.yticks(range(len(pivot.index)), pivot.index, fontsize=7)
    plt.xticks(range(len(pivot.columns)), pivot.columns)
    plt.title("Heatmap participación por estado y año")
    return fig_to_base64()


def hist_chart(hist: pd.DataFrame) -> str:
    pivot = hist.pivot(index="bin", columns="Año", values="rows").fillna(0)
    ax = pivot.plot(kind="bar", figsize=(10, 4.8), width=0.85)
    ax.set_title("Distribución de participación por fila")
    ax.set_xlabel("Bin de participación calculada")
    ax.set_ylabel("Filas")
    ax.grid(axis="y", alpha=0.25)
    return fig_to_base64()


def table(df: pd.DataFrame, n: int | None = None) -> str:
    d = df.head(n) if n else df
    return d.to_html(index=False, escape=True, float_format=lambda x: f"{x:,.4f}")


def read_all() -> dict[str, pd.DataFrame | dict[str, int]]:
    national_parts = []
    state_parts = []
    sex_parts = []
    tipo_parts = []
    ind_parts = []
    muni_parts = []
    hist_parts = []
    quality_rows = []
    sample_parts = []

    for path in FILES:
        for chunk in pd.read_csv(path, usecols=USECOLS, chunksize=CHUNKSIZE, low_memory=False):
            chunk["Sí votaron"] = pd.to_numeric(chunk["Sí votaron"], errors="coerce").fillna(0)
            chunk["No votaron"] = pd.to_numeric(chunk["No votaron"], errors="coerce").fillna(0)
            chunk["total"] = chunk["Sí votaron"] + chunk["No votaron"]
            chunk["participacion_calc"] = rate(chunk["Sí votaron"], chunk["No votaron"])
            chunk["pct_file"] = pd.to_numeric(
                chunk["% Participación"].astype(str).str.replace("%", "", regex=False),
                errors="coerce",
            ) / 100
            year = int(chunk["Año"].iloc[0])
            mismatch = (chunk["pct_file"] - chunk["participacion_calc"]).abs().gt(0.005)

            quality_rows.append(
                {
                    "Año": year,
                    "filas": len(chunk),
                    "del_nulo": int(chunk["DEL"].isna().sum()),
                    "denominador_cero": int(chunk["total"].eq(0).sum()),
                    "pct_participacion_nulo": int(chunk["pct_file"].isna().sum()),
                    "pct_inconsistente_gt_0_5pp": int(mismatch.fillna(False).sum()),
                    "participacion_0": int(chunk["participacion_calc"].eq(0).sum()),
                    "participacion_100": int(chunk["participacion_calc"].eq(1).sum()),
                    "participacion_lt_5": int(chunk["participacion_calc"].lt(0.05).sum()),
                    "participacion_gt_95": int(chunk["participacion_calc"].gt(0.95).sum()),
                }
            )

            valid = chunk[chunk["total"] > 0].copy()
            valid["bin"] = pd.cut(
                valid["participacion_calc"],
                bins=np.linspace(0, 1, 21),
                include_lowest=True,
                precision=2,
            ).astype(str)
            hist_parts.append(valid.groupby(["Año", "bin"], observed=True).size().rename("rows").reset_index())
            sample_parts.append(valid[["Año", "participacion_calc", "total"]].sample(frac=0.002, random_state=42))

            base_cols = ["Año", "Sí votaron", "No votaron"]
            national_parts.append(aggregate_sum(chunk[base_cols], ["Año"]))
            state_parts.append(aggregate_sum(chunk[["Año", "Edonom", "Estado", "Sí votaron", "No votaron"]], ["Año", "Edonom", "Estado"]))
            sex_parts.append(aggregate_sum(chunk[["Año", "Sexo", "Sí votaron", "No votaron"]], ["Año", "Sexo"]))
            tipo_parts.append(aggregate_sum(chunk[["Año", "Tiposec", "Sí votaron", "No votaron"]], ["Año", "Tiposec"]))
            ind_parts.append(aggregate_sum(chunk[["Año", "Población ind/afro", "Sí votaron", "No votaron"]], ["Año", "Población ind/afro"]))
            muni_parts.append(
                aggregate_sum(
                    chunk[["Año", "Edonom", "Estado", "Municipio", "Sí votaron", "No votaron"]],
                    ["Año", "Edonom", "Estado", "Municipio"],
                )
            )

    quality = pd.DataFrame(quality_rows).groupby("Año", as_index=False).sum()
    hist = pd.concat(hist_parts, ignore_index=True).groupby(["Año", "bin"], as_index=False)["rows"].sum()
    sample = pd.concat(sample_parts, ignore_index=True)

    return {
        "national": combine(national_parts, ["Año"]),
        "state": combine(state_parts, ["Año", "Edonom", "Estado"]),
        "sex": combine(sex_parts, ["Año", "Sexo"]),
        "tipo": combine(tipo_parts, ["Año", "Tiposec"]),
        "ind": combine(ind_parts, ["Año", "Población ind/afro"]),
        "municipality": combine(muni_parts, ["Año", "Edonom", "Estado", "Municipio"]),
        "hist": hist,
        "quality": quality,
        "sample": sample,
    }


def save_outputs(data: dict[str, pd.DataFrame]) -> None:
    for name, df in data.items():
        if name != "sample":
            df.to_csv(OUT / f"{name}.csv", index=False)


def build_html(data: dict[str, pd.DataFrame]) -> str:
    national = data["national"].sort_values("Año")
    state = data["state"]
    sex = data["sex"]
    tipo = data["tipo"]
    ind = data["ind"]
    muni = data["municipality"]
    hist = data["hist"]
    quality = data["quality"]

    latest = int(national["Año"].max())
    state_latest = state[state["Año"].eq(latest)].copy()
    top_states = state_latest.nlargest(10, "participacion")[["Estado", "participacion", "abstencion", "total"]]
    bottom_states = state_latest.nsmallest(10, "participacion")[["Estado", "participacion", "abstencion", "total"]]
    muni_latest = muni[(muni["Año"].eq(latest)) & (muni["total"].ge(MIN_MUNICIPAL_TOTAL))].copy()
    top_muni = muni_latest.nlargest(15, "participacion")[["Estado", "Municipio", "participacion", "abstencion", "total"]]
    bottom_muni = muni_latest.nsmallest(15, "participacion")[["Estado", "Municipio", "participacion", "abstencion", "total"]]

    state_delta = state.sort_values(["Edonom", "Año"]).copy()
    state_delta["delta_pp"] = state_delta.groupby("Edonom")["participacion"].diff() * 100
    latest_delta = state_delta[state_delta["Año"].eq(latest)].sort_values("delta_pp")

    charts = {
        "national": line_chart(national, ["participacion", "abstencion"], "Participación y abstención nacional ponderada", "%"),
        "sex": grouped_bar(sex, "Sexo", "Participación por sexo"),
        "tipo": grouped_bar(tipo, "Tiposec", "Participación por tipo de sección"),
        "ind": grouped_bar(ind, "Población ind/afro", "Participación por indicador indígena/afro"),
        "top_states": horizontal_bar(top_states, "Estado", f"Top estados por participación {latest}"),
        "bottom_states": horizontal_bar(bottom_states, "Estado", f"Estados con menor participación {latest}"),
        "heatmap": heatmap_state_year(state),
        "hist": hist_chart(hist),
    }

    kpis = {
        "filas": int(quality["filas"].sum()),
        "años": int(national["Año"].nunique()),
        "estados": int(state["Edonom"].nunique()),
        "participación_latest": float(national.loc[national["Año"].eq(latest), "participacion"].iloc[0] * 100),
        "abstención_latest": float(national.loc[national["Año"].eq(latest), "abstencion"].iloc[0] * 100),
        "denominador_cero": int(quality["denominador_cero"].sum()),
    }

    css = """
    body{font-family:Inter,Arial,sans-serif;margin:0;background:#f7f3ec;color:#17202a} main{max-width:1180px;margin:auto;padding:28px}
    h1,h2{color:#111827}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}.card{background:white;border:1px solid #eadfce;border-radius:14px;padding:16px;box-shadow:0 1px 4px #0001}
    .kpi{font-size:28px;font-weight:800;color:#7c2d12}.muted{color:#6b7280}.chart{width:100%;border-radius:10px}.warn{background:#fff7ed;border-left:5px solid #f97316}.ok{background:#ecfdf5;border-left:5px solid #10b981}
    table{border-collapse:collapse;width:100%;font-size:13px;background:white} th,td{border:1px solid #e5e7eb;padding:7px;text-align:right} th{text-align:center;background:#f3f4f6} td:first-child,th:first-child{text-align:left}
    """

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>EDA Participación Ciudadana</title><style>{css}</style></head>
<body><main>
<h1>Análisis estadístico inicial de participación ciudadana</h1>
<p class="muted">Generado desde <code>{html.escape(str(DATA))}</code>. Salidas en <code>{html.escape(str(OUT))}</code>.</p>

<section class="grid">
<div class="card"><div class="muted">Filas procesadas</div><div class="kpi">{kpis['filas']:,}</div></div>
<div class="card"><div class="muted">Años</div><div class="kpi">{kpis['años']}</div></div>
<div class="card"><div class="muted">Estados</div><div class="kpi">{kpis['estados']}</div></div>
<div class="card"><div class="muted">Participación {latest}</div><div class="kpi">{kpis['participación_latest']:.2f}%</div></div>
<div class="card"><div class="muted">Abstención {latest}</div><div class="kpi">{kpis['abstención_latest']:.2f}%</div></div>
<div class="card"><div class="muted">Filas con denominador cero</div><div class="kpi">{kpis['denominador_cero']:,}</div></div>
</section>

<h2>Tendencias nacionales</h2><div class="card"><img class="chart" src="data:image/png;base64,{charts['national']}"></div>
<h2>Segmentos</h2><section class="grid"><div class="card"><img class="chart" src="data:image/png;base64,{charts['sex']}"></div><div class="card"><img class="chart" src="data:image/png;base64,{charts['tipo']}"></div><div class="card"><img class="chart" src="data:image/png;base64,{charts['ind']}"></div></section>
<h2>Territorio</h2><section class="grid"><div class="card"><img class="chart" src="data:image/png;base64,{charts['top_states']}"></div><div class="card"><img class="chart" src="data:image/png;base64,{charts['bottom_states']}"></div></section>
<div class="card"><img class="chart" src="data:image/png;base64,{charts['heatmap']}"></div>
<h2>Distribución y calidad</h2><div class="card"><img class="chart" src="data:image/png;base64,{charts['hist']}"></div>
<div class="card">{table(quality)}</div>

<h2>Tablas útiles</h2>
<section class="grid"><div class="card"><h3>Nacional</h3>{table(national)}</div><div class="card"><h3>Top estados {latest}</h3>{table(top_states)}</div><div class="card"><h3>Bottom estados {latest}</h3>{table(bottom_states)}</div></section>
<section class="grid"><div class="card"><h3>Municipios mayor participación {latest}</h3>{table(top_muni)}</div><div class="card"><h3>Municipios menor participación {latest}</h3>{table(bottom_muni)}</div></section>
<div class="card"><h3>Mayores caídas estatales vs elección previa</h3>{table(latest_delta.head(10)[['Estado','participacion','delta_pp','total']])}</div>
<div class="card"><h3>Mayores subidas estatales vs elección previa</h3>{table(latest_delta.tail(10).sort_values('delta_pp', ascending=False)[['Estado','participacion','delta_pp','total']])}</div>

<h2>Lectura para ST-GCN</h2>
<div class="card warn"><p><b>Riesgo principal:</b> los CSV no incluyen aristas espaciales, geometría, centroides ni una matriz de vecindad. Una ST-GCN necesita construir el grafo fuera de estos archivos.</p>
<p><b>Riesgo temporal:</b> sólo hay 6 cortes electorales, y para una predicción tipo 2027 intermedia sólo hay 3 cortes comparables: 2009, 2015 y 2021.</p>
<p><b>Antes de modelar:</b> construir panel sección-año, llave territorial estable, máscara de secciones que nacen/mueren y una matriz de adyacencia.</p></div>

<h2>Evaluación de modelo recomendada</h2>
<div class="card ok"><p>Usar ST-GCN como challenger, no como default. Debe superar baselines temporales simples y modelos tabulares bajo split temporal estricto.</p>
<ul><li>Target: abstención = No votaron / (Sí votaron + No votaron).</li><li>Baselines: persistencia misma familia electoral, elección reciente, blend simple, modelo lineal.</li><li>Métricas: MAE pp, RMSE pp, bias, Spearman, recall@K de zonas de alta abstención.</li><li>Validación: backtesting por años, sin leakage, con ablation de grafo real vs grafo aleatorio/sin grafo.</li></ul></div>

</main></body></html>"""


def main() -> None:
    if not FILES:
        raise FileNotFoundError(f"No CSV files found in {DATA}")
    data = read_all()
    save_outputs(data)
    report = build_html(data)
    (OUT / "participation_eda_report.html").write_text(report, encoding="utf-8")
    print(f"Report: {OUT / 'participation_eda_report.html'}")


if __name__ == "__main__":
    main()
