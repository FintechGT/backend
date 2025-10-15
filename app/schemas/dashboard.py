"""
Schemas para Dashboard de Métricas
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


# ============== SUB-SCHEMAS ==============

class PeriodoMetricas(BaseModel):
    """Periodo de tiempo del dashboard"""
    desde: date = Field(description="Fecha inicial del periodo")
    hasta: date = Field(description="Fecha final del periodo")


class MetricasPrestamos(BaseModel):
    """Métricas relacionadas con préstamos"""
    total_activos: int = Field(default=0, description="Total de préstamos activos")
    total_en_mora: int = Field(default=0, description="Total de préstamos en mora")
    total_liquidados: int = Field(default=0, description="Total de préstamos liquidados en el periodo")
    monto_total_cartera: Decimal = Field(default=Decimal("0.00"), description="Monto total de la cartera activa")
    monto_en_mora: Decimal = Field(default=Decimal("0.00"), description="Monto total en mora")


class MetricasSolicitudes(BaseModel):
    """Métricas relacionadas con solicitudes"""
    total_pendientes: int = Field(default=0, description="Total de solicitudes pendientes")
    total_evaluadas: int = Field(default=0, description="Total de solicitudes evaluadas en el periodo")
    total_rechazadas: int = Field(default=0, description="Total de solicitudes rechazadas en el periodo")


class MetricasPagos(BaseModel):
    """Métricas relacionadas con pagos"""
    total_validados: int = Field(default=0, description="Total de pagos validados en el periodo")
    monto_cobrado: Decimal = Field(default=Decimal("0.00"), description="Monto total cobrado en el periodo")
    total_pendientes: int = Field(default=0, description="Total de pagos pendientes de validación")
    monto_pendiente: Decimal = Field(default=Decimal("0.00"), description="Monto total pendiente de cobro")


class MetricasInventario(BaseModel):
    """Métricas relacionadas con inventario"""
    total_articulos: int = Field(default=0, description="Total de artículos en inventario")
    disponibles_venta: int = Field(default=0, description="Artículos disponibles para venta")
    vendidos: int = Field(default=0, description="Artículos vendidos en el periodo")
    valor_inventario: Decimal = Field(default=Decimal("0.00"), description="Valor total del inventario")


class MetricasCobranza(BaseModel):
    """Métricas relacionadas con cobranza en campo"""
    rutas_activas: int = Field(default=0, description="Número de rutas activas")
    visitas_completadas: int = Field(default=0, description="Visitas de cobranza completadas")
    tasa_exito_cobro: float = Field(default=0.0, ge=0, le=1, description="Tasa de éxito en cobros (0-1)")
    monto_cobrado_campo: Decimal = Field(default=Decimal("0.00"), description="Monto cobrado en campo")


class TopDeudor(BaseModel):
    """Información de los principales deudores"""
    id_usuario: int = Field(description="ID del usuario deudor")
    nombre: str = Field(description="Nombre completo del deudor")
    total_deuda: Decimal = Field(description="Deuda total incluyendo moras e intereses")
    dias_mora: int = Field(description="Días en mora del préstamo más antiguo")
    prestamos_en_mora: int = Field(description="Cantidad de préstamos en mora")


class ProximoVencimiento(BaseModel):
    """Información de próximos vencimientos"""
    id_prestamo: int = Field(description="ID del préstamo")
    cliente: str = Field(description="Nombre del cliente")
    monto_pendiente: Decimal = Field(description="Monto pendiente de pago")
    fecha_vencimiento: date = Field(description="Fecha de vencimiento")
    dias_restantes: int = Field(description="Días restantes para el vencimiento")


# ============== SCHEMA PRINCIPAL ==============

class DashboardMetricasResponse(BaseModel):
    """Respuesta completa del dashboard de métricas"""
    periodo: PeriodoMetricas
    prestamos: MetricasPrestamos
    solicitudes: MetricasSolicitudes
    pagos: MetricasPagos
    inventario: MetricasInventario
    cobranza: MetricasCobranza
    top_deudores: List[TopDeudor] = Field(default_factory=list, description="Top 10 deudores con mayor deuda")
    proximos_vencimientos: List[ProximoVencimiento] = Field(default_factory=list, description="Próximos 20 vencimientos")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat()
        }