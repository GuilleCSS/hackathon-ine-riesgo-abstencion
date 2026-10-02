from pathlib import Path
import importlib
import sys
import zipfile
import re

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "docs"
REPORTS = ROOT / "reports" / "audit"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"
DASHBOARD = ROOT / "dashboard"
NOTEBOOKS = ROOT / "notebooks"

YEARS = [2009, 2012, 2015, 2018, 2021, 2024]
EXPECTED_COLS = [
    "AELEC", "FELECCION", "EDOCVE", "EDONOM", "MPIOCVE", "MPIONOM",
    "SECCION", "TIPOSEC", "DEF", "DEL", "SEXO", "EDAD", "LN", "SV", "NV", "NS"
]


def fail(msg: str) -> None:
    print(f"[ERROR] {msg}")


def ok(msg: str) -> None:
    print(f"[OK]    {msg}")


def warn(msg: str) -> None:
    print(f"[AVISO] {msg}")


def main() -> int:
    print("\n=== Verificación del proyecto CCPC ===")
    print(f"Raíz detectada: {ROOT}\n")

    errors = 0

    # 1) Python
    if sys.version_info >= (3, 10):
        ok(f"Python {sys.version.split()[0]}")
    else:
        fail("Se recomienda Python 3.10 o superior.")
        errors += 1

    # 2) Carpetas
    required_dirs = [RAW, REPORTS, INTERIM, PROCESSED, MODELS, DASHBOARD, NOTEBOOKS]
    for d in required_dirs:
        if d.exists():
            ok(f"Carpeta: {d.relative_to(ROOT)}")
        else:
            fail(f"Falta carpeta: {d.relative_to(ROOT)}")
            errors += 1

    if DOCS.exists():
        ok("Carpeta: docs")
    else:
        warn("No existe docs/. No impide ejecutar la pipeline, pero conviene guardar ahí manual y convocatoria.")

    # 3) Dependencias
    packages = ["pandas", "numpy", "pyarrow", "sklearn", "matplotlib"]
    for package in packages:
        try:
            module = importlib.import_module(package)
            version = getattr(module, "__version__", "instalado")
            ok(f"Dependencia {package}: {version}")
        except Exception:
            fail(f"No se pudo importar {package}. Ejecuta: pip install -r requirements.txt")
            errors += 1

    # 4) ZIPs
    print("\n--- Revisando ZIPs ---")
    for year in YEARS:
        path = RAW / f"DatosAbiertos_DECEyEC_ConteosCensales{year}.zip"
        if not path.exists():
            fail(f"Falta {path.name}")
            errors += 1
            continue

        try:
            with zipfile.ZipFile(path) as zf:
                csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                txts = [n for n in zf.namelist() if n.lower().endswith(".txt")]
                if len(csvs) != 32:
                    fail(f"{year}: se esperaban 32 CSV y se encontraron {len(csvs)}")
                    errors += 1
                else:
                    ok(f"{year}: 32 CSV encontrados")

                if not txts:
                    warn(f"{year}: no se encontró archivo de descripción de campos")

                # Verifica encabezado del primer CSV sin cargar el archivo completo.
                with zf.open(csvs[0]) as fh:
                    header = fh.readline().decode("utf-8-sig").strip().split(",")
                missing = [c for c in EXPECTED_COLS if c not in header]
                if missing:
                    fail(f"{year}: faltan columnas esperadas en el primer CSV: {missing}")
                    errors += 1
                else:
                    ok(f"{year}: estructura de columnas correcta")
        except zipfile.BadZipFile:
            fail(f"{year}: el archivo ZIP está dañado o no es un ZIP válido")
            errors += 1

    print("\n=== Resultado ===")
    if errors:
        fail(f"Se detectaron {errors} problema(s). Corrígelos antes de continuar.")
        return 1

    ok("La estructura básica está lista. Puedes ejecutar 01_audit_raw.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
