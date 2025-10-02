from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field, condecimal

from app.db.database import get_db
from app.core.security import get_current_user
from app.db.models.user import User
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.solicitud import Solicitud
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.utils.roles import usuario_tiene_algun_rol
from app.utils.auditoria import registrar_auditoria

router = APIRouter(prefix="/articulos", tags=["Valuador - Artículos"])

# ============== SCHEMAS ==============
class AprobarArticuloRequest(BaseModel):
    """Request para aprobar un artículo."""
    valor_aprobado: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Monto que la empresa decide prestar (debe ser mayor a 0)"
    )
    plazo_dias: int | None = Field(
        None,
        ge=1,
        description="Plazo en días (opcional, se usa valor por defecto de configuración si se omite)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "valor_aprobado": 1200.00,
                "plazo_dias": 30
            }
        }


class AprobarArticuloResponse(BaseModel):
    """Response después de aprobar un artículo."""
    id_articulo: int
    estado_articulo: str
    valor_aprobado: float
    prestamo: dict

    class Config:
        json_schema_extra = {
            "example": {
                "id_articulo": 3001,
                "estado_articulo": "evaluado",
                "valor_aprobado": 1200.00,
                "prestamo": {
                    "id_prestamo": 5001,
                    "estado": "aprobado_pendiente_entrega",
                    "fecha_inicio": "2025-09-29",
                    "fecha_vencimiento": "2025-10-29",
                    "monto_prestamo": 1200.00,
                    "deuda_actual": 0.00
                }
            }
        }


# ============== ENDPOINT ==============
@router.post(
    "/{id_articulo}/aprobar",
    response_model=AprobarArticuloResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Aprobar artículo y crear préstamo",
    description="""
    **Mega API controlada** que convierte un Artículo no evaluado en un Préstamo aprobado.
    
    En una sola llamada hace:
    1. Valida el artículo y la entrada
    2. Actualiza el estado del Artículo a "evaluado" y guarda el valor_aprobado
    3. Crea el Préstamo (1:1 con el artículo) en estado "aprobado_pendiente_entrega"
    4. Registra auditoría (y opcionalmente cierra la Solicitud si ya no quedan artículos pendientes)
    
    **Permisos:** Solo usuarios con rol VALUADOR (o equivalente).
    
    **Validaciones:**
    - El artículo existe y está en estado "pendiente"
    - El usuario que llama tiene rol VALUADOR
    - valor_aprobado > 0
    - No existe ya un préstamo para ese artículo (regla 1:1)
    - (Opcional) La Solicitud del artículo está abierta/pendiente
    """
)
async def aprobar_articulo_crear_prestamo(
    id_articulo: int,
    payload: AprobarArticuloRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aprueba un artículo y crea el préstamo asociado.
    
    Esta es una operación transaccional que garantiza que:
    - El artículo pasa de "pendiente" a "evaluado"
    - Se crea un nuevo préstamo en estado "aprobado_pendiente_entrega"
    - Todo ocurre de forma atómica (todo o nada)
    """
    
    # ====== 1) VALIDAR ROL ======
    if not await usuario_tiene_algun_rol(current_user, db, ["VALUADOR", "ADMIN"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso de VALUADOR"
        )
    
    # ====== 2) BUSCAR ARTÍCULO ======
    result = await db.execute(
        select(Articulo)
        .options(selectinload(Articulo.estado))  # evita lazy loading
        .where(Articulo.id_articulo == id_articulo)
    )
    articulo = result.scalar_one_or_none()
    
    if not articulo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artículo {id_articulo} no existe"
        )
    
    # ====== 3) VALIDAR ESTADO "PENDIENTE" ======
    result_estado = await db.execute(
        select(EstadoArticulo).where(EstadoArticulo.id_estado_articulo == articulo.id_estado)
    )
    estado_actual = result_estado.scalar_one_or_none()
    
    if not estado_actual or estado_actual.nombre.lower() != "pendiente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El artículo ya está evaluado o tiene préstamo"
        )
    
    # ====== 4) VERIFICAR QUE NO EXISTA PRÉSTAMO (REGLA 1:1) ======
    result_prestamo = await db.execute(
        select(Prestamo).where(Prestamo.id_articulo == id_articulo)
    )
    prestamo_existente = result_prestamo.scalar_one_or_none()
    
    if prestamo_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un préstamo para este artículo (1:1)"
        )
    
    # ====== 5) VALIDAR VALOR_APROBADO ======
    # Obtener configuraciones opcionales
    config_result = await db.execute(
        select(ConfiguracionesGenerales).where(
            ConfiguracionesGenerales.clave.in_(["PLAZO_DEFAULT", "FACTOR_MAX_APROBACION"])
        )
    )
    configs = {c.clave: c.valor for c in config_result.scalars().all()}
    
    # Validación opcional: valor_aprobado no debe exceder valor_estimado * factor
    if "FACTOR_MAX_APROBACION" in configs:
        try:
            factor_max = Decimal(configs["FACTOR_MAX_APROBACION"])
            valor_max = articulo.valor_estimado * factor_max
            if payload.valor_aprobado > valor_max:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"El valor aprobado no puede exceder {float(valor_max):.2f} "
                           f"(valor estimado {float(articulo.valor_estimado):.2f} × {float(factor_max)})"
                )
        except (ValueError, TypeError):
            pass  # Si la configuración es inválida, omitir esta validación
    
    # ====== 6) OBTENER ESTADOS PARA ACTUALIZACIÓN ======
    # Estado para el artículo: "evaluado"
    result_evaluado = await db.execute(
        select(EstadoArticulo).where(EstadoArticulo.nombre.ilike("evaluado"))
    )
    estado_evaluado = result_evaluado.scalar_one_or_none()
    if not estado_evaluado:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Estado 'evaluado' no existe en Estado_Articulo"
        )
    
    # Estado para el préstamo: "aprobado_pendiente_entrega"
    result_prestamo_estado = await db.execute(
        select(EstadoPrestamo).where(
            EstadoPrestamo.nombre.ilike("aprobado_pendiente_entrega")
        )
    )
    estado_prestamo = result_prestamo_estado.scalar_one_or_none()
    if not estado_prestamo:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Estado 'aprobado_pendiente_entrega' no existe en Estado_Prestamo"
        )
    
    # ====== 7) CALCULAR FECHAS DEL PRÉSTAMO ======
    from datetime import date, timedelta
    
    # Usar plazo_dias del request o valor por defecto
    plazo = payload.plazo_dias
    if plazo is None:
        plazo = int(configs.get("PLAZO_DEFAULT", "30"))
    
    fecha_inicio = date.today()
    fecha_vencimiento = fecha_inicio + timedelta(days=plazo)
    
    # ====== 8) ACTUALIZAR ARTÍCULO ======
    articulo.id_estado = estado_evaluado.id_estado_articulo
    articulo.valor_aprobado = payload.valor_aprobado
    
    await db.flush()
    
    # ====== 9) CREAR PRÉSTAMO ======
    nuevo_prestamo = Prestamo(
        id_articulo=articulo.id_articulo,
        id_usuario_evaluador=current_user.ID_Usuario,
        id_estado=estado_prestamo.id_estado_prestamo,
        fecha_inicio=fecha_inicio,
        fecha_vencimiento=fecha_vencimiento,
        monto_prestamo=payload.valor_aprobado,
        deuda_actual=Decimal("0.00"),  # Se actualiza al desembolsar
        mora_acumulada=Decimal("0.00"),
        interes_acumulada=Decimal("0.00"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        ultimo_calculo_en=None,
    )
    
    db.add(nuevo_prestamo)
    await db.flush()
    
    # ====== 10) (OPCIONAL) ACTUALIZAR SOLICITUD SI YA NO HAY PENDIENTES ======
    # Verificar si quedan artículos pendientes en la solicitud
    result_pendientes = await db.execute(
        select(Articulo)
        .join(EstadoArticulo)
        .where(
            Articulo.id_solicitud == articulo.id_solicitud,
            EstadoArticulo.nombre.ilike("pendiente")
        )
    )
    articulos_pendientes = result_pendientes.scalars().all()
    
    if not articulos_pendientes:
        # No quedan artículos pendientes, marcar solicitud como "evaluada"
        result_solicitud = await db.execute(
            select(Solicitud).where(Solicitud.id_solicitud == articulo.id_solicitud)
        )
        solicitud = result_solicitud.scalar_one_or_none()
        
        if solicitud:
            from app.db.models.estado_solicitud import EstadoSolicitud
            result_estado_sol = await db.execute(
                select(EstadoSolicitud).where(EstadoSolicitud.nombre.ilike("evaluada"))
            )
            estado_evaluada = result_estado_sol.scalar_one_or_none()
            if estado_evaluada:
                solicitud.id_estado = estado_evaluada.id_estado_solicitud
    
    # ====== 11) REGISTRAR AUDITORÍA ======
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="APROBAR_PRESTAMO",
        modulo="Articulo",
        detalle=f"Artículo {articulo.id_articulo} aprobado, Préstamo {nuevo_prestamo.id_prestamo} creado",
        valores_anteriores={
            "articulo_estado": estado_actual.nombre,
            "articulo_valor_aprobado": None,
        },
        valores_nuevos={
            "articulo_estado": "evaluado",
            "articulo_valor_aprobado": float(payload.valor_aprobado),
            "prestamo_id": nuevo_prestamo.id_prestamo,
            "prestamo_monto": float(payload.valor_aprobado),
        }
    )
    
    # ====== 12) COMMIT Y RESPUESTA ======
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
        }
    )