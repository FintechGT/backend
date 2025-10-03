from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.core.security import get_current_user
from app.schemas.articulo_rechazar import RechazoArticulo, RespuestaRechazo

router = APIRouter(prefix="/articulo/rechazar", tags=["Articulo Rechazar"])

@router.patch(
    "/{id_articulo}/rechazar",
    response_model=RespuestaRechazo,
    status_code=status.HTTP_200_OK
)
async def rechazar_articulo(
    id_articulo: int,
    datos: RechazoArticulo,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    articulo = await db.get(Articulo, id_articulo)
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    estado_rechazado = await db.execute(
        EstadoArticulo.__table__.select().where(EstadoArticulo.nombre == "rechazado")
    )
    estado = estado_rechazado.scalar_one_or_none()
    if not estado:
        raise HTTPException(status_code=500, detail="Estado 'rechazado' no existe")

    articulo.id_estado = estado.id_estado_articulo
    articulo.motivo_rechazo = datos.motivo
    await db.commit()
    await db.refresh(articulo)

    return {
        "id_articulo": id_articulo,
        "estado": "rechazado",
        "motivo": datos.motivo
    }
