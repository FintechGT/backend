# app/api/routers/pagos.py
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.pagos import PagoListItemOut, PagoListResponse, PagoComprobanteOut

# 🔥 Importa las CLASES directamente desde tus submódulos
from app.db.models.prestamo import Prestamo
from app.db.models.pago import Pago
from app.db.models.comprobante import Comprobante  # Comprobante de pago

router = APIRouter(prefix="/prestamos", tags=["Pagos"])

@router.get(
    "/{id_prestamo}/pagos",
    response_model=PagoListResponse,
    summary="Listar pagos de un préstamo",
    description="Devuelve los pagos asociados a un préstamo (ordenados por fecha_pago DESC) e incluye comprobantes.",
)
async def listar_pagos_de_prestamo(
    id_prestamo: int = Path(..., ge=1, description="ID del préstamo"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    # 1) Verifica que el préstamo exista
    res = await db.execute(
        select(Prestamo).where(Prestamo.id_prestamo == id_prestamo)
    )
    prestamo = res.scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    # 2) Total de pagos del préstamo
    res = await db.execute(
        select(func.count(Pago.id_pago)).where(Pago.id_prestamo == id_prestamo)
    )
    total = res.scalar() or 0

    # 3) Pagos paginados (ORDENADOS por fecha_pago DESC; si no hay fecha, por id_pago DESC)
    order_col = getattr(Pago, "fecha_pago", Pago.id_pago)
    res = await db.execute(
        select(Pago)
        .where(Pago.id_prestamo == id_prestamo)
        .order_by(order_col.desc())
        .limit(limit)
        .offset(offset)
    )
    pagos = res.scalars().all()

    # 4) Comprobantes en bloque (tabla Comprobante)
    comps_map: Dict[int, List[PagoComprobanteOut]] = {}
    if pagos:
        ids = [p.id_pago for p in pagos]
        res = await db.execute(
            select(Comprobante).where(Comprobante.id_pago.in_(ids))
        )
        for c in res.scalars().all():
            comps_map.setdefault(c.id_pago, []).append(
                PagoComprobanteOut(
                    id_comprobante=c.id_comprobante,
                    url=str(c.imagen),         # ← tu columna real
                    descripcion=None,          # no tienes descripción
                )
            )

    # 5) Construir respuesta
    items: List[PagoListItemOut] = []
    for p in pagos:
        items.append(
            PagoListItemOut(
                id_pago=p.id_pago,
                id_prestamo=p.id_prestamo,
                id_estado=p.id_estado,
                id_validador=p.id_validador,
                fecha_pago=(p.fecha_pago.isoformat() if getattr(p, "fecha_pago", None) else None),
                monto=float(p.monto),
                tipo_pago=p.tipo_pago,
                medio_pago=p.medio_pago,
                ref_bancaria=p.ref_bancaria,
                comprobantes=comps_map.get(p.id_pago, []),
            )
        )

    return PagoListResponse(items=items, total=total)
