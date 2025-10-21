# app/api/routers/prestamos_activar.py
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.prestamo_movimiento import PrestamoMovimiento
from app.db.models.user import User

# Schemas
from app.schemas.prestamos_activar import PrestamoActivarIn, PrestamoActivarOut

# Utils
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Activación"])


# ============================================================
# HELPERS
# ============================================================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _ensure_id_usuario_attr(u: User) -> None:
    """Asegura que el usuario tenga el atributo id_usuario para compatibilidad."""
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))


async def _obtener_estado_prestamo(db: AsyncSession, nombre: str) -> EstadoPrestamo:
    """Obtiene un estado de préstamo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoPrestamo).where(func.lower(EstadoPrestamo.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de préstamo '{nombre}' no existe en catálogo"
        )
    return estado


async def _obtener_estado_articulo(db: AsyncSession, nombre: str) -> EstadoArticulo:
    """Obtiene un estado de artículo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de artículo '{nombre}' no existe en catálogo"
        )
    return estado


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================
@router.patch(
    "/{id_prestamo}/activar",
    response_model=PrestamoActivarOut,
    status_code=status.HTTP_200_OK,
    summary="Activar préstamo (post-firma de contrato)",
    description=(
        "Cambia el estado del préstamo de 'aprobado_pendiente_entrega' a 'activo'. "
        "Actualiza el artículo asociado a 'empeñado'. "
        "Registra el movimiento de desembolso. "
        "**Permisos:** ADMINISTRADOR, VALUADOR, OPERADOR"
    )
)
async def activar_prestamo(
    id_prestamo: int = Path(..., ge=1),
    payload: PrestamoActivarIn = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Activa un préstamo que ya fue aprobado y tiene contrato firmado.
    
    **Proceso:**
    1. Valida que el préstamo esté en estado 'aprobado_pendiente_entrega'
    2. Cambia el estado del préstamo a 'activo'
    3. Actualiza el artículo asociado a estado 'empeñado'
    4. Establece deuda_actual = monto_prestamo
    5. Registra movimiento de desembolso
    6. Registra auditoría completa
    
    **Casos de uso:**
    - Post-firma de contrato (ambas partes)
    - Activación manual por operador
    - Integración con sistema de pagos
    """
    
    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)
    
    roles_permitidos = ["ADMINISTRADOR", "VALUADOR", "OPERADOR"]
    tiene_permiso = await usuario_tiene_algun_rol(current_user, db, roles_permitidos)
    
    if not tiene_permiso:
        raise HTTPException(
            status_code=403,
            detail=f"Requiere uno de estos roles: {', '.join(roles_permitidos)}"
        )
    
    # 2) Cargar préstamo con lock
    result = await db.execute(
        select(Prestamo)
        .where(Prestamo.id_prestamo == id_prestamo)
        .with_for_update()
    )
    prestamo = result.scalar_one_or_none()
    
    if not prestamo:
        raise HTTPException(
            status_code=404,
            detail=f"Préstamo {id_prestamo} no encontrado"
        )
    
    # 3) Validar estado actual
    result_estado = await db.execute(
        select(EstadoPrestamo).where(
            EstadoPrestamo.id_estado_prestamo == prestamo.id_estado
        )
    )
    estado_actual = result_estado.scalar_one_or_none()
    estado_nombre = (estado_actual.nombre if estado_actual else "").lower()
    
    if estado_nombre != "aprobado_pendiente_entrega":
        raise HTTPException(
            status_code=409,
            detail=f"El préstamo está en estado '{estado_nombre}'. Solo se puede activar desde 'aprobado_pendiente_entrega'"
        )
    
    # 4) Obtener estados necesarios
    estado_activo = await _obtener_estado_prestamo(db, "activo")
    estado_empenado = await _obtener_estado_articulo(db, "empeñado")
    
    # 5) Actualizar préstamo
    prestamo.id_estado = estado_activo.id_estado_prestamo
    prestamo.deuda_actual = Decimal(str(prestamo.monto_prestamo))
    prestamo.updated_at = datetime.now(timezone.utc)
    
    # 6) Actualizar artículo asociado
    result_art = await db.execute(
        select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo)
    )
    articulo = result_art.scalar_one_or_none()
    
    if articulo:
        articulo.id_estado = estado_empenado.id_estado_articulo
    
    # 7) Fecha de desembolso
    fecha_desembolso = payload.fecha_desembolso or datetime.now(timezone.utc)
    
    # 8) Crear movimiento de desembolso
    movimiento = PrestamoMovimiento(
        id_prestamo=prestamo.id_prestamo,
        tipo="desembolso",
        monto=prestamo.monto_prestamo,
        nota=payload.nota or "Desembolso por activación de préstamo",
        fecha=fecha_desembolso,
    )
    db.add(movimiento)
    
    # 9) Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="ACTIVAR_PRESTAMO",
        modulo="Prestamo",
        detalle=(
            f"Préstamo {id_prestamo} activado. "
            f"Desembolso: Q{float(prestamo.monto_prestamo):.2f}. "
            f"Nota: {payload.nota or 'N/A'}"
        ),
        valores_anteriores={
            "estado": estado_nombre,
            "deuda_actual": 0.0,
            "articulo_estado": "evaluado" if articulo else None,
        },
        valores_nuevos={
            "estado": "activo",
            "deuda_actual": float(prestamo.monto_prestamo),
            "articulo_estado": "empeñado" if articulo else None,
            "fecha_desembolso": fecha_desembolso.isoformat(),
        }
    )
    
    # 10) Commit
    try:
        await db.commit()
        await db.refresh(prestamo)
        await db.refresh(movimiento)
        if articulo:
            await db.refresh(articulo)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al activar el préstamo: {str(e)}"
        )
    
    # 11) Respuesta
    return PrestamoActivarOut(
        id_prestamo=prestamo.id_prestamo,
        estado_anterior=estado_nombre,
        estado_nuevo="activo",
        fecha_desembolso=fecha_desembolso,
        mensaje="Préstamo activado exitosamente. Artículo empeñado y desembolso registrado."
    )