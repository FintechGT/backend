# app/api/routers/crear_pagos.py
from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# MODELOS (ajusta rutas si difieren)
from app.db.models.prestamo import Prestamo
from app.db.models.pago import Pago
from app.db.models.comprobante import Comprobante
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.estado_pago import EstadoPago

from app.schemas.crear_pagos import CrearPagoIn, CrearPagoOut
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/crear-pagos", tags=["Crear-Pagos"])

# Estados de préstamo que admiten pagos
ESTADOS_PRESTAMO_ADMITE = {"activo", "en_mora_parcial", "en_mora_grave", "aprobado_pendiente_entrega"}
PAGO_ESTADO_PENDIENTE_TXT = "pendiente"


# ---------------------- Helpers de atributos (case-friendly) ----------------------
def _attr(model, names: Iterable[str]) -> str:
    """Devuelve el primer nombre de atributo que exista en el modelo."""
    for n in names:
        if hasattr(model, n):
            return n
    raise RuntimeError(f"{model.__name__}: ninguno de {list(names)} existe como atributo del modelo")

def _get(obj, names: Iterable[str]):
    """Obtiene un valor del objeto probando múltiples nombres de atributo."""
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return None

def _set_kw(model, names, value, into: dict):
    """Asigna al dict la clave correcta (según el atributo existente en el modelo)."""
    k = _attr(model, names)
    into[k] = value

def _resolve_user_id(user) -> int | None:
    for n in ("id_usuario", "ID_Usuario", "id"):
        v = getattr(user, n, None)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None
# ------------------------------------------------------------------------------


async def _get_estado_pago_pendiente_id(db: AsyncSession) -> int:
    row = (await db.execute(
        select(EstadoPago).where(EstadoPago.nombre.ilike(PAGO_ESTADO_PENDIENTE_TXT))
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=500, detail="Catálogo EstadoPago no contiene 'pendiente'")
    # id_estado_pago | Id_estado_pago
    return _get(row, ("id_estado_pago", "Id_estado_pago"))


@router.post(
    "",
    response_model=CrearPagoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un pago en estado pendiente"
)
async def crear_pago_pendiente(
    data: CrearPagoIn,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    # 1) Validar préstamo (id_prestamo | Id_prestamo | ID_Prestamo)
    prestamo_id_col = _attr(Prestamo, ("id_prestamo", "Id_prestamo", "ID_Prestamo"))
    prestamo = (await db.execute(
        select(Prestamo).where(getattr(Prestamo, prestamo_id_col) == data.id_prestamo)
    )).scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail=f"Préstamo {data.id_prestamo} no encontrado")

    # 2) Verificar estado del préstamo (id_estado | Id_estado)
    prestamo_id_estado_attr = _attr(Prestamo, ("id_estado", "Id_estado"))
    estado_prestamo_id = getattr(prestamo, prestamo_id_estado_attr)
    est = (await db.execute(
        select(EstadoPrestamo).where(
            getattr(EstadoPrestamo, _attr(EstadoPrestamo, ("id_estado_prestamo", "Id_estado_prestamo")))
            == estado_prestamo_id
        )
    )).scalar_one_or_none()

    est_nombre = (getattr(est, "nombre", None) or getattr(est, "Nombre", None) or "").lower()
    if not est or est_nombre not in ESTADOS_PRESTAMO_ADMITE:
        raise HTTPException(
            status_code=409,
            detail=f"El préstamo está en estado '{est_nombre or 'desconocido'}' y no admite pagos",
        )

    # 3) Reglas adicionales
    if data.medio_pago in ("transferencia", "tarjeta") and not data.ref_bancaria:
        raise HTTPException(status_code=400, detail="ref_bancaria es requerida para transferencia o tarjeta")

    # 4) Estado 'pendiente'
    id_estado_pendiente = await _get_estado_pago_pendiente_id(db)

    # 5) Crear Pago usando nombres reales de ATRIBUTOS del modelo
    id_validador = _resolve_user_id(current_user)
    kwargs = {}
    _set_kw(Pago, ("id_prestamo", "Id_prestamo"), data.id_prestamo, kwargs)
    _set_kw(Pago, ("id_estado", "Id_estado"), id_estado_pendiente, kwargs)
    _set_kw(Pago, ("id_validador", "Id_validador"), id_validador, kwargs)
    _set_kw(Pago, ("fecha_pago", "Fecha_pago"), datetime.now(timezone.utc), kwargs)
    _set_kw(Pago, ("monto", "Monto"), data.monto, kwargs)
    _set_kw(Pago, ("tipo_pago", "Tipo_pago"), "abono", kwargs)  # fija por ahora
    _set_kw(Pago, ("medio_pago", "Medio_pago"), data.medio_pago, kwargs)
    _set_kw(Pago, ("ref_bancaria", "Ref_bancaria"), data.ref_bancaria, kwargs)

    obj_pago = Pago(**kwargs)
    db.add(obj_pago)

    try:
        # obtener id del pago para comprobante
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto al crear el pago") from e

    # 6) Comprobante (opcional): Url | url | Imagen | imagen
    if data.comprobante_url:
        comp_kwargs = {}
        _set_kw(Comprobante, ("id_pago", "Id_pago"), _get(obj_pago, ("id_pago", "Id_pago")), comp_kwargs)
        # campo URL de la imagen
        if hasattr(Comprobante, "url") or hasattr(Comprobante, "Url"):
            _set_kw(Comprobante, ("url", "Url"), str(data.comprobante_url), comp_kwargs)
        else:
            _set_kw(Comprobante, ("imagen", "Imagen"), str(data.comprobante_url), comp_kwargs)

        db.add(Comprobante(**comp_kwargs))

    # 7) Auditoría (no rompe si falla)
    try:
        await registrar_auditoria(
            db=db,
            usuario_id=id_validador,
            accion="CREAR_PAGO",
            modulo="Pago",
            detalle=f"Pago creado para préstamo {data.id_prestamo} por Q{float(data.monto):.2f}",
            valores_anteriores=None,
            valores_nuevos={
                "Id_prestamo": data.id_prestamo,
                "Monto": float(data.monto),
                "Medio_pago": data.medio_pago,
                "Ref_bancaria": data.ref_bancaria,
                "Estado": PAGO_ESTADO_PENDIENTE_TXT,
                "Comprobante_url": str(data.comprobante_url) if data.comprobante_url else None,
            },
        )
    except Exception:
        pass

    # 8) Commit final
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto de unicidad o reglas internas") from e

    await db.refresh(obj_pago)

    # 9) Respuesta (normalizada en minúsculas para el frontend)
    return CrearPagoOut(
        id_pago=_get(obj_pago, ("id_pago", "Id_pago")),
        id_prestamo=_get(obj_pago, ("id_prestamo", "Id_prestamo")),
        estado=PAGO_ESTADO_PENDIENTE_TXT,
        monto=float(_get(obj_pago, ("monto", "Monto"))),
        medio_pago=_get(obj_pago, ("medio_pago", "Medio_pago")),
        ref_bancaria=_get(obj_pago, ("ref_bancaria", "Ref_bancaria")),
        comprobante_url=str(data.comprobante_url) if data.comprobante_url else None,
    )
