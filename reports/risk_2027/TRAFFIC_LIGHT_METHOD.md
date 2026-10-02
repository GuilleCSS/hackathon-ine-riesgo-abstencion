# Semáforo territorial de riesgo · metodología v1

## Naturaleza del semáforo

El semáforo es una **clasificación relativa de priorización territorial** dentro
del universo `primary_clean10`. No debe interpretarse como una probabilidad
absoluta de que una sección se abstenga.

Se utiliza la estimación continua generada por la arquitectura bloqueada
`two_history_linear`.

## Regla

- **BAJO / verde:** percentil de riesgo <= 50.
- **MEDIO / amarillo:** percentil > 50 y <= 80.
- **ALTO / rojo:** percentil > 80.
- **PRIORITY_TOP10:** bandera adicional para percentil >= 90.

Los puntos Top20 y Top10 se eligieron porque fueron evaluados explícitamente
durante los backtests temporales del proyecto.

## Validación

Antes de aplicarse a 2027, la misma regla se aplica retrospectivamente a los
backtests 2021 y 2024. Para cada nivel se documentan:

- promedio de abstención observado;
- error absoluto medio;
- proporción de secciones que realmente estuvieron en el Top20 observado;
- proporción de secciones que realmente estuvieron en el Top10 observado.

También se verifica que el promedio de abstención observado aumente
monótonamente de BAJO a MEDIO y ALTO.

## Umbrales 2027

Los cortes porcentuales se traducen a valores absolutos usando la distribución
de `PRED_ABSTENCION_2027` del universo primario. Por tanto, el semáforo es
relativo al universo analizado y deberá recalibrarse si cambia la cartografía
o el universo operativo.

## Incertidumbre

El semáforo no elimina la incertidumbre. Cada sección conserva:

- `PRED_LOWER_90_OOS`;
- `PRED_UPPER_90_OOS`;
- `INTERVAL_WIDTH_PP`;
- `HISTORY_DISAGREEMENT_PP`.

Estas columnas deberán mostrarse en el producto final como información
complementaria a la prioridad territorial.

## Limitación

La base aún no ha sido reconciliada con la cartografía oficial vigente del
proceso futuro. Esta conciliación será una etapa independiente antes de la
visualización geográfica final.
