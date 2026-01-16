"""
Módulo para integración con Google Cloud Tasks.
Permite encolar tareas para procesamiento paralelo.
"""
import os
import json
from typing import List
from google.cloud import tasks_v2
from google.oauth2 import service_account


class TaskManager:
    """Gestor de tareas de Cloud Tasks."""
    
    def __init__(self):
        self.project_id = os.getenv("GCP_PROJECT_ID")
        self.location = os.getenv("QUEUE_LOCATION", "us-central1")
        self.queue_name = os.getenv("QUEUE_NAME")
        self.worker_url = os.getenv("WORKER_URL")
        self.service_account_email = os.getenv("SERVICE_ACCOUNT_EMAIL")
        
        print(f"[Tasks] Config: PROJECT={self.project_id}, LOCATION={self.location}, QUEUE={self.queue_name}, WORKER={self.worker_url}")
        
        self.client = None
        self.parent = None
        
        # Validar configuración mínima
        if not self.project_id or not self.queue_name:
            missing = []
            if not self.project_id:
                missing.append("GCP_PROJECT_ID")
            if not self.queue_name:
                missing.append("QUEUE_NAME")
            print(f"[Tasks] ADVERTENCIA: Variables faltantes: {', '.join(missing)}")
            print("[Tasks] Cloud Tasks NO está habilitado.")
            return
        
        # Intentar inicializar cliente
        self._init_client()
    
    def _init_client(self):
        """Inicializa el cliente de Cloud Tasks con ADC o archivo de credenciales."""
        
        # Intento 1: Application Default Credentials (ADC)
        try:
            self.client = tasks_v2.CloudTasksClient()
            self.parent = self.client.queue_path(self.project_id, self.location, self.queue_name)
            print(f"[Tasks] ✓ Cliente inicializado con ADC. Queue: {self.parent}")
            return
        except Exception as e:
            print(f"[Tasks] ADC no disponible: {e}")
        
        # Intento 2: Archivo de credenciales explícito
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/credentials/google_service_account.json")
        
        if os.path.exists(credentials_path):
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                self.client = tasks_v2.CloudTasksClient(credentials=credentials)
                self.parent = self.client.queue_path(self.project_id, self.location, self.queue_name)
                print(f"[Tasks] ✓ Cliente inicializado con archivo: {credentials_path}")
                print(f"[Tasks] Queue path: {self.parent}")
                return
            except Exception as e:
                print(f"[Tasks] ERROR con archivo de credenciales: {e}")
        else:
            print(f"[Tasks] Archivo de credenciales no encontrado: {credentials_path}")
        
        print("[Tasks] ERROR: No se pudo inicializar el cliente de Cloud Tasks")

    def is_enabled(self) -> bool:
        """Verifica si Cloud Tasks está configurado y listo."""
        return self.client is not None and self.worker_url is not None

    def create_invoice_batch_task(self, invoice_numbers: List[str], batch_id: int, total_batches: int, provider: str, execution_id: str) -> bool:
        """Crea una tarea para procesar un lote de facturas."""
        if not self.client:
            print("[Tasks] ERROR: Cliente no inicializado")
            return False
        if not self.worker_url:
            print("[Tasks] ERROR: Falta WORKER_URL")
            return False
            
        payload = {
            "invoice_numbers": invoice_numbers,
            "batch_id": batch_id,
            "total_batches": total_batches,
            "provider": provider,
            "execution_id": execution_id
        }
        
        try:
            task = {
                "http_request": {
                    "http_method": tasks_v2.HttpMethod.POST,
                    "url": f"{self.worker_url}/api/worker",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(payload).encode(),
                }
            }
            
            # Agregar OIDC token si hay service account
            if self.service_account_email:
                task["http_request"]["oidc_token"] = {
                    "service_account_email": self.service_account_email
                }
                
            self.client.create_task(request={"parent": self.parent, "task": task})
            print(f"[Tasks] ✓ Tarea encolada: Lote {batch_id+1}/{total_batches} ({len(invoice_numbers)} facturas)")
            return True
            
        except Exception as e:
            print(f"[Tasks] ERROR encolando tarea: {e}")
            return False


def create_task_manager() -> TaskManager:
    return TaskManager()
