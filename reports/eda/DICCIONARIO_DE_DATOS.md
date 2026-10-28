# Diccionario de datos y perfil de calidad

Generado el 2026-10-02 a partir de los archivos originales del INE y de las salidas del pipeline. Describe qué significa cada campo, cómo se calcula y qué tan completo y consistente es: nulos, valores fuera de rango, inconsistencias y rarezas detectadas.

**Contenido**

1. [Fuentes originales](#1-fuentes-originales)
   - [Conteos Censales de Participación Ciudadana (CCPC)](#11-conteos-censales-de-participación-ciudadana-ccpc)
   - [Marco Geográfico Seccional (cartografía)](#12-marco-geográfico-seccional-cartografía)
2. [Base maestra sección × elección](#2-base-maestra-sección--elección)
3. [Tabla final 2027](#3-tabla-final-2027)
4. [Glosario](#4-glosario)

Convenciones: los conteos usan coma de miles; *pp* = puntos porcentuales; las tasas se guardan como proporción (0–1) y aquí se muestran en %. "Nulos" son celdas vacías; "errores" son valores presentes pero imposibles o inconsistentes.

## Hallazgos principales

1. **Los CSV del INE son internamente consistentes:** sin conteos negativos, sin renglones duplicados y con `LN = SV + NV + NS` en los 54.9 millones de renglones.
2. **`NS` es el problema de calidad dominante.** Desde 2015, entre 8.8% y 12.7% de las secciones tienen más de 5% de registros sin información (en 2012, 0.4%), y 9,438 sección-elección son 100% NS (sin abstención calculable).
3. **`DEF`/`DEL` vienen en blanco** en 2009 y 2012 (con un espacio, no vacíos) en secciones que ya no existen en 2021, y `DEL` falta en 136 secciones de 2024.
4. **`FELECCION` cambia de formato:** D/M/AAAA en 2009–2021 y MM/DD/AAAA en 2024.
5. **Edades implausibles:** hay personas en lista nominal con más de 100 años (hasta 140), entre 10 mil y 34 mil por elección.
6. **Tamaño de sección fuera de norma:** miles de secciones superan los 3,000 electores que fija la ley (4,431 en 2024; la mayor tiene 40,865).
7. **La cartografía DIC-2025 está limpia** (73,268 polígonos, sin duplicados ni geometrías inválidas), pero usa códigos numéricos de tipo de sección distintos a los CCPC.
8. **Detalles de la base derivada:** `N_INTERMEDIA`/`N_PRESIDENCIAL` usan nulo en vez de 0, y la tabla final 2027 arrastra columnas duplicadas del cruce entre años (`AELEC_x`, `AELEC_y`).

## 1. Fuentes originales

### 1.1 Conteos Censales de Participación Ciudadana (CCPC)

- **Fuente:** INE, datos abiertos: <https://ine.mx/transparencia/datos-abiertos/visualizacion-datos/conteos-censales-participacion/>
- **Archivos:** `data/raw/DatosAbiertos_DECEyEC_ConteosCensales{AÑO}.zip`, uno por elección federal. Cada ZIP trae 32 CSV (uno por estado, UTF-8 con BOM, separados por coma) y un `01_descripcioncampos_conteoscensales{AÑO}.txt` con el diccionario oficial.
- **Unidad de registro:** un renglón = **sección × sexo × edad** en una elección. Por eso son ~9 millones de renglones por año aunque solo haya ~70 mil secciones.
- **Cobertura (según el INE):** cuenta a las personas de los cuadernillos de la lista nominal de las casillas aprobadas. No incluye a quienes votaron en casillas especiales ni a residentes en el extranjero. La sección es la del domicilio de la credencial, por lo que las cifras pueden diferir de los cómputos distritales.

#### Resumen por año

| Año | CSV | Renglones | Secciones | Municipios | Lista nominal | FELECCION | Encabezado idéntico |
|---|---|---|---|---|---|---|---|
| 2009 | 32 | 8,706,843 | 64,934 | 2,458 | 77,481,831 | 5/7/2009 | sí |
| 2012 | 32 | 8,604,456 | 65,599 | 2,455 | 76,490,962 | 1/7/2012 | sí |
| 2015 | 32 | 9,106,059 | 68,362 | 2,458 | 83,563,462 | 7/6/2015 | sí |
| 2018 | 32 | 9,251,122 | 68,408 | 2,463 | 89,123,997 | 1/7/2018 | sí |
| 2021 | 32 | 9,430,502 | 68,812 | 2,468 | 93,532,133 | 6/6/2021 | sí |
| 2024 | 32 | 9,773,730 | 70,751 | 2,477 | 98,330,348 | 06/02/2024 | sí |

Total: **54,872,712 renglones** en 192 CSV.

#### Campos

| Campo | Tipo | Significado | Rango / valores | Nulos o en blanco |
|---|---|---|---|---|
| `AELEC` | entero | Año de la elección. | 2009 – 2024 | 0 |
| `FELECCION` | texto | Fecha de la jornada electoral. El formato cambia: D/M/AAAA en 2009–2021 (`5/7/2009` = 5 de julio) y MM/DD/AAAA en 2024 (`06/02/2024` = 2 de junio). | una por año | 0 |
| `EDOCVE` | entero | Clave INE del estado. | 1 – 32 | 0 |
| `EDONOM` | texto | Nombre del estado. La Ciudad de México aparece como DISTRITO FEDERAL antes de 2015. | 32 nombres por año | 0 |
| `MPIOCVE` | entero | Clave INE del municipio, única dentro de cada estado. | 1 – 570 | 0 |
| `MPIONOM` | texto | Nombre del municipio. | 2,455–2,477 municipios por año | 0 |
| `SECCION` | entero | Número de sección electoral en ese año, único dentro de cada estado. La clave de sección del proyecto es `EDOCVE-SECCION`. | 1 – 9,004 | 0 |
| `TIPOSEC` | texto | Tipo de sección en ese año: U urbana, M mixta, R rural. | U, M, R | 0 |
| `DEF` | entero | Distrito electoral federal. Marco cartográfico DERFE 2021 (2009–2021) y DERFE 2023 (2024). | 1 – 41 | 44,154 (2009: 28,477; 2012: 15,677) |
| `DEL` | entero | Distrito electoral local. Mismo marco que DEF. | 1 – 45 | 65,066 (2009: 28,477; 2012: 15,677; 2024: 20,912) |
| `SEXO` | entero | Sexo: 0 hombres, 1 mujeres; 2 no binario (solo 2024). | 0 – 2 | 0 |
| `EDAD` | entero | Años cumplidos el día de la elección. | 18 – 140 | 0 |
| `LN` | entero | Lista nominal: personas registradas en los cuadernillos de las casillas catalogadas para esa sección, sexo y edad. | 1 – 982 | 0 |
| `SV` | entero | Registros **con** marca de voto (sí votaron). | 0 – 424 | 0 |
| `NV` | entero | Registros **sin** marca de voto (no votaron). | 0 – 603 | 0 |
| `NS` | entero | Registros sin información de participación: cuadernillo sin marcas de votación, no disponible para captura, solicitado por autoridad jurisdiccional (hasta 2021) o página faltante. No se sabe si esas personas votaron. | 0 – 259 | 0 |

En 2009 y 2012, `DEF` y `DEL` no vienen vacíos sino con un espacio (`' '`). Para el análisis equivalen a nulo, pero quien lea los CSV sin limpiar espacios los verá como texto en un campo numérico.

#### Cambios de definición entre años

- **2024** agrega `SEXO = 2` (no binario).
- **2024** usa el marco cartográfico DERFE 2023 para `DEF` y `DEL`; 2009–2021 usan el de 2021.
- **2024** ya no lista "cuadernillo solicitado por autoridad jurisdiccional" como causa de `NS`.
- **2024** cambia el formato de `FELECCION` de D/M/AAAA a MM/DD/AAAA.

#### Calidad por año

Cada fila cuenta **renglones** (sección × sexo × edad) salvo donde dice *secciones*.

| Revisión | 2009 | 2012 | 2015 | 2018 | 2021 | 2024 |
|---|---|---|---|---|---|---|
| `DEF` vacío o en blanco | 28,477 | 15,677 | 0 | 0 | 0 | 0 |
| `DEL` vacío o en blanco | 28,477 | 15,677 | 0 | 0 | 0 | 20,912 |
| Texto en otros campos numéricos | 0 | 0 | 0 | 0 | 0 | 0 |
| Conteos negativos (`LN`, `SV`, `NV`, `NS`) | 0 | 0 | 0 | 0 | 0 | 0 |
| `LN` ≠ `SV + NV + NS` (balance) | 0 | 0 | 0 | 0 | 0 | 0 |
| Renglones duplicados (misma sección, sexo y edad) | 0 | 0 | 0 | 0 | 0 | 0 |
| Renglones con `LN = 0` | 0 | 0 | 0 | 0 | 0 | 0 |
| Renglones con `SV + NV = 0` (todo NS) | 142,141 | 9,839 | 309,186 | 363,901 | 246,681 | 323,984 |
| Renglones con `EDAD > 100` | 32,761 | 10,318 | 12,123 | 10,320 | 13,216 | 12,891 |
| Renglones con `EDAD > 110` | 1,663 | 402 | 359 | 304 | 376 | 227 |
| Personas en lista nominal con `EDAD > 100` | 34,028 | 10,522 | 12,345 | 10,468 | 13,530 | 13,197 |
| *Secciones* con más de un municipio en el año | 0 | 0 | 0 | 0 | 0 | 0 |
| *Secciones* con más de un tipo en el año | 0 | 0 | 0 | 0 | 0 | 0 |
| *Secciones* con más de un distrito federal en el año | 0 | 0 | 0 | 0 | 0 | 0 |
| Estados con más de un nombre en el año | 0 | 0 | 0 | 0 | 0 | 0 |
| Municipios con más de un nombre en el año | 0 | 0 | 0 | 0 | 0 | 0 |

Distribución de `SEXO` y `TIPOSEC` (renglones):

| Año | SEXO 0 | SEXO 1 | SEXO 2 | U | M | R | Otro tipo |
|---|---|---|---|---|---|---|---|
| 2009 | 4,319,232 | 4,387,611 | 0 | 5,415,966 | 802,990 | 2,487,887 | 0 |
| 2012 | 4,261,802 | 4,342,654 | 0 | 5,449,108 | 822,843 | 2,332,505 | 0 |
| 2015 | 4,505,049 | 4,601,010 | 0 | 5,827,491 | 865,402 | 2,413,166 | 0 |
| 2018 | 4,572,091 | 4,679,031 | 0 | 5,920,841 | 899,994 | 2,430,287 | 0 |
| 2021 | 4,652,658 | 4,777,844 | 0 | 6,074,241 | 919,109 | 2,437,152 | 0 |
| 2024 | 4,817,367 | 4,956,258 | 105 | 6,368,734 | 921,814 | 2,483,182 | 0 |

**Lectura de los hallazgos**

- Fuera de `DEF` y `DEL` no hay celdas vacías ni texto en campos numéricos, y no hay conteos negativos, renglones duplicados ni descuadres entre `LN` y `SV + NV + NS`: los archivos son internamente consistentes.
- `DEF`/`DEL` vacíos en 2009: 318 secciones; el 100% de ellas ya no existe en 2021. Como esos años usan el marco de distritos 2021, lo más probable es que sean secciones sin equivalente en ese marco.
- `DEF`/`DEL` vacíos en 2012: 221 secciones; el 100% de ellas ya no existe en 2021. Como esos años usan el marco de distritos 2021, lo más probable es que sean secciones sin equivalente en ese marco.
- `DEL` vacío en 2024: 136 secciones repartidas en 32 estados: JALISCO (19), MEXICO (15), PUEBLA (10), NUEVO LEON (9), SONORA (8), BAJA CALIFORNIA (8), HIDALGO (6), QUERETARO (6), QUINTANA ROO (5), VERACRUZ (5), GUANAJUATO (5), AGUASCALIENTES (4), COLIMA (3), MICHOACAN (3), OAXACA (3), YUCATAN (3), SINALOA (3), TAMAULIPAS (2), DURANGO (2), COAHUILA (2), CHIHUAHUA (2), CHIAPAS (2), SAN LUIS POTOSI (2), TABASCO (1), TLAXCALA (1), MORELOS (1), NAYARIT (1), GUERRERO (1), CIUDAD DE MEXICO (1), CAMPECHE (1), BAJA CALIFORNIA SUR (1), ZACATECAS (1).
- Hay edades de hasta 140 años. Son pocas personas (ver tabla), pero probablemente son registros del padrón sin depurar, no personas reales de esa edad. No afectan las tasas de forma visible.
- Los renglones con `SV + NV = 0` son combinaciones sección × sexo × edad donde todo es NS; al agregar por sección, algunas secciones quedan completas en NS (ver `FLAG_DENOM_ZERO` en la base maestra).

### 1.2 Marco Geográfico Seccional (cartografía)

- **Fuente:** SIGE del INE (<https://cartografia.ine.mx/sige8/>), Marco Geográfico Seccional en Shapefile, corte 15-DIC-2025. El MGE 2026–2027 ya fue aprobado por el INE, pero el SIGE anuncia la publicación de sus productos descargables para el 12-NOV-2026, después del cierre del Hackathon; el pipeline queda preparado para actualizar la cartografía cuando estén disponibles.
- **Archivos:** `data/raw/cartography_2027/mgs_{N}_Shapefile.zip`, 32 ZIP (uno por estado). Cada uno trae las capas `DISTRITO_FEDERAL.shp`, `DISTRITO_LOCAL.shp`, `ENTIDAD.shp`, `MUNICIPIO.shp`, `SECCION.shp`; el pipeline solo usa `SECCION.shp`.
- **Unidad de registro:** un polígono por sección vigente en el corte.

| Campo | Tipo | Significado | Nulos |
|---|---|---|---|
| `id` | float64 | Identificador del polígono dentro de la capa del estado. | 0 |
| `entidad` | int64 | Clave INE del estado (= `EDOCVE`). | 0 |
| `distrito_f` | int64 | Distrito electoral federal vigente en el corte. | 0 |
| `distrito_l` | int64 | Distrito electoral local vigente en el corte. | 0 |
| `municipio` | int64 | Clave INE del municipio (= `MPIOCVE`). | 0 |
| `seccion` | int64 | Número de sección (= `SECCION`). | 0 |
| `tipo` | int64 | Tipo de sección con códigos numéricos. El pipeline auditó la equivalencia 2 → U, 3 → M, 4 → R comparando con los CCPC. | 0 |
| `control` | float64 | Campo interno del INE sin documentación en el ZIP; el pipeline no lo usa. | 0 |
| `geometry` | polígono | Contorno de la sección. | 0 |

| Revisión | Valor |
|---|---|
| Secciones (polígonos) | 73,268 |
| Claves `entidad-seccion` únicas | 73,268 |
| Claves duplicadas | 0 |
| Geometrías inválidas | 0 |
| Tipos de geometría | Polygon: 73,161, MultiPolygon: 107 |
| Valores de `tipo` | 2: 47,806, 3: 6,582, 4: 18,880 |
| Sistemas de coordenadas | EPSG:32611 (1 estado), EPSG:32612 (2 estados), EPSG:32613 (8 estados), EPSG:32614 (16 estados), EPSG:32615 (3 estados), EPSG:32616 (2 estados); el pipeline reproyecta todo a EPSG:4326 |

## 2. Base maestra sección × elección

- **Archivo:** `data/processed/section_election_master_v1.csv.gz` (lo genera `src/02_build_master.py`).
- **Tamaño:** 406,866 filas × 95 columnas; una fila por **sección y elección**. Suma los renglones sección × sexo × edad de los CCPC y agrega tasas, grupos, historia y banderas de calidad.
- **Filas por año:** 2009: 64,934, 2012: 65,599, 2015: 68,362, 2018: 68,408, 2021: 68,812, 2024: 70,751.

#### Integridad

| Revisión | Resultado |
|---|---|
| Filas duplicadas (misma elección y sección) | 0 |
| `LN` ≠ `SV + NV + NS` | 0 |
| `LN` ≠ suma por sexo (`LN_H + LN_M + LN_NB`) | 0 |
| `LN` ≠ suma por grupos de edad | 0 |
| Tasas o proporciones fuera de 0–1 | ninguna |
| Secciones con `SV + NV = 0` vs. nulos en `PCT_ABSTENCION` | 9,438 vs. 9,438 (coinciden) |
| Edad promedio de la lista nominal (mín – máx) | 23.2 – 80.0 años |
| Secciones con edad promedio > 70 años | 1 |
| Secciones con `LN` > 3,000 (por año) | 2009: 1,906, 2012: 2,244, 2015: 2,962, 2018: 3,693, 2021: 4,081, 2024: 4,431 |
| Secciones con `LN` < 100 (por año) | 2009: 565, 2012: 691, 2015: 631, 2018: 675, 2021: 212, 2024: 68 |
| No binario 2024 (LN / SV / NV) | 105 / 79 / 23 en 105 secciones |

La ley fija entre 100 y 3,000 electores por sección. Las secciones fuera de ese rango son candidatas naturales a reseccionamiento, que es una de las causas de secciones nuevas o desaparecidas entre elecciones.

#### Columnas

"Valores" muestra mínimo · mediana · máximo en columnas numéricas.

**Identificación**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `AELEC` | entero | Año de la elección. | 0 | 2009 · 2018 · 2024 |
| `TIPO_ELECCION` | texto | `intermedia` (2009, 2015, 2021) o `presidencial` (2012, 2018, 2024). | 0 | 2 distintos; más frecuentes: presidencial (204,758), intermedia (202,108) |
| `EDOCVE` | entero | Clave INE del estado. | 0 | 1 · 15 · 32 |
| `EDONOM` | texto | Nombre del estado. | 0 | 33 distintos; más frecuentes: MEXICO (38,710), VERACRUZ (28,955), SINALOA (22,492) |
| `MPIOCVE` | entero | Clave del municipio en ese año. | 0 | 1 · 30 · 570 |
| `MPIONOM` | texto | Nombre del municipio en ese año. | 0 | 2,403 distintos; más frecuentes: Juárez (7,690), Tijuana (6,182), Iztapalapa (6,018) |
| `SECCION` | entero | Número de sección en ese año. | 0 | 1 · 1,234 · 9,004 |
| `SECTION_KEY` | texto | Clave única de sección del proyecto: `EE-SSSS` (estado a 2 dígitos, sección a 4). | 0 | 72,681 distintos; más frecuentes: 01-0001 (6), 20-1303 (6), 20-1305 (6) |
| `TIPOSEC` | texto | Tipo de sección en ese año (U, M, R). | 0 | 3 distintos; más frecuentes: U (256,134), R (113,911), M (36,821) |
| `DEF` | entero | Distrito electoral federal (marco DERFE 2021; 2024: DERFE 2023). | 539 (0.1%) | 1 · 5 · 41 |
| `DEL` | entero | Distrito electoral local (mismo marco). | 675 (0.2%) | 1 · 12 · 45 |

**Conteos totales**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `LN` | entero | Lista nominal de la sección. | 0 | 1 · 1,043 · 40,865 |
| `SV` | entero | Personas que votaron. | 0 | 0 · 538 · 16,789 |
| `NV` | entero | Personas que no votaron. | 0 | 0 · 413 · 22,608 |
| `NS` | entero | Personas sin información de participación. | 0 | 0 · 0 · 12,833 |
| `AGE_LN_SUM` | entero | Auxiliar: suma de `EDAD × LN`; sirve para calcular la edad promedio. | 0 | 39 · 45,182 · 1,429,053 |
| `AGE_SV_SUM` | entero | Auxiliar: suma de `EDAD × SV`. | 0 | 0 · 24,284 · 585,756 |

**Tasas totales y edad promedio**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `PCT_PARTICIPACION` | decimal | Participación = `SV / (SV + NV)`. NS queda fuera del denominador. | 9,438 (2.3%) | 0.0% · 56.6% · 100.0% |
| `PCT_ABSTENCION` | decimal | Abstención = `NV / (SV + NV)`. Es la variable que modela el proyecto. | 9,438 (2.3%) | 0.0% · 43.4% · 100.0% |
| `PCT_NS_LN` | decimal | Proporción sin información = `NS / LN`. Indicador de calidad. | 0 | 0.0% · 0.0% · 100.0% |
| `EDAD_PROM_LN` | decimal | Edad promedio de la lista nominal = `AGE_LN_SUM / LN`. | 0 | 23.2 · 42.8 · 80.0 |
| `EDAD_PROM_VOTANTES` | decimal | Edad promedio de quienes votaron = `AGE_SV_SUM / SV`. | 9,528 (2.3%) | 18.0 · 44.8 · 75.0 |

**Por sexo**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `LN_H` | entero | Lista nominal de hombres. | 0 | 0 · 500 · 22,210 |
| `SV_H` | entero | Votaron: hombres. | 0 | 0 · 238 · 8,622 |
| `NV_H` | entero | No votaron: hombres. | 0 | 0 · 219 · 12,783 |
| `LN_M` | entero | Lista nominal de mujeres. | 0 | 0 · 542 · 22,085 |
| `SV_M` | entero | Votaron: mujeres. | 0 | 0 · 299 · 9,047 |
| `NV_M` | entero | No votaron: mujeres. | 0 | 0 · 194 · 9,825 |
| `LN_NB` | entero | Lista nominal de personas no binarias. | 0 | 0 · 0 · 1 |
| `SV_NB` | entero | Votaron: personas no binarias. | 0 | 0 · 0 · 1 |
| `NV_NB` | entero | No votaron: personas no binarias. | 0 | 0 · 0 · 1 |
| `PCT_PART_H` | decimal | Participación de hombres = `SV_H / (SV_H + NV_H)`. | 9,467 (2.3%) | 0.0% · 52.3% · 100.0% |
| `PCT_ABST_H` | decimal | Abstención de hombres = `NV_H / (SV_H + NV_H)`. | 9,467 (2.3%) | 0.0% · 47.7% · 100.0% |
| `PROP_LN_H` | decimal | Peso de hombres en la lista nominal = `LN_H / LN`. | 0 | 0.0% · 48.2% · 100.0% |
| `PCT_PART_M` | decimal | Participación de mujeres = `SV_M / (SV_M + NV_M)`. | 9,493 (2.3%) | 0.0% · 60.6% · 100.0% |
| `PCT_ABST_M` | decimal | Abstención de mujeres = `NV_M / (SV_M + NV_M)`. | 9,493 (2.3%) | 0.0% · 39.4% · 100.0% |
| `PROP_LN_M` | decimal | Peso de mujeres en la lista nominal = `LN_M / LN`. | 0 | 0.0% · 51.8% · 100.0% |
| `PCT_PART_NB` | decimal | Participación de personas no binarias = `SV_NB / (SV_NB + NV_NB)`. | 406,764 (100.0%) | 0.0% · 100.0% · 100.0% |
| `PCT_ABST_NB` | decimal | Abstención de personas no binarias = `NV_NB / (SV_NB + NV_NB)`. | 406,764 (100.0%) | 0.0% · 0.0% · 100.0% |
| `PROP_LN_NB` | decimal | Peso de personas no binarias en la lista nominal = `LN_NB / LN`. | 0 | 0.0% · 0.0% · 0.6% |
| `BRECHA_PART_MENOS_H` | decimal | Participación de mujeres menos participación de hombres (`PCT_PART_M − PCT_PART_H`). Positivo = votan más las mujeres. | 9,522 (2.3%) | -100.0 pp · +7.4 pp · +100.0 pp |

**Por grupo de edad**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `LN_18_24` | entero | Lista nominal de 18 a 24 años. | 0 | 0 · 152 · 8,706 |
| `SV_18_24` | entero | Votaron: 18 a 24 años. | 0 | 0 · 67 · 2,472 |
| `NV_18_24` | entero | No votaron: 18 a 24 años. | 0 | 0 · 71 · 5,938 |
| `LN_25_34` | entero | Lista nominal de 25 a 34 años. | 0 | 0 · 234 · 16,710 |
| `SV_25_34` | entero | Votaron: 25 a 34 años. | 0 | 0 · 98 · 6,926 |
| `NV_25_34` | entero | No votaron: 25 a 34 años. | 0 | 0 · 114 · 9,188 |
| `LN_35_44` | entero | Lista nominal de 35 a 44 años. | 0 | 0 · 205 · 12,002 |
| `SV_35_44` | entero | Votaron: 35 a 44 años. | 0 | 0 · 104 · 4,973 |
| `NV_35_44` | entero | No votaron: 35 a 44 años. | 0 | 0 · 81 · 5,256 |
| `LN_45_59` | entero | Lista nominal de 45 a 59 años. | 0 | 0 · 239 · 5,965 |
| `SV_45_59` | entero | Votaron: 45 a 59 años. | 0 | 0 · 141 · 4,022 |
| `NV_45_59` | entero | No votaron: 45 a 59 años. | 0 | 0 · 77 · 2,593 |
| `LN_60_plus` | entero | Lista nominal de 60 años o más. | 0 | 0 · 193 · 3,254 |
| `SV_60_plus` | entero | Votaron: 60 años o más. | 0 | 0 · 113 · 2,422 |
| `NV_60_plus` | entero | No votaron: 60 años o más. | 0 | 0 · 61 · 1,918 |
| `PCT_PART_18_24` | decimal | Participación de 18 a 24 años = `SV_18_24 / (SV_18_24 + NV_18_24)`. | 9,584 (2.4%) | 0.0% · 48.8% · 100.0% |
| `PCT_ABST_18_24` | decimal | Abstención de 18 a 24 años = `NV_18_24 / (SV_18_24 + NV_18_24)`. | 9,584 (2.4%) | 0.0% · 51.2% · 100.0% |
| `PROP_LN_18_24` | decimal | Peso de 18 a 24 años en la lista nominal = `LN_18_24 / LN`. | 0 | 0.0% · 15.2% · 67.0% |
| `PCT_PART_25_34` | decimal | Participación de 25 a 34 años = `SV_25_34 / (SV_25_34 + NV_25_34)`. | 9,522 (2.3%) | 0.0% · 46.9% · 100.0% |
| `PCT_ABST_25_34` | decimal | Abstención de 25 a 34 años = `NV_25_34 / (SV_25_34 + NV_25_34)`. | 9,522 (2.3%) | 0.0% · 53.1% · 100.0% |
| `PROP_LN_25_34` | decimal | Peso de 25 a 34 años en la lista nominal = `LN_25_34 / LN`. | 0 | 0.0% · 23.0% · 82.1% |
| `PCT_PART_35_44` | decimal | Participación de 35 a 44 años = `SV_35_44 / (SV_35_44 + NV_35_44)`. | 9,514 (2.3%) | 0.0% · 56.7% · 100.0% |
| `PCT_ABST_35_44` | decimal | Abstención de 35 a 44 años = `NV_35_44 / (SV_35_44 + NV_35_44)`. | 9,514 (2.3%) | 0.0% · 43.3% · 100.0% |
| `PROP_LN_35_44` | decimal | Peso de 35 a 44 años en la lista nominal = `LN_35_44 / LN`. | 0 | 0.0% · 19.7% · 100.0% |
| `PCT_PART_45_59` | decimal | Participación de 45 a 59 años = `SV_45_59 / (SV_45_59 + NV_45_59)`. | 9,520 (2.3%) | 0.0% · 64.6% · 100.0% |
| `PCT_ABST_45_59` | decimal | Abstención de 45 a 59 años = `NV_45_59 / (SV_45_59 + NV_45_59)`. | 9,520 (2.3%) | 0.0% · 35.4% · 100.0% |
| `PROP_LN_45_59` | decimal | Peso de 45 a 59 años en la lista nominal = `LN_45_59 / LN`. | 0 | 0.0% · 22.8% · 100.0% |
| `PCT_PART_60_plus` | decimal | Participación de 60 años o más = `SV_60_plus / (SV_60_plus + NV_60_plus)`. | 9,593 (2.4%) | 0.0% · 64.6% · 100.0% |
| `PCT_ABST_60_plus` | decimal | Abstención de 60 años o más = `NV_60_plus / (SV_60_plus + NV_60_plus)`. | 9,593 (2.4%) | 0.0% · 35.4% · 100.0% |
| `PROP_LN_60_plus` | decimal | Peso de 60 años o más en la lista nominal = `LN_60_plus / LN`. | 0 | 0.0% · 18.4% · 100.0% |

**Presencia y estabilidad 2009–2024**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `n_years` | entero | En cuántas de las 6 elecciones aparece la sección (misma clave). | 0 | 1 · 6 · 6 |
| `n_mpios` | entero | Cuántos municipios distintos tuvo la sección entre 2009 y 2024. | 0 | 1 · 1 · 2 |
| `n_types` | entero | Cuántos tipos de sección distintos tuvo entre 2009 y 2024. | 0 | 1 · 1 · 3 |
| `STABLE_MUNICIPALITY_ALL_YEARS` | booleano | Verdadero si siempre estuvo en el mismo municipio (`n_mpios = 1`). | 0 | verdadero en 405,356 (99.6%) |
| `STABLE_TIPO_ALL_YEARS` | booleano | Verdadero si siempre tuvo el mismo tipo (`n_types = 1`). | 0 | verdadero en 397,533 (97.7%) |
| `N_INTERMEDIA` | entero | En cuántas intermedias (2009, 2015, 2021) aparece la sección. | 2,787 (0.7%) | 1 · 3 · 3 |
| `N_PRESIDENCIAL` | entero | En cuántas presidenciales (2012, 2018, 2024) aparece la sección. | 110 (0.0%) | 1 · 3 · 3 |

**Historia (misma familia de elección)**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `PREV_YEAR` | entero | Año de la elección anterior **de la misma familia** (2015 ← 2009, 2018 ← 2012, 2021 ← 2015, 2024 ← 2018). | 142,465 (35.0%) | 2009 · 2015 · 2018 |
| `PREV_PCT_ABSTENCION` | decimal | Abstención en la elección anterior de la misma familia. | 147,951 (36.4%) | 0.0% · 44.1% · 100.0% |
| `PREV_PCT_PARTICIPACION` | decimal | Participación en la elección anterior de la misma familia. | 147,951 (36.4%) | 0.0% · 55.9% · 100.0% |
| `PREV_LN` | entero | Lista nominal en la elección anterior de la misma familia. | 142,465 (35.0%) | 2 · 1,021 · 14,857 |
| `PREV_PCT_NS_LN` | decimal | Proporción NS en la elección anterior de la misma familia. | 142,465 (35.0%) | 0.0% · 0.0% · 100.0% |
| `PREV_EDAD_PROM_LN` | decimal | Edad promedio de la lista nominal en la elección anterior de la misma familia. | 142,465 (35.0%) | 23.2 · 42.2 · 66.0 |
| `PREV_PROP_LN_18_24` | decimal | Peso de 18–24 años en la lista nominal anterior (misma familia). | 142,465 (35.0%) | 0.0% · 15.7% · 67.0% |
| `PREV_PROP_LN_25_34` | decimal | Peso de 25–34 años en la lista nominal anterior (misma familia). | 142,465 (35.0%) | 0.0% · 23.7% · 82.1% |
| `PREV_PROP_LN_60_plus` | decimal | Peso de 60+ años en la lista nominal anterior (misma familia). | 142,465 (35.0%) | 0.0% · 17.3% · 69.8% |
| `PREV2_PCT_ABSTENCION` | decimal | Abstención dos elecciones atrás en la misma familia (p. ej., 2021 ← 2009). | 280,190 (68.9%) | 0.6% · 44.9% · 100.0% |
| `DELTA_ABST_VS_PREV` | decimal | Cambio de abstención contra la anterior de la misma familia (`PCT_ABSTENCION − PREV_PCT_ABSTENCION`). | 155,386 (38.2%) | -100.0 pp · -0.9 pp · +72.8 pp |
| `DELTA_LN_PCT_VS_PREV` | decimal | Crecimiento relativo de la lista nominal contra la anterior de la misma familia. | 142,465 (35.0%) | -99.8% · 4.3% · 7919.8% |
| `TREND_ABST_2_INTERVALS` | decimal | Tendencia previa: `PREV_PCT_ABSTENCION − PREV2_PCT_ABSTENCION`. | 284,108 (69.8%) | -83.8 pp · -1.5 pp · +72.8 pp |

**Banderas de calidad**

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `FLAG_DENOM_ZERO` | booleano | Verdadero si `SV + NV = 0`: toda la sección es NS y no se puede calcular abstención. | 0 | verdadero en 9,438 (2.3%) |
| `FLAG_NS_GT_05PCT` | booleano | Verdadero si `PCT_NS_LN > 5%`. | 0 | verdadero en 33,640 (8.3%) |
| `FLAG_NS_GT_10PCT` | booleano | Verdadero si `PCT_NS_LN > 10%` (umbral que usa el modelo 2027). | 0 | verdadero en 33,007 (8.1%) |
| `FLAG_NS_GT_25PCT` | booleano | Verdadero si `PCT_NS_LN > 25%`. | 0 | verdadero en 28,694 (7.1%) |

#### Por qué hay nulos

- **Tasas totales** (`PCT_PARTICIPACION`, `PCT_ABSTENCION`): nulas cuando `SV + NV = 0` (2009: 1,004, 2012: 82, 2015: 2,042, 2018: 2,517, 2021: 1,693, 2024: 2,100). Son las secciones de `FLAG_DENOM_ZERO`.
- **No binario** (`PCT_PART_NB`, `PCT_ABST_NB`): nulas en toda sección sin personas no binarias, es decir, en todas las elecciones antes de 2024 y en la mayoría de 2024 (2009: 64,934, 2012: 65,599, 2015: 68,362, 2018: 68,408, 2021: 68,812, 2024: 70,649).
- **Tasas por sexo o edad**: nulas cuando ese grupo no tiene `SV + NV` en la sección (grupo vacío o todo NS).
- **`EDAD_PROM_VOTANTES`**: nula cuando `SV = 0` (2009: 1,031, 2012: 97, 2015: 2,069, 2018: 2,520, 2021: 1,705, 2024: 2,106).
- **Historia (`PREV_*`)**: nula en 2009 y 2012 (primera elección de cada familia) y en secciones que no existían en la elección anterior de su familia. `PREV_PCT_ABSTENCION`: 2009: 64,934, 2012: 65,599, 2015: 4,737, 2018: 3,103, 2021: 3,230, 2024: 6,348.
  `PREV_PCT_ABSTENCION` tiene más nulos que `PREV_YEAR` porque también es nula cuando la elección anterior fue 100% NS.
- **`N_INTERMEDIA` / `N_PRESIDENCIAL`**: nulas (en lugar de 0) en secciones que nunca aparecen en esa familia de elecciones (2,787 y 110 filas).
- **`PREV2_PCT_ABSTENCION` y `TREND_ABST_2_INTERVALS`**: solo existen desde 2021 y 2024 (necesitan dos elecciones previas de la familia). `PREV2_PCT_ABSTENCION`: 2009: 64,934, 2012: 65,599, 2015: 68,362, 2018: 68,408, 2021: 5,925, 2024: 6,962.
- **`DEF` / `DEL`**: ver hallazgos de los CCPC (`DEF`: 2009: 318, 2012: 221; `DEL`: 2009: 318, 2012: 221, 2024: 136).

#### Banderas de calidad por año

| Bandera | 2009 | 2012 | 2015 | 2018 | 2021 | 2024 |
|---|---|---|---|---|---|---|
| `FLAG_DENOM_ZERO` | 1,004 | 82 | 2,042 | 2,517 | 1,693 | 2,100 |
| `FLAG_NS_GT_05PCT` | 2,672 | 287 | 7,197 | 8,720 | 6,060 | 8,704 |
| `FLAG_NS_GT_10PCT` | 2,644 | 278 | 7,091 | 8,552 | 5,901 | 8,541 |
| `FLAG_NS_GT_25PCT` | 2,444 | 251 | 6,313 | 7,415 | 5,078 | 7,193 |

#### Presencia de las secciones

| Elecciones en que aparece | Secciones |
|---|---|
| 1 | 2,897 |
| 2 | 1,393 |
| 3 | 81 |
| 4 | 2,658 |
| 5 | 3,604 |
| 6 | 62,048 |

Pares de historia usados en `PREV_*` (elección ← anterior de la misma familia): 2015<-2009: 64,616, 2018<-2012: 65,377, 2021<-2015: 67,598, 2024<-2018: 66,810.

## 3. Tabla final 2027

- **Archivo:** `data/processed/sensitivity_2027/section_sensitivity_2027.parquet` (lo genera `src/13_sensitivity_prioritization.py`). Es la tabla más completa por sección del producto; de ella salen la capa espacial y el dashboard.
- **Tamaño:** 54,772 filas × 41 columnas; una fila por sección del universo `primary_clean10`.
- **Universo:** de 67,976 secciones presentes en 2021 y 2024 (`forecast_2027_all_comparable.parquet`), quedan en esta tabla solo las `primary_clean10`: `primary_clean10` 54,772, `comparable_high_ns` 9,199, `insufficient_inputs` 3,532, `valid_inputs_low_comparability` 473.

| Columna | Tipo | Significado | Nulos | Valores |
|---|---|---|---|---|
| `TARGET_YEAR` | entero | Elección que se estima (2027). | 0 | 2027 · 2027 · 2027 |
| `SAME_YEAR` | entero | Elección de la misma familia usada como historia (2021, intermedia). | 0 | 2021 · 2021 · 2021 |
| `RECENT_YEAR` | entero | Elección federal más reciente usada como historia (2024). | 0 | 2024 · 2024 · 2024 |
| `AELEC_x` | entero | Copia de `AELEC` de 2021 que quedó del cruce entre años. Redundante con `SAME_YEAR`. | 0 | 2021 · 2021 · 2021 |
| `EDOCVE` | entero | Clave del estado. | 0 | 1 · 15 · 32 |
| `SAME_EDONOM` | texto | Nombre del estado en 2021. | 0 | 32 distintos |
| `SAME_MPIOCVE` | entero | Clave del municipio en 2021. | 0 | 1 · 29 · 570 |
| `SAME_MPIONOM` | texto | Nombre del municipio en 2021. | 0 | 2,272 distintos |
| `SAME_SECCION` | entero | Número de sección en 2021. | 0 | 1 · 1,273 · 6,636 |
| `SAME_TIPOSEC` | texto | Tipo de sección en 2021. | 0 | U (35,193), R (14,933), M (4,646) |
| `SAME_LN` | entero | Lista nominal en 2021. | 0 | 14 · 1,031 · 16,458 |
| `SAME_PCT_ABSTENCION` | decimal | Abstención en 2021. | 0 | 0.0% · 46.0% · 100.0% |
| `SAME_PCT_NS_LN` | decimal | Proporción NS en 2021. | 0 | 0.0% · 0.0% · 10.0% |
| `SECTION_KEY` | texto | Clave de sección `EE-SSSS`. | 0 | 54,772 distintos |
| `AELEC_y` | entero | Copia de `AELEC` de 2024 que quedó del cruce. Redundante con `RECENT_YEAR`. | 0 | 2024 · 2024 · 2024 |
| `RECENT_EDONOM` | texto | Nombre del estado en 2024. | 0 | 32 distintos |
| `RECENT_MPIOCVE` | entero | Clave del municipio en 2024. | 0 | 1 · 29 · 570 |
| `RECENT_MPIONOM` | texto | Nombre del municipio en 2024. | 0 | 2,271 distintos |
| `RECENT_SECCION` | entero | Número de sección en 2024. | 0 | 1 · 1,273 · 6,636 |
| `RECENT_TIPOSEC` | texto | Tipo de sección en 2024. | 0 | U (35,193), R (14,933), M (4,646) |
| `RECENT_LN` | entero | Lista nominal en 2024. | 0 | 12 · 1,049 · 20,706 |
| `RECENT_PCT_ABSTENCION` | decimal | Abstención en 2024. | 0 | 0.0% · 38.5% · 100.0% |
| `RECENT_PCT_NS_LN` | decimal | Proporción NS en 2024. | 0 | 0.0% · 0.0% · 10.0% |
| `STABLE_MPIO` | booleano | Mismo municipio en 2021 y 2024. | 0 | verdadero en 54,772 |
| `STABLE_TIPOSEC` | booleano | Mismo tipo de sección en 2021 y 2024. | 0 | verdadero en 54,772 |
| `INPUTS_VALID` | booleano | Abstención calculable en 2021 y en 2024. | 0 | verdadero en 54,772 |
| `NS_CLEAN10` | booleano | NS ≤ 10% de la lista nominal en 2021 y en 2024. | 0 | verdadero en 54,772 |
| `PRIMARY_UNIVERSE` | booleano | Cumple las cuatro condiciones anteriores. Siempre verdadero en esta tabla. | 0 | verdadero en 54,772 |
| `QUALITY_FLAG` | texto | Clasificación de calidad; aquí siempre `primary_clean10`. | 0 | primary_clean10 (54,772) |
| `PRED_ABSTENCION_2027` | decimal | Abstención estimada 2027 = 0.048 + 0.677 × abstención 2021 + 0.180 × abstención 2024, recortada a 0–1. | 0 | 5.4% · 42.8% · 86.2% |
| `PRED_LOWER_90_OOS` | decimal | Límite inferior del intervalo empírico 90% (estimación + residual q05 del backtest 2021 fuera de muestra). | 0 | 0.0% · 23.6% · 67.0% |
| `PRED_UPPER_90_OOS` | decimal | Límite superior del intervalo empírico 90% (estimación + residual q95). | 0 | 18.3% · 55.7% · 99.1% |
| `INTERVAL_WIDTH_PP` | decimal | Ancho del intervalo 90% en pp. | 0 | 18.30 · 32.13 · 32.13 |
| `HISTORY_DISAGREEMENT_PP` | decimal | Diferencia absoluta entre la abstención 2024 y la 2021, en pp. Alta = las dos historias no coinciden. | 0 | 0 · 8.12 · 79.23 |
| `RISK_PERCENTILE` | decimal | Percentil de la abstención estimada dentro del universo (0–1). | 0 | 0.0% · 50.0% · 100.0% |
| `RISK_LEVEL` | texto | Semáforo: BAJO (percentil ≤ 0.5), MEDIO (0.5–0.8), ALTO (> 0.8). | 0 | BAJO (27,386), MEDIO (16,431), ALTO (10,955) |
| `PRIORITY_TOP10` | booleano | Verdadero si el percentil es ≥ 0.9. | 0 | verdadero en 5,478 |
| `GAP_TO_EXIT_HIGH_PP` | decimal | Para secciones ALTO: pp que tendría que bajar la estimación para dejar de ser ALTO. 0 en las demás. | 0 | 0 · 0 · 35.10 |
| `GAP_TO_EXIT_PRIORITY_PP` | decimal | Para secciones Top10: pp que tendría que bajar para salir del Top10. 0 en las demás. | 0 | 0 · 0 · 30.74 |
| `HIGH_SENSITIVITY_CLASS` | texto | NO_ALTO; ALTO_SENSIBLE_2PP (sale de ALTO bajando ≤ 2 pp); ALTO_SENSIBLE_5PP (2–5 pp); ALTO_PERSISTENTE_MAS_5PP (> 5 pp). | 0 | NO_ALTO (43,817), ALTO_PERSISTENTE_MAS_5PP (4,886), ALTO_SENSIBLE_5PP (3,236), ALTO_SENSIBLE_2PP (2,833) |
| `INTERVAL_POSITION_VS_HIGH` | texto | Posición del intervalo 90% frente al umbral de ALTO: completamente debajo, lo cruza o completamente arriba. | 0 | INTERVAL_CROSSES_HIGH (36,916), INTERVAL_BELOW_HIGH (17,710), INTERVAL_ENTIRELY_HIGH (146) |

Observaciones: `AELEC_x` y `AELEC_y` son columnas duplicadas del cruce entre años (sufijos automáticos de pandas) y se podrían eliminar; `TARGET_YEAR`, `SAME_YEAR`, `RECENT_YEAR`, `PRIMARY_UNIVERSE` y `QUALITY_FLAG` son constantes en esta tabla.

## 4. Glosario

| Término | Significado |
|---|---|
| Sección electoral | Unidad territorial más pequeña del INE; por ley agrupa entre 100 y 3,000 electores. |
| Lista nominal (LN) | Personas con credencial vigente registradas para votar en la sección. |
| SV / NV / NS | Sí votó / no votó / sin información de participación. |
| Participación | `SV / (SV + NV)`. |
| Abstención | `NV / (SV + NV)`. NS se excluye del denominador. |
| Intermedia / presidencial | Elección federal sin / con elección presidencial. Intermedias: 2009, 2015, 2021; presidenciales: 2012, 2018, 2024. |
| Misma familia | Elecciones del mismo tipo (intermedia o presidencial). El historial `PREV_*` compara dentro de la familia. |
| primary_clean10 | Universo del modelo 2027: secciones en 2021 y 2024, sin cambio de municipio ni de tipo, con abstención calculable y NS ≤ 10% en ambos años. |
| pp | Puntos porcentuales. |
| DERFE | Dirección Ejecutiva del Registro Federal de Electores del INE, que define el marco cartográfico. |
