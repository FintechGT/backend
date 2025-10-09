from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.permiso import Permiso
from app.schemas.permisos import PermisoCreate, PermisoOut, PermisosBulkIn
from app.core.security import get_current_user  # deja tu auth si aplica

router = APIRouter(prefix="/permisos", tags=["permisos"])


# ============================================================
# LISTAR PERMISOS
# ============================================================
@router.get("", response_model=list[PermisoOut])
async def listar_permisos(
    id_modulo: int | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = select(Permiso).order_by(Permiso.id_permiso.desc())
    if id_modulo is not None:
        stmt = stmt.where(Permiso.id_modulo == id_modulo)

    objs = (await db.execute(stmt)).scalars().all()
    return objs


# ============================================================
# CREAR PERMISO INDIVIDUAL
# ============================================================
@router.post("", response_model=PermisoOut, status_code=status.HTTP_201_CREATED)
async def crear_permiso(
    data: PermisoCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    # Validar unicidad (id_modulo + id_accion)
    dup_q = select(Permiso).where(
        Permiso.id_modulo == data.id_modulo,
        Permiso.id_accion == data.id_accion,
    )
    if (await db.execute(dup_q)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El módulo {data.id_modulo} ya tiene un permiso para la acción {data.id_accion}.",
        )

    obj = Permiso(
        id_modulo=data.id_modulo,
        id_accion=data.id_accion,
        codigo=data.codigo,
        descripcion=data.descripcion,
        activo=data.activo,
    )
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflicto de unicidad al crear el permiso."
        ) from e

    await db.refresh(obj)
    return obj


# ============================================================
# CREAR PERMISOS EN BLOQUE
# ============================================================
@router.post("/bulk", response_model=list[PermisoOut], status_code=status.HTTP_201_CREATED)
async def crear_permisos_bulk(
    data: PermisosBulkIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    # 1) Validar duplicados en el payload
    accs = [it.id_accion for it in data.items]
    if len(set(accs)) != len(accs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hay acciones repetidas dentro del payload para este módulo.",
        )

    # 2) Verificar existentes en la BD
    rs = await db.execute(
        select(Permiso.id_accion).where(
            Permiso.id_modulo == data.id_modulo,
            Permiso.id_accion.in_(accs),
        )
    )
    ya = set(rs.scalars().all())
    if ya:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existen para el módulo {data.id_modulo} las acciones: {sorted(ya)}",
        )

    # 3) Insertar en bloque
    objs = [
        Permiso(
            id_modulo=data.id_modulo,
            id_accion=it.id_accion,
            codigo=it.codigo,
            descripcion=it.descripcion,
            activo=it.activo,
        )
        for it in data.items
    ]
    db.add_all(objs)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflicto de unicidad al crear permisos en bloque (verifica índices únicos en la tabla).",
        ) from e

    for o in objs:
        await db.refresh(o)
    return objs


# ============================================================
# ELIMINAR PERMISOS POR MÓDULO (debe ir antes del DELETE por id)
# ============================================================
@router.delete("/modulo/{id_modulo}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_permisos_por_modulo(
    id_modulo: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    rs = await db.execute(select(Permiso).where(Permiso.id_modulo == id_modulo))
    objs = rs.scalars().all()

    # Idempotente: si no hay nada, 204 igual
    if not objs:
        return

    for obj in objs:
        await db.delete(obj)
    await db.commit()
    return


# ============================================================
# ELIMINAR PERMISO INDIVIDUAL
# ============================================================
@router.delete("/{id_permiso}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_permiso(
    id_permiso: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    obj = await db.get(Permiso, id_permiso)
    if not obj:
        # también puedes hacerlo idempotente si prefieres
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El permiso con ID {id_permiso} no existe.",
        )

    await db.delete(obj)
    await db.commit()
    return
