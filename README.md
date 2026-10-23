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

### Qué tipo de modelo es

Es una **regresión lineal por mínimos cuadrados** (`LinearRegression` de
scikit-learn) con sólo dos variables por sección; no es un modelo de árboles:

```text
abstención 2027 = 0.048 + 0.677 × abstención 2021 + 0.180 × abstención 2024
```

El resultado se recorta a 0–100%.

**Ya separa los dos tipos de elección.** Las intermedias (sólo diputados:
2009, 2015, 2021 y 2027) tienen mucha más abstención que las presidenciales
(2012, 2018, 2024): a nivel nacional, 48–56% contra 38–40%. Comparar años
seguidos mezclaría ese efecto con cambios reales de comportamiento. Por eso:

- la variable principal es la **última elección del mismo tipo**: para 2027,
  que es intermedia, la de 2021;
- la segunda es la **elección federal más reciente** (2024), que aporta
  información actual aunque sea de otro tipo;
- el coeficiente de la misma familia (0.677) pesa casi 4 veces más que el de
  la reciente (0.180);
- el historial de la base maestra (`PREV_*`, `DELTA_ABST_VS_PREV`) también
  compara siempre contra la elección anterior del mismo tipo.

Los coeficientes se estimaron juntando todas las ventanas históricas
comparables, cada una con la misma lógica:

| Elección objetivo | Misma familia | Más reciente |
|---|---|---|
| 2015 | 2009 | 2012 |
| 2018 | 2012 | 2015 |
| 2021 | 2015 | 2018 |
| 2024 | 2018 | 2021 |

**Por qué no Random Forest.** Se probaron Random Forest, HistGradientBoosting y
Ridge con decenas de variables (sexo, edad, NS, historia), además de modelos de
residuo y de doble historia. En los backtests temporales quedaron por debajo de
líneas base simples: en 2024 el error medio absoluto fue de 5.42 pp (Random
Forest) y 5.46 pp (HistGradientBoosting), contra 4.74 pp de repetir la
abstención de la elección anterior y 4.36 pp de `two_history_linear` (cada
etapa evalúa un universo de secciones ligeramente distinto). La regla de
selección predefinida exigía mejorar a la línea base en 2021 y en 2024 con
respaldo de bootstrap; sólo la cumplieron `two_history_linear` y un promedio
ponderado de las dos historias, y ganó el lineal.

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
- resumen municipal;
- capa base gris con las secciones sin estimación;
- cobertura predictiva por vista y por entidad;
- capa violeta con las secciones de NS alto (estimación de baja confiabilidad,
  fuera del semáforo);
- página **Datos por año** (2009–2024, nacional o por entidad, todas las
  elecciones o sólo intermedias o presidenciales): abstención y NS por año,
  mapa por año (abstención, NS o cambio contra la elección anterior del mismo
  tipo, con rangos fijos para comparar entre elecciones), secciones por rango
  de NS y cambios de secciones entre elecciones, para valorar las
  restricciones del modelo.

El dashboard tiene dos páginas: `dashboard/app.py` es el punto de entrada y
la navegación; el mapa está en `dashboard/mapa.py`, la vista anual en
`dashboard/datos_anuales.py` y las piezas de mapa compartidas en
`dashboard/comun.py`.

Para no saturar el navegador, la vista nacional es **híbrida** por defecto:
las secciones de más de 100 km² se dibujan como polígono simplificado y las
demás como punto. El selector **Vista nacional** permite volver a la vista de
solo puntos. La vista por entidad siempre usa los polígonos seccionales.


## Nota de interpretación de la vista nacional

La vista nacional del dashboard está optimizada para rendimiento. En lugar de
enviar al navegador los más de 54 mil polígonos completos, cada sección con
estimación disponible se representa mediante un **punto representativo ubicado
dentro de su polígono**.

Por esta razón, en la vista de solo puntos las zonas con secciones rurales de
gran extensión pueden verse mucho más vacías que las zonas urbanas densas. Un
espacio blanco **no debe interpretarse automáticamente como ausencia de sección
electoral**: la cartografía cubre entre 98.8% y 100% de la superficie de cada
estado. En el norte, una sección promedia entre 75 y 134 km² (Chihuahua,
Sonora, Coahuila, Durango, Baja California Sur), contra 0.27 km² en la Ciudad
de México.

La **vista híbrida** (por defecto) corrige este efecto: las 3,902 secciones de
más de 100 km² (5.3% de las secciones, 68.9% del territorio) se dibujan como
polígono con el contorno simplificado a 500 m, y las demás como punto.

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

### Capa base y cobertura predictiva

Para evitar que las zonas blancas se interpreten como falta de territorio
electoral, el dashboard dibuja dos capas:

```text
CAPA BASE
todas las secciones de la cartografía (73,268)
→ gris claro

CAPA DE RIESGO
secciones con predicción primary_clean10 (54,448)
→ verde / amarillo / rojo
```

Interpretación:

- gris: sección cartográfica existente sin estimación dentro del universo
  predictivo primario, o que quedó fuera de los filtros activos;
- verde: riesgo relativo bajo;
- amarillo: riesgo relativo medio;
- rojo: riesgo relativo alto;
- borde oscuro: Top10 prioritario.

El indicador **Cobertura predictiva** (secciones con estimación / secciones de
la cartografía) se muestra para la vista actual (nacional, entidad o municipio)
y por entidad en el resumen estatal. Nacionalmente es 74.3%; en Baja California,
64.1% (1,445 de 2,254), porque sus secciones rurales extensas no tienen
estimación. No depende de los filtros de riesgo.

`15_build_spatial_layer.py` genera la capa base en
`data/processed/spatial_2027/cartography_base_2027.parquet`. Si no existe
(salidas anteriores), el dashboard funciona sin ella.

Esta mejora es visual y de transparencia metodológica; no modifica el modelo,
los umbrales del semáforo ni las predicciones.

### Semáforo alternativo (Oscar)

`st_gcn_participation/` (rama `Oscar`) propone otro semáforo 2027. Usa
persistencia, es decir la abstención de 2021, sobre 72,599 secciones sin filtro
de NS. La página **Semáforo alternativo (Oscar)** lo compara sección por sección
con el oficial, que no cambia.

- En las 54,772 secciones compartidas coinciden en nivel el 92.8%
  (Spearman 0.991).
- La diferencia real es de cobertura: Oscar suma 17,827 secciones que el filtro
  de calidad oficial excluye, 9,199 de ellas por NS alto.

- Oscar probó también 2015 y 2018. `src/semaforo_oscar/03_backtest_2018.py`
  evalúa el modelo oficial en 2018: pierde contra la persistencia (11.35 vs.
  4.77 pp de MAE; Spearman 0.71 vs. 0.78). Ahí sólo puede entrenarse con la
  ventana de 2015, una intermedia. 2015 no se puede evaluar porque no hay
  ventana anterior.

Su trabajo se replica exacto desde los ZIP oficiales. Comandos y resultados en
`reports/semaforo_oscar/REPLICA.md`; la comparación completa está en
`reports/semaforo_oscar/COMPARACION.md`.

### Auditoría del NS

`src/auditoria_ns/01_auditar_ns.py` revisa los registros sin información (NS): de
dónde vienen, si sesgan la abstención y qué le hace al semáforo el filtro
NS ≤ 10%. Reporte completo en `reports/auditoria_ns/AUDITORIA_NS.md`.

- El NS viene de casillas completas: dentro de cada sección afecta igual a todas
  las edades y ambos sexos.
- No sesga de forma relevante la abstención medida (+0.44 pp en promedio).
- El filtro sí deja fuera más secciones de riesgo: 27.4% de las excluidas serían
  ALTO, contra 20% en el semáforo.
- Subir el umbral a 25% recupera 1,683 secciones y mantiene en ALTO al 97.7% de
  las ALTO oficiales. Queda como propuesta; el universo del modelo no cambió.

### Descomposición por edad y sexo

`src/descomposicion_edad/01_descomponer_edad.py` (~20 s) arma la curva de
participación por edad simple desde los ZIP originales y separa los cambios de
abstención en composición (el electorado envejece) y comportamiento (cada grupo
vota distinto, método de Kitagawa). Reporte en
`reports/descomposicion_edad/DESCOMPOSICION_EDAD.md`.

- Los de 18 años votan más que los de 19 a 30, por el primer voto. La abstención
  es máxima cerca de los 25 y mínima entre los 61 y 69 años.
- El envejecimiento baja la abstención alrededor de 1 pp en 12 años. En
  presidenciales, de 2012 a 2024, el comportamiento empeoró +3.5 pp; el
  envejecimiento lo disimula y el total sólo sube +2.4 pp.
- Los hombres se abstienen 9.4 pp más que las mujeres (2024), hasta +14.1 pp a
  los 29 años.
- La edad explica poco las diferencias entre territorios (R² ≤ 0.14). De los
  26.7 pp que separan las secciones ALTO de las BAJO, explica 1.3 pp.
- La abstención cae de golpe a los 65 años: −2.5 pp en 2024 y −1.2 pp en 2021,
  cuando antes los saltos eran de −0.9 pp como mucho. Coincide con la edad de la
  pensión para adultos mayores; es una asociación por verificar, no un efecto
  causal.

### Brecha intermedia vs. presidencial

`src/brecha_tipo/01_brecha_intermedia_presidencial.py` (~5 s) mide, por sección,
la abstención de la intermedia menos la de la presidencial contigua: cuánta gente
sólo vota cuando hay elección presidencial. 2027 es intermedia. Reporte en
`reports/brecha_tipo/BRECHA_TIPO.md`.

- La brecha nacional se cerró de +18.0 pp (2009–2012) a +7.8 pp (2021–2024). En
  2021–2024, 20% de las secciones se abstuvieron más en la presidencial. Es
  grande en secciones urbanas y casi nula en las rurales.
- Elecciones locales el mismo día que la intermedia reducen la brecha 10.4 pp, y
  una gubernatura 5.5 pp más. Que más entidades empataran sus elecciones locales
  con las federales explicaría cerca de 64% del cierre. El calendario está
  pendiente de validar.
- Las secciones ALTO del semáforo 2027 tienen la brecha más grande (+10.9 pp,
  contra +3.6 pp en BAJO).
- Aguascalientes y Quintana Roo tendrán gubernatura concurrente en 2027 y en 2021
  no; el modelo no usa concurrencia.

## Sitio web (Astro + FastAPI, en construcción)

Migración del dashboard de Streamlit a un sitio con frontend estático y API de
sólo lectura. Streamlit sigue disponible para exploración interna.

```text
FastAPI (api/main.py, puerto 8000)
 ├─ /api/...       resumen y ficha por sección, histórico, grupos y semáforo alternativo (DuckDB sobre data/processed/web/*.parquet)
 ├─ /tiles/...     secciones.pmtiles con HTTP Range (MapLibre lo lee sin servidor de teselas)
 └─ /              build estático de Astro + React (web/dist)
```

Cómo instalarlo y levantarlo: ver **Instalación → Sitio web**.

Páginas (las cuatro primeras son las de Streamlit, con números idénticos; las de análisis son nuevas y están en el menú "Análisis"):

| Página | Ruta | Qué muestra |
|---|---|---|
| Mapa de riesgo | `/` | Semáforo 2027, escenarios, filtros, KPIs y tablas; 54,448 secciones y 74.3% de cobertura nacional |
| Datos por año | `/historico/` | Mapa por elección (abstención, NS o cambio), series 2009–2024, rangos de NS y cambios de secciones |
| Grupos | `/grupos/` | Tipología del clustering: perfil, trayectorias, mapa por grupo y composición por entidad o municipio |
| Semáforo alternativo | `/semaforo-alternativo/` | Oficial vs. Oscar: mapa de diferencias, matriz de niveles, motivos y coincidencia por entidad |
| Edad y sexo | `/edad/` | Abstención no explicada por la edad en el mapa, curva por edad y sexo, salto a los 65, Kitagawa y entidades |
| Intermedia vs. presidencial | `/brecha/` | Brecha por sección en el mapa, evolución, efecto de la concurrencia local e implicaciones para 2027 |
| Auditoría NS | `/auditoria-ns/` | Qué secciones entrarían al semáforo con otro umbral de NS (y con qué nivel), NS por año en el mapa y las pruebas de la auditoría |

Todas dibujan polígonos reales también a nivel nacional y abren una ficha por
sección al hacer clic. El mapa de riesgo guarda sus filtros en la URL para
compartir una vista. Las gráficas son SVG propias (sin librería): Plot o Vega
insertan estilos en línea que la CSP bloquearía.

La página de Random Forest M17 todavía no se migra: depende de
`data/processed/rf_dashboard/`, que generan `src/16`–`20`, y esa cadena no corre
en una copia limpia del repo (ver "Limitaciones actuales").

Seguridad:

- En producción no corre Node: sólo Python, sin escritura ni sesiones, con
  entradas validadas y consultas parametrizadas.
- CSP estricta sin `'unsafe-inline'`: los scripts y estilos en línea de Astro
  van con hash.
- Imágenes base fijadas por digest; la API corre con un usuario sin privilegios.
- Las dependencias deben tener al menos 7 días publicadas: `--uploaded-prior-to P7D`
  en pip y `minimumReleaseAge` en pnpm. pnpm no ejecuta scripts de instalación de
  dependencias.
- `pip-audit` y `pnpm audit` sin vulnerabilidades conocidas (oct-2026).
- Antes de publicar falta poner HTTPS con un proxy (Caddy o el del hosting).

### Pendientes del sitio

1. **Página Random Forest M17.** Está bloqueada porque `src/16`–`20` no corren en
   una copia limpia (ver "Limitaciones actuales", punto 7). Hay dos formas de
   destrabarla:
   - que se comparta `data/processed/rf_dashboard/` de la corrida original;
   - corregir las etapas 18 y 19 para que elijan del registro la predicción que
     sí existe, y correr la cadena (unos 90 minutos de cómputo).
2. **Nombres de entidad.** Salen en mayúsculas y sin acentos ("CIUDAD DE
   MEXICO"), como vienen en los CCPC. Falta un catálogo con los nombres oficiales.
3. **Modo oscuro.** Los colores ya son variables CSS
   (`web/src/styles/global.css`); falta definir la paleta oscura y validarla.
4. **Mapa base con nombres de lugares.** Hoy sólo hay contornos de entidades y
   municipios. Para no depender de terceros, la opción es un mapa base de
   Protomaps autoalojado.
5. **Publicación.** Falta HTTPS con un proxy (Caddy o el del hosting) y acceso
   restringido mientras se revisan los términos del concurso.
6. **CI.** Falta correr `pip-audit`, `pnpm audit` y OSV-Scanner en cada PR, y
   automatizar el build y el despliegue.
7. **Pruebas del frontend.** Hoy sólo existe la prueba de humo de la API
   (`api/test_api.py`).
8. **Carga de datos (más adelante).** Requiere autenticación, escritura,
   PostgreSQL y una cola para correr el pipeline.

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
21_export_web.py        # teselas PMTiles + tabla para el sitio web (ver reports/web_export/)
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
├── dashboard/        # Streamlit (exploración interna)
├── api/              # API FastAPI + DuckDB del sitio web
├── web/              # frontend Astro + React del sitio web
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

Dashboard exploratorio en Streamlit.

### `api/`

API de sólo lectura del sitio (`main.py`), su imagen de Docker y su prueba de
humo (`test_api.py`).

### `web/`

Frontend Astro + React:

- `src/pages/`: una página por ruta.
- `src/components/`: mapa, ficha, gráficas y controles.
- `src/styles/global.css`: tokens de diseño.

`node_modules/` y `dist/` no se versionan.

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

`requirements.txt` incluye las dependencias geoespaciales y del dashboard
(geopandas, pyogrio, shapely, pyproj, streamlit, pydeck).

### Docker

Alternativa sin entorno local. El contenedor monta la carpeta del proyecto,
así que `data/` y `reports/` se leen y escriben en el disco local y los cambios
de código no requieren reconstruir la imagen (sólo cambios en `requirements.txt`
o en el `Dockerfile`). La imagen base está fijada por digest e incluye
`tippecanoe` para `src/21_export_web.py`.

```powershell
docker compose build
docker compose run --rm app python src/00_check_setup.py   # cualquier etapa del pipeline
docker compose up                                          # dashboard en http://localhost:8501
```

### Sitio web (API FastAPI + frontend Astro)

**Qué alimenta cada página.** Cada análisis es un script que escribe sus CSV y su
reporte en `reports/<análisis>/`. Esos archivos se versionan y el script los
reescribe completos cada vez que corre. Los datos pesados por sección quedan en
`data/processed/<análisis>/`, que no se versiona.

| Página | Ruta | Script que genera sus datos | Qué escribe | ¿Hay que correrlo? |
|---|---|---|---|---|
| Mapa de riesgo | `/` | Pipeline 00–15 y `src/21_export_web.py` | `data/processed/web/` | Sí |
| Datos por año | `/historico/` | `src/21_export_web.py` | `data/processed/web/historico.parquet` | Sí |
| Grupos | `/grupos/` | `src/clustering/01_build_section_clusters.py` | `data/processed/clustering/`, `reports/clustering/` | Sí, para esa página |
| Semáforo alternativo | `/semaforo-alternativo/` | Réplica de Oscar (cuatro pasos, abajo) | `data/processed/semaforo_oscar/`, `reports/semaforo_oscar/` | Sí, para esa página |
| Auditoría del NS | `/auditoria-ns/` | `src/auditoria_ns/01_auditar_ns.py` (segundos) | `reports/auditoria_ns/` | No: sus CSV ya están en el repo |
| Edad y sexo | `/edad/` | `src/descomposicion_edad/01_descomponer_edad.py` (~20 s) | `reports/descomposicion_edad/`, `data/processed/descomposicion_edad/` | Las tablas ya están en el repo; la capa del mapa sí lo necesita |
| Intermedia vs. presidencial | `/brecha/` | `src/brecha_tipo/01_brecha_intermedia_presidencial.py` (~5 s) | `reports/brecha_tipo/`, `data/processed/brecha_tipo/` | Las tablas ya están en el repo; la capa del mapa sí lo necesita |

Si falta lo de una página, esa página muestra un aviso o su mapa sale vacío; las
demás funcionan igual.

**Orden completo desde cero, con Docker (recomendado).** No hace falta instalar
Node ni Python en la máquina. Los análisis van **antes** de la etapa 21, porque
ésta une sus resultados por sección a las teselas del mapa.

```bash
# 0. Imágenes: una vez, o cuando cambie requirements.txt, un Dockerfile o api/requirements.txt
docker compose build app api
docker compose --profile web build web

# 1. Pipeline base, etapas 00–15 (~10 min). Necesita los datos de "Obtención de datos".
docker compose run --rm app sh -c 'for s in src/0*.py src/1[0-5]*.py; do python "$s" || exit 1; done'

# 2. Análisis que alimentan páginas
docker compose run --rm app python src/clustering/01_build_section_clusters.py           # Grupos
docker compose run --rm app python src/semaforo_oscar/01_generar_csv_oscar.py            # Oscar 1/4: CSV desde los ZIP (~4 GB)
docker compose run --rm -e OSCAR_DATA_DIR=data/interim/oscar_tableau app sh -c \
  'python st_gcn_participation/analyze_participation.py && python st_gcn_participation/modeling/run_models.py && python st_gcn_participation/modeling/risk_scenarios.py'  # Oscar 2/4 (~11 min)
git checkout -- st_gcn_participation/outputs st_gcn_participation/modeling                 # deja como estaban los archivos versionados de Oscar
docker compose run --rm app python src/semaforo_oscar/02_comparar_semaforos.py           # Oscar 3/4: cruce con el oficial
docker compose run --rm app python src/semaforo_oscar/03_backtest_2018.py                # Oscar 4/4 (opcional): backtest 2018
docker compose run --rm app python src/auditoria_ns/01_auditar_ns.py                     # Auditoría del NS
docker compose run --rm app python src/descomposicion_edad/01_descomponer_edad.py        # Edad y sexo
docker compose run --rm app python src/brecha_tipo/01_brecha_intermedia_presidencial.py  # Intermedia vs. presidencial

# 3. Exportación para el sitio (~2 min): teselas PMTiles y tablas de la API
docker compose run --rm app python src/21_export_web.py

# 4. Frontend y API
docker compose run --rm web pnpm install    # una vez, o cuando cambie web/package.json
docker compose run --rm web pnpm build      # genera web/dist
docker compose up -d api                    # sitio en http://localhost:8000
python api/test_api.py                      # prueba de humo: debe imprimir "API OK"
```

**Qué volver a correr según lo que cambió:**

| Cambió… | Corre… |
|---|---|
| Los datos del INE o el pipeline | Pasos 1, 2 y 3, y luego `docker compose restart api` |
| Un análisis (por ejemplo, la edad) | Ese script; si cambia su capa del mapa, también el paso 3; luego `docker compose restart api` |
| El código del frontend (`web/`) | `docker compose run --rm web pnpm build` y `docker compose restart api` |
| El código de la API (`api/main.py`) | `docker compose restart api` |
| `web/package.json` | `docker compose run --rm web pnpm install` y el build |
| Un `requirements.txt` o un `Dockerfile` | El paso 0 |

**Modo desarrollo del frontend** (recarga al guardar, con la API corriendo):

```bash
docker compose --profile web up web         # http://localhost:4321
```

**Sin Docker: API.** Necesita Python 3.12 y pip 26.2 o posterior, que es el que
admite `--uploaded-prior-to`:

```bash
python -m venv .venv-api
source .venv-api/bin/activate                  # Windows: .\.venv-api\Scripts\Activate.ps1
pip install "pip>=26.2"
pip install --uploaded-prior-to P7D -r api/requirements.txt
uvicorn api.main:app --port 8000               # desde la raíz del repo
```

**Sin Docker: frontend.** Necesita Node 24.22.1 o posterior (LTS con los
parches de seguridad del 21-oct-2026) y pnpm 12.13:

```bash
npm install --global --ignore-scripts pnpm@12.13.0
cd web
pnpm install     # aplica pnpm-workspace.yaml: 7 días mínimos de publicación y sin scripts de instalación
pnpm build       # genera web/dist, que sirve la API
pnpm dev         # desarrollo en http://localhost:4321; manda /api a localhost:8000 (se cambia con API_URL)
```

**Cuándo reiniciar la API** (`docker compose restart api`):

- después de correr la etapa 21;
- después de cada `pnpm build`.

La API carga las tablas y calcula los hashes de la CSP al arrancar.

**Seguridad de las dependencias:**

- Antes de agregar o actualizar una dependencia, revisa que tenga al menos 7
  días publicada. pnpm y pip lo exigen; si una versión es más nueva, la
  instalación falla a propósito.
- Después de cualquier cambio, corre `pip-audit` y `pnpm audit`.

## Obtención de datos

`data/` no se versiona, así que en un clon nuevo hay que descargar las fuentes
oficiales (~455 MB) y correr el pipeline. Los comandos son para bash/zsh
(macOS, Linux, Git Bash o WSL) y se ejecutan desde la raíz del proyecto.

### 1. Carpetas

```bash
mkdir -p data/raw/cartography_2027 data/interim data/processed models notebooks
```

### 2. Conteos Censales de Participación Ciudadana (6 ZIP, ~290 MB)

Fuente: [Conteos Censales de Participación](https://ine.mx/transparencia/datos-abiertos/visualizacion-datos/conteos-censales-participacion/)
(INE, datos abiertos). Sólo se usan los seis ZIP de elecciones federales; los de
Prisión Preventiva, Voto Anticipado y Poder Judicial 2025 no entran al pipeline.

```bash
for f in 2022/04/DatosAbiertos_DECEyEC_ConteosCensales{2009,2012,2015,2018,2021}.zip \
         2025/08/DatosAbiertos_DECEyEC_ConteosCensales2024.zip; do
  curl -fL -o "data/raw/$(basename "$f")" "https://ine.mx/wp-content/uploads/$f"
done
```

### 3. Cartografía MGS por entidad (32 ZIP, ~165 MB)

Fuente: [SIGE · Sistema de Información Geográfica Electoral](https://cartografia.ine.mx/sige8/),
Marco Geográfico Seccional en Shapefile, corte 15-DIC-2025 (el más reciente
publicado). Cada ZIP trae `SECCION.shp`, que es la capa que usan los scripts 14 y 15.

```bash
for e in $(seq 1 32); do
  curl -fL -o "data/raw/cartography_2027/mgs_${e}_Shapefile.zip" \
    "https://cartografia.ine.mx/mapoteca/MGS_UTM_SHAPEFILE_15DIC2025/$(printf %02d "$e").zip"
done
```

Descargar desde la interfaz web del SIGE también funciona: genera el mismo nombre
`mgs_N_Shapefile.zip`, pero con el ZIP oficial anidado dentro, y
`14_reconcile_cartography.py` lo extrae.

Cuando se publique un corte nuevo (p. ej. el Marco Geográfico Electoral
2026–2027), la API del SIGE indica el corte vigente y la ruta de cada archivo:

```text
https://cartografia.ine.mx/sige8/api/corte/?tipo=base
https://cartografia.ine.mx/sige8/api/bases/?producto=mgs&entidad=1&formato=Shapefile
→ archivo en https://cartografia.ine.mx/mapoteca/<path><archivo>
```

### 4. Verificar

```bash
docker compose run --rm app python src/00_check_setup.py
```

Debe terminar con `La estructura básica está lista`. Los registros por año deben
coincidir con la tabla de auditoría de la sección [Datos](#datos), y la
cartografía suma 73,268 secciones.

### 5. Correr el pipeline completo y levantar el dashboard

```bash
docker compose run --rm app sh -c 'for s in src/0*.py src/1[0-5]*.py; do python "$s" || exit 1; done'
docker compose up -d     # http://localhost:8501
```

Tarda ~10 minutos (Docker con 8 GB de RAM) y se detiene en el primer paso que
falle. Corre las etapas 00–15 del modelo oficial; los experimentos de Random Forest
(`src/16`–`20`) quedan fuera porque no corren en una copia limpia (ver
"Limitaciones actuales"). Para el sitio web y los análisis, ver **Instalación →
Sitio web**.

El pipeline reescribe las tablas versionadas de `reports/`. Aunque los resultados
coinciden, `git status` las marcará como modificadas por rutas locales, tiempos
de ejecución y diferencias de redondeo entre máquinas. Si no se cambió la
metodología, descartarlas antes de hacer commit:

```bash
git checkout -- reports/
```

## Archivos que no deben subirse

```text
.venv/
data/raw/*
data/interim/*
data/processed/*
reports/*/predictions/
models/*
web/node_modules/
web/dist/
web/.astro/
```

La cartografía y los CCPC originales se descargan desde sus fuentes oficiales
(ver [Obtención de datos](#obtención-de-datos)) y los productos derivados se
reconstruyen con el pipeline.

## Limitaciones actuales

1. La cartografía visual es provisional MGS DIC-2025.
2. El universo forecast es una cohorte comparable filtrada, no el universo
   electoral oficial futuro completo.
3. Los intervalos de incertidumbre son empíricos.
4. Los escenarios son supuestos de sensibilidad, no inferencia causal.
5. Las secciones sin correspondencia cartográfica no reciben interpolación
   automática.
6. El semáforo representa prioridad relativa territorial.
7. Los experimentos de Random Forest (`src/16`–`20`) no se reproducen en una
   copia limpia. Las etapas 16 y 17 corren (la 16 reproduce sus resultados al
   decimal), pero la 18 toma del registro versionado
   (`reports/experiment_rf_improved/registro_pruebas.json`) la primera
   predicción que coincide. Esa es la de la corrida original, cuyo archivo sólo
   existe en la máquina donde se generó, y la etapa falla con
   `FileNotFoundError`. La 19 tiene el mismo problema: exige una sola
   coincidencia en el registro.

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
