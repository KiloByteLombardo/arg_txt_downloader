# ============================================
# ARG TXT Downloader - Dockerfile para Cloud Run
# Optimizado para Playwright con Chromium + xvfb
# ============================================

FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Establecer directorio de trabajo
WORKDIR /app

# Instalar xvfb para display virtual (necesario para Monroe)
RUN apt-get update && apt-get install -y \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DISPLAY=:99

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

# Crear directorio para credenciales y sesiones
RUN mkdir -p /app/credentials /app/sessions && \
    chmod 777 /app/sessions

# Exponer puerto
EXPOSE 8080

# Script de inicio que lanza xvfb + gunicorn
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Comando de inicio
CMD ["/start.sh"]

