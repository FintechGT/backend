# app/schemas/solicitudes_articulos.py
from typing import List, Optional
from pydantic import BaseModel, Field, condecimal

# ============================================================
# SCHEMAS PARA POST /solicitudes/{id}/articulos
# ============================================================
class SolicitudArticuloCreate(BaseModel):
    """Request para agregar un artículo a una solicitud existente."""
    id_tipo: int = Field(..., gt=0, description="ID del tipo de artículo")
    descripcion: str = Field(..., min_length=3, max_length=800, description="Descripción del artículo")
    valor_estimado: condecimal(ge=0, max_digits=12, decimal_places=2) = Field(
        ..., description="Valor estimado del artículo"
    )
    condicion: Optional[str] = Field(None, max_length=120, description="Condición del artículo")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_tipo": 2,
                "descripcion": "Anillo de oro 14k con piedra verde",
                "valor_estimado": 3200,
                "condicion": "Usado, en buen estado",
            }
        }
    }


class FotoOut(BaseModel):
    """Representación de una foto de artículo."""
    id_foto: int
    url: str
    orden: int = 1


class SolicitudArticuloOut(BaseModel):
    """Respuesta al agregar o listar artículos de una solicitud."""
    id_articulo: int
    id_solicitud: int
    id_tipo: int
    descripcion: str
    valor_estimado: float
    condicion: Optional[str] = None
    estado: str
    fotos: List[FotoOut] = []

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_articulo": 101,
                "id_solicitud": 15,
                "id_tipo": 2,
                "descripcion": "Anillo de oro 14k con piedra verde",
                "valor_estimado": 3200.0,
                "condicion": "Usado, en buen estado",
                "estado": "pendiente",
                "fotos": [],
            }
        }
    }
