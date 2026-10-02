# Sistema de riesgo territorial de abstención electoral
## Hackathon INE 2026 · Reto 2: Predicción y escenarios de riesgo de abstención

> **Estado:** proyecto en desarrollo. Los resultados incluidos en este repositorio corresponden a etapas de auditoría, análisis exploratorio y backtesting. La arquitectura predictiva final, los escenarios de intervención y el mapa territorial aún no se consideran cerrados.

## 1. Descripción

Este proyecto desarrolla una propuesta para el **Reto 2: Predicción y escenarios de riesgo de abstención** del concurso *Hackea la participación: Datos que construyen democracia*, organizado por el Instituto Nacional Electoral (INE).

El objetivo es construir un sistema reproducible que permita:

- analizar la evolución histórica de la participación y la abstención electoral;
- identificar territorios con señales de mayor riesgo de abstención;
- comparar estrategias predictivas mediante validación temporal;
- construir un semáforo territorial interpretable;
- simular escenarios sin intervención y con intervención hipotética;
- transformar los resultados en una herramienta útil para priorización territorial.

La fuente principal son los **Conteos Censales de Participación Ciudadana (CCPC) 2009–2024** del INE.

## 2. Fuente de datos

Procesos electorales utilizados:

- 2009
- 2012
- 2015
- 2018
- 2021
- 2024

Los archivos originales se descargan de la plataforma oficial del INE:

https://ine.mx/transparencia/datos-abiertos/visualizacion-datos/conteos-censales-participacion/

Convocatoria del Hackathon:

https://ine.mx/hackathon-2026/

### Datos originales

Cada ZIP anual contiene 32 archivos CSV, uno por entidad federativa, además del diccionario correspondiente. Los registros incluyen, entre otras variables:

- año electoral;
- entidad;
- municipio;
- sección electoral;
- distrito federal y local;
- tipo de sección;
- sexo;
- edad;
- lista nominal (`LN`);
- sí votaron (`SV`);
- no votaron (`NV`);
- registros no especificados (`NS`).

Los datos utilizados son agregados y no contienen información personal identificable.

### Definición de abstención utilizada

Se conserva la definición institucional:

```text
Abstención = NV / (SV + NV)
Participación = SV / (SV + NV)
```

Los registros `NS` se tratan por separado y no se contabilizan automáticamente como abstención.

## 3. Magnitud de la base

La auditoría de los seis procesos electorales produjo:

| Año | Registros originales | Secciones |
|---|---:|---:|
| 2009 | 8,706,843 | 64,934 |
| 2012 | 8,604,456 | 65,599 |
| 2015 | 9,106,059 | 68,362 |
| 2018 | 9,251,122 | 68,408 |
| 2021 | 9,430,502 | 68,812 |
| 2024 | 9,773,730 | 70,751 |
| **Total** | **54,872,712** | — |

Después de la agregación, la base maestra contiene:

```text
406,866 observaciones sección × elección
95 variables
```

## 4. Principios metodológicos

El proyecto sigue cuatro reglas principales.

### 4.1 Reproducibilidad

Los ZIP originales no se modifican. Todos los archivos derivados se generan mediante código.

```text
datos RAW
    ↓
auditoría
    ↓
agregación
    ↓
EDA
    ↓
construcción de features
    ↓
backtesting temporal
    ↓
escenarios y riesgo territorial
```

### 4.2 Separación entre elecciones

Para comparaciones del mismo tipo se conservan las familias:

```text
Intermedias:
2009 → 2015 → 2021

Presidenciales:
2012 → 2018 → 2024
```

### 4.3 Control de calidad

Se valida, entre otras cosas:

```text
LN = SV + NV + NS
```

También se generan banderas para:

- denominadores no calculables;
- proporciones elevadas de `NS`;
- cambios de municipio;
- cambios de tipo de sección;
- problemas de comparabilidad longitudinal.

El subconjunto `clean10` utiliza como criterio operativo principal `NS <= 10%` tanto en la observación histórica como en la observación utilizada como ground truth. Los datos completos se conservan para análisis de sensibilidad.

### 4.4 Prevención de fuga de información

Las variables utilizadas para predecir una elección deben corresponder a información disponible antes de conocer su resultado.

No se permite utilizar como predictor información como:

- abstención del año objetivo;
- `SV` del año objetivo;
- `NV` del año objetivo;
- participación por edad del año objetivo;
- comportamiento de votación del año objetivo.

Los manifiestos de features permiten auditar qué variables están autorizadas en cada experimento.

---

# 5. Estructura del proyecto

```text
hackathon_ine/
│
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
│       ├── modeling/
│       └── dual_history/
│
├── docs/
│
├── reports/
│   ├── audit/
│   ├── eda/
│   ├── modeling/
│   ├── backtesting/
│   ├── backtesting_residual/
│   └── dual_history/
│
├── src/
│   ├── 00_check_setup.py
│   ├── 01_audit_raw.py
│   ├── 02_build_master.py
│   ├── 03_eda.py
│   ├── 04_build_features.py
│   ├── 05_backtesting.py
│   ├── 06_residual_preelection.py
│   └── 07_dual_history_backtest.py
│
├── models/
├── dashboard/
├── notebooks/
│
├── requirements.txt
├── .gitignore
└── README.md
```

## 6. Descripción de carpetas

### `data/raw/`

Contiene localmente los seis ZIP originales descargados del INE.

Estos archivos **no se versionan en Git**. Son la fuente inmutable del pipeline y deben descargarse nuevamente desde la fuente oficial al reproducir el proyecto.

### `data/interim/`

Contiene agregados intermedios por elección, principalmente archivos Parquet generados por `02_build_master.py`.

Ejemplos:

```text
section_election_2009.parquet
section_election_2012.parquet
...
section_election_2024.parquet
```

No se versionan porque pueden regenerarse.

### `data/processed/`

Contiene productos derivados listos para análisis.

Principales archivos locales:

```text
section_election_master_v1.csv.gz
section_quality_summary.csv
national_totals_check.csv
nonbinary_2024_summary.csv
build_master_log.txt
```

También contiene:

#### `data/processed/modeling/`

Datasets de transiciones electorales y splits para backtesting:

```text
transition_2009_2015_all.parquet
transition_2009_2015_clean10.parquet
transition_2012_2018_all.parquet
transition_2012_2018_clean10.parquet
transition_2015_2021_all.parquet
transition_2015_2021_clean10.parquet
transition_2018_2024_all.parquet
transition_2018_2024_clean10.parquet

backtest_2021_train_clean10.parquet
backtest_2021_family_train_clean10.parquet
backtest_2021_test_clean10.parquet

backtest_2024_train_clean10.parquet
backtest_2024_family_train_clean10.parquet
backtest_2024_test_clean10.parquet
```

#### `data/processed/dual_history/`

Ventanas de doble historia electoral generadas por `07_dual_history_backtest.py`.

Ejemplo:

```text
dual_history_target_2015_clean10.parquet
dual_history_target_2018_clean10.parquet
dual_history_target_2021_clean10.parquet
dual_history_target_2024_clean10.parquet
```

Los archivos de `data/processed/` no se versionan por defecto porque son derivados y pueden ser pesados.

### `docs/`

Contiene localmente la convocatoria y el manual de la plataforma CCPC.

Por defecto los PDF no se versionan; el repositorio mantiene enlaces a las fuentes oficiales para evitar duplicar documentación externa.

### `reports/audit/`

Resultados de la auditoría de los datos originales.

Principales archivos:

- `AUDIT_REPORT.md`: reporte legible de calidad de datos.
- `audit_year_summary.csv`: resumen por proceso electoral.
- `audit_file_summary.csv`: auditoría por CSV original.
- `audit_missing_by_year.csv`: faltantes por año.
- `section_presence_audit.csv`: presencia longitudinal de secciones.
- `cohort_summary.csv`: tamaño de las cohortes comparables.

### `reports/eda/`

Resultados del análisis exploratorio:

- `EDA_REPORT.md`
- `01_national_summary.csv`
- `02_section_distributions.csv`
- `03_ns_quality.csv`
- `04_by_section_type.csv`
- `05_age_summary.csv`
- `06_sex_summary.csv`
- `07_persistence_baseline.csv`
- `08_ns_sensitivity_baseline.csv`
- `09_longitudinal_changes.csv`
- `10_safe_feature_correlations.csv`
- `figures/`

### `reports/modeling/`

Metadatos de los datasets predictivos:

- `transition_summary.csv`
- `backtest_split_summary.csv`
- `feature_manifest.csv`
- `model_feature_columns.txt`

### `reports/backtesting/`

Resultados de los modelos iniciales:

- `model_comparison.csv`
- `model_comparison_compact.csv`
- `baseline_shift_values.csv`
- `predictions/`

Los archivos de `predictions/` no se versionan por defecto debido a su tamaño.

### `reports/backtesting_residual/`

Resultados del enfoque residual:

- `residual_model_comparison.csv`
- `residual_model_comparison_compact.csv`
- `residual_feature_columns.txt`
- `predictions/`

### `reports/dual_history/`

Resultados del análisis con dos memorias electorales:

- `dual_history_window_summary.csv`
- `dual_history_model_comparison.csv`
- `dual_history_model_comparison_compact.csv`
- `blend_weights.csv`
- `dual_history_feature_manifest.csv`
- `predictions/`

### `src/`

Contiene el pipeline reproducible completo.

### `models/`

Reservado para modelos serializados y artefactos finales. Por ahora no se consideran resultados definitivos.

### `dashboard/`

Reservado para el mapa interactivo, semáforo territorial y visualización de escenarios.

### `notebooks/`

Reservado para análisis exploratorios o demostraciones. La lógica productiva debe permanecer en `src/`.

---

# 7. Scripts

## `00_check_setup.py`

Verifica que el entorno esté preparado antes de procesar datos.

Comprueba:

- versión de Python;
- estructura de carpetas;
- dependencias;
- existencia de los seis ZIP;
- validez de los ZIP;
- presencia de 32 CSV por año;
- columnas esperadas.

No modifica los datos.

## `01_audit_raw.py`

Audita los 54.8 millones de registros originales directamente desde los ZIP.

Valida:

- número de filas;
- entidades;
- municipios;
- secciones;
- nulos;
- negativos;
- categorías de sexo y edad;
- consistencia de `LN`, `SV`, `NV` y `NS`;
- presencia longitudinal de secciones.

Genera `reports/audit/`.

## `02_build_master.py`

Agrega los registros originales de edad × sexo a nivel:

```text
sección electoral × elección
```

Genera:

- totales de lista nominal;
- participación y abstención;
- proporción de `NS`;
- indicadores por sexo;
- estructura por grupos de edad;
- participación/abstención histórica por grupo;
- edad promedio;
- variables longitudinales;
- banderas de calidad.

Produce la base maestra de 406,866 filas y 95 variables.

## `03_eda.py`

Realiza el análisis exploratorio.

Incluye:

- resumen nacional por año;
- distribuciones por sección;
- calidad de `NS`;
- diferencias por tipo de sección;
- estructura por edad;
- diferencias por sexo;
- baseline de persistencia;
- análisis de sensibilidad de `NS`;
- cambios longitudinales;
- correlaciones de variables disponibles antes del resultado objetivo.

## `04_build_features.py`

Convierte la base maestra en transiciones electorales para modelado.

Transiciones:

```text
2009 → 2015
2012 → 2018
2015 → 2021
2018 → 2024
```

Genera:

- datasets completos;
- datasets `clean10`;
- splits temporales;
- splits de misma familia;
- manifiesto de variables;
- lista cerrada de features autorizadas.

Incluye controles explícitos contra fuga de información.

## `05_backtesting.py`

Compara modelos y baselines mediante validación temporal.

Baselines:

- persistencia histórica;
- persistencia con desplazamiento medio histórico.

Modelos:

- Ridge Regression;
- Random Forest;
- HistGradientBoosting.

Métricas:

- MAE;
- RMSE;
- R²;
- Pearson;
- Spearman;
- bias;
- Top 20% overlap;
- Top 10% overlap;
- tiempo de entrenamiento.

## `06_residual_preelection.py`

Evalúa una formulación residual:

```text
abstención futura
=
abstención histórica
+
cambio estimado
```

También incorpora variables de composición registral del periodo objetivo que no dependen del comportamiento de votación.

El objetivo es evaluar si un corrector de cambio añade valor sobre el baseline histórico.

## `07_dual_history_backtest.py`

Evalúa una arquitectura con **dos memorias electorales**:

```text
última elección de la misma familia
+
última elección federal reciente
→
siguiente elección
```

Ventanas evaluadas:

```text
2009 + 2012 → 2015
2012 + 2015 → 2018
2015 + 2018 → 2021
2018 + 2021 → 2024
```

Compara:

- última elección de la misma familia;
- elección más reciente;
- promedio 50/50;
- blend con peso aprendido;
- regresión lineal con dos historias;
- Ridge con variables históricas enriquecidas;
- HistGradientBoosting con variables históricas enriquecidas.

---

# 8. Resultados provisionales

> Estos resultados sirven para selección metodológica y todavía no representan el producto final del concurso.

## Baseline histórico

En el backtest 2024, la persistencia de la elección presidencial anterior obtuvo aproximadamente:

```text
MAE = 4.74 puntos porcentuales
R² = 0.611
Top20 overlap = 0.710
```

Esto mostró que la estructura territorial histórica contiene una señal fuerte y que modelos más complejos no deben adoptarse automáticamente.

## Doble historia electoral

El enfoque de doble historia produjo mejoras importantes.

### Backtest 2021

El promedio simple de las dos elecciones previas obtuvo aproximadamente:

```text
MAE = 6.18 pp
RMSE = 8.02 pp
R² = 0.588
Top20 = 0.657
Top10 = 0.621
```

### Backtest 2024

El blend aprendido usando las dos memorias electorales obtuvo aproximadamente:

```text
MAE = 4.44 pp
RMSE = 5.90 pp
R² = 0.678
Top20 = 0.725
```

La regresión lineal de dos historias obtuvo un MAE aún menor:

```text
MAE = 4.36 pp
R² = 0.672
Top20 = 0.721
```

Estos resultados sugieren que combinar la elección comparable anterior con la elección federal más reciente puede aportar información útil. La arquitectura final todavía no se considera seleccionada; se requiere análisis adicional de estabilidad, incertidumbre y aplicabilidad a escenarios futuros.

---

# 9. Instalación

## Requisitos

Se utilizó Python 3.10 durante el desarrollo inicial.

Crear entorno virtual:

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Datos

Descargar desde la fuente oficial los seis ZIP y colocarlos sin modificar en:

```text
data/raw/
```

Con los nombres:

```text
DatosAbiertos_DECEyEC_ConteosCensales2009.zip
DatosAbiertos_DECEyEC_ConteosCensales2012.zip
DatosAbiertos_DECEyEC_ConteosCensales2015.zip
DatosAbiertos_DECEyEC_ConteosCensales2018.zip
DatosAbiertos_DECEyEC_ConteosCensales2021.zip
DatosAbiertos_DECEyEC_ConteosCensales2024.zip
```

## Ejecución

Ejecutar desde la raíz del proyecto:

```powershell
python src\00_check_setup.py
python src\01_audit_raw.py
python src\02_build_master.py
python src\03_eda.py
python src\04_build_features.py
python src\05_backtesting.py
python src\06_residual_preelection.py
python src\07_dual_history_backtest.py
```

Cada etapa utiliza las salidas de las anteriores.

---

# 10. Archivos que NO deben subirse a GitHub

El repositorio está diseñado para **no versionar**:

- `.venv/`;
- los seis ZIP originales;
- archivos Parquet intermedios;
- la base maestra comprimida;
- datasets de modelado pesados;
- predicciones sección por sección;
- modelos serializados pesados;
- cachés de Python;
- documentación PDF externa.

Estos archivos se regeneran a partir del código o se descargan de la fuente oficial.

Los reportes pequeños, figuras, manifiestos y tablas de resultados sí pueden mantenerse en Git para documentar la evolución metodológica.

---

# 11. Próximas etapas

El desarrollo previsto continúa con:

1. selección y calibración de la arquitectura predictiva;
2. estimación territorial futura;
3. cuantificación de incertidumbre;
4. clasificación de riesgo territorial;
5. escenario sin intervención;
6. escenario con intervención hipotética;
7. mapa interactivo;
8. recomendaciones preventivas;
9. reporte metodológico;
10. presentación ejecutiva.

---

# 12. Reproducibilidad

Una persona que clone el repositorio debe poder:

```text
1. instalar requirements.txt
2. descargar los seis ZIP oficiales
3. colocarlos en data/raw/
4. ejecutar los scripts en orden
5. reconstruir todos los resultados derivados
```

No se requiere edición manual de CSV o Excel en ninguna etapa del pipeline.

---

# 13. Nota sobre licencia y concurso

Este repositorio forma parte de una propuesta para el Hackathon del INE. Durante el desarrollo **no se incluye una licencia open source automática** hasta revisar las condiciones de cesión de derechos aplicables al concurso.

Se recomienda mantener el repositorio **privado durante la etapa de desarrollo** y revisar la modalidad de publicación antes de convertirlo en público.

---

## Equipo

**Nombre del equipo:** _pendiente de definir en el repositorio_

**Reto:** Predicción y escenarios de riesgo de abstención

**Hackathon:** Hackea la participación: Datos que construyen democracia · INE 2026
