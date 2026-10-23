# Imagen fijada por digest: una actualización de la base es un cambio explícito.
# Para subir de versión: docker pull python:3.12.X-slim y copiar el nuevo digest.
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

# tippecanoe genera las teselas vectoriales (PMTiles) del sitio web (src/21).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tippecanoe \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir "pip==26.2.1" \
    && pip install --no-cache-dir -r requirements.txt

# ponytail: el código, data/ y reports/ entran por el volumen de compose (.:/app);
# añadir COPY src/ dashboard/ reports/ si algún día se despliega la imagen sola.
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.headless=true"]
