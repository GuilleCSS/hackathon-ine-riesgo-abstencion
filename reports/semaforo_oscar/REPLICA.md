# Réplica del trabajo de Oscar (`st_gcn_participation/`)

Objetivo: comprobar que el semáforo alternativo de Oscar sale de los mismos datos
oficiales que usa el pipeline y que se puede regenerar sin archivos externos.

## De dónde salen sus CSV

Sus scripts leen `../Data/Participación_Datos completos_data_*.csv`, una carpeta
fuera del repo. Son la descarga "Datos completos" de la visualización Tableau del
INE (`tableau.ine.mx`, sitio DECEYEC, libro `Prototipo9`), embebida en
<https://ine.mx/transparencia/datos-abiertos/visualizacion-datos/conteos-censales-participacion/>.

Es la misma base que los ZIP de Conteos Censales que usa el pipeline:

- 54,872,712 renglones en ambos.
- Totales nacionales de SV y NV iguales en los 6 años.
- Los 192 totales estado × año de SV y NV coinciden exactamente.

Diferencias de forma, no de cifras:

| Tableau | ZIP oficial |
|---|---|
| `Población ind/afro` ("Excluir" / "Mostrar ") | no existe |
| `% Participación` calculado por Tableau | se calcula SV / (SV + NV) |
| Algunos nombres de municipio con erratas ("Hopelche}én", "San José de Gracía") | nombres limpios |

## Cómo regenerarlo

```bash
# 1. CSV con el formato de Tableau a partir de los ZIP (≈4.2 GB, ignorado por git)
python src/semaforo_oscar/01_generar_csv_oscar.py

# 2. Sus tres scripts, apuntando a esos CSV (≈11 min en Docker)
export OSCAR_DATA_DIR=data/interim/oscar_tableau
python st_gcn_participation/analyze_participation.py
python st_gcn_participation/modeling/run_models.py
python st_gcn_participation/modeling/risk_scenarios.py

# 3. Cruce con el semáforo oficial (lo usa la página "Semáforo alternativo (Oscar)")
python src/semaforo_oscar/02_comparar_semaforos.py
```

El único cambio a su código es `OSCAR_DATA_DIR`: sin la variable se sigue leyendo
`../Data` como antes. Los pasos 1 y 2 sobrescriben sus salidas versionadas
(CSV de métricas y `.joblib`). Para no ensuciar el repo, regrésalas con
`git checkout -- st_gcn_participation/outputs st_gcn_participation/modeling`.
Los CSV pesados que necesita el paso 3 (`risk_2027_sections.csv`, etc.) están
en `.gitignore`.

## Resultado

**Su semáforo se replica exacto.** Estos archivos salen idénticos byte a byte a
los que subió:

- `modeling/outputs/risk_2027_by_state.csv`
- `modeling/outputs/scenario_2027_summary.csv`
- `modeling/outputs/scenario_2027_by_state.csv`
- `modeling/outputs/risk_pipeline_summary.json`
- `modeling/outputs/run_summary.json`
- `outputs/national.csv`, `state.csv`, `sex.csv`, `tipo.csv`, `hist.csv`

El semáforo usa 72,599 secciones, con umbrales q50 46.55%, q80 57.10% y q90 62.63%,
14,520 secciones en ALTO y 7,262 en Top10. El modelo elegido es
`baseline_same_family`, con MAE medio de 7.08 pp. Todo coincide con su
`RISK_REPORT.md`.

Backtests (MAE en pp, su archivo vs. réplica):

| Modelo | 2015 | 2018 | 2021 | 2024 |
|---|---|---|---|---|
| Persistencia misma familia | 8.109 = 8.109 | 5.253 = 5.253 | 10.001 = 10.001 | 4.975 = 4.975 |
| Persistencia reciente | 14.995 = 14.995 | 15.381 = 15.381 | 10.047 = 10.047 | 8.931 = 8.931 |
| Ridge | 20.350 = 20.350 | 9.151 = 9.151 | 7.905 = 7.905 | 7.766 = 7.766 |
| HGB | 23.258 / 23.241 | 5.633 / 5.672 | 8.508 = 8.508 | 6.447 / 6.406 |
| MLP | 21.657 / 21.561 | 5.743 / 6.865 | 8.939 / 8.780 | 7.057 / 6.516 |

Las persistencias y Ridge son exactas. HGB difiere por centésimas. El MLP varía
hasta 1.1 pp: es el más sensible a la máquina y a `poblacion_mostrar_share`, que
con los ZIP siempre vale 0. Ridge y HGB también usan esa variable, pero apenas
cambian, así que su peso es casi nulo. Ninguno de los tres interviene en su semáforo.

Lo que no se replica, por diseño:

- `outputs/ind.csv`: sin la columna ind/afro sólo hay renglones "Excluir".
- `outputs/quality.csv`: `pct_inconsistente_gt_0_5pp` mide el redondeo de la
  columna de Tableau, y `del_nulo` difiere en 2 años. El resto es igual.
- `outputs/municipality.csv`: 598 renglones no empatan por las erratas de nombre.
  Las cifras por estado son iguales.

## Comparación con el semáforo oficial

Ver `COMPARACION.md`. En las 54,772 secciones que comparten, coinciden en nivel
el 92.8% (Spearman 0.991). La diferencia real es de cobertura: Oscar suma 17,827
secciones que el filtro de calidad oficial deja fuera, 9,199 de ellas por NS alto.
