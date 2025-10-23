# ============================================================
# app/schemas/pagos_listar.py
# ============================================================
"""
Schemas para el listado y detalle de pagos.
Incluye resúmenes embebidos de cliente, préstamo y comprobantes.
"""
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================
# Objetos embebidos (resúmenes)
# ============================================================
class EstadoResumen(BaseModel):
    """Resumen de estado (genérico)"""
    id: int
    nombre: str


class ClienteResumen(BaseModel):
    """Resumen del cliente (dueño del préstamo)"""
    id: int
    nombre: str
    correo: str


class PrestamoResumen(BaseModel):
    """Resumen del préstamo asociado al pago"""
    id: int
    estado: str
    monto_prestamo: float
    deuda_actual: float
    mora_acumulada: float
    interes_acumulada: float


class ComprobanteItem(BaseModel):
    """Item de comprobante asociado a un pago"""
    id_comprobante: int
    url: str


# ============================================================
# Item de listado (usado en GET /pagos)
# ============================================================
class PagoListItemOut(BaseModel):
    """
    Item de pago en el listado.
    Incluye comprobantes, resumen del préstamo y cliente.
    """
    id_pago: int
    id_prestamo: int
    id_estado: int
    estado: str = Field(description="Nombre del estado (ej: pendiente, validado)")
    fecha_pago: Optional[str] = Field(None, description="Fecha del pago (ISO)")
    monto: float
    tipo_pago: Optional[str] = None
    medio_pago: Optional[str] = None
    ref_bancaria: Optional[str] = None
    comprobantes: List[ComprobanteItem] = Field(default_factory=list)
    prestamo: Optional[PrestamoResumen] = None
    cliente: Optional[ClienteResumen] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_pago": 8010,
                "id_prestamo": 5001,
                "id_estado": 1,
                "estado": "pendiente",
                "fecha_pago": "2025-10-23",
                "monto": 300.5,
                "tipo_pago": "abono",
                "medio_pago": "transferencia",
                "ref_bancaria": "BANK-123-XYZ",
                "comprobantes": [
                    {"id_comprobante": 17, "url": "https://cloudinary.com/..."}
                ],
                "prestamo": {
                    "id": 5001,
                    "estado": "activo",
                    "monto_prestamo": 1200.0,
                    "deuda_actual": 1050.0,
                    "mora_acumulada": 25.0,
                    "interes_acumulada": 87.5,
                },
                "cliente": {
                    "id": 42,
                    "nombre": "Juan Pérez",
                    "correo": "juan@example.com"
                }
            }
        }
    }


# ============================================================
# Respuesta del listado (GET /pagos)
# ============================================================
class PagoListResponse(BaseModel):
    """
    Respuesta paginada del listado de pagos.
    """
    items: List[PagoListItemOut]
    total: int = Field(description="Total de pagos que cumplen los filtros")
    limit: int
    offset: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id_pago": 8010,
                        "id_prestamo": 5001,
                        "id_estado": 1,
                        "estado": "pendiente",
                        "fecha_pago": "2025-10-23",
                        "monto": 300.5,
                        "tipo_pago": "abono",
                        "medio_pago": "transferencia",
                        "ref_bancaria": "BANK-123",
                        "comprobantes": [
                            {"id_comprobante": 17, "url": "https://..."}
                        ],
                        "prestamo": {
                            "id": 5001,
                            "estado": "activo",
                            "monto_prestamo": 1200.0,
                            "deuda_actual": 1050.0,
                            "mora_acumulada": 25.0,
                            "interes_acumulada": 87.5,
                        },
                        "cliente": {
                            "id": 42,
                            "nombre": "Juan Pérez",
                            "correo": "juan@example.com"
                        }
                    }
                ],
                "total": 127,
                "limit": 50,
                "offset": 0
            }
        }
    }


# ============================================================
# Detalle de pago (GET /pagos/{id_pago})
# ============================================================
class PagoDetalleOut(PagoListItemOut):
    """
    Detalle completo de un pago.
    Mismo shape que PagoListItemOut pero como objeto único.
    Se puede extender con campos adicionales si es necesario.
    """
    pass