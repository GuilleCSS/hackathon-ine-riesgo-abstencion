# Brecha intermedia vs. presidencial

Generado por `src/brecha_tipo/01_brecha_intermedia_presidencial.py`. Brecha = abstención en la elección
intermedia − abstención en la presidencial contigua (pp). Positiva = más gente vota cuando hay elección
presidencial. Por sección sólo se usan pares con NS ≤ 10% en ambas elecciones.

## 1. Tamaño y evolución

| Par | Abstención intermedia | Abstención presidencial | Brecha |
|---|---|---|---|
| 2009–2012 | 55.9% | 37.9% | +18.0 pp |
| 2015–2012 | 52.9% | 37.9% | +15.0 pp |
| 2015–2018 | 52.9% | 37.6% | +15.3 pp |
| 2021–2018 | 48.2% | 37.6% | +10.5 pp |
| 2021–2024 | 48.2% | 40.3% | +7.8 pp |

Por grupo (brecha en pp):

| Grupo | 2009–2012 | 2015–2012 | 2015–2018 | 2021–2018 | 2021–2024 |
|---|---|---|---|---|---|
| Urbana | +18.8 | +16.8 | +17.1 | +11.9 | +9.8 |
| Mixta | +16.7 | +12.9 | +13.0 | +9.2 | +5.7 |
| Rural | +16.1 | +9.7 | +10.2 | +6.3 | +1.7 |
| Hombres | +17.2 | +14.8 | +15.2 | +10.4 | +7.0 |
| Mujeres | +18.7 | +15.2 | +15.4 | +10.7 | +8.6 |
| 18–24 | +18.5 | +17.6 | +16.7 | +10.8 | +6.4 |
| 25–34 | +17.5 | +16.1 | +17.9 | +14.0 | +8.2 |
| 35–44 | +19.4 | +15.7 | +15.4 | +13.1 | +7.7 |
| 45–59 | +17.8 | +15.5 | +13.9 | +9.7 | +7.0 |
| 60+ | +16.6 | +10.6 | +10.3 | +5.3 | +8.2 |

## 2. Entre secciones

| Par | Secciones | Mediana | P10 | P90 | Brecha negativa |
|---|---|---|---|---|---|
| 2009–2012 | 60,957 | +18.1 pp | +6.4 | +28.3 | 1.5% |
| 2015–2012 | 58,382 | +15.2 pp | +0.0 | +26.2 | 9.9% |
| 2015–2018 | 53,963 | +15.8 pp | -1.0 | +28.4 | 12.1% |
| 2021–2018 | 54,531 | +9.0 pp | -0.3 | +18.7 | 10.6% |
| 2021–2024 | 55,171 | +7.2 pp | -4.1 | +16.9 | 20.2% |

Persistencia: la correlación (Spearman) entre la brecha 2015–2018 y la 2021–2024 de la misma sección es
0.33: la brecha depende más de cada elección que de la sección.

## 3. ¿Dónde es mayor? (2021–2024, mediana en pp)

| Variable | Categoría | Secciones | Mediana |
|---|---|---|---|
| Tipo de sección | Mixta | 4,750 | +3.0 |
| Tipo de sección | Rural | 15,002 | +0.8 |
| Tipo de sección | Urbana | 35,419 | +9.7 |
| Tamaño (lista nominal) | Q1 más chicas | 11,060 | +3.3 |
| Tamaño (lista nominal) | Q2 | 11,041 | +6.8 |
| Tamaño (lista nominal) | Q3 | 11,010 | +8.3 |
| Tamaño (lista nominal) | Q4 | 11,029 | +8.9 |
| Tamaño (lista nominal) | Q5 más grandes | 11,031 | +8.8 |
| Jóvenes 18–24 (quintil) | Q1 menos jóvenes | 11,036 | +7.4 |
| Jóvenes 18–24 (quintil) | Q2 | 11,033 | +7.9 |
| Jóvenes 18–24 (quintil) | Q3 | 11,035 | +7.6 |
| Jóvenes 18–24 (quintil) | Q4 | 11,033 | +6.7 |
| Jóvenes 18–24 (quintil) | Q5 más jóvenes | 11,034 | +6.2 |
| Abstención 2021 (quintil) | Q1 menos abstención | 11,035 | -0.7 |
| Abstención 2021 (quintil) | Q2 | 11,034 | +4.8 |
| Abstención 2021 (quintil) | Q3 | 11,034 | +7.9 |
| Abstención 2021 (quintil) | Q4 | 11,034 | +10.3 |
| Abstención 2021 (quintil) | Q5 más abstención | 11,034 | +11.9 |

## 4. ¿La explica la concurrencia local?

MCO de la brecha por entidad y par (32 × 5) sobre las banderas del calendario, con efectos fijos de par.
Error estándar e intervalo al 90% por bootstrap de entidades (1,000 réplicas). Calendario pendiente de validar.

| Variable | Efecto (pp) | Error estándar | IC 90% |
|---|---|---|---|
| gob_intermedia | -5.49 | 1.55 | [-7.73, -2.65] |
| gob_presidencial | +0.44 | 1.82 | [-2.10, +3.65] |
| local_intermedia | -10.41 | 1.88 | [-13.73, -7.55] |
| local_presidencial | +2.98 | 1.40 | [+0.67, +5.25] |

Las banderas se traslapan (toda gubernatura concurrente implica elección local concurrente): en el modelo descriptivo, una entidad
con elecciones locales y gubernatura el mismo día que la intermedia se asocia con una brecha 15.9 pp menor.

Entidades con elecciones locales y gubernaturas el mismo día que la federal:

| Año | 2009 | 2012 | 2015 | 2018 | 2021 | 2024 | 2027 |
|---|---|---|---|---|---|---|---|
| Locales | 11 | 15 | 16 | 30 | 32 | 32 | 32 |
| Gubernaturas | 6 | 7 | 9 | 9 | 15 | 9 | 17 |

Entre 2009–2012 y 2021–2024 la brecha promedio de las entidades cambió -10.6 pp;
bajo este modelo descriptivo, -6.8 pp (64%) se asocian con que más entidades
empataron sus elecciones locales con las federales. Es una estimación gruesa (32 entidades × 5 pares, sin ponderar
por población) y no identifica un efecto causal del calendario.

## 5. Implicaciones para 2027

Brecha 2021–2024 por nivel del semáforo 2027:

| Nivel | Secciones | Mediana | Media |
|---|---|---|---|
| BAJO | 27,386 | +3.6 pp | +3.4 pp |
| MEDIO | 16,431 | +9.5 pp | +9.4 pp |
| ALTO | 10,955 | +10.9 pp | +11.1 pp |

2 entidades cambian su situación de gubernatura concurrente entre 2021 y 2027; el modelo 2027
no usa concurrencia, así que ahí el contexto de 2027 será distinto al de la intermedia que más pesa (2021):

| Entidad | Gubernatura 2021 | Gubernatura 2024 | Gubernatura 2027 |
|---|---|---|---|
| AGUASCALIENTES | no | no | sí |
| QUINTANA ROO | no | no | sí |

## Conclusiones

1. **La brecha se cerró a menos de la mitad:** de +18.0 pp (2009–2012) a
   +7.8 pp (2021–2024). Las intermedias bajaron su abstención y la presidencial de 2024 la subió.
2. **Ya no es universal:** en 2021–2024, 20% de las secciones se abstuvieron más en la presidencial
   que en la intermedia. La brecha es grande en secciones urbanas y casi nula en las rurales.
3. **Es poco persistente** (Spearman 0.33): depende más del contexto de cada elección que de la sección.
4. **El calendario local está asociado con la brecha.** En el modelo descriptivo, elecciones locales el mismo día que la intermedia
   se asocian con una brecha 10.4 pp menor y una gubernatura con 5.5 pp adicionales;
   la fracción asociada al cambio de calendario equivale a cerca de 64% del cierre observado. No es una estimación causal.
5. **Para 2027:** las secciones ALTO del semáforo son las de mayor brecha (votan sobre todo en presidenciales),
   lo que refuerza su riesgo en una intermedia. Habrá 17 gubernaturas concurrentes (15 en 2021); Aguascalientes
   y Quintana Roo tendrán gubernatura el mismo día y en 2021 no; el modelo no usa concurrencia.

El resumen del calendario 2027 debe mantenerse contrastado con la información oficial del INE y los OPLE; las asociaciones históricas no son causales.
