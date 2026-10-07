# Random Forest M17 en el tablero

Se añade un selector de modelo a `dashboard/app.py`. La opción predeterminada conserva el tablero anterior. La nueva opción carga `dashboard/rf_dashboard.py` y utiliza archivos independientes en `data/processed/rf_dashboard`; no sustituye los pronósticos, escenarios ni umbrales del modelo lineal.

El ganador municipal fue M17: regresión Random Forest de 64 árboles, profundidad máxima 12, hojas mínimas de 25 registros seccionales, `max_features=sqrt`, `max_samples=0.8`, semilla 42. Usa 143 variables históricas y demográficas, incluyendo logaritmos y resúmenes acumulados. Las tasas se agregan por lista nominal de la elección anterior. MAE municipal: 7.7294 pp en 2021 y 4.4684 pp en 2024; media 6.0989 pp. No se presenta como ganador demostrado estatal o distrital. `metricas_multinivel.csv` evalúa esos niveles reutilizando las predicciones fuera de muestra guardadas, sin repetir entrenamientos.

La única refitación nueva es la del modelo final 2027, con objetivos 2015, 2018, 2021 y 2024. Sus predictores provienen de 2021 y 2024. La selección futura exige disponibilidad en ambos años, municipio y tipo de sección estables, estado de votación conocido suficiente (NS/LN ≤10%) y claves territoriales completas; no exige resultados futuros. El modelo se guarda en Joblib y se reutiliza por firma de datos, características y configuración. No se entrena al navegar.

## Interpretación

- Año: 2027 es pronóstico; 2021/2024 son pruebas históricas. Nivel: entidad, municipio, distrito federal o local.
- Objetivo: NV/(SV+NV). La participación es su complemento entre personas con estado de votación conocido. NS permanece separado.
- Lista nominal y denominador conocidos son históricos de las secciones modeladas: 2024 para el pronóstico 2027, 2018 para la prueba 2021 y 2021 para la prueba 2024. No se pronostica la lista nominal.
- Los conteos hipotéticos son `PRED × D_BASE` y `(1-PRED) × D_BASE`; mantienen constante ese denominador histórico. No son conteos observados futuros. Las pruebas históricas muestran también resultados observados de su cohorte.
- Estos conteos son orientativos al nivel seleccionado: las tasas se ponderan por LN, mientras que los conteos se obtienen aplicándolas a D_BASE. Si D/LN varía entre territorios, sumar conteos municipales no reproduce exactamente el conteo estatal. Se conserva SV+NV=D_BASE dentro de cada territorio y la masa LN entre niveles. No se evaluó un modelo de conteos.
- No hay resultados por partido/candidatura en la base; no se inventan.
- El semáforo usa percentiles 50 y 80 del pronóstico 2027 por nivel, congelados entre filtros, años y escenarios. Es relativo dentro de cada nivel; no comparar categorías como umbrales absolutos idénticos entre niveles.
- Escenarios: base, reducción hipotética de 2 o 5 pp en territorios clasificados altos en la base. El filtro de riesgo se aplica después del escenario. No son estimaciones causales.
- Polígonos reconstruidos a partir de la capa seccional disponible MGS DIC-2025 y asignación territorial del año fuente. Esa capa ya tiene cobertura parcial; no constituye cartografía completa ni límites históricos certificados. Las divisiones 2027 usan asignación 2024 y requieren validación con cartografía oficial 2026–2027.
- La cobertura electoral divide LN modelada por toda la LN del territorio fuente; la cobertura cartográfica divide LN modelada con geometría por LN modelada. El mapa, aun con un polígono visible, no demuestra cobertura territorial completa.

## Reproducir

```text
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/19_publish_rf_dashboard.py
docker exec -w /app hackathon-ine-riesgo-abstencion-app-1 python src/19_publish_rf_dashboard.py --verify-ui
```

Archivos: `model_m17_2027.joblib`, manifiesto de modelo, tasas seccionales 2027, `territories.parquet/.csv`, doce GeoJSON por año/nivel y metadatos. El tablero descarga la selección en CSV y el mapa en GeoJSON; ambos se vinculan mediante `ID`. Los informes registran métricas, cobertura y verificación. El bootstrap municipal de la selección previa incluye cero: la mejora sigue siendo exploratoria y necesita un nuevo ciclo electoral de evaluación.
