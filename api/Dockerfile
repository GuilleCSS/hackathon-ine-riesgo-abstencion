# Imagen mínima de la API: sólo FastAPI, uvicorn y DuckDB (sin streamlit, sklearn, etc.).
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

COPY requirements.txt /tmp/requirements.txt
# --uploaded-prior-to P7D: también las dependencias indirectas deben tener 7 días publicadas.
RUN pip install --no-cache-dir "pip==26.2.1" \
    && pip install --no-cache-dir --uploaded-prior-to P7D -r /tmp/requirements.txt \
    && useradd --create-home api

USER api
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
