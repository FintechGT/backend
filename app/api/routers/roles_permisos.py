# app/api/routers/roles_permisos.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.permiso import Permiso
from app.db.models.rol_permiso import RolPermiso

# Schemas
from app.schemas.roles_permisos import (
    RolPermisoBulkIn,
    IdsPermisosIn,
    PermisosDeRolOut,
)


router = APIRouter(prefix="/roles", tags=["roles_permisos"])

# ============================================================
# LISTAR permisos asignados a un rol
# ============================================================
@router.get("/{id_rol}/permisos", response_model=list[PermisosDeRolOut])
async def listar_permisos_de_rol(
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Devuelve todos los permisos actualmente otorgados a un rol.
    """
    stmt = (
        select(Permiso)
        .join(RolPermiso, and_(
            RolPermiso.id_permiso == Permiso.id_permiso,
            RolPermiso.id_rol == id_rol,
            RolPermiso.otorgado == True  # noqa: E712
        ))
        .order_by(Permiso.id_permiso.asc())
    )
    permisos = (await db.execute(stmt)).scalars().all()
    return permisos


# ============================================================
# ASIGNAR / ACTUALIZAR permisos a un rol (bulk)
# ============================================================
@router.post("/{id_rol}/permisos", response_model=list[PermisosDeRolOut], status_code=status.HTTP_201_CREATED)
async def asignar_permisos_a_rol(
    id_rol: int,
    data: RolPermisoBulkIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Asigna o actualiza permisos a un rol.
    Si el permiso ya estaba asignado, actualiza su campo `otorgado`.
    """
    ids = [it.id_permiso for it in data.items]
    if not ids:
        raise HTTPException(status_code=400, detail="No se enviaron permisos.")

    # Validar que existan los permisos
    rs_perm = await db.execute(select(Permiso.id_permiso).where(Permiso.id_permiso.in_(ids)))
    existentes = set(rs_perm.scalars().all())
    faltantes = set(ids) - existentes
    if faltantes:
        raise HTTPException(status_code=404, detail=f"Permisos inexistentes: {sorted(faltantes)}")

    # Upsert manual
    for it in data.items:
        rs = await db.execute(
            select(RolPermiso).where(
                RolPermiso.id_rol == id_rol,
                RolPermiso.id_permiso == it.id_permiso,
            )
        )
        rp = rs.scalar_one_or_none()
        if rp:
            rp.otorgado = it.otorgado
        else:
            db.add(RolPermiso(id_rol=id_rol, id_permiso=it.id_permiso, otorgado=it.otorgado))

    await db.commit()

    # Retornar los permisos actualmente otorgados
    stmt = (
        select(Permiso)
        .join(RolPermiso, and_(
            RolPermiso.id_permiso == Permiso.id_permiso,
            RolPermiso.id_rol == id_rol,
            RolPermiso.otorgado == True  # noqa: E712
        ))
        .order_by(Permiso.id_permiso.asc())
    )
    permisos = (await db.execute(stmt)).scalars().all()
    return permisos


# ============================================================
# QUITAR varios permisos (bulk)
# ============================================================
@router.delete("/{id_rol}/permisos", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_permisos_de_rol_bulk(
    id_rol: int,
    data: IdsPermisosIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Elimina varios permisos de un rol según sus IDs.
    """
    if not data.items:
        return

    stmt = delete(RolPermiso).where(
        RolPermiso.id_rol == id_rol,
        RolPermiso.id_permiso.in_(data.items),
    )
    await db.execute(stmt)
    await db.commit()
    return


# ============================================================
# QUITAR un permiso individual
# ============================================================
@router.delete("/{id_rol}/permisos/{id_permiso}", status_code=status.HTTP_204_NO_CONTENT)
async def quitar_permiso_de_rol(
    id_rol: int,
    id_permiso: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Elimina un permiso específico asignado a un rol.
    """
    stmt = delete(RolPermiso).where(
        RolPermiso.id_rol == id_rol,
        RolPermiso.id_permiso == id_permiso,
    )
    await db.execute(stmt)
    await db.commit()
    return
