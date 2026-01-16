"""
Módulo para integración con Google Drive.
Permite subir archivos descargados a una carpeta de Drive.
"""
import os
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Scopes necesarios para Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']


@dataclass
class UploadResult:
    """Resultado de una subida a Google Drive."""
    file_name: str
    success: bool
    drive_file_id: Optional[str] = None
    drive_link: Optional[str] = None
    error_message: Optional[str] = None


class GoogleDriveUploader:
    """
    Cliente para subir archivos a Google Drive.
    Usa una cuenta de servicio para autenticación.
    """
    
    def __init__(
        self, 
        credentials_path: Optional[str] = None,
        folder_id: Optional[str] = None
    ):
        """
        Inicializa el cliente de Google Drive.
        
        Args:
            credentials_path: Ruta al archivo JSON de credenciales
            folder_id: ID de la carpeta de destino en Google Drive
        """
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH", 
            "credentials/google_service_account.json"
        )
        
        # Limpiar folder_id de caracteres extraños
        raw_folder_id = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
        self.folder_id = self._clean_folder_id(raw_folder_id)
        
        self.service = None
        self._initialized = False
    
    def _clean_folder_id(self, folder_id: str) -> Optional[str]:
        """Limpia el folder ID de caracteres extraños."""
        if not folder_id:
            return None
        
        # Quitar espacios, saltos de línea, guiones al inicio/final
        cleaned = folder_id.strip().strip('-').strip()
        
        # Si viene como URL, extraer solo el ID
        if 'drive.google.com' in cleaned:
            # Formato: https://drive.google.com/drive/folders/ID
            if '/folders/' in cleaned:
                cleaned = cleaned.split('/folders/')[-1].split('?')[0].split('/')[0]
            # Formato: https://drive.google.com/open?id=ID
            elif 'id=' in cleaned:
                cleaned = cleaned.split('id=')[-1].split('&')[0]
        
        # Validar que solo contenga caracteres válidos (alfanuméricos, guiones y guiones bajos)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', cleaned):
            print(f"[Drive] ADVERTENCIA: folder_id contiene caracteres inválidos: '{folder_id}' -> '{cleaned}'")
        
        print(f"[Drive] Folder ID configurado: {cleaned}")
        return cleaned if cleaned else None
        
    def initialize(self) -> bool:
        """
        Inicializa la conexión con Google Drive.
        
        Returns:
            True si la inicialización fue exitosa
        """
        try:
            if not Path(self.credentials_path).exists():
                print(f"[Drive] ERROR: Credenciales no encontradas: {self.credentials_path}")
                return False
            
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
            
            self.service = build('drive', 'v3', credentials=credentials)
            self._initialized = True
            
            print(f"[Drive] Inicializado. Carpeta destino: {self.folder_id}")
            return True
            
        except Exception as e:
            print(f"[Drive] ERROR de inicialización: {e}")
            return False
    
    def upload_file(
        self, 
        file_path: str, 
        drive_filename: Optional[str] = None,
        folder_id: Optional[str] = None
    ) -> UploadResult:
        """
        Sube un archivo a Google Drive.
        
        Args:
            file_path: Ruta local del archivo a subir
            drive_filename: Nombre del archivo en Drive (opcional)
            folder_id: ID de carpeta de destino (opcional)
            
        Returns:
            UploadResult con el resultado de la subida
        """
        if not self._initialized:
            if not self.initialize():
                return UploadResult(
                    file_name=Path(file_path).name,
                    success=False,
                    error_message="No se pudo inicializar Google Drive"
                )
        
        file_path = Path(file_path)
        
        if not file_path.exists():
            return UploadResult(
                file_name=file_path.name,
                success=False,
                error_message=f"Archivo no encontrado: {file_path}"
            )
        
        target_folder = folder_id or self.folder_id
        filename = drive_filename or file_path.name
        
        try:
            # Metadata del archivo
            file_metadata = {'name': filename}
            
            if target_folder:
                file_metadata['parents'] = [target_folder]
            
            # Determinar MIME type
            mime_type = 'text/plain' if file_path.suffix == '.txt' else 'application/octet-stream'
            
            # Crear media para upload
            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True
            )
            
            # Subir archivo (supportsAllDrives=True para Shared Drives)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            print(f"[Drive] Archivo subido: {filename} -> {file.get('webViewLink')}")
            
            return UploadResult(
                file_name=filename,
                success=True,
                drive_file_id=file.get('id'),
                drive_link=file.get('webViewLink')
            )
            
        except Exception as e:
            print(f"[Drive] ERROR subiendo {filename}: {e}")
            return UploadResult(
                file_name=filename,
                success=False,
                error_message=str(e)
            )
    
    def upload_files(
        self, 
        file_paths: List[str],
        folder_id: Optional[str] = None
    ) -> List[UploadResult]:
        """
        Sube múltiples archivos a Google Drive.
        
        Args:
            file_paths: Lista de rutas de archivos a subir
            folder_id: ID de carpeta de destino
            
        Returns:
            Lista de UploadResult
        """
        results = []
        total = len(file_paths)
        
        for idx, file_path in enumerate(file_paths, 1):
            print(f"[Drive] Subiendo {idx}/{total}: {file_path}")
            result = self.upload_file(file_path, folder_id=folder_id)
            results.append(result)
        
        successful = sum(1 for r in results if r.success)
        print(f"[Drive] Completado: {successful}/{total} archivos subidos")
        
        return results
    
    def create_subfolder(
        self, 
        folder_name: str, 
        parent_folder_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Crea una subcarpeta en Google Drive.
        
        Args:
            folder_name: Nombre de la carpeta a crear
            parent_folder_id: ID de la carpeta padre
            
        Returns:
            ID de la carpeta creada o None si falla
        """
        if not self._initialized:
            if not self.initialize():
                return None
        
        parent = parent_folder_id or self.folder_id
        
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            if parent:
                file_metadata['parents'] = [parent]
            
            folder = self.service.files().create(
                body=file_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()
            
            folder_id = folder.get('id')
            print(f"[Drive] Carpeta creada: {folder_name} (ID: {folder_id})")
            
            return folder_id
            
        except Exception as e:
            print(f"[Drive] ERROR creando carpeta {folder_name}: {e}")
            return None


    def get_or_create_subfolder(
        self, 
        folder_name: str, 
        parent_folder_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Obtiene una subcarpeta existente o la crea si no existe.
        
        Args:
            folder_name: Nombre de la carpeta
            parent_folder_id: ID de la carpeta padre
            
        Returns:
            ID de la carpeta o None si falla
        """
        if not self._initialized:
            if not self.initialize():
                return None
        
        parent = parent_folder_id or self.folder_id
        
        try:
            # Buscar si ya existe la carpeta
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent:
                query += f" and '{parent}' in parents"
            
            results = self.service.files().list(
                q=query,
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                folder_id = files[0]['id']
                print(f"[Drive] Carpeta existente encontrada: {folder_name} (ID: {folder_id})")
                return folder_id
            
            # Si no existe, crearla
            print(f"[Drive] Creando carpeta: {folder_name}")
            return self.create_subfolder(folder_name, parent_folder_id)
            
        except Exception as e:
            print(f"[Drive] ERROR buscando/creando carpeta {folder_name}: {e}")
            # Intentar crear de todas formas
            return self.create_subfolder(folder_name, parent_folder_id)


def create_drive_uploader() -> GoogleDriveUploader:
    """Factory function para crear un uploader de Google Drive."""
    return GoogleDriveUploader()
