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


if __name__ == "__main__":
    # Verificar credenciales
    if not os.getenv("SUIZO_USERNAME") or not os.getenv("SUIZO_PASSWORD"):
        print("ERROR: Configura las variables de entorno:")
        print("  SUIZO_USERNAME=tu_usuario")
        print("  SUIZO_PASSWORD=tu_contraseña")
        print("\nO crea un archivo .env con estas variables")
        exit(1)
    
    print("\n¿Qué prueba quieres ejecutar?")
    print("1. Solo login")
    print("2. Buscar una factura")
    print("3. Descargar una factura")
    print("4. Descargar múltiples facturas")
    
    opcion = input("\nOpción (1-4): ").strip()
    
    if opcion == "1":
        test_login_only()
    
    elif opcion == "2":
        numero = input("Número de factura (ej: 20057036): ").strip()
        test_search_invoice(numero)
    
    elif opcion == "3":
        numero = input("Número de factura (ej: 20057036): ").strip()
        test_download_invoice(numero)
    
    elif opcion == "4":
        numeros_input = input("Números de factura separados por coma: ").strip()
        numeros = [n.strip() for n in numeros_input.split(",")]
        test_multiple_invoices(numeros)
    
    else:
        print("Opción inválida")

