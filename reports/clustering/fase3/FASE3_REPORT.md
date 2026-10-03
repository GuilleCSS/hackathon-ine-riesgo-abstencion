# Fase 3 · Elecciones locales concurrentes

Generado por `src/clustering/04_backtest_concurrencia.py`. Experimento aparte: no
cambia `selected_architecture.json` ni las salidas del modelo actual.

## Datos

`data/external/calendario_concurrente.csv` (de `03_build_calendario_concurrente.py`,
fuente Wikipedia, **pendiente de validar** contra INE y OPLEs): para cada estado y
elección federal 2009–2027, si hubo elección local y gubernatura el mismo día.

Variables nuevas por fila: `LOCAL_*` y `GOB_*` para la elección objetivo (`TGT`),
la historia del mismo tipo (`SAME`) y la reciente (`RECENT`). El calendario se fija
por ley antes de cada elección: no hay fuga de información.

Abstención agregada por año según hubo gubernatura concurrente:

| Año | Con gubernatura | Sin gubernatura |
|---|---|---|
| 2009 | 45.7% | 57.3% |
| 2012 | 34.8% | 39.2% |
| 2015 | 44.3% | 54.9% |
| 2018 | 35.4% | 39.2% |
| 2021 | 50.0% | 47.3% |
| 2024 | 38.1% | 41.9% |

## Resultados (mismo protocolo que la fase 2)

Modelo actual: MAE 2021 = 7.69 pp, 2024 = 4.36 pp.

| Modelo | MAE 2021 (pp) | MAE 2024 (pp) | Sesgo 2021 / 2024 (pp) | Elegible (regla 09) | IC95% ΔMAE vs. actual (pp) |
|---|---|---|---|---|---|
| `two_history_linear` | 7.69 | 4.36 | +1.88 / -1.68 | sí | — |
| `linear_concurrencia_vecinos` | 7.04 | 4.38 | -2.86 / -0.21 | sí | 2021: [-1.02, -0.30]; 2024: [-0.15, +0.20] |
| `linear_concurrencia` | 7.27 | 4.51 | -3.22 / +0.33 | no | 2021: [-0.80, -0.06]; 2024: [-0.04, +0.33] |
| `xgb_concurrencia_sin_estado` | 6.68 | 4.54 | -1.12 / -0.79 | no | 2021: [-1.43, -0.59]; 2024: [-0.06, +0.42] |
| `baseline_same_family` | 9.91 | 4.72 | +5.89 / -2.29 | no | — |
| `xgb_concurrencia` | 6.66 | 4.90 | -1.23 / -1.61 | no | 2021: [-1.39, -0.67]; 2024: [+0.34, +0.75] |

ΔMAE negativo = el modelo se equivoca menos que el actual. Peso de las variables de
concurrencia en `xgb_concurrencia` (gain): 2021: 25.1%, 2024: 18.4%.

## Conclusión

Con la regla de la etapa 09, el mejor candidato es `two_history_linear`. Ningún modelo con concurrencia mejora al actual de forma robusta en ambos años.

## Limitaciones

- En 2021 y 2024 los 32 estados tuvieron elección local: en los años de prueba sólo
  varía la gubernatura (15 y 9 estados), y la variable local sólo varía en la historia.
- 32 estados × 4 ventanas de entrenamiento: poca variación para aprender el efecto.
- El calendario no distingue qué cargos locales (congreso, ayuntamientos) ni su
  competitividad.
