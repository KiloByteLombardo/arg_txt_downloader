"""
Clase base para scrapers de portales de proveedores.
Define la interfaz común que todos los scrapers deben implementar.
"""
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DownloadResult:
    """Resultado de una descarga de factura."""
    invoice_number: str
    success: bool
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    retries: int = 0


class BaseScraper(ABC):
    """
    Clase base abstracta para scrapers de portales de proveedores.
    """
    
    def __init__(
        self,
        name: str,
        login_url: str,
        username: str,
        password: str,
        headless: bool = True,
        timeout: int = 30000,
        download_path: str = "./downloads",
        upload_screenshots_to_gcs: bool = False
    ):
        self.name = name
        self.login_url = login_url
        self.username = username
        self.password = password
        self.headless = headless
        self.timeout = timeout
        self.download_path = download_path
        self.upload_screenshots_to_gcs = upload_screenshots_to_gcs
        
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._is_logged_in = False
        
        # GCS uploader (se inicializa lazy)
        self._gcs_uploader = None
        
        # Log de ejecución
        self.execution_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.execution_logs = []
        
        # Tracking de screenshots para el frontend
        self.screenshots_uploaded = []  # Lista de {name, url, timestamp}
        
        # Asegurar que existe el directorio de descargas
        Path(download_path).mkdir(parents=True, exist_ok=True)
    
    def _log(self, message: str, level: str = "INFO"):
        """Agrega entrada al log interno."""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] [{level}] [{self.name}] {message}"
        self.execution_logs.append(entry)
        print(entry)
    
    def _get_gcs_uploader(self):
        """Obtiene el uploader de GCS (lazy initialization)."""
        if self._gcs_uploader is None and self.upload_screenshots_to_gcs:
            try:
                from src.storage.gcs import GCSUploader
                # Usar fecha de hoy como subcarpeta: screenshots/2026-01-14/suizo/
                today = datetime.now().strftime("%Y-%m-%d")
                self._gcs_uploader = GCSUploader(prefix=f"screenshots/{today}/{self.name.lower()}/")
            except Exception as e:
                print(f"[{self.name}] No se pudo inicializar GCS: {e}")
        return self._gcs_uploader
        
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        
    def start(self) -> None:
        """Inicia el navegador y crea el contexto."""
        from playwright.sync_api import sync_playwright
        
        print(f"[{self.name}] Iniciando navegador (headless={self.headless})")
        self._log(f"Iniciando navegador (headless={self.headless})")
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        self.context = self.browser.new_context(
            accept_downloads=True,
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        
        print(f"[{self.name}] Navegador iniciado")
        self._log("Navegador iniciado")
        
    def close(self) -> None:
        """Cierra el navegador y limpia recursos."""
        print(f"[{self.name}] Cerrando navegador")
        self._log("Cerrando navegador")
        
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
            
        self._is_logged_in = False
        print(f"[{self.name}] Navegador cerrado")
    
    @abstractmethod
    def login(self) -> bool:
        """Realiza el login en el portal."""
        pass
    
    @abstractmethod
    def search_invoice(self, invoice_number: str) -> bool:
        """Busca una factura por su número."""
        pass
    
    @abstractmethod
    def download_invoice(self, invoice_number: str) -> DownloadResult:
        """Descarga el archivo de una factura."""
        pass
    
    def process_invoices(self, invoice_numbers: List[str], max_retries: int = 4) -> List[DownloadResult]:
        """
        Procesa una lista de facturas: busca y descarga cada una.
        
        Args:
            invoice_numbers: Lista de números de factura
            max_retries: Número máximo de intentos por factura (default: 4)
        """
        results = []
        failed_invoices = []  # Track de facturas fallidas
        self._log(f"Iniciando procesamiento de {len(invoice_numbers)} facturas (max_retries={max_retries})")
        
        if not self._is_logged_in:
            if not self.login():
                self._log("ERROR: Falló el login", "ERROR")
                return [
                    DownloadResult(
                        invoice_number=inv,
                        success=False,
                        error_message="Error de login"
                    ) for inv in invoice_numbers
                ]
        
        total = len(invoice_numbers)
        for idx, invoice_number in enumerate(invoice_numbers, 1):
            print(f"[{self.name}] Procesando factura {idx}/{total}: {invoice_number}")
            self._log(f"Procesando factura {idx}/{total}: {invoice_number}")
            
            result = self._process_single_invoice(invoice_number, max_retries)
            results.append(result)
            
            if result.success:
                print(f"  ✓ Descargado: {result.file_path}")
                self._log(f"OK: {invoice_number} -> {result.file_path}")
            else:
                print(f"  ✗ Error después de {max_retries} intentos: {result.error_message}")
                self._log(f"FALLIDA: {invoice_number} - {result.error_message}", "ERROR")
                failed_invoices.append(invoice_number)
        
        # Resumen
        successful = sum(1 for r in results if r.success)
        print(f"\n[{self.name}] ========== RESUMEN ==========")
        print(f"[{self.name}] Total: {total} | Exitosos: {successful} | Fallidos: {len(failed_invoices)}")
        self._log(f"RESUMEN: Total={total}, Exitosos={successful}, Fallidos={len(failed_invoices)}")
        
        # Log de facturas fallidas
        if failed_invoices:
            print(f"[{self.name}] Facturas fallidas:")
            self._log("FACTURAS FALLIDAS:", "ERROR")
            for inv in failed_invoices:
                print(f"  - {inv}")
                self._log(f"  - {inv}", "ERROR")
        
        return results
    
    def _process_single_invoice(self, invoice_number: str, max_retries: int) -> DownloadResult:
        """Procesa una sola factura con reintentos."""
        last_error = None
        
        for attempt in range(max_retries):
            attempt_num = attempt + 1
            
            try:
                result = self.download_invoice(invoice_number)
                result.retries = attempt
                
                if result.success:
                    return result
                    
                last_error = result.error_message
                print(f"  Intento {attempt_num}/{max_retries} falló: {last_error}")
                self._log(f"Intento {attempt_num}/{max_retries} para {invoice_number}: {last_error}", "WARNING")
                
            except Exception as e:
                last_error = str(e)
                print(f"  Intento {attempt_num}/{max_retries} falló: {e}")
                self._log(f"Intento {attempt_num}/{max_retries} para {invoice_number}: {e}", "WARNING")
            
            # Esperar antes de reintentar (excepto en el último intento)
            if attempt < max_retries - 1:
                print(f"  Reintentando en 2 segundos...")
                self.page.wait_for_timeout(2000)
        
        # Después de agotar todos los intentos, tomar screenshot final
        print(f"  ⚠ Factura {invoice_number} fallida después de {max_retries} intentos")
        self._log(f"AGOTADOS {max_retries} INTENTOS para factura {invoice_number}: {last_error}", "ERROR")
        
        # Screenshot final del error
        self.take_screenshot(f"final_error_{invoice_number}")
        
        return DownloadResult(
            invoice_number=invoice_number,
            success=False,
            error_message=f"Falló después de {max_retries} intentos: {last_error}",
            retries=max_retries
        )
    
    def take_screenshot(self, name: str) -> dict:
        """
        Toma una captura de pantalla para debugging.
        Si upload_screenshots_to_gcs=True, también la sube a GCS.
        
        Returns:
            Dict con {name, local_path, gcs_url}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{name}_{timestamp}.png"
        screenshot_path = Path(self.download_path) / filename
        
        self.page.screenshot(path=str(screenshot_path))
        print(f"[{self.name}] Screenshot guardado: {screenshot_path}")
        self._log(f"Screenshot guardado: {filename}")
        
        screenshot_info = {
            "name": name,
            "filename": filename,
            "local_path": str(screenshot_path),
            "gcs_url": None,
            "timestamp": timestamp
        }
        
        # Subir a GCS si está habilitado
        if self.upload_screenshots_to_gcs:
            uploader = self._get_gcs_uploader()
            if uploader:
                result = uploader.upload_file(str(screenshot_path))
                if result.success:
                    screenshot_info["gcs_url"] = result.public_url
                    print(f"[{self.name}] Screenshot subido a GCS: {result.public_url}")
                    self._log(f"Screenshot subido a GCS: {result.public_url}")
        
        # Guardar para el resumen final
        self.screenshots_uploaded.append(screenshot_info)
        
        return screenshot_info
    
    def get_execution_log(self) -> str:
        """Retorna el log de ejecución completo."""
        header = f"=== Ejecución {self.execution_id} - {self.name} ===\n"
        header += "=" * 50 + "\n\n"
        return header + "\n".join(self.execution_logs)
    
    def save_execution_log(self, upload_to_gcs: bool = False) -> dict:
        """
        Guarda el log de ejecución localmente y opcionalmente a GCS.
        
        Returns:
            Dict con {local_path, gcs_url}
        """
        log_content = self.get_execution_log()
        filename = f"execution_{self.name.lower()}_{self.execution_id}.log"
        filepath = Path(self.download_path) / filename
        
        result = {
            "filename": filename,
            "local_path": str(filepath),
            "gcs_url": None
        }
        
        # Guardar localmente
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(log_content)
        print(f"[{self.name}] Log guardado: {filepath}")
        
        # Subir a GCS si se solicita
        if upload_to_gcs:
            try:
                from src.storage.gcs import GCSUploader
                uploader = GCSUploader(prefix="logs/")
                upload_result = uploader.upload_file(str(filepath))
                if upload_result.success:
                    result["gcs_url"] = upload_result.public_url
                    print(f"[{self.name}] Log subido a GCS: {upload_result.public_url}")
            except Exception as e:
                print(f"[{self.name}] Error subiendo log a GCS: {e}")
        
        return result
    
    def get_execution_summary(self) -> dict:
        """
        Retorna un resumen completo de la ejecución para el frontend.
        Incluye todos los links de GCS.
        """
        return {
            "execution_id": self.execution_id,
            "provider": self.name,
            "screenshots": [
                {
                    "name": s["name"],
                    "url": s["gcs_url"] or s["local_path"],
                    "timestamp": s["timestamp"]
                }
                for s in self.screenshots_uploaded
            ],
            "logs_count": len(self.execution_logs)
        }
    
    def save_execution_log_json(
        self, 
        results: list, 
        upload_to_gcs: bool = False,
        execution_id: str = None,
        batch_id: int = None
    ) -> dict:
        """
        Guarda el log de ejecución en formato JSON para el frontend.
        
        Args:
            results: Lista de DownloadResult
            upload_to_gcs: Subir a GCS
            execution_id: ID de ejecución global (para agrupar logs de múltiples workers)
            batch_id: ID del lote (para diferenciar logs de cada worker)
        
        Returns:
            Dict con {local_path, gcs_url, data}
        """
        import json
        
        # Usar execution_id pasado o el interno
        exec_id = execution_id or self.execution_id
        
        # Estructura JSON para el frontend
        log_data = {
            "execution_id": exec_id,
            "batch_id": batch_id,
            "provider": self.name,
            "timestamp_start": self.execution_logs[0].split("]")[0].replace("[", "") if self.execution_logs else None,
            "timestamp_end": self.execution_logs[-1].split("]")[0].replace("[", "") if self.execution_logs else None,
            "summary": {
                "total": len(results),
                "successful": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success)
            },
            "results": [
                {
                    "invoice_number": r.invoice_number,
                    "success": r.success,
                    "file_path": r.file_path,
                    "error_message": r.error_message,
                    "retries": r.retries,
                    "timestamp": r.timestamp
                }
                for r in results
            ],
            "failed_invoices": [r.invoice_number for r in results if not r.success],
            "screenshots": [
                {
                    "name": s["name"],
                    "url": s["gcs_url"],
                    "local_path": s["local_path"],
                    "timestamp": s["timestamp"]
                }
                for s in self.screenshots_uploaded
            ],
            "logs": self.execution_logs
        }
        
        # Nombre del archivo incluye batch_id si existe
        if batch_id is not None:
            filename = f"execution_{exec_id}_batch_{batch_id}.json"
        else:
            filename = f"execution_{exec_id}.json"
        
        filepath = Path(self.download_path) / filename
        
        result = {
            "filename": filename,
            "local_path": str(filepath),
            "gcs_url": None,
            "data": log_data
        }
        
        # Guardar localmente
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        print(f"[{self.name}] Log JSON guardado: {filepath}")
        
        # Subir a GCS si se solicita
        if upload_to_gcs:
            try:
                from src.storage.gcs import GCSUploader
                # Usar fecha de hoy como subcarpeta: logs/2026-01-14/
                today = datetime.now().strftime("%Y-%m-%d")
                uploader = GCSUploader(prefix=f"logs/{today}/")
                upload_result = uploader.upload_file(str(filepath), content_type="application/json")
                if upload_result.success:
                    result["gcs_url"] = upload_result.public_url
                    print(f"[{self.name}] Log JSON subido a GCS: {upload_result.public_url}")
            except Exception as e:
                print(f"[{self.name}] Error subiendo log JSON a GCS: {e}")
        
        return result
