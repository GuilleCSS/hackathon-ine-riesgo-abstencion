# Evaluación independiente de modelos

## Veredicto

No recomendar Ridge, HistGradientBoosting ni MLP como modelo general de producción todavía. Ninguno mejora de forma consistente la persistencia por misma familia electoral en los cuatro backtests. Ridge resulta el mejor candidato aprendido en 2021, pero falla en 2015 y 2024; HGB y MLP tampoco superan establemente los baselines.

## Resultados (puntos porcentuales)

| Objetivo | Baseline misma familia MAE | Baseline reciente MAE | Ridge MAE | HGB MAE | MLP MAE |
|---:|---:|---:|---:|---:|---:|
| 2015 | **8.11** | 15.00 | 20.35 | 23.26 | 21.66 |
| 2018 | **5.25** | 15.38 | 9.15 | 5.63 | 5.74 |
| 2021 | 10.00 | 10.05 | **7.91** | 8.51 | 8.94 |
| 2024 | **4.97** | 8.93 | 7.77 | 6.45 | 7.06 |

Hay una oportunidad operativa distinta al error: en 2021 el baseline reciente obtiene mejor Spearman (0.747) y recall de top 10% (0.589) que Ridge (0.675 y 0.524). Por tanto, la decisión depende también de si importa más calibrar la tasa o priorizar zonas.

## Revisión metodológica

- Las variables de cada ejemplo se forman con elecciones anteriores al objetivo; el train de cada fold excluye el año de prueba. Codificación categórica y escalado se ajustan en el train.
- No se observa fuga temporal directa. La validación interna aleatoria del MLP solo afecta el early stopping dentro del train, no sustituye los folds temporales.
- Secciones repetidas entre train/test son apropiadas para pronosticar unidades conocidas, pero no miden generalización a secciones nuevas.
- Se construyeron 406,866 observaciones sección-año, 72,681 identificadores y 324,829 ejemplos temporales. La llave entidad-número de sección no usa crosswalk oficial.
- Los cuatro cortes no son muestras independientes; hay solo seis elecciones y fuertes diferencias entre años/familias.
- Importancias: Ridge usa coeficientes absolutos (dummies sin estandarizar, comparación imperfecta); HGB/MLP usan permutación sobre 2024 con dos repeticiones. Son pistas, no inferencia causal ni evidencia de estabilidad.

## Variables destacadas

Las señales de mayor relevancia/permutación en 2024 son las abstenciones históricas (`abst_same_family`, `abst_recent`) y la abstención masculina/femenina reciente. En Ridge también destacan entidad y familia electoral. Esto es compatible con persistencia espacial/territorial; no implica que las covariables causen abstención.

## Pronóstico experimental 2027

El forecast inicial quedó supersedido al corregir explícitamente la familia electoral. En el pipeline final, 72,599 secciones usan abstención intermedia 2021 como comparable y 2024 como elección reciente. Medias actuales: baseline misma familia 46.20%, baseline reciente 39.86%, Ridge ajustado 47.07%, HGB ajustado 45.88%, MLP 48.76%. La desviación y falta de backtest 2027 impiden tratar estas cifras como pronóstico calibrado.

La separación de 5–6 pp entre modelos ajustados y persistencias es una señal de inestabilidad de calibración; estos pronósticos no deben tratarse como predicciones oficiales ni como riesgo calibrado. 2027 no tuvo un backtest histórico y la familia electoral objetivo se asumió, no se confirmó.

## Decisión

Conservar `baseline_same_family` como referencia principal. No desplegar las tres alternativas aprendidas ni la MLP. Reconsiderar solo tras verificar crosswalk oficial de secciones, significado de agregados, universo de población y definición del evento electoral 2027; después ampliar baselines y cuantificar incertidumbre por municipio/estado. Sin geometrías no procede ST-GCN.
