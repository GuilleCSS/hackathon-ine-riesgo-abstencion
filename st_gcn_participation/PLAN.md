# Plan de accion

Objetivo: preparar un diagnostico estadistico antes de decidir si conviene una ST-GCN para riesgo de abstencion/participacion.

## Agentes delegados

- `agents/data_inventory.md`: inventario de datos, columnas, granularidad y problemas base.
- `agents/eda_stats.md`: metricas y graficos prioritarios para mineria inicial.
- `agents/stgcn_feasibility.md`: requisitos faltantes para ST-GCN.
- `agents/model_evaluator.md`: protocolo para comparar ST-GCN contra alternativas.

## Ejecucion actual

1. Crear carpeta exclusiva `st_gcn_participation`.
2. Leer CSV fuente desde `../Data` sin copiarlos ni modificarlos.
3. Procesar por chunks para no cargar ~55M filas completas en memoria.
4. Generar agregados CSV en `outputs/`.
5. Generar reporte HTML autocontenido en `outputs/participation_eda_report.html`.

## Siguiente fase

Construir panel seccion-anio y decidir si se consigue una matriz de adyacencia espacial. Sin esa matriz, ST-GCN queda como opcion especulativa.

## Resultados de modelado

- Se construyo `outputs/section_year_panel.csv` con 406,866 filas seccion-anio.
- Backtesting temporal con Ridge, HistGradientBoosting y MLP; evaluacion independiente en `agents/evaluator/final_review.md`.
- Resultados y escenario exploratorio 2027 en `modeling/REPORT.md` y `modeling/outputs/`.
- El modelo neuronal y los dos modelos clasicos no superaron consistentemente la persistencia por misma familia. No declarar un modelo ganador.
- Pipeline ajustado y semáforo territorial en `modeling/risk_scenarios.py`; reporte en `modeling/RISK_REPORT.md`.
- Escenarios ilustrativos con reducciones supuestas, nunca efectos causales; datos personales no se usan.
- El semáforo conserva persistencia por misma familia porque Ridge/HGB no ganaron en MAE medio temporal; se guardan modelos entrenados como challengers.
- Rama local `Oscar`; modelos serializados bajo `modeling/models/`. Los CSV sección-año grandes se reproducen localmente y están excluidos de Git.
- En horizonte 2027 se define explícitamente familia intermedia (historial comparable 2021 + reciente 2024); los escenarios se regeneraron con esa definición.
