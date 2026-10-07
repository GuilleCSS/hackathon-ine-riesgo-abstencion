# Nuevas pruebas del Random Forest

Se completaron 80 ajustes nuevos: ocho variantes, dos evaluaciones temporales (2021 y 2024) y cinco unidades de entrenamiento (sección, entidad, municipio y distritos federal/local). Se evaluaron ambos enfoques: agregar predicciones seccionales con pesos electorales históricos y entrenar directamente por territorio. Hay 208 filas de métricas. No se reentrenó ninguna configuración de la ronda anterior. La página y el modelo productivo no se modificaron.

## Qué se probó

Todas las variantes conservan `log1p(lista nominal)` de los dos antecedentes, que ya estaba en el modelo previo. R01 añade 36 conteos logarítmicos por sexo, edad y condición de participación. Otras variantes añaden composición etaria, proporciones, contexto municipal/estatal excluyendo la sección propia, tasas suavizadas según soporte, percentiles territoriales e históricos ampliados. También se probaron un objetivo de cambio respecto al antecedente de la misma familia electoral y un bosque de 96 árboles con mayor profundidad.

La lista exacta de entradas por variante está en `variables_por_variante.csv`; parámetros, firmas y disponibilidad temporal están documentados en el TXT y en `configuracion.json`.

## Comparación seccional

MAE expresado en puntos porcentuales de abstención; menor es mejor. La media da igual peso a los dos años.

| Variante | Variables | MAE 2021 | MAE 2024 | MAE medio |
|---|---:|---:|---:|---:|
| RF anterior B5 | 79 | 6.935 | 4.155 | 5.545 |
| R01: logs de conteos por grupo | 115 | 6.468 | 4.153 | **5.310** |
| R02: pares territoriales y soporte | 151 | 7.553 | 4.159 | 5.856 |
| R03: combinación compacta con logs | 93 | 8.216 | 4.884 | 6.550 |
| R04: combinación ampliada | 203 | 7.580 | 4.171 | 5.875 |
| R05: combinación e historia larga | 231 | 6.664 | **4.149** | 5.407 |
| R06: cambio, combinación compacta | 93 | 7.953 | 4.593 | 6.273 |
| R07: más árboles y profundidad | 203 | 7.404 | 4.154 | 5.779 |
| R08: cambio e historia larga | 231 | 7.574 | 4.388 | 5.981 |

R01 reduce el MAE medio un 4.23% frente al RF anterior. Sus RMSE son 8.401/5.596 y sus R² son 0.547/0.710 para 2021/2024. Su recuperación del 20% de secciones con mayor abstención es 60.52%/71.16%, frente a 58.15%/71.00% del anterior.

R05 reduce el MAE medio un 2.49%; obtiene RMSE 8.615/5.562 y R² 0.524/0.713. Es el ganador del criterio principal de menor peor cociente de MAE frente al RF previo entre ambos años. R01 gana por menor MAE medio. La pequeña ventaja de R05 en 2024 explica esta diferencia entre criterios; no hay un ganador universal.

## Resultados territoriales

La siguiente tabla usa el criterio alternativo de menor MAE medio entre los dos años. R01 es la mejor nueva combinación agregada en los cuatro niveles. Los pesos se eligen entre lista nominal histórica y SV+NV históricos; no se utilizan pesos observados del año objetivo.

| Nivel, agregación seccional | MAE medio del RF anterior seleccionado | MAE medio nuevo R01 |
|---|---:|---:|
| Entidad | 3.836 | 3.650 |
| Municipio | 6.434 | 6.200 |
| Distrito federal | 4.075 | 3.812 |
| Distrito local | 4.439 | 4.163 |

Con el criterio principal de menor peor cociente, se selecciona R05 agregado para entidad y ambos distritos, y R01 agregado para municipio. Los detalles de ambos criterios están separados en los CSV 04 y 05. R05 agregado a entidad todavía tiene R² negativo en 2021; un menor MAE frente al RF previo no garantiza superar todos los referentes.

Entrenar directamente por municipio mejora ambos años con R05 (MAE 8.525/4.846), pero sigue teniendo más error que la agregación seccional. En entrenamiento directo de entidad y distritos ninguna variante nueva mejora al candidato anterior en ambos años; se indica conservar el anterior en esas comparaciones.

## Verificación y límites

Se verificaron 80 firmas únicas, sin coincidencias con pruebas anteriores, y se recalcularon las métricas desde las 80 predicciones directas guardadas. Las comprobaciones de disponibilidad histórica y de ausencia de resultados futuros en las variables pasaron. La revisión final no realizó entrenamientos.

Para R01 frente al RF B5, el cambio de MAE de 2021 es -0.467 puntos; el intervalo bootstrap por entidades es [-0.728, -0.190]. En 2024 es -0.002 puntos, con intervalo [-0.102, 0.104]: prácticamente un empate. Los intervalos son exploratorios y no corrigen la selección entre múltiples variantes.

Se reutilizaron los mismos dos backtests para comparar y seleccionar variantes; falta validación temporal independiente. Las cohortes comparables cubren aproximadamente 64% de la lista nominal nacional de 2021 y 60% de 2024, por los filtros de calidad y estabilidad territorial. Los distritos corresponden a marcos retrospectivos; estos resultados no equivalen a una validación de distritos futuros. La abstención objetivo es NV/(SV+NV); NS se mantiene separado según la definición del proyecto.

Recomendación: mantener R01 como candidato práctico para la siguiente validación, por su menor error promedio y menor número de variables que R05. Conservar R05 como alternativa para estudiar historia larga. Añadir todas las variables, aumentar profundidad o predecir cambios no mejoró el error medio seccional frente a R01. Estos resultados justifican experimentar, pero todavía no demuestran una mejora en una elección futura.
