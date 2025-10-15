"""
Router de Dashboard de Métricas
Proporciona KPIs y métricas para administradores y operadores
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, and_, or_, text, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased

from app.db.database import get_db
from app.db.models import (
    Prestamo,
    EstadoPrestamo,
    Articulo,
    EstadoArticulo,
    Solicitud,
    EstadoSolicitud,
    User,
    Pago,
    EstadoPago,
    RutaCobranza,
    VisitaCobranza,
    EstadoVisita
)
from app.api.deps import get_current_user
from app.schemas.dashboard import (
    DashboardMetricasResponse,
    PeriodoMetricas,
    MetricasPrestamos,
    MetricasSolicitudes,
    MetricasPagos,
    MetricasInventario,
    MetricasCobranza,
    TopDeudor,
    ProximoVencimiento
)
from app.utils.roles import usuario_tiene_algun_rol

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ============== FUNCIONES AUXILIARES ==============

def get_primer_dia_mes_actual() -> date:
    """Obtiene el primer día del mes actual"""
    hoy = date.today()
    return date(hoy.year, hoy.month, 1)


async def obtener_metricas_prestamos(
    db: AsyncSession,
    fecha_desde: date,
    fecha_hasta: date
) -> MetricasPrestamos:
    """Obtiene las métricas relacionadas con préstamos"""
    
    # Estados de préstamos activos
    estados_activos = ['activo', 'aprobado_pendiente_entrega']
    # Estados de préstamos en mora
    estados_mora = ['en_mora_parcial', 'en_mora_grave']
    # Estado liquidado
    estado_liquidado = 'liquidado'
    
    # Total de préstamos activos
    query_activos = select(func.count(Prestamo.id_prestamo)).where(
        Prestamo.id_estado.in_(
            select(EstadoPrestamo.id_estado_prestamo).where(
                EstadoPrestamo.nombre.in_(estados_activos)
            )
        )
    )
    result_activos = await db.execute(query_activos)
    total_activos = result_activos.scalar() or 0
    
    # Total de préstamos en mora
    query_mora = select(func.count(Prestamo.id_prestamo)).where(
        Prestamo.id_estado.in_(
            select(EstadoPrestamo.id_estado_prestamo).where(
                EstadoPrestamo.nombre.in_(estados_mora)
            )
        )
    )
    result_mora = await db.execute(query_mora)
    total_en_mora = result_mora.scalar() or 0
    
    # Total de préstamos liquidados en el periodo
    query_liquidados = select(func.count(Prestamo.id_prestamo)).where(
        and_(
            Prestamo.id_estado == select(EstadoPrestamo.id_estado_prestamo).where(
                EstadoPrestamo.nombre == estado_liquidado
            ).scalar_subquery(),
            Prestamo.fecha_actualizacion >= fecha_desde,
            Prestamo.fecha_actualizacion <= fecha_hasta
        )
    )
    result_liquidados = await db.execute(query_liquidados)
    total_liquidados = result_liquidados.scalar() or 0
    
    # Monto total de la cartera activa
    query_monto_cartera = select(func.sum(Prestamo.deuda_actual)).where(
        Prestamo.id_estado.in_(
            select(EstadoPrestamo.id_estado_prestamo).where(
                EstadoPrestamo.nombre.in_(estados_activos + estados_mora)
            )
        )
    )
    result_monto_cartera = await db.execute(query_monto_cartera)
    monto_total_cartera = result_monto_cartera.scalar() or Decimal("0.00")
    
    # Monto total en mora
    query_monto_mora = select(
        func.sum(Prestamo.deuda_actual + Prestamo.mora_acumulada)
    ).where(
        Prestamo.id_estado.in_(
            select(EstadoPrestamo.id_estado_prestamo).where(
                EstadoPrestamo.nombre.in_(estados_mora)
            )
        )
    )
    result_monto_mora = await db.execute(query_monto_mora)
    monto_en_mora = result_monto_mora.scalar() or Decimal("0.00")
    
    return MetricasPrestamos(
        total_activos=total_activos,
        total_en_mora=total_en_mora,
        total_liquidados=total_liquidados,
        monto_total_cartera=monto_total_cartera,
        monto_en_mora=monto_en_mora
    )


async def obtener_metricas_solicitudes(
    db: AsyncSession,
    fecha_desde: date,
    fecha_hasta: date
) -> MetricasSolicitudes:
    """Obtiene las métricas relacionadas con solicitudes"""
    
    # Total pendientes
    query_pendientes = select(func.count(Solicitud.id_solicitud)).where(
        Solicitud.id_estado == select(EstadoSolicitud.id_estado_solicitud).where(
            EstadoSolicitud.nombre == 'pendiente'
        ).scalar_subquery()
    )
    result_pendientes = await db.execute(query_pendientes)
    total_pendientes = result_pendientes.scalar() or 0
    
    # Total evaluadas en el periodo
    query_evaluadas = select(func.count(Solicitud.id_solicitud)).where(
        and_(
            Solicitud.id_estado == select(EstadoSolicitud.id_estado_solicitud).where(
                EstadoSolicitud.nombre == 'evaluada'
            ).scalar_subquery(),
            Solicitud.fecha_actualizacion >= fecha_desde,
            Solicitud.fecha_actualizacion <= fecha_hasta
        )
    )
    result_evaluadas = await db.execute(query_evaluadas)
    total_evaluadas = result_evaluadas.scalar() or 0
    
    # Total rechazadas en el periodo
    query_rechazadas = select(func.count(Solicitud.id_solicitud)).where(
        and_(
            Solicitud.id_estado == select(EstadoSolicitud.id_estado_solicitud).where(
                EstadoSolicitud.nombre == 'rechazada'
            ).scalar_subquery(),
            Solicitud.fecha_actualizacion >= fecha_desde,
            Solicitud.fecha_actualizacion <= fecha_hasta
        )
    )
    result_rechazadas = await db.execute(query_rechazadas)
    total_rechazadas = result_rechazadas.scalar() or 0
    
    return MetricasSolicitudes(
        total_pendientes=total_pendientes,
        total_evaluadas=total_evaluadas,
        total_rechazadas=total_rechazadas
    )


async def obtener_metricas_pagos(
    db: AsyncSession,
    fecha_desde: date,
    fecha_hasta: date
) -> MetricasPagos:
    """Obtiene las métricas relacionadas con pagos"""
    
    # Pagos validados en el periodo
    query_validados = select(
        func.count(Pago.id_pago),
        func.sum(Pago.monto)
    ).where(
        and_(
            Pago.id_estado == select(EstadoPago.id_estado_pago).where(
                EstadoPago.nombre == 'validado'
            ).scalar_subquery(),
            Pago.fecha_pago >= fecha_desde,
            Pago.fecha_pago <= fecha_hasta
        )
    )
    result_validados = await db.execute(query_validados)
    total_validados, monto_cobrado = result_validados.first() or (0, Decimal("0.00"))
    
    # Pagos pendientes de validación
    query_pendientes = select(
        func.count(Pago.id_pago),
        func.sum(Pago.monto)
    ).where(
        Pago.id_estado == select(EstadoPago.id_estado_pago).where(
            EstadoPago.nombre == 'pendiente_validacion'
        ).scalar_subquery()
    )
    result_pendientes = await db.execute(query_pendientes)
    total_pendientes, monto_pendiente = result_pendientes.first() or (0, Decimal("0.00"))
    
    return MetricasPagos(
        total_validados=total_validados or 0,
        monto_cobrado=monto_cobrado or Decimal("0.00"),
        total_pendientes=total_pendientes or 0,
        monto_pendiente=monto_pendiente or Decimal("0.00")
    )


async def obtener_metricas_inventario(
    db: AsyncSession,
    fecha_desde: date,
    fecha_hasta: date
) -> MetricasInventario:
    """Obtiene las métricas relacionadas con inventario"""
    
    # Total de artículos en inventario
    query_total = select(func.count(Articulo.id_articulo)).where(
        Articulo.id_estado == select(EstadoArticulo.id_estado_articulo).where(
            EstadoArticulo.nombre == 'en_inventario'
        ).scalar_subquery()
    )
    result_total = await db.execute(query_total)
    total_articulos = result_total.scalar() or 0
    
    # Disponibles para venta
    query_disponibles = select(func.count(Articulo.id_articulo)).where(
        Articulo.id_estado == select(EstadoArticulo.id_estado_articulo).where(
            EstadoArticulo.nombre == 'disponible_venta'
        ).scalar_subquery()
    )
    result_disponibles = await db.execute(query_disponibles)
    disponibles_venta = result_disponibles.scalar() or 0
    
    # Vendidos en el periodo
    query_vendidos = select(func.count(Articulo.id_articulo)).where(
        and_(
            Articulo.id_estado == select(EstadoArticulo.id_estado_articulo).where(
                EstadoArticulo.nombre == 'vendido'
            ).scalar_subquery(),
            Articulo.fecha_actualizacion >= fecha_desde,
            Articulo.fecha_actualizacion <= fecha_hasta
        )
    )
    result_vendidos = await db.execute(query_vendidos)
    vendidos = result_vendidos.scalar() or 0
    
    # Valor del inventario
    query_valor = select(func.sum(Articulo.valor)).where(
        Articulo.id_estado.in_(
            select(EstadoArticulo.id_estado_articulo).where(
                EstadoArticulo.nombre.in_(['en_inventario', 'disponible_venta'])
            )
        )
    )
    result_valor = await db.execute(query_valor)
    valor_inventario = result_valor.scalar() or Decimal("0.00")
    
    return MetricasInventario(
        total_articulos=total_articulos,
        disponibles_venta=disponibles_venta,
        vendidos=vendidos,
        valor_inventario=valor_inventario
    )


async def obtener_metricas_cobranza(
    db: AsyncSession,
    fecha_desde: date,
    fecha_hasta: date
) -> MetricasCobranza:
    """Obtiene las métricas relacionadas con cobranza en campo"""
    
    # Rutas activas
    # Rutas activas (EstadoRuta eliminado, ajustar lógica si es necesario)
    rutas_activas = 0  # Ajusta aquí según tu lógica real
    
    # Visitas completadas en el periodo
    query_visitas = select(func.count(VisitaCobranza.id_visita)).where(
        and_(
            VisitaCobranza.id_estado == select(EstadoVisita.id_estado_visita).where(
                EstadoVisita.nombre == 'completada'
            ).scalar_subquery(),
            VisitaCobranza.fecha_visita >= fecha_desde,
            VisitaCobranza.fecha_visita <= fecha_hasta
        )
    )
    result_visitas = await db.execute(query_visitas)
    visitas_completadas = result_visitas.scalar() or 0
    
    # Tasa de éxito y monto cobrado en campo
    query_exito = select(
        func.count(case((VisitaCobranza.cobro_exitoso == True, 1))),
        func.count(VisitaCobranza.id_visita),
        func.sum(case((VisitaCobranza.cobro_exitoso == True, VisitaCobranza.monto_cobrado), else_=0))
    ).where(
        and_(
            VisitaCobranza.fecha_visita >= fecha_desde,
            VisitaCobranza.fecha_visita <= fecha_hasta,
            VisitaCobranza.id_estado == select(EstadoVisita.id_estado_visita).where(
                EstadoVisita.nombre == 'completada'
            ).scalar_subquery()
        )
    )
    result_exito = await db.execute(query_exito)
    visitas_exitosas, total_visitas, monto_cobrado_campo = result_exito.first() or (0, 0, Decimal("0.00"))
    
    tasa_exito = (visitas_exitosas / total_visitas) if total_visitas > 0 else 0.0
    
    return MetricasCobranza(
        rutas_activas=rutas_activas,
        visitas_completadas=visitas_completadas,
        tasa_exito_cobro=round(tasa_exito, 2),
        monto_cobrado_campo=monto_cobrado_campo or Decimal("0.00")
    )


async def obtener_top_deudores(
    db: AsyncSession,
    limite: int = 10
) -> list[TopDeudor]:
    """Obtiene el top de deudores con mayor deuda"""
    
    # Query compleja con JOINs para obtener deudores
    query = text("""
        SELECT 
            u.id_usuario,
            u.nombre,
            u.apellido,
            SUM(p.deuda_actual + p.mora_acumulada + p.interes_acumulada) AS total_deuda,
            MAX(DATEDIFF(CURDATE(), p.fecha_vencimiento)) AS dias_mora,
            COUNT(DISTINCT p.id_prestamo) AS prestamos_en_mora
        FROM prestamo p
        JOIN articulo a ON a.id_articulo = p.id_articulo
        JOIN solicitud s ON s.id_solicitud = a.id_solicitud
        JOIN users u ON u.id_usuario = s.id_usuario
        JOIN estado_prestamo ep ON ep.id_estado_prestamo = p.id_estado
        WHERE ep.nombre IN ('en_mora_parcial', 'en_mora_grave')
        GROUP BY u.id_usuario, u.nombre, u.apellido
        ORDER BY total_deuda DESC
        LIMIT :limite
    """)
    
    result = await db.execute(query, {"limite": limite})
    rows = result.fetchall()
    
    deudores = []
    for row in rows:
        deudores.append(TopDeudor(
            id_usuario=row.id_usuario,
            nombre=f"{row.nombre} {row.apellido}",
            total_deuda=Decimal(str(row.total_deuda or 0)),
            dias_mora=row.dias_mora or 0,
            prestamos_en_mora=row.prestamos_en_mora or 0
        ))
    
    return deudores


async def obtener_proximos_vencimientos(
    db: AsyncSession,
    dias_adelante: int = 30,
    limite: int = 20
) -> list[ProximoVencimiento]:
    """Obtiene los próximos préstamos a vencer"""
    
    fecha_limite = date.today() + timedelta(days=dias_adelante)
    
    query = text("""
        SELECT 
            p.id_prestamo,
            CONCAT(u.nombre, ' ', u.apellido) AS cliente,
            (p.deuda_actual + p.mora_acumulada + p.interes_acumulada) AS monto_pendiente,
            p.fecha_vencimiento,
            DATEDIFF(p.fecha_vencimiento, CURDATE()) AS dias_restantes
        FROM prestamo p
        JOIN articulo a ON a.id_articulo = p.id_articulo
        JOIN solicitud s ON s.id_solicitud = a.id_solicitud
        JOIN users u ON u.id_usuario = s.id_usuario
        JOIN estado_prestamo ep ON ep.id_estado_prestamo = p.id_estado
        WHERE p.fecha_vencimiento BETWEEN CURDATE() AND :fecha_limite
            AND ep.nombre = 'activo'
        ORDER BY p.fecha_vencimiento ASC
        LIMIT :limite
    """)
    
    result = await db.execute(query, {"fecha_limite": fecha_limite, "limite": limite})
    rows = result.fetchall()
    
    vencimientos = []
    for row in rows:
        vencimientos.append(ProximoVencimiento(
            id_prestamo=row.id_prestamo,
            cliente=row.cliente,
            monto_pendiente=Decimal(str(row.monto_pendiente or 0)),
            fecha_vencimiento=row.fecha_vencimiento,
            dias_restantes=row.dias_restantes or 0
        ))
    
    return vencimientos


# ============== ENDPOINT PRINCIPAL ==============

@router.get(
    "/metricas",
    response_model=DashboardMetricasResponse,
    summary="Obtener métricas del dashboard",
    description="Obtiene KPIs y métricas para el dashboard de administradores y operadores"
)
async def obtener_dashboard_metricas(
    fecha_desde: Optional[date] = Query(
        None,
        description="Fecha inicial del periodo (por defecto: primer día del mes actual)"
    ),
    fecha_hasta: Optional[date] = Query(
        None,
        description="Fecha final del periodo (por defecto: hoy)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> DashboardMetricasResponse:
    """
    Obtiene las métricas del dashboard para administradores y operadores.
    
    Incluye:
    - Métricas de préstamos
    - Métricas de solicitudes
    - Métricas de pagos
    - Métricas de inventario
    - Métricas de cobranza
    - Top 10 deudores
    - Próximos 20 vencimientos
    """
    
    # Verificar permisos (solo Admin y Operador)
    if not usuario_tiene_algun_rol(current_user, ["ADMIN", "OPERADOR"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para acceder al dashboard"
        )
    
    # Establecer fechas por defecto si no se proporcionan
    if fecha_desde is None:
        fecha_desde = get_primer_dia_mes_actual()
    
    if fecha_hasta is None:
        fecha_hasta = date.today()
    
    # Validar que fecha_desde no sea mayor que fecha_hasta
    if fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha inicial no puede ser mayor que la fecha final"
        )
    
    # Obtener todas las métricas
    try:
        # Métricas principales
        metricas_prestamos = await obtener_metricas_prestamos(db, fecha_desde, fecha_hasta)
        metricas_solicitudes = await obtener_metricas_solicitudes(db, fecha_desde, fecha_hasta)
        metricas_pagos = await obtener_metricas_pagos(db, fecha_desde, fecha_hasta)
        metricas_inventario = await obtener_metricas_inventario(db, fecha_desde, fecha_hasta)
        metricas_cobranza = await obtener_metricas_cobranza(db, fecha_desde, fecha_hasta)
        
        # Top deudores y próximos vencimientos
        top_deudores = await obtener_top_deudores(db)
        proximos_vencimientos = await obtener_proximos_vencimientos(db)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener las métricas: {str(e)}"
        )
    
    # Construir y retornar la respuesta
    return DashboardMetricasResponse(
        periodo=PeriodoMetricas(
            desde=fecha_desde,
            hasta=fecha_hasta
        ),
        prestamos=metricas_prestamos,
        solicitudes=metricas_solicitudes,
        pagos=metricas_pagos,
        inventario=metricas_inventario,
        cobranza=metricas_cobranza,
        top_deudores=top_deudores,
        proximos_vencimientos=proximos_vencimientos
    )