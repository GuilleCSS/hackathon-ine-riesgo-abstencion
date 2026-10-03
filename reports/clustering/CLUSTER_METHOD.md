# Grupos de secciones por trayectoria (fase 1, descriptiva)

Generado por `src/clustering/01_build_section_clusters.py`. No modifica el
pipeline del modelo 2027.

## Idea

Agrupar las secciones por **cómo se comportan** frente al promedio nacional de
cada elección, para analizar territorios parecidos de forma separada. El
contexto (tipo de sección, tamaño, edad) se usa sólo para **describir** los
grupos, no para formarlos.

## Variables (pp frente a la abstención nacional de cada elección)

- `nivel_intermedia`: promedio en 2009, 2015 y 2021.
- `nivel_presidencial`: promedio en 2012, 2018 y 2024.
- `tendencia`: promedio de 2021 y 2024 menos promedio de 2009 y 2012.
- `volatilidad`: desviación media de cada elección frente al promedio de la sección.

Se estandarizan y se agrupan con k-means (k = 5, `random_state` = 42).

## Universo

41,136 de 72,681 secciones de la base maestra:
las que tienen abstención calculable en las 6 elecciones y NS ≤ 25% en todas.
Quedan fuera las secciones nuevas o renumeradas y las de datos poco confiables.

## Grupos

Nombres asignados por reglas sobre los centroides: tendencia mayor a ±5 pp
→ "Empeorando"/"Mejorando"; si no, nivel medio mayor a ±5 pp → "alta"/"baja"
persistente; si no, "En el promedio".

| Grupo | Nombre | Secciones | Intermedias (pp) | Presidenciales (pp) | Tendencia (pp) | Volatilidad (pp) | Urbana / rural | LN mediana 2024 |
|---|---|---|---|---|---|---|---|---|
| G1 | Abstención baja persistente | 6,874 (17%) | -18.0 | -11.8 | -0.3 | 5.1 | 40% / 49% | 939 |
| G2 | En el promedio | 15,941 (39%) | -1.6 | -4.4 | -2.7 | 3.9 | 81% / 14% | 1,111 |
| G3 | Abstención alta persistente | 8,664 (21%) | +9.8 | +9.0 | -0.2 | 3.8 | 72% / 19% | 1,091 |
| G4 | Mejorando | 4,219 (10%) | -3.4 | -4.2 | -15.7 | 8.7 | 39% / 46% | 939 |
| G5 | Empeorando | 5,438 (13%) | -2.6 | +4.4 | +9.9 | 6.6 | 41% / 47% | 1,122 |

## Elección de k

| k | Silhouette | Tamaños |
|---|---|---|
| 3 | 0.270 | 17829, 17562, 5745 |
| 4 | 0.253 | 16918, 12139, 7485, 4594 |
| 5 | 0.259 | 15941, 8664, 6874, 5438, 4219 |
| 6 | 0.248 | 10483, 9153, 7637, 6206, 5026, 2631 |
| 7 | 0.245 | 10124, 8354, 6370, 5437, 4280, 4041, 2530 |
| 8 | 0.235 | 8717, 7808, 6761, 4639, 4228, 3353, 3181, 2449 |

El silhouette es moderado (≈0.25) para cualquier k: las secciones forman un
continuo más que grupos bien separados. Los grupos son una **tipología útil para
segmentar**, con fronteras difusas; secciones cerca de la frontera podrían caer en
el grupo vecino con otra configuración.

## Limitaciones

- Descriptivo: usa 2009–2024 completo. Para usar los grupos en el modelo, hay que
  reconstruirlos sólo con elecciones anteriores a la que se predice.
- Comparar grupos no es causalidad; sirve para comparaciones controladas entre
  territorios parecidos.
- La cartografía para el mapa es la provisional DIC-2025.

## Salidas

- `data/processed/clustering/section_clusters.parquet`: grupo y variables por sección.
- `reports/clustering/01_k_selection.csv`: silhouette por k.
- `reports/clustering/02_cluster_profiles.csv`: perfil de cada grupo.
- `reports/clustering/03_cluster_trajectories.csv`: abstención por grupo y elección.
- `reports/clustering/04_state_composition.csv`: composición de grupos por estado.
- `reports/clustering/clustering_config.json`: parámetros y resumen.
