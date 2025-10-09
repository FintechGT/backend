# app/schemas/recalculo.py
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, Dict, Any
from decimal import Decimal

class RecalculoIn(BaseModel):
    """
    Payload para recalcular un préstamo.
    Todos los campos son opcionales; si no se envían, se usan valores por defecto.
    """
    fecha_corte: Optional[date] = Field(
        None, 
        description="Fecha hasta la cual calcular (default: hoy)"
    )
    tasa_interes_diaria: Optional[Decimal] = Field(
        None, 
        ge=0,
        description="Tasa de interés diaria (default: 0.0005 desde config)"
    )
    tasa_mora_diaria: Optional[Decimal] = Field(
        None,
        ge=0, 
        description="Tasa de mora diaria (default: 0.001 desde config)"
    )
    dias_gracia: Optional[int] = Field(
        None,
        ge=0,
        le=60,
        description="Días de gracia después del vencimiento (default: 3 desde config)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "fecha_corte": "2025-10-15",
                    "tasa_interes_diaria": 0.0005,
                    "tasa_mora_diaria": 0.001,
                    "dias_gracia": 3
                },
                {
                    "fecha_corte": "2025-10-09"
                },
                {}
            ]
        }
    }


class RecalculoOut(BaseModel):
    """
    Respuesta exitosa del recálculo.
    """
    id_prestamo: int
    fecha_corte: date
    dias_acumulados: int = Field(description="Días procesados en este recálculo")
    interes_agregado: float = Field(description="Interés agregado en este periodo")
    mora_agregada: float = Field(description="Mora agregada en este periodo")
    deuda_actual: float = Field(description="Deuda total actualizada (capital inicial)")
    interes_acumulada: float = Field(description="Interés acumulado total")
    mora_acumulada: float = Field(description="Mora acumulada total")
    ultimo_calculo_en: date
    estado_prestamo: Optional[Dict[str, Any]] = Field(
        None,
        description="Estado sugerido del préstamo"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_prestamo": 5001,
                "fecha_corte": "2025-10-09",
                "dias_acumulados": 5,
                "interes_agregado": 12.50,
                "mora_agregada": 5.00,
                "deuda_actual": 600.00,
                "interes_acumulada": 87.50,
                "mora_acumulada": 25.00,
                "ultimo_calculo_en": "2025-10-09",
                "estado_prestamo": {
                    "id": 2,
                    "codigo": "en_mora_parcial",
                    "dias_mora": 4
                }
            }
        }
    }