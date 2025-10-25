# ============================================================
# app/schemas/inventario_completo.py
# ============================================================
"""
Schemas para el inventario completo de artículos.
Incluye toda la información disponible sin importar el estado.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class InventarioCompletoItemOut(BaseModel):
    """
    Item completo de inventario con toda la información del artículo.
    """
    # Artículo base
    id_articulo: int
    id_solicitud: int
    id_tipo: int
    tipo_nombre: Optional[str] = None
    id_estado: int
    estado_nombre: Optional[str] = None
    descripcion: str
    valor_estimado: float
    valor_aprobado: Optional[float] = None
    condicion: Optional[str] = None
    
    # Fotos
    fotos: List[str] = Field(default_factory=list, description="URLs de las fotos del artículo")
    
    # Información de la solicitud
    solicitud_fecha: Optional[str] = Field(None, description="Fecha de envío de la solicitud")
    solicitud_metodo_entrega: Optional[str] = None
    solicitud_estado: Optional[str] = None
    
    # Información del cliente
    cliente_id: Optional[int] = None
    cliente_nombre: Optional[str] = None
    cliente_correo: Optional[str] = None
    cliente_telefono: Optional[str] = None
    
    # Información de inventario (si existe)
    inventario: Optional[dict] = Field(
        None,
        description="Info del inventario: id_inventario, estado, precio_base, precio_actual, dias_en_bodega, fecha_ingreso"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_articulo": 101,
                "id_solicitud": 15,
                "id_tipo": 2,
                "tipo_nombre": "Joyería",
                "id_estado": 3,
                "estado_nombre": "aprobado",
                "descripcion": "Anillo de oro 14k con piedra verde",
                "valor_estimado": 3200.0,
                "valor_aprobado": 1500.0,
                "condicion": "Usado, buen estado",
                "fotos": [
                    "https://cloudinary.com/foto1.jpg",
                    "https://cloudinary.com/foto2.jpg"
                ],
                "solicitud_fecha": "2025-10-15T10:30:00",
                "solicitud_metodo_entrega": "domicilio",
                "solicitud_estado": "evaluada",
                "cliente_id": 42,
                "cliente_nombre": "Juan Pérez",
                "cliente_correo": "juan@example.com",
                "cliente_telefono": "+502 5555-1234",
                "inventario": {
                    "id_inventario": 25,
                    "estado": "disponible",
                    "precio_base": 1400.0,
                    "precio_actual": 1400.0,
                    "dias_en_bodega": 5,
                    "fecha_ingreso": "2025-10-20"
                }
            }
        }
    }


class InventarioCompletoListResponse(BaseModel):
    """Respuesta del listado completo de inventario"""
    items: List[InventarioCompletoItemOut]
    total: int
    limit: int
    offset: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id_articulo": 101,
                        "id_solicitud": 15,
                        "id_tipo": 2,
                        "tipo_nombre": "Joyería",
                        "id_estado": 3,
                        "estado_nombre": "aprobado",
                        "descripcion": "Anillo de oro 14k",
                        "valor_estimado": 3200.0,
                        "valor_aprobado": 1500.0,
                        "condicion": "Usado, buen estado",
                        "fotos": ["https://cloudinary.com/foto1.jpg"],
                        "solicitud_fecha": "2025-10-15T10:30:00",
                        "solicitud_metodo_entrega": "domicilio",
                        "solicitud_estado": "evaluada",
                        "cliente_id": 42,
                        "cliente_nombre": "Juan Pérez",
                        "cliente_correo": "juan@example.com",
                        "cliente_telefono": "+502 5555-1234",
                        "inventario": {
                            "id_inventario": 25,
                            "estado": "disponible",
                            "precio_base": 1400.0,
                            "precio_actual": 1400.0,
                            "dias_en_bodega": 5,
                            "fecha_ingreso": "2025-10-20"
                        }
                    }
                ],
                "total": 150,
                "limit": 50,
                "offset": 0
            }
        }
    }