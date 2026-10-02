# Dashboard interactivo

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
pip install streamlit pydeck geopandas pyogrio
```

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
