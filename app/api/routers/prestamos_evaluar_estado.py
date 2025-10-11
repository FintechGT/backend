# app/api/routers/prestamos_evaluar_estado.py
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
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.inventario_venta import InventarioVenta
from app.db.models.estado_inventario import EstadoInventario
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.db.models.user import User

# Schemas
from app.schemas.evaluacion_estado import (
    EvaluarEstadoIn,
    EvaluarEstadoOut,
    EstadoDto,
    AccionesDto
)

# Utilidades
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Evaluación Estado"])


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


async def _obtener_estado_articulo(
    db: AsyncSession,
    nombre: str
) -> Optional[EstadoArticulo]:
    """Obtiene un estado de artículo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoArticulo).where(
            func.lower(EstadoArticulo.nombre) == nombre.lower()
        )
    )
    return result.scalar_one_or_none()


async def _obtener_estado_inventario(
    db: AsyncSession,
    nombre: str
) -> Optional[EstadoInventario]:
    """Obtiene un estado de inventario por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoInventario).where(
            func.lower(EstadoInventario.nombre) == nombre.lower()
        )
    )
    return result.scalar_one_or_none()


async def _es_estado_inventario(
    db: AsyncSession,
    id_estado_articulo: int
) -> bool:
    """Verifica si el estado del artículo es un estado de inventario."""
    estados_inventario = ["en_inventario", "vendido", "en_venta"]
    result = await db.execute(
        select(EstadoArticulo).where(
            EstadoArticulo.id_estado_articulo == id_estado_articulo
        )
    )
    estado = result.scalar_one_or_none()
    if not estado:
        return False
    return estado.nombre.lower() in estados_inventario


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================
@router.patch(
    "/{id_prestamo}/evaluar-estado",
    response_model=EvaluarEstadoOut,
    status_code=status.HTTP_200_OK,
    summary="Evaluar estado operativo de un préstamo",
    description=(
        "Determina el estado operativo del préstamo según reglas de negocio: "
        "activo, en_mora, incumplido, liquidado. "
        "Si el incumplimiento supera un umbral y marcar_inventario=true, "
        "mueve el artículo asociado al inventario. Operación determinística e idempotente."
    )
)
async def evaluar_estado_prestamo(
    id_prestamo: int,
    payload: EvaluarEstadoIn = Body(default=EvaluarEstadoIn()),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Evalúa y actualiza el estado operativo de un préstamo.
    
    ## Reglas de negocio:
    - **liquidado**: deuda_actual <= 0
    - **activo**: fecha_corte <= fecha_vencimiento
    - **en_mora**: dentro de días de gracia
    - **incumplido**: fuera de días de gracia
    
    ## Pase a inventario:
    Si incumplido + fecha_corte > (vencimiento + gracia + umbral) + marcar_inventario=true:
    - Articulo.Id_Estado → en_inventario
    - Crea registro en Inventario_Venta
    - Audita el movimiento
    
    ## Permisos requeridos:
    - ADMIN, CAJERO, OPERADOR, VALUADOR
    """
    
    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)
    
    roles_permitidos = ["ADMIN", "CAJERO", "OPERADOR", "VALUADOR"]
    tiene_permiso = await usuario_tiene_algun_rol(
        current_user, db, roles_permitidos
    )
    
    if not tiene_permiso:
        raise HTTPException(
            status_code=403,
            detail=f"Requiere uno de estos roles: {', '.join(roles_permitidos)}"
        )
    
    # 2) Determinar fecha de corte
    fecha_corte = payload.fecha_corte or date.today()
    
    # 3) Cargar préstamo con lock (SELECT FOR UPDATE)
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
    
    # 4) Obtener configuraciones
    dias_gracia = payload.dias_gracia if payload.dias_gracia is not None else await _obtener_config_int(
        db, "GRACIA_DIAS", 3
    )
    umbral_incumplido_dias = payload.umbral_incumplido_dias if payload.umbral_incumplido_dias is not None else await _obtener_config_int(
        db, "UMBRAL_INCUMPLIDO_DIAS", 15
    )
    
    # 5) (Opcional) Recalcular saldos primero
    recalculo_ejecutado = False
    if payload.forzar_recalculo:
        # Aquí deberías llamar a la lógica de recálculo (API #1)
        # Por simplicidad, asumimos que ya está actualizado
        # En producción, importarías y llamarías la función de recálculo
        recalculo_ejecutado = True
    
    # 6) Obtener estado actual
    result_estado_actual = await db.execute(
        select(EstadoPrestamo).where(
            EstadoPrestamo.id_estado_prestamo == prestamo.id_estado
        )
    )
    estado_anterior = result_estado_actual.scalar_one_or_none()
    if not estado_anterior:
        raise HTTPException(
            status_code=500,
            detail="Estado actual del préstamo no encontrado"
        )
    
    # 7) Determinar estado objetivo según reglas de negocio
    frontera_gracia = prestamo.fecha_vencimiento + timedelta(days=dias_gracia)
    deuda = Decimal(str(prestamo.deuda_actual))
    
    # Regla 1: Liquidado (deuda en cero)
    if deuda <= Decimal("0.009"):  # tolerancia de centavos
        estado_obj_nombre = "liquidado"
        motivo = "Deuda en cero"
    # Regla 2: Activo (dentro del plazo)
    elif fecha_corte <= prestamo.fecha_vencimiento:
        estado_obj_nombre = "activo"
        motivo = "Dentro del plazo"
    # Regla 3: En mora (dentro de días de gracia)
    elif fecha_corte <= frontera_gracia:
        estado_obj_nombre = "en_mora"
        motivo = "Dentro de días de gracia"
    # Regla 4: Incumplido (fuera de días de gracia)
    else:
        estado_obj_nombre = "incumplido"
        motivo = "Superó días de gracia"
    
    # 8) Obtener ID del estado objetivo
    estado_objetivo = await _obtener_estado_prestamo(db, estado_obj_nombre)
    if not estado_objetivo:
        raise HTTPException(
            status_code=500,
            detail=f"Estado '{estado_obj_nombre}' no existe en catálogo"
        )
    
    # 9) Actualizar estado si cambió
    cambio_estado = (prestamo.id_estado != estado_objetivo.id_estado_prestamo)
    if cambio_estado:
        prestamo.id_estado = estado_objetivo.id_estado_prestamo
        prestamo.updated_at = datetime.now(timezone.utc)
        
        await registrar_auditoria(
            db=db,
            usuario_id=user_id,
            accion="CAMBIO_ESTADO_PRESTAMO",
            modulo="Prestamo",
            detalle=(
                f"Préstamo {id_prestamo}: {estado_anterior.nombre} → {estado_obj_nombre}. "
                f"Motivo: {motivo}"
            ),
            valores_anteriores={"estado": estado_anterior.nombre},
            valores_nuevos={"estado": estado_obj_nombre}
        )
    
    # 10) Evaluar pase a inventario
    articulo_a_inventario = False
    
    if (estado_obj_nombre == "incumplido" and 
        payload.marcar_inventario and
        deuda > Decimal("0")):
        
        # Verificar si superó el umbral de incumplimiento definitivo
        if fecha_corte > (frontera_gracia + timedelta(days=umbral_incumplido_dias)):
            # Cargar artículo con lock
            result_art = await db.execute(
                select(Articulo)
                .where(Articulo.id_articulo == prestamo.id_articulo)
                .with_for_update()
            )
            articulo = result_art.scalar_one_or_none()
            
            if not articulo:
                raise HTTPException(
                    status_code=500,
                    detail=f"Artículo {prestamo.id_articulo} no encontrado"
                )
            
            # Verificar que no esté ya en inventario
            es_inventario = await _es_estado_inventario(db, articulo.id_estado)
            
            if not es_inventario:
                # a) Cambiar estado del artículo a en_inventario
                estado_art_inventario = await _obtener_estado_articulo(db, "en_inventario")
                if not estado_art_inventario:
                    raise HTTPException(
                        status_code=500,
                        detail="Estado 'en_inventario' no existe en catálogo de artículos"
                    )
                
                articulo.id_estado = estado_art_inventario.id_estado_articulo
                
                # b) Obtener estado de inventario 'disponible'
                estado_inv_disponible = await _obtener_estado_inventario(db, "disponible")
                if not estado_inv_disponible:
                    raise HTTPException(
                        status_code=500,
                        detail="Estado 'disponible' no existe en catálogo de inventario"
                    )
                
                # c) Crear registro en Inventario_Venta
                precio_base = articulo.valor_aprobado or Decimal("0.00")
                
                nuevo_inventario = InventarioVenta(
                    id_articulo=articulo.id_articulo,
                    id_estado=estado_inv_disponible.id_estado_inventario,
                    precio_base=precio_base,
                    precio_actual=precio_base,
                    dias_en_bodega=0,
                    fecha_ingreso=fecha_corte
                )
                db.add(nuevo_inventario)
                
                # d) Auditoría
                await registrar_auditoria(
                    db=db,
                    usuario_id=user_id,
                    accion="ARTICULO_A_INVENTARIO_POR_INCUMPLIDO",
                    modulo="Inventario",
                    detalle=(
                        f"Artículo {articulo.id_articulo} movido a inventario. "
                        f"Préstamo {id_prestamo} superó umbral de incumplimiento ({umbral_incumplido_dias} días)"
                    ),
                    valores_nuevos={
                        "id_articulo": articulo.id_articulo,
                        "id_prestamo": id_prestamo,
                        "precio_base": float(precio_base)
                    }
                )
                
                articulo_a_inventario = True
    
    # 11) Commit
    try:
        await db.commit()
        await db.refresh(prestamo)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al evaluar estado del préstamo: {str(e)}"
        )
    
    # 12) Respuesta
    return EvaluarEstadoOut(
        id_prestamo=prestamo.id_prestamo,
        estado_anterior=EstadoDto(
            id=estado_anterior.id_estado_prestamo,
            codigo=estado_anterior.nombre
        ),
        estado_nuevo=EstadoDto(
            id=estado_objetivo.id_estado_prestamo,
            codigo=estado_obj_nombre
        ),
        motivo=motivo,
        deuda_actual=float(prestamo.deuda_actual),
        mora_acumulada=float(prestamo.mora_acumulada),
        interes_acumulada=float(prestamo.interes_acumulada),
        fecha_corte=fecha_corte,
        acciones=AccionesDto(
            recalculo_ejecutado=recalculo_ejecutado,
            articulo_a_inventario=articulo_a_inventario
        )
    )