# Subir el proyecto a GitHub

## Recomendación

Mantener el repositorio **privado** durante el desarrollo.

No añadir una licencia open source hasta revisar las condiciones de cesión de derechos del concurso.

## 1. Verificar Git

En PowerShell:

```powershell
git --version
```

## 2. Ir a la raíz del proyecto

```powershell
cd "C:\Users\guill\OneDrive\Documentos\hackathon_ine"
```

## 3. Inicializar Git

```powershell
git init
git branch -M main
```

## 4. Revisar que `.gitignore` funcione

```powershell
git status
```

No deben aparecer:

- `.venv/`
- ZIP de `data/raw/`
- Parquet de `data/interim/`
- datasets pesados de `data/processed/`
- `reports/*/predictions/`
- PDF de `docs/`

## 5. Añadir archivos

```powershell
git add .
git status
```

Revisar otra vez antes de crear el commit.

## 6. Primer commit

```powershell
git commit -m "Initial reproducible CCPC pipeline and temporal backtesting"
```

## 7. Crear el repositorio en GitHub

Nombre sugerido:

```text
hackathon-ine-riesgo-abstencion
```

Configuración recomendada:

```text
Visibility: Private
Initialize with README: No
Add .gitignore: No
Choose a license: No license
```

El README y `.gitignore` ya existen localmente.

## 8. Vincular el repositorio

GitHub mostrará la URL del repositorio. Sustituir `TU_USUARIO`:

```powershell
git remote add origin https://github.com/TU_USUARIO/hackathon-ine-riesgo-abstencion.git
git push -u origin main
```

## 9. Verificar

Abrir el repositorio y comprobar que aparecen:

- `src/`
- `reports/`
- `README.md`
- `requirements.txt`
- `.gitignore`
- `data/README.md`
- `docs/README.md`

y que **no** aparecen los archivos grandes excluidos.

## Commits posteriores

Después de nuevas etapas:

```powershell
git status
git add .
git commit -m "Describe aquí el cambio"
git push
```
