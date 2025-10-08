from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.pago import Pago
from app.db.models.prestamo import Prestamo
from app.db.models.estado_pago import EstadoPago
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.prestamo_movimiento import PrestamoMovimiento
from app.db.models.user import User

# Schemas
from app.schemas.pagos_validar import ValidarPagoRequest, ValidarPagoResponse

# Utilidades (no las tocamos)
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/pagos", tags=["Pagos - Validación"])


def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


class _UserIdAdapter:
    """
    Adaptador local para NO tocar utils.roles.
    Expone la propiedad 'id_usuario' aunque el modelo real use 'ID_Usuario' o 'id'.
    """
    def __init__(self, user_id: int):
        self.id_usuario = user_id


async def _obtener_estado_pago(db: AsyncSession, nombre: str) -> EstadoPago:
    """Obtiene un estado de pago por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoPago).where(func.lower(EstadoPago.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de pago '{nombre}' no existe en catálogo",
        )
    return estado


async def _obtener_estado_prestamo(db: AsyncSession, nombre: str) -> EstadoPrestamo:
    """Obtiene un estado de préstamo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoPrestamo).where(func.lower(EstadoPrestamo.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de préstamo '{nombre}' no existe en catálogo",
        )
    return estado


async def _obtener_estado_prestamo_flexible(
    db: AsyncSession, nombres: Iterable[str]
) -> EstadoPrestamo | None:
    """
    Devuelve el primer estado de préstamo que exista en catálogo de la lista de nombres (case-insensitive).
    Si no hay ninguno, retorna None.
    """
    for nombre in nombres:
        try:
            return await _obtener_estado_prestamo(db, nombre)
        except HTTPException:
            continue
    return None


async def _tiene_rol_fallback(db: AsyncSession, user_id: int, roles: list[str]) -> bool:
    """
    Verificación de roles directa contra tus tablas reales (Roles / Usuario_Rol),
    por si la utilidad utils.roles no coincide con los nombres de tu esquema.
    """
    q = text("""
        SELECT 1
        FROM Usuario_Rol ur
        JOIN Roles r ON r.ID_Rol = ur.ID_Rol
        WHERE ur.ID_Usuario = :uid
          AND LOWER(r.Nombre) IN :rn
        LIMIT 1
    """)
    # Nota: el IN con tupla requiere pasarla así:
    params = {"uid": user_id, "rn": tuple(n.lower() for n in roles)}
    result = await db.execute(q, params)
    return result.scalar_one_or_none() is not None


def _aplicar_pago_a_saldos(
    monto_pago: Decimal,
    mora_actual: Decimal,
    interes_actual: Decimal,
    deuda_actual: Decimal,
) -> dict:
    """
    Aplica el monto del pago siguiendo el orden: mora → interés → capital.
    Retorna un dict con el desglose de aplicación y los nuevos saldos.
    """
    restante = monto_pago
    aplicado_mora = Decimal("0.00")
    aplicado_interes = Decimal("0.00")
    aplicado_capital = Decimal("0.00")

    # 1) Mora
    if restante > Decimal("0") and mora_actual > Decimal("0"):
        aplicado_mora = min(restante, mora_actual)
        restante -= aplicado_mora

    # 2) Interés
    if restante > Decimal("0") and interes_actual > Decimal("0"):
        aplicado_interes = min(restante, interes_actual)
        restante -= aplicado_interes

    # 3) Capital
    if restante > Decimal("0") and deuda_actual > Decimal("0"):
        aplicado_capital = min(restante, deuda_actual)
        restante -= aplicado_capital

    nuevo_mora = mora_actual - aplicado_mora
    nuevo_interes = interes_actual - aplicado_interes
    nuevo_capital = deuda_actual - aplicado_capital

    return {
        "aplicado_mora": aplicado_mora,
        "aplicado_interes": aplicado_interes,
        "aplicado_capital": aplicado_capital,
        "nuevo_mora": nuevo_mora,
        "nuevo_interes": nuevo_interes,
        "nuevo_capital": nuevo_capital,
    }


@router.post(
    "/{id_pago}/validar",
    response_model=ValidarPagoResponse,
    status_code=status.HTTP_200_OK,
    summary="Validar un pago pendiente",
    description=(
        "Valida un pago pendiente, aplica el monto a los saldos del préstamo "
        "(mora → interés → capital), actualiza el estado del pago a 'validado', "
        "crea el movimiento de abono y registra auditoría. Operación idempotente."
    ),
)
async def validar_pago(
    id_pago: int,
    payload: ValidarPagoRequest = Body(default=ValidarPagoRequest()),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) Verificar permisos (CAJERO, ADMIN, OPERADOR)
    user_id = _resolve_user_id(current_user)
    user_adapter = _UserIdAdapter(user_id)  # para utils.roles
    roles_permitidos = ["CAJERO", "ADMIN", "OPERADOR"]

    allowed = await usuario_tiene_algun_rol(user_adapter, db, roles_permitidos)
    if not allowed:
        # Fallback a consulta directa por si utils.roles no coincide con tu esquema
        allowed = await _tiene_rol_fallback(db, user_id, roles_permitidos)

    if not allowed:
        raise HTTPException(status_code=403, detail="No tiene permiso para validar pagos")

    # 2) Buscar el pago
    result_pago = await db.execute(select(Pago).where(Pago.id_pago == id_pago))
    pago = result_pago.scalar_one_or_none()
    if not pago:
        raise HTTPException(status_code=404, detail=f"Pago {id_pago} no encontrado")

    # 3) Validar que esté en estado 'pendiente'
    result_estado_pago = await db.execute(
        select(EstadoPago).where(EstadoPago.id_estado_pago == pago.id_estado)
    )
    estado_actual_pago = result_estado_pago.scalar_one_or_none()
    if not estado_actual_pago or estado_actual_pago.nombre.lower() != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"El pago está en estado '{estado_actual_pago.nombre if estado_actual_pago else 'desconocido'}', no se puede validar",
        )

    # 4) Buscar el préstamo asociado
    result_prestamo = await db.execute(
        select(Prestamo).where(Prestamo.id_prestamo == pago.id_prestamo)
    )
    prestamo = result_prestamo.scalar_one_or_none()
    if not prestamo:
        raise HTTPException(
            status_code=404,
            detail=f"Préstamo {pago.id_prestamo} asociado al pago no encontrado",
        )

    # 5) Validar que el préstamo admita pagos
    result_estado_prestamo = await db.execute(
        select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
    )
    estado_actual_prestamo = result_estado_prestamo.scalar_one_or_none()
    estados_admitidos = {"activo", "en_mora_parcial", "en_mora_grave", "aprobado_pendiente_entrega"}
    if (not estado_actual_prestamo) or (estado_actual_prestamo.nombre.lower() not in estados_admitidos):
        raise HTTPException(
            status_code=409,
            detail=f"El préstamo está en estado '{estado_actual_prestamo.nombre if estado_actual_prestamo else 'desconocido'}', no admite pagos",
        )

    # 6) Validar monto del pago
    monto_pago = Decimal(str(pago.monto))
    if monto_pago <= Decimal("0"):
        raise HTTPException(status_code=400, detail="El monto del pago debe ser mayor a 0")

    # 7) Saldos actuales
    mora_actual = Decimal(str(prestamo.mora_acumulada))
    interes_actual = Decimal(str(prestamo.interes_acumulada))
    deuda_actual = Decimal(str(prestamo.deuda_actual))

    # 8) Aplicar pago
    aplicacion = _aplicar_pago_a_saldos(monto_pago, mora_actual, interes_actual, deuda_actual)

    # 9) Actualizar saldos del préstamo
    prestamo.mora_acumulada = aplicacion["nuevo_mora"]
    prestamo.interes_acumulada = aplicacion["nuevo_interes"]
    prestamo.deuda_actual = aplicacion["nuevo_capital"]
    prestamo.updated_at = datetime.now(timezone.utc)

    # 10) Determinar nuevo estado del préstamo
    saldo_total = aplicacion["nuevo_mora"] + aplicacion["nuevo_interes"] + aplicacion["nuevo_capital"]

    if saldo_total == Decimal("0"):
        # Intentar 'cancelado' y si no existe, probar sinónimos comunes.
        estado_cancel = await _obtener_estado_prestamo_flexible(
            db,
            ["cancelado", "completado", "pagado", "cerrado", "finalizado"]
        )
        if estado_cancel:
            prestamo.id_estado = estado_cancel.id_estado_prestamo
        # si ninguno existe, dejamos el estado como está (no rompemos la operación)
    elif aplicacion["nuevo_mora"] == Decimal("0") and aplicacion["nuevo_interes"] == Decimal("0"):
        # Si estaba en mora y ahora quedó al día
        if estado_actual_prestamo.nombre.lower() in {"en_mora_parcial", "en_mora_grave"}:
            estado_activo = await _obtener_estado_prestamo_flexible(db, ["activo"])
            if estado_activo:
                prestamo.id_estado = estado_activo.id_estado_prestamo

    # 11) Actualizar estado del pago a 'validado'
    estado_validado = await _obtener_estado_pago(db, "validado")
    pago.id_estado = estado_validado.id_estado_pago
    pago.id_validador = user_id

    # 12) Crear movimiento de abono
    nota_detallada = (
        f"Abono aplicado: Mora Q{float(aplicacion['aplicado_mora']):.2f}, "
        f"Interés Q{float(aplicacion['aplicado_interes']):.2f}, "
        f"Capital Q{float(aplicacion['aplicado_capital']):.2f}"
    )
    if payload.nota:
        nota_detallada += f" | {payload.nota}"

    movimiento = PrestamoMovimiento(
        id_prestamo=prestamo.id_prestamo,
        tipo="abono",
        monto=monto_pago,
        nota=nota_detallada,
        fecha=datetime.now(timezone.utc),
    )
    db.add(movimiento)

    # 13) Auditoría
    valores_nuevos_estado = {
        "prestamo_estado": (
            await db.execute(
                select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
            )
        ).scalar_one().nombre
    }

    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="VALIDAR_PAGO",
        modulo="Pago",
        detalle=(
            f"Pago {id_pago} validado. Aplicado: Mora Q{float(aplicacion['aplicado_mora']):.2f}, "
            f"Interés Q{float(aplicacion['aplicado_interes']):.2f}, "
            f"Capital Q{float(aplicacion['aplicado_capital']):.2f}. "
            f"Préstamo {prestamo.id_prestamo} nuevo estado: {prestamo.id_estado}"
        ),
        valores_anteriores={
            "pago_estado": estado_actual_pago.nombre,
            "prestamo_mora": float(mora_actual),
            "prestamo_interes": float(interes_actual),
            "prestamo_deuda": float(deuda_actual),
            "prestamo_estado": estado_actual_prestamo.nombre,
        },
        valores_nuevos={
            "pago_estado": "validado",
            "prestamo_mora": float(prestamo.mora_acumulada),
            "prestamo_interes": float(prestamo.interes_acumulada),
            "prestamo_deuda": float(prestamo.deuda_actual),
            **valores_nuevos_estado,
        },
    )

    # 14) Commit
    try:
        await db.commit()
        await db.refresh(pago)
        await db.refresh(prestamo)
        await db.refresh(movimiento)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al validar el pago: {str(e)}")

    # 15) Estado final para respuesta
    result_estado_final = await db.execute(
        select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
    )
    estado_final = result_estado_final.scalar_one()

    # 16) Respuesta
    return ValidarPagoResponse(
        id_pago=pago.id_pago,
        estado="validado",
        aplicacion={
            "mora": float(aplicacion["aplicado_mora"]),
            "interes": float(aplicacion["aplicado_interes"]),
            "capital": float(aplicacion["aplicado_capital"]),
        },
        prestamo={
            "id": prestamo.id_prestamo,
            "estado": estado_final.nombre,
            "deuda_actual": float(prestamo.deuda_actual),
            "mora_acumulada": float(prestamo.mora_acumulada),
            "interes_acumulada": float(prestamo.interes_acumulada),
        },
    )
