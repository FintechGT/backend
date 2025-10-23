# app/api/routers/prestamos_listado.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from types import SimpleNamespace
from datetime import date, datetime
from typing import Optional, List

from app.db.database import get_db
from app.core.security import get_current_user

from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.solicitud import Solicitud

from app.schemas.prestamos import (
    PrestamoItemOut, PrestamoListOut,
    PrestamoCreateIn, PrestamoCreateOut
)
from app.utils.roles import usuario_tiene_algun_rol

router = APIRouter(prefix="/prestamos", tags=["Préstamos"])

ADMIN_LIKE_ROLES = ["admin", "administrador", "operador", "cobrador"]
CREATOR_ROLES    = ["admin", "administrador", "valuador", "operador"]

# Alias de TABLA para Estado_Prestamo (usar nombres reales de columnas)
EPt = EstadoPrestamo.__table__.alias("ep")


# ---------- Utils ----------
def _uid(user) -> int:
    for a in ("id_usuario", "id", "user_id", "usuario_id", "ID_Usuario"):
        if hasattr(user, a) and getattr(user, a) is not None:
            return int(getattr(user, a))
    raise AttributeError("Usuario sin id compatible.")

def _as_roles_user(user):
    return user if hasattr(user, "id_usuario") and user.id_usuario is not None else SimpleNamespace(id_usuario=_uid(user))

async def _is_admin_like(user, db: AsyncSession) -> bool:
    return await usuario_tiene_algun_rol(_as_roles_user(user), db, ADMIN_LIKE_ROLES)

def _parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except Exception:
        raise HTTPException(status_code=400, detail="Fecha inválida (usar YYYY-MM-DD).")

def _prestamo_to_item(p: Prestamo, estado_id: Optional[int], estado_nombre: Optional[str]) -> PrestamoItemOut:
    return PrestamoItemOut(
        id_prestamo=p.id_prestamo,
        id_articulo=p.id_articulo,
        id_usuario_evaluador=p.id_usuario_evaluador,
        estado={"id": estado_id, "nombre": estado_nombre or "desconocido"},
        fecha_inicio=p.fecha_inicio,
        fecha_vencimiento=p.fecha_vencimiento,
        monto_prestamo=p.monto_prestamo,
        deuda_actual=p.deuda_actual,
        mora_acumulada=p.mora_acumulada,
        interes_acumulada=p.interes_acumulada,
        ultimo_calculo_en=p.ultimo_calculo_en,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )

def _q_ident(db: AsyncSession):
    """
    Devuelve una función para citar identificadores según el motor:
    - MySQL: `backticks`
    - Otros (Postgres, etc.): "comillas dobles"
    """
    dialect = getattr(getattr(db, "bind", None), "dialect", None)
    name = getattr(dialect, "name", "").lower() if dialect else ""
    if name == "mysql":
        return lambda x: f"`{x}`"
    else:
        return lambda x: f'"{x}"'


# ---------- GET /prestamos  y  GET /prestamos/listado ----------
@router.get("", response_model=PrestamoListOut)
@router.get("/listado", response_model=PrestamoListOut)
async def listar_prestamos(
    estado: Optional[str] = Query(None, description="Filtro por Estado_Prestamo.Nombre (ej. activo, en_mora_parcial)"),
    usuario_id: Optional[int] = Query(None, description="Dueño de la Solicitud (solo admins/operadores)"),
    id_articulo: Optional[int] = Query(None),
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
    vencimiento_antes: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort: str = Query("desc", regex="^(asc|desc)$"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    es_admin = await _is_admin_like(current_user, db)
    f_desde = _parse_date(fecha_desde)
    f_hasta = _parse_date(fecha_hasta)
    f_venc  = _parse_date(vencimiento_antes)

    # Base SELECT con LEFT JOIN a Estado_Prestamo (alias de TABLA)
    base = (
        select(
            Prestamo,
            EPt.c.Id_Estado_Prestamo.label("estado_id"),
            EPt.c.Nombre.label("estado_nombre"),
        )
        .join(EPt, EPt.c.Id_Estado_Prestamo == Prestamo.id_estado, isouter=True)
    )

    conds = []
    if estado:
        conds.append(func.lower(EPt.c.Nombre).like(f"%{estado.lower()}%"))
    if id_articulo is not None:
        conds.append(Prestamo.id_articulo == id_articulo)
    if f_desde is not None:
        conds.append(Prestamo.fecha_inicio >= f_desde)
    if f_hasta is not None:
        conds.append(Prestamo.fecha_inicio <= f_hasta)
    if f_venc is not None:
        conds.append(Prestamo.fecha_vencimiento < f_venc)

    # Visibilidad por rol
    if es_admin:
        if usuario_id is not None:
            base = base.join(Articulo, Articulo.id_articulo == Prestamo.id_articulo) \
                       .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
            conds.append(Solicitud.id_usuario == usuario_id)
    else:
        base = base.join(Articulo, Articulo.id_articulo == Prestamo.id_articulo) \
                   .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        conds.append(Solicitud.id_usuario == _uid(current_user))

    if conds:
        base = base.where(and_(*conds))

    # Total con mismos filtros
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    # Orden por Created_At (mapeado a created_at)
    order_col = Prestamo.created_at
    base = base.order_by(order_col.desc() if sort == "desc" else order_col.asc()) \
               .limit(limit).offset(offset)

    rows = (await db.execute(base)).all()
    items: List[PrestamoItemOut] = [
        _prestamo_to_item(p=row[0], estado_id=row.estado_id, estado_nombre=row.estado_nombre)
        for row in rows
    ]
    return PrestamoListOut(items=items, total=total, limit=limit, offset=offset)


# ---------- POST /prestamos  y  POST /prestamos/crear ----------
@router.post("", response_model=PrestamoCreateOut, status_code=status.HTTP_201_CREATED)
@router.post("/crear", response_model=PrestamoCreateOut, status_code=status.HTTP_201_CREATED)
async def crear_prestamo(
    payload: PrestamoCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Permisos
    if not await usuario_tiene_algun_rol(_as_roles_user(current_user), db, CREATOR_ROLES):
        raise HTTPException(status_code=403, detail="Sin permiso para crear préstamo manual.")

    # Validaciones básicas
    if payload.fecha_vencimiento <= payload.fecha_inicio:
        raise HTTPException(status_code=400, detail="La fecha de vencimiento debe ser posterior a la de inicio.")
    try:
        if payload.monto_prestamo is None or float(payload.monto_prestamo) <= 0:
            raise HTTPException(status_code=400, detail="monto_prestamo debe ser > 0.")
    except Exception:
        raise HTTPException(status_code=400, detail="monto_prestamo inválido.")

    # Verificar artículo existente
    art = (await db.execute(
        select(Articulo).where(Articulo.id_articulo == payload.id_articulo)
    )).scalar_one_or_none()
    if not art:
        raise HTTPException(status_code=404, detail="Artículo no encontrado.")

    # Validar que artículo esté en estado 'evaluado' (SQL crudo, con quoting según motor)
    q = _q_ident(db)

    # Opción robusta: obtener el Id_Estado_Articulo para 'evaluado' y compararlo en Articulo
    estado_eval_sql = text(f"""
        SELECT ea.{q('Id_Estado_Articulo')}
          FROM {q('Estado_Articulo')} ea
         WHERE LOWER(ea.{q('Nombre')}) = 'evaluado'
         LIMIT 1
    """)
    eval_row = (await db.execute(estado_eval_sql)).first()
    if not eval_row:
        raise HTTPException(status_code=500, detail="No existe estado 'evaluado' en Estado_Articulo.")
    id_estado_evaluado = eval_row[0]

    art_estado_sql = text(f"""
        SELECT 1
          FROM {q('Articulo')} a
         WHERE a.{q('Id_articulo')} = :id_articulo
           AND a.{q('Id_Estado')} = :id_estado
         LIMIT 1
    """)
    ok = (await db.execute(art_estado_sql, {
        "id_articulo": payload.id_articulo,
        "id_estado": id_estado_evaluado
    })).first()
    if not ok:
        raise HTTPException(status_code=400, detail="El artículo no está en estado 'evaluado'.")

    # Validar que no exista otro préstamo activo (excluyendo finalizado/cancelado/rechazado)
    active_check = await db.execute(
        select(Prestamo)
        .join(EPt, EPt.c.Id_Estado_Prestamo == Prestamo.id_estado)
        .where(
            Prestamo.id_articulo == payload.id_articulo,
            func.lower(EPt.c.Nombre).notin_(("finalizado", "cancelado", "rechazado")),
        )
        .limit(1)
    )
    if active_check.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un préstamo activo para este artículo.")

    # Buscar estado 'aprobado_pendiente_entrega'
    ep_row = (await db.execute(
        select(EPt.c.Id_Estado_Prestamo, EPt.c.Nombre)
        .where(func.lower(EPt.c.Nombre) == "aprobado_pendiente_entrega")
    )).first()
    if not ep_row:
        raise HTTPException(status_code=500, detail="Estado 'aprobado_pendiente_entrega' no existe en Estado_Prestamo.")
    id_estado_aprobado, nombre_estado = ep_row

    # Crear préstamo (transacción)
    ahora = datetime.utcnow()
    async with db.begin():
        nuevo = Prestamo(
            id_articulo=payload.id_articulo,
            id_usuario_evaluador=_uid(current_user),
            id_estado=id_estado_aprobado,
            fecha_inicio=payload.fecha_inicio,
            fecha_vencimiento=payload.fecha_vencimiento,
            monto_prestamo=payload.monto_prestamo,
            deuda_actual=0,
            mora_acumulada=0,
            interes_acumulada=0,
            created_at=ahora,
            updated_at=ahora,
        )
        db.add(nuevo)
        await db.flush()   # para obtener id_prestamo
        # (Opcional) asegurar 'evaluado' en artículo (idempotente)
        await db.execute(text(f"""
            UPDATE {q('Articulo')}
               SET {q('Id_Estado')} = :id_estado
             WHERE {q('Id_articulo')} = :id_articulo
        """), {"id_estado": id_estado_evaluado, "id_articulo": payload.id_articulo})
        await db.refresh(nuevo)

    return PrestamoCreateOut(
        id_prestamo=nuevo.id_prestamo,
        id_articulo=nuevo.id_articulo,
        estado=nombre_estado,
        mensaje="Préstamo creado exitosamente. Falta ingresar artículo a oficina para desembolsar."
    )
