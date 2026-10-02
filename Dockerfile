FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ponytail: el código, data/ y reports/ entran por el volumen de compose (.:/app);
# añadir COPY src/ dashboard/ reports/ si algún día se despliega la imagen sola.
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.headless=true"]
