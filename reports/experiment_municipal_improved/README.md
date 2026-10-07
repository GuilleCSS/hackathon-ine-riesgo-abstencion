# Experimento aislado de mejora municipal

Entrena Random Forest, Extra Trees y HistGradientBoosting con las mejores variables anteriores y combinaciones orientadas al municipio. No modifica la página ni el pronóstico productivo.

Hay 16 configuraciones evaluadas en 2021/2024 por dos enfoques: entrenamiento seccional y agregación municipal, o entrenamiento municipal directo. Son 60 entrenamientos únicos; cuatro configuraciones de pesos coinciden al entrenar directamente y reutilizan predicciones.

La extensión añade diez configuraciones: historia larga sin los demás bloques nuevos, contexto municipal básico con soporte observado, quitar el código de entidad, dos boosting con historia, tres regresiones Ridge, aumentar sólo árboles y regularizar más el RF. El plan completo contiene 100 ajustes únicos posibles. En esta ejecución se descartaron tres ajustes seccionales de 2024 tras errores más de 25% superiores al RF anterior en 2021; los modelos directos y las variantes representativas de boosting permanecen. El plan efectivo tiene 97 ajustes únicos, además del piloto retenido. `PODAS_BUSQUEDA.csv` registra los descartes. Los resultados con un solo año se excluyen del ranking de dos años.

Antes de esta ronda se completó un piloto RF con `max_features=0.7`: tardó 393 segundos y empeoró el MAE municipal de 2021 a 9.298 puntos. Se conserva separado en los archivos `PILOTO_*` y en su checkpoint; no se repite ni entra al ranking de dos años. Se interrumpió el siguiente ajuste costoso antes de completarlo. La ronda principal RF usa `max_features=sqrt`; los demás parámetros y las combinaciones se mantienen documentados.

Los resúmenes municipales nuevos usan todos los registros del año fuente: cuantiles y dispersión de abstención entre secciones, concentración y tamaño de lista nominal, composición urbana/rural y cambios históricos. Se comprueba que alterar resultados futuros no modifica esas entradas.

La ponderación de entrenamiento seccional distribuye igual masa a cada municipio-año según su lista nominal previa. El entrenamiento directo trata a cada municipio por igual. Se prueban pérdidas cuadrática y absoluta, objetivos tasa y cambio respecto al antecedente de la misma familia, y árboles más regularizados.

La métrica principal es MAE municipal no ponderado, en puntos porcentuales, promediado entre ambos años. Se reportan RMSE, R², sesgo, MAE ponderado por tamaño electoral y recuperación del Top20. La comparación utiliza exactamente las cohortes de la ronda anterior.

Las mezclas con el RF R01 anterior usan pesos fijos 25%, 50% y 75% para el candidato nuevo; no ajustan pesos usando resultados observados. Su selección, al igual que la de configuraciones, es exploratoria sobre los mismos backtests. El bootstrap agrupado por entidad no corrige esa selección múltiple. Falta validación temporal independiente antes de promover un modelo.

La revisión adicional compara también seis híbridos de los dos nuevos RF con historia M17: 25%, 50% o 75% del modelo municipal directo y el resto de las secciones agregadas, con pesos electorales LN/D históricos. Reutiliza predicciones; no entrena modelos ni ajusta coeficientes.

El descriptor inicial `M_WEIGHTED_A` es sum(LN × tasa observada)/LN total: refleja tanto cobertura como participación; las secciones sin tasa observable no aportan al numerador. M18 añade una tasa ponderada condicional sobre secciones con información, la proporción de LN en esas secciones, la proporción de electores con estado conocido (SV+NV)/LN y sus cambios históricos. Los resultados evaluados siguen usando NV/(SV+NV).

## Archivos

- `plan_pruebas.json`, `variables_por_variante.csv`: configuraciones y variables exactas.
- `registro_pruebas.json`, `configuracion.json`: firmas de pruebas, parámetros y comprobaciones.
- `00_referencias_previas.csv`: resultados municipales anteriores reutilizados.
- `01_metricas_modelos.csv`: modelos individuales y referencias con predicciones disponibles.
- `02_metricas_con_mezclas.csv`, `03_ranking.csv`: evaluación completa y ranking.
- `04_mejores_por_enfoque.csv`, `05_metricas_seleccionadas.csv`: candidatos por enfoque.
- `06_bootstrap.csv`: intervalos exploratorios de diferencias de MAE frente al R01 agregado anterior.
- `07_diagnostico_por_tamano_composicion_entidad.csv`, `08_municipios_mejorados.csv`: errores por tamaño, composición y entidad del ganador final.
- `09_bootstrap_ganador_global.csv`, `10_ranking_estabilidad.csv`: comparación del ganador global y criterio de estabilidad.
- `11_resultados_parciales_excluidos_ranking.csv`, `12_VERIFICACION.txt`: resultados parciales y revisión independiente de firmas/predicciones.
- `13_metricas_hibridos_historia.csv`: híbridos de los dos nuevos modelos con historia, sin ajustes adicionales.
- `RESULTADOS_MUNICIPALES.txt`: metodología, configuraciones, métricas y verificaciones completas.

Las predicciones se guardan en `data/processed/experiment_municipal_improved/`. Si se vuelve a ejecutar el script, las firmas completas reutilizan predicciones, sin volver a entrenar.

```powershell
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/18_improve_municipal.py --smoke
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/18_improve_municipal.py
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/18_improve_municipal.py --extend --focus
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/18_improve_municipal.py --review-only
```

El objetivo es NV/(SV+NV); NS se conserva separado. La cobertura es parcial por los filtros históricos heredados, aproximadamente 64% de la lista nominal nacional de 2021 y 60% de 2024. Las cohortes usan estabilidad territorial y calidad observadas retrospectivamente. Los resultados no representan todavía una evaluación sobre todos los electores ni una confirmación del error de una elección futura.
