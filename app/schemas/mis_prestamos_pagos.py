# ============================================================
# app/schemas/mis_prestamos_pagos.py
# ============================================================
from pydantic import BaseModel
from typing import List, Optional
from datetime import date


# ============================================================
# Préstamos del usuario
# ============================================================
class EstadoMiniOut(BaseModel):
    """Resumen de estado de préstamo"""
    id: Optional[int] = None
    nombre: str


class MiPrestamoItemOut(BaseModel):
    """Item de préstamo del usuario actual"""
    id_prestamo: int
    id_articulo: int
    estado: EstadoMiniOut
    fecha_inicio: date
    fecha_vencimiento: date
    monto_prestamo: float
    deuda_actual: float
    mora_acumulada: float
    interes_acumulada: float
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MisPrestamosListOut(BaseModel):
    """Respuesta de listado de mis préstamos"""
    items: List[MiPrestamoItemOut]
    total: int
    limit: int
    offset: int


# ============================================================
# Pagos del usuario
# ============================================================
class PagoComprobanteOut(BaseModel):
    """Comprobante adjunto a un pago"""
    id_comprobante: int
    url: str
    descripcion: Optional[str] = None


class MiPagoItemOut(BaseModel):
    """Item de pago de préstamos del usuario actual"""
    id_pago: int
    id_prestamo: int
    estado: str
    fecha_pago: Optional[str] = None
    monto: float
    tipo_pago: Optional[str] = None
    medio_pago: Optional[str] = None
    ref_bancaria: Optional[str] = None
    comprobantes: List[PagoComprobanteOut] = []


class MisPagosListOut(BaseModel):
    """Respuesta de listado de mis pagos"""
    items: List[MiPagoItemOut]
    total: int
    limit: int
    offset: int