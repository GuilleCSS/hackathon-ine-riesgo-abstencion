# Proyección territorial 2027 v1

## Arquitectura

La arquitectura fue bloqueada previamente como `two_history_linear`.

El estimador utiliza dos memorias territoriales:

- abstención 2021: última elección de la misma familia usada por la proyección;
- abstención 2024: elección federal más reciente disponible en CCPC.

La forma del modelo es:

`pred = intercept + beta_same * abst_2021 + beta_recent * abst_2024`

Los coeficientes se reestiman después de la selección utilizando todas las ventanas
históricas clean10 disponibles con targets 2015, 2018, 2021 y 2024.

## Universo

La salida v1 sólo incluye secciones presentes en 2021 y 2024. El universo primario
exige además:

- municipio estable entre ambas observaciones;
- tipo de sección estable;
- abstención calculable en ambas observaciones;
- NS <= 10% en ambas observaciones.

Este universo todavía **no equivale a la cartografía oficial 2027**. La conciliación
cartográfica será una etapa posterior.

## Incertidumbre

El intervalo empírico primario se construye con los residuales fuera de muestra del
backtest temporal 2021, por ser la evaluación intermedia comparable más cercana.

No se interpreta como una garantía probabilística si existen cambios estructurales
fuera de lo observado históricamente.

## Importante

Esta etapa genera una estimación continua y un intervalo de incertidumbre. Todavía
no asigna niveles de semáforo ni simula efectos de intervención.
