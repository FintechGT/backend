from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models.solicitud import Solicitud
from app.db.models.estado_solicitud import EstadoSolicitud
from app.utils.auditoria import registrar_auditoria
from app.core.security import get_current_user
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])

class SolicitudCreate(BaseModel):
    metodo_entrega: str = Field(..., description="domicilio | oficina")
    direccion_entrega: str | None = Field(None, max_length=300)

class SolicitudOut(BaseModel):
    id_solicitud: int
    estado: str
    metodo_entrega: str
    direccion_entrega: str | None

    class Config:
        from_attributes = True

@router.post("", response_model=SolicitudOut, status_code=status.HTTP_201_CREATED)
async def crear_solicitud(
    payload: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    metodo = payload.metodo_entrega.lower()
    if metodo not in {"domicilio", "oficina"}:
        raise HTTPException(status_code=400, detail="Método de entrega inválido (domicilio | oficina)")

    if metodo == "domicilio" and not payload.direccion_entrega:
        raise HTTPException(status_code=400, detail="Debe proporcionar una dirección si el método es domicilio")

    result = await db.execute(select(EstadoSolicitud).where(EstadoSolicitud.Nombre == "pendiente"))
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(status_code=500, detail="Estado 'pendiente' no existe en el catálogo")

    nueva = Solicitud(
        id_usuario=current_user.ID_Usuario,
        id_estado=estado.Id_Estado_Solicitud,
        metodo_entrega=metodo,
        direccion_entrega=payload.direccion_entrega
    )

    db.add(nueva)
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CREAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud ID {nueva.id_solicitud} creada por usuario {current_user.ID_Usuario}",
        valores_nuevos=nueva.__dict__,
    )

    await db.commit()
    await db.refresh(nueva)

    return SolicitudOut(
        id_solicitud=nueva.id_solicitud,
        estado=estado.Nombre,
        metodo_entrega=nueva.metodo_entrega,
        direccion_entrega=nueva.direccion_entrega
    )

@router.get("/mis", response_model=list[SolicitudOut])
async def listar_mis_solicitudes(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(Solicitud.id_usuario == current_user.ID_Usuario)
    )
    solicitudes = result.scalars().all()
    return [
        SolicitudOut(
            id_solicitud=s.id_solicitud,
            estado=s.estado.Nombre if s.estado else "",
            metodo_entrega=s.metodo_entrega,
            direccion_entrega=s.direccion_entrega
        ) for s in solicitudes
    ]