from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.api.deps import get_current_user

from app.schemas.solicitudes_completa import (
    SolicitudCompletaIn, SolicitudCompletaOut, SolicitudResumenOut,
    ArticuloOut, FotoOut
)

from app.db.models import (
    Solicitud, Articulo, ArticuloFoto,
    EstadoSolicitud, EstadoArticulo, CatTipoArticulo
)

router = APIRouter(prefix="", tags=["solicitudes-completa"])


# ----------------- helpers -----------------
def _attr(entity, *candidates, default=None):
    """Devuelve el primer atributo existente del objeto."""
    for c in candidates:
        if hasattr(entity, c):
            return getattr(entity, c)
    return default


async def _cargar_solicitud_completa(
    db: AsyncSession,
    id_solicitud: int,
    owner_id: int | None = None
) -> SolicitudCompletaOut:
    """
    Arma la salida SolicitudCompletaOut desde BD (carga estado con selectinload).
    """
    sol: Solicitud | None = (
        await db.execute(
            select(Solicitud)
            .options(selectinload(Solicitud.estado))
            .where(Solicitud.id_solicitud == id_solicitud)
        )
    ).scalar_one_or_none()

    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")

    if owner_id and sol.id_usuario != owner_id:
        raise HTTPException(status_code=403, detail="No puedes acceder a esta solicitud.")

    estado_nombre = sol.estado.nombre if sol.estado else ""

    # Artículos
    arts: List[Articulo] = (
        await db.execute(
            select(Articulo).where(Articulo.id_solicitud == sol.id_solicitud)
        )
    ).scalars().all()

    articulos_out: list[ArticuloOut] = []
    for a in arts:
        fotos: List[ArticuloFoto] = (
            await db.execute(
                select(ArticuloFoto)
                .where(ArticuloFoto.id_articulo == a.id_articulo)
                .order_by(ArticuloFoto.orden)
            )
        ).scalars().all()

        fotos_out = [FotoOut(id_foto=f.id_foto, url=f.url, orden=f.orden) for f in fotos]

        articulos_out.append(
            ArticuloOut(
                id_articulo=a.id_articulo,
                id_tipo=a.id_tipo,
                descripcion=a.descripcion,
                valor_estimado=float(a.valor_estimado),
                condicion=a.condicion,
                fotos=fotos_out,
            )
        )

    return SolicitudCompletaOut(
        id_solicitud=sol.id_solicitud,
        estado=estado_nombre,
        metodo_entrega=sol.metodo_entrega,
        direccion_entrega=sol.direccion_entrega,
        articulos=articulos_out,
    )


# ----------------- CREATE -----------------
@router.post("/solicitudes-completa", response_model=SolicitudCompletaOut)
async def crear_solicitud_completa(
    payload: SolicitudCompletaIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 1) Usuario
    user_id = _attr(current_user, "ID_Usuario", "id_usuario")
    if not user_id:
        raise HTTPException(status_code=401, detail="No se pudo resolver el usuario.")

    # 2) Estados 'pendiente'
    estado_sol = (
        await db.execute(
            select(EstadoSolicitud).where(EstadoSolicitud.nombre.ilike("pendiente"))
        )
    ).scalar_one_or_none()
    if not estado_sol:
        raise HTTPException(status_code=500, detail="No existe Estado_Solicitud 'pendiente'.")

    estado_art = (
        await db.execute(
            select(EstadoArticulo).where(EstadoArticulo.nombre.ilike("pendiente"))
        )
    ).scalar_one_or_none()
    if not estado_art:
        raise HTTPException(status_code=500, detail="No existe Estado_Articulo 'pendiente'.")

    # 3) Validar tipos
    tipos_ids = {a.id_tipo for a in payload.articulos}
    existentes = (
        await db.execute(
            select(CatTipoArticulo.id_tipo).where(CatTipoArticulo.id_tipo.in_(tipos_ids))
        )
    ).scalars().all()
    faltantes = tipos_ids - set(existentes)
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Tipos de artículo inexistentes: {sorted(faltantes)}",
        )

    # 4) Crear Solicitud (usar atributo del modelo 'id_estado')
    nueva = Solicitud(
        id_usuario=user_id,
        id_estado=estado_sol.id_estado_solicitud,
        metodo_entrega=payload.metodo_entrega,
        direccion_entrega=payload.direccion_entrega,
    )
    db.add(nueva)
    await db.flush()  # obtiene Id_Solicitud

    # 5) Artículos + fotos
    for a in payload.articulos:
        art = Articulo(
            id_solicitud=nueva.id_solicitud,
            id_tipo=a.id_tipo,
            id_estado=estado_art.id_estado_articulo,
            descripcion=a.descripcion,
            valor_estimado=a.valor_estimado,
            condicion=a.condicion,
        )
        db.add(art)
        await db.flush()  # Id_articulo

        # Fotos del artículo
        for f in a.fotos:
            db.add(
                ArticuloFoto(
                    id_articulo=art.id_articulo,
                    url=str(f.url),
                    orden=f.orden,
                )
            )

    await db.commit()
    return await _cargar_solicitud_completa(db, nueva.id_solicitud, owner_id=user_id)


# ----------------- READ (detalle) -----------------
@router.get("/solicitudes-completa/{id_solicitud}", response_model=SolicitudCompletaOut)
async def obtener_solicitud_completa(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = _attr(current_user, "ID_Usuario", "id_usuario")
    return await _cargar_solicitud_completa(db, id_solicitud, owner_id=user_id)


# ----------------- READ (mis solicitudes resumidas) -----------------
@router.get("/solicitudes-completa", response_model=list[SolicitudResumenOut])
async def listar_mis_solicitudes_completas(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = _attr(current_user, "ID_Usuario", "id_usuario")

    filas: List[Solicitud] = (
        await db.execute(
            select(Solicitud)
            .options(selectinload(Solicitud.estado))  # evita MissingGreenlet
            .where(Solicitud.id_usuario == user_id)
            .order_by(Solicitud.id_solicitud.desc())
        )
    ).scalars().all()

    res: list[SolicitudResumenOut] = []
    for s in filas:
        res.append(
            SolicitudResumenOut(
                id_solicitud=s.id_solicitud,
                estado=s.estado.nombre if s.estado else "",
                metodo_entrega=s.metodo_entrega,
                direccion_entrega=s.direccion_entrega,
                fecha_envio=s.fecha_envio.isoformat(sep=" ", timespec="seconds"),
            )
        )
    return res


# ----------------- UPDATE (reemplazo total de artículos) -----------------
@router.put("/solicitudes-completa/{id_solicitud}", response_model=SolicitudCompletaOut)
async def actualizar_solicitud_completa(
    id_solicitud: int,
    payload: SolicitudCompletaIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = _attr(current_user, "ID_Usuario", "id_usuario")

    sol: Solicitud | None = (
        await db.execute(
            select(Solicitud).where(Solicitud.id_solicitud == id_solicitud)
        )
    ).scalar_one_or_none()

    if not sol or sol.id_usuario != user_id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")

    # Validar método + dirección
    metodo = payload.metodo_entrega.lower()
    if metodo not in {"domicilio", "oficina"}:
        raise HTTPException(status_code=400, detail="Método inválido (domicilio | oficina).")
    if metodo == "domicilio" and not payload.direccion_entrega:
        raise HTTPException(status_code=400, detail="Debe proporcionar dirección si el método es domicilio.")

    # Validar tipos
    tipos_ids = {a.id_tipo for a in payload.articulos}
    existentes = (
        await db.execute(
            select(CatTipoArticulo.id_tipo).where(CatTipoArticulo.id_tipo.in_(tipos_ids))
        )
    ).scalars().all()
    faltantes = tipos_ids - set(existentes)
    if faltantes:
        raise HTTPException(status_code=400, detail=f"Tipos inexistentes: {sorted(faltantes)}")

    # Estado por defecto de artículos
    estado_art = (
        await db.execute(
            select(EstadoArticulo).where(EstadoArticulo.nombre.ilike("pendiente"))
        )
    ).scalar_one_or_none()
    if not estado_art:
        raise HTTPException(status_code=500, detail="No existe Estado_Articulo 'pendiente'.")

    # Actualizar encabezado
    sol.metodo_entrega = metodo
    sol.direccion_entrega = payload.direccion_entrega
    await db.flush()

    # Borrar artículos/fotos actuales
    arts_ids = (
        await db.execute(
            select(Articulo.id_articulo).where(Articulo.id_solicitud == id_solicitud)
        )
    ).scalars().all()
    if arts_ids:
        await db.execute(delete(ArticuloFoto).where(ArticuloFoto.id_articulo.in_(arts_ids)))
        await db.execute(delete(Articulo).where(Articulo.id_articulo.in_(arts_ids)))

    # Crear nuevos artículos/fotos (reemplazo)
    for a in payload.articulos:
        art = Articulo(
            id_solicitud=sol.id_solicitud,
            id_tipo=a.id_tipo,
            id_estado=estado_art.id_estado_articulo,
            descripcion=a.descripcion,
            valor_estimado=a.valor_estimado,
            condicion=a.condicion,
        )
        db.add(art)
        await db.flush()
        for f in a.fotos:
            db.add(ArticuloFoto(
                id_articulo=art.id_articulo,
                url=str(f.url),
                orden=f.orden
            ))

    await db.commit()
    return await _cargar_solicitud_completa(db, sol.id_solicitud, owner_id=user_id)


# ----------------- DELETE -----------------
@router.delete("/solicitudes-completa/{id_solicitud}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_solicitud_completa(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    user_id = _attr(current_user, "ID_Usuario", "id_usuario")

    sol: Solicitud | None = (
        await db.execute(
            select(Solicitud).where(Solicitud.id_solicitud == id_solicitud)
        )
    ).scalar_one_or_none()

    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")

    if sol.id_usuario != user_id:
        raise HTTPException(status_code=403, detail="No puedes eliminar esta solicitud.")

    # Borrado manual en orden (fotos -> artículos -> solicitud)
    arts_ids = (
        await db.execute(
            select(Articulo.id_articulo).where(Articulo.id_solicitud == id_solicitud)
        )
    ).scalars().all()

    if arts_ids:
        await db.execute(delete(ArticuloFoto).where(ArticuloFoto.id_articulo.in_(arts_ids)))
        await db.execute(delete(Articulo).where(Articulo.id_articulo.in_(arts_ids)))

    await db.execute(delete(Solicitud).where(Solicitud.id_solicitud == id_solicitud))
    await db.commit()
    return None
