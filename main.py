"""
ARG TXT Downloader - API Principal
Automatización de descarga de facturas de proveedores farmacéuticos.
"""
import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from flask import Flask, request, jsonify

from src.utils.excel_reader import ExcelReader
from src.scraper.suizo_scraper import SuizoScraper
from src.storage.google_drive import GoogleDriveUploader

# Inicializar Flask
app = Flask(__name__)

# Directorio temporal para descargas
DOWNLOAD_DIR = os.getenv("DOWNLOAD_PATH", "./downloads")
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)


@app.route("/", methods=["GET"])
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
    
    Espera un archivo Excel en el body (multipart/form-data).
    
    Query params:
        provider: Filtrar por proveedor (suizo, del_sud, monroe)
        dry_run: true/false - Solo analizar sin descargar
    """
    print("[API] Recibida solicitud de procesamiento")
    
    # Verificar que hay un archivo
    if 'file' not in request.files:
        return jsonify({
            "error": "No se envió ningún archivo",
            "detail": "El request debe incluir un archivo Excel con key 'file'"
        }), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "Archivo vacío"}), 400
    
    # Verificar extensión
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({
            "error": "Formato inválido",
            "detail": "El archivo debe ser Excel (.xlsx o .xls)"
        }), 400
    
    # Parámetros opcionales
    provider_filter = request.args.get('provider', None)
    dry_run = request.args.get('dry_run', 'false').lower() == 'true'
    
    try:
        # Guardar archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name
        
        print(f"[API] Archivo guardado: {temp_path}")
        
        # Leer y procesar Excel
        reader = ExcelReader()
        all_records, by_provider = reader.read_excel(temp_path)
        
        # Limpiar archivo temporal
        os.unlink(temp_path)
        
        # Preparar respuesta de análisis
        analysis = {
            "total_records": len(all_records),
            "by_provider": {k: len(v) for k, v in by_provider.items()},
            "records_preview": [
                {
                    "provider": r.provider,
                    "document": r.full_document,
                    "invoice_number": r.invoice_number
                }
                for r in all_records[:10]
            ]
        }
        
        if dry_run:
            return jsonify({
                "status": "dry_run",
                "message": "Análisis completado (sin descarga)",
                "analysis": analysis
            })
        
        # Filtrar por proveedor si se especificó
        if provider_filter:
            if provider_filter not in by_provider:
                return jsonify({
                    "error": "Proveedor no encontrado",
                    "available_providers": list(by_provider.keys())
                }), 400
            
            records_to_process = by_provider[provider_filter]
        else:
            # Por ahora solo procesamos Suizo
            records_to_process = by_provider.get("suizo", [])
            if not records_to_process:
                return jsonify({
                    "status": "no_records",
                    "message": "No se encontraron registros de Suizo",
                    "analysis": analysis
                })
        
        # Procesar facturas
        results = process_invoices(records_to_process)
        
        return jsonify({
            "status": "completed",
            "analysis": analysis,
            "results": results
        })
        
    except ValueError as e:
        print(f"[API] Error de validación: {e}")
        return jsonify({"error": "Error de validación", "detail": str(e)}), 400
        
    except Exception as e:
        print(f"[API] Error: {e}")
        return jsonify({"error": "Error de procesamiento", "detail": str(e)}), 500


def process_invoices(records: list) -> Dict[str, Any]:
    """Procesa una lista de registros de factura."""
    if not records:
        return {"processed": 0, "successful": 0, "failed": 0, "details": []}
    
    invoice_numbers = [r.invoice_number for r in records]
    download_results = []
    upload_results = []
    
    # Descargar con scraper
    try:
        with SuizoScraper() as scraper:
            download_results = scraper.process_invoices(invoice_numbers)
    except Exception as e:
        print(f"[API] Error del scraper: {e}")
        return {
            "error": f"Error del scraper: {str(e)}",
            "processed": 0,
            "successful": 0,
            "failed": len(records)
        }
    
    # Subir archivos exitosos a Google Drive
    successful_downloads = [r for r in download_results if r.success]
    
    if successful_downloads:
        try:
            uploader = GoogleDriveUploader()
            file_paths = [r.file_path for r in successful_downloads if r.file_path]
            upload_results = uploader.upload_files(file_paths)
        except Exception as e:
            print(f"[API] Error de upload: {e}")
    
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
        "processed": len(records),
        "successful": successful,
        "failed": len(records) - successful,
        "details": details
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
                    "invoice_number": r.invoice_number,
                    "observation": r.observation
                }
                for r in all_records[:5]
            ]
        })
        
    except Exception as e:
        return jsonify({"status": "invalid", "error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    print(f"[API] Iniciando servidor en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
