# Dashboard interactivo

La navegación conserva las páginas existentes y añade
**Random Forest M17**. Esta página permite elegir 2027
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

La aplicación tiene dos páginas (`app.py` es el punto de entrada y la
navegación):

- **Mapa de riesgo 2027** (`mapa.py`): estimación territorial, semáforo,
  incertidumbre, persistencia, escenarios hipotéticos, capa gris de secciones
  sin estimación y capa violeta de secciones con NS alto.
- **Datos por año** (`datos_anuales.py`): abstención y NS 2009–2024, mapa por
  año de cada sección (abstención, NS o cambio contra la elección anterior del
  mismo tipo), secciones por rango de NS y cambios de secciones entre
  elecciones. Filtros: entidad y tipo de elección (todas, intermedias o
  presidenciales).

`comun.py` reúne la cartografía base y las piezas de mapa que usan ambas
páginas, para cargarlas una sola vez.

### Optimización del mapa

Para evitar enviar cientos de MB al navegador:

- **Vista nacional híbrida** (por defecto): secciones de más de 100 km² como
  polígono simplificado a 500 m y coordenadas a 4 decimales; las demás como
  punto representativo. La opción **Puntos** dibuja un punto por sección.
- **Entidad seleccionada:** se muestran polígonos seccionales.
- Los datos enviados a PyDeck se reducen a las columnas necesarias para el mapa.
- `CompactDeck` (`comun.py`) envía el JSON del mapa sin la indentación que
  agrega pydeck, lo que reduce el envío a la mitad (nacional: ~35 MB en vez de
  ~70 MB).

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

Opcionales en el mapa (si faltan, esas capas se omiten):

```text
data/processed/spatial_2027/cartography_base_2027.parquet       # capa gris y cobertura
data/processed/forecast_2027/forecast_2027_all_comparable.parquet  # capa violeta (NS alto)
```

Página Datos por año:

```text
data/processed/section_election_master_v1.csv.gz
data/processed/spatial_2027/cartography_base_2027.parquet       # mapa por año
```

El mapa por año dibuja cada elección sobre la cartografía DIC-2025: las
secciones que ya no existen con la misma clave no aparecen (en 2024 se dibujan
70,301 de 70,751; en 2009, 62,623 de 64,934).

## Nota

La cartografía utilizada en esta versión es MGS DIC-2025 y se considera
provisional. Debe sustituirse por el Marco Geográfico Electoral 2026–2027
oficial antes de la entrega final.
