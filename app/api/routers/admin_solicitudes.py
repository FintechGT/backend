# app/api/routers/admin_solicitudes.py
from typing import Optional, List, Dict
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy import select, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.solicitud import Solicitud
from app.db.models.articulo import Articulo
from app.db.models.articulo_foto import ArticuloFoto
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.user import User
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.configuraciones_generales import ConfiguracionesGenerales

# Schemas
from app.schemas.admin_solicitudes import (
    SolicitudesListResponse,
    SolicitudListItemAdmin,
    SolicitudDetalleAdmin,
    ArticuloDetalleAdmin,
    ArticuloFotoAdmin,
    ClienteInfoAdmin,
    EvaluarArticuloIn,
    EvaluarArticuloOut,
    PrestamoCreadoInfo,
    CambiarEstadoSolicitudIn,
    CambiarEstadoSolicitudOut,
    EstadisticasSolicitudesOut,
)

# Utils
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/admin/solicitudes", tags=["Admin - Solicitudes"])


# ============================================================
# HELPERS
# ============================================================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _ensure_id_usuario_attr(u: User) -> None:
    """Asegura que el usuario tenga el atributo id_usuario para compatibilidad."""
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))


async def _tiene_permisos_admin(user: User, db: AsyncSession) -> bool:
    """Verifica si el usuario tiene rol ADMINISTRADOR, SUPERVISOR o VALUADOR."""
    _ensure_id_usuario_attr(user)
    return await usuario_tiene_algun_rol(user, db, ["ADMINISTRADOR", "SUPERVISOR", "VALUADOR"])


async def _obtener_estado_solicitud(db: AsyncSession, nombre: str) -> EstadoSolicitud:
    """Obtiene un estado de solicitud por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoSolicitud).where(func.lower(EstadoSolicitud.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de solicitud '{nombre}' no existe en catálogo"
        )
    return estado


async def _obtener_estado_articulo(db: AsyncSession, nombre: str) -> EstadoArticulo:
    """Obtiene un estado de artículo por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de artículo '{nombre}' no existe en catálogo"
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
            detail=f"Estado de préstamo '{nombre}' no existe en catálogo"
        )
    return estado


# ============================================================
# 1. LISTAR SOLICITUDES (con filtros y paginación)
# ============================================================
@router.get(
    "",
    response_model=SolicitudesListResponse,
    summary="Listar todas las solicitudes (Admin)",
    description=(
        "Lista todas las solicitudes con filtros opcionales. "
        "**Permisos:** ADMINISTRADOR, SUPERVISOR, VALUADOR"
    )
)
async def listar_solicitudes_admin(
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    usuario_id: Optional[int] = Query(None, description="Filtrar por ID de usuario"),
    fecha_desde: Optional[date] = Query(None, description="Fecha de envío desde"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha de envío hasta"),
    metodo_entrega: Optional[str] = Query(None, description="domicilio | oficina"),
    q: Optional[str] = Query(None, description="Buscar en nombre/correo del cliente"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)
    
    # Verificar permisos
    if not await _tiene_permisos_admin(current_user, db):
        raise HTTPException(
            status_code=403,
            detail="Requiere rol ADMINISTRADOR, SUPERVISOR o VALUADOR"
        )
    
    # Query base
    stmt = select(Solicitud).order_by(desc(Solicitud.id_solicitud))
    
    # Aplicar filtros
    if estado:
        result_estado = await db.execute(
            select(EstadoSolicitud).where(func.lower(EstadoSolicitud.nombre) == estado.lower())
        )
        estado_obj = result_estado.scalar_one_or_none()
        if estado_obj:
            stmt = stmt.where(Solicitud.id_estado == estado_obj.id_estado_solicitud)
    
    if usuario_id:
        stmt = stmt.where(Solicitud.id_usuario == usuario_id)
    
    if fecha_desde:
        stmt = stmt.where(func.date(Solicitud.fecha_envio) >= fecha_desde)
    
    if fecha_hasta:
        stmt = stmt.where(func.date(Solicitud.fecha_envio) <= fecha_hasta)
    
    if metodo_entrega:
        stmt = stmt.where(func.lower(Solicitud.metodo_entrega) == metodo_entrega.lower())
    
    if q:
        # Buscar en nombre o correo del cliente (join con User)
        like_pattern = f"%{q.lower()}%"
        stmt = stmt.join(User, User.ID_Usuario == Solicitud.id_usuario).where(
            or_(
                func.lower(User.Nombre).like(like_pattern),
                func.lower(User.Correo).like(like_pattern)
            )
        )
    
    # Total
    count_result = await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )
    total = count_result.scalar() or 0
    
    # Paginación
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    solicitudes = result.scalars().all()
    
    # Construir respuesta
    items: List[SolicitudListItemAdmin] = []
    
    for sol in solicitudes:
        # Obtener cliente
        result_user = await db.execute(
            select(User).where(User.ID_Usuario == sol.id_usuario)
        )
        user = result_user.scalar_one_or_none()
        
        # Obtener estado
        result_estado = await db.execute(
            select(EstadoSolicitud).where(EstadoSolicitud.id_estado_solicitud == sol.id_estado)
        )
        estado_sol = result_estado.scalar_one_or_none()
        
        # Contar artículos por estado
        result_arts = await db.execute(
            select(
                Articulo.id_estado,
                func.count(Articulo.id_articulo).label("count")
            ).where(
                Articulo.id_solicitud == sol.id_solicitud
            ).group_by(Articulo.id_estado)
        )
        arts_by_estado = dict(result_arts.all())
        
        # Mapear estados a nombres
        estado_evaluado = await _obtener_estado_articulo(db, "evaluado")
        estado_rechazado = await _obtener_estado_articulo(db, "rechazado")
        estado_pendiente = await _obtener_estado_articulo(db, "pendiente")
        
        items.append(
            SolicitudListItemAdmin(
                id_solicitud=sol.id_solicitud,
                id_usuario=sol.id_usuario,
                usuario_nombre=user.Nombre if user else "Desconocido",
                usuario_correo=user.Correo if user else "",
                estado=estado_sol.nombre if estado_sol else "desconocido",
                fecha_envio=sol.fecha_envio.isoformat() if sol.fecha_envio else "",
                metodo_entrega=sol.metodo_entrega,
                direccion_entrega=sol.direccion_entrega,
                total_articulos=sum(arts_by_estado.values()),
                articulos_aprobados=arts_by_estado.get(estado_evaluado.id_estado_articulo, 0),
                articulos_rechazados=arts_by_estado.get(estado_rechazado.id_estado_articulo, 0),
                articulos_pendientes=arts_by_estado.get(estado_pendiente.id_estado_articulo, 0),
            )
        )
    
    return SolicitudesListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


# ============================================================
# 2. DETALLE DE SOLICITUD
# ============================================================
@router.get(
    "/{id_solicitud}",
    response_model=SolicitudDetalleAdmin,
    summary="Obtener detalle completo de una solicitud",
    description="**Permisos:** ADMINISTRADOR, SUPERVISOR, VALUADOR"
)
async def obtener_detalle_solicitud(
    id_solicitud: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_id_usuario_attr(current_user)
    
    if not await _tiene_permisos_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Sin permisos")
    
    # Solicitud
    result_sol = await db.execute(
        select(Solicitud).where(Solicitud.id_solicitud == id_solicitud)
    )
    sol = result_sol.scalar_one_or_none()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    # Cliente
    result_user = await db.execute(
        select(User).where(User.ID_Usuario == sol.id_usuario)
    )
    user = result_user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    cliente_info = ClienteInfoAdmin(
        id_usuario=user.ID_Usuario,
        nombre=user.Nombre,
        correo=user.Correo,
        telefono=user.Telefono,
        direccion=user.Direccion
    )
    
    # Estado
    result_estado = await db.execute(
        select(EstadoSolicitud).where(EstadoSolicitud.id_estado_solicitud == sol.id_estado)
    )
    estado_sol = result_estado.scalar_one_or_none()
    
    # Artículos
    result_arts = await db.execute(
        select(Articulo).where(Articulo.id_solicitud == id_solicitud).order_by(Articulo.id_articulo)
    )
    articulos = result_arts.scalars().all()
    
    articulos_detalle: List[ArticuloDetalleAdmin] = []
    contadores = {"total": len(articulos), "aprobados": 0, "rechazados": 0, "pendientes": 0}
    
    for art in articulos:
        # Estado del artículo
        result_estado_art = await db.execute(
            select(EstadoArticulo).where(EstadoArticulo.id_estado_articulo == art.id_estado)
        )
        estado_art = result_estado_art.scalar_one_or_none()
        estado_nombre = estado_art.nombre.lower() if estado_art else "desconocido"
        
        # Actualizar contadores
        if estado_nombre == "evaluado":
            contadores["aprobados"] += 1
        elif estado_nombre == "rechazado":
            contadores["rechazados"] += 1
        elif estado_nombre == "pendiente":
            contadores["pendientes"] += 1
        
        # Tipo
        result_tipo = await db.execute(
            select(CatTipoArticulo).where(CatTipoArticulo.id_tipo == art.id_tipo)
        )
        tipo = result_tipo.scalar_one_or_none()
        
        # Fotos
        result_fotos = await db.execute(
            select(ArticuloFoto).where(ArticuloFoto.id_articulo == art.id_articulo).order_by(ArticuloFoto.orden)
        )
        fotos_db = result_fotos.scalars().all()
        fotos = [ArticuloFotoAdmin(id_foto=f.id_foto, url=f.url, orden=f.orden) for f in fotos_db]
        
        # Préstamo (si existe)
        result_prest = await db.execute(
            select(Prestamo).where(Prestamo.id_articulo == art.id_articulo)
        )
        prestamo = result_prest.scalar_one_or_none()
        
        tiene_prestamo = False
        prestamo_id = None
        prestamo_estado = None
        
        if prestamo:
            tiene_prestamo = True
            prestamo_id = prestamo.id_prestamo
            result_estado_prest = await db.execute(
                select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
            )
            estado_prest = result_estado_prest.scalar_one_or_none()
            prestamo_estado = estado_prest.nombre if estado_prest else None
        
        articulos_detalle.append(
            ArticuloDetalleAdmin(
                id_articulo=art.id_articulo,
                id_tipo=art.id_tipo,
                tipo_nombre=tipo.nombre if tipo else None,
                descripcion=art.descripcion,
                valor_estimado=float(art.valor_estimado),
                valor_aprobado=float(art.valor_aprobado) if art.valor_aprobado else None,
                condicion=art.condicion,
                estado=estado_art.nombre if estado_art else "desconocido",
                fotos=fotos,
                tiene_prestamo=tiene_prestamo,
                prestamo_id=prestamo_id,
                prestamo_estado=prestamo_estado
            )
        )
    
    return SolicitudDetalleAdmin(
        id_solicitud=sol.id_solicitud,
        estado=estado_sol.nombre if estado_sol else "desconocido",
        fecha_envio=sol.fecha_envio.isoformat() if sol.fecha_envio else "",
        metodo_entrega=sol.metodo_entrega,
        direccion_entrega=sol.direccion_entrega,
        cliente=cliente_info,
        articulos=articulos_detalle,
        resumen=contadores
    )


# ============================================================
# 3. EVALUAR ARTÍCULO (Aprobar o Rechazar)
# ============================================================
@router.post(
    "/articulos/{id_articulo}/evaluar",
    response_model=EvaluarArticuloOut,
    status_code=status.HTTP_200_OK,
    summary="Evaluar artículo (aprobar o rechazar)",
    description=(
        "Aprueba o rechaza un artículo de una solicitud. "
        "Si aprueba, crea el préstamo en estado 'aprobado_pendiente_entrega'. "
        "**Permisos:** ADMINISTRADOR, SUPERVISOR, VALUADOR"
    )
)
async def evaluar_articulo(
    id_articulo: int = Path(..., ge=1),
    payload: EvaluarArticuloIn = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)
    
    if not await _tiene_permisos_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Sin permisos")
    
    accion = payload.accion.lower()
    if accion not in ("aprobar", "rechazar"):
        raise HTTPException(status_code=400, detail="Acción debe ser 'aprobar' o 'rechazar'")
    
    # Validar payload según acción
    if accion == "aprobar" and not payload.valor_aprobado:
        raise HTTPException(status_code=400, detail="valor_aprobado es obligatorio para aprobar")
    
    if accion == "rechazar" and not payload.motivo_rechazo:
        raise HTTPException(status_code=400, detail="motivo_rechazo es obligatorio para rechazar")
    
    # Obtener artículo
    result_art = await db.execute(
        select(Articulo).where(Articulo.id_articulo == id_articulo)
    )
    articulo = result_art.scalar_one_or_none()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    
    # Verificar que esté en estado pendiente
    result_estado_art = await db.execute(
        select(EstadoArticulo).where(EstadoArticulo.id_estado_articulo == articulo.id_estado)
    )
    estado_actual = result_estado_art.scalar_one_or_none()
    if not estado_actual or estado_actual.nombre.lower() != "pendiente":
        raise HTTPException(
            status_code=409,
            detail=f"El artículo está en estado '{estado_actual.nombre if estado_actual else 'desconocido'}', no se puede evaluar"
        )
    
    # Verificar que no tenga préstamo ya creado (regla 1:1)
    result_prest = await db.execute(
        select(Prestamo).where(Prestamo.id_articulo == id_articulo)
    )
    if result_prest.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El artículo ya tiene un préstamo asociado")
    
    # APROBAR
    if accion == "aprobar":
        # Estados necesarios
        estado_evaluado = await _obtener_estado_articulo(db, "evaluado")
        estado_prestamo_aprobado = await _obtener_estado_prestamo(db, "aprobado_pendiente_entrega")
        
        # Actualizar artículo
        articulo.id_estado = estado_evaluado.id_estado_articulo
        articulo.valor_aprobado = payload.valor_aprobado
        await db.flush()
        
        # Calcular fechas del préstamo
        plazo_dias = payload.plazo_dias or 30
        fecha_inicio = date.today()
        fecha_vencimiento = fecha_inicio + timedelta(days=plazo_dias)
        
        # Crear préstamo
        nuevo_prestamo = Prestamo(
            id_articulo=articulo.id_articulo,
            id_usuario_evaluador=user_id,
            id_estado=estado_prestamo_aprobado.id_estado_prestamo,
            fecha_inicio=fecha_inicio,
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
        
        # Auditoría
        await registrar_auditoria(
            db=db,
            usuario_id=user_id,
            accion="APROBAR_ARTICULO",
            modulo="Admin_Solicitudes",
            detalle=f"Artículo {id_articulo} aprobado por Q{float(payload.valor_aprobado):.2f}, Préstamo {nuevo_prestamo.id_prestamo} creado",
            valores_anteriores={"estado": estado_actual.nombre, "valor_aprobado": None},
            valores_nuevos={
                "estado": "evaluado",
                "valor_aprobado": float(payload.valor_aprobado),
                "prestamo_id": nuevo_prestamo.id_prestamo
            }
        )
        
        await db.commit()
        await db.refresh(articulo)
        await db.refresh(nuevo_prestamo)
        
        return EvaluarArticuloOut(
            id_articulo=articulo.id_articulo,
            accion="aprobado",
            estado_articulo="evaluado",
            valor_aprobado=float(articulo.valor_aprobado),
            prestamo=PrestamoCreadoInfo(
                id_prestamo=nuevo_prestamo.id_prestamo,
                estado="aprobado_pendiente_entrega",
                fecha_inicio=nuevo_prestamo.fecha_inicio,
                fecha_vencimiento=nuevo_prestamo.fecha_vencimiento,
                monto_prestamo=float(nuevo_prestamo.monto_prestamo)
            )
        )
    
    # RECHAZAR
    else:  # accion == "rechazar"
        estado_rechazado = await _obtener_estado_articulo(db, "rechazado")
        
        # Actualizar artículo
        articulo.id_estado = estado_rechazado.id_estado_articulo
        articulo.valor_aprobado = None
        await db.flush()
        
        # Auditoría
        await registrar_auditoria(
            db=db,
            usuario_id=user_id,
            accion="RECHAZAR_ARTICULO",
            modulo="Admin_Solicitudes",
            detalle=f"Artículo {id_articulo} rechazado. Motivo: {payload.motivo_rechazo}",
            valores_anteriores={"estado": estado_actual.nombre},
            valores_nuevos={"estado": "rechazado", "motivo": payload.motivo_rechazo}
        )
        
        await db.commit()
        await db.refresh(articulo)
        
        return EvaluarArticuloOut(
            id_articulo=articulo.id_articulo,
            accion="rechazado",
            estado_articulo="rechazado",
            motivo_rechazo=payload.motivo_rechazo
        )


# ============================================================
# 4. CAMBIAR ESTADO DE SOLICITUD (Manual)
# ============================================================
@router.patch(
    "/{id_solicitud}/estado",
    response_model=CambiarEstadoSolicitudOut,
    summary="Cambiar estado de una solicitud manualmente",
    description=(
        "Permite cambiar el estado de una solicitud de forma manual. "
        "Útil para casos especiales o correcciones. "
        "**Permisos:** ADMINISTRADOR, SUPERVISOR"
    )
)
async def cambiar_estado_solicitud(
    id_solicitud: int = Path(..., ge=1),
    payload: CambiarEstadoSolicitudIn = ...,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)
    
    # Solo ADMIN y SUPERVISOR pueden cambiar estados manualmente
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "SUPERVISOR"]):
        raise HTTPException(
            status_code=403,
            detail="Requiere rol ADMINISTRADOR o SUPERVISOR"
        )
    
    # Validar estado destino
    estados_validos = {"pendiente", "en_revision", "evaluada", "rechazada"}
    nuevo_estado_norm = payload.nuevo_estado.lower()
    if nuevo_estado_norm not in estados_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Estado inválido. Válidos: {', '.join(sorted(estados_validos))}"
        )
    
    # Obtener solicitud
    result_sol = await db.execute(
        select(Solicitud).where(Solicitud.id_solicitud == id_solicitud)
    )
    solicitud = result_sol.scalar_one_or_none()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    # Estado actual
    result_estado_actual = await db.execute(
        select(EstadoSolicitud).where(EstadoSolicitud.id_estado_solicitud == solicitud.id_estado)
    )
    estado_actual = result_estado_actual.scalar_one_or_none()
    estado_anterior_nombre = estado_actual.nombre if estado_actual else "desconocido"
    
    # Estado nuevo
    estado_nuevo = await _obtener_estado_solicitud(db, nuevo_estado_norm)
    
    # Evitar cambio innecesario
    if solicitud.id_estado == estado_nuevo.id_estado_solicitud:
        raise HTTPException(
            status_code=400,
            detail=f"La solicitud ya está en estado '{estado_anterior_nombre}'"
        )
    
    # Actualizar
    solicitud.id_estado = estado_nuevo.id_estado_solicitud
    await db.flush()
    
    # Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="CAMBIAR_ESTADO_SOLICITUD",
        modulo="Admin_Solicitudes",
        detalle=f"Solicitud {id_solicitud}: {estado_anterior_nombre} → {nuevo_estado_norm}. Motivo: {payload.motivo or 'N/A'}",
        valores_anteriores={"estado": estado_anterior_nombre},
        valores_nuevos={"estado": nuevo_estado_norm, "motivo": payload.motivo}
    )
    
    await db.commit()
    await db.refresh(solicitud)
    
    return CambiarEstadoSolicitudOut(
        id_solicitud=solicitud.id_solicitud,
        estado_anterior=estado_anterior_nombre,
        estado_nuevo=nuevo_estado_norm,
        actualizado_en=datetime.now(timezone.utc).isoformat()
    )


# ============================================================
# 5. ESTADÍSTICAS (Dashboard)
# ============================================================
@router.get(
    "/stats/dashboard",
    response_model=EstadisticasSolicitudesOut,
    summary="Estadísticas para dashboard administrativo",
    description=(
        "Retorna estadísticas generales de solicitudes. "
        "**Permisos:** ADMINISTRADOR, SUPERVISOR, VALUADOR"
    )
)
async def obtener_estadisticas_solicitudes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_id_usuario_attr(current_user)
    
    if not await _tiene_permisos_admin(current_user, db):
        raise HTTPException(status_code=403, detail="Sin permisos")
    
    # Total de solicitudes
    result_total = await db.execute(select(func.count(Solicitud.id_solicitud)))
    total_solicitudes = result_total.scalar() or 0
    
    # Por estado
    result_por_estado = await db.execute(
        select(
            EstadoSolicitud.nombre,
            func.count(Solicitud.id_solicitud)
        )
        .join(EstadoSolicitud, EstadoSolicitud.id_estado_solicitud == Solicitud.id_estado)
        .group_by(EstadoSolicitud.nombre)
    )
    por_estado: Dict[str, int] = {nombre: count for nombre, count in result_por_estado.all()}
    
    # Solicitudes hoy
    hoy = date.today()
    result_hoy = await db.execute(
        select(func.count(Solicitud.id_solicitud))
        .where(func.date(Solicitud.fecha_envio) == hoy)
    )
    solicitudes_hoy = result_hoy.scalar() or 0
    
    # Solicitudes esta semana (últimos 7 días)
    hace_7_dias = hoy - timedelta(days=7)
    result_semana = await db.execute(
        select(func.count(Solicitud.id_solicitud))
        .where(func.date(Solicitud.fecha_envio) >= hace_7_dias)
    )
    solicitudes_semana = result_semana.scalar() or 0
    
    # Artículos pendientes de evaluación
    estado_pendiente = await _obtener_estado_articulo(db, "pendiente")
    result_pendientes = await db.execute(
        select(func.count(Articulo.id_articulo))
        .where(Articulo.id_estado == estado_pendiente.id_estado_articulo)
    )
    articulos_pendientes = result_pendientes.scalar() or 0
    
    return EstadisticasSolicitudesOut(
        total_solicitudes=total_solicitudes,
        por_estado=por_estado,
        solicitudes_hoy=solicitudes_hoy,
        solicitudes_semana=solicitudes_semana,
        articulos_pendientes_evaluacion=articulos_pendientes
    )