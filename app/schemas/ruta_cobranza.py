# app/schemas/ruta_cobranza.py
from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional

from .visita_cobranza import VisitaDetalle

# --- Schemas para POST /rutas-cobranza ---

class RutaCobranzaCreate(BaseModel):
    id_usuario_cobrador: int
    fecha_asignacion: date
    prestamos: List[int] = Field(..., min_items=1)

class CobradorInfo(BaseModel):
    nombre: str
    telefono: Optional[str] = None

    class Config:
        orm_mode = True

class RutaCobranzaCreada(BaseModel):
    id_ruta: int
    id_usuario_cobrador: int
    cobrador: CobradorInfo
    fecha_asignacion: date
    total_prestamos: int
    monto_total_a_cobrar: float


# --- Schemas para GET /rutas-cobranza ---

class CobradorResumen(BaseModel):
    id_usuario: int
    nombre: str

    class Config:
        orm_mode = True

class RutaCobranzaListado(BaseModel):
    id_ruta: int
    cobrador: CobradorResumen
    fecha_asignacion: date
    total_visitas: int
    visitas_completadas: int
    monto_cobrado: float
    monto_pendiente: float

    class Config:
        orm_mode = True

class PaginatedRutasCobranza(BaseModel):
    items: List[RutaCobranzaListado]
    total: int
    limit: int
    offset: int


# --- Schemas para GET /rutas-cobranza/{id_ruta}/visitas ---

class RutaConVisitas(BaseModel):
    id_ruta: int
    visitas: List[VisitaDetalle]

    class Config:
        orm_mode = True