# Modelos y backtesting temporal

## Alcance

Se agregaron los datos originales a nivel de **entidad + número de sección + año**, sumando primero `Sí votaron` y `No votaron`. Target: `abstention = No votaron / (Sí votaron + No votaron)`. Esto genera 406,866 filas sección-año, 72,681 identificadores de sección y 324,829 ejemplos de predicción.

Variables disponibles antes del año objetivo: abstención en la elección más reciente, abstención en la elección previa de la misma familia, logaritmo de votos válidos del origen, tasas de abstención de hombres/mujeres, estado, tipo de sección y familia electoral. No se usa información de votos del año objetivo.

Modelos evaluados: Ridge, HistGradientBoostingRegressor y MLP pequeño (32,16) en scikit-learn. El MLP corrió en CPU: PyTorch no está instalado; no se añadió otra dependencia. ST-GCN no se probó porque no hay grafo/adyacencias espaciales.

## Diseño

Backtesting por elección: para el objetivo `t`, se entrena solo con ejemplos cuyo año objetivo sea menor que `t`. Los cortes son 2015, 2018, 2021 y 2024. Sin partición aleatoria entre años. Referencias simples: persistencia por misma familia y elección más reciente.

## Métricas

MAE/RMSE/sesgo se expresan en puntos porcentuales. `top10_recall` mide qué fracción del 10% de secciones con más abstención real se encuentra dentro del 10% de mayor riesgo predicho.

| Año | Modelo | MAE pp | RMSE pp | Sesgo pp | Spearman | Recall top 10% |
|---:|---|---:|---:|---:|---:|---:|
| 2015 | Persistencia misma familia | **8.11** | 11.73 | +3.27 | 0.606 | 0.439 |
| 2015 | Persistencia reciente | 15.00 | 17.46 | −13.58 | 0.570 | 0.402 |
| 2015 | Ridge | 20.35 | 22.96 | −19.77 | 0.448 | 0.357 |
| 2015 | HistGradientBoosting | 23.26 | 25.79 | −23.01 | 0.461 | 0.287 |
| 2015 | MLP pequeño | 21.66 | 24.34 | −21.23 | 0.424 | 0.284 |
| 2018 | Persistencia misma familia | **5.25** | 7.52 | +1.26 | 0.770 | 0.512 |
| 2018 | Persistencia reciente | 15.38 | 18.35 | +14.22 | 0.506 | 0.375 |
| 2018 | Ridge | 9.15 | 11.27 | −8.46 | 0.722 | 0.487 |
| 2018 | HistGradientBoosting | 5.63 | **7.46** | −2.73 | 0.727 | 0.532 |
| 2018 | MLP pequeño | 5.74 | 7.61 | −2.86 | 0.718 | **0.547** |
| 2021 | Persistencia misma familia | 10.00 | 12.91 | +5.64 | 0.579 | 0.431 |
| 2021 | Persistencia reciente | 10.05 | 12.04 | −8.58 | **0.747** | **0.589** |
| 2021 | Ridge | **7.91** | **10.20** | +4.37 | 0.675 | 0.524 |
| 2021 | HistGradientBoosting | 8.51 | 10.89 | +4.29 | 0.645 | 0.465 |
| 2021 | MLP pequeño | 8.94 | 11.34 | +4.35 | 0.629 | 0.467 |
| 2024 | Persistencia misma familia | **4.97** | **6.86** | −2.19 | **0.823** | **0.606** |
| 2024 | Persistencia reciente | 8.93 | 10.91 | +6.53 | 0.717 | 0.606 |
| 2024 | Ridge | 7.77 | 9.87 | −7.23 | 0.766 | 0.584 |
| 2024 | HistGradientBoosting | 6.45 | 8.29 | −5.13 | 0.806 | 0.525 |
| 2024 | MLP pequeño | 7.06 | 8.92 | −5.24 | 0.776 | 0.493 |

## Variables más relevantes

El análisis de permutación de 2024 sitúa entre las señales más útiles la abstención de misma familia, abstención reciente y tasa de abstención masculina reciente; la tasa femenina aparece también entre las primeras señales. Ridge asigna coeficientes a la familia electoral y a entidades; sus magnitudes absolutas no son comparables directamente porque no se escalaron las variables one-hot.

Son asociaciones predictivas en este backtest, no efectos causales. Las importancias de HGB/MLP se calcularon en la prueba 2024 con dos permutaciones y deben leerse como exploratorias.

## Pronóstico exploratorio 2027

El forecast inicial (`outputs/forecast_2027.csv`) fue supersedido al corregir la familia electoral de destino explícitamente a intermedia. Los resultados vigentes están en `RISK_REPORT.md` y `outputs/risk_2027_sections.csv`: promedio seleccionado 46.20% usando persistencia comparable 2021, con 2024 como elección reciente. Medias alternativas: Ridge 47.07%, HGB 45.88%, MLP 48.76%, baseline reciente 39.86%. Es extrapolación exploratoria sin backtest 2027, no pronóstico calibrado.

## Evaluación independiente

El agente evaluador concluye que ningún modelo aprendido es ganador general: Ridge reduce MAE en 2021, pero se degrada severamente en 2015 y queda detrás de persistencia en 2024. HGB se acerca a persistencia en 2018/2024; MLP no aporta ventaja estable y tarda hasta ~63 s en un fold frente a segundos para HGB. Mantener persistencia misma familia como baseline/incumbent, no desplegar el MLP ni reclamar beneficio neuronal.

## Límites / siguientes datos necesarios

- No hay crosswalk oficial para altas, bajas, fusiones y cambios de sección; la llave actual es nombre de entidad + número de sección.
- No hay geometría ni matriz de adyacencia, así que no se puede probar una ST-GCN válida.
- Los CSV no aportan lista nominal ni otras variables socio-demográficas consistentes; la predicción mide la proporción sobre los conteos observados, no turnout sobre lista nominal.
- Seis elecciones son poca profundidad temporal y 2021 puede representar un shock estructural.
- Hace falta confirmar qué elección/evento de 2027 se quiere anticipar. El forecast asume familia intermedia.

## Archivos

- `outputs/backtest_metrics.csv`: métricas por año/modelo.
- `outputs/predictions.csv`: predicciones backtest por sección.
- `outputs/feature_importance.csv`: coeficientes/importancias exploratorias.
- `outputs/forecast_2027.csv`: escenario hipotético de 2027.
- `outputs/temporal_examples.csv`: ejemplos de entrenamiento con variables.
- `../outputs/section_year_panel.csv`: panel agregado sección-año.
- Ejecutar `python modeling/run_models.py` para reproducir el entrenamiento; si ya existe `outputs/section_year_panel.csv`, la agregación cruda se omite.
