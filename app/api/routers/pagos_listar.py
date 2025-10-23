# ============================================================
# app/api/routers/pagos_listar.py
# ============================================================
"""
Router para listar y consultar pagos (admin/cajero/supervisor).
Incluye filtros avanzados, paginación y detalle individual.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

# Deps
from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.pago import Pago
from app.db.models.estado_pago import EstadoPago
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.solicitud import Solicitud
from app.db.models.user import User
from app.db.models.comprobante import Comprobante

# Schemas
from app.schemas.pagos_listar import (
    PagoListItemOut,
    PagoListResponse,
    PagoDetalleOut,
    ClienteResumen,
    PrestamoResumen,
    EstadoResumen,
)

# Utils
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/pagos", tags=["Pagos - Listado"])

# Roles con permisos de lectura
ROLES_LECTURA = ["ADMINISTRADOR", "CAJERO", "SUPERVISOR"]


# ============================================================
# HELPERS
# ============================================================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _parse_date(d: Optional[str]) -> Optional[date]:
    """Parsea string YYYY-MM-DD a date o None."""
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Fecha inválida: {d} (usar YYYY-MM-DD)")


async def _cargar_comprobantes(db: AsyncSession, id_pago: int) -> List[Dict[str, Any]]:
    """Carga comprobantes asociados a un pago."""
    result = await db.execute(
        select(Comprobante).where(Comprobante.id_pago == id_pago)
    )
    comprobantes = result.scalars().all()
    return [
        {
            "id_comprobante": c.id_comprobante,
            "url": c.imagen,  # mapea a 'imagen' en BD
        }
        for c in comprobantes
    ]


async def _cargar_cliente_prestamo(
    db: AsyncSession,
    id_prestamo: int
) -> tuple[Optional[ClienteResumen], Optional[PrestamoResumen]]:
    """
    Carga resumen del préstamo y cliente asociado.
    Retorna (cliente, prestamo) o (None, None) si no existe.
    """
    # Cargar préstamo con estado
    result_prest = await db.execute(
        select(Prestamo).where(Prestamo.id_prestamo == id_prestamo)
    )
    prestamo = result_prest.scalar_one_or_none()
    if not prestamo:
        return None, None

    # Estado del préstamo
    result_estado = await db.execute(
        select(EstadoPrestamo).where(
            EstadoPrestamo.id_estado_prestamo == prestamo.id_estado
        )
    )
    estado_prest = result_estado.scalar_one_or_none()
    estado_nombre = estado_prest.nombre if estado_prest else "desconocido"

    # Artículo → Solicitud → Usuario
    result_art = await db.execute(
        select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo)
    )
    articulo = result_art.scalar_one_or_none()
    if not articulo:
        return None, PrestamoResumen(
            id=prestamo.id_prestamo,
            estado=estado_nombre,
            monto_prestamo=float(prestamo.monto_prestamo),
            deuda_actual=float(prestamo.deuda_actual),
            mora_acumulada=float(prestamo.mora_acumulada),
            interes_acumulada=float(prestamo.interes_acumulada),
        )

    # Solicitud
    result_sol = await db.execute(
        select(Solicitud).where(Solicitud.id_solicitud == articulo.id_solicitud)
    )
    solicitud = result_sol.scalar_one_or_none()
    if not solicitud:
        return None, PrestamoResumen(
            id=prestamo.id_prestamo,
            estado=estado_nombre,
            monto_prestamo=float(prestamo.monto_prestamo),
            deuda_actual=float(prestamo.deuda_actual),
            mora_acumulada=float(prestamo.mora_acumulada),
            interes_acumulada=float(prestamo.interes_acumulada),
        )

    # Usuario (cliente)
    result_user = await db.execute(
        select(User).where(User.ID_Usuario == solicitud.id_usuario)
    )
    usuario = result_user.scalar_one_or_none()

    cliente = None
    if usuario:
        cliente = ClienteResumen(
            id=usuario.ID_Usuario,
            nombre=usuario.Nombre,
            correo=usuario.Correo,
        )

    prestamo_resumen = PrestamoResumen(
        id=prestamo.id_prestamo,
        estado=estado_nombre,
        monto_prestamo=float(prestamo.monto_prestamo),
        deuda_actual=float(prestamo.deuda_actual),
        mora_acumulada=float(prestamo.mora_acumulada),
        interes_acumulada=float(prestamo.interes_acumulada),
    )

    return cliente, prestamo_resumen


# ============================================================
# GET /pagos - LISTADO CON FILTROS
# ============================================================
@router.get(
    "",
    response_model=PagoListResponse,
    summary="Listar pagos con filtros avanzados",
    description=(
        "Lista global de pagos con filtros opcionales. "
        "Solo accesible para roles ADMINISTRADOR, CAJERO o SUPERVISOR. "
        "\n\n**Filtros disponibles:**\n"
        "- estado, medio_pago, tipo_pago\n"
        "- id_prestamo, usuario_id (dueño del préstamo)\n"
        "- Rango de fechas (fecha_desde, fecha_hasta)\n"
        "- Búsqueda en ref_bancaria (ref_contains)\n"
        "\n**Ordenamiento:**\n"
        "- Por defecto: DESC por fecha_pago y id_pago\n"
        "- Parámetro `sort` puede ser 'asc' o 'desc'"
    )
)
async def listar_pagos(
    # Paginación
    limit: int = Query(50, ge=1, le=200, description="Cantidad máxima de resultados"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    sort: str = Query("desc", regex="^(asc|desc)$", description="Orden: asc o desc"),
    
    # Filtros de estado y forma de pago
    estado: Optional[str] = Query(None, description="Nombre del estado (ej: pendiente, validado)"),
    medio_pago: Optional[str] = Query(None, description="Medio de pago (ej: efectivo, transferencia, tarjeta)"),
    tipo_pago: Optional[str] = Query(None, description="Tipo de pago (ej: abono, total)"),
    
    # Filtros relacionales
    id_prestamo: Optional[int] = Query(None, ge=1, description="Filtrar por ID de préstamo"),
    usuario_id: Optional[int] = Query(None, ge=1, description="Filtrar por dueño del préstamo (cliente)"),
    
    # Filtros de fecha
    fecha_desde: Optional[str] = Query(None, description="Fecha inicio (YYYY-MM-DD)"),
    fecha_hasta: Optional[str] = Query(None, description="Fecha fin (YYYY-MM-DD)"),
    
    # Búsqueda en ref_bancaria
    ref_contains: Optional[str] = Query(None, max_length=60, description="Buscar en referencia bancaria"),
    
    # Dependencies
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista pagos con filtros avanzados y paginación.
    Incluye comprobantes, estado, resumen del préstamo y cliente.
    """
    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)

    tiene_permiso = await usuario_tiene_algun_rol(current_user, db, ROLES_LECTURA)
    if not tiene_permiso:
        raise HTTPException(
            status_code=403,
            detail=f"Requiere uno de estos roles: {', '.join(ROLES_LECTURA)}"
        )

    # 2) Parsear fechas
    f_desde = _parse_date(fecha_desde)
    f_hasta = _parse_date(fecha_hasta)

    # 3) Query base con JOINs necesarios
    stmt = (
        select(Pago)
        .join(EstadoPago, EstadoPago.id_estado_pago == Pago.id_estado, isouter=True)
    )

    # JOIN a Prestamo (siempre necesario para acceder a cliente)
    stmt = stmt.join(Prestamo, Prestamo.id_prestamo == Pago.id_prestamo, isouter=True)

    # Si filtro por usuario_id, necesitamos JOIN a Articulo → Solicitud
    if usuario_id is not None:
        stmt = stmt.join(
            Articulo, Articulo.id_articulo == Prestamo.id_articulo, isouter=True
        ).join(
            Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud, isouter=True
        )

    # 4) Aplicar filtros
    condiciones = []

    if estado:
        condiciones.append(func.lower(EstadoPago.nombre) == estado.lower())

    if medio_pago:
        condiciones.append(func.lower(Pago.medio_pago) == medio_pago.lower())

    if tipo_pago:
        condiciones.append(func.lower(Pago.tipo_pago) == tipo_pago.lower())

    if id_prestamo is not None:
        condiciones.append(Pago.id_prestamo == id_prestamo)

    if usuario_id is not None:
        condiciones.append(Solicitud.id_usuario == usuario_id)

    if f_desde is not None:
        condiciones.append(Pago.fecha_pago >= f_desde)

    if f_hasta is not None:
        condiciones.append(Pago.fecha_pago <= f_hasta)

    if ref_contains:
        # Búsqueda case-insensitive en ref_bancaria
        condiciones.append(
            func.lower(Pago.ref_bancaria).like(f"%{ref_contains.lower()}%")
        )

    if condiciones:
        stmt = stmt.where(and_(*condiciones))

    # 5) Total (antes de paginar)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    result_count = await db.execute(count_stmt)
    total = result_count.scalar() or 0

    # 6) Ordenamiento
    if sort == "asc":
        stmt = stmt.order_by(Pago.fecha_pago.asc(), Pago.id_pago.asc())
    else:
        stmt = stmt.order_by(Pago.fecha_pago.desc(), Pago.id_pago.desc())

    # 7) Paginación
    stmt = stmt.limit(limit).offset(offset)

    # 8) Ejecutar query
    result = await db.execute(stmt)
    pagos = result.scalars().all()

    # 9) Construir respuesta con comprobantes y resúmenes
    items: List[PagoListItemOut] = []

    for pago in pagos:
        # Estado del pago
        result_estado = await db.execute(
            select(EstadoPago).where(EstadoPago.id_estado_pago == pago.id_estado)
        )
        estado_pago = result_estado.scalar_one_or_none()
        estado_nombre = estado_pago.nombre if estado_pago else "desconocido"

        # Comprobantes
        comprobantes = await _cargar_comprobantes(db, pago.id_pago)

        # Cliente y préstamo
        cliente, prestamo_resumen = await _cargar_cliente_prestamo(db, pago.id_prestamo)

        items.append(
            PagoListItemOut(
                id_pago=pago.id_pago,
                id_prestamo=pago.id_prestamo,
                id_estado=pago.id_estado,
                estado=estado_nombre,
                fecha_pago=pago.fecha_pago.isoformat() if pago.fecha_pago else None,
                monto=float(pago.monto),
                tipo_pago=pago.tipo_pago,
                medio_pago=pago.medio_pago,
                ref_bancaria=pago.ref_bancaria,
                comprobantes=comprobantes,
                prestamo=prestamo_resumen,
                cliente=cliente,
            )
        )

    return PagoListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================
# GET /pagos/{id_pago} - DETALLE
# ============================================================
@router.get(
    "/{id_pago}",
    response_model=PagoDetalleOut,
    summary="Obtener detalle de un pago",
    description=(
        "Devuelve información completa de un pago específico. "
        "Incluye comprobantes, estado, resumen del préstamo y datos del cliente. "
        "Solo accesible para roles ADMINISTRADOR, CAJERO o SUPERVISOR."
    )
)
async def obtener_pago(
    id_pago: int = Path(..., ge=1, description="ID del pago"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtiene el detalle completo de un pago.
    Mismo shape que items del listado pero como objeto único.
    """
    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)

    tiene_permiso = await usuario_tiene_algun_rol(current_user, db, ROLES_LECTURA)
    if not tiene_permiso:
        raise HTTPException(
            status_code=403,
            detail=f"Requiere uno de estos roles: {', '.join(ROLES_LECTURA)}"
        )

    # 2) Cargar pago
    result = await db.execute(
        select(Pago).where(Pago.id_pago == id_pago)
    )
    pago = result.scalar_one_or_none()
    if not pago:
        raise HTTPException(status_code=404, detail=f"Pago {id_pago} no encontrado")

    # 3) Estado del pago
    result_estado = await db.execute(
        select(EstadoPago).where(EstadoPago.id_estado_pago == pago.id_estado)
    )
    estado_pago = result_estado.scalar_one_or_none()
    estado_nombre = estado_pago.nombre if estado_pago else "desconocido"

    # 4) Comprobantes
    comprobantes = await _cargar_comprobantes(db, pago.id_pago)

    # 5) Cliente y préstamo
    cliente, prestamo_resumen = await _cargar_cliente_prestamo(db, pago.id_prestamo)

    # 6) Respuesta
    return PagoDetalleOut(
        id_pago=pago.id_pago,
        id_prestamo=pago.id_prestamo,
        id_estado=pago.id_estado,
        estado=estado_nombre,
        fecha_pago=pago.fecha_pago.isoformat() if pago.fecha_pago else None,
        monto=float(pago.monto),
        tipo_pago=pago.tipo_pago,
        medio_pago=pago.medio_pago,
        ref_bancaria=pago.ref_bancaria,
        comprobantes=comprobantes,
        prestamo=prestamo_resumen,
        cliente=cliente,
    )