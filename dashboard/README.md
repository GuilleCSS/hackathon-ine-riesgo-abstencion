# Dashboard interactivo

El selector **Modelo predictivo** conserva la opción actual y añade
**Random Forest M17 · multinivel**. Esta opción permite elegir 2027
(pronóstico), 2021/2024 (pruebas históricas), nivel estatal, municipal o
distrital, entidad, territorio, semáforo y escenario. Haz clic en un polígono
o selecciona un territorio para consultar sus tasas, conteos y cobertura.

Los artefactos nuevos se generan con `python src/19_publish_rf_dashboard.py`.
La metodología y reproducción están en
`reports/rf_dashboard/IMPLEMENTACION.md`.

### Exploración rápida del Random Forest

- La vista nacional estatal usa polígonos simplificados; los niveles municipal
  y distrital usan puntos. Selecciona una entidad o un territorio para cargar
  sus polígonos detallados y consultar la ficha junto al mapa.
- La entidad se conserva al cambiar año o nivel. El buscador permite escribir
  el nombre del territorio. Las métricas y la cobertura permanecen visibles.
- Los límites detallados se guardan por entidad en GeoParquet y se leen desde
  caché. Las predicciones y geometrías regionales no se modifican.
- El GeoJSON detallado se prepara al pulsar **Preparar mapa GeoJSON**; descargar
  un archivo no vuelve a ejecutar la página. Los datos CSV también están disponibles.
- Las vistas de modelos anteriores conservan su diseño y carga originales.

Preparar y verificar sin reentrenar:

```text
python src/19_publish_rf_dashboard.py --optimize-dashboard
python src/19_publish_rf_dashboard.py --verify-dashboard-performance
python src/19_publish_rf_dashboard.py --verify-ui
```

Con Docker, anteponer `docker exec -w /app hackathon-ine-riesgo-abstencion-app-1`.
Las mediciones están en `reports/rf_dashboard/RENDIMIENTO_MAPA.csv` y las
verificaciones en `VERIFICACION_RENDIMIENTO.txt` y `VERIFICACION_UI.txt`.

## Qué muestra

La aplicación integra la estimación territorial, el semáforo de riesgo,
la incertidumbre, la persistencia del riesgo y los escenarios hipotéticos.

### Optimización del mapa

Para evitar enviar cientos de MB al navegador:

- **Vista nacional:** se muestran puntos representativos de las secciones.
- **Entidad seleccionada:** se muestran polígonos seccionales.
- Los datos enviados a PyDeck se reducen a las columnas necesarias para el mapa.

Esto evita el error de Streamlit `MessageSizeError` que ocurría al intentar
enviar los 54 mil polígonos completos en una sola visualización.

## Ejecutar

Desde la raíz del proyecto:

```powershell
streamlit run dashboard\app.py
```

## Dependencias

```powershell
pip install -r requirements.txt
```

Con Docker, desde la raíz: `docker compose up` (http://localhost:8501).

## Archivos requeridos

```text
data/processed/spatial_2027/risk_2027_dashboard_simplified.geojson
data/processed/scenarios_2027/section_scenarios_2027.parquet
reports/scenarios_2027/scenario_config.json
reports/spatial_2027/spatial_layer_metadata.json
```

## Nota

La cartografía utilizada en esta versión es MGS DIC-2025 y se considera
provisional. Debe sustituirse por el Marco Geográfico Electoral 2026–2027
oficial antes de la entrega final.
