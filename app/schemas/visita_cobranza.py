from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, Literal

# --- Schemas para GET /rutas-cobranza/{id_ruta}/visitas ---

class ClienteInfo(BaseModel):
    nombre: str
    apellido: Optional[str] = None

    class Config:
        orm_mode = True

class PrestamoInfoVisita(BaseModel):
    id_prestamo: int
    cliente: ClienteInfo
    deuda_actual: float
    direccion_cobro: Optional[str] = None

    class Config:
        orm_mode = True

class VisitaDetalle(BaseModel):
    id_visita: int
    prestamo: PrestamoInfoVisita
    resultado: Optional[str] = None
    comentario: Optional[str] = None
    monto_pagado: Optional[float] = None
    gps: Optional[str] = None
    fecha_visita: Optional[datetime] = None
    id_pago: Optional[int] = None

    class Config:
        orm_mode = True

# --- Schemas para POST /visitas-cobranza ---

ResultadoVisita = Literal[
    "cobro_exitoso", "cliente_ausente", "promesa_pago", "sin_fondos", "rechazado"
]

class VisitaCobranzaCreate(BaseModel):
    id_ruta_cobranza: int
    id_prestamo: int
    resultado: ResultadoVisita
    comentario: Optional[str] = None
    monto_pagado: Optional[float] = Field(None, gt=0)
    gps: Optional[str] = None
    medio_pago: Optional[str] = None
    ref_bancaria: Optional[str] = None

class VisitaCobranzaCreada(BaseModel):
    id_visita: int
    id_pago: Optional[int] = None
    mensaje: str