# ============================================================
# app/api/routers/solicitudes.py
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect

from app.db.database import get_db
from app.db.models.solicitud import Solicitud
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.user import User
from app.schemas.solicitudes import SolicitudCreate, SolicitudUpdate, SolicitudOut
from app.core.security import get_current_user
from app.utils.auditoria import registrar_auditoria
from app.deps.perm import perm  # ✅ nuevo: control de permisos

router = APIRouter(tags=["Solicitudes"])

# ============================================================
# Helpers
# ============================================================

def _cols_dict(obj):
    """Convierte un modelo SQLAlchemy a dict simple para auditoría."""
    m = inspect(obj)
    return {c.key: getattr(obj, c.key) for c in m.mapper.column_attrs}


# -----------------
# Helpers de estados
# -----------------
ESTADOS_SOLICITUD_VALIDOS = {"pendiente", "en_revision", "evaluada", "rechazada"}

async def _get_estado_solicitud_by_name(db: AsyncSession, nombre: str) -> EstadoSolicitud | None:
    """Obtiene EstadoSolicitud por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoSolicitud).where(func.lower(EstadoSolicitud.nombre) == nombre.lower())
    )
    return result.scalar_one_or_none()

def _to_std_estado_nombre(estado: EstadoSolicitud | None) -> str:
    """Normaliza el nombre del estado (minusculas)."""
    return (estado.nombre if estado else "").lower()


# ============================================================
# CREATE - CON PERMISOS
# ============================================================
@router.post(
    "",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(perm("solicitudes.create"))]
)
async def crear_solicitud(
    payload: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea una nueva solicitud si el usuario tiene permiso."""
    metodo = (payload.metodo_entrega or "").lower()
    if metodo not in {"domicilio", "oficina"}:
        raise HTTPException(status_code=400, detail="Método de entrega inválido (domicilio | oficina)")
    if metodo == "domicilio" and not payload.direccion_entrega:
        raise HTTPException(status_code=400, detail="Debe proporcionar dirección si el método es domicilio")

    estado = await _get_estado_solicitud_by_name(db, "pendiente")
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
    await db.refresh(estado)

    return SolicitudOut(
        id_solicitud=nueva.id_solicitud,
        estado=_to_std_estado_nombre(estado),
        metodo_entrega=nueva.metodo_entrega,
        direccion_entrega=nueva.direccion_entrega,
    )


# ============================================================
# READ - MIS SOLICITUDES
# ============================================================
@router.get(
    "/mis",
    response_model=list[SolicitudOut],
    dependencies=[Depends(perm("solicitudes.view"))]
)
async def listar_mis_solicitudes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista las solicitudes del usuario actual."""
    result = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(Solicitud.id_usuario == current_user.ID_Usuario)
    )
    solicitudes = result.scalars().all()

    return [
        SolicitudOut(
            id_solicitud=s.id_solicitud,
            estado=_to_std_estado_nombre(s.estado),
            metodo_entrega=s.metodo_entrega,
            direccion_entrega=s.direccion_entrega,
        )
        for s in solicitudes
    ]


# ============================================================
# READ - DETALLE
# ============================================================
@router.get(
    "/{id_solicitud}",
    response_model=SolicitudOut,
    dependencies=[Depends(perm("solicitudes.view"))]
)
async def obtener_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene una solicitud del usuario actual."""
    result = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(Solicitud.id_solicitud == id_solicitud)
    )
    s = result.scalar_one_or_none()
    if not s or s.id_usuario != current_user.ID_Usuario:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=_to_std_estado_nombre(s.estado),
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )


# ============================================================
# UPDATE
# ============================================================
@router.put(
    "/{id_solicitud}",
    response_model=SolicitudOut,
    dependencies=[Depends(perm("solicitudes.update"))]
)
async def actualizar_solicitud(
    id_solicitud: int,
    payload: SolicitudUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualiza una solicitud del usuario actual."""
    result = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(
            Solicitud.id_solicitud == id_solicitud,
            Solicitud.id_usuario == current_user.ID_Usuario,
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
        estado=_to_std_estado_nombre(s.estado),
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )


# ============================================================
# DELETE
# ============================================================
@router.delete(
    "/{id_solicitud}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(perm("solicitudes.delete"))]
)
async def eliminar_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Elimina una solicitud del usuario actual."""
    result = await db.execute(
        select(Solicitud).where(
            Solicitud.id_solicitud == id_solicitud,
            Solicitud.id_usuario == current_user.ID_Usuario,
        )
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


# ============================================================
# PATCH - CAMBIAR ESTADO
# ============================================================
@router.patch(
    "/{id_solicitud}/estado/{nuevo}",
    response_model=SolicitudOut,
    dependencies=[Depends(perm("solicitudes.cambiar_estado"))]
)
async def cambiar_estado(
    id_solicitud: int,
    nuevo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cambia el estado de una solicitud (solo usuarios autorizados)."""
    nuevo_std = (nuevo or "").lower()
    if nuevo_std not in ESTADOS_SOLICITUD_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Válidos: {sorted(ESTADOS_SOLICITUD_VALIDOS)}")

    result = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(Solicitud.id_solicitud == id_solicitud)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    est_dest = await _get_estado_solicitud_by_name(db, nuevo_std)
    if not est_dest:
        raise HTTPException(status_code=400, detail=f"Estado '{nuevo_std}' no existe en catálogo")

    old = _cols_dict(s)
    s.id_estado = est_dest.Id_Estado_Solicitud
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CAMBIAR_ESTADO_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {s.id_solicitud} -> {nuevo_std}",
        valores_anteriores=old,
        valores_nuevos=s,
    )
    await db.commit()
    await db.refresh(s)

    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=nuevo_std,
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )
