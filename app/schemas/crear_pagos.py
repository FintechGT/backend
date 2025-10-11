# app/schemas/crear_pagos.py
from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from typing import Literal

MedioPago = Literal["tarjeta", "efectivo", "transferencia", "otros"]

class CrearPagoIn(BaseModel):
    id_prestamo: int
    monto: float = Field(gt=0, description="Monto del pago, debe ser > 0")
    medio_pago: MedioPago
    ref_bancaria: str | None = None
    comprobante_url: HttpUrl | None = None

class CrearPagoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_pago: int
    id_prestamo: int
    estado: str  # "pendiente"
    monto: float
    medio_pago: MedioPago
    ref_bancaria: str | None = None
    comprobante_url: HttpUrl | None = None
