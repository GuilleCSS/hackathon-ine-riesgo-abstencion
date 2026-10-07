# Experimento multinivel separado de producción

Este experimento compara Random Forest y HistGradientBoosting con siete bloques de variables históricas, dos elecciones de evaluación y dos enfoques territoriales. También conserva persistencia y la arquitectura lineal de dos historias como referencias.

## Ejecutar

Desde la raíz, con las dependencias del proyecto:

```powershell
python src/16_experiment_multilevel.py --smoke
python src/16_experiment_multilevel.py
```

En el contenedor actual:

```powershell
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/16_experiment_multilevel.py
```

Después de una ejecución completa, `--report-only` regenera las comparaciones desde las métricas y predicciones guardadas, sin entrenar otra vez.
`--verify-results` recalcula las métricas de los candidatos seleccionados y, cuando están disponibles las predicciones del pipeline previo, añade el bootstrap seccional frente a su referencia lineal.

## Diseño

| Prueba | Objetivos de entrenamiento | Objetivo de evaluación | Inputs de evaluación |
|---|---|---|---|
| 2021 | 2015 y 2018 | 2021 | 2015 y 2018 |
| 2024 | 2015, 2018 y 2021 | 2024 | 2018 y 2021 |

Cada ejemplo de entrenamiento también usa exclusivamente sus dos elecciones anteriores. Cada fold reajusta sus propios modelos e imputadores. No se usan los coeficientes reajustados para 2027.

Los enfoques son:

1. Entrenar por sección y agregar las tasas predichas por entidad, municipio y distrito federal/local. Peso principal: LN de la elección previa; sensibilidad: SV+NV de la elección previa.
2. Sumar los conteos de las mismas secciones, recalcular características territoriales y entrenar por entidad, municipio y distrito federal/local.

Los siete bloques, acumulativos o alternativos, son:

- B0: dos historias + entidad y familia electoral.
- B1: B0 + composición por edad/sexo, tipo urbano/rural, tamaño LN y edad media.
- B2: B1 + abstención histórica por grupos, brechas de participación y diferencia de edad votante/electorado.
- B3: B1 + historia anterior de la misma familia, tendencias y cambios entre historias.
- B4: B1 + contexto municipal/estatal/nacional, pesos electorales y calidad NS.
- B5: historia + demografía + comportamiento por grupos + tendencias + contexto.
- B6: B5 + abstención esperada por composición etaria y exceso frente a referencias municipal/estatal.

Los hiperparámetros se fijan por algoritmo y nivel y se registran en JSON/TXT. Son 140 entrenamientos de árboles y 10 ajustes lineales; persistencia no se entrena. Hay 544 filas de métricas incluyendo referencias y ponderaciones diagnósticas.

Se conserva un piloto parcial en `PILOTO_RECURSOS_*`, con RF de 100 árboles, profundidad 14 y fracción de variables 0.65. Se interrumpió por costo de cómputo. La comparación completa utiliza 64 árboles, profundidad 12 y `max_features=sqrt` uniformemente; el piloto no se mezcla con los rankings finales.

## Archivos

- `RESULTADOS_EXPERIMENTO_MULTINIVEL.txt`: documentación, todas las pruebas, métricas, rankings, configuración y cobertura.
- `configuracion.json`: versiones, semillas, parámetros, columnas y hashes de datos/script.
- `variables_por_bloque.csv`: manifiesto de variables.
- `00_cobertura.csv`: universo por año y nivel.
- `01_metricas_todas.csv`: MAE, RMSE, R², sesgo, errores ponderados, correlación de rangos, recuperación Top10/Top20, tiempo y diagnóstico sobre universo ampliado.
- `02_mejores_por_ano_enfoque.csv`: mínimo MAE por año y enfoque; resultado descriptivo, no selección independiente.
- `03_ranking_dos_anos.csv`: media de errores y peor razón frente al lineal directo del nivel.
- `04_comparacion_enfoques.csv`: candidato de cada enfoque que minimiza esa peor razón en los dos años, incluyendo referencias.
- `05_mejores_por_modelo.csv`: mejor bloque para cada algoritmo y enfoque con el mismo criterio.
- `06_bootstrap_pareado.csv`: diferencias directo–agregado y bootstrap por entidad.
- `07_predicciones_candidatos_seleccionados.csv.gz`: predicciones de los candidatos de cada enfoque.
- `08_efecto_bloques_variables.csv`: diferencia de cada bloque frente a B0, manteniendo año, algoritmo, nivel, enfoque y pesos.
- `09_sensibilidad_ponderacion.csv`: efecto de ponderación histórica y del peso oráculo futuro.
- `10_VERIFICACION.txt`: resultado de comprobaciones independientes de los artefactos.
- `11_bootstrap_seccion_vs_lineal.csv`: contraste seccional por municipio y por entidad.
- `RESUMEN_RESULTADOS.md`: interpretación de resultados, tablas y límites prácticos.

## Interpretación y límites

MAE/RMSE/sesgo están en puntos porcentuales. MAE territorial asigna el mismo peso a cada territorio. WMAE pondera la evaluación por el denominador objetivo SV+NV; no utiliza ese denominador para entrenar ni generar la predicción operativa.

Los resultados principales se refieren a la cohorte comparable y evaluable, con NS <=10% en las tres observaciones y municipio/tipo estables. La cohorte representa aproximadamente 64.36% de LN nacional 2021 y 60.30% de LN nacional 2024. No debe presentarse como cobertura nacional completa. Los dos enfoques comparten exactamente las secciones y targets de evaluación.

`full_reference_mae_pp` compara también contra todas las secciones objetivo mapeables al marco de la elección previa, incluso las excluidas por calidad. Es sensibilidad al cambio de universo, no un segundo modelo entrenado para el universo completo.

Los distritos quedan congelados a los códigos de la elección fuente más reciente, no a la asignación del año objetivo. Los diccionarios antiguos refieren un marco DERFE2021 y el de 2024 DERFE2023; el análisis geográfico es retrospectivo y no certifica disponibilidad histórica de ese marco ni predice los distritos 2027.

El agregado con `TARGET_D` es un ORÁCULO diagnóstico. No participa en selección porque su peso solo se conoce después de la elección.

El ranking usa ambos backtests para comparar muchos candidatos. No queda un holdout independiente para confirmar el ganador; los intervalos bootstrap son exploratorios y no corrigen selección múltiple. Solo existen pocos ciclos temporales y 32 entidades por año.

Las comprobaciones automáticas verifican fórmulas de tasas, columnas disponibles, suma ponderada exacta con peso oráculo, y que alterar SV/NV y los distritos del objetivo no cambia los predictores. La pertenencia a la cohorte evaluable sí está condicionada a disponibilidad y calidad del target y se documenta expresamente.

No se modifica el dashboard, la arquitectura bloqueada, el forecast 2027 ni sus escenarios. Los cruces RAW sexo×edad, cuantiles de edad, variables espaciales y fuentes externas quedan fuera de esta primera comparación.
