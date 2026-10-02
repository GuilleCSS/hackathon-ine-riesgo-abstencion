# Sensibilidad y persistencia territorial del riesgo

## Objetivo

Esta etapa no estima efectos causales. Evalúa qué tan lejos se encuentra cada
territorio de los umbrales fijos del semáforo 2027.

## Distancia al umbral ALTO

Para cada sección clasificada como ALTO se calcula:

`GAP_TO_EXIT_HIGH_PP = (predicción - umbral_ALTO) * 100`

Esto permite una tipología descriptiva:

- `ALTO_SENSIBLE_2PP`: está a 2 pp o menos de salir de ALTO.
- `ALTO_SENSIBLE_5PP`: requiere más de 2 y hasta 5 pp.
- `ALTO_PERSISTENTE_MAS_5PP`: se encuentra más de 5 pp sobre el umbral.

La palabra "sensible" significa sensibilidad matemática al supuesto de escenario;
no implica que una intervención real consiga esa reducción.

## Curva de sensibilidad

Se simulan reducciones hipotéticas de 0 a 10 pp, cada 0.5 pp, aplicadas por
separado a:

1. todas las secciones ALTO;
2. únicamente las secciones PRIORITY_TOP10.

Los umbrales permanecen congelados en los valores del escenario base.

## Incertidumbre

También se compara el intervalo empírico OOS de cada sección con el umbral ALTO:

- `INTERVAL_BELOW_HIGH`
- `INTERVAL_CROSSES_HIGH`
- `INTERVAL_ENTIRELY_HIGH`

Esto no transforma el intervalo empírico en una probabilidad posterior. Es una
bandera de estabilidad relativa respecto al corte operativo.

## Uso

La tipología sirve para distinguir entre:

- riesgo alto cercano al umbral;
- riesgo alto que permanece lejos del umbral bajo supuestos moderados;
- territorios con alta incertidumbre alrededor del corte.

No constituye una recomendación automática de intervención.
