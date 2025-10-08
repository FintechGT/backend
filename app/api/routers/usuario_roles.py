from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from app.db.database import get_db
from app.core.security import get_current_user


from app.db.models.roles import Rol
from app.db.models.usuario_rol import UsuarioRol

# Schemas
from app.schemas.roles import RolOut
from app.schemas.usuario_roles import RolesIdsIn

router = APIRouter(prefix="/usuarios", tags=["usuario_roles"])

# ============================================================
# LISTAR roles asignados a un usuario
# ============================================================
@router.get("/{id_usuario}/roles", response_model=list[RolOut])
async def listar_roles_de_usuario(
    id_usuario: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = (
        select(Rol)
        .join(UsuarioRol, and_(
            UsuarioRol.id_rol == Rol.id_rol,
            UsuarioRol.id_usuario == id_usuario
        ))
        .order_by(Rol.id_rol.asc())
    )
    roles = (await db.execute(stmt)).scalars().all()
    return roles

# ============================================================
# ASIGNAR roles a un usuario (bulk idempotente)
# ============================================================
@router.post("/{id_usuario}/roles", response_model=list[RolOut], status_code=status.HTTP_201_CREATED)
async def asignar_roles_a_usuario(
    id_usuario: int,
    data: RolesIdsIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not data.items:
        raise HTTPException(status_code=400, detail="No se enviaron roles.")

    # Validar que existan los roles
    rs_roles = await db.execute(select(Rol.id_rol).where(Rol.id_rol.in_(data.items)))
    existentes = set(rs_roles.scalars().all())
    faltantes = set(data.items) - existentes
    if faltantes:
        raise HTTPException(status_code=404, detail=f"Roles inexistentes: {sorted(faltantes)}")

    # Upsert manual: crea relación si no existe
    for id_rol in data.items:
        rs = await db.execute(
            select(UsuarioRol).where(
                UsuarioRol.id_usuario == id_usuario,
                UsuarioRol.id_rol == id_rol
            )
        )
        ur = rs.scalar_one_or_none()
        if not ur:
            db.add(UsuarioRol(id_usuario=id_usuario, id_rol=id_rol))

    await db.commit()

    # Devolver roles vigentes del usuario
    stmt = (
        select(Rol)
        .join(UsuarioRol, and_(
            UsuarioRol.id_rol == Rol.id_rol,
            UsuarioRol.id_usuario == id_usuario
        ))
        .order_by(Rol.id_rol.asc())
    )
    roles = (await db.execute(stmt)).scalars().all()
    return roles

# ============================================================
# QUITAR varios roles de un usuario (bulk)
# ============================================================
@router.delete("/{id_usuario}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_roles_de_usuario_bulk(
    id_usuario: int,
    data: RolesIdsIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if not data.items:
        return

    stmt = delete(UsuarioRol).where(
        UsuarioRol.id_usuario == id_usuario,
        UsuarioRol.id_rol.in_(data.items)
    )
    await db.execute(stmt)
    await db.commit()
    return  # 204

# ============================================================
# QUITAR un rol individual de un usuario
# ============================================================
@router.delete("/{id_usuario}/roles/{id_rol}", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_rol_de_usuario(
    id_usuario: int,
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = delete(UsuarioRol).where(
        UsuarioRol.id_usuario == id_usuario,
        UsuarioRol.id_rol == id_rol
    )
    await db.execute(stmt)
    await db.commit()
    return  # 204
