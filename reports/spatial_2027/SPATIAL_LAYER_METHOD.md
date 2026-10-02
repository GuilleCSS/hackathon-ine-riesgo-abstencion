# Capa espacial provisional 2027

## Estado

**PROVISIONAL**

La geometría utilizada corresponde al MGS por entidad federativa con corte
DIC-2025. La capa deberá regenerarse con el Marco Geográfico Electoral
2026-2027 vigente antes de la entrega final.

## Unión

La llave espacial es:

`SECTION_KEY = EDOCVE + "-" + SECCION`

Sólo se cartografían secciones del universo `primary_clean10` que tienen una
geometría equivalente en la fuente provisional.

## TIPOSEC

La auditoría 14B mostró el siguiente mapeo dominante:

- `2 -> U`
- `3 -> M`
- `4 -> R`

La capa espacial conserva tanto el código original cartográfico como el valor
normalizado.

## Productos

- GeoPackage: análisis en QGIS / interoperabilidad.
- GeoJSON completo: intercambio.
- GeoJSON simplificado: dashboard web.

## Limitación

No se asignan predicciones a secciones cartográficas sin historia comparable.
Las secciones no emparejadas se mantienen documentadas en la auditoría del
paso 14.
