"""
Scraper específico para el portal de Monroe Americana (MASA).
https://www.monroeamericana.com.ar/apps/login/ext/index.html

Flujo:
1. Login (con soporte para cookies guardadas para evitar captcha)
2. Click en "Comprobantes emitidos"
3. Configurar período de fechas (una sola vez)
4. Buscar factura en campo "Buscar"
5. Marcar checkbox de la factura
6. Exportar con Informe="Impositivo", Formato="Delimitado x coma"
7. Repetir desde paso 4
"""
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .base_scraper import BaseScraper, DownloadResult
from ..utils.session_manager import load_cookies, save_cookies, is_session_valid, get_storage_state


class MonroeScraper(BaseScraper):
    """
    Scraper para el portal de Monroe Americana (MASA).
    Permite buscar y descargar archivos TXT de facturas.
    """
    
    # URLs del portal
    LOGIN_URL = "https://www.monroeamericana.com.ar/apps/login/ext/index.html"
    DASHBOARD_URL = "https://www.monroeamericana.com.ar/apps/masaWeb/r6en1/index.html#bienvenido.html"
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = True,
        download_path: str = "./downloads",
        upload_screenshots_to_gcs: bool = False,
        use_chrome_profile: bool = False,
        chrome_user_data_dir: Optional[str] = None
    ):
        """
        Inicializa el scraper de Monroe.
        
        Args:
            username: Usuario (si es None, lee de MONROE_USERNAME)
            password: Contraseña (si es None, lee de MONROE_PASSWORD)
            headless: Ejecutar navegador sin interfaz gráfica
            download_path: Directorio para guardar archivos
            upload_screenshots_to_gcs: Subir screenshots de errores a GCS
            use_chrome_profile: Si True, usa el perfil de Chrome del usuario
            chrome_user_data_dir: Ruta al User Data Dir de Chrome (opcional)
        """
        username = username or os.getenv("MONROE_USERNAME")
        password = password or os.getenv("MONROE_PASSWORD")
        
        if not username or not password:
            raise ValueError(
                "Credenciales no configuradas. "
                "Define MONROE_USERNAME y MONROE_PASSWORD como variables de entorno."
            )
        
        # Monroe detecta navegadores headless, usar display virtual cuando esté disponible
        # En Cloud Run con xvfb, DISPLAY=:99 permite usar headless=False
        use_virtual_display = os.getenv("DISPLAY") == ":99"
        if use_virtual_display and headless:
            print(f"[Monroe] Display virtual detectado (DISPLAY=:99), usando modo visible")
            headless = False
        
        super().__init__(
            name="Monroe",
            login_url=self.LOGIN_URL,
            username=username,
            password=password,
            headless=headless,
            download_path=download_path,
            upload_screenshots_to_gcs=upload_screenshots_to_gcs
        )
        
        # Flag para saber si ya se configuró el período
        self._period_configured = False
        
        # Configuración para usar perfil de Chrome existente
        self._use_chrome_profile = use_chrome_profile
        self._chrome_user_data_dir = chrome_user_data_dir or self._get_default_chrome_profile()
    
    def _get_default_chrome_profile(self) -> str:
        """Obtiene la ruta por defecto del perfil de Chrome del usuario."""
        import platform
        
        system = platform.system()
        home = os.path.expanduser("~")
        
        if system == "Windows":
            return os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data")
        elif system == "Darwin":  # macOS
            return os.path.join(home, "Library", "Application Support", "Google", "Chrome")
        else:  # Linux
            return os.path.join(home, ".config", "google-chrome")
    
    def start(self) -> None:
        """Inicia el navegador, opcionalmente conectándose a Chrome existente via CDP."""
        from playwright.sync_api import sync_playwright
        
        if self._use_chrome_profile:
            # Conectarse a Chrome via CDP (Chrome DevTools Protocol)
            # El usuario debe lanzar Chrome con: chrome.exe --remote-debugging-port=9222
            cdp_url = "http://localhost:9222"
            print(f"[{self.name}] Conectando a Chrome via CDP en {cdp_url}")
            self._log(f"Conectando a Chrome via CDP: {cdp_url}")
            
            self.playwright = sync_playwright().start()
            
            try:
                # Conectarse al Chrome que ya está corriendo
                self.browser = self.playwright.chromium.connect_over_cdp(cdp_url)
                
                # Obtener el contexto existente
                self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
                
                # Crear nueva página o usar la existente
                self.page = self.context.new_page()
                self.page.set_default_timeout(self.timeout)
                self._apply_stealth(self.page)
                
                print(f"[{self.name}] [OK] Conectado a Chrome existente!")
                self._log("Conectado a Chrome via CDP")
                
            except Exception as e:
                print(f"[{self.name}] [ERROR] No se pudo conectar a Chrome: {e}")
                print(f"[{self.name}]")
                print(f"[{self.name}] Para usar esta opcion, lanza Chrome asi:")
                print(f"[{self.name}]   1. Cierra Chrome completamente")
                print(f"[{self.name}]   2. Abre CMD y ejecuta:")
                print(f'[{self.name}]      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
                print(f"[{self.name}]   3. Inicia sesion en Monroe en ese Chrome")
                print(f"[{self.name}]   4. Vuelve a ejecutar esta opcion")
                raise
        else:
            # Usar el método original de BaseScraper
            super().start()
        
    def login(self) -> bool:
        """
        Paso 1: Realiza el login en el portal de Monroe Americana.
        Si usa perfil de Chrome, navega directo al dashboard.
        Si no, intenta cookies guardadas y luego login normal.
        """
        print(f"[{self.name}] Paso 1: Iniciando login")
        
        # Si usamos perfil de Chrome, navegar directo al dashboard
        if self._use_chrome_profile:
            return self._login_with_chrome_profile()
        
        # Intentar login con cookies guardadas primero
        if self._try_login_with_cookies():
            return True
        
        # Si no hay cookies o fallaron, hacer login normal
        return self._do_normal_login()
    
    def _login_with_chrome_profile(self) -> bool:
        """
        Login usando el perfil de Chrome existente.
        Simplemente navega al dashboard ya que Chrome ya tiene la sesión.
        """
        print(f"[{self.name}] Usando sesion de Chrome existente...")
        
        try:
            # Navegar directamente al dashboard
            self.page.goto(self.DASHBOARD_URL, wait_until="load", timeout=30000)
            self.page.wait_for_timeout(3000)
            
            current_url = self.page.url
            print(f"[{self.name}] URL actual: {current_url}")
            
            # Verificar si estamos logueados
            if self._verify_login_success():
                print(f"[{self.name}] [OK] Sesion de Chrome valida!")
                self._is_logged_in = True
                return True
            else:
                print(f"[{self.name}] [WARN] Sesion de Chrome no valida, intenta loguearte en Chrome primero")
                self.take_screenshot("chrome_session_invalid")
                return False
                
        except Exception as e:
            print(f"[{self.name}] Error con perfil de Chrome: {e}")
            self.take_screenshot("chrome_profile_error")
            return False
    
    def _try_login_with_cookies(self) -> bool:
        """
        Intenta iniciar sesión usando storage state guardado.
        """
        storage_state_path = get_storage_state("monroe")
        
        if not storage_state_path:
            print(f"[{self.name}] No hay sesion guardada, se requiere login normal")
            return False
        
        try:
            print(f"[{self.name}] Intentando login con storage state...")
            
            # Cerrar la página y contexto actuales
            self.page.close()
            self.context.close()
            
            # Crear nuevo contexto con storage state
            self.context = self.browser.new_context(
                storage_state=storage_state_path,
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True
            )
            self.page = self.context.new_page()
            self._apply_stealth(self.page)
            
            # Navegar DIRECTAMENTE al dashboard (no al login)
            # Si el storage_state es válido, cargará el dashboard
            # Si no, redirigirá al login
            print(f"[{self.name}] Navegando al dashboard...")
            self.page.goto(self.DASHBOARD_URL, wait_until="load", timeout=30000)
            self.page.wait_for_timeout(3000)
            
            current_url = self.page.url
            print(f"[{self.name}] URL actual: {current_url}")
            
            # Si nos redirigió al login (apps/login/ext/), la sesión no es válida
            if "/apps/login/ext/" in current_url.lower():
                print(f"[{self.name}] Redirigido al login - sesion no valida")
                return False
            
            # Verificar si estamos logueados buscando elementos del dashboard
            if self._verify_login_success():
                print(f"[{self.name}] [OK] Login con storage state exitoso!")
                self._is_logged_in = True
                return True
            else:
                print(f"[{self.name}] Storage state expirado o invalido")
                return False
                
        except Exception as e:
            print(f"[{self.name}] Error usando storage state: {e}")
            return False
    
    def _do_normal_login(self, wait_for_manual_captcha: bool = True) -> bool:
        """
        Realiza el login normal.
        Si aparece captcha y estamos en modo visible, espera resolución manual.
        
        Args:
            wait_for_manual_captcha: Si True y headless=False, espera que el usuario resuelva el captcha
        """
        print(f"[{self.name}] Realizando login normal en {self.login_url}")
        
        try:
            # Navegar a la página de login
            self.page.goto(self.login_url, wait_until="load", timeout=60000)
            self.page.wait_for_timeout(3000)
            
            # Ingresar usuario (usar ID específico porque hay 2 inputs con mismo placeholder)
            usuario_input = self.page.locator('#pUser')
            usuario_input.fill(self.username)
            print(f"[{self.name}] Usuario ingresado")
            
            # Ingresar contraseña (usar el primer input de tipo password)
            password_input = self.page.locator('input[type="password"]').first
            password_input.fill(self.password)
            print(f"[{self.name}] Contrasena ingresada")
            
            # Click en "Iniciar sesión" (botón del formulario principal)
            login_button = self.page.locator('button:has-text("Iniciar")').first
            login_button.click()
            print(f"[{self.name}] Click en Iniciar sesion")
            
            # Esperar un poco para que aparezca cualquier popup
            self.page.wait_for_timeout(3000)
            
            # Verificar si apareció el captcha o error de credenciales
            captcha_modal = self.page.locator('text="Para una mayor seguridad"')
            error_modal = self.page.locator('text="Error de Credenciales"')
            
            if error_modal.is_visible(timeout=2000):
                print(f"[{self.name}] [!] Error de credenciales detectado")
                self.take_screenshot("error_credenciales")
                
                if not self.headless and wait_for_manual_captcha:
                    print(f"[{self.name}] ")
                    print(f"[{self.name}] ========================================")
                    print(f"[{self.name}] INTERVENCION MANUAL REQUERIDA")
                    print(f"[{self.name}] ========================================")
                    print(f"[{self.name}] El portal muestra un error.")
                    print(f"[{self.name}] Por favor, en el navegador:")
                    print(f"[{self.name}]   1. Cierra el popup de error (OK)")
                    print(f"[{self.name}]   2. Inicia sesion manualmente")
                    print(f"[{self.name}]   3. Resuelve el captcha si aparece")
                    print(f"[{self.name}]   4. Navega hasta ver 'Comprobantes emitidos'")
                    print(f"[{self.name}] ")
                    print(f"[{self.name}] Esperando... (maximo 5 minutos)")
                    
                    try:
                        # Esperar a que llegue al dashboard
                        self.page.wait_for_url("**/masaWeb/**", timeout=300000)
                        print(f"[{self.name}] [OK] Navegacion manual exitosa!")
                        
                        # Guardar cookies para futuros usos
                        save_cookies(self.context, "monroe")
                        print(f"[{self.name}] Sesion guardada para proximos logins")
                        
                        self._is_logged_in = True
                        return True
                    except:
                        print(f"[{self.name}] Timeout esperando navegacion manual")
                        return False
                else:
                    print(f"[{self.name}] [ERROR] Error de credenciales en modo headless!")
                    return False
            
            if captcha_modal.is_visible(timeout=2000):
                print(f"[{self.name}] [!] CAPTCHA detectado")
                self.take_screenshot("captcha_detected")
                
                if not self.headless and wait_for_manual_captcha:
                    print(f"[{self.name}] Por favor resuelve el captcha manualmente...")
                    print(f"[{self.name}] (Tienes 5 minutos)")
                    
                    try:
                        self.page.wait_for_selector('text="Para una mayor seguridad"', 
                                                   state='hidden', timeout=300000)
                        print(f"[{self.name}] Captcha resuelto!")
                    except:
                        print(f"[{self.name}] Timeout esperando resolucion de captcha")
                        return False
                else:
                    print(f"[{self.name}] [ERROR] Captcha en modo headless!")
                    print(f"[{self.name}] Monroe requiere captcha. Usa headless=False")
                    return False
            
            # Esperar a que cargue la página post-login
            self.page.wait_for_load_state("load")
            self.page.wait_for_timeout(2000)
            
            # Verificar login exitoso
            if self._verify_login_success():
                print(f"[{self.name}] [OK] Login exitoso")
                self._is_logged_in = True
                
                # Guardar cookies para futuros usos
                try:
                    save_cookies(self.context, "monroe")
                    print(f"[{self.name}] Cookies guardadas para proximos logins")
                except Exception as e:
                    print(f"[{self.name}] No se pudieron guardar cookies: {e}")
                
                return True
            else:
                print(f"[{self.name}] [FAIL] Login fallido")
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
    
    def _verify_login_success(self) -> bool:
        """
        Verifica si el login fue exitoso buscando elementos del dashboard.
        """
        try:
            current_url = self.page.url
            print(f"[{self.name}] URL actual: {current_url}")
            
            # Si estamos en masaWeb, definitivamente estamos logueados
            if "masaWeb" in current_url:
                print(f"[{self.name}] Detectado masaWeb en URL - login exitoso")
                return True
            
            # Si estamos en el login, no estamos logueados
            if "/apps/login/ext/" in current_url:
                return False
            
            # Verificar si estamos en la página de bienvenida/dashboard
            # Buscar elementos específicos del dashboard de Monroe
            dashboard_indicators = [
                'text="Bienvenido"',
                'text="Acceso Rápido"',
                'text="Comprobantes emitidos"',
                'text="Estado de Cuenta"',
                'text="Grupo Económico"',
                'text="Pedidos"',
                'text="Cerrar Sesión"'
            ]
            
            for selector in dashboard_indicators:
                try:
                    if self.page.locator(selector).first.is_visible(timeout=2000):
                        print(f"[{self.name}] Encontrado indicador: {selector}")
                        return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            print(f"[{self.name}] Error verificando login: {e}")
            return False
    
    def navigate_to_comprobantes(self) -> bool:
        """
        Paso 2: Click en "Comprobantes emitidos" desde la página de bienvenida.
        """
        print(f"[{self.name}] Paso 2: Navegando a Comprobantes emitidos")
        
        try:
            # Esperar a que cargue la página de bienvenida
            self.page.wait_for_load_state("load")
            self.page.wait_for_timeout(2000)
            
            # Buscar el botón/enlace "Comprobantes emitidos"
            comprobantes_btn = self.page.locator('text="Comprobantes emitidos"')
            
            if comprobantes_btn.is_visible(timeout=10000):
                comprobantes_btn.click()
                print(f"[{self.name}] Click en Comprobantes emitidos")
                
                # Esperar a que cargue la página de comprobantes
                self.page.wait_for_load_state("load")
                self.page.wait_for_timeout(3000)
                
                # Verificar que estamos en la página correcta
                if self.page.locator('text="Detalle de Emisiones"').is_visible(timeout=10000):
                    print(f"[{self.name}] [OK] En pagina de Comprobantes")
                    return True
                else:
                    print(f"[{self.name}] No se cargo la pagina de comprobantes")
                    self.take_screenshot("error_comprobantes_not_loaded")
                    return False
            else:
                print(f"[{self.name}] Boton 'Comprobantes emitidos' no encontrado")
                self.take_screenshot("error_comprobantes_btn_not_found")
                return False
                
        except Exception as e:
            print(f"[{self.name}] Error navegando a comprobantes: {e}")
            self.take_screenshot("error_navigate_comprobantes")
            return False
    
    def configure_period(self, start_date: str = None, end_date: str = None, force: bool = False) -> bool:
        """
        Paso 3: Configura el período de fechas automáticamente.
        
        Abre el modal de período, configura fechas (60 días) y hace click en Consultar.
        
        Args:
            start_date: Fecha inicial (formato DD/MM/YYYY). Si None, usa 59 días atrás
            end_date: Fecha final (formato DD/MM/YYYY). Si None, usa hoy
            force: Si True, fuerza reconfigurar aunque ya haya datos
        """
        if self._period_configured and not force:
            print(f"[{self.name}] Periodo ya configurado, saltando...")
            return True
        
        print(f"[{self.name}] Paso 3: Configurando periodo de fechas")
        
        # Esperar a que cargue la página
        self.page.wait_for_timeout(2000)
        
        # Verificar si ya hay datos en la tabla (y no forzamos)
        if not force:
            try:
                rows = self.page.locator('table tbody tr')
                row_count = rows.count()
                
                if row_count > 0:
                    print(f"[{self.name}] [OK] Ya hay {row_count} facturas en la tabla")
                    self._period_configured = True
                    return True
            except:
                pass
        
        # Calcular fechas (máximo 60 días que permite el portal)
        # Fecha final: ayer (hoy - 1 día)
        # Fecha inicial: 59 días antes de ayer (total 60 días)
        if not end_date:
            yesterday = datetime.now() - timedelta(days=1)
            end_date = yesterday.strftime("%d/%m/%Y")
        
        if not start_date:
            start = datetime.now() - timedelta(days=60)  # 60 días atrás desde hoy = 59 días antes de ayer
            start_date = start.strftime("%d/%m/%Y")
        
        print(f"[{self.name}] Rango a configurar: {start_date} - {end_date}")
        
        try:
            # Click en botón "Período" (botón verde)
            periodo_btn = self.page.locator('button.btn-success:has-text("Período")').first
            if not periodo_btn.is_visible(timeout=3000):
                periodo_btn = self.page.locator('button:has-text("Período")').first
            if not periodo_btn.is_visible(timeout=3000):
                periodo_btn = self.page.locator('button:has-text("Periodo")').first
            
            if not periodo_btn.is_visible(timeout=5000):
                print(f"[{self.name}] [WARN] No se encontro boton Periodo")
                self.take_screenshot("no_periodo_btn")
                self._period_configured = True
                return True
            
            periodo_btn.click()
            print(f"[{self.name}] Click en boton Periodo")
            self.page.wait_for_timeout(2000)
            
            # Esperar a que aparezca el modal con el datepicker
            date_input = self.page.locator('#masa-datepicker-input')
            if not date_input.is_visible(timeout=5000):
                date_input = self.page.locator('input.dma-datepicker-input')
            
            if date_input.is_visible(timeout=3000):
                date_range = f"{start_date} - {end_date}"
                
                # Método: Interactuar directamente con el input
                print(f"[{self.name}] Configurando fechas: {date_range}")
                
                # Hacer click para abrir el datepicker
                date_input.click()
                self.page.wait_for_timeout(500)
                
                # Limpiar el campo completamente
                date_input.click(click_count=3)  # Seleccionar todo
                self.page.keyboard.press("Control+a")
                self.page.keyboard.press("Backspace")
                self.page.wait_for_timeout(300)
                
                # Escribir el rango de fechas caracter por caracter
                date_input.type(date_range, delay=50)
                print(f"[{self.name}] Rango escrito: {date_range}")
                
                self.page.wait_for_timeout(500)
                
                # Presionar Tab para salir del campo y cerrar el datepicker
                self.page.keyboard.press("Tab")
                self.page.wait_for_timeout(500)
                
                # También cerrar el datepicker via JavaScript por si acaso
                self.page.evaluate('''
                    const pickers = document.querySelectorAll('.daterangepicker');
                    pickers.forEach(p => p.style.display = 'none');
                ''')
                
                self.page.wait_for_timeout(500)
            else:
                print(f"[{self.name}] [WARN] Input de fecha no encontrado")
                self.take_screenshot("no_date_input")
            
            # Click en botón "Consultar" del modal
            self.page.wait_for_timeout(500)
            
            consultar_btn = self.page.locator('#masa-modal-consultar')
            if not consultar_btn.is_visible(timeout=2000):
                consultar_btn = self.page.locator('button.btn-primary:has-text("Consultar")').first
            if not consultar_btn.is_visible(timeout=2000):
                consultar_btn = self.page.locator('button:has-text("Consultar")').first
            
            if consultar_btn.is_visible(timeout=3000):
                consultar_btn.click()
                print(f"[{self.name}] Click en Consultar")
            else:
                print(f"[{self.name}] [WARN] Boton Consultar no encontrado")
                self.take_screenshot("no_consultar_btn")
                # Intentar presionar Enter como alternativa
                self.page.keyboard.press("Enter")
            
            # Esperar a que carguen los datos
            print(f"[{self.name}] Esperando carga de datos...")
            self.page.wait_for_timeout(3000)
            self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # Verificar si cargaron facturas
            try:
                rows = self.page.locator('table tbody tr')
                row_count = rows.count()
                
                if row_count > 0:
                    print(f"[{self.name}] [OK] Periodo configurado! {row_count} facturas disponibles")
                else:
                    print(f"[{self.name}] [WARN] No se encontraron facturas en el rango")
                    self.take_screenshot("no_invoices_in_range")
            except:
                pass
            
            self._period_configured = True
            return True
            
        except Exception as e:
            print(f"[{self.name}] Error configurando periodo: {e}")
            self.take_screenshot("error_configure_period")
            self._period_configured = True
            return True
    
    def search_invoice(self, invoice_number: str) -> bool:
        """
        Paso 4: Busca una factura por su número en el campo "Buscar".
        """
        print(f"[{self.name}] Paso 4: Buscando factura {invoice_number}")
        
        try:
            # Esperar a que la tabla esté visible
            self.page.wait_for_selector('table, .table', timeout=10000)
            
            # Buscar el campo de búsqueda (arriba a la derecha de la tabla)
            search_input = self.page.locator('input[type="search"]').first
            if not search_input.is_visible(timeout=3000):
                search_input = self.page.get_by_placeholder("Buscar")
            if not search_input.is_visible(timeout=3000):
                search_input = self.page.locator('input').filter(has_text="").last
            
            # Limpiar y escribir el número de factura
            search_input.click()
            search_input.fill("")
            self.page.wait_for_timeout(500)
            search_input.type(invoice_number, delay=50)  # Escribir lentamente
            print(f"[{self.name}] Numero ingresado: {invoice_number}")
            
            # Esperar a que filtre (es filtro en tiempo real)
            self.page.wait_for_timeout(3000)
            
            # Tomar screenshot para debug
            self.take_screenshot(f"debug_search_{invoice_number}")
            
            # Verificar si aparece la factura en la tabla
            # Buscar en cualquier celda de la tabla
            invoice_cell = self.page.locator(f'td:has-text("{invoice_number}")')
            
            if invoice_cell.count() > 0:
                print(f"[{self.name}] [OK] Factura {invoice_number} encontrada")
                return True
            
            # Intentar buscar con formato parcial
            invoice_row = self.page.locator(f'tr:has-text("{invoice_number}")')
            if invoice_row.count() > 0:
                print(f"[{self.name}] [OK] Factura {invoice_number} encontrada")
                return True
            
            print(f"[{self.name}] Factura {invoice_number} no encontrada")
            return False
                
        except Exception as e:
            print(f"[{self.name}] Error buscando factura: {e}")
            self.take_screenshot(f"error_search_{invoice_number}")
            return False
    
    def download_invoice(self, invoice_number: str) -> DownloadResult:
        """
        Pasos 4-6: Busca, selecciona y descarga una factura.
        """
        print(f"[{self.name}] Procesando factura: {invoice_number}")
        
        try:
            # Paso 4: Buscar la factura
            if not self.search_invoice(invoice_number):
                return DownloadResult(
                    invoice_number=invoice_number,
                    success=False,
                    error_message="Factura no encontrada"
                )
            
            # Paso 5: Marcar el checkbox de la factura
            print(f"[{self.name}] Paso 5: Marcando checkbox")
            
            # Buscar la fila que contiene el número de factura
            invoice_row = self.page.locator(f'tr:has-text("{invoice_number}")').first
            
            # Buscar el checkbox dentro de esa fila (última columna)
            checkbox = invoice_row.locator('input[type="checkbox"]')
            if not checkbox.is_visible(timeout=3000):
                # El checkbox puede estar en la columna "Serie"
                checkbox = invoice_row.locator('td:last-child input, td:nth-last-child(1) input')
            
            checkbox.click(force=True)
            print(f"[{self.name}] Checkbox marcado")
            self.page.wait_for_timeout(500)
            
            # Paso 6: Click en "Exportar" (botón verde de la barra superior)
            print(f"[{self.name}] Paso 6: Exportando")
            
            # Usar el botón verde de exportar (el primero, en la barra superior)
            exportar_btn = self.page.locator('button.btn-success:has-text("Exportar")').first
            if not exportar_btn.is_visible(timeout=3000):
                exportar_btn = self.page.locator('button:has-text("Exportar")').first
            exportar_btn.click()
            print(f"[{self.name}] Click en Exportar")
            
            # Esperar a que aparezca el modal de exportación
            self.page.wait_for_timeout(2000)
            
            # Configurar el modal de exportación
            # Seleccionar Informe = "Impositivo"
            modal = self.page.locator('.modal.show, [role="dialog"]:visible').first
            
            informe_select = modal.locator('select').first
            informe_select.select_option(label="Impositivo")
            print(f"[{self.name}] Informe: Impositivo")
            
            # Seleccionar Formato = "Delimitado x coma(,)"
            formato_select = modal.locator('select').nth(1)
            formato_select.select_option(label="Delimitado x coma(,)")
            print(f"[{self.name}] Formato: Delimitado x coma")
            
            self.page.wait_for_timeout(500)
            
            # Click en botón Exportar del modal (el segundo botón Exportar)
            with self.page.expect_download(timeout=30000) as download_info:
                export_modal_btn = modal.locator('button:has-text("Exportar")')
                export_modal_btn.click()
                print(f"[{self.name}] Click en Exportar (modal)")
            
            # Obtener el archivo descargado
            download = download_info.value
            
            # Guardar el archivo con el nombre de la factura
            file_name = f"{invoice_number}.txt"
            file_path = Path(self.download_path) / file_name
            download.save_as(str(file_path))
            
            print(f"[{self.name}] [OK] Archivo descargado: {file_path}")
            
            # Esperar a que se cierre el modal
            self.page.wait_for_timeout(1000)
            
            # Desmarcar el checkbox para la siguiente búsqueda
            try:
                if checkbox.is_checked():
                    checkbox.click(force=True)
            except:
                pass
            
            # Limpiar el campo de búsqueda para la siguiente factura
            try:
                search_input = self.page.locator('input[placeholder="Buscar"], input[type="search"]').first
                search_input.fill("")
                self.page.wait_for_timeout(500)
            except:
                pass
            
            return DownloadResult(
                invoice_number=invoice_number,
                success=True,
                file_path=str(file_path)
            )
            
        except PlaywrightTimeout as e:
            print(f"[{self.name}] Timeout descargando factura: {e}")
            self.take_screenshot(f"error_download_timeout_{invoice_number}")
            return DownloadResult(
                invoice_number=invoice_number,
                success=False,
                error_message=f"Timeout: {str(e)[:100]}"
            )
        except Exception as e:
            print(f"[{self.name}] Error descargando factura: {e}")
            self.take_screenshot(f"error_download_{invoice_number}")
            return DownloadResult(
                invoice_number=invoice_number,
                success=False,
                error_message=str(e)[:200]
            )


    def process_invoices(self, invoice_numbers: List[str], max_retries: int = 4) -> List[DownloadResult]:
        """
        Procesa una lista de facturas de Monroe.
        
        Sobrescribe el método base para incluir:
        1. Login
        2. Navegación a Comprobantes
        3. Configuración de Período
        4. Procesamiento de facturas
        
        Args:
            invoice_numbers: Lista de números de factura
            max_retries: Número máximo de intentos por factura
        """
        from .base_scraper import DownloadResult
        
        self._log(f"Iniciando procesamiento de {len(invoice_numbers)} facturas Monroe")
        
        # Paso 1: Login
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
        
        # Paso 2: Navegar a Comprobantes
        if not self.navigate_to_comprobantes():
            self._log("ERROR: No se pudo navegar a Comprobantes", "ERROR")
            return [
                DownloadResult(
                    invoice_number=inv,
                    success=False,
                    error_message="Error navegando a Comprobantes"
                ) for inv in invoice_numbers
            ]
        
        # Paso 3: Configurar Período (forzar para asegurar rango máximo)
        if not self.configure_period(force=True):
            self._log("ERROR: No se pudo configurar el período", "ERROR")
            return [
                DownloadResult(
                    invoice_number=inv,
                    success=False,
                    error_message="Error configurando período"
                ) for inv in invoice_numbers
            ]
        
        # Paso 4: Procesar facturas usando la lógica del padre
        results = []
        failed_invoices = []
        
        total = len(invoice_numbers)
        for idx, invoice_number in enumerate(invoice_numbers, 1):
            print(f"[{self.name}] Procesando factura {idx}/{total}: {invoice_number}")
            self._log(f"Procesando factura {idx}/{total}: {invoice_number}")
            
            result = self._process_single_invoice(invoice_number, max_retries)
            results.append(result)
            
            if result.success:
                print(f"  [OK] Descargado: {result.file_path}")
                self._log(f"OK: {invoice_number} -> {result.file_path}")
            else:
                print(f"  [FAIL] Error: {result.error_message}")
                self._log(f"FALLIDA: {invoice_number} - {result.error_message}", "ERROR")
                failed_invoices.append(invoice_number)
        
        # Resumen
        successful = sum(1 for r in results if r.success)
        print(f"\n[{self.name}] ========== RESUMEN ==========")
        print(f"[{self.name}] Total: {total} | Exitosos: {successful} | Fallidos: {len(failed_invoices)}")
        self._log(f"RESUMEN: Total={total}, Exitosos={successful}, Fallidos={len(failed_invoices)}")
        
        if failed_invoices:
            print(f"[{self.name}] Facturas fallidas:")
            self._log("FACTURAS FALLIDAS:", "ERROR")
            for inv in failed_invoices:
                print(f"  - {inv}")
                self._log(f"  - {inv}", "ERROR")
        
        return results


def create_monroe_scraper(headless: bool = True) -> MonroeScraper:
    """Factory function para crear un scraper de Monroe configurado."""
    return MonroeScraper(headless=headless)

