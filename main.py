"""
ARG TXT Downloader - API Principal
Automatización de descarga de facturas de proveedores farmacéuticos.
"""
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from flask import Flask, request, jsonify
from flask_cors import CORS

from src.utils.excel_reader import ExcelReader, InvoiceRecord
from src.scraper.suizo_scraper import SuizoScraper
from src.scraper.monroe_scraper import MonroeScraper
from src.storage.google_drive import GoogleDriveUploader
from src.utils.tasks import TaskManager, create_task_manager

# Inicializar Flask
app = Flask(__name__)

# Habilitar CORS para todas las rutas y orígenes
CORS(app, resources={r"/*": {"origins": "*"}})

# Directorio temporal para descargas
DOWNLOAD_DIR = os.getenv("DOWNLOAD_PATH", "./downloads")
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Configuración de Batch
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))


def clean_downloads_folder():
    """
    Limpia la carpeta de downloads.
    Solo debe llamarse al inicio del proceso maestro, NO en workers.
    """
    try:
        download_path = Path(DOWNLOAD_DIR)
        if download_path.exists():
            # Eliminar todos los archivos .txt y .png (screenshots)
            for file in download_path.glob("*.txt"):
                file.unlink()
                print(f"[Clean] Eliminado: {file.name}")
            for file in download_path.glob("*.png"):
                file.unlink()
                print(f"[Clean] Eliminado: {file.name}")
            for file in download_path.glob("*.json"):
                file.unlink()
                print(f"[Clean] Eliminado: {file.name}")
            print("[Clean] Carpeta downloads limpiada")
    except Exception as e:
        print(f"[Clean] Error limpiando downloads: {e}")


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check para Cloud Run."""
    return jsonify({
        "status": "healthy",
        "service": "ARG TXT Downloader",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/process", methods=["POST"])
def process_excel():
    """
    Endpoint principal para procesar un archivo Excel.
    Si Cloud Tasks está configurado (WORKER_URL), divide en lotes y encola tareas.
    Si no, procesa localmente (secuencial).
    """
    print("[API] Recibida solicitud de procesamiento")
    
    # Limpiar carpeta de downloads al inicio (solo proceso maestro)
    clean_downloads_folder()
    
    # Verificar archivo
    if 'file' not in request.files:
        return jsonify({"error": "No file", "detail": "Falta archivo Excel"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Archivo vacío"}), 400
    
    # Parámetros opcionales
    provider_filter = request.args.get('provider', None)
    dry_run = request.args.get('dry_run', 'false').lower() == 'true'
    force_local = request.args.get('force_local', 'false').lower() == 'true'
    
    try:
        # Guardar archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name
        
        # Leer Excel
        reader = ExcelReader()
        all_records, by_provider = reader.read_excel(temp_path)
        os.unlink(temp_path) # Limpiar
        
        # Preparar análisis inicial
        analysis = {
            "total_records": len(all_records),
            "by_provider": {k: len(v) for k, v in by_provider.items()}
        }
        
        if dry_run:
            return jsonify({"status": "dry_run", "analysis": analysis})
        
        # Filtrar facturas
        records_to_process = []
        target_providers = [provider_filter] if provider_filter else list(by_provider.keys())
        
        for prov in target_providers:
            if prov in by_provider:
                records_to_process.extend(by_provider[prov])
        
        if not records_to_process:
            return jsonify({"status": "no_records", "analysis": analysis})

        # Decidir si usar Cloud Tasks o Local
        task_manager = create_task_manager()
        use_cloud_tasks = task_manager.is_enabled() and not force_local
        print(f"[API] Cloud Tasks habilitado: {use_cloud_tasks} (force_local={force_local})")
        
        execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if use_cloud_tasks:
            # Estrategia Cloud Tasks (Fan-out)
            return _process_with_cloud_tasks(records_to_process, task_manager, execution_id)
        else:
            # Estrategia Local (Secuencial)
            print("[API] Procesando localmente (Cloud Tasks no configurado o force_local=true)")
            results = process_invoices_local(records_to_process)
            return jsonify({
                "status": "completed",
                "execution_id": execution_id,
                "analysis": analysis,
                "results": results
            })
            
    except Exception as e:
        print(f"[API] Error global: {e}")
        return jsonify({"error": "Error de procesamiento", "detail": str(e)}), 500


def _process_with_cloud_tasks(records: List[InvoiceRecord], task_manager: TaskManager, execution_id: str):
    """Divide las facturas en lotes y crea tareas en Cloud Tasks."""
    # Agrupar por proveedor para mantener contexto
    by_provider = {}
    for r in records:
        if r.provider not in by_provider:
            by_provider[r.provider] = []
        by_provider[r.provider].append(r.invoice_number)
    
    total_tasks = 0
    batches_info = []
    
    for provider, invoices in by_provider.items():
        # Dividir en chunks de BATCH_SIZE
        chunks = [invoices[i:i + BATCH_SIZE] for i in range(0, len(invoices), BATCH_SIZE)]
        total_batches = len(chunks)
        
        for i, chunk in enumerate(chunks):
            success = task_manager.create_invoice_batch_task(
                invoice_numbers=chunk,
                batch_id=i,
                total_batches=total_batches,
                provider=provider,
                execution_id=execution_id
            )
            if success:
                total_tasks += 1
                batches_info.append({
                    "provider": provider,
                    "batch": i+1,
                    "size": len(chunk),
                    "status": "queued"
                })
            else:
                batches_info.append({
                    "provider": provider,
                    "batch": i+1,
                    "status": "failed_to_queue"
                })
    
    return jsonify({
        "status": "queued",
        "execution_id": execution_id,
        "message": f"Se encolaron {total_tasks} tareas para procesamiento paralelo",
        "batches": batches_info
    })


@app.route("/api/worker", methods=["POST"])
def worker_process():
    """
    Endpoint WORKER llamado por Cloud Tasks.
    Recibe un lote de facturas y las procesa.
    """
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Invalid payload"}), 400
            
        invoice_numbers = payload.get("invoice_numbers", [])
        provider = payload.get("provider", "suizo") # Default por ahora
        batch_id = payload.get("batch_id")
        execution_id = payload.get("execution_id")
        
        print(f"[Worker] Procesando lote {batch_id} de {provider} ({len(invoice_numbers)} facturas)")
        
        # Aquí reutilizamos la lógica de procesamiento pero adaptada para lista de strings
        # Reconstruimos objetos InvoiceRecord mínimos si es necesario, o adaptamos process_invoices_local
        
        # Como process_invoices_local espera InvoiceRecord, creamos dummies
        records = [
            InvoiceRecord(
                provider=provider,
                full_document=inv, # No tenemos el doc completo aquí, usamos num
                invoice_number=inv,
                observation="From Worker",
                row_index=0
            ) for inv in invoice_numbers
        ]
        
        # Procesar (pasar execution_id y batch_id para el log)
        results = process_invoices_local(records, execution_id=execution_id, batch_id=batch_id)
        
        return jsonify({
            "status": "success",
            "batch_id": batch_id,
            "execution_id": execution_id,
            "processed": len(records),
            "results": results
        })
        
    except Exception as e:
        print(f"[Worker] Error fatal: {e}")
        return jsonify({"error": str(e)}), 500


def process_invoices_local(
    records: list, 
    upload_to_gcs: bool = True,
    execution_id: str = None,
    batch_id: int = None
) -> Dict[str, Any]:
    """
    Lógica core de procesamiento (Scraper + Drive + GCS).
    Usada tanto por el endpoint local como por el worker.
    
    Args:
        records: Lista de InvoiceRecord
        upload_to_gcs: Subir logs/screenshots a GCS
        execution_id: ID de ejecución (para agrupar logs de múltiples workers)
        batch_id: ID del lote (para diferenciar logs de cada worker)
    """
    if not records:
        return {"processed": 0, "successful": 0, "failed": 0, "details": [], "logs": {}}
    
    invoice_numbers = [r.invoice_number for r in records]
    download_results = []
    upload_results = []
    execution_summary = {}
    log_info = {}
    
    # Determinar proveedor
    provider_name = records[0].provider.lower() if records else "suizo"
    print(f"[Process] Proveedor detectado: {provider_name}")
    
    # Seleccionar scraper según proveedor
    def get_scraper(provider: str):
        """Factory para obtener el scraper correcto."""
        provider_lower = provider.lower()
        
        if "monroe" in provider_lower or "masa" in provider_lower:
            print(f"[Process] Usando MonroeScraper")
            return MonroeScraper(upload_screenshots_to_gcs=upload_to_gcs)
        elif "suizo" in provider_lower:
            print(f"[Process] Usando SuizoScraper")
            return SuizoScraper(upload_screenshots_to_gcs=upload_to_gcs)
        else:
            # Default a Suizo por ahora
            print(f"[Process] Proveedor '{provider}' no reconocido, usando SuizoScraper")
            return SuizoScraper(upload_screenshots_to_gcs=upload_to_gcs)
    
    # Descargar con scraper
    try:
        with get_scraper(provider_name) as scraper:
            download_results = scraper.process_invoices(invoice_numbers)
            execution_summary = scraper.get_execution_summary()
            # Guardar log en formato JSON para el frontend
            log_info = scraper.save_execution_log_json(
                download_results, 
                upload_to_gcs=upload_to_gcs,
                execution_id=execution_id,
                batch_id=batch_id
            )
            
    except Exception as e:
        print(f"[Process] Error del scraper: {e}")
        return {
            "error": f"Error del scraper: {str(e)}",
            "processed": 0,
            "successful": 0,
            "failed": len(records),
            "logs": {}
        }
    
    # Subir archivos exitosos a Google Drive
    successful_downloads = [r for r in download_results if r.success]
    
    if successful_downloads:
        try:
            uploader = GoogleDriveUploader()
            
            # Crear subcarpeta con la fecha de hoy
            today_folder_name = datetime.now().strftime("%Y-%m-%d")
            today_folder_id = uploader.get_or_create_subfolder(today_folder_name)
            
            if today_folder_id:
                print(f"[Drive] Usando carpeta: {today_folder_name}")
            else:
                print(f"[Drive] No se pudo crear carpeta {today_folder_name}, usando carpeta raíz")
            
            # Subir archivos a la carpeta de hoy
            file_paths = [r.file_path for r in successful_downloads if r.file_path]
            upload_results = uploader.upload_files(file_paths, folder_id=today_folder_id)
        except Exception as e:
            print(f"[Process] Error de upload a Drive: {e}")
    
    # Compilar resultados
    details = []
    for download_res in download_results:
        detail = {
            "invoice_number": download_res.invoice_number,
            "download_success": download_res.success,
            "download_error": download_res.error_message,
            "upload_success": False,
            "drive_link": None
        }
        
        if download_res.success and download_res.file_path:
            for upload_res in upload_results:
                if upload_res.file_name in download_res.file_path:
                    detail["upload_success"] = upload_res.success
                    detail["drive_link"] = upload_res.drive_link
                    break
        
        details.append(detail)
    
    successful = sum(1 for d in details if d["download_success"] and d["upload_success"])
    
    return {
        "execution_id": execution_summary.get("execution_id"),
        "processed": len(records),
        "successful": successful,
        "failed": len(records) - successful,
        "details": details,
        "logs": {
            "execution_log_url": log_info.get("gcs_url"),
            "execution_log_local": log_info.get("local_path"),
            "screenshots": execution_summary.get("screenshots", [])
        }
    }


@app.route("/api/test-excel", methods=["POST"])
def test_excel():
    """Endpoint de prueba para validar el formato del Excel."""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name
        
        reader = ExcelReader()
        all_records, by_provider = reader.read_excel(temp_path)
        os.unlink(temp_path)
        
        return jsonify({
            "status": "valid",
            "total_records": len(all_records),
            "by_provider": {k: len(v) for k, v in by_provider.items()},
            "sample_records": [
                {
                    "provider": r.provider,
                    "document": r.full_document,
                    "invoice_number": r.invoice_number
                } for r in all_records[:5]
            ]
        })
    except Exception as e:
        return jsonify({"status": "invalid", "error": str(e)}), 400


@app.route("/api/logs/folders", methods=["GET"])
def list_log_folders():
    """
    Lista las carpetas de logs (fechas) disponibles en el bucket.
    
    Returns:
        {
            "folders": [
                {"date": "2026-01-16", "displayName": "16 Enero 2026"},
                {"date": "2026-01-15", "displayName": "15 Enero 2026"},
                ...
            ]
        }
    """
    try:
        from src.storage.gcs import GCSUploader
        
        uploader = GCSUploader()
        folders = uploader.list_log_folders()
        
        return jsonify({
            "folders": folders,
            "count": len(folders)
        })
        
    except Exception as e:
        print(f"[API] Error listando carpetas de logs: {e}")
        return jsonify({"error": str(e), "folders": []}), 500


@app.route("/api/logs/<date>", methods=["GET"])
def get_logs_by_date(date: str):
    """
    Obtiene todos los logs de una fecha específica.
    
    Args:
        date: Fecha en formato YYYY-MM-DD (ej: 2026-01-16)
        
    Returns:
        Array de JSONs con el contenido de cada log
    """
    # Validar formato de fecha
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        return jsonify({
            "error": "Formato de fecha inválido. Usar YYYY-MM-DD",
            "example": "2026-01-16"
        }), 400
    
    try:
        from src.storage.gcs import GCSUploader
        
        uploader = GCSUploader()
        logs = uploader.get_logs_by_date(date)
        
        # Calcular resumen consolidado
        total_processed = sum(log.get("summary", {}).get("total", 0) for log in logs)
        total_successful = sum(log.get("summary", {}).get("successful", 0) for log in logs)
        total_failed = sum(log.get("summary", {}).get("failed", 0) for log in logs)
        
        # Consolidar facturas fallidas
        all_failed_invoices = []
        for log in logs:
            all_failed_invoices.extend(log.get("failed_invoices", []))
        
        return jsonify({
            "date": date,
            "batches_count": len(logs),
            "consolidated_summary": {
                "total": total_processed,
                "successful": total_successful,
                "failed": total_failed
            },
            "failed_invoices": all_failed_invoices,
            "logs": logs
        })
        
    except Exception as e:
        print(f"[API] Error obteniendo logs de {date}: {e}")
        return jsonify({"error": str(e), "logs": []}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    print(f"[API] Iniciando servidor en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
