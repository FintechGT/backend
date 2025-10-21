# app/schemas/prestamos_activar.py
from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class PrestamoActivarIn(BaseModel):
    """
    Payload para activar un préstamo (cambiar de 'aprobado_pendiente_entrega' a 'activo').
    Todos los campos son opcionales.
    """
    nota: Optional[str] = Field(
        None,
        max_length=500,
        description="Observación adicional para auditoría"
    )
    fecha_desembolso: Optional[datetime] = Field(
        None,
        description="Fecha/hora del desembolso (si no se envía, se usa el momento actual)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "nota": "Contrato firmado por ambas partes",
                    "fecha_desembolso": "2025-10-21T14:30:00"
                },
                {
                    "nota": "Activación automática post-firma"
                },
                {}
            ]
        }
    }


class PrestamoActivarOut(BaseModel):
    """
    Respuesta tras activar el préstamo.
    """
    id_prestamo: int
    estado_anterior: str
    estado_nuevo: str
    fecha_desembolso: datetime
    mensaje: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_prestamo": 5001,
                "estado_anterior": "aprobado_pendiente_entrega",
                "estado_nuevo": "activo",
                "fecha_desembolso": "2025-10-21T14:30:00",
                "mensaje": "Préstamo activado exitosamente"
            }
        }
    }