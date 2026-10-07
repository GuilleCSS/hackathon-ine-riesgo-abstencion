# Resultados del experimento multinivel

Se ejecutaron 140 entrenamientos de árboles (Random Forest y HistGradientBoosting), 10 ajustes lineales y referencias de persistencia. Se compararon siete bloques de variables, dos años fuera de muestra, cinco unidades de predicción y los dos enfoques territoriales. Hay 544 registros de métricas, incluidos pesos operativos y diagnósticos. La corrida completa tardó 969.2 segundos, aproximadamente 16.2 minutos, más el piloto de recursos y la verificación.

La página, la arquitectura bloqueada y los pronósticos productivos no se modificaron.

## Selección

Se elige una configuración fija por nivel/enfoque que minimice la peor razón de MAE frente al lineal directo del mismo nivel entre 2021 y 2024. Esto considera los dos años, sin cambiar retrospectivamente de bloque para cada elección. La media de MAE también se reporta.

Random Forest quedó por delante de Gradient Boosting en las configuraciones elegidas por ese criterio. La agregación de predicciones seccionales tuvo menor MAE que el entrenamiento directo por territorio en ambos años para las configuraciones seleccionadas.

## Predicción por sección

La configuración elegida es Random Forest B5: historia, demografía, tasas por grupos, tendencias y contexto. B6 agrega expectativa etaria: mejora más 2021, pero tiene un MAE 2024 prácticamente igual y ligeramente mayor. No hay una separación sustancial que permita afirmar superioridad general de B5 frente a B6; son candidatos cercanos y la decisión depende del criterio.

| Modelo / bloque | MAE 2021 (pp) | MAE 2024 (pp) | Media MAE (pp) |
|---|---:|---:|---:|
| Lineal de dos historias | 7.690 | 4.357 | 6.023 |
| Random Forest B5 | 6.935 | 4.155 | 5.545 |
| Random Forest B6 | 6.762 | 4.156 | 5.459 |
| Gradient Boosting B5 | 8.287 | 4.227 | 6.257 |

RF B5 reduce MAE frente al lineal aproximadamente 9.82% en 2021 y 4.63% en 2024. B6 tiene mejor media, mientras B5 tiene la menor peor razón frente al lineal. Los bloques B0–B4 y los restantes candidatos están en el TXT y CSV completos.

| Métrica seccional | Lineal 2021 | RF B5 2021 | Lineal 2024 | RF B5 2024 |
|---|---:|---:|---:|---:|
| RMSE (pp) | 10.094 | 8.931 | 5.946 | 5.623 |
| R² | 0.347 | 0.489 | 0.672 | 0.707 |
| Recuperación del Top20 | 53.65% | 58.15% | 72.05% | 71.00% |

La mejora de error no equivale a mejora de todas las tareas: la recuperación del Top20 seccional de 2024 baja unos 1.05 puntos porcentuales. Si la prioridad principal es identificar territorios de mayor riesgo, hay que incorporar ese objetivo a la decisión.

## Dos enfoques por territorio

Todos los candidatos de esta tabla son Random Forest. Los errores principales se refieren a la MISMA cohorte de secciones evaluables por territorio.

| Nivel | Bloque agregado / directo | Agregado MAE 2021 | Directo MAE 2021 | Agregado MAE 2024 | Directo MAE 2024 | Media agregado / directo |
|---|---|---:|---:|---:|---:|---:|
| Entidad | B6 / B6 | 5.316 | 5.786 | 2.357 | 2.627 | 3.836 / 4.207 |
| Municipio | B6 / B5 | 8.253 | 8.701 | 4.615 | 4.968 | 6.434 / 6.835 |
| Distrito federal | B5 / B5 | 5.361 | 5.785 | 2.790 | 3.050 | 4.075 / 4.417 |
| Distrito local | B5 / B5 | 5.839 | 6.082 | 3.040 | 3.315 | 4.439 / 4.699 |

Todos los MAE están en puntos porcentuales. La agregación seleccionada usa LN previa en municipios y SV+NV previo en entidades/distritos. Ambos pesos son históricos. No se usaron pesos del año futuro en la selección.

| Nivel agregado | RMSE 2021 | R² 2021 | RMSE 2024 | R² 2024 |
|---|---:|---:|---:|---:|
| Entidad | 6.411 | -0.081 | 2.910 | 0.720 |
| Municipio | 10.597 | 0.451 | 6.339 | 0.684 |
| Distrito federal | 6.591 | 0.390 | 3.455 | 0.732 |
| Distrito local | 7.292 | 0.430 | 3.831 | 0.726 |

El R² estatal de 2021 sigue siendo negativo: aunque el error mejora respecto a las referencias históricas, la diferenciación entre entidades todavía es débil en ese ciclo. No debe ocultarse este resultado.

## Qué variables aportaron

- Demografía sola no fue suficiente para superar el modelo lineal por sección en ambos años.
- Tendencias y contexto mejoraron los bloques iniciales.
- Combinar composición, comportamiento por grupos, tendencias y contexto (B5) dio una mejora en ambos backtests seccionales.
- La expectativa por composición etaria (B6) mejoró más el MAE seccional 2021 y favoreció las configuraciones agregadas de entidad/municipio. No mejoró todo nivel/año.
- El tamaño electoral, sus cambios, composición etaria/sexual, tasas históricas, brechas y referencias territoriales se probaron por bloques. Este experimento NO identifica un efecto causal ni demuestra importancia individual de cada columna.

## Incertidumbre de la comparación

Con bootstrap pareado por municipio, el IC95% de diferencia MAE RF B5 menos lineal es negativo en ambos años: [-0.908, -0.604] pp en 2021 y [-0.324, -0.086] pp en 2024. Con agrupación más amplia por entidad, el intervalo 2024 cruza cero: [-0.452, 0.077] pp.

La diferencia directo menos agregado favorece agregación puntualmente en los cuatro niveles y ambos años. El bootstrap por entidad respalda esa diferencia en municipios en ambos años y distritos en 2024; los intervalos estatales y distritales 2021 cruzan cero. No se puede afirmar superioridad concluyente en todas las geografías.

Estos intervalos son exploratorios: se examinaron múltiples candidatos sobre los mismos dos años y no hay un holdout independiente para confirmar el ganador.

## Cobertura y alcance

- Evaluación 2021: 48,885 secciones, 32 entidades, 2,339 municipios, 300 distritos federales, 673 locales.
- Evaluación 2024: 47,741 secciones, 32 entidades, 2,343 municipios, 300 distritos federales, 673 locales.
- La cohorte representa aproximadamente 64.36% de LN nacional 2021 y 60.30% de LN nacional 2024.
- Tasas objetivo: NV/(SV+NV). NS separado. Evaluación condicionada a NS <=10% y estabilidad de municipio/tipo en las tres observaciones.
- Los distritos se mantienen en el marco de códigos de la elección previa. Los diccionarios refieren marcos históricos armonizados: esto es evaluación retrospectiva, no certificación del marco vigente 2027.
- Existe un diagnóstico `full_reference_mae_pp` sobre secciones objetivo mapeables al marco previo, fuera de la cohorte principal. No convierte automáticamente el modelo en un pronóstico de todo el electorado.
- No se usan todavía cruces RAW sexo×edad, cuantiles exactos de edad, variables espaciales ni fuentes externas.

## Resultado práctico

La siguiente opción a desarrollar es Random Forest seccional B5/B6 con agregación territorial. B5 favorece el criterio de estabilidad relativa aplicado; B6 favorece la media y algunos niveles agregados. Antes de sustituir producción hay que decidir el objetivo de selección (error de tasa versus recuperación de alto riesgo), ampliar cobertura y verificar geografía. No se implementó ningún cambio productivo.

## Verificación y reproducción

Pasaron las comprobaciones de fórmulas, agregación exacta, disponibilidad de columnas y ausencia de dependencia de predictores respecto de SV/NV o distrito del objetivo. La verificación posterior recalculó las métricas de todos los candidatos seleccionados a partir de sus predicciones guardadas y cotejó la referencia seccional contra el pipeline previo.

```powershell
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/16_experiment_multilevel.py
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/16_experiment_multilevel.py --verify-results
```

Resultados completos: `RESULTADOS_EXPERIMENTO_MULTINIVEL.txt` y `01_metricas_todas.csv`. Parámetros/variables/versiones/hashes: `configuracion.json` y `variables_por_bloque.csv`. El piloto parcial RF100 está separado en `PILOTO_RECURSOS_*` y no entra al ranking final.
