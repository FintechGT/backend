# app/schemas/pagos.py
from pydantic import BaseModel
from typing import List, Optional

class PagoComprobanteOut(BaseModel):
    id_comprobante: int
    url: str                       # mapea a Comprobante.imagen
    descripcion: Optional[str] = None  # no existe en tu modelo, lo dejamos por compatibilidad (siempre null)

class PagoListItemOut(BaseModel):
    id_pago: int
    id_prestamo: int
    id_estado: int                 # FK a Estado_Pago
    id_validador: int
    fecha_pago: Optional[str] = None
    monto: float
    tipo_pago: Optional[str] = None
    medio_pago: Optional[str] = None
    ref_bancaria: Optional[str] = None
    # Compatibilidad con el contrato previo (si no los manejas aún, retornan 0):
    aplicacion: dict = {"mora": 0.0, "interes": 0.0, "capital": 0.0}
    comprobantes: List[PagoComprobanteOut] = []

class PagoListResponse(BaseModel):
    items: List[PagoListItemOut]
    total: int
