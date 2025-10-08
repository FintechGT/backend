from pydantic import BaseModel, Field
from typing import Optional

class RecepcionCreate(BaseModel):
    id_articulo: int = Field(..., gt=0, description="ID del artículo a recepcionar")
    metodo_entrega: str = Field(..., description="domicilio | oficina")
    gps: Optional[str] = Field(None, max_length=60, description="Coordenadas GPS")
    estado_verificacion: str = Field(..., description="recogido_ok | rechazado_domicilio | aprobado")

class ArticuloResumen(BaseModel):
    id: int
    estado: str

class PrestamoResumen(BaseModel):
    id: int
    estado: str
    deuda_actual: float  # Se serializa como float para el front

class MovimientoResumen(BaseModel):
    tipo: str
    monto: float  # Se serializa como float para el front

class RecepcionOut(BaseModel):
    id_recepcion: int
    fase: str
    articulo: ArticuloResumen
    prestamo: Optional[PrestamoResumen] = None
    movimiento: Optional[MovimientoResumen] = None

    class Config:
        from_attributes = True
