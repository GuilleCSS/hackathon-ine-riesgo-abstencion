# Segunda ronda: mejorar Random Forest sin repetir pruebas

El script `src/17_improve_random_forest.py` reutiliza la preparación temporal de la ronda anterior y compara configuraciones nuevas. Conserva las mismas cohortes, años y marcos geográficos para que los errores sean comparables.

## Variable logarítmica

`SAME_LOG_LN` y `RECENT_LOG_LN` son `log1p(lista nominal)` y YA estaban en B5/B6 de la primera ronda. Se mantienen en todas las nuevas variantes. No se presenta su inclusión como un experimento nuevo por sí sola.

Las novedades incluyen `log1p(LN_grupo)`, `log1p(SV_grupo+NV_grupo)`, logaritmos de conteos históricos SV/NV/NS y del tamaño relativo al municipio. Una transformación monotónica de un predictor no crea información adicional para los árboles; los conteos por grupo y las combinaciones derivadas se evalúan junto con la representación logarítmica.

## Configuraciones nuevas

| Variante | Novedad frente a la ronda anterior |
|---|---|
| R01 | B5 + conteos logarítmicos históricos por sexo/edad y participación. |
| R02 | B6 + referencias de pares sin propia sección, tasas suavizadas por grupo y NS por grupo. |
| R03 | Combinación compacta de historia, demografía y tendencias con logs y forma de distribución demográfica. |
| R04 | B6 + logs + forma demográfica + referencias de pares + soporte de tasas. |
| R05 | R04 + historia acumulada anterior, tanto de todas las elecciones como de la misma familia. |
| R06 | Variables de R03; el RF aprende el cambio respecto de la abstención de la misma familia. |
| R07 | Variables de R04; 96 árboles, profundidad 16 y hojas menores. |
| R08 | Variables de R05; el RF aprende el cambio respecto de la misma familia. |

La distribución demográfica incorpora entropía etaria, proporción 18–34, razón mayores/jóvenes, log razón mujeres/hombres, dispersión de tasas etarias y composición de abstencionistas. No genera microdatos.

Las tasas suavizadas usan 100 registros de referencia, fijados antes de medir errores. La referencia excluye la propia sección, usa el resto del municipio y, si no tiene soporte, el resto del estado o la tasa nacional del grupo en la elección fuente. No usa resultados futuros.

La historia acumulada se calcula cronológicamente hasta cada elección fuente, inclusive. Las variables de disponibilidad calculadas usando todos los años del proyecto no entran al modelo.

## No repetición

Antes de ajustar se cotejan firmas compuestas por datos, columnas, parámetros, objetivo, corte temporal, nivel y política de entrenamiento. Se rechaza una firma de la primera ronda y se verifica que no haya duplicados entre las 80 configuraciones nuevas planificadas.

Cada ajuste completo se guarda en `registro_pruebas.json` con una predicción Parquet en `data/processed/experiment_rf_improved`. Al repetir la ejecución, los ajustes completos se recuperan del disco; no se vuelven a entrenar. Los datos derivados se cachean por hash de datos y definiciones de variables.

Cambiar objetivo o parámetros constituye una prueba diferente, aunque comparta columnas. Los pares R03/R06, R04/R07 y R05/R08 permiten separar esos cambios.

## Evaluación

- 2021: entrenamiento con objetivos 2015 y 2018; inputs 2015/2018 para evaluar 2021.
- 2024: entrenamiento con objetivos 2015, 2018 y 2021; inputs 2018/2021 para evaluar 2024.
- Ocho variantes en sección, entidad, municipio y distritos federal/local: 80 ajustes RF nuevos.
- Predicciones seccionales agregadas con dos pesos históricos: LN y SV+NV de la elección previa.
- Además, entrenamiento directo de las ocho variantes por cada nivel territorial.
- 208 filas nuevas de métricas, sin pesos oráculo futuros.
- Comparación contra el RF previo seleccionado para cada nivel/enfoque, reutilizando sus métricas y predicciones.

Ranking principal: menor peor cociente de MAE nuevo / RF previo entre ambos años. También se muestra menor media de MAE y recuperación del Top20. Si ninguna variante mejora ambos años, se indica conservar el candidato previo; no se llama mejora al mejor de los nuevos por defecto.

## Archivos

- `RESULTADOS_RF_MEJORADO.txt`: metodología, configuraciones, métricas completas, referencias, rankings, verificaciones y bootstrap.
- `01_metricas_nuevas.csv`: todas las métricas nuevas.
- `02_comparacion_con_rf_previo.csv`: diferencias de MAE y Top20 frente al RF previo.
- `03_ranking_nuevos.csv`: ranking de dos años.
- `04_mejores_nuevos_por_enfoque.csv`: ganador nuevo por nivel/enfoque.
- `05_mejores_por_media.csv`: selección por media de MAE como criterio alternativo.
- `06_decisiones_vs_previo.csv`: mejorar o conservar el candidato previo.
- `07_bootstrap_vs_rf_previo.csv`: intervalos exploratorios pareados.
- `08_metricas_seleccionadas.csv`: métricas por año de candidatos nuevos seleccionados.
- `09_efectos_aislados.csv`: contrastes de logs, historia adicional, objetivo residual y parámetros.
- `10_importancias_entrenamiento.csv`: importancia por reducción de impureza en entrenamiento; no importancia causal ni validación independiente.
- `configuracion.json`, `registro_pruebas.json`, `variables_por_variante.csv`: trazabilidad.

## Ejecutar

```powershell
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/17_improve_random_forest.py --smoke
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/17_improve_random_forest.py
```

La verificación inicial comprueba logs, tasas, disponibilidad de columnas, coincidencia de cohortes y que modificar resultados futuros no altere las nuevas variables históricas. Al finalizar se recalculan métricas de candidatos seleccionados desde predicciones guardadas.

Es exploración sobre los mismos dos backtests, sin holdout independiente para confirmar selección. Cobertura y limitaciones geográficas siguen siendo las de la ronda anterior: cohortes comparables con filtros de calidad, aproximadamente 64% de LN nacional 2021 y 60% de 2024; distritos retrospectivos. No se cambia la página ni el modelo productivo.

## Resumen y revisión final

Consultar RESUMEN_RESULTADOS.md, 11_bootstrap_logs_vs_rf_previo.csv y 12_VERIFICACION.txt. Para recalcular métricas y comprobar firmas sin entrenar: docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/17_improve_random_forest.py --review-only
