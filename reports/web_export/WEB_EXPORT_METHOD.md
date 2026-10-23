# Exportación para el sitio web (`src/21_export_web.py`)

Prepara los datos del sitio web (Astro + React en el frontend, API en Python).
El dashboard de Streamlit no se toca.

```bash
python src/21_export_web.py      # ~110 s; requiere tippecanoe (incluido en la imagen Docker)
```

## Salidas (`data/processed/web/`, no versionadas)

| Archivo | Contenido | Uso |
|---|---|---|
| `secciones.pmtiles` | 73,268 secciones de la cartografía, geometría completa, zoom 3–12 | Mapa (MapLibre), servido como archivo estático con HTTP Range |
| `secciones.parquet` | 75,636 filas (cartografía ∪ semáforo ∪ NS alto), sin geometría; incluye la caja `BBOX_*` de cada sección | Tabla que lee la API (`api/main.py`) |
| `historico.parquet` | Sección × elección 2009–2024 (LN, SV, NV, NS, tipo, municipio) | Series y tablas de "Datos por año" |
| `grupos.parquet` | Grupo y variables del clustering por sección (si se corrió `src/clustering/01`) | Página "Grupos" |

`export_summary.json` (versionado) guarda los conteos de cada corrida.

La geometría se lee de los ZIP del MGS con el lector de la etapa 15. Al cambiar
al Marco Geográfico Electoral oficial basta con cambiar la ruta de entrada.

## Contrato de atributos de las teselas

La capa de datos se llama `secciones`. El mismo archivo trae dos capas sólo de contorno, `estados` (`edo`)
y `municipios` (`edo`, `mun`), porque el sitio no usa mapa base de terceros. Los porcentajes van en puntos (0–100) con un decimal.
Si un atributo no aplica a una sección, no viene en la tesela: en MapLibre usar
`["coalesce", ["get", "x"], …]`.

| Atributo | Tipo | Significado |
|---|---|---|
| `clave` | texto | `EDOCVE-SECCION`, por ejemplo `09-4882`; llave para pedir el detalle a la API |
| `edo`, `mun` | entero | Entidad y municipio (CCPC; coincide 100% con el MGS) |
| `capa` | texto | `semaforo` (primary_clean10), `ns_alto` (comparable, NS > 10%), `sin_estimacion` |
| `nivel`, `top10`, `pred` | texto, bool, número | Semáforo oficial 2027: BAJO/MEDIO/ALTO, Top10, abstención estimada |
| `sensibilidad` | texto | Clase de persistencia: `NO_ALTO`, `ALTO_SENSIBLE_2PP`, `ALTO_SENSIBLE_5PP`, `ALTO_PERSISTENTE_MAS_5PP` |
| `nivel_s1..s3`, `top10_s1..s3` | texto, bool | Escenarios S1 (Top10 −2 pp), S2 (ALTO −2 pp), S3 (ALTO −5 pp); umbrales congelados |
| `abst_2009..2024`, `ns_2009..2024` | número | Abstención y NS observados por elección |
| `grupo` | entero | Grupo de clustering 1–5 (fase 1, descriptivo) |
| `nivel_oscar`, `comp_oscar` | texto | Semáforo alternativo y su comparación con el oficial |

El cambio frente a la elección anterior del mismo tipo se calcula en el cliente,
por ejemplo `abst_2021 − abst_2015`.

## Decisión de diseño y medición

Con el límite por defecto de tippecanoe (500 KB por tesela), a zoom 5 sólo quedaba
el 16% de las secciones y las ciudades salían huecas. Se compararon tres variantes:

| Variante | Secciones a zoom 5 | Peso total a zoom 5 |
|---|---|---|
| Atributos en la tesela, límite de 500 KB | 16% | 1.1 MB |
| Sólo geometría + `clave`, sin límite (datos unidos desde la API) | 76% | 1.7 MB + datos |
| **Atributos en la tesela, sin límite (elegida)** | **76%** | **3.0 MB** |

El 24% restante mide menos de un píxel a esa escala y tippecanoe lo dibuja como
"polvo". La variante elegida es la más simple para el cliente y pesa casi lo mismo
que la segunda. Si los atributos crecen mucho, conviene pasar a la segunda con
`feature-state`.

Prueba en navegador (MapLibre 5.24 + pmtiles 4.5, servidor local con Range):

- Vista nacional: 7 peticiones, 2.0 MB, ~1 s. Todo el país con polígonos, sin la vista híbrida de Streamlit.
- CDMX a zoom 11: +790 KB. A zoom 14 (sobre-zoom desde 12): +131 KB, bordes precisos.
- Los atributos de la sección 09-4882 coinciden con el semáforo, la base maestra y los escenarios.

Nota para el frontend: MapLibre 6 sólo se distribuye como módulo ES y crea su
*worker* como módulo, así que no funciona desde un CDN. Con Astro/Vite se
empaqueta localmente y no hay problema.
