# ARG TXT Downloader

Automatización de descarga de archivos TXT de facturas desde portales de proveedores farmacéuticos.

## 🎯 Descripción

Este proyecto automatiza:
1. Leer un archivo Excel ("Análisis REIM") con números de factura
2. Iniciar sesión en portales de proveedores (Suizo, Del Sud, Monroe)
3. Buscar y descargar archivos TXT de cada factura
4. Subir los archivos a Google Drive
5. Guardar logs y screenshots de errores en Google Cloud Storage

## 📁 Estructura del Proyecto

```
arg_txt_downloader/
├── credentials/
│   └── google_service_account.json  # Credenciales de Google
├── src/
│   ├── scraper/
│   │   ├── base_scraper.py     # Clase base con logging a GCS
│   │   └── suizo_scraper.py    # Scraper de Suizo Argentina
│   ├── storage/
│   │   ├── google_drive.py     # Integración con Google Drive
│   │   └── gcs.py              # Integración con Cloud Storage
│   ├── utils/
│   │   └── excel_reader.py     # Lector de Excel
│   └── models.py               # Modelos de respuesta API
├── main.py                     # API Flask
├── test_scraper.py             # Script de pruebas local
├── Dockerfile                  # Para Cloud Run
├── docker-compose.yml          # Para desarrollo local
├── requirements.txt
└── env.example                 # Variables de entorno ejemplo
```

---

## 🐳 Ejecución con Docker Compose (Recomendado)

### 1. Configurar variables de entorno

```bash
cp env.example .env
# Editar .env con tus credenciales
```

### 2. Colocar credenciales de Google

Coloca tu archivo `google_service_account.json` en la carpeta `credentials/`

### 3. Ejecutar

```bash
# Producción
docker-compose up arg-txt-downloader

# Desarrollo (con hot-reload del código)
docker-compose --profile dev up arg-txt-downloader-dev
```

### 4. Probar

```bash
# Health check
curl http://localhost:8080/

# Probar Excel
curl -X POST -F "file=@mi_archivo.xlsx" http://localhost:8080/api/test-excel

# Procesar (dry-run)
curl -X POST -F "file=@mi_archivo.xlsx" "http://localhost:8080/api/process?dry_run=true"

# Procesar completo
curl -X POST -F "file=@mi_archivo.xlsx" http://localhost:8080/api/process
```

---

## 🚀 Instalación Local (Sin Docker)

### 1. Crear entorno virtual

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurar variables de entorno

```powershell
# Windows PowerShell
$env:SUIZO_USERNAME="tu_usuario"
$env:SUIZO_PASSWORD="tu_contraseña"
$env:GOOGLE_DRIVE_FOLDER_ID="id_de_carpeta_drive"
$env:GCS_BUCKET_NAME="tu-bucket"  # Opcional
```

### 4. Ejecutar

```bash
python main.py
```

### 5. Probar scraper interactivamente

```bash
python test_scraper.py
```

---

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
- provider: suizo|del_sud|monroe - Filtrar por proveedor
```

**Respuesta:**
```json
{
  "status": "completed",
  "results": {
    "execution_id": "20240113_143022",
    "processed": 10,
    "successful": 8,
    "failed": 2,
    "details": [...],
    "logs": {
      "execution_log_url": "https://storage.googleapis.com/bucket/logs/...",
      "screenshots": [
        {"name": "error_login", "url": "https://..."}
      ]
    }
  }
}
```

### Probar Excel
```
POST /api/test-excel
Content-Type: multipart/form-data

file: [archivo Excel]
```

---

## 📊 Formato del Excel

El archivo Excel debe tener las columnas:
- **Proveedor**: Nombre del proveedor (Suizo, Del Sud, Monroe)
- **Documento Asociado**: Formato `A-XXXX-YYYYYYYY` (se extrae YYYYYYYY)
- **Observación**: Debe decir "Cargar txt"

---

## ☁️ Deploy en Cloud Run

### Build y Deploy

```bash
# Build
gcloud builds submit --tag gcr.io/[PROJECT_ID]/arg-txt-downloader

# Deploy
gcloud run deploy arg-txt-downloader \
  --image gcr.io/[PROJECT_ID]/arg-txt-downloader \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --timeout 3600 \
  --set-env-vars "SUIZO_USERNAME=xxx,SUIZO_PASSWORD=xxx,GOOGLE_DRIVE_FOLDER_ID=xxx,GCS_BUCKET_NAME=xxx"
```

### Configurar Secret Manager (Recomendado)

```bash
# Crear secretos
echo -n "tu_usuario" | gcloud secrets create suizo-username --data-file=-
echo -n "tu_password" | gcloud secrets create suizo-password --data-file=-

# Deploy con secretos
gcloud run deploy arg-txt-downloader \
  --image gcr.io/[PROJECT_ID]/arg-txt-downloader \
  --set-secrets "SUIZO_USERNAME=suizo-username:latest,SUIZO_PASSWORD=suizo-password:latest"
```

---

## 👥 Proveedores

| Proveedor | Estado | URL |
|-----------|--------|-----|
| Suizo Argentina | 🟡 En desarrollo | https://web1.suizoargentina.com |
| Del Sud | ⚪ Pendiente | - |
| Monroe | ⚪ Pendiente | - |

---

## 📝 Logs y Debugging

Los logs y screenshots de errores se guardan en:

- **Local**: `./downloads/`
- **GCS** (si está configurado): 
  - Logs: `gs://tu-bucket/logs/`
  - Screenshots: `gs://tu-bucket/screenshots/suizo/`

Para ver los logs en tu frontend, usa las URLs retornadas en `results.logs`.
