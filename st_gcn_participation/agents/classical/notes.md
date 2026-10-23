# Espacio agente modelos clásicos

Agente: `classical`.

Recomendó comparar persistencia (`same-family` y elección más reciente), regresión de dos historias y un modelo tabular. El repositorio ya contiene `two_history_linear` validado para 2021 y 2024 (MAE 7.69 y 4.36 pp en su propio dataset procesado). Ridge y HGB existentes no lo superan consistentemente.

En esta carpeta se hará una réplica independiente sobre los seis CSV presentes: Ridge y HistGradientBoosting, junto con baselines, estrictamente por corte temporal. No asumir equivalencia de fuente respecto a los reportes existentes.
