"""
Script de prueba para el scraper de Suizo Argentina.
Ejecutar: python test_scraper.py

Requiere variables de entorno:
- SUIZO_USERNAME
- SUIZO_PASSWORD
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

from src.scraper.suizo_scraper import SuizoScraper
from src.scraper.monroe_scraper import MonroeScraper
from src.utils.session_manager import interactive_login_and_save, is_session_valid, upload_session_to_gcs


# ============================================================
# TESTS DE SUIZO
# ============================================================

def test_login_only():
    """Prueba solo el login (sin descargar)."""
    print("=" * 50)
    print("TEST: Solo Login")
    print("=" * 50)
    
    # headless=False para ver el navegador
    with SuizoScraper(headless=False) as scraper:
        if scraper.login():
            print("\n✓ Login exitoso!")
            
            # Navegar a Mis Comprobantes
            if scraper.navigate_to_mis_comprobantes():
                print("✓ Navegación a Mis Comprobantes exitosa!")
                input("\nPresiona Enter para cerrar el navegador...")
            else:
                print("✗ Error navegando a Mis Comprobantes")
        else:
            print("\n✗ Login fallido")


def test_search_invoice(invoice_number: str):
    """Prueba buscar una factura específica."""
    print("=" * 50)
    print(f"TEST: Buscar factura {invoice_number}")
    print("=" * 50)
    
    with SuizoScraper(headless=False) as scraper:
        if scraper.login():
            print("✓ Login exitoso!")
            
            if scraper.navigate_to_mis_comprobantes():
                print("✓ En Mis Comprobantes")
                
                if scraper.search_invoice(invoice_number):
                    print(f"✓ Factura {invoice_number} encontrada!")
                else:
                    print(f"✗ Factura {invoice_number} no encontrada")
                
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("✗ Login fallido")


def test_download_invoice(invoice_number: str):
    """Prueba descargar una factura específica."""
    print("=" * 50)
    print(f"TEST: Descargar factura {invoice_number}")
    print("=" * 50)
    
    with SuizoScraper(headless=False) as scraper:
        if scraper.login():
            print("✓ Login exitoso!")
            
            if scraper.navigate_to_mis_comprobantes():
                print("✓ En Mis Comprobantes")
                
                result = scraper.download_invoice(invoice_number)
                
                if result.success:
                    print(f"\n✓ Descarga exitosa!")
                    print(f"  Archivo: {result.file_path}")
                else:
                    print(f"\n✗ Descarga fallida: {result.error_message}")
                
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("✗ Login fallido")


def test_multiple_invoices(invoice_numbers: list):
    """Prueba descargar múltiples facturas."""
    print("=" * 50)
    print(f"TEST: Descargar {len(invoice_numbers)} facturas")
    print("=" * 50)
    
    with SuizoScraper(headless=False) as scraper:
        if scraper.login():
            print("✓ Login exitoso!")
            
            if scraper.navigate_to_mis_comprobantes():
                print("✓ En Mis Comprobantes\n")
                
                results = scraper.process_invoices(invoice_numbers)
                
                print("\n" + "=" * 50)
                print("RESUMEN:")
                print("=" * 50)
                for r in results:
                    status = "✓" if r.success else "✗"
                    print(f"  {status} {r.invoice_number}: {r.file_path or r.error_message}")
                
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("✗ Login fallido")


def test_drive_upload():
    """Prueba subir un archivo de prueba a Google Drive."""
    print("=" * 50)
    print("TEST: Subir archivo a Google Drive")
    print("=" * 50)
    
    from src.storage.google_drive import GoogleDriveUploader
    from pathlib import Path
    
    # Verificar variables de entorno
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/google_service_account.json")
    
    print(f"\nConfiguración:")
    print(f"  GOOGLE_DRIVE_FOLDER_ID: {folder_id}")
    print(f"  GOOGLE_CREDENTIALS_PATH: {creds_path}")
    print(f"  Archivo de credenciales existe: {Path(creds_path).exists()}")
    
    if not folder_id:
        print("\n✗ ERROR: Falta GOOGLE_DRIVE_FOLDER_ID")
        return
    
    if not Path(creds_path).exists():
        print(f"\n✗ ERROR: No existe el archivo de credenciales: {creds_path}")
        return
    
    # Crear archivo de prueba
    test_file = Path("downloads/test_upload.txt")
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("Este es un archivo de prueba para Google Drive.\nFecha: " + 
                         __import__('datetime').datetime.now().isoformat())
    print(f"\n✓ Archivo de prueba creado: {test_file}")
    
    # Intentar subir
    print("\nIntentando subir a Google Drive...")
    uploader = GoogleDriveUploader(credentials_path=creds_path, folder_id=folder_id)
    
    if uploader.initialize():
        print("✓ Cliente de Drive inicializado")
        
        result = uploader.upload_file(str(test_file))
        
        if result.success:
            print(f"\n✓ ÉXITO!")
            print(f"  File ID: {result.drive_file_id}")
            print(f"  Link: {result.drive_link}")
        else:
            print(f"\n✗ ERROR: {result.error_message}")
    else:
        print("✗ ERROR: No se pudo inicializar el cliente de Drive")
    
    # Limpiar archivo de prueba
    test_file.unlink()
    print("\n✓ Archivo de prueba eliminado")


def test_drive_folder_access():
    """Verifica si el service account tiene acceso a la carpeta de Drive."""
    print("=" * 50)
    print("TEST: Verificar acceso a carpeta de Drive")
    print("=" * 50)
    
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from pathlib import Path
    
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/google_service_account.json")
    
    print(f"\nFolder ID a verificar: {folder_id}")
    
    if not folder_id or not Path(creds_path).exists():
        print("✗ Falta configuración")
        return
    
    try:
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.metadata.readonly']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        
        # Intentar obtener metadata de la carpeta (supportsAllDrives para Shared Drives)
        print("\nIntentando acceder a la carpeta...")
        folder = service.files().get(
            fileId=folder_id, 
            fields='id, name, mimeType',
            supportsAllDrives=True
        ).execute()
        
        print(f"\n✓ ACCESO EXITOSO!")
        print(f"  ID: {folder.get('id')}")
        print(f"  Nombre: {folder.get('name')}")
        print(f"  Tipo: {folder.get('mimeType')}")
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print("\nPosibles causas:")
        print("  1. El Folder ID es incorrecto")
        print("  2. La carpeta fue eliminada")
        print("  3. El Service Account no tiene acceso a la carpeta")
        print("\nSolución:")
        print("  - Ve a Google Drive")
        print("  - Abre la carpeta destino")
        print("  - Click derecho → Compartir")
        print("  - Agrega el email del Service Account con permisos de 'Editor'")


# ============================================================
# TESTS DE MONROE
# ============================================================

def test_monroe_login_only(headless: bool = False):
    """Prueba solo el login de Monroe (sin descargar)."""
    print("=" * 50)
    print(f"TEST MONROE: Solo Login (headless={headless})")
    print("=" * 50)
    
    with MonroeScraper(headless=headless) as scraper:
        if scraper.login():
            print("\n[OK] Login exitoso!")
            
            # Navegar a comprobantes para verificar que la sesión funciona completa
            if scraper.navigate_to_comprobantes():
                print("[OK] Navegacion a Comprobantes exitosa!")
                scraper.take_screenshot("login_success_comprobantes")
            else:
                print("[WARN] Login OK pero no pudo navegar a Comprobantes")
                scraper.take_screenshot("login_success_no_nav")
            
            if not headless:
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("\n[FAIL] Login fallido")
            scraper.take_screenshot("login_failed")


def test_monroe_search_invoice(invoice_number: str):
    """Prueba buscar una factura especifica en Monroe."""
    print("=" * 50)
    print(f"TEST MONROE: Buscar factura {invoice_number}")
    print("=" * 50)
    
    with MonroeScraper(headless=False) as scraper:
        if scraper.login():
            print("[OK] Login exitoso!")
            
            if scraper.navigate_to_comprobantes():
                print("[OK] En seccion de comprobantes")
                
                # Verificar periodo (debe configurarse manualmente en opcion 14)
                if scraper.configure_period():
                    print("[OK] Periodo configurado")
                    
                    if scraper.search_invoice(invoice_number):
                        print(f"[OK] Factura {invoice_number} encontrada!")
                    else:
                        print(f"[FAIL] Factura {invoice_number} no encontrada")
                else:
                    print("[FAIL] Error configurando periodo")
                
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("[FAIL] Login fallido")


def test_monroe_download_invoice(invoice_number: str):
    """Prueba descargar una factura especifica de Monroe."""
    print("=" * 50)
    print(f"TEST MONROE: Descargar factura {invoice_number}")
    print("=" * 50)
    
    with MonroeScraper(headless=False) as scraper:
        if scraper.login():
            print("[OK] Login exitoso!")
            
            if scraper.navigate_to_comprobantes():
                print("[OK] En seccion de comprobantes")
                
                # Configurar periodo (solo la primera vez)
                if scraper.configure_period():
                    print("[OK] Periodo configurado")
                    
                    result = scraper.download_invoice(invoice_number)
                    
                    if result.success:
                        print(f"\n[OK] Descarga exitosa!")
                        print(f"  Archivo: {result.file_path}")
                    else:
                        print(f"\n[FAIL] Descarga fallida: {result.error_message}")
                else:
                    print("[FAIL] Error configurando periodo")
                
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("[FAIL] Login fallido")


def test_monroe_with_chrome_profile():
    """Login semi-automatico: abre navegador visible y espera intervencion manual si hay captcha."""
    print("=" * 50)
    print("TEST MONROE: Login Semi-Automatico")
    print("=" * 50)
    print("\n[COMO FUNCIONA]")
    print("1. Se abrira un navegador visible")
    print("2. Intentara login automatico")
    print("3. Si aparece captcha o error, te pedira que lo resuelvas manualmente")
    print("4. Una vez logueado, navegara al dashboard")
    print("5. IMPORTANTE: La sesion se guarda SOLO cuando estas en masaWeb")
    input("\nPresiona Enter para comenzar...")
    
    from src.utils.session_manager import save_cookies
    
    # Usar headless=False para permitir intervencion manual
    with MonroeScraper(headless=False, use_chrome_profile=False) as scraper:
        if scraper.login():
            print("\n[OK] Login exitoso!")
            
            if scraper.navigate_to_comprobantes():
                print("[OK] Navegacion a Comprobantes exitosa!")
                
                # Verificar URL
                current_url = scraper.page.url
                print(f"[INFO] URL actual: {current_url}")
                
                if "masaWeb" in current_url:
                    # Ahora sí guardar las cookies (estamos en el dashboard)
                    print("\n[Session] Guardando sesion desde el dashboard...")
                    
                    # Mostrar cookies para debugging
                    cookies = scraper.context.cookies()
                    print(f"[Session] Cookies totales: {len(cookies)}")
                    auth_cookies = [c for c in cookies if c['name'] not in ['_ga', '_ga_1HWKMEWGPJ'] and not c['name'].startswith('5745_')]
                    print(f"[Session] Cookies relevantes: {len(auth_cookies)}")
                    for c in auth_cookies:
                        val = c.get('value', '')
                        print(f"  - {c['name']}: {val[:40]}..." if len(val) > 40 else f"  - {c['name']}: {val}")
                    
                    # Guardar
                    save_cookies(scraper.context, "monroe")
                    print("\n[OK] Sesion guardada!")
                    print("     Ahora puedes probar la opcion 16 (headless)")
                    print("     O subir a GCS con la opcion 18")
                else:
                    print("[WARN] No estas en masaWeb, la sesion podria no ser valida")
                
                # Configurar periodo
                if scraper.configure_period():
                    print("[OK] Periodo verificado!")
                    scraper.take_screenshot("monroe_ready")
            
            input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("\n[FAIL] Login fallido")
            print("       Revisa el navegador para mas detalles")


def test_monroe_multiple_invoices(invoice_numbers: list):
    """Prueba descargar multiples facturas de Monroe."""
    print("=" * 50)
    print(f"TEST MONROE: Descargar {len(invoice_numbers)} facturas")
    print("=" * 50)
    
    with MonroeScraper(headless=False) as scraper:
        if scraper.login():
            print("[OK] Login exitoso!")
            
            if scraper.navigate_to_comprobantes():
                print("[OK] En seccion de comprobantes")
                
                # Configurar periodo (forzar para asegurar rango correcto)
                if scraper.configure_period(force=True):
                    print("[OK] Periodo configurado\n")
                    
                    results = scraper.process_invoices(invoice_numbers)
                    
                    print("\n" + "=" * 50)
                    print("RESUMEN:")
                    print("=" * 50)
                    for r in results:
                        status = "[OK]" if r.success else "[FAIL]"
                        print(f"  {status} {r.invoice_number}: {r.file_path or r.error_message}")
                else:
                    print("[FAIL] Error configurando periodo")
                
                input("\nPresiona Enter para cerrar el navegador...")
        else:
            print("[FAIL] Login fallido")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("¿Qué prueba quieres ejecutar?")
    print("=" * 50)
    print("\n--- SUIZO ARGENTINA ---")
    print("1. Solo login")
    print("2. Buscar una factura")
    print("3. Descargar una factura")
    print("4. Descargar múltiples facturas")
    print("\n--- MONROE AMERICANA ---")
    print("10. Solo login (visible)")
    print("11. Buscar una factura")
    print("12. Descargar una factura")
    print("13. Descargar multiples facturas")
    print("14. [IMPORTANTE] Guardar sesion (evitar captcha)")
    print("15. Ver estado de sesiones guardadas")
    print("16. [TEST] Login HEADLESS (verificar bypass captcha)")
    print("17. [RECOMENDADO] Login semi-automatico (resuelve captcha 1 vez)")
    print("18. [PRODUCCION] Subir sesion Monroe a GCS")
    print("\n--- GOOGLE DRIVE ---")
    print("20. Probar subida a Google Drive")
    print("21. Verificar acceso a carpeta de Drive")
    
    opcion = input("\nOpción: ").strip()
    
    # ========== SUIZO ==========
    if opcion == "1":
        if not os.getenv("SUIZO_USERNAME") or not os.getenv("SUIZO_PASSWORD"):
            print("ERROR: Configura SUIZO_USERNAME y SUIZO_PASSWORD")
            exit(1)
        test_login_only()
    
    elif opcion == "2":
        if not os.getenv("SUIZO_USERNAME") or not os.getenv("SUIZO_PASSWORD"):
            print("ERROR: Configura SUIZO_USERNAME y SUIZO_PASSWORD")
            exit(1)
        numero = input("Número de factura (ej: 20057036): ").strip()
        test_search_invoice(numero)
    
    elif opcion == "3":
        if not os.getenv("SUIZO_USERNAME") or not os.getenv("SUIZO_PASSWORD"):
            print("ERROR: Configura SUIZO_USERNAME y SUIZO_PASSWORD")
            exit(1)
        numero = input("Número de factura (ej: 20057036): ").strip()
        test_download_invoice(numero)
    
    elif opcion == "4":
        if not os.getenv("SUIZO_USERNAME") or not os.getenv("SUIZO_PASSWORD"):
            print("ERROR: Configura SUIZO_USERNAME y SUIZO_PASSWORD")
            exit(1)
        numeros_input = input("Números de factura separados por coma: ").strip()
        numeros = [n.strip() for n in numeros_input.split(",")]
        test_multiple_invoices(numeros)
    
    # ========== MONROE ==========
    elif opcion == "10":
        if not os.getenv("MONROE_USERNAME") or not os.getenv("MONROE_PASSWORD"):
            print("ERROR: Configura MONROE_USERNAME y MONROE_PASSWORD en .env")
            exit(1)
        test_monroe_login_only()
    
    elif opcion == "11":
        if not os.getenv("MONROE_USERNAME") or not os.getenv("MONROE_PASSWORD"):
            print("ERROR: Configura MONROE_USERNAME y MONROE_PASSWORD en .env")
            exit(1)
        numero = input("Número de factura: ").strip()
        test_monroe_search_invoice(numero)
    
    elif opcion == "12":
        if not os.getenv("MONROE_USERNAME") or not os.getenv("MONROE_PASSWORD"):
            print("ERROR: Configura MONROE_USERNAME y MONROE_PASSWORD en .env")
            exit(1)
        numero = input("Número de factura: ").strip()
        test_monroe_download_invoice(numero)
    
    elif opcion == "13":
        if not os.getenv("MONROE_USERNAME") or not os.getenv("MONROE_PASSWORD"):
            print("ERROR: Configura MONROE_USERNAME y MONROE_PASSWORD en .env")
            exit(1)
        numeros_input = input("Numeros de factura separados por coma: ").strip()
        numeros = [n.strip() for n in numeros_input.split(",")]
        test_monroe_multiple_invoices(numeros)
    
    elif opcion == "14":
        # Guardar sesion de Monroe (login manual para evitar captcha)
        interactive_login_and_save(
            provider="monroe",
            login_url="https://www.monroeamericana.com.ar/apps/login/ext/index.html"
        )
    
    elif opcion == "15":
        # Ver estado de sesiones
        print("\n" + "=" * 50)
        print("ESTADO DE SESIONES GUARDADAS")
        print("=" * 50)
        for provider in ["monroe", "suizo", "delsud"]:
            valid = is_session_valid(provider)
            status = "[OK] Valida" if valid else "[X] No existe o expirada"
            print(f"  {provider}: {status}")
        print()
    
    elif opcion == "16":
        # Test headless para verificar bypass de captcha
        if not os.getenv("MONROE_USERNAME") or not os.getenv("MONROE_PASSWORD"):
            print("ERROR: Configura MONROE_USERNAME y MONROE_PASSWORD en .env")
            exit(1)
        print("\n[INFO] Probando login en modo HEADLESS...")
        print("[INFO] Si funciona, el storage_state esta bypasseando el captcha!")
        print()
        test_monroe_login_only(headless=True)
    
    elif opcion == "17":
        # Login semi-automatico (recomendado)
        if not os.getenv("MONROE_USERNAME") or not os.getenv("MONROE_PASSWORD"):
            print("ERROR: Configura MONROE_USERNAME y MONROE_PASSWORD en .env")
            exit(1)
        test_monroe_with_chrome_profile()
    
    elif opcion == "18":
        # Subir sesion a GCS para produccion
        print("\n" + "=" * 50)
        print("SUBIR SESION MONROE A GCS (PRODUCCION)")
        print("=" * 50)
        
        if is_session_valid("monroe"):
            print("[OK] Sesion Monroe valida encontrada")
            print("\nSubiendo a GCS...")
            if upload_session_to_gcs("monroe"):
                print("\n[OK] Sesion subida exitosamente!")
                print("    Cloud Run ahora usara esta sesion.")
            else:
                print("\n[ERROR] No se pudo subir la sesion.")
                print("    Verifica que tengas credenciales de GCP configuradas.")
        else:
            print("[ERROR] No hay sesion valida de Monroe.")
            print("    Primero ejecuta la opcion 17 para crear una sesion.")
    
    # ========== GOOGLE DRIVE ==========
    elif opcion == "20":
        test_drive_upload()
    
    elif opcion == "21":
        test_drive_folder_access()
    
    else:
        print("Opción inválida")

