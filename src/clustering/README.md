# Clustering de secciones y experimentos de modelo

Trabajo independiente del pipeline del modelo 2027: sólo lee la base maestra,
las ventanas `clean10` de la etapa 07 y la cartografía; no modifica
`selected_architecture.json` ni ninguna salida del modelo actual.

## Fase 1 · Grupos de secciones (descriptiva)

Agrupa las secciones por su trayectoria de abstención 2009–2024 frente al
promedio nacional de cada elección.

```bash
docker compose run --rm app python src/clustering/01_build_section_clusters.py
```

- Escribe `data/processed/clustering/section_clusters.parquet` y `reports/clustering/`.
- Método y grupos: `reports/clustering/CLUSTER_METHOD.md`.
- Dashboard: página **Grupos de secciones** (`dashboard/clustering/grupos.py`).

## Fase 2 · ¿Mejoran los grupos y las variables territoriales al modelo?

Backtest de 2021 y 2024 con las mismas ventanas, métricas, bootstrap por
municipio y regla de selección que las etapas 07–09. Compara el modelo actual
contra: ajuste por grupo, un modelo por grupo, vecinos, Ridge con contexto,
HistGradientBoosting, XGBoost y XGBoost sobre el residuo del modelo actual.

```bash
docker compose run --rm app python src/clustering/02_backtest_fase2.py
```

- Requiere la etapa 07 corrida y la cartografía en `data/raw/cartography_2027/`.
- Tarda ~10 min (400 réplicas de bootstrap por comparación).
- Sin fuga de información: cada variable de una fila con objetivo t usa sólo
  elecciones anteriores a t; los grupos se reconstruyen para cada t.
- Resultados y conclusión: `reports/clustering/fase2/FASE2_REPORT.md`.

## Fase 3 · Elecciones locales concurrentes

1. Calendario 2009–2027 de elecciones locales y gubernaturas el mismo día que la
   federal (`data/external/calendario_concurrente.csv`, fuente Wikipedia,
   pendiente de validar):

   ```bash
   docker compose run --rm app python src/clustering/03_build_calendario_concurrente.py
   ```

2. Backtest con el mismo protocolo de la fase 2, agregando concurrencia en la
   elección objetivo y en las dos historias (~6 min):

   ```bash
   docker compose run --rm app python src/clustering/04_backtest_concurrencia.py
   ```

- Resultados y conclusión: `reports/clustering/fase3/FASE3_REPORT.md`.
