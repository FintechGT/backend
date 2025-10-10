from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.prestamo_movimiento import PrestamoMovimiento
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.db.models.user import User

# Schemas
from app.schemas.recalculo import RecalculoIn, RecalculoOut

# Utilidades
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Recálculo"])


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


async def _obtener_config_decimal(
    db: AsyncSession,
    clave: str,
    default: Decimal
) -> Decimal:
    """Obtiene un valor de configuración como Decimal."""
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            ConfiguracionesGenerales.clave == clave
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return default
    try:
        return Decimal(str(config.valor))
    except (ValueError, TypeError):
        return default


async def _obtener_config_int(
    db: AsyncSession,
    clave: str,
    default: int
) -> int:
    """Obtiene un valor de configuración como int."""
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            ConfiguracionesGenerales.clave == clave
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return default
    try:
        return int(config.valor)
    except (ValueError, TypeError):
        return default


async def _obtener_estado_prestamo(
    db: AsyncSession,
    nombre: str
) -> Optional[EstadoPrestamo]:
    """Obtiene un estado de préstamo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoPrestamo).where(
            func.lower(EstadoPrestamo.nombre) == nombre.lower()
        )
    )
    return result.scalar_one_or_none()


async def _derivar_estado_sugerido(
    prestamo: Prestamo,
    fecha_corte: date,
    dias_gracia: int,
    db: AsyncSession
) -> dict:
    """
    Deriva un estado sugerido basado en las reglas del PASO 6.
    NO modifica el préstamo, solo devuelve una sugerencia.

    Reglas (usando umbrales de Configuraciones_Generales):
    - liquidado: deuda_actual == 0
    - activo: dentro del plazo o dentro de gracia
    - en_mora_parcial: 0 < dias_mora < UMBRAL_MORA_GRAVE_DIAS
    - en_mora_grave: dias_mora >= UMBRAL_MORA_GRAVE_DIAS
    - incobrable: dias_mora >= UMBRAL_INCOBRABLE_DIAS
    """
    # Obtener umbrales desde BD
    umbral_mora_grave = await _obtener_config_int(db, "UMBRAL_MORA_GRAVE_DIAS", 15)
    umbral_incobrable = await _obtener_config_int(db, "UMBRAL_INCOBRABLE_DIAS", 60)

    # Si no hay deuda, está liquidado
    if prestamo.deuda_actual <= Decimal("0"):
        return {"codigo": "liquidado", "razon": "deuda_cero", "dias_mora": 0}

    # Calcular días de mora (después de vencimiento + gracia)
    frontera_gracia = prestamo.fecha_vencimiento + timedelta(days=dias_gracia)

    if fecha_corte <= frontera_gracia:
        # Dentro del plazo o dentro de gracia
        return {"codigo": "activo", "razon": "en_plazo_o_gracia", "dias_mora": 0}

    # Calcular días de mora
    dias_mora = (fecha_corte - frontera_gracia).days

    # Aplicar umbrales desde configuración
    if dias_mora >= umbral_incobrable:
        return {"codigo": "incobrable", "razon": "mora_critica", "dias_mora": dias_mora}

    if dias_mora >= umbral_mora_grave:
        return {"codigo": "en_mora_grave", "razon": "mora_severa", "dias_mora": dias_mora}

    # Mora parcial (1 a umbral_mora_grave-1 días)
    return {"codigo": "en_mora_parcial", "razon": "mora_leve", "dias_mora": dias_mora}


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================
@router.post(
    "/{id_prestamo}/recalcular",
    response_model=RecalculoOut,
    status_code=status.HTTP_200_OK,
    summary="Recalcular interés y mora de un préstamo",
    description=(
        "Actualiza los acumulados de interés y mora de un préstamo desde la última "
        "fecha de cálculo hasta una fecha de corte (por defecto hoy). "
        "Operación idempotente: llamar múltiples veces con la misma fecha no duplica cálculos. "
        "\n\n**Reglas (PASO 6):**\n"
        "- Interés: se aplica diariamente sobre deuda_actual\n"
        "- Mora: solo después de (fecha_vencimiento + dias_gracia)\n"
        "- Estados derivados: activo → en_mora_parcial → en_mora_grave → incobrable → liquidado"
    )
)
async def recalcular_prestamo(
    id_prestamo: int,
    payload: RecalculoIn = Body(default=RecalculoIn()),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recalcula interés y mora de un préstamo según flujo del PASO 6.

    ## Orden de aplicación:
    1. **Interés diario**: deuda_actual × tasa_interes_diaria
    2. **Mora diaria**: solo si fecha > (vencimiento + gracia)

    ## Estados (según días de mora):
    - `activo`: dentro de plazo o gracia
    - `en_mora_parcial`: 1-14 días (por defecto)
    - `en_mora_grave`: 15-59 días (por defecto)
    - `incobrable`: 60+ días (por defecto)
    - `liquidado`: deuda_actual == 0

    ## Permisos requeridos:
    - ADMIN, CAJERO, OPERADOR
    """

    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)

    # Crear adaptador para utils.roles
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)

    roles_permitidos = ["ADMIN", "CAJERO", "OPERADOR"]
    tiene_permiso = await usuario_tiene_algun_rol(
        current_user, db, roles_permitidos
    )

    if not tiene_permiso:
        raise HTTPException(
            status_code=403,
            detail=f"Requiere uno de estos roles: {', '.join(roles_permitidos)}"
        )

    # 2) Cargar préstamo con lock (SELECT FOR UPDATE)
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

    # 3) Validar estado del préstamo (solo recalcular activos o en mora)
    result_estado = await db.execute(
        select(EstadoPrestamo).where(
            EstadoPrestamo.id_estado_prestamo == prestamo.id_estado
        )
    )
    estado_actual = result_estado.scalar_one_or_none()
    estados_permitidos = ["activo", "en_mora_parcial", "en_mora_grave"]

    if estado_actual and estado_actual.nombre.lower() not in estados_permitidos:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede recalcular un préstamo en estado '{estado_actual.nombre}'"
        )

    # 4) Determinar fecha de corte
    fecha_corte = payload.fecha_corte or date.today()

    # 5) Validar que fecha_corte >= fecha_inicio
    if fecha_corte < prestamo.fecha_inicio:
        raise HTTPException(
            status_code=422,
            detail=f"fecha_corte ({fecha_corte}) no puede ser anterior a fecha_inicio ({prestamo.fecha_inicio})"
        )

    # 6) Determinar inicio del periodo (según PASO 6)
    # COALESCE(ultimo_calculo_en, fecha_inicio - 1) + 1
    if prestamo.ultimo_calculo_en:
        inicio_periodo = prestamo.ultimo_calculo_en + timedelta(days=1)
    else:
        # Primera vez: desde fecha_inicio
        inicio_periodo = prestamo.fecha_inicio

    # Asegurar que no sea anterior a fecha_inicio
    if inicio_periodo < prestamo.fecha_inicio:
        inicio_periodo = prestamo.fecha_inicio

    # 7) Validar que no estemos retrocediendo
    if fecha_corte < inicio_periodo:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede recalcular hacia atrás: fecha_corte ({fecha_corte}) < inicio ({inicio_periodo})"
        )

    # 8) Idempotencia: si ya calculamos hasta esta fecha, retornar sin cambios
    dias_total = (fecha_corte - inicio_periodo).days + 1
    if dias_total <= 0:
        estado_info = await _derivar_estado_sugerido(prestamo, fecha_corte, 3, db)
        return RecalculoOut(
            id_prestamo=prestamo.id_prestamo,
            fecha_corte=fecha_corte,
            dias_acumulados=0,
            interes_agregado=0.0,
            mora_agregada=0.0,
            deuda_actual=float(prestamo.deuda_actual),
            interes_acumulada=float(prestamo.interes_acumulada),
            mora_acumulada=float(prestamo.mora_acumulada),
            ultimo_calculo_en=prestamo.ultimo_calculo_en or prestamo.fecha_inicio,
            estado_prestamo={
                "id": estado_actual.id_estado_prestamo if estado_actual else 0,
                "codigo": estado_info["codigo"],
                "dias_mora": estado_info["dias_mora"]
            }
        )

    # 9) Obtener configuraciones (según PASO 6)
    tasa_interes = payload.tasa_interes_diaria or await _obtener_config_decimal(
        db, "TASA_INTERES_DIARIO", Decimal("0.0005")
    )
    tasa_mora = payload.tasa_mora_diaria or await _obtener_config_decimal(
        db, "MORA_DIARIA", Decimal("0.001")
    )
    dias_gracia = payload.dias_gracia if payload.dias_gracia is not None else await _obtener_config_int(
        db, "GRACIA_DIAS", 3
    )

    # Validar tasas
    if tasa_interes < 0 or tasa_mora < 0:
        raise HTTPException(
            status_code=422,
            detail="Las tasas no pueden ser negativas"
        )

    # 10) Calcular día por día (según PASO 6, sección 3)
    valores_anteriores = {
        "deuda_actual": float(prestamo.deuda_actual),
        "interes_acumulada": float(prestamo.interes_acumulada),
        "mora_acumulada": float(prestamo.mora_acumulada),
        "ultimo_calculo_en": str(prestamo.ultimo_calculo_en) if prestamo.ultimo_calculo_en else None
    }

    interes_total_agregado = Decimal("0")
    mora_total_agregada = Decimal("0")
    frontera_gracia = prestamo.fecha_vencimiento + timedelta(days=dias_gracia)

    # Procesar cada día del periodo
    fecha_actual = inicio_periodo
    while fecha_actual <= fecha_corte:
        # Interés diario (siempre se aplica)
        interes_dia = round(prestamo.deuda_actual * tasa_interes, 2)
        if interes_dia > 0:
            interes_total_agregado += interes_dia
            # Crear movimiento de interés
            mov_interes = PrestamoMovimiento(
                id_prestamo=prestamo.id_prestamo,
                tipo="interes",
                monto=interes_dia,
                nota=f"Interés diario del {fecha_actual.isoformat()}",
                fecha=datetime.combine(fecha_actual, datetime.min.time()).replace(tzinfo=timezone.utc)
            )
            db.add(mov_interes)

        # Mora diaria (solo si estamos después de gracia)
        if fecha_actual > frontera_gracia:
            mora_dia = round(prestamo.deuda_actual * tasa_mora, 2)
            if mora_dia > 0:
                mora_total_agregada += mora_dia
                # Crear movimiento de mora
                mov_mora = PrestamoMovimiento(
                    id_prestamo=prestamo.id_prestamo,
                    tipo="mora",
                    monto=mora_dia,
                    nota=f"Mora diaria del {fecha_actual.isoformat()}",
                    fecha=datetime.combine(fecha_actual, datetime.min.time()).replace(tzinfo=timezone.utc)
                )
                db.add(mov_mora)

        fecha_actual += timedelta(days=1)

    # 11) Actualizar acumulados del préstamo
    prestamo.interes_acumulada = round(
        Decimal(str(prestamo.interes_acumulada)) + interes_total_agregado, 2
    )
    prestamo.mora_acumulada = round(
        Decimal(str(prestamo.mora_acumulada)) + mora_total_agregada, 2
    )
    # NOTA: deuda_actual NO se modifica aquí (es el capital inicial)
    # Los intereses y mora se acumulan por separado
    prestamo.ultimo_calculo_en = fecha_corte
    prestamo.updated_at = datetime.now(timezone.utc)

    # 12) Derivar y actualizar estado según días de mora (o liquidación)
    estado_sugerido_info = await _derivar_estado_sugerido(prestamo, fecha_corte, dias_gracia, db)
    estado_sugerido = await _obtener_estado_prestamo(db, estado_sugerido_info["codigo"])

    # Actualizar estado si cambió
    if estado_sugerido and prestamo.id_estado != estado_sugerido.id_estado_prestamo:
        prestamo.id_estado = estado_sugerido.id_estado_prestamo

    # 13) Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="RECALCULO_PRESTAMO",
        modulo="Prestamo",
        detalle=(
            f"Recálculo préstamo {id_prestamo} del {inicio_periodo} al {fecha_corte}. "
            f"Agregado: Q{float(interes_total_agregado):.2f} interés, "
            f"Q{float(mora_total_agregada):.2f} mora. "
            f"Estado: {estado_sugerido_info['codigo']} ({estado_sugerido_info['dias_mora']} días mora)"
        ),
        valores_anteriores=valores_anteriores,
        valores_nuevos={
            "deuda_actual": float(prestamo.deuda_actual),
            "interes_acumulada": float(prestamo.interes_acumulada),
            "mora_acumulada": float(prestamo.mora_acumulada),
            "ultimo_calculo_en": str(fecha_corte),
            "estado": estado_sugerido_info["codigo"]
        }
    )

    # 14) Commit
    try:
        await db.commit()
        await db.refresh(prestamo)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al guardar el recálculo: {str(e)}"
        )

    # 15) Respuesta
    return RecalculoOut(
        id_prestamo=prestamo.id_prestamo,
        fecha_corte=fecha_corte,
        dias_acumulados=dias_total - 1,  # Días reales procesados
        interes_agregado=float(interes_total_agregado),
        mora_agregada=float(mora_total_agregada),
        deuda_actual=float(prestamo.deuda_actual),
        interes_acumulada=float(prestamo.interes_acumulada),
        mora_acumulada=float(prestamo.mora_acumulada),
        ultimo_calculo_en=fecha_corte,
        estado_prestamo={
            "id": estado_sugerido.id_estado_prestamo if estado_sugerido else 0,
            "codigo": estado_sugerido_info["codigo"],
            "razon": estado_sugerido_info["razon"],
            "dias_mora": estado_sugerido_info["dias_mora"]
        } if estado_sugerido else None
    )
