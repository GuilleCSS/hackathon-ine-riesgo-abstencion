# Agente: model_evaluator

## Protocolo recomendado

- Target: `abstencion = No votaron / (Sí votaron + No votaron)`.
- Reportar participacion como `1 - abstencion`.
- Split temporal estricto: entrenar solo con años previos al target.
- Backtesting: 2015, 2018, 2021, 2024 segun disponibilidad historica.
- Separar familias electorales cuando aplique: intermedias vs presidenciales.

## Baselines minimos

- Persistencia misma familia electoral.
- Eleccion reciente.
- Blend simple.
- Modelo lineal/tabular.

## Metricas

- MAE en puntos porcentuales.
- RMSE.
- Bias.
- Spearman para ranking territorial.
- Recall@K / precision@K para zonas de alta abstencion.

## Criterio para aceptar ST-GCN

Debe mejorar fuera de muestra contra baselines y demostrar que el grafo real aporta mas que un grafo aleatorio o una version sin grafo.
