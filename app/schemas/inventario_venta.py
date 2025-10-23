# app/schemas/inventario_venta.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import date
from decimal import Decimal


# ============================================================
# CREAR INVENTARIO (ingreso inicial)
# ============================================================
class InventarioCrearIn(BaseModel):
    """Datos para ingresar un artículo al inventario"""
    id_articulo: int = Field(..., ge=1, description="ID del artículo a ingresar")
    precio_base: Decimal = Field(..., ge=0, description="Precio base/referencia")
    precio_actual: Optional[Decimal] = Field(None, ge=0, description="Precio actual (si no se envía, usa precio_base)")
    nota_ingreso: Optional[str] = Field(None, max_length=500, description="Observaciones del ingreso")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_articulo": 5001,
                "precio_base": 1200.0,
                "precio_actual": 1200.0,
                "nota_ingreso": "Laptop Dell en buen estado"
            }
        }
    }


class InventarioCrearOut(BaseModel):
    """Respuesta tras crear un registro de inventario"""
    id_inventario: int
    id_articulo: int
    estado: str
    precio_base: float
    precio_actual: float
    dias_en_bodega: int
    fecha_ingreso: date


# ============================================================
# ACTUALIZAR INVENTARIO (cambio de precio/estado)
# ============================================================
class InventarioActualizarIn(BaseModel):
    """Datos para actualizar un registro de inventario"""
    precio_actual: Optional[Decimal] = Field(None, ge=0, description="Nuevo precio de venta")
    estado: Optional[str] = Field(None, description="disponible | en_venta | reservado | vendido")
    nota: Optional[str] = Field(None, max_length=500, description="Observaciones del cambio")

    model_config = {
        "json_schema_extra": {
            "example": {
                "precio_actual": 1100.0,
                "estado": "en_venta",
                "nota": "Precio rebajado por promoción"
            }
        }
    }


class InventarioActualizarOut(BaseModel):
    """Respuesta tras actualizar inventario"""
    id_inventario: int
    estado: str
    precio_actual: float
    dias_en_bodega: int


# ============================================================
# REGISTRAR VENTA
# ============================================================
class InventarioVentaIn(BaseModel):
    """Datos para registrar una venta de inventario"""
    id_inventario: int = Field(..., ge=1, description="ID del registro en Inventario_Venta")
    precio_venta: Decimal = Field(..., ge=0, description="Precio final de venta")
    fecha_venta: Optional[date] = Field(None, description="Fecha de la venta (si no se envía, se usa hoy)")
    medio_pago: Optional[str] = Field(default="efectivo", description="efectivo | transferencia | tarjeta")
    ref_bancaria: Optional[str] = Field(None, max_length=100, description="Referencia bancaria si aplica")
    comprador_nombre: Optional[str] = Field(None, max_length=200, description="Nombre del comprador")
    comprador_nit: Optional[str] = Field(None, max_length=50, description="NIT/DPI del comprador")
    comprobante_url: Optional[HttpUrl] = Field(None, description="URL del comprobante/ticket")
    nota: Optional[str] = Field(None, max_length=500, description="Observaciones adicionales")


class CompradorOut(BaseModel):
    """Datos del comprador en la respuesta"""
    nombre: Optional[str] = None
    nit: Optional[str] = None


class InventarioVentaOut(BaseModel):
    """Respuesta tras registrar una venta"""
    id_inventario: int
    estado: str
    precio_venta: float
    fecha_venta: date
    medio_pago: Optional[str] = None
    ref_bancaria: Optional[str] = None
    comprador: Optional[CompradorOut] = None
    comprobante_url: Optional[str] = None
    nota: Optional[str] = None


# ============================================================
# LISTAR INVENTARIO (GET con filtros)
# ============================================================
class InventarioListItemOut(BaseModel):
    """Item de inventario en listado"""
    id_inventario: int
    id_articulo: int
    estado: str
    precio_base: float
    precio_actual: float
    dias_en_bodega: int
    fecha_ingreso: date
    descripcion_articulo: Optional[str] = None


class InventarioListResponse(BaseModel):
    """Respuesta de listado con paginación"""
    items: list[InventarioListItemOut]
    total: int
    limit: int
    offset: int


# ============================================================
# DETALLE DE INVENTARIO (GET individual)
# ============================================================
class InventarioDetalleOut(BaseModel):
    """Detalle completo de un item de inventario"""
    id_inventario: int
    id_articulo: int
    estado: str
    precio_base: float
    precio_actual: float
    dias_en_bodega: int
    fecha_ingreso: date
    articulo: Optional[dict] = None
    ultima_modificacion: Optional[str] = None