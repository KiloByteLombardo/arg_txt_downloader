"""
Modelos de datos para respuestas de la API.
Diseñados para ser fácilmente consumidos por un frontend.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class InvoiceResult:
    """Resultado del procesamiento de una factura individual."""
    invoice_number: str
    success: bool
    file_path: Optional[str] = None
    drive_link: Optional[str] = None
    error_message: Optional[str] = None
    error_screenshot_url: Optional[str] = None
    retries: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionSummary:
    """Resumen completo de una ejecución para el frontend."""
    execution_id: str
    status: str  # "completed", "partial", "failed"
    provider: str
    started_at: str
    finished_at: str = ""
    
    # Contadores
    total_invoices: int = 0
    successful: int = 0
    failed: int = 0
    
    # Resultados detallados
    results: List[InvoiceResult] = field(default_factory=list)
    
    # Links a recursos en GCS
    log_url: Optional[str] = None
    screenshots: List[Dict[str, str]] = field(default_factory=list)  # [{name, url}]
    
    # Errores generales
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para JSON response."""
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "provider": self.provider,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {
                "total": self.total_invoices,
                "successful": self.successful,
                "failed": self.failed,
                "success_rate": f"{(self.successful/self.total_invoices*100):.1f}%" if self.total_invoices > 0 else "0%"
            },
            "results": [r.to_dict() for r in self.results],
            "logs": {
                "execution_log_url": self.log_url,
                "screenshots": self.screenshots
            },
            "errors": self.errors
        }


@dataclass 
class ProcessingRequest:
    """Request para procesar facturas."""
    provider: str
    invoice_numbers: List[str]
    upload_to_gcs: bool = True
    upload_to_drive: bool = True
    dry_run: bool = False


def create_execution_summary(
    provider: str,
    execution_id: Optional[str] = None
) -> ExecutionSummary:
    """Crea un nuevo resumen de ejecución."""
    return ExecutionSummary(
        execution_id=execution_id or datetime.now().strftime("%Y%m%d_%H%M%S"),
        status="running",
        provider=provider,
        started_at=datetime.now().isoformat()
    )

