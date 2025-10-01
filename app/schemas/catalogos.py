from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ========== SCHEMAS DE SALIDA (OUT) ==========

class MetodoEntregaOut(BaseModel):
    """Schema para catálogo de métodos de entrega"""
    valor: str
    etiqueta: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "valor": "domicilio",
                "etiqueta": "Domicilio"
            }
        }


class CondicionArticuloOut(BaseModel):
    """Schema para catálogo de condiciones del artículo"""
    valor: str
    etiqueta: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "valor": "nuevo",
                "etiqueta": "Nuevo"
            }
        }


class TipoArticuloOut(BaseModel):
    """Schema para catálogo de tipos de artículo (Cat_Tipo_Articulo)"""
    id: int = Field(..., alias="id_tipo")
    nombre: str
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_tipo": 1,
                "nombre": "Electrónicos"
            }
        }


class EstadoSolicitudOut(BaseModel):
    """Schema para catálogo de estados de solicitud"""
    id: int = Field(..., alias="id_estado")
    nombre: str
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_estado": 1,
                "nombre": "Pendiente"
            }
        }


class EstadoArticuloOut(BaseModel):
    """Schema para catálogo de estados de artículo"""
    id: int = Field(..., alias="id_estado")
    nombre: str
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_estado": 1,
                "nombre": "En evaluación"
            }
        }


class EstadoPrestamoOut(BaseModel):
    """Schema para catálogo de estados de préstamo"""
    id: int = Field(..., alias="id_estado")
    nombre: str
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_estado": 1,
                "nombre": "Activo"
            }
        }


class EstadoPagoOut(BaseModel):
    """Schema para catálogo de estados de pago"""
    id: int = Field(..., alias="id_estado")
    nombre: str
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_estado": 1,
                "nombre": "Pendiente"
            }
        }


class EstadoInventarioOut(BaseModel):
    """Schema para catálogo de estados de inventario"""
    id: int = Field(..., alias="id_estado")
    nombre: str
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_estado": 1,
                "nombre": "Disponible"
            }
        }


# ========== SCHEMA PARA BOOTSTRAP (TODOS LOS CATÁLOGOS) ==========

class CatalogosBootstrapOut(BaseModel):
    """
    Schema que contiene todos los catálogos básicos en una sola respuesta.
    Usado para el endpoint /catalogos/bootstrap
    """
    metodos_entrega: List[MetodoEntregaOut]
    condiciones_articulo: List[CondicionArticuloOut]
    tipos_articulo: List[TipoArticuloOut]
    estados_solicitud: List[EstadoSolicitudOut]
    estados_articulo: List[EstadoArticuloOut]
    estados_prestamo: List[EstadoPrestamoOut]
    estados_pago: List[EstadoPagoOut]
    estados_inventario: List[EstadoInventarioOut]
    
    class Config:
        json_schema_extra = {
            "example": {
                "metodos_entrega": [
                    {"valor": "domicilio", "etiqueta": "Domicilio"},
                    {"valor": "oficina", "etiqueta": "Oficina"}
                ],
                "condiciones_articulo": [
                    {"valor": "nuevo", "etiqueta": "Nuevo"},
                    {"valor": "seminuevo", "etiqueta": "Seminuevo"},
                    {"valor": "usado", "etiqueta": "Usado"},
                    {"valor": "malo", "etiqueta": "Malo"}
                ],
                "tipos_articulo": [
                    {"id_tipo": 1, "nombre": "Electrónicos"},
                    {"id_tipo": 2, "nombre": "Joyas"}
                ],
                "estados_solicitud": [
                    {"id_estado": 1, "nombre": "Pendiente"},
                    {"id_estado": 2, "nombre": "Aprobada"}
                ],
                "estados_articulo": [
                    {"id_estado": 1, "nombre": "En evaluación"}
                ],
                "estados_prestamo": [
                    {"id_estado": 1, "nombre": "Activo"}
                ],
                "estados_pago": [
                    {"id_estado": 1, "nombre": "Pendiente"}
                ],
                "estados_inventario": [
                    {"id_estado": 1, "nombre": "Disponible"}
                ]
            }
        }


# ========== SCHEMA GENÉRICO PARA RESPUESTA VACÍA ==========

class CatalogoVacioOut(BaseModel):
    """Schema para cuando un catálogo está vacío"""
    message: str = "Sin datos"
    data: List = []
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Sin datos",
                "data": []
            }
        }