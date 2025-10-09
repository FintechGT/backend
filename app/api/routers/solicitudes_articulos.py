# app/api/routers/solicitudes_articulos.py
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.solicitud import Solicitud
from app.db.models.articulo import Articulo
from app.db.models.articulo_foto import ArticuloFoto
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.user import User

# Schemas
from app.schemas.solicitudes_articulos import SolicitudArticuloCreate, SolicitudArticuloOut, FotoOut

# Utils
from app.utils.roles import usuario_tiene_algun_rol
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes - Artículos"])


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario autenticado")


def _ensure_id_usuario_attr(u: User) -> None:
    """
    Si el modelo de usuario no tiene .id_usuario (pero sí ID_Usuario o id),
    lo crea al vuelo para compatibilidad con utilidades que esperan ese atributo.
    """
    if hasattr(u, "id_usuario") and isinstance(getattr(u, "id_usuario"), int):
        return
    uid = None
    for attr in ("ID_Usuario", "id_usuario", "id"):
        v = getattr(u, attr, None)
        if isinstance(v, int):
            uid = v
            break
    if uid is None:
        raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario autenticado")
    setattr(u, "id_usuario", uid)


# ============================================================
# POST /solicitudes/{id_solicitud}/articulos
# ============================================================
@router.post(
    "/{id_solicitud}/articulos",
    response_model=SolicitudArticuloOut,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar artículo a una solicitud existente",
    description="Permite al dueño o a un operador/admin agregar un nuevo artículo a una solicitud.",
)
async def agregar_articulo_a_solicitud(
    id_solicitud: int,
    payload: SolicitudArticuloCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # 1) Verificar que la solicitud exista
    result_sol = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(Solicitud.id_solicitud == id_solicitud)
    )
    solicitud = result_sol.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    # 2) Verificar permisos
    es_admin = await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR"])
    if not es_admin and solicitud.id_usuario != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar esta solicitud")

    # 3) Validar estado permitido
    estados_permitidos = ["pendiente", "en_revision"]
    estado_nombre = solicitud.estado.nombre.lower() if solicitud.estado else ""
    if estado_nombre not in estados_permitidos:
        raise HTTPException(
            status_code=409,
            detail=f"No se pueden agregar artículos en estado '{estado_nombre}'. Solo en: {', '.join(estados_permitidos)}",
        )

    # 4) Validar tipo de artículo
    result_tipo = await db.execute(select(CatTipoArticulo).where(CatTipoArticulo.id_tipo == payload.id_tipo))
    tipo_articulo = result_tipo.scalar_one_or_none()
    if not tipo_articulo:
        raise HTTPException(status_code=422, detail=f"Tipo de artículo {payload.id_tipo} no existe")

    # 5) Obtener estado pendiente
    result_estado = await db.execute(
        select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == "pendiente")
    )
    estado_pendiente = result_estado.scalar_one_or_none()
    if not estado_pendiente:
        raise HTTPException(status_code=500, detail="Estado 'pendiente' no existe en catálogo")

    # 6) Crear el artículo
    nuevo_articulo = Articulo(
        id_solicitud=id_solicitud,
        id_tipo=payload.id_tipo,
        id_estado=estado_pendiente.id_estado_articulo,
        descripcion=payload.descripcion,
        valor_estimado=payload.valor_estimado,
        condicion=payload.condicion,
    )
    db.add(nuevo_articulo)
    await db.flush()

    # 7) Registrar auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="AGREGAR_ARTICULO_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Artículo {nuevo_articulo.id_articulo} agregado a solicitud {id_solicitud}",
        valores_nuevos={
            "id_articulo": nuevo_articulo.id_articulo,
            "id_tipo": payload.id_tipo,
            "valor_estimado": float(payload.valor_estimado),
        },
    )

    await db.commit()
    await db.refresh(nuevo_articulo)

    # 8) Respuesta
    return SolicitudArticuloOut(
        id_articulo=nuevo_articulo.id_articulo,
        id_solicitud=id_solicitud,
        id_tipo=nuevo_articulo.id_tipo,
        descripcion=nuevo_articulo.descripcion,
        valor_estimado=float(nuevo_articulo.valor_estimado),
        condicion=nuevo_articulo.condicion,
        estado="pendiente",
        fotos=[],
    )


# ============================================================
# GET /solicitudes/{id_solicitud}/articulos
# ============================================================
@router.get(
    "/{id_solicitud}/articulos",
    response_model=List[SolicitudArticuloOut],
    summary="Listar artículos de una solicitud",
    description="Lista todos los artículos de una solicitud con sus fotos (si existen).",
)
async def listar_articulos_de_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # 1) Verificar que la solicitud exista
    result_sol = await db.execute(select(Solicitud).where(Solicitud.id_solicitud == id_solicitud))
    solicitud = result_sol.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    # 2) Verificar permisos
    es_admin = await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR", "VALUADOR"])
    if not es_admin and solicitud.id_usuario != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta solicitud")

    # 3) Obtener artículos
    result_arts = await db.execute(
        select(Articulo).where(Articulo.id_solicitud == id_solicitud).order_by(Articulo.id_articulo)
    )
    articulos = result_arts.scalars().all()

    # 4) Construir respuesta
    respuesta = []
    for art in articulos:
        result_estado = await db.execute(
            select(EstadoArticulo).where(EstadoArticulo.id_estado_articulo == art.id_estado)
        )
        estado = result_estado.scalar_one_or_none()
        estado_nombre = estado.nombre if estado else "desconocido"

        result_fotos = await db.execute(
            select(ArticuloFoto).where(ArticuloFoto.id_articulo == art.id_articulo).order_by(ArticuloFoto.orden)
        )
        fotos_db = result_fotos.scalars().all()
        fotos = [FotoOut(id_foto=f.id_foto, url=f.url, orden=f.orden) for f in fotos_db]

        respuesta.append(
            SolicitudArticuloOut(
                id_articulo=art.id_articulo,
                id_solicitud=id_solicitud,
                id_tipo=art.id_tipo,
                descripcion=art.descripcion,
                valor_estimado=float(art.valor_estimado),
                condicion=art.condicion,
                estado=estado_nombre,
                fotos=fotos,
            )
        )

    return respuesta
