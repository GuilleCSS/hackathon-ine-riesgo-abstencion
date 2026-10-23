# Descomposición de la abstención por edad

Generado por `src/descomposicion_edad/01_descomponer_edad.py` desde los ZIP originales (curva por
edad simple) y la base maestra (grupos de edad por sección). Abstención = NV / (SV + NV).

## 1. La curva de participación por edad

| Año | 18 | 19 | 20 | 25 | 30 | 40 | 50 | 60 | 70 | 80 | 90+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2009 (inter.) | 51% | 59% | 62% | 66% | 64% | 55% | 47% | 42% | 42% | 54% | 88% |
| 2012 (presi.) | 33% | 41% | 44% | 48% | 47% | 35% | 29% | 26% | 27% | 39% | 71% |
| 2015 (inter.) | 51% | 59% | 62% | 65% | 63% | 51% | 45% | 39% | 37% | 48% | 78% |
| 2018 (presi.) | 35% | 43% | 45% | 48% | 44% | 36% | 31% | 27% | 27% | 38% | 71% |
| 2021 (inter.) | 44% | 51% | 56% | 60% | 59% | 49% | 41% | 35% | 31% | 42% | 74% |
| 2024 (presi.) | 39% | 47% | 50% | 53% | 50% | 41% | 34% | 28% | 24% | 33% | 67% |

Abstención por grupo y su peso entre quienes tienen participación conocida:

| Año | 18–24 | 25–34 | 35–44 | 45–59 | 60+ | Brecha 18–24 vs. 60+ |
|---|---|---|---|---|---|---|
| 2009 | 62.8% (16%) | 63.9% (26%) | 55.7% (22%) | 46.9% (21%) | 47.8% (15%) | +15.1 pp |
| 2012 | 44.3% (17%) | 46.4% (25%) | 36.3% (22%) | 29.1% (22%) | 31.2% (15%) | +13.1 pp |
| 2015 | 61.9% (17%) | 62.5% (24%) | 52.0% (21%) | 44.5% (22%) | 41.8% (16%) | +20.1 pp |
| 2018 | 45.2% (16%) | 44.7% (23%) | 36.5% (20%) | 30.6% (23%) | 31.6% (17%) | +13.7 pp |
| 2021 | 56.0% (15%) | 58.6% (23%) | 49.6% (20%) | 40.3% (24%) | 36.8% (18%) | +19.2 pp |
| 2024 | 49.6% (15%) | 50.4% (22%) | 41.9% (19%) | 33.3% (24%) | 28.6% (19%) | +21.0 pp |

## 2. ¿Por qué cambió la abstención? (Kitagawa)

Composición = efecto de que cambie el peso de cada grupo (el electorado envejece).
Comportamiento = efecto de que cada grupo se abstenga más o menos. Suman el cambio total.

| Periodo | Tipo | Abstención | Cambio | Composición | Comportamiento |
|---|---|---|---|---|---|
| 2009→2015 | intermedia | 55.9% → 52.9% | -3.01 pp | -0.29 pp | -2.73 pp |
| 2015→2021 | intermedia | 52.9% → 48.2% | -4.76 pp | -0.59 pp | -4.18 pp |
| 2009→2021 | intermedia | 55.9% → 48.2% | -7.78 pp | -0.86 pp | -6.92 pp |
| 2012→2018 | presidencial | 37.9% → 37.6% | -0.28 pp | -0.47 pp | +0.19 pp |
| 2018→2024 | presidencial | 37.6% → 40.3% | +2.70 pp | -0.46 pp | +3.16 pp |
| 2012→2024 | presidencial | 37.9% → 40.3% | +2.41 pp | -1.07 pp | +3.48 pp |

Contribución de cada grupo al comportamiento (pp):

| Periodo | 18–24 | 25–34 | 35–44 | 45–59 | 60+ |
|---|---|---|---|---|---|
| 2009→2015 | -0.15 | -0.35 | -0.81 | -0.51 | -0.91 |
| 2015→2021 | -0.95 | -0.92 | -0.48 | -0.97 | -0.84 |
| 2009→2021 | -1.06 | -1.30 | -1.29 | -1.48 | -1.78 |
| 2012→2018 | +0.16 | -0.43 | +0.05 | +0.35 | +0.05 |
| 2018→2024 | +0.69 | +1.31 | +1.07 | +0.63 | -0.54 |
| 2012→2024 | +0.85 | +0.95 | +1.16 | +0.96 | -0.45 |

## 3. ¿Cuánto explica la edad las diferencias entre secciones?

Abstención esperada de cada sección si cada grupo de edad votara como el promedio nacional del año.

| Año | Secciones | Desviación de la observada | Desviación de la esperada por edad | R² |
|---|---|---|---|---|
| 2009 | 63,930 | 11.4 pp | 1.1 pp | 0.036 |
| 2012 | 65,517 | 9.0 pp | 0.9 pp | 0.101 |
| 2015 | 66,320 | 12.8 pp | 1.3 pp | 0.056 |
| 2018 | 65,891 | 10.1 pp | 0.9 pp | 0.097 |
| 2021 | 67,119 | 12.8 pp | 1.4 pp | 0.107 |
| 2024 | 68,651 | 10.5 pp | 1.4 pp | 0.136 |

Entidades con más abstención de la que explica su estructura de edad (2024):

| Entidad | Observada | Esperada por edad | No explicada | Brecha 18–24 vs. 60+ |
|---|---|---|---|---|
| BAJA CALIFORNIA | 53.0% | 40.5% | +12.5 pp | +18.2 pp |
| SONORA | 50.4% | 40.1% | +10.3 pp | +26.7 pp |
| CHIHUAHUA | 48.1% | 40.3% | +7.9 pp | +19.8 pp |
| DURANGO | 46.3% | 40.2% | +6.1 pp | +16.7 pp |
| MICHOACAN | 46.0% | 40.0% | +6.0 pp | +15.6 pp |
| BAJA CALIFORNIA SUR | 46.9% | 40.9% | +6.0 pp | +28.2 pp |
| SINALOA | 45.5% | 40.0% | +5.5 pp | +26.8 pp |
| TAMAULIPAS | 44.6% | 39.9% | +4.7 pp | +19.9 pp |

Y las de menos:

| Entidad | Observada | Esperada por edad | No explicada | Brecha 18–24 vs. 60+ |
|---|---|---|---|---|
| COAHUILA | 35.3% | 40.3% | -5.0 pp | +19.1 pp |
| PUEBLA | 35.7% | 40.8% | -5.1 pp | +20.2 pp |
| CIUDAD DE MEXICO | 30.7% | 39.3% | -8.6 pp | +16.1 pp |
| TLAXCALA | 29.9% | 40.9% | -11.0 pp | +16.9 pp |
| YUCATAN | 28.6% | 40.4% | -11.8 pp | +15.2 pp |

## 4. ¿Las secciones ALTO del semáforo 2027 son más jóvenes?

| Nivel 2027 | Secciones | 18–24 | 60+ | Abstención 2021 | Esperada por edad 2021 |
|---|---|---|---|---|---|
| BAJO | 27,386 | 14.2% | 21.1% | 36.2% | 47.6% |
| MEDIO | 16,431 | 14.8% | 18.1% | 51.2% | 48.0% |
| ALTO | 10,955 | 16.3% | 14.7% | 62.9% | 48.8% |

La brecha de abstención 2021 entre ALTO y BAJO es de 26.7 pp; la estructura de edad
explica 1.3 pp (4.7%).

## 5. Brecha por sexo

Abstención de hombres menos la de mujeres (pp; positivo = los hombres se abstienen más):

| Año | Nacional | 18 | 20 | 25 | 30 | 40 | 50 | 60 | 70 | 80 | 90+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2009 | +6.8 | +5.6 | +7.8 | +10.1 | +10.9 | +9.0 | +6.2 | +1.2 | -4.1 | -8.7 | -4.7 |
| 2012 | +8.3 | +5.6 | +7.6 | +11.3 | +12.6 | +10.6 | +7.8 | +2.7 | -2.1 | -7.4 | -9.7 |
| 2015 | +7.9 | +5.7 | +7.3 | +9.7 | +11.5 | +10.9 | +8.0 | +3.3 | -1.7 | -7.8 | -8.2 |
| 2018 | +8.1 | +5.2 | +7.6 | +10.7 | +11.8 | +11.1 | +8.4 | +3.7 | -0.9 | -6.5 | -8.3 |
| 2021 | +7.9 | +6.3 | +8.2 | +10.3 | +11.1 | +11.1 | +7.6 | +3.3 | -2.3 | -7.8 | -8.0 |
| 2024 | +9.4 | +7.2 | +9.5 | +12.5 | +13.9 | +13.2 | +9.1 | +5.0 | -1.1 | -6.0 | -7.8 |

## 6. Salto a los 65 años

Cambio de abstención de los 64 a los 65 años, frente a la pendiente normal entre un año de edad y el
siguiente (promedio de 61–64 y 67–70):

| Grupo | 2009 | 2012 | 2015 | 2018 | 2021 | 2024 |
|---|---|---|---|---|---|---|
| Total | -0.4 (-0.0) | -0.1 (+0.1) | -0.9 (-0.2) | -0.3 (-0.0) | -1.2 (-0.3) | -2.5 (-0.2) |
| Hombres | -0.3 (-0.3) | -0.3 (-0.2) | -1.1 (-0.4) | -0.4 (-0.3) | -1.5 (-0.6) | -3.1 (-0.5) |
| Mujeres | -0.5 (+0.3) | +0.1 (+0.3) | -0.7 (+0.1) | -0.1 (+0.2) | -0.9 (-0.1) | -2.0 (+0.0) |
| Tipo U | -0.2 (+0.0) | -0.1 (+0.1) | -0.9 (-0.2) | -0.3 (-0.0) | -1.1 (-0.4) | -2.5 (-0.3) |
| Tipo M | -0.6 (-0.1) | -0.3 (+0.1) | -1.0 (-0.1) | -0.2 (+0.0) | -1.3 (-0.3) | -2.8 (-0.2) |
| Tipo R | -1.1 (+0.1) | +0.0 (+0.2) | -1.0 (+0.1) | -0.1 (+0.0) | -1.4 (-0.1) | -2.5 (-0.1) |

Entre paréntesis, la pendiente normal. En 2024 la abstención cae 2.5 pp justo a los 65 años, en hombres,
mujeres y en secciones urbanas, mixtas y rurales; de 2009 a 2018 los saltos son pequeños (−0.1 a −0.9 pp).
Coincide con la edad de
acceso a la Pensión para el Bienestar de las Personas Adultas Mayores, que según la prensa se aplica desde
los 65 años a partir de julio de 2021 (reforma constitucional en 2024). En 2021 ya aparece un salto menor
(−1.2 pp), anterior a ese cambio (la elección fue en junio). Es una asociación, no una prueba causal, y
conviene verificar el calendario del programa con fuentes oficiales.

## Conclusiones

1. **La curva de edad tiene una forma estable.** Los de 18 años votan más que los de 19 a 30 (efecto del
   primer voto), la abstención llega a su máximo cerca de los 25, baja con la edad hasta su mínimo entre los
   61 y 69 años y vuelve a subir en edades avanzadas.
2. **El electorado envejece y eso baja la abstención, pero poco.** De 2009 a 2021 (intermedias) la
   composición explica -0.86 pp de -7.78 pp; de 2012 a 2024 (presidenciales)
   -1.07 pp. Lo demás es comportamiento.
3. **En presidenciales el comportamiento empeoró más de lo que se ve:** +3.48 pp de 2012 a 2024,
   disimulado por el envejecimiento. De 2018 a 2024 subió la abstención en todos los grupos menos en 60+,
   y la brecha entre 18–24 y 60+ llegó a +21.0 pp, la mayor del periodo.
4. **Los hombres se abstienen más que las mujeres**, sobre todo entre los 20 y los 50 años
   (hasta +14.1 pp a los 29 en 2024); la brecha se cierra cerca de los 70 y se
   invierte en edades avanzadas.
5. **La edad explica poco las diferencias entre territorios.** La abstención esperada por la estructura de
   edad varía 1–1.4 pp entre secciones contra 9–13 pp de la observada (R² ≤ 0.14). Entre las secciones
   ALTO y BAJO de 2027 hay 26.7 pp de diferencia, y la edad explica 1.3 pp. El riesgo
   territorial depende sobre todo del lugar, no de que su población sea joven.
6. **La abstención cae de golpe a los 65 años desde 2021** (−2.5 pp en 2024; antes, como mucho −0.9 pp),
   la edad de acceso a la pensión universal para adultos mayores. Es una asociación por verificar.

Implicaciones: (a) la edad no aporta al modelo territorial 2027 (coherente con que la historia de cada
sección domine); (b) sí sirve para explicar cambios nacionales y para focalizar mensajes por grupo: jóvenes
de 19 a 34 años y hombres son quienes más se abstienen en todas las elecciones.
