# ============================================================
# app/schemas/articulos_publicos.py
# ============================================================
"""
Schemas para la API pública de artículos.
"""
from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field, HttpUrl


# ============================================================
# LISTAR ARTÍCULOS
# ============================================================
class ArticuloPublicoListItem(BaseModel):
    """Item de artículo en el listado público"""
    id_articulo: int
    id_tipo: Optional[int] = Field(default=None)
    tipo_nombre: str = Field(default="N/A")
    descripcion: str
    valor_estimado: float
    valor_aprobado: Optional[float] = None
    condicion: Optional[str] = None
    estado: str
    fotos: List[str] = Field(default_factory=list, description="URLs de fotos del artículo")
    precio_venta: Optional[float] = Field(None, description="Precio actual de venta si está en inventario")
    disponible_compra: bool = Field(False, description="Si el artículo está disponible para compra")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id_articulo": 101,
                "id_tipo": 2,
                "tipo_nombre": "Joyería",
                "descripcion": "Anillo de oro 14k con piedra verde",
                "valor_estimado": 3200.0,
                "valor_aprobado": 1500.0,
                "condicion": "Usado, buen estado",
                "estado": "en_venta",
                "fotos": [
                    "https://cdn.example.com/foto1.jpg",
                    "https://cdn.example.com/foto2.jpg"
                ],
                "precio_venta": 1400.0,
                "disponible_compra": True
            }
        }
    }


class ArticuloPublicoListResponse(BaseModel):
    """Respuesta del listado de artículos"""
    items: List[ArticuloPublicoListItem]
    total: int
    limit: int
    offset: int

    model_config = {
        "from_attributes": True
    }


# ============================================================
# DETALLE DE ARTÍCULO
# ============================================================
class ArticuloPublicoDetalle(BaseModel):
    """Detalle completo de un artículo"""
    id_articulo: int
    id_solicitud: Optional[int] = None
    id_tipo: Optional[int] = None
    tipo_nombre: str = Field(default="N/A")
    descripcion: str
    valor_estimado: float
    valor_aprobado: Optional[float] = None
    condicion: Optional[str] = None
    estado: str
    fotos: List[str] = Field(default_factory=list, description="URLs de todas las fotos")
    precio_venta: Optional[float] = Field(None, description="Precio de venta si está en inventario")
    disponible_compra: bool = Field(False, description="Si está disponible para compra")
    fecha_ingreso_inventario: Optional[date] = Field(None, description="Fecha de ingreso al inventario")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id_articulo": 101,
                "id_solicitud": 15,
                "id_tipo": 2,
                "tipo_nombre": "Joyería",
                "descripcion": "Anillo de oro 14k con piedra verde",
                "valor_estimado": 3200.0,
                "valor_aprobado": 1500.0,
                "condicion": "Usado, buen estado",
                "estado": "en_venta",
                "fotos": [
                    "https://cdn.example.com/foto1.jpg",
                    "https://cdn.example.com/foto2.jpg",
                    "https://cdn.example.com/foto3.jpg"
                ],
                "precio_venta": 1400.0,
                "disponible_compra": True,
                "fecha_ingreso_inventario": "2025-10-15"
            }
        }
    }


# ============================================================
# COMPRAR ARTÍCULO
# ============================================================
class ComprarArticuloIn(BaseModel):
    """Datos para comprar un artículo"""
    precio_venta: Optional[float] = Field(None, ge=0, description="Precio acordado (si difiere del actual)")
    fecha_venta: Optional[date] = Field(None, description="Fecha de la venta (default: hoy)")
    medio_pago: str = Field(default="efectivo", description="efectivo | transferencia | tarjeta")
    ref_bancaria: Optional[str] = Field(None, max_length=100, description="Referencia bancaria si aplica")
    comprador_nombre: Optional[str] = Field(None, max_length=200, description="Nombre del comprador")
    comprador_nit: Optional[str] = Field(None, max_length=50, description="NIT/DPI del comprador")
    comprobante_url: Optional[HttpUrl] = Field(None, description="URL del comprobante de pago")
    nota: Optional[str] = Field(None, max_length=500, description="Observaciones adicionales")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "precio_venta": 1400.0,
                "medio_pago": "transferencia",
                "ref_bancaria": "BANK-123456",
                "comprador_nombre": "Juan Pérez",
                "comprador_nit": "12345678-9",
                "nota": "Compra desde app web"
            }
        }
    }


class ComprarArticuloOut(BaseModel):
    """Respuesta tras comprar un artículo"""
    id_articulo: int
    id_inventario: int
    estado: str = Field(description="Estado del artículo tras la compra (vendido)")
    precio_venta: float
    fecha_venta: Optional[date] = None
    mensaje: str

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id_articulo": 101,
                "id_inventario": 42,
                "estado": "vendido",
                "precio_venta": 1400.0,
                "fecha_venta": "2025-10-24",
                "mensaje": "Compra registrada exitosamente"
            }
        }
    }
