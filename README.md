# Sistema de riesgo territorial de abstención electoral
## Hackathon INE 2026 · Reto 2: Predicción y escenarios de riesgo de abstención

> **Estado actual:** pipeline reproducible completo hasta la construcción del
> dashboard interactivo provisional. La cartografía empleada para visualización
> es MGS DIC-2025 y deberá sustituirse por el Marco Geográfico Electoral
> 2026–2027 vigente antes de la entrega final.

## Objetivo

Construir una herramienta reproducible de priorización territorial que utilice
los Conteos Censales de Participación Ciudadana (CCPC) 2009–2024 para:

- analizar la evolución histórica de participación y abstención;
- identificar territorios con mayor riesgo relativo de abstención;
- validar modelos mediante backtesting temporal;
- generar una estimación territorial futura;
- cuantificar incertidumbre;
- construir un semáforo territorial;
- simular escenarios hipotéticos;
- visualizar resultados en un dashboard geográfico.

## Datos

Se utilizan los procesos:

```text
2009 · 2012 · 2015 · 2018 · 2021 · 2024
```

Auditoría inicial:

| Año | Registros originales | Secciones |
|---|---:|---:|
| 2009 | 8,706,843 | 64,934 |
| 2012 | 8,604,456 | 65,599 |
| 2015 | 9,106,059 | 68,362 |
| 2018 | 9,251,122 | 68,408 |
| 2021 | 9,430,502 | 68,812 |
| 2024 | 9,773,730 | 70,751 |
| **Total** | **54,872,712** | — |

La base maestra agregada contiene:

```text
406,866 observaciones sección × elección
95 variables
```

La definición utilizada es:

```text
Participación = SV / (SV + NV)
Abstención    = NV / (SV + NV)
```

`NS` se mantiene separado y se usa como indicador de calidad.

## Arquitectura seleccionada

Después de comparar baselines, Ridge, Random Forest,
HistGradientBoosting, modelos residuales y modelos de doble historia, la regla
formal de selección bloqueó:

```text
two_history_linear
```

El modelo utiliza dos memorias electorales:

```text
última elección de la misma familia
+
elección federal más reciente
→
siguiente elección
```

Backtests temporales principales:

### 2021

```text
MAE two_history_linear ≈ 7.69 pp
```

La combinación 50/50 de las dos historias produjo un MAE de aproximadamente
6.18 pp, pero la arquitectura general se seleccionó con una regla minimax
predefinida para evitar elegir retrospectivamente un modelo diferente por año.

### 2024

```text
two_history_linear:
MAE ≈ 4.36 pp
R² ≈ 0.672
Top20 ≈ 0.720
```

La mejora del MAE frente a la persistencia de misma familia permaneció
respaldada por bootstrap agrupado por municipio.

## Reajuste y estimación 2027 v1

Después de bloquear la arquitectura, se reajustó con toda la historia disponible.

Coeficientes obtenidos:

```text
intercept   = 0.048004
beta_same   = 0.677339
beta_recent = 0.179781
```

Universo primario:

```text
Secciones presentes 2021+2024: 67,976
Inputs válidos:                64,444
Primary clean10:               54,772
```

Promedio de la estimación dentro del universo filtrado:

```text
42.69%
```

Este valor **no debe interpretarse como pronóstico nacional oficial**; corresponde
al universo comparable `primary_clean10`.

## Incertidumbre

La calibración empírica fuera de muestra del backtest 2021 produjo:

```text
residual q05 ≈ -19.22 pp
residual q95 ≈ +12.90 pp
error absoluto q90 ≈ 16.11 pp
```

Por ello el producto se plantea principalmente como herramienta de
**priorización territorial relativa**, no como predicción exacta del porcentaje
de abstención de cada sección.

## Semáforo

La clasificación se define de forma relativa:

```text
BAJO  : percentil <= 50
MEDIO : percentil 50–80
ALTO  : percentil > 80
Top10 : percentil >= 90
```

Umbrales v1 derivados para el universo 2027:

```text
BAJO_MAX          ≈ 42.82%
MEDIO_MAX         ≈ 51.07%
PRIORITY_TOP10    ≈ 55.44%
```

Validación retrospectiva:

| Backtest | BAJO observado | MEDIO observado | ALTO observado |
|---|---:|---:|---:|
| 2021 | 39.34% | 48.45% | 56.00% |
| 2024 | 31.66% | 41.80% | 51.44% |

En ambos casos se conserva la monotonicidad:

```text
BAJO < MEDIO < ALTO
```

## Escenarios hipotéticos

Los escenarios son ejercicios de sensibilidad y **no efectos causales
estimados**.

```text
S0_BASELINE       Sin intervención
S1_TOP10_MINUS2   -2 pp en Top10
S2_HIGH_MINUS2    -2 pp en ALTO
S3_HIGH_MINUS5    -5 pp en ALTO
```

Ejemplos:

```text
S2_HIGH_MINUS2:
ALTO 10,955 → 8,122

S3_HIGH_MINUS5:
ALTO 10,955 → 4,886
```

Los umbrales del semáforo permanecen congelados entre escenarios.

## Persistencia del riesgo

De las 10,955 secciones ALTO del universo primario:

```text
ALTO_SENSIBLE_2PP          2,833
ALTO_SENSIBLE_5PP          3,236
ALTO_PERSISTENTE_MAS_5PP   4,886
```

La tipología describe distancia matemática al umbral; no efectividad de una
intervención real.

## Cartografía provisional

Para validar el componente espacial se utilizó:

```text
MGS por entidad federativa
Corte DIC-2025
Shapefile
32 entidades
```

Conciliación:

```text
Secciones de riesgo:          54,772
Secciones con geometría:      54,448
Cobertura:                    99.41%
Sin geometría:                   324
```

Cobertura:

```text
BAJO   99.86%
MEDIO  99.38%
ALTO   98.32%
Top10  97.81%
```

El campo de tipo de sección usa códigos distintos entre CCPC y MGS. El mapeo
dominante auditado fue:

```text
2 → U
3 → M
4 → R
```

Después de normalizar quedaron 71 discrepancias de tipo y 2 discrepancias
municipales documentadas.

La capa espacial provisional contiene:

```text
54,365 Polygon
83 MultiPolygon
0 geometrías nulas
0 geometrías vacías
0 geometrías inválidas
```

## Dashboard

El dashboard provisional se encuentra en:

```text
dashboard/app.py
```

Ejecutar:

```powershell
streamlit run dashboard\app.py
```

Funciones:

- selector de escenario;
- filtro por entidad;
- filtro por municipio;
- filtro de nivel de riesgo;
- Top10;
- persistencia/sensibilidad;
- KPIs;
- mapa territorial;
- incertidumbre en tooltip;
- resumen estatal;
- resumen municipal.

Para evitar enviar más de 200 MB al navegador, la vista nacional utiliza puntos
representativos de cada sección y la vista por entidad utiliza los polígonos
seccionales.


## Nota de interpretación de la vista nacional

La vista nacional del dashboard está optimizada para rendimiento. En lugar de
enviar al navegador los más de 54 mil polígonos completos, cada sección con
estimación disponible se representa mediante un **punto representativo ubicado
dentro de su polígono**.

Por esta razón, las zonas con secciones rurales de gran extensión pueden verse
mucho más vacías que las zonas urbanas densas. Un espacio blanco en la vista
nacional **no debe interpretarse automáticamente como ausencia de sección
electoral**.

También debe distinguirse entre:

```text
universo cartográfico total
vs.
universo predictivo primary_clean10
```

El modelo sólo asigna estimación a secciones con historia comparable y controles
de calidad suficientes. Por tanto, algunas secciones existentes en la cartografía
pueden quedar sin predicción.

Ejemplo observado con la cartografía provisional:

```text
Baja California
secciones primary_clean10: 1,459
con geometría conciliada:  1,445
```

La cobertura de 99.04% anterior corresponde al **universo predictivo del estado**,
no a la totalidad de las secciones cartográficas existentes.

### Mejora visual pendiente antes de la entrega final

Para evitar que las zonas blancas se interpreten como falta de territorio
electoral, la versión final del dashboard deberá utilizar dos capas:

```text
CAPA BASE
todas las secciones de la cartografía
→ gris claro

CAPA DE RIESGO
secciones con predicción primary_clean10
→ verde / amarillo / rojo
```

La interpretación prevista será:

- gris: sección cartográfica existente sin estimación dentro del universo
  predictivo primario;
- verde: riesgo relativo bajo;
- amarillo: riesgo relativo medio;
- rojo: riesgo relativo alto;
- borde oscuro: Top10 prioritario.

También se deberá mostrar un indicador de **cobertura predictiva por entidad**
calculado directamente a partir de la cartografía utilizada, distinguiendo entre
número total de secciones cartográficas y número de secciones con estimación.

Esta mejora es visual y de transparencia metodológica; no modifica el modelo,
los umbrales del semáforo ni las predicciones.

## Pipeline

```text
00_check_setup.py
01_audit_raw.py
02_build_master.py
03_eda.py
04_build_features.py
05_backtesting.py
06_residual_preelection.py
07_dual_history_backtest.py
08_robustness_model_selection.py
09_select_architecture.py
10_fit_final_forecast_2027.py
11_calibrate_traffic_light.py
12_build_scenarios.py
13_sensitivity_prioritization.py
14_reconcile_cartography.py
14b_audit_reconciliation.py
15_build_spatial_layer.py
dashboard/app.py
```

## Estructura

```text
hackathon_ine/
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── docs/
├── reports/
├── src/
├── dashboard/
├── models/
├── notebooks/
├── requirements.txt
├── .gitignore
└── README.md
```

### `data/raw/`

Fuentes originales. No se versionan.

Incluye localmente:

- seis ZIP CCPC;
- cartografía provisional MGS.

### `data/interim/`

Productos temporales y extracción de cartografía. No se versiona.

### `data/processed/`

Bases maestra, datasets predictivos, forecast, riesgo, escenarios, sensibilidad
y capas geográficas. No se versionan por defecto debido a tamaño y porque son
reproducibles.

### `reports/`

Tablas pequeñas, manifiestos, auditorías y documentación metodológica de cada
etapa. Sí se versionan.

### `src/`

Pipeline reproducible.

### `dashboard/`

Aplicación interactiva.

## Instalación

Python usado durante el desarrollo inicial:

```text
Python 3.10.9
```

Crear entorno:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Dependencias geoespaciales y dashboard:

```text
geopandas
pyogrio
shapely
pyproj
streamlit
pydeck
```

## Archivos que no deben subirse

```text
.venv/
data/raw/*
data/interim/*
data/processed/*
reports/*/predictions/
models/*
```

La cartografía y los CCPC originales se descargan desde sus fuentes oficiales y
los productos derivados se reconstruyen con el pipeline.

## Limitaciones actuales

1. La cartografía visual es provisional MGS DIC-2025.
2. El universo forecast es una cohorte comparable filtrada, no el universo
   electoral oficial futuro completo.
3. Los intervalos de incertidumbre son empíricos.
4. Los escenarios son supuestos de sensibilidad, no inferencia causal.
5. Las secciones sin correspondencia cartográfica no reciben interpolación
   automática.
6. El semáforo representa prioridad relativa territorial.

## Próximas etapas

```text
16  Finalizar y pulir dashboard
17  Priorización y recomendaciones institucionales
18  Informe metodológico final
19  Presentación ejecutiva
20  Auditoría de reproducibilidad y paquete de entrega
```

## Estado de GitHub

El repositorio debe mantenerse actualizado después de cada etapa estable.

Flujo:

```powershell
git status
git add .
git commit -m "Descripción del cambio"
git push
```

Durante el desarrollo se recomienda mantenerlo privado y revisar las condiciones
del concurso antes de asignar una licencia pública.
