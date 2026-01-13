"""
Scraper específico para el portal de Suizo Argentina.
https://web1.suizoargentina.com/login

Flujo:
1. Login
2. Cerrar popup (si aparece) → Click en "Consultas"
3. Click en "Mis Comprobantes"
4. Seleccionar: Mi grupo → Facturas → Por Número de comprobante → Escribir número → Consultar
5. Marcar checkbox → Descargar seleccionados
6. Repetir desde paso 4
"""
import os
from pathlib import Path
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .base_scraper import BaseScraper, DownloadResult


class SuizoScraper(BaseScraper):
    """
    Scraper para el portal de Suizo Argentina.
    Permite buscar y descargar archivos TXT de facturas.
    """
    
    # URLs del portal
    LOGIN_URL = "https://web1.suizoargentina.com/login"
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = True,
        download_path: str = "./downloads"
    ):
        """
        Inicializa el scraper de Suizo.
        """
        username = username or os.getenv("SUIZO_USERNAME")
        password = password or os.getenv("SUIZO_PASSWORD")
        
        if not username or not password:
            raise ValueError(
                "Credenciales no configuradas. "
                "Define SUIZO_USERNAME y SUIZO_PASSWORD como variables de entorno."
            )
        
        super().__init__(
            name="Suizo",
            login_url=self.LOGIN_URL,
            username=username,
            password=password,
            headless=headless,
            download_path=download_path
        )
        
    def login(self) -> bool:
        """
        Paso 1: Realiza el login en el portal de Suizo Argentina.
        """
        print(f"[{self.name}] Paso 1: Iniciando login en {self.login_url}")
        
        try:
            # Navegar a la página de login
            self.page.goto(self.login_url, wait_until="networkidle")
            self.page.wait_for_timeout(1000)
            
            # Ingresar usuario
            self.page.fill('input[placeholder="Usuario"]', self.username)
            print(f"[{self.name}] Usuario ingresado")
            
            # Ingresar contraseña
            self.page.fill('input[placeholder="Contraseña"]', self.password)
            print(f"[{self.name}] Contraseña ingresada")
            
            # Click en INGRESAR y esperar navegación
            # El botón es un input type="submit", no un button
            with self.page.expect_navigation(wait_until="networkidle", timeout=30000):
                self.page.click('input.btn-login')
            print(f"[{self.name}] Click en INGRESAR - navegación completada")
            
            # Esperar a que cargue completamente
            self.page.wait_for_timeout(2000)
            
            # Paso 2: Cerrar popup si aparece
            self._close_popup_if_exists()
            
            # Verificar login exitoso (debe aparecer el menú)
            if self.page.locator('text="Consultas"').is_visible(timeout=5000):
                print(f"[{self.name}] ✓ Login exitoso")
                self._is_logged_in = True
                return True
            else:
                print(f"[{self.name}] ✗ Login fallido - no se encontró menú Consultas")
                self.take_screenshot("error_login_failed")
                return False
            
        except PlaywrightTimeout as e:
            print(f"[{self.name}] Timeout durante login: {e}")
            self.take_screenshot("error_login_timeout")
            return False
        except Exception as e:
            print(f"[{self.name}] Error durante login: {e}")
            self.take_screenshot("error_login")
            return False
    
    def _close_popup_if_exists(self):
        """Cierra el popup de ofertas si aparece."""
        try:
            # Buscar botón de cerrar popup (X o similar)
            close_buttons = [
                'button.close',
                '.modal-close',
                '[aria-label="Close"]',
                '.popup-close',
                'button:has-text("×")',
                '.modal button:has-text("Cerrar")',
            ]
            
            for selector in close_buttons:
                if self.page.locator(selector).first.is_visible(timeout=1000):
                    self.page.locator(selector).first.click()
                    print(f"[{self.name}] Popup cerrado")
                    self.page.wait_for_timeout(500)
                    return
            
            # Si no hay botón, intentar click fuera del popup
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(500)
            
        except:
            # Si no hay popup, continuar
            pass
    
    def navigate_to_mis_comprobantes(self) -> bool:
        """
        Paso 2-3: Navega a Consultas → Mis Comprobantes.
        """
        print(f"[{self.name}] Paso 2: Navegando a Consultas")
        
        try:
            # Click en Consultas (menú superior)
            self.page.click('text="Consultas"')
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(1000)
            
            print(f"[{self.name}] Paso 3: Click en Mis Comprobantes")
            
            # Click en "Mis Comprobantes" (puede ser link o tarjeta)
            # Intentar varias opciones
            comprobantes_selectors = [
                'text="Mis Comprobantes"',
                'a:has-text("Mis Comprobantes")',
                '.card:has-text("Mis Comprobantes")',
                'div:has-text("Mis Comprobantes") >> nth=0',
            ]
            
            for selector in comprobantes_selectors:
                try:
                    if self.page.locator(selector).first.is_visible(timeout=2000):
                        self.page.locator(selector).first.click()
                        self.page.wait_for_load_state("networkidle")
                        self.page.wait_for_timeout(1000)
                        print(f"[{self.name}] ✓ En página Mis Comprobantes")
                        return True
                except:
                    continue
            
            print(f"[{self.name}] ✗ No se pudo navegar a Mis Comprobantes")
            self.take_screenshot("error_navigation")
            return False
            
        except Exception as e:
            print(f"[{self.name}] Error de navegación: {e}")
            self.take_screenshot("error_navigation")
            return False
    
    def search_invoice(self, invoice_number: str) -> bool:
        """
        Paso 4: Configura filtros y busca la factura.
        - Cuenta: Mi grupo
        - Comprobantes: Facturas
        - Filtro: Por Número de comprobante
        - Escribe el número y consulta
        """
        print(f"[{self.name}] Paso 4: Buscando factura {invoice_number}")
        
        try:
            # 1. Seleccionar "Mi grupo" en Cuenta
            self.page.click('text="Mi grupo"')
            self.page.wait_for_timeout(300)
            print(f"[{self.name}]   - Seleccionado: Mi grupo")
            
            # 2. Seleccionar "Facturas" en Comprobantes
            self.page.click('label:has-text("Facturas")')
            self.page.wait_for_timeout(300)
            print(f"[{self.name}]   - Seleccionado: Facturas")
            
            # 3. Seleccionar "Por Número de comprobante" en Filtro
            self.page.click('text="Por Número de comprobante"')
            self.page.wait_for_timeout(300)
            print(f"[{self.name}]   - Seleccionado: Por Número de comprobante")
            
            # 4. Escribir el número de factura en el textbox
            # El textbox aparece después de seleccionar "Por Número de comprobante"
            input_selectors = [
                'input[type="text"]:visible',
                'input:below(:text("Por Número de comprobante"))',
                '#comprobante',
                'input[name="comprobante"]',
            ]
            
            input_found = False
            for selector in input_selectors:
                try:
                    input_element = self.page.locator(selector).last
                    if input_element.is_visible(timeout=1000):
                        input_element.fill(invoice_number)
                        input_found = True
                        print(f"[{self.name}]   - Número ingresado: {invoice_number}")
                        break
                except:
                    continue
            
            if not input_found:
                print(f"[{self.name}] ✗ No se encontró campo de texto para número")
                self.take_screenshot("error_input_not_found")
                return False
            
            # 5. Click en Consultar
            self.page.click('button:has-text("Consultar")')
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)
            print(f"[{self.name}]   - Click en Consultar")
            
            # Verificar si hay resultados
            if self.page.locator('text="Comprobantes encontrados"').is_visible(timeout=5000):
                print(f"[{self.name}] ✓ Factura encontrada")
                return True
            else:
                print(f"[{self.name}] ✗ Factura no encontrada")
                self.take_screenshot(f"no_results_{invoice_number}")
                return False
            
        except Exception as e:
            print(f"[{self.name}] Error buscando factura: {e}")
            self.take_screenshot(f"error_search_{invoice_number}")
            return False
    
    def download_invoice(self, invoice_number: str) -> DownloadResult:
        """
        Paso 5: Marca el checkbox y descarga el archivo.
        """
        print(f"[{self.name}] Paso 5: Descargando factura {invoice_number}")
        
        try:
            # Navegar a Mis Comprobantes si no estamos ahí
            if not self.page.locator('text="Mis Comprobantes"').first.is_visible():
                if not self.navigate_to_mis_comprobantes():
                    return DownloadResult(
                        invoice_number=invoice_number,
                        success=False,
                        error_message="No se pudo navegar a Mis Comprobantes"
                    )
            
            # Buscar la factura
            if not self.search_invoice(invoice_number):
                return DownloadResult(
                    invoice_number=invoice_number,
                    success=False,
                    error_message="Factura no encontrada"
                )
            
            # Marcar el checkbox de la factura
            checkbox_selectors = [
                'input[type="checkbox"]:visible',
                'table input[type="checkbox"]',
                'tr input[type="checkbox"]',
            ]
            
            checkbox_found = False
            for selector in checkbox_selectors:
                try:
                    checkbox = self.page.locator(selector).first
                    if checkbox.is_visible(timeout=2000):
                        checkbox.check()
                        checkbox_found = True
                        print(f"[{self.name}]   - Checkbox marcado")
                        break
                except:
                    continue
            
            if not checkbox_found:
                return DownloadResult(
                    invoice_number=invoice_number,
                    success=False,
                    error_message="No se encontró checkbox para seleccionar"
                )
            
            self.page.wait_for_timeout(500)
            
            # Click en "Descargar seleccionados"
            with self.page.expect_download(timeout=60000) as download_info:
                self.page.click('button:has-text("Descargar seleccionados")')
                print(f"[{self.name}]   - Click en Descargar seleccionados")
            
            download = download_info.value
            
            # Guardar archivo
            filename = f"{invoice_number}.txt"
            file_path = Path(self.download_path) / filename
            download.save_as(str(file_path))
            
            print(f"[{self.name}] ✓ Archivo descargado: {file_path}")
            
            # Paso 6: Volver a Mis Comprobantes para la siguiente factura
            self._reset_for_next_invoice()
            
            return DownloadResult(
                invoice_number=invoice_number,
                success=True,
                file_path=str(file_path)
            )
            
        except PlaywrightTimeout:
            return DownloadResult(
                invoice_number=invoice_number,
                success=False,
                error_message="Timeout durante la descarga"
            )
        except Exception as e:
            return DownloadResult(
                invoice_number=invoice_number,
                success=False,
                error_message=f"Error de descarga: {str(e)}"
            )
    
    def _reset_for_next_invoice(self):
        """
        Paso 6: Vuelve a Mis Comprobantes para buscar la siguiente factura.
        """
        try:
            # Click en "Mis Comprobantes" en el submenú
            self.page.click('a:has-text("Mis Comprobantes")')
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(1000)
            print(f"[{self.name}] Reset para siguiente factura")
        except:
            # Si falla, intentar navegar desde Consultas
            try:
                self.navigate_to_mis_comprobantes()
            except:
                pass


def create_suizo_scraper(headless: bool = True) -> SuizoScraper:
    """Factory function para crear un scraper de Suizo configurado."""
    return SuizoScraper(headless=headless)
