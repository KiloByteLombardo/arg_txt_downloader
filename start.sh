#!/bin/bash
# Script de inicio para Cloud Run
# Lanza xvfb (display virtual) y luego gunicorn

echo "[START] Iniciando xvfb en display :99..."
Xvfb :99 -screen 0 1920x1080x24 &
sleep 2

echo "[START] xvfb iniciado, lanzando gunicorn..."
exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
