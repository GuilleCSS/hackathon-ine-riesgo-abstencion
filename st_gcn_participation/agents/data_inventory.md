# Agente: data_inventory

Fuente revisada: `../Data/*.csv`.

## Hallazgos

- Años disponibles: 2009, 2012, 2015, 2018, 2021, 2024.
- Total procesado: 54,872,712 filas.
- Columnas comunes: `Año`, `Sexo`, `Tiposec`, `Distrito Federal`, `Distrito Local`, `Estado`, `Municipio`, `Población ind/afro`, `Sección`, `DEF`, `DEL`, `Edonom`, `Sección numérica`, `% Participación`, `No votaron`, `Sexo numérico`, `Sí votaron`.
- La tasa valida debe calcularse como `Sí votaron / (Sí votaron + No votaron)`, no como promedio simple de `% Participación`.
- Hay filas con denominador cero y valores extremos 0%/100%.
- La granularidad cruda no es una llave unica de seccion-anio; requiere agregacion.

## Llaves utiles

- Temporal: `Año`.
- Territorial: `Edonom`, `Estado`, `Municipio`, `Sección numérica`.
- Segmentos: `Sexo`, `Tiposec`, `Población ind/afro`.
