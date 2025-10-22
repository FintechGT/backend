# ============================================================
# app/api/routers/contratos_get.py
# ============================================================
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.contrato import Contrato
from app.db.models.prestamo import Prestamo
from app.db.models.articulo import Articulo
from app.db.models.solicitud import Solicitud
from app.db.models.user import User

# Utils (roles)
from app.utils.roles import usuario_tiene_algun_rol

# Schemas (sin modificar)
from app.schemas.contratos import (
    ContratoListItem,
    ContratoDetalle,
)

router = APIRouter(prefix="/contratos", tags=["Contratos (GET)"])


# ----------------- helpers -----------------
def _resolve_user_id(u: User) -> int:
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


async def _es_admin_valuador(user: User, db: AsyncSession) -> bool:
    return await usuario_tiene_algun_rol(user, db, ["ADMINISTRADOR", "VALUADOR"])


# ============================================================
# GET /contratos/mis
# ============================================================
@router.get(
    "/mis",
    response_model=list[ContratoListItem],
    summary="Listar mis contratos (del usuario autenticado)",
)
async def listar_mis_contratos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)

    # JOIN para filtrar por dueño (solicitud.id_usuario)
    stmt = (
        select(Contrato, Prestamo.id_prestamo, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Solicitud.id_usuario == user_id)
        .order_by(Contrato.id_contrato.desc())
    )
    rows = (await db.execute(stmt)).all()

    items: list[ContratoListItem] = []
    for row in rows:
        contrato: Contrato = row[0]
        items.append(
            ContratoListItem(
                id_contrato=contrato.id_contrato,
                id_prestamo=contrato.id_prestamo,
                url_pdf=contrato.url_pdf,
                hash_doc=contrato.hash_doc,
                firma_cliente_en=contrato.firma_cliente_en,
                firma_empresa_en=contrato.firma_empresa_en,
                created_at=getattr(contrato, "created_at", None),
                updated_at=getattr(contrato, "updated_at", None),
            )
        )
    return items


# ============================================================
# GET /contratos/{id_contrato}
# ============================================================
@router.get(
    "/{id_contrato}",
    response_model=ContratoDetalle,
    summary="Detalle de contrato (dueño o ADMIN/VALUADOR)",
)
async def obtener_contrato(
    id_contrato: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)

    # Traer contrato + owner
    stmt = (
        select(Contrato, Prestamo.id_prestamo, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Contrato.id_contrato == id_contrato)
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    contrato: Contrato = row[0]
    owner_id: int = row[2]

    # Autorización: dueño o admin/valuador
    if owner_id != user_id and not (await _es_admin_valuador(current_user, db)):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este contrato")

    return ContratoDetalle(
        id_contrato=contrato.id_contrato,
        id_prestamo=contrato.id_prestamo,
        url_pdf=contrato.url_pdf,
        hash_doc=contrato.hash_doc,
        firma_cliente_en=contrato.firma_cliente_en,
        firma_empresa_en=contrato.firma_empresa_en,
        owner_id=owner_id,
        created_at=getattr(contrato, "created_at", None),
        updated_at=getattr(contrato, "updated_at", None),
    )
