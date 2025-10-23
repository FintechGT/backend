# app/schemas/inventario.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from decimal import Decimal


# ===================== SCHEMAS BASE =====================

class ArticuloBase(BaseModel):
    """Schema base para información del artículo"""
    id: int
    descripcion: str
    tipo: str
    condicion: str
    fotos: List[str] = []


class EstadoBase(BaseModel):
    """Schema base para el estado del inventario"""
    id: int
    nombre: str


class PrestamoOrigenBase(BaseModel):
    """Schema base para el préstamo de origen"""
    id: int
    cliente: str
    monto_original: Decimal
    motivo_ingreso: str


# ===================== REQUEST SCHEMAS =====================

class InventarioQueryParams(BaseModel):
    """Query parameters para GET /inventario"""
    estado: Optional[str] = None  # "disponible", "en_venta", "vendido"
    dias_en_bodega_min: Optional[int] = None
    dias_en_bodega_max: Optional[int] = None
    precio_min: Optional[float] = None
    precio_max: Optional[float] = None
    tipo_articulo: Optional[int] = None  # FK a Cat_Tipo_Articulo
    limit: int = Field(default=50, le=100)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="fecha_ingreso")  # "precio_actual", "dias_en_bodega"
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class AjustarPrecioRequest(BaseModel):
    """Request body para PATCH /inventario/{id}/ajustar-precio"""
    precio_nuevo: Decimal = Field(..., gt=0, description="Nuevo precio del artículo")
    motivo: str = Field(..., min_length=1, max_length=500)
    
    class Config:
        json_schema_extra = {
            "example": {
                "precio_nuevo": 850.00,
                "motivo": "Descuento por 60 días en bodega"
            }
        }


# ===================== RESPONSE SCHEMAS =====================

class InventarioItem(BaseModel):
    """Schema para un artículo en inventario"""
    id_inventario: int
    articulo: ArticuloBase
    estado: EstadoBase
    precio_base: Decimal
    precio_actual: Decimal
    dias_en_bodega: int
    fecha_ingreso: date
    prestamo_origen: Optional[PrestamoOrigenBase] = None
    
    class Config:
        from_attributes = True


class ResumenInventario(BaseModel):
    """Schema para el resumen del inventario"""
    valor_total_inventario: Decimal
    articulos_disponibles: int
    articulos_vendidos: int
    promedio_dias_bodega: float


class InventarioResponse(BaseModel):
    """Response para GET /inventario"""
    items: List[InventarioItem]
    total: int
    resumen: ResumenInventario
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id_inventario": 201,
                        "articulo": {
                            "id": 3001,
                            "descripcion": "iPhone 12 128GB",
                            "tipo": "Electrónica",
                            "condicion": "seminuevo",
                            "fotos": [
                                "https://cloudinary.com/iphone1.jpg",
                                "https://cloudinary.com/iphone2.jpg"
                            ]
                        },
                        "estado": {
                            "id": 1,
                            "nombre": "disponible"
                        },
                        "precio_base": 1200.00,
                        "precio_actual": 950.00,
                        "dias_en_bodega": 45,
                        "fecha_ingreso": "2025-08-30",
                        "prestamo_origen": {
                            "id": 5001,
                            "cliente": "Ana Pérez",
                            "monto_original": 1200.00,
                            "motivo_ingreso": "incumplimiento"
                        }
                    }
                ],
                "total": 28,
                "resumen": {
                    "valor_total_inventario": 65000.00,
                    "articulos_disponibles": 18,
                    "articulos_vendidos": 10,
                    "promedio_dias_bodega": 38
                }
            }
        }


class AjustarPrecioResponse(BaseModel):
    """Response para PATCH /inventario/{id}/ajustar-precio"""
    id_inventario: int
    precio_anterior: Decimal
    precio_actual: Decimal
    descuento_aplicado: Decimal
    porcentaje_descuento: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "id_inventario": 201,
                "precio_anterior": 950.00,
                "precio_actual": 850.00,
                "descuento_aplicado": 100.00,
                "porcentaje_descuento": 10.53
            }
        }