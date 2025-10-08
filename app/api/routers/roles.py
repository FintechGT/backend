# app/api/routers/roles.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user
from app.db.models.roles import Rol
from app.schemas.roles import RolCreate, RolUpdate, RolOut

router = APIRouter(prefix="/roles", tags=["roles"])


# ===========================
# LISTAR ROLES (con filtros)
# ===========================
@router.get("", response_model=list[RolOut])
async def listar_roles(
    q: str | None = Query(default=None, description="Buscar por nombre (contiene)"),
    activo: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Rol).order_by(Rol.id_rol.desc())
    if q:
        stmt = stmt.where(func.lower(Rol.nombre).like(f"%{q.lower()}%"))
    if activo is not None:
        stmt = stmt.where(Rol.activo == activo)

    stmt = stmt.limit(limit).offset(offset)
    objs = (await db.execute(stmt)).scalars().all()
    return objs


# ===========================
# OBTENER ROL POR ID
# ===========================
@router.get("/{id_rol}", response_model=RolOut)
async def obtener_rol(
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    obj = await db.get(Rol, id_rol)
    if not obj:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")
    return obj


# ===========================
# CREAR ROL
# ===========================
@router.post("", response_model=RolOut, status_code=status.HTTP_201_CREATED)
async def crear_rol(
    data: RolCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    # Unicidad por nombre (case-insensitive)
    dup_q = select(Rol).where(func.lower(Rol.nombre) == data.nombre.lower())
    if (await db.execute(dup_q)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre.")

    obj = Rol(
        nombre=data.nombre.strip(),
        descripcion=(data.descripcion or None),
        activo=data.activo,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto de unicidad (nombre de rol).") from e

    await db.refresh(obj)
    return obj


# ===========================
# ACTUALIZAR ROL (PATCH)
# ===========================
@router.patch("/{id_rol}", response_model=RolOut)
async def actualizar_rol(
    id_rol: int,
    data: RolUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    obj = await db.get(Rol, id_rol)
    if not obj:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")

    # nombre
    if data.nombre is not None:
        nombre_nuevo = data.nombre.strip()
        if nombre_nuevo and nombre_nuevo.lower() != (obj.nombre or "").lower():
            dup_q = select(Rol).where(func.lower(Rol.nombre) == nombre_nuevo.lower(), Rol.id_rol != id_rol)
            if (await db.execute(dup_q)).scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre.")
            obj.nombre = nombre_nuevo

    # descripcion
    if data.descripcion is not None:
        obj.descripcion = data.descripcion or None

    # activo
    if data.activo is not None:
        obj.activo = data.activo

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto de unicidad (nombre de rol).") from e

    await db.refresh(obj)
    return obj


# ===========================
# ELIMINAR ROL
# ===========================
@router.delete("/{id_rol}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_rol(
    id_rol: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    obj = await db.get(Rol, id_rol)
    if not obj:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")

    await db.delete(obj)
    await db.commit()
    return
