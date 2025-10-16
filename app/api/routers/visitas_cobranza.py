# app/api/routers/visitas_cobranza.py
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user, User, has_role
from app.db.database import get_db

# Modelos
from app.db.models.visitas_cobranza import VisitasCobranza
from app.db.models.ruta_cobranza import RutaCobranza
from app.db.models.prestamo import Prestamo
from app.db.models.pago import Pago
from app.db.models.estado_pago import EstadoPago
from app.db.models.auditoria import Auditoria

# Schemas
from app.schemas.visita_cobranza import VisitaCobranzaCreate, VisitaCobranzaCreada

# --- Constantes y Enums para evitar "magic strings" ---
class ResultadoVisita(str, Enum):
    COBRO_EXITOSO = "cobro_exitoso"
    NO_ENCONTRADO = "no_encontrado"
    RECHAZO_PAGO = "rechazo_pago"
    # Agrega otros resultados posibles aquí

ESTADO_PAGO_PENDIENTE = "pendiente"
ACCION_AUDITORIA = "REGISTRAR_VISITA_COBRANZA"


router = APIRouter(prefix="/visitas-cobranza", tags=["Visitas de Cobranza"])


@router.post(
    "",
    response_model=VisitaCobranzaCreada,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(has_role(["COBRADOR"]))],
)
async def registrar_visita_cobranza(
    datos: VisitaCobranzaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Registra el resultado de una visita de cobranza. Realizado por el cobrador.
    - Valida que la ruta y el préstamo pertenezcan al cobrador.
    - Si el cobro es exitoso, crea un registro de Pago en estado 'pendiente'.
    - Actualiza el registro de la visita.
    """
    # Estandarizar obtención del ID de usuario
    id_usuario_actual = getattr(current_user, 'id_usuario', getattr(current_user, 'ID_Usuario', None))

    # 1. Validar que la visita exista y pertenezca a la ruta y al cobrador
    stmt = (
        select(VisitasCobranza)
        .join(RutaCobranza, VisitasCobranza.id_ruta == RutaCobranza.id_ruta)
        .where(
            VisitasCobranza.id_ruta == datos.id_ruta_cobranza,
            VisitasCobranza.id_prestamo == datos.id_prestamo,
            VisitasCobranza.resultado.is_(None),  # Solo se puede registrar una vez
            RutaCobranza.id_usuario_cobrador == id_usuario_actual,
        )
        .options(selectinload(VisitasCobranza.prestamo))
    )
    res = await db.execute(stmt)
    visita = res.scalar_one_or_none()

    if not visita:
        raise HTTPException(
            status_code=404,
            detail="Visita no encontrada, ya fue registrada, o no tiene permiso sobre ella.",
        )

    # 2. Validaciones de negocio
    if datos.resultado == ResultadoVisita.COBRO_EXITOSO and (
        datos.monto_pagado is None or datos.monto_pagado <= 0
    ):
        raise HTTPException(
            status_code=422,
            detail="Para un 'cobro_exitoso', el 'monto_pagado' es obligatorio y debe ser mayor a 0.",
        )

    id_pago_nuevo = None
    try:
        # 3. Si el cobro fue exitoso, crear el pago
        if datos.resultado == ResultadoVisita.COBRO_EXITOSO:
            # Obtener estado 'pendiente' para el pago
            estado_pendiente_res = await db.execute(
                select(EstadoPago).where(func.lower(EstadoPago.nombre) == ESTADO_PAGO_PENDIENTE)
            )
            estado_pendiente = estado_pendiente_res.scalar_one_or_none()
            if not estado_pendiente:
                raise HTTPException(
                    status_code=500,
                    detail="Estado de pago 'pendiente' no configurado en el sistema.",
                )

            nuevo_pago = Pago(
                id_prestamo=datos.id_prestamo,
                id_estado=estado_pendiente.id_estado_pago,
                monto=datos.monto_pagado,
                fecha_pago=datetime.utcnow().date(),
                medio_pago=datos.medio_pago,
                referencia_bancaria=datos.ref_bancaria,
                id_usuario_registro=id_usuario_actual,
            )
            db.add(nuevo_pago)
            await db.flush()  # Para obtener el ID del pago
            id_pago_nuevo = nuevo_pago.id_pago

        # 4. Actualizar la visita
        visita.resultado = datos.resultado
        visita.comentario = datos.comentario
        visita.monto_pagado = datos.monto_pagado if datos.resultado == ResultadoVisita.COBRO_EXITOSO else None
        visita.gps = datos.gps
        visita.fecha_visita = datetime.utcnow()
        visita.id_pago = id_pago_nuevo

        # 5. Auditoría
        audit = Auditoria(
            id_usuario=id_usuario_actual,
            accion=ACCION_AUDITORIA,
            modulo="VisitasCobranza",
            fecha_hora=datetime.utcnow(),
            detalle=f"Visita id={visita.id_visita}, resultado={datos.resultado}, monto={datos.monto_pagado or 0}",
        )
        db.add(audit)

        await db.commit()
        await db.refresh(visita)

    except Exception as e:
        await db.rollback()
        # No exponer detalles internos del error al cliente
        # En un entorno de producción, aquí se debería loggear el error `e`
        # import logging; logging.error(f"Error al registrar visita: {e}")
        raise HTTPException(status_code=500, detail="Ocurrió un error interno al registrar la visita.")

    return VisitaCobranzaCreada(
        id_visita=visita.id_visita,
        id_pago=id_pago_nuevo,
        mensaje="Visita registrada exitosamente."
        + (" Pago creado y pendiente de validación." if id_pago_nuevo else ""),
    )