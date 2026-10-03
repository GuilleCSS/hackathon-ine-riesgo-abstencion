# Análisis de Jayme: qué se intentó, qué se logró y qué no funcionó

Bitácora del trabajo sobre el repositorio del Hackathon INE 2026 (Reto 2), del 2 al
3 de octubre de 2026. Parte del pipeline y del dashboard que ya había construido el
equipo, y describe lo que se agregó, lo que se aprendió de los datos y lo que se
probó sin éxito.

## En un minuto

- **El proyecto ya corre en cualquier máquina** con Docker, y los datos se pueden
  descargar y reconstruir siguiendo el README. El pipeline completo reproduce los
  resultados del equipo (54,448 secciones en el mapa, mismos umbrales y escenarios).
- **El dashboard pasó de 1 a 3 páginas**: mapa de riesgo 2027 mejorado, datos por año
  2009–2024 y grupos de secciones.
- **Se documentaron todos los datos** (`reports/eda/DICCIONARIO_DE_DATOS.md`): campos,
  nulos, errores y rarezas de los archivos del INE y de las tablas derivadas.
- **El modelo del equipo sigue siendo el mejor.** Ni el clustering, ni XGBoost, ni
  variables espaciales lo superan de forma robusta en los dos años de prueba.
- **La variable que más prometió fue el calendario de elecciones locales
  concurrentes**: mejora mucho la predicción de 2021 (−0.65 pp de error), pero no la
  de 2024, así que por la regla del equipo no reemplaza al modelo actual.

---

## 1. Punto de partida

- Pipeline reproducible en `src/00`–`15`: auditoría de los Conteos Censales (CCPC)
  2009–2024, base maestra por sección y elección, backtests, selección de modelo,
  estimación 2027, semáforo, escenarios, sensibilidad y capa espacial.
- Modelo seleccionado por una regla fijada de antemano: `two_history_linear`, una
  regresión lineal con dos variables (abstención de la última elección del mismo tipo
  y de la elección federal más reciente).
- Dashboard de una página en Streamlit.
- Los datos (`data/`) no se versionan: en una copia nueva del repo no había forma de
  ver nada sin pedirle los archivos a quien corrió el pipeline.

## 2. Entorno reproducible (Docker)

**Qué se hizo**

- `Dockerfile` (Python 3.12) y `compose.yaml` que monta el proyecto en `/app`: el
  código y `data/` viven en el disco local, la imagen sólo trae las dependencias.
- `requirements.txt` ahora incluye `streamlit`, `pydeck` y `xgboost`.
- `use_container_width` (obsoleto en Streamlit) se cambió por `width="stretch"`.

**Verificación**: la imagen compila en ARM (Mac) con las versiones fijadas de
GeoPandas; los tres dashboards pasan pruebas automáticas (`AppTest`).

**Subido a GitHub**: commit `fda3c0d` ("Add Docker setup and dashboard dependencies").

## 3. Datos y reproducción del pipeline

**Fuentes descargadas** (documentadas en el README, sección "Obtención de datos",
commit `c408606`):

| Fuente | Archivos | Verificación |
|---|---|---|
| Conteos Censales (INE, datos abiertos) | 6 ZIP, ~290 MB | 54,872,712 renglones: idénticos a la auditoría del equipo |
| Marco Geográfico Seccional DIC-2025 (SIGE) | 32 ZIP, ~165 MB | 73,268 secciones: idénticas al reporte del equipo, estado por estado |

**Pipeline completo en Docker**: 16 etapas en ~9 minutos, sin errores.

**Reproducibilidad**: `reports/` se regenera con 64 archivos "modificados", pero al
compararlos columna por columna las diferencias son sólo rutas (Windows vs. Docker),
tiempos de ejecución, redondeo en el decimal 13–16 y el modelo HistGradientBoosting
(descartado), que cambia ligeramente por la versión de scikit-learn. Los resultados
finales (coeficientes, umbrales, semáforo, escenarios) son idénticos. Esos cambios se
descartaron con `git checkout -- reports/`.

## 4. Mejoras al dashboard

Todas son aditivas: si faltan los archivos nuevos, las páginas funcionan como antes.

**Mapa de riesgo 2027** (`dashboard/mapa.py`)

- **Capa gris** con las 73,268 secciones de la cartografía debajo del semáforo, para
  que "sin estimación" no se confunda con "sin territorio".
- **Cobertura predictiva**: 74.3% nacional (54,448 de 73,268); por estado y municipio.
  Baja California, por ejemplo, 64.1%.
- **Capa violeta** con las 9,087 secciones que tienen estimación pero más de 10% de
  registros sin información (NS): fuera del semáforo, con su nivel indicativo y su NS
  en el tooltip.

**Datos por año** (`dashboard/datos_anuales.py`, página nueva)

- Abstención y % NS por elección; secciones por rango de NS (las que el filtro de 10%
  deja fuera); cambios de secciones entre elecciones (nuevas, desaparecidas, cambio de
  municipio o tipo).
- **Mapa por año** con tres variables: abstención, NS y cambio contra la elección
  anterior del mismo tipo (azul = bajó, rojo = subió).
- Filtros por estado y por **tipo de elección** (intermedias / presidenciales).

**Grupos de secciones** (`dashboard/clustering/grupos.py`, página nueva): ver §7.1.

**Rendimiento y visualización**

- **Vista nacional híbrida**: las 3,902 secciones de más de 100 km² (5% de las
  secciones, 69% del territorio) se dibujan como polígono simplificado y las demás como
  punto. Elimina las "zonas blancas" del norte. La vista de puntos sigue disponible.
- **JSON compacto** (`CompactDeck` en `dashboard/comun.py`): pydeck mandaba el mapa al
  navegador con indentación; sin ella, la vista nacional bajó de 69 MB a 35 MB y la de
  un estado de 14 MB a 5 MB.
- Colores validados con la herramienta de accesibilidad (daltonismo y contraste).

## 5. Diccionario de datos y calidad

`reports/eda/DICCIONARIO_DE_DATOS.md`: los 16 campos de los CCPC, los campos de la
cartografía, las 95 columnas de la base maestra y las 41 de la tabla final 2027, con
significado, fórmula, nulos y rangos. Hallazgos principales:

- Los CSV del INE son internamente consistentes (`LN = SV + NV + NS` en todos los
  renglones, sin negativos ni duplicados).
- **NS es el problema de calidad dominante**: desde 2015, 9–13% de las secciones
  tienen más de 5% de registros sin información; 9,438 sección-elección son 100% NS.
- `DEF`/`DEL` vienen con un espacio en blanco (no vacíos) en 2009 y 2012.
- `FELECCION` cambia de formato: D/M/AAAA hasta 2021 y MM/DD/AAAA en 2024.
- Hay personas en lista nominal con más de 100 años (hasta 140).
- 4,431 secciones superan en 2024 los 3,000 electores que fija la ley.

## 6. Lo que se aprendió de los datos

- **Por qué hay secciones sin estimación (18,820)**: 67% por falta de información de
  participación (NS > 10% o 100% NS), 31% por ser secciones nuevas sin historia y 2% por
  cambiar de municipio o tipo.
- **Las zonas blancas del norte no son datos faltantes**: la cartografía cubre 98.8–100%
  de cada estado, pero ahí una sección promedia 75–134 km² (0.27 km² en la CDMX); como
  punto, una sección de 8,000 km² se ve igual que una de 5 cuadras.
- **Intermedias vs. presidenciales**: el tipo de elección mueve la abstención 8–18 pp
  (intermedias 48–56%, presidenciales 38–40%). Comparar años seguidos mezcla ese efecto
  con cambios reales; el modelo del equipo ya compara dentro del mismo tipo.
- **Tendencias**: en intermedias la abstención viene bajando (55.9% → 48.2%); en
  presidenciales subió en 2024. El cambio previo de una sección se correlaciona
  negativamente con el siguiente (−0.40): las secciones extremas tienden a regresar a
  su nivel (regresión a la media).

## 7. Experimentos de modelado

Carpeta independiente `src/clustering/`; resultados en `reports/clustering/`. Ninguno
modifica `selected_architecture.json` ni el modelo actual. Las fases 2 y 3 usan las
mismas ventanas, métricas, bootstrap por municipio y regla de selección que las etapas
07–09 del equipo (se importan de su código), y ninguna variable usa información
posterior a la elección que se predice.

### 7.1 Fase 1 · Grupos de secciones (clustering)

Las 41,136 secciones con historia completa y confiable se agruparon por su
comportamiento frente al promedio nacional (k-means, k = 5):

| Grupo | Secciones | Rasgo |
|---|---:|---|
| Abstención baja persistente | 6,874 | Votan 12–18 pp más que el promedio; mitad rurales |
| En el promedio | 15,941 | Estables; 81% urbanas |
| Abstención alta persistente | 8,664 | +9–10 pp siempre; 83% de las secciones agrupadas de Baja California |
| Mejorando | 4,219 | −15.7 pp de tendencia |
| Empeorando | 5,438 | +9.9 pp; muy presente en Sonora y Jalisco |

**Limitación**: la separación entre grupos es moderada (silhouette 0.26). Es una
tipología útil para segmentar, pero las secciones forman un continuo.

### 7.2 Fase 2 · Clustering, variables territoriales, Gradient Boosting y XGBoost

Error medio absoluto (pp) en los backtests:

| Modelo | 2021 | 2024 | Contra el actual |
|---|---:|---:|---|
| **Actual (`two_history_linear`)** | **7.69** | **4.36** | — |
| + secciones vecinas | 7.69 | 4.36 | Empate (mejor Top20) |
| + ajuste por grupo | 8.19 | 4.41 | Peor |
| Un modelo por grupo | 8.23 | 4.44 | Peor |
| Ridge con todo el contexto | 9.87 | 5.23 | Peor |
| HistGradientBoosting | 8.66 | 5.45 | Peor |
| XGBoost | 8.80 | 5.33 | Peor |
| XGBoost sobre el residuo del actual | 9.25 | 5.15 | Peor |

**Por qué**: el error está dominado por cambios de toda la elección (2021 bajó en casi
todo el país, 2024 subió). Los modelos con más variables arrastran más sesgo, y XGBoost
se apoyó en la clave de estado: memorizó cómo se movió cada estado en elecciones
pasadas, y eso no se repitió.

### 7.3 Fase 3 · Calendario de elecciones locales concurrentes

**Calendario** (`data/external/calendario_concurrente.csv`): para cada estado y
elección federal 2009–2027, si hubo elección local y gubernatura el mismo día. Se
extrajo con código de Wikipedia (cada fila cita su página) y cuadra con los conteos
de las elecciones federales:

| Año | Estados con elección local | Con gubernatura |
|---|---:|---:|
| 2009 | 11 | 6 |
| 2012 | 15 | 7 |
| 2015 | 16 | 9 |
| 2018 | 30 | 9 |
| 2021 | 32 | 15 |
| 2024 | 32 | 9 |
| 2027 | 32 | 17 |

**Resultados** (pp; IC95% de la diferencia contra el modelo actual):

| Modelo | 2021 | 2024 | Contra el actual 2021 | Contra el actual 2024 |
|---|---:|---:|---|---|
| **Actual** | **7.69** | **4.36** | — | — |
| + concurrencia + vecinos | 7.04 | 4.38 | **Mejor** [−1.02, −0.30] | Empate [−0.15, +0.20] |
| + concurrencia | 7.27 | 4.51 | Mejor [−0.80, −0.06] | Empate [−0.04, +0.33] |
| XGBoost + concurrencia, sin estado | 6.68 | 4.54 | **Mejor** [−1.43, −0.59] | Empate [−0.06, +0.42] |
| XGBoost + concurrencia | 6.66 | 4.90 | Mejor [−1.39, −0.67] | Peor [+0.34, +0.75] |

**Lectura**

- Es la primera variable que mejora de verdad: en 2021 todos los modelos con
  concurrencia bajan el error de forma significativa, y en XGBoost estas variables
  concentran 18–25% de la importancia.
- La razón de 2021: en 2015 (su historia) sólo 16 estados tuvieron elección local y en
  2021 los 32. El modelo aprende que los estados sin elección local en la historia
  tienden a bajar su abstención cuando sí la tienen.
- En 2024 no ayuda porque el calendario casi no cambió respecto a su historia (2018:
  30 estados con elección local; 2024: 32).
- **Para 2027 tampoco se espera mucho**: 2027 se compara con 2021 y en ambos años
  votan los 32 estados; sólo Aguascalientes y Quintana Roo agregan gubernatura. Por eso
  el modelo actual pierde poco por no usarla.
- Por la regla del equipo (minimax: el peor año decide), el modelo actual sigue ganando
  por muy poco frente a "concurrencia + vecinos" (cociente de error en el peor año 0.923
  contra 0.928). Si se usara el error promedio de ambos años, ganaría "concurrencia +
  vecinos". Cambiar la regla después de ver los resultados no sería válido; es una
  decisión para el equipo con esta evidencia.

## 8. Lo que no funcionó o costó trabajo

**Del modelado**

- El clustering, las variables de contexto, Gradient Boosting y XGBoost no superan al
  modelo lineal de dos historias. Más variables generaron más sesgo, no menos error.
- XGBoost con la clave de estado sobreajusta: aprende cómo se movió cada estado y falla
  cuando ese patrón cambia.
- Los grupos tienen fronteras difusas (silhouette 0.26).
- La concurrencia ayuda en un solo año de prueba; con sólo dos años es difícil
  separar un efecto real de la casualidad del calendario.

**De los datos**

- Sólo existe la cartografía DIC-2025: las secciones que cambiaron de clave no se
  pueden dibujar en años anteriores, y los vecinos y la densidad de 2015–2021 se
  calcularon con polígonos de 2025.
- El calendario de concurrencia viene de una fuente secundaria (Wikipedia) y falta
  validarlo contra el INE y los institutos locales.
- El semáforo heredado (rojo / verde) no se distingue bien con daltonismo rojo-verde;
  el texto del tooltip lo compensa, pero conviene revisarlo.

**Del proceso**

- Una instrucción se interpretó mal: "agregar CLAUDE.md" se tomó como agregarlo a git
  en vez de al `.gitignore`; se corrigió antes de subir nada.
- El caché de Streamlit sirvió datos viejos dos veces mientras el servidor estaba
  corriendo (columnas nuevas y un módulo actualizado). Se resolvió con llaves de caché
  que dependen de los datos y reiniciando el servicio.
- Un script de comparación de reportes ordenaba sólo una de las dos tablas y dio
  falsas alarmas; se corrigió antes de sacar conclusiones.
- Al agregar XGBoost, la reconstrucción de la imagen actualizó otras librerías
  (Streamlit 1.65, Altair 6). Las pruebas pasaron, pero conviene fijar versiones.
- La extensión del navegador se desconectó en algunas revisiones visuales; esas
  vistas se validaron sólo con pruebas automáticas.

## 9. Estado del repositorio

**Subido a GitHub**: Docker y dependencias (`fda3c0d`), README de obtención de datos
(`c408606`).

**Pendiente de commit** (todo funcional y probado):

| Archivo o carpeta | Contenido |
|---|---|
| `dashboard/app.py`, `mapa.py`, `comun.py`, `datos_anuales.py`, `clustering/grupos.py` | Dashboard de 3 páginas |
| `src/15_build_spatial_layer.py` | Escribe además la capa base para la capa gris |
| `src/clustering/` | Fases 1–3 y el calendario |
| `reports/clustering/`, `reports/eda/DICCIONARIO_DE_DATOS.md` | Reportes |
| `data/external/calendario_concurrente.csv` | Calendario (se versiona) |
| `requirements.txt`, `README.md`, `dashboard/README.md` | Dependencias y documentación |
| `analisis-jayme.md` | Este documento |

`CLAUDE.md` está en el `.gitignore` a propósito.

## 10. Siguientes pasos recomendados

1. **Validar el calendario de concurrencia** con el INE y los institutos locales y
   decidir con el equipo si "concurrencia + vecinos" merece entrar al modelo.
2. **Fijar versiones** en `requirements.txt` (Streamlit, Altair, scikit-learn) para que
   todo el equipo tenga exactamente el mismo entorno.
3. **Sustituir la cartografía provisional** por el Marco Geográfico Electoral
   2026–2027 cuando se publique, y volver a correr las etapas 14 y 15.
4. **Explorar datos sociodemográficos** del Censo 2020 por sección electoral, la otra
   fuente externa con potencial.
5. Revisar los colores del semáforo para daltonismo antes de la entrega final.
