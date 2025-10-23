# ============================================================
# app/api/routers/mis_prestamos_pagos.py
# ============================================================
from __future__ import annotations

from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.solicitud import Solicitud
from app.db.models.pago import Pago
from app.db.models.estado_pago import EstadoPago
from app.db.models.comprobante import Comprobante
from app.db.models.user import User

# Schemas
from app.schemas.mis_prestamos_pagos import (
    MiPrestamoItemOut,
    MisPrestamosListOut,
    MiPagoItemOut,
    MisPagosListOut,
    PagoComprobanteOut
)


router = APIRouter(prefix="/prestamos", tags=["Mis Préstamos y Pagos"])


# ============================================================
# Helpers
# ============================================================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


# ============================================================
# GET /prestamos/mis
# ============================================================
@router.get(
    "/mis",
    response_model=MisPrestamosListOut,
    summary="Listar mis préstamos (usuario autenticado)",
    description="Devuelve todos los préstamos asociados al usuario actual con paginación."
)
async def listar_mis_prestamos(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    estado: str | None = Query(None, description="Filtrar por estado (ej: activo, en_mora_parcial)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista préstamos del usuario autenticado.
    Filtra a través de: Prestamo → Articulo → Solicitud → Usuario
    """
    user_id = _resolve_user_id(current_user)

    # Base query con joins
    # Prestamo → Articulo → Solicitud (filtrar por id_usuario)
    stmt = (
        select(
            Prestamo,
            EstadoPrestamo.id_estado_prestamo.label("estado_id"),
            EstadoPrestamo.nombre.label("estado_nombre")
        )
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .join(EstadoPrestamo, EstadoPrestamo.id_estado_prestamo == Prestamo.id_estado, isouter=True)
        .where(Solicitud.id_usuario == user_id)
    )

    # Filtro opcional por estado
    if estado:
        stmt = stmt.where(func.lower(EstadoPrestamo.nombre).like(f"%{estado.lower()}%"))

    # Total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginación y orden
    stmt = stmt.order_by(Prestamo.created_at.desc()).limit(limit).offset(offset)

    # Ejecutar
    result = await db.execute(stmt)
    rows = result.all()

    # Construir respuesta
    items: List[MiPrestamoItemOut] = []
    for row in rows:
        prestamo = row[0]
        estado_id = row.estado_id
        estado_nombre = row.estado_nombre or "desconocido"

        items.append(
            MiPrestamoItemOut(
                id_prestamo=prestamo.id_prestamo,
                id_articulo=prestamo.id_articulo,
                estado={"id": estado_id, "nombre": estado_nombre},
                fecha_inicio=prestamo.fecha_inicio,
                fecha_vencimiento=prestamo.fecha_vencimiento,
                monto_prestamo=float(prestamo.monto_prestamo),
                deuda_actual=float(prestamo.deuda_actual),
                mora_acumulada=float(prestamo.mora_acumulada),
                interes_acumulada=float(prestamo.interes_acumulada),
                created_at=prestamo.created_at.isoformat() if prestamo.created_at else None,
                updated_at=prestamo.updated_at.isoformat() if prestamo.updated_at else None,
            )
        )

    return MisPrestamosListOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


# ============================================================
# GET /pagos/mis
# ============================================================
@router.get(
    "/pagos/mis",
    response_model=MisPagosListOut,
    summary="Listar mis pagos (usuario autenticado)",
    description="Devuelve todos los pagos de préstamos del usuario actual."
)
async def listar_mis_pagos(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    id_prestamo: int | None = Query(None, description="Filtrar por préstamo específico"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista pagos de préstamos del usuario autenticado.
    Filtra a través de: Pago → Prestamo → Articulo → Solicitud → Usuario
    """
    user_id = _resolve_user_id(current_user)

    # Base query
    stmt = (
        select(
            Pago,
            EstadoPago.nombre.label("estado_nombre")
        )
        .join(Prestamo, Prestamo.id_prestamo == Pago.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .join(EstadoPago, EstadoPago.id_estado_pago == Pago.id_estado, isouter=True)
        .where(Solicitud.id_usuario == user_id)
    )

    # Filtro opcional por préstamo
    if id_prestamo:
        stmt = stmt.where(Pago.id_prestamo == id_prestamo)

    # Total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginación y orden
    order_col = getattr(Pago, "fecha_pago", Pago.id_pago)
    stmt = stmt.order_by(order_col.desc()).limit(limit).offset(offset)

    # Ejecutar
    result = await db.execute(stmt)
    rows = result.all()

    # IDs de pagos para cargar comprobantes
    pago_ids = [row[0].id_pago for row in rows]

    # Cargar comprobantes en batch
    comps_map: Dict[int, List[PagoComprobanteOut]] = {}
    if pago_ids:
        comp_result = await db.execute(
            select(Comprobante).where(Comprobante.id_pago.in_(pago_ids))
        )
        for comp in comp_result.scalars().all():
            comps_map.setdefault(comp.id_pago, []).append(
                PagoComprobanteOut(
                    id_comprobante=comp.id_comprobante,
                    url=str(comp.imagen),
                    descripcion=None
                )
            )

    # Construir respuesta
    items: List[MiPagoItemOut] = []
    for row in rows:
        pago = row[0]
        estado_nombre = row.estado_nombre or "desconocido"

        items.append(
            MiPagoItemOut(
                id_pago=pago.id_pago,
                id_prestamo=pago.id_prestamo,
                estado=estado_nombre,
                fecha_pago=pago.fecha_pago.isoformat() if getattr(pago, "fecha_pago", None) else None,
                monto=float(pago.monto),
                tipo_pago=getattr(pago, "tipo_pago", None),
                medio_pago=getattr(pago, "medio_pago", None),
                ref_bancaria=getattr(pago, "ref_bancaria", None),
                comprobantes=comps_map.get(pago.id_pago, [])
            )
        )

    return MisPagosListOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )