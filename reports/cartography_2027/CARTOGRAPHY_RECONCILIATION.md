# Conciliación cartográfica

## Estado de la capa

Esta ejecución puede utilizar una capa provisional. La vigencia exacta queda
registrada en `SOURCE_METADATA.json`.

## Resultados

- Fuentes cartográficas: 32
- Secciones de riesgo: 54,772
- Secciones cartográficas únicas: 73,268
- Coincidencias: 54,448
- Riesgo sin geometría: 324
- Geometría sin riesgo: 18,820
- Tasa de cobertura: 99.4085%

## Llave

`SECTION_KEY = EDOCVE + "-" + SECCION`

## Restricción

Una sección cartográfica sin historia comparable no recibe predicción por
interpolación automática. Cualquier correspondencia entre secciones antiguas y
nuevas debe documentarse explícitamente.

## Uso

Si esta corrida usa MGS DIC-2025, los resultados son de validación provisional.
Antes de la entrega final deberá repetirse con la capa oficial del MGE
2026-2027 cuando esté disponible para descarga.
