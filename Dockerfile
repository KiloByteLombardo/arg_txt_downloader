# ============================================
# ARG TXT Downloader - Dockerfile para Cloud Run
# Optimizado para Playwright con Chromium
# ============================================

FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Establecer directorio de trabajo
WORKDIR /app

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copiar requirements primero (para cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Crear directorio para descargas temporales
RUN mkdir -p /app/downloads && \
    chmod 777 /app/downloads

# Crear directorio para credenciales
RUN mkdir -p /app/credentials

# Exponer puerto
EXPOSE 8080

# Comando de inicio con Gunicorn
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app

