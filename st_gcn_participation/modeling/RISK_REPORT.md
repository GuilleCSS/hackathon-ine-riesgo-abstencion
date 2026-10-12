# Riesgo territorial y escenarios de intervención

## Objetivo

Priorizar secciones donde podría aumentar la abstención electoral si no se interviene. Todo el flujo utiliza conteos y características agregadas por sección; no usa datos individuales ni personales.

## Modelo seleccionado para el semáforo

Se compararon Ridge y HistGradientBoosting con búsqueda temporal de hiperparámetros, junto con un MLP pequeño exploratorio y dos persistencias. La métrica principal es MAE por año, y cada elección pesa igual al resumir los resultados.

| Modelo | MAE medio temporal (pp) |
|---|---:|
| Persistencia misma familia | **7.08** |
| HistGradientBoosting ajustado | 10.70 |
| MLP pequeño CPU | 10.84 |
| Ridge ajustado | 11.18 |
| Persistencia elección reciente | 12.34 |

| Corte externo | Baseline misma familia | Ridge ajustado | HGB ajustado | MLP CPU |
|---:|---:|---:|---:|---:|
| 2015 | **8.11** | 20.22 | 23.26 | 20.60 |
| 2018 | **5.25** | 9.17 | 6.22 | 6.46 |
| 2021 | 10.00 | 7.91 | **7.22** | 9.26 |
| 2024 | **4.97** | 7.40 | 6.09 | 7.03 |

El modelo de riesgo elegido automáticamente es **persistencia de la misma familia electoral**: Ridge y HGB se entrenaron y ajustaron, pero no superaron el baseline en el promedio de los cortes externos. Por tanto, las variables sociodemográficas exploradas no se presentan como una mejora predictiva demostrada.

## Variables candidatas y búsqueda

Predictores de Ridge/HGB: abstención de la elección más reciente, abstención de la anterior de la misma familia, tamaño del total observado, abstención agregada de hombres y mujeres, tipo de sección, entidad y proporción de conteos de votos en filas cuyo campo `Población ind/afro` aparece marcado como `Mostrar`.

`poblacion_mostrar_share` es solo un proxy de la etiqueta del archivo; **no equivale a la proporción de población indígena/afro** ni debe interpretarse como identidad individual o causa de abstención.

- Ridge: búsqueda de `alpha` entre 0.01 y 10,000.
- HGB: búsqueda aleatoria de 12 combinaciones de iteraciones, hojas, tasa de aprendizaje, regularización y mínimo de muestras por hoja.
- Para cada evaluación externa, los hiperparámetros se eligen con años interiores anteriores al objetivo. 2015 no tiene fold interno; 2018 solo tiene uno. La poca profundidad temporal hace débil la sintonización temprana.
- Las evaluaciones externas usan objetivos 2015, 2018, 2021 y 2024; nunca se mezclan filas aleatoriamente entre pasado y futuro.

## Semáforo territorial

Unidad: sección identificada provisionalmente con nombre normalizado de entidad + número de sección. El pronóstico 2027 asume familia electoral intermedia.

- **BAJO:** hasta el percentil 50 del score base (`≤ 46.55%`).
- **MEDIO:** percentil 50–80 (`46.55–57.10%`).
- **ALTO:** por encima del percentil 80 (`> 57.10%`).
- **PRIORITARIO:** percentil 90 o superior (`≥ 62.63%`), bandera que complementa el semáforo.

Los cortes se congelan con el escenario base para poder observar cambios después de aplicar supuestos hipotéticos. Son categorías relativas dentro del universo, **no probabilidades ni umbrales universales**.

Resultado base: 72,599 secciones; abstención media estimada 46.20%; 14,520 (20%) en ALTO y 7,262 (~10%) prioritarias. Los cortes congelados son P50=46.55%, P80=57.10%, P90=62.63%. El CSV estatal resume cantidad de secciones y media predicha por nivel.

## Escenarios

| Escenario | Secciones alcanzadas | Cambio medio modelado | Secciones ALTO después |
|---|---:|---:|---:|
| Sin intervención | 0 | 0.00 pp | 14,520 |
| Hipotético: −2 pp en ALTO | 14,520 | −0.40 pp | 11,547 |
| Sensibilidad: −5 pp en PRIORITARIO Top 10% | 7,262 | −0.50 pp | 14,520 |

Las reducciones de 2 y 5 puntos porcentuales son entradas de sensibilidad, **no impactos estimados ni promesas causales**. El escenario de −2 pp mueve 2,973 secciones fuera de ALTO respecto a los cortes fijos; el de −5 pp mueve 3,935 fuera de la bandera PRIORITARIO.

## Acciones preventivas sugeridas

- **PRIORITARIO / Top 10%:** diagnóstico operativo local, módulos itinerantes donde el acceso sea difícil, horarios extendidos y comunicación accesible/multicanal; asignar primero recursos limitados y monitorear cobertura.
- **ALTO:** acercamiento comunitario e información cívica anticipada, revisión de accesibilidad y capacidad de instalación/traslado de casillas donde proceda.
- **MEDIO:** acciones preventivas de bajo costo y monitoreo de cambios respecto al mismo tipo de elección.
- **BAJO:** mantener monitoreo y prácticas existentes, evitando retirar cobertura básica.

Validar las acciones con equipos territoriales: un score histórico no identifica por sí solo la causa local ni garantiza que una intervención funcione. Para estimar impacto, probar un despliegue escalonado o comparación por grupos territoriales y medir cambios agregados, sin perfilar a personas.

## Uso para planeación

Usar el semáforo como lista inicial de priorización y cotejarlo con capacidad operativa, cobertura territorial y conocimiento local. El indicador `model_disagreement_pp` permite revisar zonas donde candidatos y persistencias divergen más. No se deben asignar recursos solo por una etiqueta: el backtest aún es corto y la identificación de secciones no cuenta con crosswalk oficial.

## Límites

- Los archivos no tienen lista nominal, ingresos, edad u otras covariables sociodemográficas completas; el target es abstención sobre `Sí votaron + No votaron`.
- No hay grafo espacial ni geometrías, por lo que no aplica ST-GCN con estos insumos.
- No hay crosswalk oficial de secciones altas/bajas/fusionadas; entidad + número es llave provisional.
- 2027 es una extrapolación, no existe un backtest de ese año; confirmar qué proceso electoral/territorial debe representar.
- Los escenarios no estiman efectos causales; para estimar impacto se necesitaría intervención real, diseño de evaluación y datos de implementación.

## Artefactos

- `outputs/tuned_backtest_metrics.csv`: evaluación temporal de candidatos y baselines.
- `outputs/hyperparameter_search.csv`: búsquedas por fold externo.
- `outputs/risk_2027_sections.csv`: score/semáforo por sección (generado localmente, excluido de Git por tamaño).
- `outputs/risk_2027_by_state.csv`: resumen estatal por nivel.
- `outputs/scenario_2027_summary.csv`: resultados nacionales de escenarios.
- `outputs/scenario_2027_by_state.csv`: resultados de escenario por entidad.
- `outputs/scenario_2027_sections.csv`: escenarios por sección (generado localmente, excluido de Git por tamaño).
- `models/*_2027.joblib`: estimadores clásicos y MLP ajustados; el score operativo sigue el baseline por misma familia.
- Ejecutar `python st_gcn_participation/modeling/risk_scenarios.py` desde la raíz del repositorio.
