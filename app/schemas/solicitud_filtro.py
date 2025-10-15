from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ========== SCHEMAS ANIDADOS ==========

class UsuarioBasicOut(BaseModel):
    """Información básica del usuario/cliente"""
    nombre: str
    correo: str
    
    class Config:
        from_attributes = True


class EstadoSolicitudOut(BaseModel):
    """Estado de la solicitud"""
    id: int
    nombre: str
    
    class Config:
        from_attributes = True


# ========== SCHEMA PRINCIPAL DE SOLICITUD ==========

class SolicitudConDetalleOut(BaseModel):
    """
    Schema para listar solicitudes con toda la información detallada
    Incluye: usuario, estado, y contadores de artículos
    """
    id_solicitud: int = Field(..., alias="Id_Solicitud")
    id_usuario: int = Field(..., alias="Id_Usuario")
    usuario: UsuarioBasicOut
    estado: EstadoSolicitudOut
    fecha_envio: datetime = Field(..., alias="Fecha_envio")
    metodo_entrega: str = Field(..., alias="Metodo_entrega")
    direccion_entrega: Optional[str] = Field(None, alias="Direccion_entrega")
    total_articulos: int = Field(..., description="Total de artículos en la solicitud")
    articulos_pendientes: int = Field(..., description="Artículos aún sin evaluar")
    articulos_evaluados: int = Field(..., description="Artículos ya evaluados")
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id_solicitud": 2001,
                "id_usuario": 1001,
                "usuario": {
                    "nombre": "Ana Pérez",
                    "correo": "ana.perez@example.com"
                },
                "estado": {
                    "id": 1,
                    "nombre": "pendiente"
                },
                "fecha_envio": "2025-08-13T10:05:00Z",
                "metodo_entrega": "domicilio",
                "direccion_entrega": "6a avenida 10-22, Zona 1",
                "total_articulos": 2,
                "articulos_pendientes": 1,
                "articulos_evaluados": 1
            }
        }


# ========== SCHEMA DE RESPUESTA CON PAGINACIÓN ==========

class SolicitudListResponse(BaseModel):
    """
    Respuesta paginada de solicitudes
    """
    items: List[SolicitudConDetalleOut]
    total: int = Field(..., description="Total de solicitudes que coinciden con los filtros")
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id_solicitud": 2001,
                        "id_usuario": 1001,
                        "usuario": {
                            "nombre": "Ana Pérez",
                            "correo": "ana.perez@example.com"
                        },
                        "estado": {
                            "id": 1,
                            "nombre": "pendiente"
                        },
                        "fecha_envio": "2025-08-13T10:05:00Z",
                        "metodo_entrega": "domicilio",
                        "direccion_entrega": "6a avenida 10-22, Zona 1",
                        "total_articulos": 2,
                        "articulos_pendientes": 1,
                        "articulos_evaluados": 1
                    }
                ],
                "total": 12
            }
        }