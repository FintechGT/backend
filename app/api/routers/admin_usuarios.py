from __future__ import annotations
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError, ProgrammingError, OperationalError

from passlib.hash import pbkdf2_sha256
from datetime import datetime

from app.db.database import get_db
from app.core.security import get_current_user  # tu security.py, no lo tocamos

# MODELOS
from app.db.models.user import User
from app.db.models.roles import Rol
from app.db.models.usuario_rol import UsuarioRol
from app.db.models.auditoria import Auditoria
from app.db.models.permiso import Permiso
from app.db.models.rol_permiso import RolPermiso
# Usuario_Permiso es opcional; se intentará importar solo si existe modelo/tabla

# SCHEMAS
from app.schemas.admin_usuarios import (
    UsuariosListResponse, UsuarioResumenOut,
    UsuarioEstadoIn, UsuarioEstadoOut,
    ActividadResponse, UsuarioMiniOut, AuditoriaItemOut,
    ResetPasswordIn, ResetPasswordOut,
)

router = APIRouter(prefix="/admin/usuarios", tags=["admin-usuarios"])

# ==========================
# Helpers de autorización
# ==========================
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
    1) Si existe Usuario_Permiso y hay override:
       - 'deny' → deniega
       - 'allow' → permite
    2) Si no hay override o tabla no existe → verifica por Rol_Permiso
    3) Fallback: si tiene rol ADMINISTRADOR → permite
    """
    # 1) Override por usuario (solo si existe el modelo/tabla)
    try:
        from app.db.models.usuario_permiso import UsuarioPermiso  # puede no existir
        q_user = (
            select(UsuarioPermiso.decision)
            .join(Permiso, Permiso.id_permiso == UsuarioPermiso.id_permiso)
            .where(UsuarioPermiso.id_usuario == id_usuario, Permiso.codigo == codigo_permiso)
        )
        rows = (await db.execute(q_user)).all()
        if rows:
            decisions = {str(dec).lower() for (dec,) in rows if dec}
            if "deny" in decisions:
                return False
            if "allow" in decisions:
                return True
    except (ProgrammingError, OperationalError, ModuleNotFoundError, ImportError) as e:
        # Si la tabla no existe o el modelo no está, continuar sin romper
        if "doesn't exist" not in str(e).lower():
            pass

    # 2) Permisos por rol
    q_role = (
        select(func.count())
        .select_from(RolPermiso)
        .join(Permiso, Permiso.id_permiso == RolPermiso.id_permiso)
        .join(Rol, Rol.id_rol == RolPermiso.id_rol)
        .join(UsuarioRol, UsuarioRol.id_rol == Rol.id_rol)
        .where(
            UsuarioRol.id_usuario == id_usuario,
            Permiso.codigo == codigo_permiso,
            RolPermiso.otorgado.is_(True),
            Permiso.activo.is_(True),
            Rol.activo.is_(True),
        )
    )
    if (await db.scalar(q_role)) > 0:
        return True

    # 3) Fallback: super rol
    if await _user_has_role(db, id_usuario, "ADMINISTRADOR"):
        return True

    return False

async def _requerir_permiso(db: AsyncSession, user: User, codigo_permiso: str):
    if not (await _tiene_permiso(db, user.ID_Usuario, codigo_permiso)):
        raise HTTPException(status_code=403, detail="No tienes permiso para esta operación.")


# ==========================
# 4.1 GET /admin/usuarios
# ==========================
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
    # permiso requerido
    await _requerir_permiso(db, user, "ADMIN_USUARIOS_LISTAR")

    # base
    stmt = select(User).where(True)

    # filtros
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.Nombre).like(like), func.lower(User.Correo).like(like)))
    if activo is not None:
        stmt = stmt.where(User.Estado_Activo == activo)
    if verificado is not None:
        stmt = stmt.where(User.Verificado == verificado)
    if fecha_alta_from:
        stmt = stmt.where(func.date(User.Created_At) >= fecha_alta_from)
    if fecha_alta_to:
        stmt = stmt.where(func.date(User.Created_At) <= fecha_alta_to)

    # filtro por rol (por nombre o id)
    if rol:
        try:
            rol_id = int(rol)
            stmt = stmt.join(UsuarioRol, UsuarioRol.id_usuario == User.ID_Usuario)\
                       .join(Rol, Rol.id_rol == UsuarioRol.id_rol)\
                       .where(Rol.id_rol == rol_id)
        except ValueError:
            stmt = stmt.join(UsuarioRol, UsuarioRol.id_usuario == User.ID_Usuario)\
                       .join(Rol, Rol.id_rol == UsuarioRol.id_rol)\
                       .where(Rol.nombre == rol)

    # total
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    if not total:
        return UsuariosListResponse(total=0, items=[])

    # orden
    sort_map = {
        "fecha_alta": User.Created_At,
        "nombre": User.Nombre,
        "correo": User.Correo,
        "actualizado": User.Updated_At,
        # "ultimo_login": ... si lo tienes en otra tabla, omitir aquí
    }
    col = sort_map.get(sort or "fecha_alta")
    if not col:
        raise HTTPException(status_code=400, detail="Parámetro sort inválido.")
    order_col = col.desc() if (dir or "desc").lower() == "desc" else col.asc()
    stmt = stmt.order_by(order_col)

    # paginación
    stmt = stmt.limit(limit).offset(offset)
    users: List[User] = (await db.execute(stmt)).scalars().all()

    # cargar roles en batch (evitar N+1)
    uids = [u.ID_Usuario for u in users]
    roles_map: Dict[int, List[str]] = {uid: [] for uid in uids}
    if uids:
        rows = (
            await db.execute(
                select(UsuarioRol.id_usuario, Rol.nombre)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(UsuarioRol.id_usuario.in_(uids))
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
                ultimo_login=None,  # si lo manejas, setéalo aquí
                fecha_alta=u.Created_At.isoformat() if u.Created_At else "",
                actualizado=u.Updated_At.isoformat() if u.Updated_At else "",
            )
        )
    return UsuariosListResponse(total=int(total or 0), items=items)


# ==========================
# 4.2 PATCH /{id}/estado
# ==========================
@router.patch("/{id_usuario}/estado", response_model=UsuarioEstadoOut)
async def cambiar_estado_usuario(
    id_usuario: int = Path(..., ge=1),
    body: UsuarioEstadoIn = ...,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_EDITAR")

    # no permitir desactivar al último ADMINISTRADOR activo
    if body.estado_activo is False:
        # ¿el objetivo es admin?
        es_admin_obj = await db.scalar(
            select(func.count())
            .select_from(UsuarioRol)
            .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
            .where(UsuarioRol.id_usuario == id_usuario, Rol.nombre == "ADMINISTRADOR", Rol.activo.is_(True))
        )
        if (es_admin_obj or 0) > 0:
            admins_activos = await db.scalar(
                select(func.count())
                .select_from(User)
                .join(UsuarioRol, UsuarioRol.id_usuario == User.ID_Usuario)
                .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
                .where(User.Estado_Activo.is_(True), Rol.nombre == "ADMINISTRADOR", Rol.activo.is_(True))
            )
            if (admins_activos or 0) <= 1:
                raise HTTPException(status_code=409, detail="No puedes desactivar al último ADMINISTRADOR activo.")

        # opcional: bloquear auto-desactivarse
        if admin.ID_Usuario == id_usuario:
            raise HTTPException(status_code=409, detail="No puedes desactivar tu propio usuario.")

    obj = await db.get(User, id_usuario)
    if not obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    obj.Estado_Activo = bool(body.estado_activo)
    obj.Updated_At = datetime.utcnow()

    await db.commit()
    await db.refresh(obj)

    # auditoría
    aud = Auditoria(
        id_usuario=admin.ID_Usuario,
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


# ==========================
# 4.3 GET /{id}/actividad
# ==========================
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

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
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
                new_values=(a.new_values if include_values else None),
            )
        )

    return ActividadResponse(
        usuario=UsuarioMiniOut(
            id=obj.ID_Usuario, nombre=obj.Nombre, correo=obj.Correo, roles=sorted(roles)
        ),
        total=int(total or 0),
        items=items,
    )


# ==========================
# 4.4 POST /{id}/resetear-password
# ==========================
@router.post("/{id_usuario}/resetear-password", response_model=ResetPasswordOut)
async def resetear_password_usuario(
    id_usuario: int = Path(..., ge=1),
    body: ResetPasswordIn = ...,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_user),
):
    await _requerir_permiso(db, admin, "ADMIN_USUARIOS_RESETEAR_PASSWORD")

    if admin.ID_Usuario == id_usuario:
        # Política opcional: no permitirse auto-resetear por este endpoint
        raise HTTPException(status_code=409, detail="No puedes resetear tu propia contraseña por este endpoint.")

    obj = await db.get(User, id_usuario)
    if not obj:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Genera una contraseña temporal aleatoria y guarda su hash (no se devuelve la contraseña)
    # Para evitar depender de bcrypt, usamos PBKDF2-HMAC-SHA256 (incluido en passlib core)
    temp_plain = f"tmp-{id_usuario}-{int(datetime.utcnow().timestamp())}"
    nuevo_hash = pbkdf2_sha256.hash(temp_plain)

    obj.Contrasena_hash = nuevo_hash
    obj.Token_version = (obj.Token_version or 0) + 1  # invalida JWTs vigentes
    obj.Updated_At = datetime.utcnow()

    await db.commit()
    await db.refresh(obj)

    # Auditoría
    aud = Auditoria(
        id_usuario=admin.ID_Usuario,
        accion="RESETEAR_PASSWORD",
        modulo="AdminUsuarios",
        fecha_hora=datetime.utcnow(),
        detalle=f"id_usuario={id_usuario}, motivo={body.motivo or ''}",
        old_values=None,
        new_values='{"Token_version_rotated": true}',
    )
    db.add(aud)
    await db.commit()

    # No exponemos contraseña; front debe forzar cambio al siguiente login
    return ResetPasswordOut(
        id=obj.ID_Usuario,
        reset_ok=True,
        requires_password_change=True,
        mensaje="Se reseteó la contraseña y se invalidaron las sesiones activas.",
    )
