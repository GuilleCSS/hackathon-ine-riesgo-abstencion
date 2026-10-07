# Mejora municipal: resultados finales

El mejor candidato por MAE medio de 2021/2024 es **M17: Random Forest con conteos logarítmicos e historia larga**, prediciendo por sección y agregando por lista nominal histórica. El modelo municipal directo con esas mismas variables también mejora frente al candidato directo anterior. La página y el pronóstico productivo no se modificaron.

## Comparación principal

MAE en puntos porcentuales de abstención; menor es mejor. La media da igual peso a ambos años y, dentro de cada año, a cada municipio. Son 2,339 municipios en 2021 y 2,343 en 2024, con exactamente las mismas cohortes de referencia.

| Enfoque y candidato | MAE 2021 | MAE 2024 | MAE medio |
|---|---:|---:|---:|
| Agregado anterior: RF R01, peso LN | 7.905 | 4.495 | 6.200 |
| **Agregado nuevo: RF M17, peso LN** | **7.729** | **4.468** | **6.099** |
| Directo anterior: RF R05 | 8.525 | 4.846 | 6.685 |
| **Directo nuevo: RF M17** | **7.866** | **4.700** | **6.283** |

La mejora media es **1.64% en agregación** y **6.01% en entrenamiento municipal directo**, frente al candidato anterior de cada enfoque. Se comparan modelos fijos en ambos años; no se escoge un modelo distinto retrospectivamente para cada elección.

| Métrica del nuevo M17 | Agregado 2021 | Agregado 2024 | Directo 2021 | Directo 2024 |
|---|---:|---:|---:|---:|
| RMSE, puntos porcentuales | 9.810 | 6.139 | 9.962 | 6.489 |
| R² | 0.530 | 0.704 | 0.515 | 0.669 |
| Recuperación del Top20 de riesgo | 57.26% | 69.94% | 54.06% | 68.02% |

El Top20 agregado anterior fue 53.21%/71.00%: mejora la identificación de riesgo en 2021, pero disminuye aproximadamente 1.07 puntos porcentuales en 2024. La selección principal optimiza error de tasa, no exclusivamente clasificación de los municipios de mayor riesgo.

## Qué cambió en el candidato ganador

Conserva las 115 variables del RF R01 anterior, incluidos log1p de lista nominal y conteos por sexo/edad. Añade 28 descriptores históricos: número de observaciones, media, desviación, mínimo, máximo y último cambio, tanto para todas las elecciones como para la misma familia electoral; también cambios de log de lista nominal y edad. Se calculan hasta cada año fuente, inclusive.

Total: **143 variables de entrada**, antes de codificar categorías y añadir indicadores de imputación. Se mantuvieron los parámetros del RF previo: 64 árboles, profundidad máxima 12, max_features=sqrt, max_samples=0.8 y semilla 42. Hoja mínima de 25 observaciones en sección y 8 en municipio. Esto permite contrastar el efecto de la historia adicional conservando la configuración del bosque.

Para evaluar 2021 se entrenó con objetivos 2015/2018; para 2024 con 2015/2018/2021. El objetivo es NV/(SV+NV), con NS separado. Las predicciones seccionales se agregan con LN o D=SV+NV del antecedente reciente; no se usan pesos del año objetivo.

## Otras pruebas y combinaciones

Se exploraron 26 configuraciones de Random Forest, HistGradientBoosting, Extra Trees y Ridge por ambos niveles de entrenamiento. Se completaron **97 ajustes únicos del plan y un piloto adicional**. Tres ajustes seccionales de boosting de 2024 se descartaron tras errores más de 25% superiores al RF anterior en 2021; sus resultados de 2021 quedan documentados y excluidos del ranking de dos años. Los modelos directos y las variantes representativas de pérdidas/objetivos se completaron.

Se probaron composición/dispersión municipal, cuantiles de abstención, concentración de lista nominal, cobertura observada, pesos que equilibran municipios en entrenamiento, pérdidas absoluta/cuadrática, objetivos tasa/cambio, quitar el código de entidad, más árboles, mayor regularización y regresión Ridge. Las firmas y predicciones anteriores se reutilizaron; no se reentrenaron configuraciones completas ya realizadas. Cuatro equivalencias entre variantes directas comparten resultados.

Las mejores variantes nuevas de boosting, Extra Trees y Ridge no superaron al M17 agregado en MAE medio. Añadir todo el contexto municipal o aumentar sólo árboles tampoco fue mejor.

Se evaluaron mezclas con el RF anterior y seis híbridos entre los dos nuevos M17, con pesos fijos 25%/50%/75%, sin entrenar ni ajustar coeficientes. El mejor híbrido nuevo obtiene MAE medio 6.120, frente a 6.099 del M17 agregado. Una mezcla de 75% M17 agregado y 25% R01 agregado obtiene 6.104 y mayor estabilidad relativa entre años (peor cociente frente al anterior 0.9909, frente a 0.9940 del M17 puro). Son criterios diferentes; M17 puro gana por menor media.

Hay **624 filas finales de métricas**, incluidas referencias, mezclas y resultados parciales; no equivalen a 624 entrenamientos independientes. Todos los ajustes, parámetros, variables y métricas se detallan en `RESULTADOS_MUNICIPALES.txt` y los CSV asociados.

## Calidad de datos y verificaciones

Se detectaron secciones con LN positiva y D=0: 1,004/82/2,042/2,517/1,693/2,100 para 2009/2012/2015/2018/2021/2024. El descriptor inicial M_WEIGHTED_A refleja aporte observado sobre LN total y combina participación con cobertura. M18 separa tasa ponderada sobre secciones con información, cobertura de esas secciones, electores con estado conocido (SV+NV)/LN y cambios históricos; esa variante tampoco fue la ganadora.

Pasaron las comprobaciones de disponibilidad histórica: alterar resultados futuros no cambia las nuevas variables anteriores. Se revisaron independientemente las 98 firmas completas, las claves geográficas, la verdad observada, denominadores y límites de todas las predicciones nativas. Las métricas municipales se recalcularon desde archivos guardados; los híbridos se revisaron sin entrenamientos.

## Límites y recomendación

Para M17 agregado frente a R01, el cambio de MAE es -0.176 puntos en 2021, con intervalo bootstrap por entidades [-0.669, 0.176]; en 2024 es -0.027, con intervalo [-0.183, 0.140]. Ambos incluyen cero. La mejora medida es pequeña y todavía no tiene confirmación estadística independiente. El bootstrap está condicionado al candidato seleccionado y no corrige la exploración de múltiples configuraciones.

La mejora tampoco es uniforme: el cuartil de municipios pequeños empeora 0.178 puntos en 2021 y mejora 0.108 en 2024. En el cuartil grande mejora 0.343 en 2021 y empeora 0.078 en 2024. Los detalles por tamaño, composición y entidad están en `07_diagnostico_por_tamano_composicion_entidad.csv`. Mejoran individualmente 1,288 de 2,339 municipios en 2021 y 1,184 de 2,343 en 2024.

La evaluación usa las mismas dos elecciones para explorar y seleccionar; falta validación temporal independiente. La cobertura nacional es parcial por los filtros retrospectivos de calidad/estabilidad (aproximadamente 64% de LN en 2021 y 60% en 2024). La referencia más amplia mantiene el marco territorial del antecedente y no incorpora nuevas secciones sin correspondencia. Estas métricas no representan todavía todo el universo electoral ni garantizan el error de una elección futura.

**Recomendación:** conservar M17 agregado por LN histórica como mejor candidato experimental de tasa municipal. M17 directo es la alternativa más útil para el enfoque de históricos municipales, con mejora del 6.01% frente a su referente directo. Antes de incorporarlo a la página, validar estabilidad temporal y el objetivo de priorización de riesgo, especialmente el Top20 de 2024. No se hizo ningún cambio de producción.
