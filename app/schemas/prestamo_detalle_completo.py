# ============================================================
# app/schemas/prestamo_detalle_completo.py
# ============================================================
"""
Schema unificado para el detalle completo de un préstamo.
Incluye artículo, cliente, pagos, contrato, estados, etc.
El contenido varía según el rol del usuario.
"""
from __future__ import annotations
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field


# ============================================================
# Objetos embebidos (resúmenes)
# ============================================================
class EstadoMini(BaseModel):
    """Resumen de estado (genérico)"""
    id: int
    nombre: str


class ClienteMini(BaseModel):
    """Resumen del cliente (dueño del préstamo)"""
    id: int
    nombre: str
    correo: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None


class ArticuloMini(BaseModel):
    """Resumen del artículo asociado al préstamo"""
    id_articulo: int
    id_solicitud: int
    id_tipo: int
    tipo_nombre: Optional[str] = None
    descripcion: str
    valor_estimado: float
    valor_aprobado: Optional[float] = None
    condicion: Optional[str] = None
    estado: str
    fotos: List[str] = Field(default_factory=list, description="URLs de fotos")


class PagoItem(BaseModel):
    """Item de pago asociado al préstamo"""
    id_pago: int
    fecha_pago: Optional[str] = None
    monto: float
    estado: str
    tipo_pago: Optional[str] = None
    medio_pago: Optional[str] = None
    ref_bancaria: Optional[str] = None
    validador_id: Optional[int] = None
    validador_nombre: Optional[str] = None
    comprobantes: List[str] = Field(default_factory=list, description="URLs de comprobantes")


class ContratoMini(BaseModel):
    """Resumen del contrato asociado al préstamo"""
    id_contrato: int
    url_pdf: str
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    estado: str  # pendiente_firma | firmado_parcial | firmado_completo


class MovimientoItem(BaseModel):
    """Item de movimiento del préstamo (interés, mora, pago aplicado)"""
    id_mov: int
    tipo: str  # interes | mora | pago | ajuste
    monto: float
    nota: Optional[str] = None
    fecha: datetime


# ============================================================
# Respuesta principal
# ============================================================
class PrestamoDetalleCompletoOut(BaseModel):
    """
    Detalle completo de un préstamo.
    El contenido varía según el rol del usuario:
    - INVITADO: Solo sus propios préstamos
    - ADMIN/CAJERO/VALUADOR/SUPERVISOR: Todos los préstamos con info completa
    """
    # === PRÉSTAMO ===
    id_prestamo: int
    estado: EstadoMini
    fecha_inicio: date
    fecha_vencimiento: date
    monto_prestamo: float
    deuda_actual: float
    mora_acumulada: float
    interes_acumulada: float
    ultimo_calculo_en: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    # === ARTÍCULO ===
    articulo: ArticuloMini

    # === CLIENTE (solo visible para roles con permisos) ===
    cliente: Optional[ClienteMini] = Field(
        None,
        description="Visible para ADMIN/CAJERO/VALUADOR/SUPERVISOR"
    )

    # === EVALUADOR (solo visible para roles con permisos) ===
    evaluador_id: Optional[int] = None
    evaluador_nombre: Optional[str] = None

    # === PAGOS ===
    pagos: List[PagoItem] = Field(
        default_factory=list,
        description="Historial de pagos del préstamo"
    )
    total_pagado: float = Field(
        description="Suma de todos los pagos validados"
    )

    # === CONTRATO (si existe) ===
    contrato: Optional[ContratoMini] = None

    # === MOVIMIENTOS (solo para roles con permisos) ===
    movimientos: Optional[List[MovimientoItem]] = Field(
        None,
        description="Historial de interés/mora (solo ADMIN/SUPERVISOR/VALUADOR)"
    )

    # === METADATA ===
    puede_pagar: bool = Field(
        description="Si el préstamo acepta pagos actualmente"
    )
    puede_liquidar: bool = Field(
        description="Si el préstamo puede ser liquidado"
    )
    dias_mora: int = Field(
        description="Días de mora desde fecha_vencimiento"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_prestamo": 5001,
                "estado": {"id": 2, "nombre": "activo"},
                "fecha_inicio": "2025-10-01",
                "fecha_vencimiento": "2025-12-01",
                "monto_prestamo": 1200.0,
                "deuda_actual": 1050.0,
                "mora_acumulada": 25.0,
                "interes_acumulada": 87.5,
                "ultimo_calculo_en": "2025-10-23",
                "created_at": "2025-10-01T10:00:00",
                "updated_at": "2025-10-23T08:30:00",
                "articulo": {
                    "id_articulo": 201,
                    "id_solicitud": 15,
                    "id_tipo": 2,
                    "tipo_nombre": "Joyería",
                    "descripcion": "Anillo de oro 14k",
                    "valor_estimado": 3200.0,
                    "valor_aprobado": 1500.0,
                    "condicion": "Usado, buen estado",
                    "estado": "aprobado",
                    "fotos": ["https://cloudinary.com/foto1.jpg"]
                },
                "cliente": {
                    "id": 42,
                    "nombre": "Juan Pérez",
                    "correo": "juan@example.com",
                    "telefono": "+502 5555-1234",
                    "direccion": "6a avenida 10-22, Zona 1"
                },
                "evaluador_id": 10,
                "evaluador_nombre": "María López",
                "pagos": [
                    {
                        "id_pago": 8010,
                        "fecha_pago": "2025-10-15",
                        "monto": 300.0,
                        "estado": "validado",
                        "tipo_pago": "abono",
                        "medio_pago": "transferencia",
                        "ref_bancaria": "BANK-123",
                        "validador_id": 5,
                        "validador_nombre": "Pedro Ruiz",
                        "comprobantes": ["https://cloudinary.com/comp1.jpg"]
                    }
                ],
                "total_pagado": 300.0,
                "contrato": {
                    "id_contrato": 101,
                    "url_pdf": "https://cloudinary.com/contrato.pdf",
                    "hash_doc": "sha256:abc123...",
                    "firma_cliente_en": "2025-10-02T14:30:00",
                    "firma_empresa_en": "2025-10-02T15:00:00",
                    "estado": "firmado_completo"
                },
                "movimientos": [
                    {
                        "id_mov": 5010,
                        "tipo": "interes",
                        "monto": 2.5,
                        "nota": "Interés diario del 2025-10-23",
                        "fecha": "2025-10-23T00:00:00"
                    }
                ],
                "puede_pagar": True,
                "puede_liquidar": True,
                "dias_mora": 0
            }
        }
    }