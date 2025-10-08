from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.db.database import get_db
from app.db.models.recepcion_articulo import RecepcionArticulo
from app.db.models.articulo import Articulo
from app.db.models.prestamo import Prestamo
from app.db.models.prestamo_movimiento import PrestamoMovimiento
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.user import User

from app.schemas.recepciones import (
    RecepcionCreate,
    RecepcionOut,
    ArticuloResumen,
    PrestamoResumen,
    MovimientoResumen,
)
from app.api.deps import get_current_user
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol

router = APIRouter(prefix="/recepciones", tags=["Recepciones"])


async def _obtener_estado_articulo(db: AsyncSession, nombre: str) -> EstadoArticulo:
    """Obtiene un estado de artículo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de artículo '{nombre}' no existe en catálogo",
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


@router.post("", response_model=RecepcionOut, status_code=status.HTTP_201_CREATED)
async def registrar_recepcion(
    payload: RecepcionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Registra la recepción de un artículo en domicilio u oficina.
    """

    # 🔹 Parche: alias rápido para soportar id_usuario en helpers
    setattr(current_user, "id_usuario", getattr(current_user, "ID_Usuario", None))

    # Validar permisos (ADMIN, TECNICO, OPERADOR)
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "TECNICO", "OPERADOR"]):
        raise HTTPException(status_code=403, detail="Sin permiso para recepcionar")

    metodo = payload.metodo_entrega.lower()
    if metodo not in {"domicilio", "oficina"}:
        raise HTTPException(
            status_code=400,
            detail="Método de entrega inválido (domicilio | oficina)",
        )

    estado_verif = payload.estado_verificacion.lower()
    if metodo == "domicilio" and estado_verif not in {"recogido_ok", "rechazado_domicilio"}:
        raise HTTPException(
            status_code=400,
            detail="Para domicilio: recogido_ok | rechazado_domicilio",
        )
    if metodo == "oficina" and estado_verif != "aprobado":
        raise HTTPException(
            status_code=400,
            detail="Para oficina el estado debe ser 'aprobado'",
        )

    # ====================
    # Obtención de entidades
    # ====================
    result = await db.execute(
        select(Articulo).where(Articulo.id_articulo == payload.id_articulo)
    )
    articulo = result.scalar_one_or_none()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    result_prest = await db.execute(
        select(Prestamo).where(Prestamo.id_articulo == payload.id_articulo)
    )
    prestamo = result_prest.scalar_one_or_none()
    if not prestamo:
        raise HTTPException(
            status_code=404,
            detail="No existe préstamo asociado a este artículo",
        )

    # Estados necesarios
    estado_en_transito = await _obtener_estado_articulo(db, "en_transito")
    estado_empeniado = await _obtener_estado_articulo(db, "empeñado")
    estado_rechazado = await _obtener_estado_articulo(db, "rechazado")
    estado_prestamo_activo = await _obtener_estado_prestamo(db, "activo")
    estado_prestamo_cancelado = await _obtener_estado_prestamo(db, "cancelado")

    fase = metodo

    # ====================
    # FASE: DOMICILIO
    # ====================
    if metodo == "domicilio":
        try:
            result_estado = await db.execute(
                select(EstadoArticulo).where(
                    EstadoArticulo.id_estado_articulo == articulo.id_estado
                )
            )
            estado_actual = result_estado.scalar_one_or_none()
            if estado_actual and estado_actual.nombre.lower() not in {"evaluado"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Artículo en estado '{estado_actual.nombre}', no válido para recolección",
                )

            recepcion = RecepcionArticulo(
                id_articulo=payload.id_articulo,
                id_usuario=current_user.ID_Usuario,
                metodo_entrega="domicilio",
                gps=payload.gps,
                estado_verificacion=estado_verif,
                fecha_recepcion=datetime.now(timezone.utc),
            )
            db.add(recepcion)
            await db.flush()

            if estado_verif == "recogido_ok":
                articulo.id_estado = estado_en_transito.id_estado_articulo
                await registrar_auditoria(
                    db=db,
                    usuario_id=current_user.ID_Usuario,
                    accion="RECOLECCION_DOMICILIO",
                    modulo="RecepcionArticulo",
                    detalle=f"Artículo {articulo.id_articulo} recogido OK",
                    valores_nuevos=recepcion,
                )
            else:
                articulo.id_estado = estado_rechazado.id_estado_articulo
                prestamo.id_estado = estado_prestamo_cancelado.id_estado_prestamo
                await registrar_auditoria(
                    db=db,
                    usuario_id=current_user.ID_Usuario,
                    accion="RECHAZO_DOMICILIO",
                    modulo="RecepcionArticulo",
                    detalle=f"Artículo {articulo.id_articulo} rechazado en domicilio",
                    valores_nuevos=recepcion,
                )

            await db.commit()
            await db.refresh(recepcion)
            await db.refresh(articulo)

        except Exception:
            await db.rollback()
            raise

        result_estado_final = await db.execute(
            select(EstadoArticulo).where(
                EstadoArticulo.id_estado_articulo == articulo.id_estado
            )
        )
        estado_final = result_estado_final.scalar_one_or_none()

        return RecepcionOut(
            id_recepcion=recepcion.id_recepcion,
            fase=fase,
            articulo=ArticuloResumen(
                id=articulo.id_articulo,
                estado=estado_final.nombre if estado_final else "desconocido",
            ),
        )

    # ====================
    # FASE: OFICINA
    # ====================
    try:
        result_estado = await db.execute(
            select(EstadoArticulo).where(
                EstadoArticulo.id_estado_articulo == articulo.id_estado
            )
        )
        estado_actual = result_estado.scalar_one_or_none()
        if estado_actual and estado_actual.nombre.lower() not in {"en_transito", "evaluado"}:
            raise HTTPException(
                status_code=409,
                detail=f"Artículo debe estar en 'en_transito' o 'evaluado', no '{estado_actual.nombre}'",
            )

        result_estado_prest = await db.execute(
            select(EstadoPrestamo).where(
                EstadoPrestamo.id_estado_prestamo == prestamo.id_estado
            )
        )
        estado_prest_actual = result_estado_prest.scalar_one_or_none()
        if estado_prest_actual and estado_prest_actual.nombre.lower() != "aprobado_pendiente_entrega":
            raise HTTPException(
                status_code=409,
                detail=f"Préstamo debe estar en 'aprobado_pendiente_entrega', está en '{estado_prest_actual.nombre}'",
            )

        result_check = await db.execute(
            select(RecepcionArticulo).where(
                RecepcionArticulo.id_articulo == payload.id_articulo,
                RecepcionArticulo.metodo_entrega == "oficina",
            )
        )
        if result_check.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Ya existe una recepción de oficina para este artículo",
            )

        recepcion = RecepcionArticulo(
            id_articulo=payload.id_articulo,
            id_usuario=current_user.ID_Usuario,
            metodo_entrega="oficina",
            gps=payload.gps,
            estado_verificacion="aprobado",
            fecha_recepcion=datetime.now(timezone.utc),
        )
        db.add(recepcion)
        await db.flush()

        articulo.id_estado = estado_empeniado.id_estado_articulo
        prestamo.id_estado = estado_prestamo_activo.id_estado_prestamo
        prestamo.deuda_actual = Decimal(prestamo.monto_prestamo)

        movimiento = PrestamoMovimiento(
            id_prestamo=prestamo.id_prestamo,
            tipo="desembolso",
            monto=Decimal(prestamo.monto_prestamo),
            nota="Desembolso al ingresar a oficina",
            fecha=datetime.now(timezone.utc),
        )
        db.add(movimiento)

        await registrar_auditoria(
            db=db,
            usuario_id=current_user.ID_Usuario,
            accion="INGRESO_OFICINA",
            modulo="RecepcionArticulo",
            detalle=f"Artículo {articulo.id_articulo} ingresado a oficina",
            valores_nuevos=recepcion,
        )
        await registrar_auditoria(
            db=db,
            usuario_id=current_user.ID_Usuario,
            accion="DESEMBOLSO",
            modulo="Prestamo",
            detalle=f"Desembolso Q{str(prestamo.monto_prestamo)} para préstamo {prestamo.id_prestamo}",
            valores_nuevos=movimiento,
        )

        await db.commit()
        await db.refresh(recepcion)
        await db.refresh(articulo)
        await db.refresh(prestamo)
        await db.refresh(movimiento)

    except Exception:
        await db.rollback()
        raise

    prestamo_out = PrestamoResumen(
        id=prestamo.id_prestamo,
        estado="activo",
        deuda_actual=float(prestamo.deuda_actual),
    )
    movimiento_out = MovimientoResumen(
        tipo=movimiento.tipo,
        monto=float(movimiento.monto),
    )

    return RecepcionOut(
        id_recepcion=recepcion.id_recepcion,
        fase=fase,
        articulo=ArticuloResumen(id=articulo.id_articulo, estado="empeñado"),
        prestamo=prestamo_out,
        movimiento=movimiento_out,
    )
