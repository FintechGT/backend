from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.database import get_db
from app.db.models.user import User
from app.db.models.roles import Rol
from app.db.models.usuario_rol import UsuarioRol
from app.db.models.modulo import Modulo
from app.db.models.permiso import Permiso
from app.db.models.rol_permiso import RolPermiso

from app.schemas.acl_admin import (
    AdminModuloCreate, AdminModuloUpdate, AdminModuloOut,
    AdminPermisoCreate, AdminPermisoUpdate, AdminPermisoOut,
    RolPermisoAssignIn, RolPermisoOut,
)

router = APIRouter(prefix="/acl-admin", tags=["acl-admin"])

# ===== Auth local (evita ciclo con security.py)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    user = (await db.execute(select(User).where(User.ID_Usuario == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user

# ===== Roles: ADMIN/SUPERVISOR
async def _user_has_role(db: AsyncSession, id_usuario: int, role_name: str) -> bool:
    q = (
        select(func.count())
        .select_from(UsuarioRol)
        .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
        .where(UsuarioRol.id_usuario == id_usuario, Rol.nombre == role_name, Rol.activo.is_(True))
    )
    return (await db.scalar(q) or 0) > 0

async def _require_admin(user: User, db: AsyncSession):
    if not await _user_has_role(db, user.ID_Usuario, "ADMINISTRADOR"):
        raise HTTPException(status_code=403, detail="Se requiere rol ADMINISTRADOR.")

async def _require_read(user: User, db: AsyncSession):
    if await _user_has_role(db, user.ID_Usuario, "ADMINISTRADOR"):
        return
    if await _user_has_role(db, user.ID_Usuario, "SUPERVISOR"):
        return
    raise HTTPException(status_code=403, detail="Se requiere rol SUPERVISOR o ADMINISTRADOR.")

# ==========================
# MÓDULOS (CRUD ADMIN / READ SUPERVISOR)
# ==========================
@router.get("/modulos", response_model=list[AdminModuloOut])
async def listar_modulos(
    activo: Optional[bool] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_read(user, db)
    stmt = select(Modulo).order_by(Modulo.id_modulo.desc())
    if activo is not None:
        stmt = stmt.where(Modulo.activo == activo)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Modulo.nombre).like(like))
    rows = (await db.execute(stmt)).scalars().all()
    return [AdminModuloOut.model_validate(r) for r in rows]

@router.post("/modulos", response_model=AdminModuloOut, status_code=status.HTTP_201_CREATED)
async def crear_modulo(
    data: AdminModuloCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    obj = Modulo(
        nombre=data.nombre.strip(),
        descripcion=(data.descripcion or None),
        ruta=(data.ruta or None),
        activo=data.activo,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return AdminModuloOut.model_validate(obj)

@router.patch("/modulos/{id_modulo}", response_model=AdminModuloOut)
async def actualizar_modulo(
    id_modulo: int,
    data: AdminModuloUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    obj = await db.get(Modulo, id_modulo)
    if not obj:
        raise HTTPException(status_code=404, detail="Módulo no encontrado.")
    if data.nombre is not None: obj.nombre = data.nombre.strip()
    if data.descripcion is not None: obj.descripcion = data.descripcion or None
    if data.ruta is not None: obj.ruta = data.ruta or None
    if data.activo is not None: obj.activo = data.activo
    await db.commit(); await db.refresh(obj)
    return AdminModuloOut.model_validate(obj)

@router.delete("/modulos/{id_modulo}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_modulo(
    id_modulo: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    obj = await db.get(Modulo, id_modulo)
    if not obj:
        raise HTTPException(status_code=404, detail="Módulo no encontrado.")
    await db.delete(obj); await db.commit()
    return

# ==========================
# PERMISOS (CRUD ADMIN / READ SUPERVISOR)
# ==========================
@router.get("/permisos", response_model=list[AdminPermisoOut])
async def listar_permisos(
    id_modulo: Optional[int] = Query(default=None),
    activo: Optional[bool] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_read(user, db)
    stmt = select(Permiso, Modulo.nombre.label("modulo_nombre")).join(Modulo, Modulo.id_modulo == Permiso.id_modulo)
    if id_modulo is not None:
        stmt = stmt.where(Permiso.id_modulo == id_modulo)
    if activo is not None:
        stmt = stmt.where(Permiso.activo == activo)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Permiso.codigo).like(like))
    stmt = stmt.order_by(Permiso.id_permiso.desc())
    rows = (await db.execute(stmt)).all()
    out = []
    for p, modulo_nombre in rows:
        item = AdminPermisoOut.model_validate(p)
        item.modulo_nombre = modulo_nombre
        out.append(item)
    return out

@router.post("/permisos", response_model=AdminPermisoOut, status_code=status.HTTP_201_CREATED)
async def crear_permiso(
    data: AdminPermisoCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    if not await db.get(Modulo, data.id_modulo):
        raise HTTPException(status_code=404, detail="Módulo no encontrado.")

    dup = (await db.execute(
        select(Permiso).where((Permiso.id_modulo == data.id_modulo) & (Permiso.id_accion == int(data.id_accion)))
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="Ya existe un permiso para ese módulo y acción.")

    obj = Permiso(
        id_modulo=data.id_modulo,
        id_accion=int(data.id_accion),
        codigo=data.codigo.strip(),
        descripcion=(data.descripcion or None),
        activo=data.activo,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto de unicidad (código o par módulo/acción).")
    await db.refresh(obj)

    modulo_nombre = (await db.execute(select(Modulo.nombre).where(Modulo.id_modulo == obj.id_modulo))).scalar_one_or_none()
    out = AdminPermisoOut.model_validate(obj); out.modulo_nombre = modulo_nombre
    return out

@router.patch("/permisos/{id_permiso}", response_model=AdminPermisoOut)
async def actualizar_permiso(
    id_permiso: int,
    data: AdminPermisoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    obj = await db.get(Permiso, id_permiso)
    if not obj:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")

    if data.id_modulo is not None:
        if not await db.get(Modulo, data.id_modulo):
            raise HTTPException(status_code=404, detail="Módulo no encontrado.")
        obj.id_modulo = data.id_modulo
    if data.id_accion is not None:
        obj.id_accion = int(data.id_accion)
    if data.codigo is not None:
        obj.codigo = data.codigo.strip()
    if data.descripcion is not None:
        obj.descripcion = data.descripcion or None
    if data.activo is not None:
        obj.activo = data.activo

    dup = (await db.execute(
        select(Permiso).where(
            (Permiso.id_modulo == obj.id_modulo) & (Permiso.id_accion == obj.id_accion) & (Permiso.id_permiso != obj.id_permiso)
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="Ya existe un permiso para ese módulo y acción.")

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto de unicidad (código o par módulo/acción).")
    await db.refresh(obj)

    modulo_nombre = (await db.execute(select(Modulo.nombre).where(Modulo.id_modulo == obj.id_modulo))).scalar_one_or_none()
    out = AdminPermisoOut.model_validate(obj); out.modulo_nombre = modulo_nombre
    return out

@router.delete("/permisos/{id_permiso}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_permiso(
    id_permiso: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    obj = await db.get(Permiso, id_permiso)
    if not obj:
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")
    await db.delete(obj); await db.commit()
    return

# ==========================
# ROL ⇄ PERMISO (ADMIN)
# ==========================
@router.get("/roles/{id_rol}/permisos", response_model=list[str])
async def listar_permisos_de_rol(
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_read(user, db)
    stmt = (
        select(Permiso.codigo)
        .select_from(RolPermiso)
        .join(Permiso, Permiso.id_permiso == RolPermiso.id_permiso)
        .where(RolPermiso.id_rol == id_rol, RolPermiso.otorgado.is_(True))
        .order_by(Permiso.codigo.asc())
    )
    return [c for (c,) in (await db.execute(stmt)).all()]

@router.post("/roles/{id_rol}/permisos", response_model=RolPermisoOut, status_code=status.HTTP_201_CREATED)
async def asignar_permiso_a_rol(
    id_rol: int,
    data: RolPermisoAssignIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    if not await db.get(Rol, id_rol):
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    if not await db.get(Permiso, data.id_permiso):
        raise HTTPException(status_code=404, detail="Permiso no encontrado.")

    link = (await db.execute(
        select(RolPermiso).where(RolPermiso.id_rol == id_rol, RolPermiso.id_permiso == data.id_permiso)
    )).scalar_one_or_none()
    if link:
        link.otorgado = bool(data.otorgado)
    else:
        db.add(RolPermiso(id_rol=id_rol, id_permiso=data.id_permiso, otorgado=bool(data.otorgado)))
    await db.commit()

    stmt = (
        select(Permiso.codigo)
        .select_from(RolPermiso)
        .join(Permiso, Permiso.id_permiso == RolPermiso.id_permiso)
        .where(RolPermiso.id_rol == id_rol, RolPermiso.otorgado.is_(True))
        .order_by(Permiso.codigo.asc())
    )
    codigos = [c for (c,) in (await db.execute(stmt)).all()]
    return RolPermisoOut(id_rol=id_rol, permisos=codigos)

@router.delete("/roles/{id_rol}/permisos/{id_permiso}", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_permiso_de_rol(
    id_rol: int,
    id_permiso: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(user, db)
    link = (await db.execute(
        select(RolPermiso).where(RolPermiso.id_rol == id_rol, RolPermiso.id_permiso == id_permiso)
    )).scalar_one_or_none()
    if link:
        await db.delete(link); await db.commit()
    return
