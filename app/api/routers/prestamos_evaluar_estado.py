# app/api/routers/prestamos_evaluar_estado.py
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.db.models.user import User

# Utils
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Evaluar Estado"])

# =========================
# Helpers de utilería
# =========================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")

async def _get_cfg_int(db: AsyncSession, clave: str, default: int) -> int:
    rs = await db.execute(select(ConfiguracionesGenerales).where(func.lower(ConfiguracionesGenerales.clave) == clave.lower()))
    cfg = rs.scalar_one_or_none()
    if not cfg:
        return default
    try:
        return int(cfg.valor)
    except (TypeError, ValueError):
        return default

async def _get_estado_prestamo(db: AsyncSession, nombre: str) -> Optional[EstadoPrestamo]:
    rs = await db.execute(
        select(EstadoPrestamo).where(func.lower(EstadoPrestamo.nombre) == nombre.lower())
    )
    return rs.scalar_one_or_none()

def _dias_mora(prestamo: Prestamo, fecha_corte: date, dias_gracia: int) -> int:
    """
    Días de mora contados a partir de (fecha_vencimiento + gracia) + 1 si sobrepasa esa frontera.
    Si está dentro del plazo/gracia => 0.
    """
    frontera = prestamo.fecha_vencimiento + timedelta(days=dias_gracia)
    if fecha_corte <= frontera:
        return 0
    return (fecha_corte - frontera).days

async def _derivar_estado(prestamo: Prestamo, fecha_corte: date, db: AsyncSession) -> dict:
    """
    Deriva el estado *sugerido* del préstamo usando los umbrales de configuración.
    Estados válidos: activo, en_mora_parcial, en_mora_grave, incobrable, cancelado, liquidado.
    """
    # Si no hay deuda, considerar liquidado/cancelado
    try:
        deuda_actual = Decimal(str(prestamo.deuda_actual))
    except Exception:
        deuda_actual = Decimal("0")
    if deuda_actual <= Decimal("0"):
        return {"codigo": "cancelado", "razon": "deuda_cero", "dias_mora": 0}

    # Umbrales
    dias_gracia = await _get_cfg_int(db, "GRACIA_DIAS", 3)
    umbral_mora_grave = await _get_cfg_int(db, "UMBRAL_MORA_GRAVE_DIAS", 15)
    umbral_incobrable = await _get_cfg_int(db, "UMBRAL_INCOBRABLE_DIAS", 60)

    # Dentro del plazo o gracia
    dm = _dias_mora(prestamo, fecha_corte, dias_gracia)
    if dm <= 0:
        return {"codigo": "activo", "razon": "en_plazo_o_gracia", "dias_mora": 0}

    # Clasificación por umbrales
    if dm >= umbral_incobrable:
        return {"codigo": "incobrable", "razon": "mora_critica", "dias_mora": dm}
    if dm >= umbral_mora_grave:
        return {"codigo": "en_mora_grave", "razon": "mora_severa", "dias_mora": dm}
    return {"codigo": "en_mora_parcial", "razon": "mora_leve", "dias_mora": dm}


# ============================================================
# ENDPOINT: evaluar y (opcional) actualizar el estado del préstamo
# ============================================================
@router.post(
    "/{id_prestamo}/evaluar-estado",
    status_code=status.HTTP_200_OK,
    summary="Evalúa el estado del préstamo y lo actualiza si corresponde",
    description=(
        "Calcula el estado sugerido del préstamo (activo, en_mora_parcial, en_mora_grave, incobrable, cancelado) "
        "en función de la deuda, fecha de vencimiento y umbrales configurados. "
        "Si el estado actual difiere del sugerido, lo actualiza."
    ),
)
async def evaluar_estado_prestamo(
    id_prestamo: int,
    fecha_corte: Optional[date] = Query(default=None, description="Fecha de corte (YYYY-MM-DD). Por defecto, hoy."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reglas:
    - Si deuda_actual <= 0 => cancelado
    - Si fecha_corte <= (vencimiento + gracia) => activo
    - Si días de mora >= UMBRAL_INCOBRABLE_DIAS => incobrable
    - Si días de mora >= UMBRAL_MORA_GRAVE_DIAS => en_mora_grave
    - En otro caso con mora => en_mora_parcial
    """
    # Permisos
    user_id = _resolve_user_id(current_user)
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR"]):
        raise HTTPException(status_code=403, detail="Sin permiso para evaluar estado de préstamo")

    # Cargar préstamo
    rs = await db.execute(select(Prestamo).where(Prestamo.id_prestamo == id_prestamo).with_for_update())
    prestamo = rs.scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail=f"Préstamo {id_prestamo} no encontrado")

    # Determinar fecha de corte
    fc = fecha_corte or date.today()

    # Derivar estado sugerido
    sugerido = await _derivar_estado(prestamo, fc, db)
    estado_sugerido = await _get_estado_prestamo(db, sugerido["codigo"])
    if not estado_sugerido:
        raise HTTPException(status_code=500, detail=f"Estado '{sugerido['codigo']}' no existe en catálogo")

    # Estado actual
    rs_est_act = await db.execute(
        select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
    )
    estado_actual = rs_est_act.scalar_one_or_none()
    codigo_actual = (estado_actual.nombre if estado_actual else "").lower()

    # Idempotencia: no actualizar si ya coincide
    if estado_sugerido.id_estado_prestamo == prestamo.id_estado:
        return {
            "id_prestamo": prestamo.id_prestamo,
            "fecha_corte": fc,
            "estado_actual": codigo_actual,
            "estado_sugerido": sugerido["codigo"],
            "dias_mora": sugerido["dias_mora"],
            "accion": "sin_cambios",
        }

    # Actualizar estado
    valores_anteriores = {
        "id_estado": prestamo.id_estado,
        "estado_codigo": codigo_actual,
    }
    prestamo.id_estado = estado_sugerido.id_estado_prestamo
    prestamo.updated_at = datetime.now(timezone.utc)

    # Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="EVALUAR_ESTADO_PRESTAMO",
        modulo="Prestamo",
        detalle=(
            f"Estado préstamo {prestamo.id_prestamo}: {codigo_actual or 'desconocido'} -> {sugerido['codigo']} "
            f"({sugerido['dias_mora']} días mora)"
        ),
        valores_anteriores=valores_anteriores,
        valores_nuevos={
            "id_estado": prestamo.id_estado,
            "estado_codigo": sugerido["codigo"],
            "fecha_corte": str(fc),
        }
    )

    # Commit
    try:
        await db.commit()
        await db.refresh(prestamo)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar el cambio de estado: {str(e)}")

    return {
        "id_prestamo": prestamo.id_prestamo,
        "fecha_corte": fc,
        "estado_anterior": codigo_actual,
        "estado_nuevo": sugerido["codigo"],
        "dias_mora": sugerido["dias_mora"],
        "accion": "actualizado",
    }
