# Auditoría del NS (registros sin información de participación)

Generado por `src/auditoria_ns/01_auditar_ns.py`. Lee la base maestra y el universo
comparable 2027; no modifica ninguna etapa del pipeline.

NS = personas de la lista nominal de las que no se sabe si votaron (cuadernillo sin marcas,
no disponible para captura, solicitado por autoridad o página faltante). La abstención se
calcula sin ellas y el semáforo 2027 excluye secciones con NS > 10% en 2021 o 2024.

## 1. Cuánto NS hay

| Año | Secciones | Con NS | NS > 10% | 100% NS | % de la lista nominal | NS en secciones con NS > 10% |
|---|---|---|---|---|---|---|
| 2009 | 64,934 | 2,685 | 2,644 | 1,004 | 2.4% | 98.8% |
| 2012 | 65,599 | 2,440 | 278 | 82 | 0.2% | 94.1% |
| 2015 | 68,362 | 7,331 | 7,091 | 2,042 | 6.1% | 98.6% |
| 2018 | 68,408 | 8,861 | 8,552 | 2,517 | 6.8% | 97.7% |
| 2021 | 68,812 | 6,317 | 5,901 | 1,693 | 4.3% | 96.9% |
| 2024 | 70,751 | 8,959 | 8,541 | 2,100 | 6.4% | 98.1% |

## 2. De dónde viene

Entre las secciones con NS parcial, la proporción de NS se amontona en fracciones simples,
como si faltara una casilla completa de dos, tres o cuatro (la casilla se divide por apellido):

| Fracción de NS | Secciones a ±2 pp de esa fracción |
|---|---|
| 1/4 | 9.4% |
| 1/3 | 22.2% |
| 1/2 | 41.9% |
| 2/3 | 3.5% |
| 3/4 | 0.7% |

Si la fracción fuera uniforme, cada ventana tendría alrededor de 4.2%.

Dentro de cada sección, todos los grupos de edad y ambos sexos pierden la misma proporción:
la razón entre el NS del grupo y el de su sección va de 0.977 a 1.011
(1 = igual; ver `03_ns_por_edad_y_sexo.csv`). Es lo esperable si faltan casillas o páginas
completas y no personas elegidas por su perfil. Ojo: si se agrega entre secciones, el grupo 60+
parece tener más NS, pero es un efecto de composición, no del NS.

## 3. ¿Es aleatorio entre secciones?

No. De 2015 a 2024, 10.9% de las sección-elección tienen NS > 10%, pero la tasa cambia mucho:

| Grupo | Tasa de NS > 10% |
|---|---|
| Tipo M | 13.6% |
| Tipo R | 10.2% |
| Tipo U | 10.8% |
| Lista nominal Q1 más chicas | 7.5% |
| Lista nominal Q2 | 8.3% |
| Lista nominal Q3 | 10.1% |
| Lista nominal Q4 | 11.3% |
| Lista nominal Q5 más grandes | 17.2% |
| Abstención previa Q1 menos abstención | 9.2% |
| Abstención previa Q2 | 9.5% |
| Abstención previa Q3 | 10.8% |
| Abstención previa Q4 | 11.8% |
| Abstención previa Q5 más abstención | 13.4% |

Más NS en secciones grandes (tienen más casillas que pueden faltar) y con más abstención previa.
La repetición en la misma sección es moderada: tener NS > 10% en una elección hace
1.4–1.5 veces más probable volver a tenerlo en la siguiente, pero la mayoría no repite.
Es sobre todo un problema operativo de cada elección, con un componente territorial.

| Elección | vs. | Tasa base | Si antes tuvo NS > 10% | Veces más probable |
|---|---|---|---|---|
| 2012 | 2009 | 0.4% | 0.6% | 1.4× |
| 2015 | 2012 | 10.4% | 15.7% | 1.5× |
| 2018 | 2015 | 12.5% | 17.4% | 1.4× |
| 2021 | 2018 | 8.5% | 12.5% | 1.5× |
| 2024 | 2021 | 11.9% | 17.9% | 1.5× |

## 4. ¿Sesga la abstención medida?

Para cada sección con NS ≤ 5% en la elección anterior del mismo tipo, se compara su abstención
con la esperada (abstención anterior + cambio promedio de su entidad entre secciones limpias).
Si el NS ocultara sobre todo a quienes no votaron, el residuo sería negativo donde hay NS.

| Elección | NS este año | Secciones | Residuo medio (pp) | Error estándar (pp) |
|---|---|---|---|---|
| 2015 | 0% | 55,455 | -0.00 | 0.03 |
| 2015 | 0–5% | 122 | +1.98 | 0.56 |
| 2015 | 5–10% | 84 | +5.81 | 0.74 |
| 2015 | 10–25% | 699 | +2.97 | 0.25 |
| 2015 | 25–50% | 3,011 | +0.75 | 0.14 |
| 2015 | 50–99.9% | 890 | +0.05 | 0.49 |
| 2018 | 0% | 56,636 | -0.00 | 0.02 |
| 2018 | 0–5% | 135 | +0.24 | 0.39 |
| 2018 | 5–10% | 159 | +1.05 | 0.40 |
| 2018 | 10–25% | 1,120 | +0.67 | 0.14 |
| 2018 | 25–50% | 3,760 | +0.05 | 0.09 |
| 2018 | 50–99.9% | 990 | +0.15 | 0.20 |
| 2021 | 0% | 55,128 | +0.00 | 0.04 |
| 2021 | 0–5% | 214 | -0.79 | 0.57 |
| 2021 | 5–10% | 99 | +0.87 | 0.65 |
| 2021 | 10–25% | 634 | +0.57 | 0.33 |
| 2021 | 25–50% | 2,290 | +0.17 | 0.17 |
| 2021 | 50–99.9% | 579 | +0.13 | 0.43 |
| 2024 | 0% | 51,725 | +0.00 | 0.02 |
| 2024 | 0–5% | 177 | -0.89 | 0.30 |
| 2024 | 5–10% | 105 | +1.19 | 0.47 |
| 2024 | 10–25% | 857 | +0.74 | 0.17 |
| 2024 | 25–50% | 3,050 | +0.31 | 0.10 |
| 2024 | 50–99.9% | 851 | +0.44 | 0.24 |

Promedio ponderado: +0.44 pp con NS entre 10% y 99.9%,
frente a -0.00 pp con NS ≤ 5%. El residuo es positivo y pequeño: donde hay NS
se mide un poco más de abstención de la esperada, no menos. El NS no esconde sobre todo a quienes no votaron;
si acaso, la abstención de esas secciones estaría ligeramente sobrestimada. La magnitud (décimas de punto,
salvo 2015) es mucho menor que la distancia entre umbrales del semáforo (q50 a q80 ≈ 8 pp).

## 5. Impacto en el semáforo 2027

El filtro de NS deja fuera 9,199 secciones comparables. Con los umbrales congelados del semáforo
(q50 42.8%, q80 51.1%), su nivel indicativo sería:

| Nivel | Semáforo oficial | Excluidas por NS |
|---|---|---|
| BAJO | 50.0% | 43.1% |
| MEDIO | 30.0% | 29.5% |
| ALTO | 20.0% | 27.4% |

Entidades que más pierden por el filtro:

| Entidad | Comparables | Excluidas por NS | % |
|---|---|---|---|
| CHIAPAS | 1,847 | 585 | 31.7% |
| CAMPECHE | 479 | 139 | 29.0% |
| NUEVO LEON | 2,603 | 614 | 23.6% |
| CHIHUAHUA | 2,637 | 590 | 22.4% |
| SONORA | 1,359 | 303 | 22.3% |

Por tipo de sección: M 19.9%, R 11.2%, U 14.9% excluidas.

Sensibilidad al umbral (los percentiles se recalculan sobre cada universo):

| Umbral NS | Secciones | q80 | ALTO | ALTO oficial que sigue ALTO | ALTO nuevas |
|---|---|---|---|---|---|
| 5% | 54,582 | 51.0% | 10,917 | 100.0% | 75 |
| 10% | 54,772 | 51.1% | 10,955 | 100.0% | 0 |
| 15% | 55,122 | 51.1% | 11,025 | 99.1% | 173 |
| 20% | 55,631 | 51.2% | 11,126 | 98.4% | 349 |
| 25% | 56,455 | 51.2% | 11,291 | 97.7% | 591 |
| 50% | 62,339 | 51.4% | 12,468 | 95.1% | 2,048 |
| 100% | 63,971 | 51.4% | 12,794 | 94.7% | 2,417 |

## Conclusiones

1. **El NS viene de casillas completas, no de personas.** Las fracciones se amontonan en 1/2, 1/3 y 1/4
   y, dentro de cada sección, todas las edades y ambos sexos pierden la misma proporción.
2. **No es aleatorio entre secciones.** Afecta más a secciones grandes, mixtas y con más abstención,
   y a ciertas entidades; la repetición en la misma sección es moderada.
3. **No sesga de forma relevante la abstención medida.** Las personas que sí se registraron son una
   muestra por apellido de la sección; el residuo es de décimas de punto y en dirección opuesta a
   la temida (no hay abstención escondida).
4. **Pero el filtro de NS > 10% sí sesga el semáforo.** Las secciones excluidas son más de riesgo:
   27.4% serían ALTO (vs. 20%) y 15.6% Top10 (vs. 10%).
5. **Relajar el umbral cambia poco el ranking y recupera cobertura.** Con 25% entran
   1,683 secciones más y
   97.7% de las ALTO oficiales siguen en ALTO.

Propuesta para discutir en el equipo (no se aplicó; el universo `primary_clean10` sigue igual):
en vez de excluir por NS, incluir las secciones con NS parcial marcadas como "estimación con
menos registros", o subir el umbral a 25%. Las 100% NS no tienen abstención calculable y
seguirían fuera.
