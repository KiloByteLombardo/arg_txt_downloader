# ARG TXT Downloader

Automatización de descarga de archivos TXT de facturas desde portales de proveedores farmacéuticos.

## 🎯 Descripción

Este proyecto automatiza:
1. Leer un archivo Excel ("Análisis REIM") con números de factura
2. Iniciar sesión en portales de proveedores
3. Buscar y descargar archivos TXT de cada factura
4. Subir los archivos a Google Drive

## 📁 Estructura del Proyecto

```
arg_txt_downloader/
├── credentials/
│   └── google_service_account.json  # Credenciales de Google
├── src/
│   ├── scraper/
│   │   ├── base_scraper.py     # Clase base
│   │   └── suizo_scraper.py    # Scraper de Suizo
│   ├── storage/
│   │   └── google_drive.py     # Integración con Drive
│   └── utils/
│       └── excel_reader.py     # Lector de Excel
├── main.py                     # API Flask
├── Dockerfile                  # Para Cloud Run
└── requirements.txt
```

## 🚀 Instalación Local

### 1. Crear entorno virtual

```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurar variables de entorno

```bash
# Windows PowerShell
$env:SUIZO_USERNAME="tu_usuario"
$env:SUIZO_PASSWORD="tu_contraseña"
$env:GOOGLE_DRIVE_FOLDER_ID="id_de_carpeta_drive"
```

### 4. Ejecutar

```bash
python main.py
```

## 📡 API Endpoints

### Health Check
```
GET /
```

### Procesar Excel
```
POST /api/process
Content-Type: multipart/form-data

file: [archivo Excel]

Query params:
- dry_run: true/false - Solo analizar sin descargar
```

### Probar Excel
```
POST /api/test-excel
Content-Type: multipart/form-data

file: [archivo Excel]
```

## 📊 Formato del Excel

El archivo Excel debe tener las columnas:
- **Proveedor**: Nombre del proveedor (Suizo, Del Sud, Monroe)
- **Documento Asociado**: Formato `A-XXXX-YYYYYYYY` (se extrae YYYYYYYY)
- **Observación**: Filtrar por "Cargar txt"

## 🐳 Deploy en Cloud Run

```bash
# Build
gcloud builds submit --tag gcr.io/[PROJECT_ID]/arg-txt-downloader

# Deploy
gcloud run deploy arg-txt-downloader \
  --image gcr.io/[PROJECT_ID]/arg-txt-downloader \
  --platform managed \
  --memory 2Gi \
  --timeout 3600 \
  --set-env-vars "SUIZO_USERNAME=xxx,SUIZO_PASSWORD=xxx"
```

## 👥 Proveedores

| Proveedor | Estado |
|-----------|--------|
| Suizo Argentina | 🟡 En desarrollo |
| Del Sud | ⚪ Pendiente |
| Monroe | ⚪ Pendiente |
