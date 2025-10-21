# SOLO APIRouter aquí (no crear FastAPI)
from typing import Any, Dict, Optional, List
from datetime import datetime, date, time, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, and_, or_, cast, Text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.routers.auth import get_current_user
from app.db.models.auditoria import Auditoria
from app.db.models.user import User
from app.schemas.auditoria import AuditoriaListOut, AuditoriaItem, UsuarioMini

router = APIRouter(prefix="/auditoria", tags=["Auditoría"])

# ---------------- Helpers ----------------
def _get_user_id(user: Any) -> int:
    for attr in ("id_usuario", "ID_Usuario", "id", "user_id", "usuario_id"):
        if hasattr(user, attr):
            val = getattr(user, attr)
            if val is not None:
                return int(val)
    raise HTTPException(status_code=500, detail="No se pudo determinar el id del usuario autenticado.")

def _parse_iso_any(dt_str: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    if not dt_str:
        return None
    s = dt_str.strip()
    try:
        if "T" not in s and len(s) == 10:
            d = date.fromisoformat(s)
            t = time(23, 59, 59, 999999) if end_of_day else time(0, 0, 0, 0)
            return datetime.combine(d, t).replace(tzinfo=timezone.utc)
        if s.endswith("Z"):
            s = s[:-1]
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        raise HTTPException(status_code=400, detail="Parámetro de fecha inválido (usar ISO-8601).")

def _to_json(val):
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(str(val))
    except Exception:
        return None

# ---------------- Endpoint requerido ----------------
# Registramos ambas rutas; solo /auditoria aparece en /docs.
@router.get("", response_model=AuditoriaListOut, include_in_schema=True, status_code=status.HTTP_200_OK)
@router.get("/", response_model=AuditoriaListOut, include_in_schema=False, status_code=status.HTTP_200_OK)
async def listar_auditoria(
    user_id: Optional[int] = Query(None, ge=1),
    modulo: Optional[str] = Query(None),
    accion: Optional[str] = Query(None),
    desde: Optional[str] = Query(None, description="YYYY-MM-DD o ISO-8601 (UTC)"),
    hasta: Optional[str] = Query(None, description="YYYY-MM-DD o ISO-8601 (UTC, inclusivo)"),
    q: Optional[str] = Query(None, description="Búsqueda libre en detalle y JSON"),
    sort: str = Query("-fecha_hora", description="fecha_hora|modulo|accion; prefijo - para DESC"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_user: bool = Query(False, description="Si true, devuelve usuario.nombre (JOIN liviano)"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
):
    _ = _get_user_id(current_user)  # mantiene requerimiento de usuario autenticado

    dt_desde = _parse_iso_any(desde, end_of_day=False)
    dt_hasta = _parse_iso_any(hasta, end_of_day=True)

    base = select(
        Auditoria.id_auditoria,
        Auditoria.id_usuario,
        Auditoria.modulo,
        Auditoria.accion,
        Auditoria.fecha_hora,
        Auditoria.detalle,
        Auditoria.old_values,
        Auditoria.new_values,
    )

    conds = []
    if user_id is not None:
        conds.append(Auditoria.id_usuario == user_id)
    if modulo:
        conds.append(func.lower(Auditoria.modulo) == modulo.lower())
    if accion:
        conds.append(func.lower(Auditoria.accion) == accion.lower())
    if dt_desde:
        conds.append(Auditoria.fecha_hora >= dt_desde)
    if dt_hasta:
        conds.append(Auditoria.fecha_hora <= dt_hasta)
    if q:
        like = f"%{q}%"
        conds.append(
            or_(
                Auditoria.detalle.ilike(like),
                cast(Auditoria.old_values, Text).ilike(like),
                cast(Auditoria.new_values, Text).ilike(like),
            )
        )
    if conds:
        base = base.where(and_(*conds))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    key = "fecha_hora"
    desc = True
    if sort:
        desc = sort.startswith("-")
        key = sort[1:] if desc else sort

    col = Auditoria.fecha_hora
    if key == "modulo":
        col = Auditoria.modulo
    elif key == "accion":
        col = Auditoria.accion

    query = base.order_by(col.desc() if desc else col.asc()).limit(limit).offset(offset)
    rows = (await db.execute(query)).all()

    nombres_por_usuario: Dict[int, str] = {}
    if include_user:
        ids = {r.id_usuario for r in rows if r.id_usuario is not None}
        if ids:
            q_users = select(User.id, User.nombre).where(User.id.in_(ids))
            user_rows = (await db.execute(q_users)).all()
            nombres_por_usuario = {u.id: u.nombre for u in user_rows}

    items: List[AuditoriaItem] = []
    for r in rows:
        usuario = None
        if r.id_usuario is not None:
            usuario = UsuarioMini(id=r.id_usuario, nombre=nombres_por_usuario.get(r.id_usuario))
        items.append(
            AuditoriaItem(
                id_auditoria=r.id_auditoria,
                usuario=usuario,
                modulo=r.modulo,
                accion=r.accion,
                fecha_hora=r.fecha_hora,
                detalle=r.detalle,
                old_values=_to_json(r.old_values),
                new_values=_to_json(r.new_values),
            )
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort or "-fecha_hora",
    }