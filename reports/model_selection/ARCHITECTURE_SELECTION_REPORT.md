# Selección formal de arquitectura

## Regla de selección

1. El método debe mejorar el MAE frente a `baseline_same_family` en los backtests temporales 2021 y 2024.
2. La mejora debe conservarse con bootstrap agrupado por municipio: el límite superior del IC95% de ΔMAE debe permanecer por debajo de cero.
3. Entre los métodos elegibles se minimiza el peor cociente `MAE_modelo / MAE_baseline` observado entre ambos años (criterio minimax).
4. La estabilidad por entidad se reporta como diagnóstico adicional; no se usa para escoger retrospectivamente un modelo distinto por estado.

## Resultado

**Arquitectura seleccionada:** `two_history_linear`

**Estado:** `selected_by_predefined_rule`

El modelo fue elegible por mejorar el MAE del baseline con soporte bootstrap al 95% en 2021 y 2024. Entre los elegibles, minimizó el peor cociente MAE_modelo/MAE_baseline entre ambos backtests.

## Desempeño temporal de la arquitectura seleccionada

| experiment | n | mae_pp | rmse_pp | r2 | spearman_r | top20_overlap | top10_overlap | bias_pp | mae_improvement_pct | delta_mae_vs_same_family_ci_low | delta_mae_vs_same_family_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2021_temporal_dual | 48885 | 7.6897 | 10.0936 | 0.3467 | 0.6168 | 0.5365 | 0.4723 | 1.8838 | 22.4171 | -2.5907 | -1.8614 |
| 2024_temporal_dual | 47741 | 4.3568 | 5.9464 | 0.6723 | 0.8355 | 0.7205 | 0.6381 | -1.6798 | 7.6927 | -0.4617 | -0.2595 |

## Estabilidad geográfica

| experiment | entities | entities_lower_mae_than_baseline | share_entities_lower_mae | median_delta_entity_mae_pp | p90_delta_entity_mae_pp | max_delta_entity_mae_pp |
| --- | --- | --- | --- | --- | --- | --- |
| 2021_temporal_dual | 32 | 20 | 62.5000 | -1.5881 | 1.2380 | 1.8600 |
| 2024_temporal_dual | 32 | 28 | 87.5000 | -0.4896 | 0.0033 | 0.6463 |

Un ΔMAE por entidad negativo indica que la arquitectura seleccionada tiene menor error que la persistencia de misma familia.

### Entidades con mayor degradación relativa · 2021_temporal_dual

| EDOCVE | entidad | mae_pp | baseline_entity_mae_pp | delta_entity_mae_pp | top20_overlap | baseline_entity_top20 |
| --- | --- | --- | --- | --- | --- | --- |
| 26 | SONORA | 9.2272 | 7.3672 | 1.8600 | 0.7733 | 0.7600 |
| 14 | JALISCO | 7.4738 | 5.9565 | 1.5172 | 0.7348 | 0.7178 |
| 22 | QUERETARO | 6.6236 | 5.3678 | 1.2557 | 0.7231 | 0.7077 |
| 16 | MICHOACAN | 8.0490 | 6.8020 | 1.2470 | 0.6667 | 0.6458 |
| 6 | COLIMA | 7.5496 | 6.3930 | 1.1565 | 0.6949 | 0.6780 |
| 19 | NUEVO LEON | 7.3619 | 6.2752 | 1.0868 | 0.7009 | 0.6921 |
| 27 | TABASCO | 6.8708 | 6.0361 | 0.8347 | 0.7059 | 0.6975 |
| 17 | MORELOS | 5.3947 | 4.6055 | 0.7891 | 0.5797 | 0.5362 |

### Entidades con mayor degradación relativa · 2024_temporal_dual

| EDOCVE | entidad | mae_pp | baseline_entity_mae_pp | delta_entity_mae_pp | top20_overlap | baseline_entity_top20 |
| --- | --- | --- | --- | --- | --- | --- |
| 9 | CIUDAD DE MEXICO | 3.2070 | 2.5608 | 0.6463 | 0.7366 | 0.6754 |
| 2 | BAJA CALIFORNIA | 3.9520 | 3.8813 | 0.0707 | 0.7100 | 0.6729 |
| 30 | VERACRUZ | 5.9458 | 5.8984 | 0.0473 | 0.5735 | 0.6059 |
| 14 | JALISCO | 3.1770 | 3.1672 | 0.0098 | 0.7510 | 0.7571 |
| 26 | SONORA | 3.2128 | 3.2679 | -0.0551 | 0.7901 | 0.7716 |
| 16 | MICHOACAN | 5.4608 | 5.5553 | -0.0945 | 0.6658 | 0.6340 |
| 3 | BAJA CALIFORNIA SUR | 4.0332 | 4.1306 | -0.0974 | 0.6575 | 0.6575 |
| 1 | AGUASCALIENTES | 2.6730 | 2.8355 | -0.1625 | 0.7624 | 0.7426 |

## Uso metodológico

La arquitectura seleccionada se utilizará como estimador puntual primario en la siguiente fase. Los baselines se conservarán como referencias de auditoría. La selección no se modifica posteriormente en función del resultado futuro que se desea estimar.

La incertidumbre futura se estimará por separado a partir de errores fuera de muestra de los backtests temporales; no debe interpretarse como una garantía probabilística bajo cambios estructurales no observados.