from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models.solicitud import Solicitud
from app.db.models.user import User
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.articulo import Articulo

from app.db.models.estado_articulo import EstadoArticulo



router = APIRouter(
    prefix="/solicitudes-filtros",
    tags=["Solicitudes - Filtros"]
)


@router.get("", response_model=None)
async def listar_solicitudes_con_filtros(
    estado: Optional[str] = Query(None, description="Filtro por nombre de estado (pendiente, evaluada, rechazada)"),
    usuario_id: Optional[int] = Query(None, description="Filtro por cliente (solo admins)"),
    metodo_entrega: Optional[str] = Query(None, description="Filtro: 'domicilio' | 'oficina'"),
    fecha_desde: Optional[date] = Query(None, description="Filtro por fecha_envio >= fecha_desde"),
    fecha_hasta: Optional[date] = Query(None, description="Filtro por fecha_envio <= fecha_hasta"),
    limit: int = Query(50, ge=1, le=100, description="Cantidad de resultados por página"),
    offset: int = Query(0, ge=0, description="Número de resultados a omitir"),
    sort: str = Query("desc", regex="^(asc|desc)$", description="Ordenamiento por fecha: 'asc' o 'desc'"),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar solicitudes con filtros avanzados
    """
    
    # ========== CONSTRUCCIÓN DE LA QUERY BASE ==========
    query = (
        select(Solicitud)
        .join(EstadoSolicitud, Solicitud.id_estado == EstadoSolicitud.id_estado)
        .join(User, Solicitud.id_usuario == User.id_usuario)
        .options(
            selectinload(Solicitud.estado_solicitud),
            selectinload(Solicitud.usuario)
        )
    )
    
    # ========== APLICAR FILTROS ==========
    condiciones = []
    
    if estado:
        condiciones.append(EstadoSolicitud.nombre.ilike(f"%{estado}%"))
    
    if usuario_id:
        condiciones.append(Solicitud.id_usuario == usuario_id)
    
    if metodo_entrega:
        condiciones.append(Solicitud.metodo_entrega == metodo_entrega)
    
    if fecha_desde:
        condiciones.append(Solicitud.fecha_envio >= fecha_desde)
    
    if fecha_hasta:
        condiciones.append(Solicitud.fecha_envio <= fecha_hasta)
    
    if condiciones:
        query = query.where(and_(*condiciones))
    
    # ========== CONTAR TOTAL ==========
    count_query = select(func.count()).select_from(query.subquery())
    result_count = await db.execute(count_query)
    total = result_count.scalar() or 0
    
    # ========== ORDENAMIENTO ==========
    if sort == "desc":
        query = query.order_by(Solicitud.fecha_envio.desc())
    else:
        query = query.order_by(Solicitud.fecha_envio.asc())
    
    # ========== PAGINACIÓN ==========
    query = query.limit(limit).offset(offset)
    
    # ========== EJECUTAR QUERY ==========
    result = await db.execute(query)
    solicitudes = result.scalars().all()
    
    # ========== CONSTRUIR RESPUESTA ========== 
    from app.schemas.solicitud_filtro_models import SolicitudConDetalleOut, SolicitudListResponse
    items_con_detalle = []
    for solicitud in solicitudes:
        # Contar artículos por estado
        query_articulos = (
            select(
                func.count().label("total"),
                func.sum(
                    func.case(
                        (EstadoArticulo.nombre.in_(["en evaluacion", "pendiente"]), 1),
                        else_=0
                    )
                ).label("pendientes"),
                func.sum(
                    func.case(
                        (EstadoArticulo.nombre.in_(["evaluado", "aprobado", "rechazado"]), 1),
                        else_=0
                    )
                ).label("evaluados")
            )
            .select_from(Articulo)
            .join(EstadoArticulo, Articulo.id_estado == EstadoArticulo.id_estado)
            .where(Articulo.id_solicitud == solicitud.id_solicitud)
        )
        result_articulos = await db.execute(query_articulos)
        contadores = result_articulos.first()
        # Construir objeto de respuesta
        solicitud_dict = {
            "id_solicitud": solicitud.id_solicitud,
            "id_usuario": solicitud.id_usuario,
            "usuario": {
                "nombre": solicitud.usuario.nombre if solicitud.usuario else "Desconocido",
                "correo": solicitud.usuario.correo if solicitud.usuario else ""
            },
            "estado": {
                "id": solicitud.estado_solicitud.id_estado,
                "nombre": solicitud.estado_solicitud.nombre
            },
            "fecha_envio": solicitud.fecha_envio,
            "metodo_entrega": solicitud.metodo_entrega,
            "direccion_entrega": solicitud.direccion_entrega,
            "total_articulos": contadores.total or 0,
            "articulos_pendientes": contadores.pendientes or 0,
            "articulos_evaluados": contadores.evaluados or 0
        }
        items_con_detalle.append(SolicitudConDetalleOut(**solicitud_dict))
    return SolicitudListResponse(
        items=items_con_detalle,
        total=total
    )