# ============================================================
# app/api/routers/prestamos_recalcular_bulk.py
# ============================================================
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

# Deps
from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.prestamo_movimiento import PrestamoMovimiento
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.db.models.user import User

# Schemas
from app.schemas.recalculo_bulk import (
    RecalculoBulkBody,
    RecalculoBulkOut,
    RecalculoItemOut,
)

# Utilidades
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Recálculo Bulk"])


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


def _q2(x: Decimal) -> Decimal:
    """Redondeo financiero a 2 decimales."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ============================================================
# CÁLCULO DE UN PRÉSTAMO
# ============================================================
async def _calcular_un_prestamo(
    prestamo: Prestamo,
    fecha_corte: date,
    tasa_interes: Decimal,
    tasa_mora: Decimal,
    dias_gracia: int,
    modo_preciso: bool,
    db: AsyncSession
) -> dict:
    """
    Lógica de cálculo para UN préstamo (interés simple + mora post-gracia).
    - Interés diario SIEMPRE.
    - Mora diaria DESPUÉS de (fecha_vencimiento + dias_gracia).
    - Acumula interés/mora y ACTUALIZA deuda_actual.
    - Idempotente: si no hay días, sin cambios.
    """

    # 1) Determinar inicio del periodo
    if prestamo.ultimo_calculo_en:
        inicio_periodo = prestamo.ultimo_calculo_en + timedelta(days=1)
    else:
        inicio_periodo = prestamo.fecha_inicio

    # 2) Validaciones de tiempo (retroceso)
    if fecha_corte < inicio_periodo:
        raise ValueError(f"Retroceso temporal: fecha_corte ({fecha_corte}) < inicio ({inicio_periodo})")

    # 3) Días del periodo (inclusivo)
    dias_total = (fecha_corte - inicio_periodo).days + 1
    if dias_total <= 0:
        return {
            "dias_acumulados": 0,
            "interes_agregado": Decimal("0"),
            "mora_agregada": Decimal("0"),
            "sin_cambios": True
        }

    # 4) Cálculo (base simple = deuda al inicio)
    interes_total_agregado = Decimal("0")
    mora_total_agregada = Decimal("0")
    frontera_gracia = prestamo.fecha_vencimiento + timedelta(days=dias_gracia)

    base = Decimal(str(prestamo.deuda_actual))

    fecha_actual = inicio_periodo
    while fecha_actual <= fecha_corte:
        # Interés diario
        interes_dia = _q2(base * tasa_interes)
        if interes_dia > 0:
            interes_total_agregado += interes_dia
            db.add(PrestamoMovimiento(
                id_prestamo=prestamo.id_prestamo,
                tipo="interes",
                monto=float(interes_dia),
                nota=f"Interés diario del {fecha_actual.isoformat()}",
                fecha=datetime.combine(fecha_actual, datetime.min.time()).replace(tzinfo=timezone.utc)
            ))

        # Mora diaria después de gracia
        if fecha_actual > frontera_gracia:
            mora_dia = _q2(base * tasa_mora)
            if mora_dia > 0:
                mora_total_agregada += mora_dia
                db.add(PrestamoMovimiento(
                    id_prestamo=prestamo.id_prestamo,
                    tipo="mora",
                    monto=float(mora_dia),
                    nota=f"Mora diaria del {fecha_actual.isoformat()}",
                    fecha=datetime.combine(fecha_actual, datetime.min.time()).replace(tzinfo=timezone.utc)
                ))

        fecha_actual += timedelta(days=1)

    # 5) Actualizar acumulados y deuda total
    prestamo.interes_acumulada = _q2(Decimal(str(prestamo.interes_acumulada)) + interes_total_agregado)
    prestamo.mora_acumulada    = _q2(Decimal(str(prestamo.mora_acumulada)) + mora_total_agregada)
    prestamo.deuda_actual      = _q2(Decimal(str(prestamo.deuda_actual)) + interes_total_agregado + mora_total_agregada)
    if prestamo.deuda_actual < 0:
        prestamo.deuda_actual = Decimal("0.00")

    prestamo.ultimo_calculo_en = fecha_corte
    prestamo.updated_at = datetime.now(timezone.utc)

    return {
        "dias_acumulados": dias_total,
        "interes_agregado": interes_total_agregado,
        "mora_agregada": mora_total_agregada,
        "sin_cambios": False
    }


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================
@router.post(
    "/recalcular",
    response_model=RecalculoBulkOut,
    status_code=status.HTTP_200_OK,
    summary="Recalcular interés y mora de múltiples préstamos (lote)",
    description=(
        "Ejecuta el recálculo de interés y mora para múltiples préstamos en una sola operación. "
        "Ideal para ejecutar desde un cron/scheduler diario."
    ),
)
async def recalcular_prestamos_bulk(
    # Query params (filtros)
    older_than_days: Optional[int] = Query(None, ge=0, le=365, description="Préstamos no calculados en N+ días"),
    solo_en_mora: Optional[bool] = Query(False, description="Solo préstamos en mora"),
    limit: Optional[int] = Query(500, ge=1, le=5000, description="Tamaño del lote"),
    offset: Optional[int] = Query(0, ge=0, description="Desplazamiento para paginación"),
    ids: Optional[str] = Query(None, description="IDs específicos separados por coma (ej: 5001,5002,5003)"),
    # Body (config cálculo)
    payload: RecalculoBulkBody = Body(default=RecalculoBulkBody()),
    # Deps
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recalcula interés y mora para múltiples préstamos según filtros.
    Devuelve estadísticas agregadas y detalle por préstamo.
    """
    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)

    roles_permitidos = ["ADMIN", "CAJERO", "OPERADOR"]
    tiene_permiso = await usuario_tiene_algun_rol(current_user, db, roles_permitidos)
    if not tiene_permiso:
        raise HTTPException(status_code=403, detail=f"Requiere uno de estos roles: {', '.join(roles_permitidos)}")

    # 2) Determinar fecha de corte y configs
    fecha_corte = payload.fecha_corte or date.today()
    tasa_interes = payload.tasa_interes_diaria or await _obtener_config_decimal(db, "TASA_INTERES_DIARIO", Decimal("0.0005"))
    tasa_mora    = payload.tasa_mora_diaria    or await _obtener_config_decimal(db, "MORA_DIARIA",         Decimal("0.001"))
    dias_gracia  = payload.dias_gracia if payload.dias_gracia is not None else await _obtener_config_int(db, "GRACIA_DIAS", 3)

    # 3) Construir query de candidatos
    stmt = select(Prestamo).where(Prestamo.fecha_inicio <= fecha_corte)

    # Excluir estados terminales
    estados_excluir = ["cancelado", "liquidado"]
    result_estados = await db.execute(
        select(EstadoPrestamo.id_estado_prestamo).where(func.lower(EstadoPrestamo.nombre).in_(estados_excluir))
    )
    ids_estados_excluir = [row[0] for row in result_estados.all()]
    if ids_estados_excluir:
        stmt = stmt.where(Prestamo.id_estado.notin_(ids_estados_excluir))

    # Filtro por IDs (prioritario)
    if ids:
        try:
            ids_list = [int(x.strip()) for x in ids.split(",") if x.strip()]
            if ids_list:
                stmt = stmt.where(Prestamo.id_prestamo.in_(ids_list))
        except ValueError:
            raise HTTPException(status_code=422, detail="IDs inválidos en el parámetro 'ids'")
    else:
        # older_than_days
        if older_than_days is not None:
            fecha_limite = date.today() - timedelta(days=older_than_days)
            stmt = stmt.where(or_(Prestamo.ultimo_calculo_en.is_(None), Prestamo.ultimo_calculo_en <= fecha_limite))

        # solo_en_mora
        if solo_en_mora:
            estados_mora = ["en_mora_parcial", "en_mora_grave"]
            result_estados_mora = await db.execute(
                select(EstadoPrestamo.id_estado_prestamo).where(func.lower(EstadoPrestamo.nombre).in_(estados_mora))
            )
            ids_estados_mora = [row[0] for row in result_estados_mora.all()]
            if ids_estados_mora:
                stmt = stmt.where(Prestamo.id_estado.in_(ids_estados_mora))

    # Paginación
    stmt = stmt.order_by(Prestamo.id_prestamo).limit(limit).offset(offset)

    # 4) Obtener candidatos
    result = await db.execute(stmt)
    candidatos = result.scalars().all()
    total_candidatos = len(candidatos)

    # 5) Procesar cada préstamo en su propia transacción corta
    stats = {"procesados": 0, "actualizados": 0, "sin_cambios": 0, "saltados": 0}
    detalle: List[RecalculoItemOut] = []

    for prestamo in candidatos:
        stats["procesados"] += 1
        try:
            # Bloqueo fila (SELECT FOR UPDATE)
            async with db.begin_nested():  # Savepoint
                result_locked = await db.execute(
                    select(Prestamo).where(Prestamo.id_prestamo == prestamo.id_prestamo).with_for_update()
                )
                p_locked = result_locked.scalar_one_or_none()
                if not p_locked:
                    stats["saltados"] += 1
                    detalle.append(RecalculoItemOut(
                        id_prestamo=prestamo.id_prestamo,
                        dias_acumulados=0,
                        interes_agregado=0.0,
                        mora_agregada=0.0,
                        deuda_actual=float(prestamo.deuda_actual),
                        interes_acumulada=float(prestamo.interes_acumulada),
                        mora_acumulada=float(prestamo.mora_acumulada),
                        ultimo_calculo_en=prestamo.ultimo_calculo_en or prestamo.fecha_inicio,
                        resultado="saltado",
                        motivo="No se pudo obtener el bloqueo del préstamo"
                    ))
                    continue

                # Calcular y actualizar
                resultado = await _calcular_un_prestamo(
                    p_locked, fecha_corte, tasa_interes, tasa_mora, dias_gracia, payload.modo_preciso, db
                )

                if resultado["sin_cambios"]:
                    stats["sin_cambios"] += 1
                    resultado_str = "sin_cambios"
                else:
                    stats["actualizados"] += 1
                    resultado_str = "actualizado"

                detalle.append(RecalculoItemOut(
                    id_prestamo=p_locked.id_prestamo,
                    dias_acumulados=resultado["dias_acumulados"],
                    interes_agregado=float(resultado["interes_agregado"]),
                    mora_agregada=float(resultado["mora_agregada"]),
                    deuda_actual=float(p_locked.deuda_actual),
                    interes_acumulada=float(p_locked.interes_acumulada),
                    mora_acumulada=float(p_locked.mora_acumulada),
                    ultimo_calculo_en=p_locked.ultimo_calculo_en,
                    resultado=resultado_str
                ))

                await db.commit()

        except ValueError as e:
            stats["saltados"] += 1
            detalle.append(RecalculoItemOut(
                id_prestamo=prestamo.id_prestamo,
                dias_acumulados=0,
                interes_agregado=0.0,
                mora_agregada=0.0,
                deuda_actual=float(prestamo.deuda_actual),
                interes_acumulada=float(prestamo.interes_acumulada),
                mora_acumulada=float(prestamo.mora_acumulada),
                ultimo_calculo_en=prestamo.ultimo_calculo_en or prestamo.fecha_inicio,
                resultado="saltado",
                motivo=str(e)
            ))
            await db.rollback()
            continue

        except Exception as e:
            stats["saltados"] += 1
            detalle.append(RecalculoItemOut(
                id_prestamo=prestamo.id_prestamo,
                dias_acumulados=0,
                interes_agregado=0.0,
                mora_agregada=0.0,
                deuda_actual=float(prestamo.deuda_actual),
                interes_acumulada=float(prestamo.interes_acumulada),
                mora_acumulada=float(prestamo.mora_acumulada),
                ultimo_calculo_en=prestamo.ultimo_calculo_en or prestamo.fecha_inicio,
                resultado="saltado",
                motivo=f"Error: {type(e).__name__} - {str(e)}"
            ))
            await db.rollback()
            continue

    # 6) Auditoría consolidada del lote
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="RECALCULO_PRESTAMOS_BULK",
        modulo="Prestamo",
        detalle=(
            f"Recálculo en lote del {fecha_corte.isoformat()}. "
            f"Total candidatos: {total_candidatos}, "
            f"Procesados: {stats['procesados']}, "
            f"Actualizados: {stats['actualizados']}, "
            f"Sin cambios: {stats['sin_cambios']}, "
            f"Saltados: {stats['saltados']}"
        ),
        valores_nuevos={
            "fecha_corte": str(fecha_corte),
            "tasa_interes_diaria": float(tasa_interes),
            "tasa_mora_diaria": float(tasa_mora),
            "dias_gracia": dias_gracia,
            "stats": stats
        }
    )
    await db.commit()

    # 7) Respuesta
    return RecalculoBulkOut(
        total_candidatos=total_candidatos,
        procesados=stats["procesados"],
        actualizados=stats["actualizados"],
        sin_cambios=stats["sin_cambios"],
        saltados=stats["saltados"],
        detalle=detalle
    )
