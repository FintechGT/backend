# ============================================================
# app/schemas/recalculo_bulk.py
# ============================================================
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List, Literal
from decimal import Decimal


# ============================================================
# QUERY PARAMS (filtros)
# ============================================================
class RecalculoBulkQuery(BaseModel):
    older_than_days: Optional[int] = Field(
        default=None,
        ge=0,
        le=365,
        description="Selecciona préstamos cuyo ultimo_calculo_en sea de hace ≥ N días (o NULL)"
    )
    solo_en_mora: Optional[bool] = Field(
        default=False,
        description="Si true, filtra solo préstamos en estados de mora"
    )
    limit: Optional[int] = Field(
        default=500,
        ge=1,
        le=5000,
        description="Tamaño máximo del lote a procesar en esta invocación"
    )
    offset: Optional[int] = Field(
        default=0,
        ge=0,
        description="Desplazamiento para paginar lotes en ejecuciones sucesivas"
    )
    ids: Optional[List[int]] = Field(
        default=None,
        description="Forzar a un subconjunto específico de préstamos (ignora otros filtros)"
    )


# ============================================================
# BODY (configuración del cálculo)
# ============================================================
class RecalculoBulkBody(BaseModel):
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
        default=3,
        ge=0,
        le=60,
        description="Días de gracia después del vencimiento"
    )
    modo_preciso: Optional[bool] = Field(
        default=False,
        description="Si true, hace cálculo día a día (más preciso pero más caro)"
    )


# ============================================================
# RESPUESTA (item individual)
# ============================================================
class RecalculoItemOut(BaseModel):
    id_prestamo: int
    dias_acumulados: int
    interes_agregado: float
    mora_agregada: float
    deuda_actual: float
    interes_acumulada: float
    mora_acumulada: float
    ultimo_calculo_en: date
    resultado: Literal["actualizado", "sin_cambios", "saltado"]
    motivo: Optional[str] = None


# ============================================================
# RESPUESTA (lote completo)
# ============================================================
class RecalculoBulkOut(BaseModel):
    total_candidatos: int
    procesados: int
    actualizados: int
    sin_cambios: int
    saltados: int
    detalle: List[RecalculoItemOut]
