# Catálogo de variables candidatas para predecir abstención

Fecha: 2026-10-07. Esta es una propuesta de variables; no cambia el modelo ni genera todavía una nueva matriz de entrenamiento.

## Evidencia revisada

- Diccionarios `01_descripcioncampos_conteoscensalesAAAA.txt` dentro de los seis ZIP originales en `data/raw/`, para 2009, 2012, 2015, 2018, 2021 y 2024.
- Encabezado real de `data/processed/section_election_master_v1.csv.gz` (95 columnas).
- `src/02_build_master.py`, `src/04_build_features.py`, `src/06_residual_preelection.py`, `src/07_dual_history_backtest.py` y manifiestos de variables.
- Esquema y documentación de la cartografía local.

Los diccionarios tienen caracteres de sustitución en algunos acentos; las claves de campo y sus definiciones se pueden leer. El diccionario 2024 agrega sexo no binario y usa el marco distrital DERFE 2023; los diccionarios anteriores hacen referencia a DERFE 2021. Los distritos necesitan revisión de comparabilidad y fecha del marco antes de utilizarse como información disponible históricamente.

## Convenciones y reglas

- Unidad principal: sección electoral × elección. Clave: entidad + sección. Municipio se identifica con entidad + municipio; los códigos solos no son nacionales.
- Los CSV originales contienen conteos agregados por territorio, sexo y edad. No hay identificador de casilla en estos campos.
- `LN`: registros de lista nominal en los cuadernillos catalogados; `SV`: con marca de voto; `NV`: sin marca; `NS`: participación no especificada. No se incluye participación en casillas especiales ni desde el extranjero según los diccionarios.
- `D = SV + NV`; participación `p = SV/D`; abstención `a = NV/D`. NS se trata por separado, no se suma a abstención.
- `t` es una elección histórica conocida antes de la fecha de predicción. Para 2027, `RECENT` corresponde a 2024 y `SAME` a 2021. Para cada backtest estos años se desplazan.
- E: existe en la base maestra o en un pipeline actual; M: nueva derivación a partir de la maestra; R: requiere volver a agregar el RAW; G: requiere cartografía; C: requiere otra fuente o una actualización preelectoral con fecha comprobable.
- Cada proporción usa su denominador explícito. Denominador cero produce faltante y bandera, no cero. Cada familia puede expandirse por sexo, grupo de edad y elección histórica cuando tenga sentido.
- Es un catálogo amplio de candidatos, no una instrucción de meter todos en el modelo. Su utilidad se decide después con validación temporal y comparación por bloques.

## 1. Campos originales y variables ya existentes

| Variable o familia | Estado | Definición / uso |
|---|---|---|
| Año y fecha electoral (`AELEC`, `FELECCION`) | RAW; año en maestra | Definir orden, familia electoral y cortes. La fecha no se conserva actualmente en maestra. |
| Entidad (`EDOCVE`) | E | Contexto categórico. Nombre como etiqueta, no otro predictor. |
| Municipio (`EDOCVE`, `MPIOCVE`) | E | Agrupación territorial; categoría de alta cardinalidad que exige manejo de municipios nuevos. |
| Sección (`EDOCVE`, `SECCION`) | E | Clave de unión e historial; evitar tratar número de sección como magnitud continua. |
| Distrito federal y local (`DEF`, `DEL`) | E | Contexto condicionado a la comparabilidad y disponibilidad histórica del marco. |
| Tipo de sección (`TIPOSEC`) | E | Urbana, rural o mixta; armonizar codificación con cartografía. |
| Familia de elección (`TIPO_ELECCION`) | E | Intermedia o presidencial. |
| Lista nominal total (`LN`) y `log1p(LN)` | E | Tamaño del electorado registrado. No equivale a población total ni a superficie. |
| Conteos históricos `SV`, `NV`, `NS` | E | Votantes, no votantes y registros no especificados. Solo elecciones pasadas. |
| Participación y abstención históricas | E | `SV/D`, `NV/D`; son complementarias y no es necesario duplicarlas todas. |
| Proporción NS (`PCT_NS_LN`) | E | `NS/LN`, indicador de calidad de observación. |
| Conteos por sexo | E | `LN`, `SV`, `NV` para hombres, mujeres y no binario. |
| Composición por sexo | E | `LN_sexo/LN`. La categoría NB aparece en 2024; ausencia histórica no equivale a cero real comparable. |
| Participación / abstención por sexo | E | `SV_sexo/(SV_sexo+NV_sexo)` y complemento. |
| Conteos por grupo de edad | E | `LN`, `SV`, `NV` para 18–24, 25–34, 35–44, 45–59, 60+. |
| Composición por grupo de edad | E | `LN_grupo/LN`. |
| Participación / abstención por grupo de edad | E | `SV_grupo/(SV_grupo+NV_grupo)` y complemento. |
| Edad media del electorado | E | `sum(edad*LN_edad)/LN`. |
| Edad media de votantes | E | `sum(edad*SV_edad)/SV`, solo histórica. |
| Brecha mujeres menos hombres | E | Participación femenina menos masculina, en puntos porcentuales. |
| Historia comparable previa y segunda previa | E | Columnas `PREV_*` y `PREV2_*`; verificar que sus fechas sean anteriores al objetivo. |
| Cambios de abstención y LN | E | Columnas `DELTA_*`, `TREND_*`; una columna calculada en el año objetivo no es predictor de ese objetivo. |
| Doble historia y sus diferencias | E | `SAME_*`, `RECENT_*`, diferencias de abstención, log LN, edad y composición. |

## 2. Tamaño electoral y peso dentro de territorios

Los agregados se calculan por año sobre la base completa disponible en ese año, antes de filtrar la cohorte predictiva; publicar también cobertura. No sumar la misma sección repetidamente por cruces de sexo y edad.

| Variable propuesta | Estado | Cálculo / significado |
|---|---|---|
| Lista nominal municipal, estatal y nacional | M | Suma de LN histórica en cada universo. |
| Lista nominal de distrito | M | Suma condicionada a marco distrital coherente. |
| Peso de sección en municipio | M | `LN_seccion/LN_municipio`. |
| Peso de sección en estado | M | `LN_seccion/LN_estado`. |
| Peso de sección en país | M | `LN_seccion/LN_pais`. |
| Peso de municipio en estado y país | M | `LN_municipio/LN_estado`, `LN_municipio/LN_pais`. |
| Peso de estado en país | M | `LN_estado/LN_pais`. |
| LN relativa al tamaño típico | M | LN / mediana municipal, estatal o de secciones del mismo tipo. |
| Percentil de tamaño de sección | M | Posición de LN dentro de municipio, estado o tipo de sección. |
| Número de secciones del municipio | M | Conteo único histórico; no es número de casillas. |
| Concentración del electorado municipal | M | Suma de cuadrados de pesos LN de las secciones (HHI) o peso de las mayores. |
| Crecimiento absoluto y relativo de LN | E/M | `LN_t-LN_anterior`; razón menos 1; distinguir reciente y misma familia. |
| Crecimiento anualizado de LN | M | `(LN_t/LN_anterior)^(1/años)-1`, con denominadores positivos. |
| Variabilidad histórica del tamaño | M | Desviación o coeficiente de variación de LN en historia disponible. |
| Crecimiento relativo al municipio / estado | M | Crecimiento de sección menos crecimiento agregado histórico. |

Estos pesos miden distribución del electorado observado. Por sí solos no implican mayor o menor abstención; su relación es una hipótesis para evaluar.

## 3. Composición por sexo y edad

| Variable propuesta | Estado | Cálculo / significado |
|---|---|---|
| Razón mujeres/hombres | M | `LN_M/LN_H`; manejar ausencia de hombres. Alternativa más estable: proporción femenina. |
| Diferencia de proporciones por sexo | M | `(LN_M-LN_H)/LN`; redundante con proporción femenina si solo hay dos categorías. |
| Cambios en composición sexual | M/E | Diferencias entre elecciones conocidas. |
| Proporción 18–29, 18–34, 65+, 75+ | R/M | 18–34 puede salir de maestra; cortes 18–29, 65+ y 75+ necesitan RAW. |
| Relación mayores/jóvenes | M | LN 60+ / LN 18–34. Describe electores, no dependencia demográfica total. |
| Edad media por sexo | R | Suma edad × LN por sexo dividida por LN del sexo. |
| Mediana y percentiles de edad | R | Cuantiles ponderados por LN de la distribución por edad. |
| Dispersión de edad | R | Varianza / desviación ponderada y rango intercuartílico. |
| Concentración o diversidad etaria | M | Suma de cuadrados de proporciones etarias o entropía de grupos. |
| Grupos etarios más numerosos | M | Grupo dominante y participación del grupo mayoritario. |
| Cambios de edad media y proporciones | E/M | Cambio reciente y de misma familia; anualizar cuando corresponda. |
| Distancia al perfil demográfico municipal | M | Diferencias de cada proporción respecto de su agregado municipal. |
| Distancia al perfil estatal / nacional | M | Igual definición a niveles superiores. |
| Distribución conjunta sexo × edad | R | LN por cada sexo y grupo etario / LN total. |
| Composición etaria dentro de cada sexo | R | LN sexo-edad / LN sexo. |
| Composición sexual dentro de cada edad | R | LN sexo-edad / LN edad. |

## 4. Participación histórica por grupos y brechas

| Variable propuesta | Estado | Cálculo / significado |
|---|---|---|
| Participación histórica sexo × edad | R | SV sexo-edad / (SV+NV) sexo-edad. |
| NS por sexo, edad y sexo × edad | R/M | Reagregar NS; totales marginales pueden recuperarse como LN-SV-NV tras validar balance. |
| Peso de cada grupo entre votantes | M/R | SV grupo / SV total; cruzados requieren RAW. |
| Peso de cada grupo entre abstencionistas | M/R | NV grupo / NV total. |
| Representación de grupos entre votantes | M/R | `(SV_grupo/SV_total)/(D_grupo/D_total)`, usando población de participación conocida. |
| Contribución de grupo a abstención total | M/R | `NV_grupo/D_total`; equivale a `a_grupo*(D_grupo/D_total)`. |
| Brecha joven–mayor | M | Participación 18–24 menos participación 60+, o corte alternativo consistente. |
| Brechas de cada edad frente al total | M | Participación grupo menos participación sección. |
| Máxima brecha entre edades | M | Máxima participación etaria menos mínima, con grupos de tamaño suficiente. |
| Brecha de sexo dentro de cada edad | R | Participación femenina menos masculina por grupo etario. |
| Edad votante menos edad del electorado | M | Diferencia de medias históricas. |
| Participación masculina/femenina relativa al municipio | M | Tasa sección-sexo menos tasa municipal-sexo histórica. |
| Participación etaria relativa al municipio / estado | M | Diferencia de tasas históricas del mismo grupo. |
| Cambios de tasas y brechas por grupo | M/R | Diferencias entre elecciones anteriores; cruces necesitan RAW. |
| Tasas históricas suavizadas | M/R | `(NV_g+k*a_referencia)/(D_g+k)` para reducir inestabilidad en grupos pequeños. k se elige usando solo entrenamiento. |

El denominador de contribuciones es D, no LN, para conservar la identidad con la abstención definida en el proyecto. Los conteos LN y el perfil completo se conservan aparte.

## 5. Historia, tendencia y dinámica

| Variable propuesta | Estado | Cálculo / significado |
|---|---|---|
| Últimas 1, 2 y 3 tasas federales disponibles | M/E | Rezagos reales por año; bandera cuando no hay historia suficiente. |
| Últimas tasas de la misma familia | E/M | Evitar mezclar un ciclo presidencial con uno intermedio sin indicarlo. |
| Cambio reciente y de misma familia | E/M | Diferencia en puntos porcentuales entre dos observaciones previas. |
| Pendiente histórica por año | M | Regresión descriptiva sobre años reales disponibles, por sección y familia; requiere al menos dos observaciones. |
| Aceleración o cambio de pendiente | M | Diferencia entre pendientes de dos intervalos anteriores; requiere tres observaciones. |
| Media / mediana / promedio reciente ponderado | M | Resumen de tasas pasadas; definir pesos antes de evaluar. |
| Mínimo, máximo y rango histórico | M | Resumen de tasas anteriores. |
| Volatilidad histórica | M | Desviación de tasas y/o de cambios previos; separar familias. |
| Tiempo desde última observación | M | Años entre fecha de predicción y elección fuente. |
| Distancia respecto a media histórica propia | M | Última tasa menos media de su historia anterior. |
| Persistencia de riesgo alto histórico | M | Número / proporción de elecciones previas por encima de cortes históricos definidos sin futuro. |
| Número de aumentos consecutivos | M | Racha de incrementos de abstención en observaciones conocidas. |
| Diferencia presidencial–intermedia de sección | M | Medias o pares de elecciones previas; controlar orden y tendencia. |
| Brecha de familia relativa a estado / país | M | Diferencia local menos diferencia agregada histórica. |
| Cambio local menos cambio municipal / estatal | M | Tendencia diferencial respecto del entorno. |

Hay seis elecciones: las variables de tercer rezago, aceleración y tendencia por familia tendrán cobertura limitada en los backtests tempranos. No se imputan con elecciones futuras.

## 6. Contexto municipal, estatal, distrital y nacional

| Variable propuesta | Estado | Cálculo / significado |
|---|---|---|
| Abstención territorial histórica | M | `sum(NV)/sum(SV+NV)`; no promedio simple de porcentajes. |
| Tasas por sexo y edad del territorio | M/R | Agregar numeradores y denominadores del grupo. |
| Perfil demográfico del territorio | M/R | Sumar LN por grupo / LN territorial. |
| Porcentaje de LN urbano, rural y mixto | M | Sumar LN por tipo de sección / LN territorial. |
| Tendencia y volatilidad territorial | M | Repetir resúmenes históricos a cada nivel. |
| Dispersión de abstención entre secciones | M | Desviación, cuantiles y rango intercuartílico del municipio; especificar ponderación. |
| Brecha sección–municipio / estado / país | M | Abstención histórica local menos agregado histórico. |
| Percentil histórico de riesgo territorial | M | Rango de la sección respecto a su municipio o estado. |
| Tasa del resto del municipio | M | `(NV_m-NV_s)/(D_m-D_s)`; faltante si no hay otras secciones. |
| Referencia jerárquica suavizada | M | Combinar tasas municipal y estatal según tamaño observado; ajuste solo con pasado. |
| Brecha respecto a secciones del mismo tipo | M | Comparar con urbana/rural/mixta dentro del municipio o estado. |
| Cambios del entorno frente al nacional | M | Cambio agregado local menos cambio nacional anterior. |

Un agregado de resultados de 2024 es válido para predecir 2027, pero NO para predecir 2024. Si se usa codificación territorial basada en el objetivo de entrenamiento, exige codificación fuera de pliegue y un diseño temporal coherente.

## 7. Participación esperada por composición

Estas variables desarrollan la idea de lo esperado según municipio/estado, tamaño y composición; no afirman que el tamaño determine una tasa.

1. Elegir referencia histórica municipal, estatal o nacional y una partición exhaustiva de grupos (edad o sexo × edad). No sumar a la vez márgenes de sexo y edad porque duplicaría personas.
2. Calcular `a_ref,g = NV_ref,g / D_ref,g`, con suavizado y referencia superior si el grupo es pequeño o falta.
3. Calcular `a_esperada = sum(w_seccion,g * a_ref,g)`.
4. Con pesos `w=D_g/D`, el resultado es un referente comparable para participación conocida histórica. Con `w=LN_g/LN`, es un referente basado en composición registral y supone que esa composición aproxima la del universo D; documentar el efecto de NS.

Variables candidatas:

- Abstención esperada por edad con referencia municipal, estatal y nacional (M).
- Abstención esperada por sexo con esas referencias (M).
- Abstención esperada por sexo × edad (R).
- Participación esperada, complemento de abstención esperada (M/R).
- Exceso histórico de abstención: observada menos esperada (M/R).
- Razón observada/esperada, con tratamiento de valores cercanos a cero (M/R).
- Cambio histórico del exceso observado (M/R).
- Diferencia entre referencia municipal y estatal esperada (M/R).
- Cambio esperado atribuible a composición: aplicar las mismas tasas de referencia a dos composiciones registrales conocidas y restar (M/R). Es una descomposición descriptiva, no causal.
- Conteo esperado de registros sin marca: `D_historico*a_esperada` (M/R).
- Conteo futuro aproximado: `LN_actualizada*a_predicha` (C). Solo tiene interpretación sobre LN bajo el supuesto de cobertura de participación; si D futuro no es conocido, no es un conteo exacto del objetivo NV del proyecto.

## 8. Cartografía y entorno espacial

| Variable propuesta | Estado | Condición |
|---|---|---|
| Área seccional km² | G | Proyección métrica adecuada; usar geometría vigente al corte. |
| Peso superficial sección / municipio / estado | G | Área / área del territorio, una medida distinta del peso LN. |
| Densidad de electores registrados | G | LN / km², no densidad de población total. |
| Centroides o puntos interiores, latitud y longitud | G | Revisar capacidad de generalización espacial. |
| Número de secciones vecinas | G | Matriz de contigüidad documentada. |
| Abstención histórica del vecindario | G | Agregar tasas de vecinos exclusivamente anteriores al objetivo. |
| Brecha respecto de vecinos | G | Abstención propia menos referencia espacial pasada. |
| Perfil etario / sexual del vecindario | G | Composición agregada histórica. |
| Concentración histórica de riesgo cercano | G | Proporción de vecinos históricamente altos. |
| Compacidad y fragmentación geométrica | G | Indicadores exploratorios, no medición directa de accesibilidad. |

La cartografía local es provisional de diciembre de 2025. No se debe asumir que su geometría o vecindario estaban disponibles en 2021/2024; un experimento retrospectivo con ese marco debe declararse y separarse de un backtest estricto.

## 9. Calidad y disponibilidad histórica

- LN y D de cada grupo, para valorar soporte de las tasas (E/M/R).
- Proporción NS total y por grupo (E/M/R).
- Banderas de denominador cero, grupo pequeño, tasa faltante y variable ausente (E/M/R).
- Diferencia de balance `LN-(SV+NV+NS)` y bandera de inconsistencia (M/R).
- Cantidad de elecciones disponibles hasta el corte, total y por familia (M).
- Antigüedad de la primera observación y años desde la última (M).
- Cambios de municipio, tipo y distrito entre observaciones anteriores (M).
- Cobertura histórica del territorio y de sus grupos, respecto de la fuente disponible (M/R).

Las columnas `n_years`, `n_mpios`, `n_types`, `N_INTERMEDIA`, `N_PRESIDENCIAL` y `STABLE_*_ALL_YEARS` existentes usan el conjunto de años completo. NO se usan tal cual en backtests antiguos: reconstruirlas con años disponibles al corte. Flags `PAIR_*`, `TGT_*` y elegibilidad que miran el objetivo son de auditoría/evaluación, no predictores.

## 10. Interacciones candidatas

Se pueden evaluar tipo × proporción joven; tipo × log LN; sexo × edad; brecha de sexo × composición; tendencia × volatilidad; cambio LN × cambio composición; abstención histórica × contexto municipal; exceso observado × cambio composición; desacuerdo entre historias × familia electoral.

Gradient Boosting puede aprender muchas interacciones sin columnas explícitas. Primero probar los componentes y agregar cruces seleccionados si aportan en validación; no multiplicar todas las columnas entre sí.

## 11. Variables que exigen fuentes adicionales

No aparecen en los CCPC revisados: escolaridad, ingreso, pobreza, marginación, empleo, lengua indígena, discapacidad, migración, conectividad, acceso a transporte, distancias a casillas y número/tipo de casillas. Requieren datos agregados externos, fecha de publicación y unión territorial verificable. No se infieren de LN o TIPOSEC. Proyección de nuevos electores, supervivencia o migración también exige supuestos/fuentes adicionales; sumar tres años a la edad media no representa renovación completa del electorado.

## 12. Variables excluidas para evitar fuga o duplicación

- SV, NV, NS, participación y abstención del año que se predice, incluidos sus agregados municipales/estatales: resultados futuros.
- Tasas por sexo/edad del año objetivo y cambios calculados usando ese resultado.
- Composición y LN del objetivo extraídas de CCPC posteriores a la elección sin demostrar una fuente preelectoral disponible. El experimento `06_residual_preelection.py` debe tratarse como condicionado a esa disponibilidad, no como prueba automática de disponibilidad real en 2027.
- Clasificación de riesgo, intervalos, escenarios o predicción del mismo modelo como sustitutos del objetivo. Una predicción auxiliar solo puede usarse con generación fuera de muestra coherente.
- Nombres y códigos duplicados, participación y abstención complementarias en todos los bloques, totales y todos sus componentes sin necesidad. La redundancia se controla por bloques y utilidad, no solo por correlación.
- Códigos territoriales interpretados como números continuos.
- Tasas de categorías sin observaciones inventadas como cero.

## 13. Bloques iniciales para una futura comparación

1. Referencia: las dos abstenciones históricas del modelo vigente.
2. Historia ampliada: rezagos, tendencias de misma familia, desacuerdo entre historias y volatilidad.
3. Composición y tamaño: log LN, crecimiento, edad media, proporciones etarias y sexuales, tipo de sección.
4. Comportamiento por grupos: tasas históricas etarias/sexuales, brechas y soporte D.
5. Contexto: tasas y tendencias municipales/estatales, peso electoral y brechas respecto del entorno.
6. Referentes esperados por composición y exceso histórico.
7. RAW ampliado: sexo × edad, cuantiles de edad y tasas suavizadas.
8. Espacial: solo con marco temporal defendible y documentación de cobertura.

Después se evaluará si cada bloque mejora MAE, RMSE, sesgo, recuperación Top10/Top20 y estabilidad territorial sobre los mismos universos y cortes temporales. Este catálogo no garantiza mejora por añadir variables ni selecciona todavía un algoritmo.
