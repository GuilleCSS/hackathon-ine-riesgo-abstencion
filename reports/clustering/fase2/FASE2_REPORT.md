# Fase 2 · ¿Mejoran los grupos y las variables territoriales al modelo?

Generado por `src/clustering/02_backtest_fase2.py`. Experimento aparte: no cambia
`reports/model_selection/selected_architecture.json` ni las salidas del modelo actual.

## Protocolo

- Mismas ventanas `clean10` de la etapa 07: se predice 2021 entrenando con 2015 y
  2018, y 2024 entrenando con 2015, 2018 y 2021.
- Mismas métricas (etapa 07), bootstrap por municipio con 400 réplicas (etapa 08)
  y regla de selección (etapa 09): mejorar a la línea base en ambos años con IC95%
  de ΔMAE completamente bajo cero; gana el menor cociente de MAE en el peor año.
- Sin fuga de información: cada variable de una fila con objetivo t usa sólo
  elecciones anteriores a t; los grupos se reconstruyen para cada t.
- Hiperparámetros fijados antes de evaluar.

Modelo actual (`two_history_linear`): MAE 2021 = 7.69 pp, 2024 = 4.36 pp.

## Resultados

| Modelo | MAE 2021 (pp) | MAE 2024 (pp) | Elegible (regla 09) | Mejor que el actual en ambos años | IC95% ΔMAE vs. actual (pp) |
|---|---|---|---|---|---|
| `two_history_linear` | 7.69 | 4.36 | sí | no | — |
| `linear_vecinos` | 7.69 | 4.36 | sí | no | 2021: [-0.04, +0.03]; 2024: [-0.04, +0.04] |
| `linear_grupo` | 8.19 | 4.41 | sí | no | 2021: [+0.41, +0.59]; 2024: [+0.03, +0.09] |
| `linear_por_grupo` | 8.23 | 4.44 | sí | no | 2021: [+0.41, +0.69]; 2024: [-0.00, +0.16] |
| `baseline_same_family` | 9.91 | 4.72 | no | no | — |
| `xgb_residual_fase2` | 9.25 | 5.15 | no | no | 2021: [+1.26, +1.85]; 2024: [+0.60, +1.00] |
| `linear_contexto` | 9.87 | 5.23 | no | no | 2021: [+1.87, +2.49]; 2024: [+0.74, +0.99] |
| `xgb_fase2` | 8.80 | 5.33 | no | no | 2021: [+0.80, +1.41]; 2024: [+0.77, +1.19] |
| `hgb_fase2` | 8.66 | 5.45 | no | no | 2021: [+0.66, +1.28]; 2024: [+0.89, +1.29] |

ΔMAE negativo = el modelo se equivoca menos que el actual.

## Conclusión

Con la regla de la etapa 09, el mejor candidato es `two_history_linear`. Ningún modelo nuevo mejora al actual de forma robusta en ambos años.

## Archivos

- `01_model_comparison.csv`: métricas por modelo y año.
- `02_bootstrap.csv`: IC95% de ΔMAE frente a la línea base y al modelo actual.
- `03_candidate_summary.csv`: aplicación de la regla de selección.
- `04_xgb_feature_importance.csv`: importancia (gain) de las variables en XGBoost.
- `05_feature_manifest.csv`: cómo se calcula cada variable nueva.

## Limitaciones

- Vecinos y densidad usan la cartografía DIC-2025 también para 2015–2021.
- Sólo hay 2 años de prueba; una mejora pequeña puede no repetirse en 2027.
- Faltan variables externas (elecciones locales concurrentes, censo).
