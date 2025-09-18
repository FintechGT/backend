from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect

from app.db.database import get_db
from app.db.models.solicitud import Solicitud
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.user import User
from app.schemas.solicitudes import SolicitudCreate, SolicitudUpdate, SolicitudOut
from app.core.security import get_current_user
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol

router = APIRouter(tags=["Solicitudes"])

def _cols_dict(obj):
    m = inspect(obj)
    return {c.key: getattr(obj, c.key) for c in m.mapper.column_attrs}

@router.post("", response_model=SolicitudOut, status_code=status.HTTP_201_CREATED)
async def crear_solicitud(
    payload: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        direccion_entrega=payload.direccion_entrega,
    )
    db.add(nueva)
    await db.flush()
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CREAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {nueva.id_solicitud} creada",
        valores_nuevos=nueva,
    )
    await db.commit()
    await db.refresh(nueva)

    return SolicitudOut(
        id_solicitud=nueva.id_solicitud,
        estado=estado.Nombre,
        metodo_entrega=nueva.metodo_entrega,
        direccion_entrega=nueva.direccion_entrega,
    )

@router.get("/mis", response_model=list[SolicitudOut])
async def listar_mis_solicitudes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
            direccion_entrega=s.direccion_entrega,
        )
        for s in solicitudes
    ]

@router.get("/{id_solicitud}", response_model=SolicitudOut)
async def obtener_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Solicitud).options(selectinload(Solicitud.estado)).where(Solicitud.id_solicitud == id_solicitud)
    )
    s = result.scalar_one_or_none()
    if not s or s.id_usuario != current_user.ID_Usuario:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=s.estado.Nombre if s.estado else "",
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )

@router.put("/{id_solicitud}", response_model=SolicitudOut)
async def actualizar_solicitud(
    id_solicitud: int,
    payload: SolicitudUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Solicitud).options(selectinload(Solicitud.estado)).where(
            Solicitud.id_solicitud == id_solicitud, Solicitud.id_usuario == current_user.ID_Usuario
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    old = _cols_dict(s)
    if payload.metodo_entrega is not None:
        m = payload.metodo_entrega.lower()
        if m not in {"domicilio", "oficina"}:
            raise HTTPException(status_code=400, detail="Método de entrega inválido")
        s.metodo_entrega = m
    if payload.direccion_entrega is not None:
        s.direccion_entrega = payload.direccion_entrega

    await db.flush()
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="ACTUALIZAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {s.id_solicitud} actualizada",
        valores_anteriores=old,
        valores_nuevos=s,
    )
    await db.commit()
    await db.refresh(s)

    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=s.estado.Nombre if s.estado else "",
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )

@router.delete("/{id_solicitud}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Solicitud).where(Solicitud.id_solicitud == id_solicitud, Solicitud.id_usuario == current_user.ID_Usuario)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    old = _cols_dict(s)
    await db.delete(s)
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="ELIMINAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {id_solicitud} eliminada",
        valores_anteriores=old,
    )
    await db.commit()
    return None

@router.patch("/{id_solicitud}/estado/{nuevo}", response_model=SolicitudOut)
async def cambiar_estado(
    id_solicitud: int,
    nuevo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR", "VALUADOR"]):
        raise HTTPException(status_code=403, detail="Sin permiso")

    result = await db.execute(
        select(Solicitud).options(selectinload(Solicitud.estado)).where(Solicitud.id_solicitud == id_solicitud)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    res_est = await db.execute(select(EstadoSolicitud).where(EstadoSolicitud.Nombre == nuevo.lower()))
    est = res_est.scalar_one_or_none()
    if not est:
        raise HTTPException(status_code=400, detail="Estado inválido")

    old = _cols_dict(s)
    s.id_estado = est.Id_Estado_Solicitud
    await db.flush()
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CAMBIAR_ESTADO_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {s.id_solicitud} -> {nuevo}",
        valores_anteriores=old,
        valores_nuevos=s,
    )
    await db.commit()
    await db.refresh(s)

    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=nuevo.lower(),
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )
