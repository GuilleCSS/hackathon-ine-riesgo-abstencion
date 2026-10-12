# Agente: stgcn_feasibility

## Veredicto

Los datos sirven para construir un panel temporal agregado, pero no estan listos para ST-GCN.

## Faltantes criticos

- Matriz de adyacencia espacial entre secciones.
- Geometria, centroides o contigüidad electoral.
- Llave territorial estable tipo `EDOCVE-SECCION`.
- Manejo de secciones que nacen, desaparecen o cambian entre años.
- Panel `T x N x F` con mascara de nodos validos.

## Riesgo temporal

Hay 6 cortes electorales. Para una prediccion intermedia tipo 2027, los cortes comparables son solo 2009, 2015 y 2021.

## Recomendacion

Usar ST-GCN como challenger solo despues de construir grafo y panel. No usarla como modelo base inicial.
