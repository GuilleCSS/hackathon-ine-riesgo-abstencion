# Revisión independiente: tuning, riesgo y escenarios

El revisor comprobó los artefactos en `modeling/outputs/` y el pipeline `risk_scenarios.py`.

## Hallazgos

- Validación temporal: cada test externo se mantiene aparte; la búsqueda interna solo usa objetivos anteriores a ese corte. 2015 no permite búsqueda; 2018 tiene un solo fold interno, por lo que su hiperparámetro es inestable. El MLP usa validación aleatoria interna solo para early stopping; no se considera evidencia de generalización temporal.
- MAE medio por año: persistencia misma familia **7.08 pp**, HGB **10.70 pp**, MLP **10.84 pp**, Ridge **11.18 pp**, persistencia reciente **12.34 pp**. Elegir el baseline para el score operativo es coherente con esta evidencia.
- Search final por los folds 2015/2018/2021/2024: Ridge `alpha=10000` (MAE medio interior 11.04 pp); HGB `max_iter=60`, `max_leaf_nodes=15`, `learning_rate=0.03`, `l2=10`, `min_samples_leaf=100` (10.21 pp). La elección del HGB no lo hace ganador contra la persistencia histórica.
- Los cortes P50/P80/P90 se calculan con el score base del mismo universo; categorías: BAJO hasta P50, MEDIO P50–P80, ALTO sobre P80, prioridad desde P90. Son rangos relativos, no probabilidades calibradas.
- Escenario base: 72,599 secciones, 14,520 ALTO y 7,262 prioritarias. Supuesto −2 pp en ALTO: baja mecánicamente la media 0.40 pp y hace que 2,973 secciones salgan de ALTO. Supuesto −5 pp en Top 10%: baja mecánicamente la media 0.50 pp y 3,935 zonas dejan la bandera prioritaria.
- No se observa una fuga temporal directa. Features demográficos son agregados; `Población ind/afro=Mostrar` solo constituye etiqueta proxy del dato, no prevalencia poblacional.
- No se encontró ningún bug en los escenarios; cortes congelados permiten reflejar descensos de nivel sin recalcular percentiles.

## Límites

Resultados por sección no implican inferencia individual; no se usan personas ni identificadores personales. Llave territorial `entidad + sección` aún provisional, sin crosswalk oficial. Predicción 2027 asume elección intermedia y no tiene backtest. Los impactos de escenarios son supuestos, no efectos causales. Sin geometría/adyacencia no es viable ST-GCN.

## Actualización de clasificación de horizonte

Durante la verificación se encontró y corrigió una asignación implícita: 2027 quedaba como presidencial por estar fuera del catálogo de años, pese a la hipótesis escrita de intermedia. `create_future_examples` ahora recibe explícitamente `target_family="intermediate"`, por lo que el historial comparable es 2021 y el reciente 2024. Se volvieron a ajustar los modelos y a generar los escenarios. Valores vigentes: media base 46.20%, cortes P50/P80/P90 de 46.55/57.10/62.63%; 14,520 ALTO y 7,262 prioritarias. Reducción supuesta de 2 pp en ALTO: 11,547 continúan ALTO; reducción de 5 pp en Top10: 3,935 salen de prioritario.
