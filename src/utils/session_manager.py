"""
Gestión de sesiones y cookies para evitar captchas en logins repetidos.

Uso:
1. Ejecutar save_session() para login manual y guardar storage state completo
2. El scraper usa load_session() para reutilizar la sesión
"""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from playwright.sync_api import sync_playwright, BrowserContext


# Directorio para guardar sesiones
SESSIONS_DIR = Path("sessions")


def get_session_path(provider: str) -> Path:
    """Retorna la ruta del archivo de sesión para un proveedor."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{provider.lower()}_session.json"


def get_storage_state_path(provider: str) -> Path:
    """Retorna la ruta del archivo de storage state para un proveedor."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{provider.lower()}_storage_state.json"


def save_cookies(context: BrowserContext, provider: str) -> str:
    """
    Guarda el storage state completo (cookies + localStorage) del contexto.
    
    Args:
        context: Contexto del navegador con la sesión activa
        provider: Nombre del proveedor (ej: 'monroe', 'suizo')
    
    Returns:
        Ruta del archivo guardado
    """
    session_path = get_session_path(provider)
    storage_state_path = get_storage_state_path(provider)
    
    # Guardar storage state completo (incluye cookies y localStorage)
    context.storage_state(path=str(storage_state_path))
    
    # Obtener cookies para el archivo de metadatos
    cookies = context.cookies()
    
    # Calcular expiración real basada en cookies (si existe)
    cookie_expires = []
    for c in cookies:
        try:
            exp = c.get("expires")
            if exp and exp > 0:
                cookie_expires.append(exp)
        except Exception:
            continue
    
    if cookie_expires:
        max_expires = max(cookie_expires)
        expires_at = datetime.fromtimestamp(max_expires).isoformat()
    else:
        # Fallback conservador si no hay expiración en cookies
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
    
    session_data = {
        "provider": provider,
        "saved_at": datetime.now().isoformat(),
        "expires_at": expires_at,
        "cookies": cookies,
        "storage_state_path": str(storage_state_path)
    }
    
    with open(session_path, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)
    
    print(f"[Session] Sesion guardada en: {session_path}")
    print(f"[Session] Storage state: {storage_state_path}")
    print(f"[Session] Cookies guardadas: {len(cookies)}")
    print(f"[Session] Expira: {session_data['expires_at']}")
    
    return str(session_path)


def load_cookies(provider: str) -> Optional[List[Dict]]:
    """
    Carga las cookies guardadas para un proveedor.
    (Mantener para compatibilidad, pero preferir load_storage_state)
    
    Args:
        provider: Nombre del proveedor
    
    Returns:
        Lista de cookies o None si no existen/expiraron
    """
    session_path = get_session_path(provider)
    
    if not session_path.exists():
        print(f"[Session] No existe sesion guardada para {provider}")
        return None
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Verificar expiración
        expires_at = datetime.fromisoformat(session_data.get('expires_at', '2000-01-01'))
        if datetime.now() > expires_at:
            print(f"[Session] Sesion de {provider} expirada")
            return None
        
        cookies = session_data.get('cookies', [])
        saved_at = session_data.get('saved_at', 'desconocido')
        
        print(f"[Session] Sesion de {provider} cargada")
        print(f"[Session] Guardada: {saved_at}")
        print(f"[Session] Cookies: {len(cookies)}")
        
        return cookies
        
    except Exception as e:
        print(f"[Session] Error cargando sesion: {e}")
        return None


def upload_session_to_gcs(provider: str) -> bool:
    """
    Sube el storage_state local a GCS para uso en producción.
    
    Args:
        provider: Nombre del proveedor
    
    Returns:
        True si se subió exitosamente
    """
    storage_state_path = get_storage_state_path(provider)
    
    if not storage_state_path.exists():
        print(f"[Session] No existe storage state local para {provider}")
        return False
    
    bucket_name = os.getenv("GCS_BUCKET_NAME", "arg_txt_error_screenshots")
    gcs_path = f"sessions/{provider.lower()}_storage_state.json"
    
    try:
        from google.cloud import storage
        from google.oauth2 import service_account
        
        print(f"[Session] Subiendo sesion a GCS: gs://{bucket_name}/{gcs_path}")
        
        # Buscar archivo de credenciales
        credentials_path = Path("credentials.json")
        if credentials_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
            client = storage.Client(credentials=credentials)
        else:
            client = storage.Client()
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        
        blob.upload_from_filename(str(storage_state_path))
        print(f"[Session] Sesion subida exitosamente!")
        print(f"[Session] URI: gs://{bucket_name}/{gcs_path}")
        
        return True
        
    except Exception as e:
        print(f"[Session] Error subiendo sesion a GCS: {e}")
        return False


def download_session_from_gcs(provider: str) -> bool:
    """
    Descarga el storage_state desde GCS si no existe localmente.
    
    Args:
        provider: Nombre del proveedor
    
    Returns:
        True si se descargó o ya existe, False si falló
    """
    storage_state_path = get_storage_state_path(provider)
    
    # Si ya existe localmente, no descargar
    if storage_state_path.exists():
        print(f"[Session] Storage state local existe para {provider}")
        return True
    
    # Intentar descargar desde GCS
    bucket_name = os.getenv("GCS_BUCKET_NAME", "arg_txt_error_screenshots")
    gcs_path = f"sessions/{provider.lower()}_storage_state.json"
    
    try:
        from google.cloud import storage
        from google.oauth2 import service_account
        
        print(f"[Session] Descargando sesion desde GCS: gs://{bucket_name}/{gcs_path}")
        
        # Buscar archivo de credenciales
        credentials_path = Path("credentials.json")
        if credentials_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
            client = storage.Client(credentials=credentials)
        else:
            client = storage.Client()
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        
        if blob.exists():
            # Asegurar que existe el directorio
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            
            # Descargar
            blob.download_to_filename(str(storage_state_path))
            print(f"[Session] Sesion descargada: {storage_state_path}")
            
            # También crear el archivo de metadata
            session_path = get_session_path(provider)
            if not session_path.exists():
                session_data = {
                    "provider": provider,
                    "saved_at": datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
                    "cookies": [],
                    "storage_state_path": str(storage_state_path),
                    "source": "GCS"
                }
                with open(session_path, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2)
            
            return True
        else:
            print(f"[Session] No existe sesion en GCS: gs://{bucket_name}/{gcs_path}")
            return False
            
    except Exception as e:
        print(f"[Session] Error descargando sesion desde GCS: {e}")
        return False


def get_storage_state(provider: str) -> Optional[str]:
    """
    Obtiene la ruta del storage state si existe y no ha expirado.
    Intenta descargar desde GCS si no existe localmente.
    
    Args:
        provider: Nombre del proveedor
    
    Returns:
        Ruta al archivo de storage state o None
    """
    session_path = get_session_path(provider)
    storage_state_path = get_storage_state_path(provider)
    
    # Si no existe localmente, intentar descargar desde GCS
    if not storage_state_path.exists():
        print(f"[Session] No existe storage state local para {provider}, intentando GCS...")
        download_session_from_gcs(provider)
    
    if not storage_state_path.exists():
        print(f"[Session] No existe storage state para {provider}")
        return None
    
    if not session_path.exists():
        print(f"[Session] No existe metadata de sesion para {provider}, usando storage state")
        return str(storage_state_path)
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Verificar expiración
        expires_at = datetime.fromisoformat(session_data.get('expires_at', '2000-01-01'))
        if datetime.now() > expires_at:
            # Igual intentamos usar el storage state; el portal decide si es válido
            print(f"[Session] Sesion de {provider} expirada segun metadata, intentando igual...")
        
        saved_at = session_data.get('saved_at', 'desconocido')
        print(f"[Session] Storage state de {provider} disponible")
        print(f"[Session] Guardada: {saved_at}")
        
        return str(storage_state_path)
        
    except Exception as e:
        print(f"[Session] Error verificando sesion: {e}")
        return None


def is_session_valid(provider: str) -> bool:
    """Verifica si existe una sesión válida para el proveedor."""
    session_path = get_session_path(provider)
    
    if not session_path.exists():
        return False
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        expires_at = datetime.fromisoformat(session_data.get('expires_at', '2000-01-01'))
        return datetime.now() < expires_at
        
    except:
        return False


def delete_session(provider: str) -> bool:
    """Elimina la sesión guardada de un proveedor."""
    session_path = get_session_path(provider)
    
    if session_path.exists():
        session_path.unlink()
        print(f"[Session] Sesion de {provider} eliminada")
        return True
    
    return False


def interactive_login_and_save(
    provider: str,
    login_url: str,
    success_indicator: str = None
) -> bool:
    """
    Abre un navegador para login manual y guarda la sesión.
    
    Args:
        provider: Nombre del proveedor
        login_url: URL de login
        success_indicator: Selector o URL que indica login exitoso
    
    Returns:
        True si se guardó la sesión exitosamente
    """
    print("=" * 60)
    print(f"LOGIN MANUAL - {provider.upper()}")
    print("=" * 60)
    print(f"\n1. Se abrira el navegador en: {login_url}")
    print("2. Marca 'Recordar sesion por 7 dias' ANTES de iniciar sesion")
    print("3. Inicia sesion manualmente (resuelve el captcha si aparece)")
    print("4. Espera a que cargue el dashboard (masaWeb)")
    print("5. [IMPORTANTE] Ve a 'Comprobantes emitidos' y configura el PERIODO")
    print("   - Click en boton 'Periodo' (verde)")
    print("   - Configura el rango de fechas que necesites (max 60 dias)")
    print("   - Click en 'Consultar'")
    print("6. Una vez que veas las facturas, presiona ENTER en esta consola")
    print("\n" + "=" * 60)
    
    with sync_playwright() as p:
        # Lanzar navegador visible
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()
        try:
            from playwright_stealth import Stealth  # type: ignore[import-not-found]
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
            print("[Session] Stealth aplicado")
        except Exception as e:
            print(f"[Session] Stealth no disponible: {e}")
        
        # Navegar al login
        page.goto(login_url, wait_until="load")
        
        # Esperar a que el usuario complete el login
        input("\n>>> Presiona ENTER cuando hayas iniciado sesion exitosamente...")
        
        # Verificar si realmente está logueado
        current_url = page.url
        print(f"\n[Session] URL actual: {current_url}")
        
        # Tomar screenshot de verificación
        screenshot_path = SESSIONS_DIR / f"{provider}_login_verification.png"
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"[Session] Screenshot guardado: {screenshot_path}")
        
        # Verificar que estamos logueados antes de guardar
        current_url = page.url
        print(f"\n[Session] URL actual: {current_url}")
        
        # Para Monroe, debe estar en masaWeb
        if provider.lower() == "monroe":
            if "masaWeb" not in current_url and "/apps/login/" in current_url:
                print("[Session] ERROR: Aun estas en la pagina de login!")
                print("[Session] Debes completar el login y llegar al dashboard antes de guardar.")
                browser.close()
                return False
        
        # Mostrar cookies para debugging
        cookies = context.cookies()
        print(f"\n[Session] Cookies encontradas: {len(cookies)}")
        for c in cookies:
            # Mostrar solo las importantes (no las de analytics)
            if not c['name'].startswith('_ga') and not c['name'].startswith('5745_'):
                print(f"  - {c['name']}: {c['value'][:50]}..." if len(c.get('value', '')) > 50 else f"  - {c['name']}: {c['value']}")
        
        # También obtener sessionStorage (puede tener tokens)
        session_storage = page.evaluate("""() => {
            const items = {};
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                items[key] = sessionStorage.getItem(key);
            }
            return items;
        }""")
        
        if session_storage:
            print(f"\n[Session] sessionStorage encontrado: {len(session_storage)} items")
            for key, value in session_storage.items():
                print(f"  - {key}: {str(value)[:50]}..." if len(str(value)) > 50 else f"  - {key}: {value}")
        
        # Guardar cookies
        save_cookies(context, provider)
        
        # Cerrar
        browser.close()
    
    print("\n[Session] Sesion guardada localmente!")
    
    # Preguntar si subir a GCS
    upload = input("\n¿Subir sesion a GCS para produccion? (s/n): ").strip().lower()
    if upload == 's':
        upload_session_to_gcs(provider)
    
    print("\n[Session] Proceso completado!")
    return True


# ============================================================
# SCRIPT PRINCIPAL PARA GUARDAR SESIONES
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("GESTOR DE SESIONES - Guardar cookies para evitar captcha")
    print("=" * 60)
    
    print("\nProveedores disponibles:")
    print("1. Monroe Americana")
    print("2. Suizo Argentina")
    print("3. Del Sud")
    print("4. Ver sesiones guardadas")
    print("5. Eliminar sesion")
    
    opcion = input("\nOpcion: ").strip()
    
    if opcion == "1":
        interactive_login_and_save(
            provider="monroe",
            login_url="https://www.monroeamericana.com.ar/apps/login/ext/index.html"
        )
    
    elif opcion == "2":
        interactive_login_and_save(
            provider="suizo",
            login_url="https://web1.suizoargentina.com/login"
        )
    
    elif opcion == "3":
        url = input("URL de login de Del Sud: ").strip()
        interactive_login_and_save(
            provider="delsud",
            login_url=url
        )
    
    elif opcion == "4":
        print("\nSesiones guardadas:")
        for provider in ["monroe", "suizo", "delsud"]:
            valid = is_session_valid(provider)
            status = "[OK] Valida" if valid else "[X] No existe o expirada"
            print(f"  - {provider}: {status}")
    
    elif opcion == "5":
        provider = input("Proveedor a eliminar (monroe/suizo/delsud): ").strip().lower()
        delete_session(provider)
    
    else:
        print("Opcion invalida")

