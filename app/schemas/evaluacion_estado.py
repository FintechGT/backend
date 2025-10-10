# app/schemas/evaluacion_estado.py
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, Dict, Any


class EvaluarEstadoIn(BaseModel):
    """
    Payload para evaluar el estado operativo de un préstamo.
    Todos los campos son opcionales con valores por defecto.
    """
    fecha_corte: Optional[date] = Field(
        None,
        description="Fecha de corte para la evaluación (default: hoy)"
    )
    dias_gracia: Optional[int] = Field(
        default=3,
        ge=0,
        le=60,
        description="Días de gracia después del vencimiento"
    )
    umbral_incumplido_dias: Optional[int] = Field(
        default=15,
        ge=0,
        le=365,
        description="Días después de gracia para considerar incumplimiento definitivo"
    )
    forzar_recalculo: Optional[bool] = Field(
        default=False,
        description="Si true, ejecuta recálculo de saldos antes de evaluar"
    )
    marcar_inventario: Optional[bool] = Field(
        default=True,
        description="Si true y hay incumplimiento definitivo, mueve artículo a inventario"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "fecha_corte": "2025-10-10",
                    "dias_gracia": 3,
                    "umbral_incumplido_dias": 15,
                    "forzar_recalculo": False,
                    "marcar_inventario": True
                },
                {
                    "fecha_corte": "2025-10-09"
                },
                {}
            ]
        }
    }


class EstadoDto(BaseModel):
    """Representación de un estado de préstamo."""
    id: int
    codigo: str


class AccionesDto(BaseModel):
    """Acciones ejecutadas durante la evaluación."""
    recalculo_ejecutado: bool
    articulo_a_inventario: bool


class EvaluarEstadoOut(BaseModel):
    """
    Respuesta exitosa de la evaluación de estado.
    """
    id_prestamo: int
    estado_anterior: EstadoDto
    estado_nuevo: EstadoDto
    motivo: str = Field(description="Razón del cambio de estado")
    deuda_actual: float
    mora_acumulada: float
    interes_acumulada: float
    fecha_corte: date
    acciones: AccionesDto

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_prestamo": 5001,
                "estado_anterior": {"id": 1, "codigo": "activo"},
                "estado_nuevo": {"id": 2, "codigo": "en_mora"},
                "motivo": "Fecha corte supera vencimiento + gracia",
                "deuda_actual": 1317.50,
                "mora_acumulada": 25.00,
                "interes_acumulada": 87.50,
                "fecha_corte": "2025-10-09",
                "acciones": {
                    "recalculo_ejecutado": True,
                    "articulo_a_inventario": False
                }
            }
        }
    }