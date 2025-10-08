from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update
from typing import List, Optional

from app.db.database import get_db
from app.core.security import get_current_user
from app.db.models.modulo import Modulo
from app.schemas.modulos import ModuloIn, ModuloUpdate, ModuloOut

router = APIRouter(prefix="/modulos", tags=["modulos"])

@router.post("", response_model=ModuloOut, summary="Crear módulo (admin)")
async def crear_modulo(data: ModuloIn, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    dup = (await db.execute(select(Modulo).where(Modulo.nombre == data.nombre))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="El módulo ya existe")
    await db.execute(insert(Modulo).values(
        Nombre=data.nombre, Descripcion=data.descripcion, Ruta=data.ruta, Activo=data.activo
    ))
    await db.commit()
    creado = (await db.execute(select(Modulo).where(Modulo.nombre == data.nombre))).scalar_one()
    return creado

@router.get("", response_model=List[ModuloOut], summary="Listar módulos")
async def listar_modulos(
    activo: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    stmt = select(Modulo)
    if activo is not None:
        stmt = stmt.where(Modulo.activo == activo)
    rows = (await db.execute(stmt.order_by(Modulo.nombre.asc()))).scalars().all()
    return rows

@router.get("/{id_modulo}", response_model=ModuloOut, summary="Obtener módulo")
async def obtener_modulo(id_modulo: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    mod = (await db.execute(select(Modulo).where(Modulo.id_modulo == id_modulo))).scalar_one_or_none()
    if not mod:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    return mod

@router.patch("/{id_modulo}", response_model=ModuloOut, summary="Actualizar módulo (admin)")
async def actualizar_modulo(id_modulo: int, data: ModuloUpdate, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    exists = (await db.execute(select(Modulo).where(Modulo.id_modulo == id_modulo))).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    vals = {}
    if data.nombre is not None: vals["Nombre"] = data.nombre
    if data.descripcion is not None: vals["Descripcion"] = data.descripcion
    if data.ruta is not None: vals["Ruta"] = data.ruta
    if data.activo is not None: vals["Activo"] = data.activo
    if vals:
        await db.execute(update(Modulo).where(Modulo.id_modulo == id_modulo).values(**vals))
        await db.commit()
    actualizado = (await db.execute(select(Modulo).where(Modulo.id_modulo == id_modulo))).scalar_one()
    return actualizado

@router.delete("/{id_modulo}", summary="Eliminar módulo (soft delete, admin)")
async def eliminar_modulo(id_modulo: int, db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    exists = (await db.execute(select(Modulo).where(Modulo.id_modulo == id_modulo))).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    await db.execute(update(Modulo).where(Modulo.id_modulo == id_modulo).values(Activo=False))
    await db.commit()
    return {"ok": True}
