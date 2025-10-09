from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.db.models import CatTipoArticulo, User, Articulo
from app.schemas.cat_tipo_articulo import (
    CatTipoArticuloCreate,
    CatTipoArticuloOut,
    CatTipoArticuloUpdate,
)
from app.core.security import get_current_user
from app.utils.roles import usuario_tiene_algun_rol
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/catalogos/tipo-articulo", tags=["Catalogos"])


@router.get("", response_model=list[CatTipoArticuloOut])
async def listar_tipos_articulo(db: AsyncSession = Depends(get_db)):
    """Listar todos los tipos de artículo disponibles."""
    result = await db.execute(select(CatTipoArticulo).order_by(CatTipoArticulo.nombre))
    tipos = result.scalars().all()
    return tipos


@router.get("/{id_tipo}", response_model=CatTipoArticuloOut)
async def obtener_tipo_articulo(id_tipo: int, db: AsyncSession = Depends(get_db)):
    """Obtener un tipo de artículo específico por su ID."""
    tipo = await db.get(CatTipoArticulo, id_tipo)
    if not tipo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tipo de artículo con id {id_tipo} no encontrado",
        )
    return tipo


@router.post("", response_model=CatTipoArticuloOut, status_code=status.HTTP_201_CREATED)
async def crear_tipo_articulo(
    payload: CatTipoArticuloCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crear un nuevo tipo de artículo. Requiere rol de ADMIN."""
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para esta acción")

    # Verificar duplicados por nombre (insensible a mayúsculas/minúsculas)
    result = await db.execute(select(CatTipoArticulo).where(func.lower(CatTipoArticulo.nombre) == payload.nombre.lower()))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El tipo de artículo '{payload.nombre}' ya existe.")

    nuevo_tipo = CatTipoArticulo(**payload.model_dump())
    db.add(nuevo_tipo)
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CAT_TIPO_ARTICULO_CREATE",
        modulo="Catalogos",
        detalle=f"nombre={nuevo_tipo.nombre}",
        valores_nuevos=nuevo_tipo,
    )

    await db.commit()
    await db.refresh(nuevo_tipo)
    return nuevo_tipo


@router.put("/{id_tipo}", response_model=CatTipoArticuloOut)
async def actualizar_tipo_articulo(
    id_tipo: int,
    payload: CatTipoArticuloUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizar un tipo de artículo existente. Requiere rol de ADMIN."""
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para esta acción")

    tipo = await db.get(CatTipoArticulo, id_tipo)
    if not tipo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tipo de artículo con id {id_tipo} no encontrado")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe proporcionar al menos un campo para actualizar")

    # Verificar duplicado si se cambia el nombre
    if 'nombre' in update_data and update_data['nombre'].lower() != tipo.nombre.lower():
        result = await db.execute(select(CatTipoArticulo).where(func.lower(CatTipoArticulo.nombre) == update_data['nombre'].lower()))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El nombre '{update_data['nombre']}' ya está en uso.")

    old_values = {"nombre": tipo.nombre, "descripcion": tipo.descripcion}

    for key, value in update_data.items():
        setattr(tipo, key, value)

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CAT_TIPO_ARTICULO_UPDATE",
        modulo="Catalogos",
        detalle=f"id={id_tipo}",
        valores_anteriores=old_values,
        valores_nuevos=tipo,
    )

    await db.commit()
    await db.refresh(tipo)
    return tipo


@router.delete("/{id_tipo}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_tipo_articulo(
    id_tipo: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eliminar un tipo de artículo. Requiere rol de ADMIN."""
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene permiso para esta acción")

    tipo = await db.get(CatTipoArticulo, id_tipo)
    if not tipo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tipo de artículo con id {id_tipo} no encontrado")

    # Verificar si está en uso antes de borrar
    result = await db.execute(select(Articulo.id_articulo).where(Articulo.id_tipo == id_tipo).limit(1))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar el tipo '{tipo.nombre}' porque está siendo utilizado por al menos un artículo."
        )

    old_values = {"nombre": tipo.nombre, "descripcion": tipo.descripcion}

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CAT_TIPO_ARTICULO_DELETE",
        modulo="Catalogos",
        detalle=f"id={id_tipo}",
        valores_anteriores=old_values,
    )

    await db.delete(tipo)
    await db.commit()

    return None