# app/api/routers/admin_usuarios.py
from __future__ import annotations

from typing import Optional, Dict, List, Tuple
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from passlib.hash import pbkdf2_sha256

from app.db.database import get_db
from app.core.security import get_current_user  # token → User

# MODELOS
from app.db.models.user import User
from app.db.models.roles import Rol
from app.db.models.usuario_rol import UsuarioRol
from app.db.models.auditoria import Auditoria
from app.db.models.permiso import Permiso
from app.db.models.rol_permiso import RolPermiso

# SCHEMAS
from app.schemas.admin_usuarios import (
    # listado
    UsuariosListResponse, UsuarioResumenOut,
    # patch estado
    UsuarioEstadoIn, UsuarioEstadoOut,
    # actividad
    ActividadResponse, UsuarioMiniOut, AuditoriaItemOut,
    # reset password
    ResetPasswordIn, ResetPasswordOut,
    # detalle
    UsuarioDetalleOut,
)

router = APIRouter(prefix="/admin/usuarios", tags=["admin-usuarios"])


# ============================================================
# Helpers de autorización
# ============================================================
async def _user_has_role(db: AsyncSession, id_usuario: int, role_name: str) -> bool:
    q = (
        select(func.count())
        .select_from(UsuarioRol)
        .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
        .where(UsuarioRol.id_usuario == id_usuario, Rol.nombre == role_name, Rol.activo.is_(True))
    )
    return (await db.scalar(q) or 0) > 0


async def _tiene_permiso(db: AsyncSession, id_usuario: int, codigo_permiso: str) -> bool:
    """
    Verifica permiso efectivo del usuario:
      1) Si tiene rol ADMINISTRADOR → True
      2) Roles → RolPermiso (otorgado) + Permiso activo
    """
    if await _user_has_role(db, id_usuario, "ADMINISTRADOR"):
        return True

    q = (
        select(func.count())
        .select_from(UsuarioRol)
        .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
        .join(RolPermiso, RolPermiso.id_rol == Rol.id_rol)
        .join(Permiso, Permiso.id_permiso == RolPermiso.id_permiso)
        .where(
            UsuarioRol.id_usuario == id_usuario,
            RolPermiso.otorgado.is_(True),
            Rol.activo.is_(True),
            Permiso.activo.is_(True),
            Permiso.codigo == codigo_permiso,
        )
    )
    return (await db.scalar(q) or 0) > 0


async def _requerir_permiso(db: AsyncSession, user: User, codigo_permiso: str):
    uid = getattr(user, "ID_Usuario", None) or getattr(user, "id_usuario", None) or getattr(user, "id", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Usuario inválido")
    if not await _tiene_permiso(db, int(uid), codigo_permiso):
        raise HTTPException(status_code=403, detail="No tienes permiso para esta operación.")


# ============================================================
# 1) LISTADO DE USUARIOS
# ============================================================
@router.get("", response_model=UsuariosListResponse)
async def listar_usuarios_admin(
    q: Optional[str] = Query(default=None, description="Busca por nombre/correo (LIKE %q%)"),
    activo: Optional[bool] = Query(default=None),
    rol: Optional[str] = Query(default=None, description="Nombre de rol o ID numérico"),
    verificado: Optional[bool] = Query(default=None),
    fecha_alta_from: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    fecha_alta_to: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    sort: Optional[str] = Query(default="fecha_alta", description="fecha_alta|nombre|correo|ultimo_login|actualizado"),
    dir: Optional[str] = Query(default="desc", description="asc|desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _requerir_permiso(db, user, "ADMIN_USUARIOS_LISTAR")

    stmt = select(User)

    # filtros
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.Nombre).like(like), func.lower(User.Correo).like(like)))
    if activo is not None:
        stmt = stmt.where(User.Estado_Activo == activo)
    if verificado is not None and hasattr(User, "Verificado"):
        stmt = stmt.where(User.Verificado == verificado)
    if fecha_alta_from:
        stmt = stmt.where(func.date(User.Created_At) >= fecha_alta_from)
    if fecha_alta_to:
        stmt = stmt.where(func.date(User.Created_At) <= fecha_alta_to)

    # por rol (nombre o id)
    if rol:
        try:
            rol_id = int(rol)
            stmt = (
                stmt.join(UsuarioRol, UsuarioRol.id_usuario == User.ID_Usuario)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(Rol.id_rol == rol_id)
            )
        except ValueError:
            stmt = (
                stmt.join(UsuarioRol, UsuarioRol.id_usuario == User.ID_Usuario)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(Rol.nombre == rol)
            )

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    # orden
    sort_map = {
        "fecha_alta": User.Created_At,
        "nombre": User.Nombre,
        "correo": User.Correo,
        "actualizado": User.Updated_At,
    }
    col = sort_map.get((sort or "fecha_alta").lower())
    if not col:
        raise HTTPException(status_code=400, detail="Parámetro sort inválido.")
    order_col = col.desc() if (dir or "desc").lower() == "desc" else col.asc()
    stmt = stmt.order_by(order_col).limit(limit).offset(offset)

    users: List[User] = (await db.execute(stmt)).scalars().all()

    # roles por usuario en batch
    uids = [u.ID_Usuario for u in users]
    roles_map: Dict[int, List[str]] = {uid: [] for uid in uids}
    if uids:
        rows = (
            await db.execute(
                select(UsuarioRol.id_usuario, Rol.nombre)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(UsuarioRol.id_usuario.in_(uids), Rol.activo.is_(True))
            )
        ).all()
        for uid, rname in rows:
            roles_map.setdefault(uid, []).append(rname)

    items: List[UsuarioResumenOut] = []
    for u in users:
        items.append(
            UsuarioResumenOut(
                id=u.ID_Usuario,
                nombre=u.Nombre,
                correo=u.Correo,
                estado_activo=bool(u.Estado_Activo),
                roles=sorted(roles_map.get(u.ID_Usuario, [])),
                ultimo_login=None,  # si manejas último login en otra tabla, ajústalo
                fecha_alta=u.Created_At.isoformat() if u.Created_At else "",
                actualizado=u.Updated_At.isoformat() if u.Updated_At else "",
            )
        )

    return UsuariosListResponse(total=int(total), items=items)


# ============================================================
# 2) DETALLE DE USUARIO
# ============================================================
@router.get("/{id_usuario}", response_model=UsuarioDetalleOut)
async def obtener_usuario_admin(
    id_usuario: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_LISTAR")

    obj = await db.get(User, id_usuario)
    if not obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    return UsuarioDetalleOut(
        id=obj.ID_Usuario,
        nombre=obj.Nombre,
        correo=obj.Correo,
        telefono=getattr(obj, "Telefono", None),
        direccion=getattr(obj, "Direccion", None),
        verificado=bool(getattr(obj, "Verificado", False)),
        estado_activo=bool(obj.Estado_Activo),
        created_at=obj.Created_At.isoformat() if obj.Created_At else None,
        updated_at=obj.Updated_At.isoformat() if obj.Updated_At else None,
    )


# ============================================================
# 3) ROLES DEL USUARIO / CATÁLOGO / ASIGNAR / QUITAR
# ============================================================
@router.get("/{id_usuario}/roles", response_model=list[str])
async def listar_roles_de_usuario(
    id_usuario: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_LISTAR")

    rows = (
        await db.execute(
            select(Rol.nombre)
            .join(UsuarioRol, UsuarioRol.id_rol == Rol.id_rol)
            .where(UsuarioRol.id_usuario == id_usuario, Rol.activo.is_(True))
            .order_by(Rol.nombre.asc())
        )
    ).all()
    return [r for (r,) in rows]


@router.get("/roles", response_model=list[dict])
async def listar_roles_disponibles(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_LISTAR")

    rows = (await db.execute(select(Rol).where(Rol.activo.is_(True)).order_by(Rol.nombre.asc()))).scalars().all()
    return [{"id_rol": r.id_rol, "nombre": r.nombre} for r in rows]


@router.post("/{id_usuario}/roles/{id_rol}", status_code=status.HTTP_204_NO_CONTENT)
async def asignar_rol_a_usuario(
    id_usuario: int,
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_EDITAR")

    if not await db.get(User, id_usuario):
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if not await db.get(Rol, id_rol):
        raise HTTPException(status_code=404, detail="Rol no encontrado.")

    link = (
        await db.execute(
            select(UsuarioRol).where(UsuarioRol.id_usuario == id_usuario, UsuarioRol.id_rol == id_rol)
        )
    ).scalar_one_or_none()
    if not link:
        db.add(UsuarioRol(id_usuario=id_usuario, id_rol=id_rol))
        await db.commit()
    return


@router.delete("/{id_usuario}/roles/{id_rol}", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_rol_de_usuario(
    id_usuario: int,
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_EDITAR")

    link = (
        await db.execute(
            select(UsuarioRol).where(UsuarioRol.id_usuario == id_usuario, UsuarioRol.id_rol == id_rol)
        )
    ).scalar_one_or_none()
    if link:
        await db.delete(link)
        await db.commit()
    return


# ============================================================
# 4) CAMBIAR ESTADO (activar / desactivar)
# ============================================================
@router.patch("/{id_usuario}/estado", response_model=UsuarioEstadoOut)
async def cambiar_estado_usuario(
    id_usuario: int = Path(..., ge=1),
    body: UsuarioEstadoIn = ...,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_EDITAR")

    # Bloquear auto-desactivarse
    if not body.estado_activo and getattr(admin, "ID_Usuario", None) == id_usuario:
        raise HTTPException(status_code=409, detail="No puedes desactivar tu propio usuario.")

    # Evitar dejar sin admins
    if not body.estado_activo:
        es_obj_admin = await _user_has_role(db, id_usuario, "ADMINISTRADOR")
        if es_obj_admin:
            admins_activos = await db.scalar(
                select(func.count())
                .select_from(User)
                .join(UsuarioRol, UsuarioRol.id_usuario == User.ID_Usuario)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(User.Estado_Activo.is_(True), Rol.nombre == "ADMINISTRADOR", Rol.activo.is_(True))
            )
            if (admins_activos or 0) <= 1:
                raise HTTPException(status_code=409, detail="No puedes desactivar al último ADMINISTRADOR activo.")

    obj = await db.get(User, id_usuario)
    if not obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    obj.Estado_Activo = bool(body.estado_activo)
    obj.Updated_At = datetime.utcnow()
    await db.commit()
    await db.refresh(obj)

    # Auditoría
    aud = Auditoria(
        id_usuario=getattr(admin, "ID_Usuario", None),
        accion="CAMBIO_ESTADO_USUARIO",
        modulo="AdminUsuarios",
        fecha_hora=datetime.utcnow(),
        detalle=f"id_usuario={id_usuario}, nuevo_estado={obj.Estado_Activo}",
        old_values='{"Estado_Activo": null}',
        new_values='{"Estado_Activo": %s}' % ("true" if obj.Estado_Activo else "false"),
    )
    db.add(aud)
    await db.commit()

    return UsuarioEstadoOut(
        id=obj.ID_Usuario, estado_activo=bool(obj.Estado_Activo), actualizado=obj.Updated_At.isoformat()
    )


# ============================================================
# 5) ACTIVIDAD / AUDITORÍA
# ============================================================
@router.get("/{id_usuario}/actividad", response_model=ActividadResponse)
async def actividad_usuario(
    id_usuario: int = Path(..., ge=1),
    modulo: Optional[str] = Query(default=None),
    accion: Optional[str] = Query(default=None),
    fecha_from: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    fecha_to: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    include_values: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_VER_ACTIVIDAD")

    # usuario mini
    obj = await db.get(User, id_usuario)
    if not obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    roles = [
        r for (r,) in (
            await db.execute(
                select(Rol.nombre)
                .select_from(UsuarioRol)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(UsuarioRol.id_usuario == id_usuario, Rol.activo.is_(True))
            )
        ).all()
    ]

    # consulta auditoría
    stmt = select(Auditoria).where(Auditoria.id_usuario == id_usuario)
    if modulo:
        stmt = stmt.where(Auditoria.modulo == modulo)
    if accion:
        stmt = stmt.where(Auditoria.accion == accion)
    if fecha_from:
        stmt = stmt.where(func.date(Auditoria.fecha_hora) >= fecha_from)
    if fecha_to:
        stmt = stmt.where(func.date(Auditoria.fecha_hora) <= fecha_to)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(Auditoria.fecha_hora.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    items: List[AuditoriaItemOut] = []
    for a in rows:
        items.append(
            AuditoriaItemOut(
                id_auditoria=a.id_auditoria,
                fecha_hora=a.fecha_hora.isoformat() if a.fecha_hora else "",
                modulo=a.modulo,
                accion=a.accion,
                detalle=a.detalle,
                old_values=(a.old_values if include_values else None),
                new_values=((a.new_values if include_values else None)),
            )
        )

    return ActividadResponse(
        usuario=UsuarioMiniOut(
            id=obj.ID_Usuario, nombre=obj.Nombre, correo=obj.Correo, roles=sorted(roles)
        ),
        total=int(total),
        items=items,
    )


# ============================================================
# 6) RESETEAR PASSWORD
# ============================================================
@router.post("/{id_usuario}/resetear-password", response_model=ResetPasswordOut)
async def resetear_password_usuario(
    id_usuario: int = Path(..., ge=1),
    body: ResetPasswordIn = ...,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_RESETEAR_PASSWORD")

    if getattr(admin, "ID_Usuario", None) == id_usuario:
        raise HTTPException(status_code=409, detail="No puedes resetear tu propia contraseña por este endpoint.")

    obj = await db.get(User, id_usuario)
    if not obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # genera hash temporal (no se devuelve la clave)
    temp_plain = f"tmp-{id_usuario}-{int(datetime.utcnow().timestamp())}"
    nuevo_hash = pbkdf2_sha256.hash(temp_plain)

    obj.Contrasena_hash = nuevo_hash
    obj.Token_version = (obj.Token_version or 0) + 1  # invalida JWTs vigentes
    obj.Updated_At = datetime.utcnow()

    await db.commit()
    await db.refresh(obj)

    # Auditoría
    aud = Auditoria(
        id_usuario=getattr(admin, "ID_Usuario", None),
        accion="RESETEAR_PASSWORD",
        modulo="AdminUsuarios",
        fecha_hora=datetime.utcnow(),
        detalle=f"id_usuario={id_usuario}, motivo={body.motivo or ''}",
        old_values=None,
        new_values='{"Token_version_rotated": true}',
    )
    db.add(aud)
    await db.commit()

    return ResetPasswordOut(
        id=obj.ID_Usuario,
        reset_ok=True,
        requires_password_change=True,
        mensaje="Se reseteó la contraseña y se invalidaron las sesiones activas.",
    )
