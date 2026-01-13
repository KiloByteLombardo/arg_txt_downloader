"""
Módulo para leer y procesar el archivo Excel "Analisis REIM".
Extrae los números de factura filtrados por observación.
"""
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import pandas as pd


@dataclass
class InvoiceRecord:
    """Representa un registro de factura extraído del Excel."""
    provider: str
    full_document: str
    invoice_number: str
    observation: str
    row_index: int


class ExcelReader:
    """Lee y procesa archivos Excel de Analisis REIM."""
    
    # Configuración del Excel
    REQUIRED_COLUMNS = ["Proveedor", "Documento Asociado", "Observación"]
    FILTER_COLUMN = "Observación"
    FILTER_VALUE = "Cargar txt"
    DOCUMENT_COLUMN = "Documento Asociado"
    PROVIDER_COLUMN = "Proveedor"
    
    def _find_header_row(self, df: pd.DataFrame) -> Optional[int]:
        """
        Busca automáticamente la fila que contiene los cabezales.
        
        Args:
            df: DataFrame sin procesar
            
        Returns:
            Índice de la fila con cabezales o None si no se encuentra
        """
        # Buscar en las primeras 20 filas
        for idx in range(min(20, len(df))):
            row_values = df.iloc[idx].astype(str).str.strip().tolist()
            # Verificar si esta fila contiene todas las columnas requeridas
            matches = sum(1 for col in self.REQUIRED_COLUMNS if col in row_values)
            if matches == len(self.REQUIRED_COLUMNS):
                print(f"[Excel] Cabezales encontrados en fila {idx}")
                return idx
        return None
    
    def _extract_invoice_number(self, document: str) -> Optional[str]:
        """
        Extrae el número de factura del documento.
        Formato esperado: A-XXXX-YYYYYYYY
        Retorna: YYYYYYYY
        
        Args:
            document: String del documento completo
            
        Returns:
            Número de factura extraído o None
        """
        if pd.isna(document) or not document:
            return None
            
        document = str(document).strip()
        
        # Patrón: letra-4digitos-número
        pattern = r"^[A-Z]-\d{4}-(\d+)$"
        match = re.match(pattern, document)
        if match:
            return match.group(1)
        
        # Intento alternativo: dividir por guiones y tomar el último
        parts = document.split('-')
        if len(parts) >= 3:
            return parts[-1]
            
        print(f"[Excel] Formato de documento inválido: {document}")
        return None
    
    def read_excel(self, file_path: str) -> Tuple[List[InvoiceRecord], Dict[str, List[InvoiceRecord]]]:
        """
        Lee el archivo Excel y extrae los registros de facturas.
        
        Args:
            file_path: Ruta al archivo Excel
            
        Returns:
            Tupla con:
            - Lista de todos los registros filtrados
            - Diccionario agrupado por proveedor
        """
        print(f"[Excel] Leyendo archivo: {file_path}")
        
        # Leer Excel sin cabezales para buscarlos automáticamente
        df_raw = pd.read_excel(file_path, header=None)
        
        header_row = self._find_header_row(df_raw)
        
        if header_row is None:
            raise ValueError(
                f"No se encontraron los cabezales requeridos: {self.REQUIRED_COLUMNS}. "
                "Verifica que el archivo tenga las columnas correctas."
            )
        
        # Re-leer con el cabezal correcto
        df = pd.read_excel(file_path, header=header_row)
        df.columns = df.columns.str.strip()
        
        print(f"[Excel] Archivo cargado: {len(df)} filas, columnas: {list(df.columns)}")
        
        # Filtrar por observación
        mask = df[self.FILTER_COLUMN].astype(str).str.strip().str.lower() == self.FILTER_VALUE.lower()
        df_filtered = df[mask].copy()
        
        print(f"[Excel] Registros filtrados: {len(df_filtered)} de {len(df)} (filtro: {self.FILTER_VALUE})")
        
        # Extraer registros
        records = []
        
        for idx, row in df_filtered.iterrows():
            provider = str(row[self.PROVIDER_COLUMN]).strip() if pd.notna(row[self.PROVIDER_COLUMN]) else ""
            full_document = str(row[self.DOCUMENT_COLUMN]).strip() if pd.notna(row[self.DOCUMENT_COLUMN]) else ""
            observation = str(row[self.FILTER_COLUMN]).strip() if pd.notna(row[self.FILTER_COLUMN]) else ""
            
            invoice_number = self._extract_invoice_number(full_document)
            
            if invoice_number:
                record = InvoiceRecord(
                    provider=provider,
                    full_document=full_document,
                    invoice_number=invoice_number,
                    observation=observation,
                    row_index=idx
                )
                records.append(record)
            else:
                print(f"[Excel] Saltando fila {idx}: documento inválido '{full_document}'")
        
        # Agrupar por proveedor
        by_provider: Dict[str, List[InvoiceRecord]] = {}
        for record in records:
            provider_key = self._normalize_provider_name(record.provider)
            if provider_key not in by_provider:
                by_provider[provider_key] = []
            by_provider[provider_key].append(record)
        
        print(f"[Excel] Extracción completa: {len(records)} registros")
        for prov, recs in by_provider.items():
            print(f"  - {prov}: {len(recs)} facturas")
        
        return records, by_provider
    
    def _normalize_provider_name(self, provider: str) -> str:
        """
        Normaliza el nombre del proveedor para matching.
        
        Args:
            provider: Nombre del proveedor del Excel
            
        Returns:
            Clave normalizada del proveedor
        """
        provider_lower = provider.lower().strip()
        
        # Mapeo de nombres comunes a claves
        mappings = {
            "suizo": "suizo",
            "suizo argentina": "suizo",
            "del sud": "del_sud",
            "delsud": "del_sud",
            "monroe": "monroe",
        }
        
        for key, value in mappings.items():
            if key in provider_lower:
                return value
        
        # Si no hay match, retornar el nombre limpio
        return provider_lower.replace(" ", "_")


def read_invoices_from_excel(file_path: str) -> Tuple[List[InvoiceRecord], Dict[str, List[InvoiceRecord]]]:
    """
    Función de conveniencia para leer facturas de un Excel.
    
    Args:
        file_path: Ruta al archivo Excel
        
    Returns:
        Tupla con lista de registros y diccionario por proveedor
    """
    reader = ExcelReader()
    return reader.read_excel(file_path)
