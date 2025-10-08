# app/api/routers/articulo_rechazar.py

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db

# Modelos
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.auditoria import Auditoria

# Auth / seguridad
from app.core.security import get_current_user

# Schemas
from app.schemas.articulo_rechazar import RechazoArticulo, RespuestaRechazo


router = APIRouter(prefix="/articulo/rechazar", tags=["Articulo Rechazar"])


async def _estado_por_nombre(db: AsyncSession, nombre: str):
    res = await db.execute(select(EstadoArticulo).where(EstadoArticulo.nombre == nombre))
    return res.scalar_one_or_none()


@router.patch(
    "/{id_articulo}/rechazar",
    response_model=RespuestaRechazo,
    status_code=status.HTTP_200_OK,
)
async def rechazar_articulo(
    id_articulo: int,
    datos: RechazoArticulo,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Rechaza un artículo SIN modificar el esquema:
    - Actualiza Articulo.Id_Estado -> 'rechazado'
    - Limpia Articulo.Valor_Aprobado -> NULL (si existe en el modelo)
    - Registra motivo en Auditoria (usando fecha_hora explícita)
    """

    # 1) Traer artículo
    articulo = await db.get(Articulo, id_articulo)
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    # 2) Estados
    estado_rech = await _estado_por_nombre(db, "rechazado")
    if not estado_rech:
        raise HTTPException(status_code=500, detail="Estado 'rechazado' no existe")

    estado_pend = await _estado_por_nombre(db, "pendiente")

    # 3) Validación de transición (opcional pero recomendado)
    if estado_pend and articulo.id_estado != estado_pend.id_estado_articulo:
        raise HTTPException(
            status_code=409,
            detail="El artículo ya fue evaluado o no está en 'pendiente'",
        )

    # 4) Actualizar artículo
    articulo.id_estado = estado_rech.id_estado_articulo
    if hasattr(articulo, "valor_aprobado"):
        articulo.valor_aprobado = None

    # 5) Auditoría con fecha_hora (tu tabla la requiere NOT NULL)
    user_id = (
        getattr(current_user, "id_usuario", None)
        or getattr(current_user, "ID_Usuario", None)
        or 0
    )
    audit = Auditoria(
        id_usuario=user_id,
        accion="RECHAZAR_ARTICULO",
        modulo="Articulos",
        fecha_hora=datetime.utcnow(),  # 👈 evita IntegrityError (NOT NULL)
        detalle=f"id_articulo={id_articulo}; motivo={datos.motivo}",
        old_values=None,
        new_values=None,
    )
    db.add(audit)

    # 6) Guardar cambios
    try:
        await db.commit()
        await db.refresh(articulo)
    except Exception:
        await db.rollback()
        raise

    # 7) Respuesta
    return RespuestaRechazo(
        id_articulo=id_articulo,
        estado="rechazado",
        motivo=datos.motivo,
    )
