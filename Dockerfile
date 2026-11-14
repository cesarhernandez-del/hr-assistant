# Imagen del HR Assistant: Python 3.12 slim, sin root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Primero las dependencias, para aprovechar la caché de capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Solo lo que el servicio necesita para correr
COPY app ./app
COPY data ./data

# Usuario sin privilegios
RUN useradd --system --no-create-home --uid 10001 appuser \
    && chown -R appuser /srv
USER appuser

# Render inyecta PORT; en local se usa 8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
