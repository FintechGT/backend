# app/api/routers/articulos_valuador.py
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field
from sqlalchemy import select, text, bindparam, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.solicitud import Solicitud
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/articulos", tags=["Valuador - Artículos"])


# ----------------- Helpers locales -----------------
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


async def _usuario_tiene_algun_rol(db: AsyncSession, user_id: int, roles: list[str]) -> bool:
    """Chequeo de roles sin depender de otros módulos."""
    stmt = text("""
        SELECT 1
        FROM Usuario_Rol ur
        JOIN Roles r ON r.ID_rol = ur.ID_rol
        WHERE ur.ID_Usuario = :uid
          AND r.Nombre IN :roles
        LIMIT 1
    """).bindparams(bindparam("roles", expanding=True))
    res = await db.execute(stmt, {"uid": user_id, "roles": roles})
    return res.scalar_one_or_none() is not None
# ----------------------------------------------------


# ============== Schemas ==============
class AprobarArticuloRequest(BaseModel):
    valor_aprobado: Decimal = Field(..., gt=0, description="Monto aprobado (> 0)")
    plazo_dias: int | None = Field(None, ge=1, description="Plazo en días (opcional)")
    model_config = {
        "json_schema_extra": {"example": {"valor_aprobado": 1200.00, "plazo_dias": 30}}
    }


class AprobarArticuloResponse(BaseModel):
    id_articulo: int
    estado_articulo: str
    valor_aprobado: float
    prestamo: dict
    model_config = {
        "json_schema_extra": {
            "example": {
                "id_articulo": 3001,
                "estado_articulo": "evaluado",
                "valor_aprobado": 1200.0,
                "prestamo": {
                    "id_prestamo": 5001,
                    "estado": "aprobado_pendiente_entrega",
                    "fecha_inicio": "2025-09-29",
                    "fecha_vencimiento": "2025-10-29",
                    "monto_prestamo": 1200.0,
                    "deuda_actual": 0.0
                }
            }
        }
    }


# ============== Endpoint ==============
@router.post(
    "/{id_articulo}/aprobar",
    response_model=AprobarArticuloResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Aprobar artículo y crear préstamo",
    description=(
        "Convierte un Artículo 'pendiente' en Préstamo aprobado en una sola llamada: "
        "valida, cambia estado a 'evaluado', crea préstamo (1:1) en "
        "'aprobado_pendiente_entrega', registra auditoría y (opcional) cierra la solicitud."
    ),
)
async def aprobar_articulo_crear_prestamo(
    id_articulo: int,
    payload: AprobarArticuloRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) Permisos
    user_id = _resolve_user_id(current_user)
    if not await _usuario_tiene_algun_rol(db, user_id, ["VALUADOR", "ADMIN"]):
        raise HTTPException(status_code=403, detail="No tiene permiso de VALUADOR")

    # 2) Buscar artículo (sin relaciones)
    articulo = (
        await db.execute(select(Articulo).where(Articulo.id_articulo == id_articulo))
    ).scalar_one_or_none()
    if not articulo:
        raise HTTPException(404, f"Artículo {id_articulo} no existe")

    # 3) Validar estado 'pendiente'
    estado_actual = (
        await db.execute(
            select(EstadoArticulo).where(
                EstadoArticulo.id_estado_articulo == articulo.id_estado
            )
        )
    ).scalar_one_or_none()
    if not estado_actual or estado_actual.nombre.lower() != "pendiente":
        raise HTTPException(409, "El artículo ya está evaluado o tiene préstamo")

    # 4) Regla 1:1
    if (
        await db.execute(select(Prestamo).where(Prestamo.id_articulo == id_articulo))
    ).scalar_one_or_none():
        raise HTTPException(409, "Ya existe un préstamo para este artículo (1:1)")

    # 5) Configuraciones opcionales
    cfg_rows = (
        await db.execute(
            select(ConfiguracionesGenerales).where(
                ConfiguracionesGenerales.clave.in_(
                    ["PLAZO_DEFAULT", "FACTOR_MAX_APROBACION"]
                )
            )
        )
    ).scalars().all()
    configs = {c.clave: c.valor for c in cfg_rows}

    if "FACTOR_MAX_APROBACION" in configs:
        try:
            factor_max = Decimal(configs["FACTOR_MAX_APROBACION"])
            valor_max = articulo.valor_estimado * factor_max
            if payload.valor_aprobado > valor_max:
                raise HTTPException(
                    400,
                    detail=(
                        f"El valor aprobado no puede exceder {float(valor_max):.2f} "
                        f"(estimado {float(articulo.valor_estimado):.2f} × {float(factor_max)})"
                    ),
                )
        except (ValueError, TypeError):
            pass

    # 6) Estados requeridos (sin ILIKE -> usamos LOWER() == '...').
    estado_evaluado = (
        await db.execute(
            select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == "evaluado")
        )
    ).scalar_one_or_none()
    if not estado_evaluado:
        raise HTTPException(500, "Estado 'evaluado' no existe en Estado_Articulo")

    estado_prestamo = (
        await db.execute(
            select(EstadoPrestamo).where(
                func.lower(EstadoPrestamo.nombre) == "aprobado_pendiente_entrega"
            )
        )
    ).scalar_one_or_none()
    if not estado_prestamo:
        raise HTTPException(
            500, "Estado 'aprobado_pendiente_entrega' no existe en Estado_Prestamo"
        )

    # 7) Fechas del préstamo
    plazo = payload.plazo_dias or int(configs.get("PLAZO_DEFAULT", "30"))
    hoy = date.today()
    fecha_vencimiento = hoy + timedelta(days=plazo)

    # 8) Actualizar artículo
    articulo.id_estado = estado_evaluado.id_estado_articulo
    articulo.valor_aprobado = payload.valor_aprobado
    await db.flush()

    # 9) Crear préstamo
    nuevo_prestamo = Prestamo(
        id_articulo=articulo.id_articulo,
        id_usuario_evaluador=user_id,
        id_estado=estado_prestamo.id_estado_prestamo,
        fecha_inicio=hoy,
        fecha_vencimiento=fecha_vencimiento,
        monto_prestamo=payload.valor_aprobado,
        deuda_actual=Decimal("0.00"),
        mora_acumulada=Decimal("0.00"),
        interes_acumulada=Decimal("0.00"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        ultimo_calculo_en=None,
    )
    db.add(nuevo_prestamo)
    await db.flush()

    # 10) (Opcional) Cerrar solicitud si ya no hay pendientes (sin ILIKE)
    pendiente_q = (
        select(Articulo.id_articulo)
        .join(EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado)
        .where(
            Articulo.id_solicitud == articulo.id_solicitud,
            func.lower(EstadoArticulo.nombre) == "pendiente",
        )
        .limit(1)
    )
    pendiente_row = (await db.execute(pendiente_q)).scalar_one_or_none()

    if pendiente_row is None:
        from app.db.models.estado_solicitud import EstadoSolicitud

        solicitud = (
            await db.execute(
                select(Solicitud).where(Solicitud.id_solicitud == articulo.id_solicitud)
            )
        ).scalar_one_or_none()
        if solicitud:
            estado_evaluada = (
                await db.execute(
                    select(EstadoSolicitud).where(
                        func.lower(EstadoSolicitud.nombre) == "evaluada"
                    )
                )
            ).scalar_one_or_none()
            if estado_evaluada:
                solicitud.id_estado = estado_evaluada.id_estado_solicitud

    # 11) Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="APROBAR_PRESTAMO",
        modulo="Articulo",
        detalle=f"Artículo {articulo.id_articulo} aprobado, Préstamo {nuevo_prestamo.id_prestamo} creado",
        valores_anteriores={"articulo_estado": estado_actual.nombre, "articulo_valor_aprobado": None},
        valores_nuevos={
            "articulo_estado": "evaluado",
            "articulo_valor_aprobado": float(payload.valor_aprobado),
            "prestamo_id": nuevo_prestamo.id_prestamo,
            "prestamo_monto": float(payload.valor_aprobado),
        },
    )

    # 12) Commit y respuesta
    await db.commit()
    await db.refresh(articulo)
    await db.refresh(nuevo_prestamo)

    return AprobarArticuloResponse(
        id_articulo=articulo.id_articulo,
        estado_articulo="evaluado",
        valor_aprobado=float(articulo.valor_aprobado),
        prestamo={
            "id_prestamo": nuevo_prestamo.id_prestamo,
            "estado": "aprobado_pendiente_entrega",
            "fecha_inicio": nuevo_prestamo.fecha_inicio.isoformat(),
            "fecha_vencimiento": nuevo_prestamo.fecha_vencimiento.isoformat(),
            "monto_prestamo": float(nuevo_prestamo.monto_prestamo),
            "deuda_actual": float(nuevo_prestamo.deuda_actual),
        },
    )
