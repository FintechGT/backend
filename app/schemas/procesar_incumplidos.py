# app/schemas/procesar_incumplidos.py
from __future__ import annotations

from datetime import date
from typing import Optional, List

from pydantic import BaseModel, Field


class ProcesarIncumplidosIn(BaseModel):
    """
    Payload para procesar préstamos en incumplimiento definitivo (masivo).
    Todos los campos son opcionales; si no se envían, se usarán defaults
    o valores de Configuraciones_Generales cuando aplique.
    """
    fecha_corte: Optional[date] = Field(
        default=None,
        description="Fecha base del proceso (si no se envía, se usa la fecha de hoy)."
    )
    dias_gracia: Optional[int] = Field(
        default=3,
        ge=0,
        le=60,
        description="Días posteriores al vencimiento antes de considerar mora."
    )
    umbral_incumplido_dias: Optional[int] = Field(
        default=15,
        ge=0,
        le=365,
        description="Días adicionales después de la gracia para considerar incumplimiento definitivo."
    )
    estado_prestamo_incumplido: str = Field(
        default="incumplido",
        description="Nombre del estado de préstamo para filtrar candidatos (case-insensitive)."
    )
    estado_articulo_inventario: str = Field(
        default="en_inventario",
        description="Nombre del estado de artículo a aplicar (case-insensitive)."
    )
    insertar_en_tabla_inventario: bool = Field(
        default=True,
        description="Si true, inserta registro en Inventario_Venta si aún no existe."
    )
    ubicacion_default: str = Field(
        default="Bodega Central",
        max_length=120,
        description="Ubicación inicial (solo para auditoría si la tabla no tiene ese campo)."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "fecha_corte": "2025-10-10",
                    "dias_gracia": 3,
                    "umbral_incumplido_dias": 15,
                    "estado_prestamo_incumplido": "incumplido",
                    "estado_articulo_inventario": "en_inventario",
                    "insertar_en_tabla_inventario": True,
                    "ubicacion_default": "Bodega Central"
                },
                {
                    "fecha_corte": "2025-10-10"
                },
                {}
            ]
        }
    }


class ProcesarIncumplidosItem(BaseModel):
    """Detalle por préstamo procesado."""
    id_prestamo: int = Field(description="ID del préstamo afectado.")
    id_articulo: int = Field(description="ID del artículo asociado.")
    accion: str = Field(description="Acción aplicada: 'trasladado' | 'omitido'.")
    motivo: str = Field(description="Motivo de la acción realizada.")
    fecha_ingreso: Optional[date] = Field(
        default=None,
        description="Fecha de ingreso a inventario (si aplica)."
    )


class ProcesarIncumplidosOut(BaseModel):
    """
    Respuesta del procesamiento masivo de incumplidos.
    """
    total_candidatos: int = Field(description="Total de préstamos evaluados como candidatos.")
    articulos_trasladados: int = Field(description="Cantidad de artículos movidos a inventario.")
    prestamos_actualizados: int = Field(
        description="Cantidad de préstamos impactados (equivale a artículos trasladados)."
    )
    ya_en_inventario: int = Field(description="Artículos que ya estaban en inventario/venta/vendido.")
    errores: int = Field(description="Número de errores encontrados durante el proceso.")
    detalle: List[ProcesarIncumplidosItem]

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_candidatos": 32,
                "articulos_trasladados": 28,
                "prestamos_actualizados": 28,
                "ya_en_inventario": 4,
                "errores": 0,
                "detalle": [
                    {
                        "id_prestamo": 21,
                        "id_articulo": 50,
                        "accion": "trasladado",
                        "motivo": "Superó 15 días después del período de gracia",
                        "fecha_ingreso": "2025-10-10"
                    },
                    {
                        "id_prestamo": 24,
                        "id_articulo": 57,
                        "accion": "omitido",
                        "motivo": "Artículo ya está en inventario"
                    }
                ]
            }
        }
    }
