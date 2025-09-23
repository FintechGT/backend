from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.api.deps import get_current_user  # tu dependencia
from app.schemas.solicitudes_completa import SolicitudCompletaIn, SolicitudCompletaOut, ArticuloOut, FotoOut
from app.db.models import (
    Solicitud, Articulo, ArticuloFoto,
    EstadoSolicitud, EstadoArticulo, CatTipoArticulo
)

router = APIRouter(prefix="", tags=["solicitudes-completa"])

def _attr(entity, *candidates, default=None):
    for c in candidates:
        if hasattr(entity, c):
            return getattr(entity, c)
    return default

@router.post("/solicitudes-completa", response_model=SolicitudCompletaOut)
async def crear_solicitud_completa(
    payload: SolicitudCompletaIn,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # 1) Resolver IDs
    user_id = _attr(current_user, "ID_Usuario", "id_usuario")
    if not user_id:
        raise HTTPException(401, "No se pudo resolver el usuario.")

    # 2) Buscar estados 'pendiente'
    estado_sol = (await db.execute(
        select(EstadoSolicitud).where(EstadoSolicitud.nombre.ilike("pendiente"))
    )).scalar_one_or_none()
    if not estado_sol:
        raise HTTPException(500, "No existe Estado_Solicitud 'pendiente'.")

    estado_art = (await db.execute(
        select(EstadoArticulo).where(EstadoArticulo.nombre.ilike("pendiente"))
    )).scalar_one_or_none()
    if not estado_art:
        raise HTTPException(500, "No existe Estado_Articulo 'pendiente'.")

    # 3) Validar tipos de artículo que vienen
    tipos_ids = {a.id_tipo for a in payload.articulos}
    existentes = (await db.execute(
        select(CatTipoArticulo.id_tipo).where(CatTipoArticulo.id_tipo.in_(tipos_ids))
    )).scalars().all()
    faltantes = tipos_ids - set(existentes)
    if faltantes:
        raise HTTPException(400, f"Tipos de artículo inexistentes: {sorted(faltantes)}")

    # 4) Crear Solicitud  (OJO: usar id_estado=..., no id_estado_solicitud=)
    nueva = Solicitud(
        id_usuario=user_id,
        id_estado=estado_sol.id_estado_solicitud,
        metodo_entrega=payload.metodo_entrega,
        direccion_entrega=payload.direccion_entrega,
    )
    db.add(nueva)
    await db.flush()  # obtiene Id_Solicitud

    articulos_out = []

    # 5) Crear Artículos y sus fotos
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

        fotos_out = []
        for f in a.fotos:
            af = ArticuloFoto(
                id_articulo=art.id_articulo,
                url=str(f.url),
                orden=f.orden,
            )
            db.add(af)
            await db.flush()
            fotos_out.append(FotoOut(id_foto=af.id_foto, url=af.url, orden=af.orden))

        articulos_out.append(
            ArticuloOut(
                id_articulo=art.id_articulo,
                id_tipo=art.id_tipo,
                descripcion=art.descripcion,
                valor_estimado=float(art.valor_estimado),
                condicion=art.condicion,
                fotos=fotos_out,
            )
        )

    await db.commit()

    return SolicitudCompletaOut(
        id_solicitud=nueva.id_solicitud,
        estado=estado_sol.nombre,
        metodo_entrega=nueva.metodo_entrega,
        direccion_entrega=nueva.direccion_entrega,
        articulos=articulos_out,
    )
