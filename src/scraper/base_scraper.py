"""
Clase base para scrapers de portales de proveedores.
Define la interfaz común que todos los scrapers deben implementar.
"""
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime

from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext


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
        download_path: str = "./downloads"
    ):
        self.name = name
        self.login_url = login_url
        self.username = username
        self.password = password
        self.headless = headless
        self.timeout = timeout
        self.download_path = download_path
        
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_logged_in = False
        
        # Asegurar que existe el directorio de descargas
        Path(download_path).mkdir(parents=True, exist_ok=True)
        
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        
    def start(self) -> None:
        """Inicia el navegador y crea el contexto."""
        print(f"[{self.name}] Iniciando navegador (headless={self.headless})")
        
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
        
    def close(self) -> None:
        """Cierra el navegador y limpia recursos."""
        print(f"[{self.name}] Cerrando navegador")
        
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
    
    def process_invoices(self, invoice_numbers: List[str], max_retries: int = 3) -> List[DownloadResult]:
        """
        Procesa una lista de facturas: busca y descarga cada una.
        
        Args:
            invoice_numbers: Lista de números de factura
            max_retries: Número máximo de reintentos por factura
            
        Returns:
            Lista de resultados de descarga
        """
        results = []
        
        if not self._is_logged_in:
            if not self.login():
                print(f"[{self.name}] ERROR: Falló el login")
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
            
            result = self._process_single_invoice(invoice_number, max_retries)
            results.append(result)
            
            if result.success:
                print(f"  ✓ Descargado: {result.file_path}")
            else:
                print(f"  ✗ Error: {result.error_message}")
        
        # Resumen
        successful = sum(1 for r in results if r.success)
        print(f"\n[{self.name}] Completado: {successful}/{total} exitosos")
        
        return results
    
    def _process_single_invoice(self, invoice_number: str, max_retries: int) -> DownloadResult:
        """Procesa una sola factura con reintentos."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = self.download_invoice(invoice_number)
                result.retries = attempt
                
                if result.success:
                    return result
                    
                last_error = result.error_message
                
            except Exception as e:
                last_error = str(e)
                print(f"  Intento {attempt + 1}/{max_retries} falló: {e}")
            
            # Esperar antes de reintentar
            if attempt < max_retries - 1:
                self.page.wait_for_timeout(2000)
        
        return DownloadResult(
            invoice_number=invoice_number,
            success=False,
            error_message=f"Falló después de {max_retries} intentos: {last_error}",
            retries=max_retries
        )
    
    def take_screenshot(self, name: str) -> str:
        """Toma una captura de pantalla para debugging."""
        screenshot_path = Path(self.download_path) / f"screenshot_{name}.png"
        self.page.screenshot(path=str(screenshot_path))
        print(f"[{self.name}] Screenshot guardado: {screenshot_path}")
        return str(screenshot_path)
