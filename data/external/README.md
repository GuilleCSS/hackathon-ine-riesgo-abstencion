# Datos externos

## `calendario_concurrente.csv`

Para cada estado (`EDOCVE`) y elección federal 2009–2027: si hubo elecciones
locales el mismo día (`LOCAL_CONCURRENTE`) y si incluyeron gubernatura o jefatura
de gobierno (`GUBERNATURA_CONCURRENTE`).

- Generado por `src/clustering/03_build_calendario_concurrente.py` desde
  Wikipedia en español ("Anexo:Elecciones locales de México" y la página de cada
  elección estatal). Cada fila cita su página en `FUENTE`.
- El script falla si el número de gubernaturas por año no coincide con lo
  esperado (6, 7, 9, 9, 15, 9 y 17).
- **Pendiente de validar** (`VALIDADO = pendiente`) contra los calendarios del
  INE y de los institutos electorales locales. Al validar una fila, cambiar a `si`.
