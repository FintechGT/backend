from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field

class EstadoMiniOut(BaseModel):
    id: Optional[int] = Field(None, description="Id_Estado_Prestamo")
    nombre: str

class PrestamoItemOut(BaseModel):
    id_prestamo: int
    id_articulo: int
    id_usuario_evaluador: int
    estado: EstadoMiniOut
    fecha_inicio: date
    fecha_vencimiento: date
    monto_prestamo: Decimal
    deuda_actual: Decimal
    mora_acumulada: Decimal
    interes_acumulada: Decimal
    ultimo_calculo_en: Optional[date] = None
    created_at: datetime
    updated_at: datetime

class PrestamoListOut(BaseModel):
    items: List[PrestamoItemOut]
    total: int
    limit: int
    offset: int

class PrestamoCreateIn(BaseModel):
    id_articulo: int
    fecha_inicio: date
    fecha_vencimiento: date
    monto_prestamo: Decimal
    plazo_dias: Optional[int] = Field(None, ge=1)

class PrestamoCreateOut(BaseModel):
    id_prestamo: int
    id_articulo: int
    estado: str
    mensaje: str
