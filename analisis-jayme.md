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

### 7.4 Auditoría del NS (registros sin información)

`src/auditoria_ns/01_auditar_ns.py`; reporte en `reports/auditoria_ns/AUDITORIA_NS.md`.
Se hizo porque el filtro NS ≤ 10% deja fuera una de cada siete secciones comparables
(9,199) y hacía falta saber si el NS distorsiona la abstención.

**Hallazgos:**

- **El NS viene de casillas completas, no de personas.** En las secciones con NS
  parcial, la proporción se amontona en 1/2 (41.9% de las secciones), 1/3 (22.2%) y
  1/4 (9.4%); si fuera uniforme, cada fracción tendría 4.2%. Dentro de cada sección,
  todas las edades y ambos sexos pierden la misma proporción (razón de 0.98 a 1.01).
- **No es aleatorio entre secciones.** Las secciones grandes tienen NS > 10% en
  17.2% de los casos, contra 7.5% de las chicas, y las de más abstención previa en
  13.4%, contra 9.2%. Pesan Chiapas, Sonora, Campeche y Tabasco. La repetición en la
  misma sección es moderada (1.4–1.5 veces más probable).
- **No esconde abstención.** Con NS entre 10% y 99.9%, la abstención medida queda
  +0.44 pp sobre la esperada en promedio: décimas de punto y en dirección contraria
  a la temida. La excepción es 2015, con hasta +3 pp.
- **El filtro sí sesga el semáforo.** De las secciones excluidas, 27.4% serían ALTO
  (contra 20%) y 15.6% Top10 (contra 10%).
- **Subir el umbral a 25% cambia poco el ranking.** Entran 1,683 secciones más y
  97.7% de las ALTO oficiales siguen en ALTO.

Queda como propuesta para el equipo: incluir las secciones con NS parcial marcadas
como estimación con menos registros, o subir el umbral a 25%. No se tocó el
universo `primary_clean10`.

### 7.5 Descomposición por edad y sexo

`src/descomposicion_edad/01_descomponer_edad.py`; reporte en
`reports/descomposicion_edad/DESCOMPOSICION_EDAD.md`. Usa los ZIP originales (edad
simple × sexo) y la base maestra (grupos de edad por sección).

- **Curva por edad estable en las seis elecciones.** El primer voto (18 años)
  participa más que los de 19 a 30. La abstención es máxima cerca de los 25 y
  mínima entre los 61 y 69, y sube de nuevo en edades avanzadas.
- **Kitagawa.** El envejecimiento explica −0.86 pp de los −7.78 pp de 2009 a 2021
  (intermedias) y −1.07 pp de los +2.41 pp de 2012 a 2024 (presidenciales). En
  presidenciales, el comportamiento empeoró +3.48 pp. De 2018 a 2024 subió la
  abstención en todos los grupos salvo 60+, y la brecha entre 18–24 y 60+ llegó a
  21 pp.
- **Sexo.** Los hombres se abstienen 7–9 pp más que las mujeres en todas las
  elecciones, hasta 14 pp entre los 25 y los 40 años. La brecha se invierte después
  de los 70.
- **Territorio.** La estructura de edad casi no explica las diferencias entre
  secciones (R² 0.04–0.14). Entre ALTO y BAJO 2027 explica 1.3 de 26.7 pp. Las
  entidades con más abstención de la esperada por su edad son Baja California
  (+12.5 pp), Sonora y Chihuahua; las de menos, Yucatán (−11.8 pp), Tlaxcala y
  Ciudad de México.

- **Salto a los 65 años.** La abstención cae −2.5 pp justo a los 65 en 2024 y
  −1.2 pp en 2021; antes, el salto era de −0.9 pp como mucho. Aparece en hombres,
  mujeres y en todo tipo de sección. Coincide con la edad de acceso a la pensión
  universal para adultos mayores, que según la prensa se paga desde los 65 años a
  partir de julio de 2021. Es una asociación por verificar con fuentes oficiales.

**Implicación:** la edad no aporta al modelo territorial, pero sí sirve para
explicar los cambios nacionales y para focalizar mensajes en hombres de 19 a 34
años.

### 7.6 Brecha intermedia vs. presidencial

`src/brecha_tipo/01_brecha_intermedia_presidencial.py`; reporte en
`reports/brecha_tipo/BRECHA_TIPO.md`. Brecha = abstención en la intermedia menos la
de la presidencial contigua, por sección. Sólo se usan pares con NS ≤ 10%.

- **Se cerró a menos de la mitad.** Pasó de +18.0 pp (2009–2012) a +7.8 pp
  (2021–2024). La mediana por sección bajó de 18.1 a 7.2 pp, y las secciones con
  brecha negativa subieron de 1.5% a 20.2%.
- **Por tipo de sección (2021–2024):** urbanas +9.8 pp, mixtas +5.7 pp, rurales
  +1.7 pp.
- **Por abstención previa:** es mayor donde ya se abstienen más (mediana +11.9 pp
  en el quintil de más abstención 2021, contra −0.7 pp en el de menos).
- **Poco persistente.** La correlación de Spearman entre la brecha 2015–2018 y la
  2021–2024 de la misma sección es 0.33.
- **Calendario local.** En el MCO por entidad y par con efectos fijos de par,
  elecciones locales el mismo día que la intermedia restan −10.4 pp
  (IC 90% −13.7 a −7.5) y una gubernatura −5.5 pp más. Entre 2009 y 2021 las
  locales concurrentes pasaron de 11 a 32 entidades; eso explicaría ~64% del
  cierre. El calendario está pendiente de validar.
- **2027.** Las secciones ALTO tienen la mayor brecha. Habrá 17 gubernaturas
  concurrentes; Aguascalientes y Quintana Roo no la tuvieron en 2021.

**Siguiente paso posible:** probar la concurrencia de 2027 como ajuste del modelo
(la fase 3 ya mostró ganancia en 2021).

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

- El caché de Streamlit sirvió datos viejos dos veces mientras el servidor estaba
  corriendo (columnas nuevas y un módulo actualizado). Se resolvió con llaves de caché
  que dependen de los datos y reiniciando el servicio.
- Un script de comparación de reportes ordenaba sólo una de las dos tablas y dio
  falsas alarmas; se corrigió antes de sacar conclusiones.
- Al agregar XGBoost, la reconstrucción de la imagen actualizó otras librerías
  (Streamlit 1.65, Altair 6). Las pruebas pasaron, pero conviene fijar versiones.

## 9. Estado del repositorio

Todo lo de este documento ya está en `main`: Docker, dashboard, clustering (fases 1–3),
calendario de concurrencia, diccionario de datos y reportes. `data/` no se versiona;
se reconstruye con los comandos del README.

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
