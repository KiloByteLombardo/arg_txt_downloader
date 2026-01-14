"""
Módulo para integración con Google Cloud Storage.
Permite subir screenshots de errores y logs de ejecución.
"""
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from google.cloud import storage
from google.oauth2 import service_account


@dataclass
class GCSUploadResult:
    """Resultado de una subida a GCS."""
    file_name: str
    success: bool
    gcs_url: Optional[str] = None
    public_url: Optional[str] = None
    error_message: Optional[str] = None


class GCSUploader:
    """
    Cliente para subir archivos a Google Cloud Storage.
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        credentials_path: Optional[str] = None,
        prefix: str = ""
    ):
        """
        Inicializa el cliente de GCS.
        
        Args:
            bucket_name: Nombre del bucket
            credentials_path: Ruta al archivo JSON de credenciales
            prefix: Prefijo para los archivos (ej: "logs/", "screenshots/")
        """
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH",
            "credentials/google_service_account.json"
        )
        self.prefix = prefix
        
        self.client = None
        self.bucket = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """Inicializa la conexión con GCS."""
        if not self.bucket_name:
            print("[GCS] ERROR: No se configuró GCS_BUCKET_NAME")
            return False
            
        try:
            if Path(self.credentials_path).exists():
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                self.client = storage.Client(credentials=credentials)
            else:
                # En Cloud Run, usa las credenciales del servicio
                self.client = storage.Client()
            
            self.bucket = self.client.bucket(self.bucket_name)
            self._initialized = True
            print(f"[GCS] Inicializado. Bucket: {self.bucket_name}")
            return True
            
        except Exception as e:
            print(f"[GCS] ERROR de inicialización: {e}")
            return False
    
    def upload_file(
        self,
        file_path: str,
        destination_name: Optional[str] = None,
        content_type: Optional[str] = None
    ) -> GCSUploadResult:
        """
        Sube un archivo a GCS.
        
        Args:
            file_path: Ruta local del archivo
            destination_name: Nombre en GCS (opcional, usa el nombre del archivo)
            content_type: Tipo MIME (opcional, se detecta automáticamente)
        """
        if not self._initialized:
            if not self.initialize():
                return GCSUploadResult(
                    file_name=Path(file_path).name,
                    success=False,
                    error_message="No se pudo inicializar GCS"
                )
        
        file_path = Path(file_path)
        if not file_path.exists():
            return GCSUploadResult(
                file_name=file_path.name,
                success=False,
                error_message=f"Archivo no encontrado: {file_path}"
            )
        
        # Nombre destino con prefijo
        dest_name = destination_name or file_path.name
        blob_name = f"{self.prefix}{dest_name}" if self.prefix else dest_name
        
        # Detectar content type
        if content_type is None:
            if file_path.suffix == '.png':
                content_type = 'image/png'
            elif file_path.suffix == '.txt':
                content_type = 'text/plain'
            elif file_path.suffix == '.log':
                content_type = 'text/plain'
            elif file_path.suffix == '.json':
                content_type = 'application/json'
            else:
                content_type = 'application/octet-stream'
        
        try:
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(str(file_path), content_type=content_type)
            
            gcs_url = f"gs://{self.bucket_name}/{blob_name}"
            public_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
            
            print(f"[GCS] Archivo subido: {blob_name}")
            
            return GCSUploadResult(
                file_name=dest_name,
                success=True,
                gcs_url=gcs_url,
                public_url=public_url
            )
            
        except Exception as e:
            print(f"[GCS] ERROR subiendo {file_path.name}: {e}")
            return GCSUploadResult(
                file_name=file_path.name,
                success=False,
                error_message=str(e)
            )
    
    def upload_string(
        self,
        content: str,
        destination_name: str,
        content_type: str = "text/plain"
    ) -> GCSUploadResult:
        """
        Sube un string directamente a GCS (útil para logs).
        
        Args:
            content: Contenido a subir
            destination_name: Nombre del archivo en GCS
            content_type: Tipo MIME
        """
        if not self._initialized:
            if not self.initialize():
                return GCSUploadResult(
                    file_name=destination_name,
                    success=False,
                    error_message="No se pudo inicializar GCS"
                )
        
        blob_name = f"{self.prefix}{destination_name}" if self.prefix else destination_name
        
        try:
            blob = self.bucket.blob(blob_name)
            blob.upload_from_string(content, content_type=content_type)
            
            gcs_url = f"gs://{self.bucket_name}/{blob_name}"
            public_url = f"https://storage.googleapis.com/{self.bucket_name}/{blob_name}"
            
            print(f"[GCS] String subido: {blob_name}")
            
            return GCSUploadResult(
                file_name=destination_name,
                success=True,
                gcs_url=gcs_url,
                public_url=public_url
            )
            
        except Exception as e:
            print(f"[GCS] ERROR subiendo string: {e}")
            return GCSUploadResult(
                file_name=destination_name,
                success=False,
                error_message=str(e)
            )
    
    def list_files(self, prefix: Optional[str] = None) -> list:
        """Lista archivos en el bucket."""
        if not self._initialized:
            if not self.initialize():
                return []
        
        try:
            search_prefix = prefix or self.prefix
            blobs = self.bucket.list_blobs(prefix=search_prefix)
            
            files = []
            for blob in blobs:
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "url": f"https://storage.googleapis.com/{self.bucket_name}/{blob.name}"
                })
            
            return files
            
        except Exception as e:
            print(f"[GCS] ERROR listando archivos: {e}")
            return []


class ExecutionLogger:
    """
    Logger que guarda logs en memoria y los sube a GCS al finalizar.
    """
    
    def __init__(self, execution_id: Optional[str] = None, gcs_uploader: Optional[GCSUploader] = None):
        """
        Args:
            execution_id: ID único de la ejecución (genera uno si es None)
            gcs_uploader: Instancia de GCSUploader (crea uno si es None)
        """
        self.execution_id = execution_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.gcs_uploader = gcs_uploader or GCSUploader(prefix="logs/")
        self.logs = []
        self.start_time = datetime.now()
    
    def log(self, message: str, level: str = "INFO"):
        """Agrega un mensaje al log."""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] [{level}] {message}"
        self.logs.append(entry)
        print(entry)
    
    def info(self, message: str):
        self.log(message, "INFO")
    
    def error(self, message: str):
        self.log(message, "ERROR")
    
    def warning(self, message: str):
        self.log(message, "WARNING")
    
    def get_full_log(self) -> str:
        """Retorna todo el log como string."""
        header = f"=== Ejecución {self.execution_id} ===\n"
        header += f"Inicio: {self.start_time.isoformat()}\n"
        header += f"Fin: {datetime.now().isoformat()}\n"
        header += "=" * 40 + "\n\n"
        return header + "\n".join(self.logs)
    
    def save_to_gcs(self) -> GCSUploadResult:
        """Sube el log completo a GCS."""
        log_content = self.get_full_log()
        filename = f"execution_{self.execution_id}.log"
        return self.gcs_uploader.upload_string(log_content, filename)
    
    def save_locally(self, path: str = "./downloads") -> str:
        """Guarda el log localmente."""
        Path(path).mkdir(parents=True, exist_ok=True)
        filename = f"execution_{self.execution_id}.log"
        filepath = Path(path) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.get_full_log())
        
        return str(filepath)


def create_gcs_uploader(prefix: str = "") -> GCSUploader:
    """Factory function para crear un uploader de GCS."""
    return GCSUploader(prefix=prefix)


def create_screenshot_uploader() -> GCSUploader:
    """Crea un uploader específico para screenshots."""
    return GCSUploader(prefix="screenshots/")


def create_log_uploader() -> GCSUploader:
    """Crea un uploader específico para logs."""
    return GCSUploader(prefix="logs/")

