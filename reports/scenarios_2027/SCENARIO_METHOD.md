# Escenarios hipotéticos de intervención · metodología

## Objetivo

Los escenarios permiten explorar cómo cambiaría la priorización territorial bajo
supuestos explícitos de reducción de abstención estimada.

**No son estimaciones causales de efectividad de una política específica.**

## Escenario base

`S0_BASELINE` conserva la proyección territorial generada por el modelo bloqueado.

## Escenarios de sensibilidad

- `S1_TOP10_MINUS2`: supuesto de -2 pp únicamente en el Top10 prioritario.
- `S2_HIGH_MINUS2`: supuesto de -2 pp en todas las secciones ALTO.
- `S3_HIGH_MINUS5`: supuesto de -5 pp en todas las secciones ALTO.

Los valores 2 pp y 5 pp son parámetros de sensibilidad, no efectos históricos
atribuidos a una intervención real.

## Umbrales congelados

Los cortes del semáforo se mantienen fijos en los valores derivados del escenario
base 2027.

Esto es fundamental: si los percentiles se recalcularan dentro de cada escenario,
siempre habría un 20% de secciones clasificadas como ALTO, incluso después de una
mejora general. Con umbrales fijos es posible observar cuántas secciones cruzan de
ALTO a MEDIO o de MEDIO a BAJO.

## Lectura institucional

Los escenarios deben leerse como preguntas de planeación:

> "Si en los territorios priorizados se alcanzara una reducción de X puntos
> porcentuales respecto de la estimación base, ¿cómo cambiaría el mapa de riesgo?"

No deben leerse como:

> "La intervención causará una reducción de X puntos porcentuales."

## Próxima etapa

Estos escenarios deberán vincularse posteriormente con la cartografía oficial y
el dashboard, conservando siempre la diferencia entre:

- predicción histórica;
- nivel de riesgo relativo;
- incertidumbre;
- supuesto de escenario.
