from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class MovimientoResponse(BaseModel):
    id_mov: int
    tipo: str
    monto: float
    nota: Optional[str] = None
    fecha: datetime

class ResumenMovimientos(BaseModel):
    total_intereses: float
    total_mora: float
    total_abonos: float
    saldo_actual: float

class KardexPrestamoResponse(BaseModel):
    id_prestamo: int
    movimientos: List[MovimientoResponse]
    total: int
    resumen: ResumenMovimientos

    class Config:
        from_attributes = True