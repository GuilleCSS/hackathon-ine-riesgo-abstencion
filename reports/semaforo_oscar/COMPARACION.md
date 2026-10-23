# Semáforo 2027: oficial vs. alternativo de Oscar

Generado por `src/semaforo_oscar/02_comparar_semaforos.py`. Ninguno de los dos
semáforos se modifica; sólo se cruzan por sección.

## Qué compara

| | Oficial | Oscar |
|---|---|---|
| Estimación | `two_history_linear`: 0.048 + 0.677 × abst. 2021 + 0.180 × abst. 2024 | Persistencia: abstención 2021 (misma familia) |
| Universo | `primary_clean10`: NS ≤ 10% y sin cambios de municipio/tipo | Todas las secciones con historia comparable |
| Umbrales BAJO / MEDIO / Top10 | ≤ 42.8% / ≤ 51.1% / ≥ 55.4% | ≤ 46.5% / ≤ 57.1% / ≥ 62.6% |

Los dos usan la misma regla relativa (percentiles 50, 80 y 90 de su propio universo).

## Resultados

- Secciones en ambos: 54,772. Sólo en el de Oscar: 17,827. Sólo en el oficial: 0.
- **Mismo nivel: 92.8%** (si fueran independientes coincidirían 38.5%).
- Misma marca Top10: 98.0%. Correlación de Spearman entre estimaciones: 0.991.
- La estimación de Oscar es en promedio +2.92 pp distinta de la oficial
  (persistencia de 2021, una intermedia con más abstención, sin el ajuste hacia 2024).

Niveles (filas = oficial, columnas = Oscar):

| Oficial \ Oscar | BAJO | MEDIO | ALTO |
|---|---|---|---|
| BAJO | 26,706 | 680 | 0 |
| MEDIO | 1,568 | 14,536 | 327 |
| ALTO | 1 | 1,384 | 9,570 |

Estados con menor coincidencia:

| Estado | Secciones en ambos | Mismo nivel | Oscar − oficial (pp) | ALTO oficial / Oscar |
|---|---|---|---|---|
| COLIMA | 333 | 86.5% | +2.3 | 37 / 28 |
| GUERRERO | 2,282 | 88.3% | +1.0 | 267 / 266 |
| NAYARIT | 787 | 88.6% | +1.8 | 97 / 114 |
| BAJA CALIFORNIA SUR | 400 | 89.5% | +2.8 | 117 / 136 |
| SINALOA | 2,762 | 89.7% | +2.6 | 560 / 809 |

Por qué hay secciones sólo en el semáforo de Oscar (filtro de calidad del oficial):

| Motivo | Secciones |
|---|---|
| `comparable_high_ns` | 9,199 |
| `sin_dato_comparable` | 4,625 |
| `insufficient_inputs` | 3,530 |
| `valid_inputs_low_comparability` | 473 |

## Lectura

Las diferencias vienen de dos decisiones, no de errores: Oscar no aplica el filtro
de NS ni de estabilidad (por eso cubre más secciones, incluidas las de NS alto que
el dashboard oficial muestra en violeta), y usa persistencia en lugar de la
regresión.

En los backtests, la regresión de dos historias tiene menor error que la
persistencia en 2021 y 2024 (7.69 vs. 9.91 pp y 4.36 vs. 4.72 pp). En 2018 pierde
(11.35 vs. 4.77 pp; `03_backtest_2018.py`). Ahí sólo puede entrenarse con la
ventana de 2015, una intermedia, y sobreestima la abstención de una presidencial
por +10.9 pp. 2015 no se puede evaluar porque no hay ventana anterior.
