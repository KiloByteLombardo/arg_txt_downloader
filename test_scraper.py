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


if __name__ == "__main__":
    print("\n¿Qué prueba quieres ejecutar?")
    print("1. Solo login")
    print("2. Buscar una factura")
    print("3. Descargar una factura")
    print("4. Descargar múltiples facturas")
    print("5. Probar subida a Google Drive")
    print("6. Verificar acceso a carpeta de Drive")
    
    opcion = input("\nOpción (1-6): ").strip()
    
    if opcion == "1":
        # Verificar credenciales para opciones de scraping
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
    
    elif opcion == "5":
        test_drive_upload()
    
    elif opcion == "6":
        test_drive_folder_access()
    
    else:
        print("Opción inválida")

