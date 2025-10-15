from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models.solicitud import Solicitud
from app.db.models.usuario import Usuario
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.schemas.solicitudes_filtros import SolicitudConDetalleOut, SolicitudListResponse


router = APIRouter(
    prefix="/solicitudes-filtros",
    tags=["Solicitudes - Filtros"]
)


@router.get("", response_model=SolicitudListResponse)
async def listar_solicitudes_con_filtros(
    estado: Optional[str] = Query(None, description="Filtro por nombre de estado (pendiente, evaluada, rechazada)"),
    usuario_id: Optional[int] = Query(None, description="Filtro por cliente (solo admins)"),
    metodo_entrega: Optional[str] = Query(None, description="Filtro: 'domicilio' | 'oficina'"),
    fecha_desde: Optional[date] = Query(None, description="Filtro por Fecha_envio >= fecha_desde"),
    fecha_hasta: Optional[date] = Query(None, description="Filtro por Fecha_envio <= fecha_hasta"),
    limit: int = Query(50, ge=1, le=100, description="Cantidad de resultados por página"),
    offset: int = Query(0, ge=0, description="Número de resultados a omitir"),
    sort: str = Query("desc", regex="^(asc|desc)$", description="Ordenamiento por fecha: 'asc' o 'desc'"),
    db: AsyncSession = Depends(get_db)
):
    """
    Listar solicitudes con filtros avanzados
    
    **Filtros disponibles:**
    - `estado`: Filtra por nombre del estado (ej: "pendiente", "evaluada")
    - `usuario_id`: Filtra por ID del cliente (solo admins)
    - `metodo_entrega`: Filtra por método ("domicilio" o "oficina")
    - `fecha_desde` y `fecha_hasta`: Rango de fechas de envío
    - Paginación: `limit` y `offset`
    - Ordenamiento: `sort` (asc/desc por fecha de envío)
    
    **Joins:**
    - Solicitud → Estado_Solicitud (siempre)
    - Solicitud → Usuario (para mostrar nombre del cliente)
    
    **Retorna:** Lista de solicitudes con contadores de artículos y total de registros
    """
    
    # ========== CONSTRUCCIÓN DE LA QUERY BASE ==========
    query = (
        select(Solicitud)
        .join(EstadoSolicitud, Solicitud.Id_Estado == EstadoSolicitud.Id_Estado)
        .join(Usuario, Solicitud.Id_Usuario == Usuario.Id_Usuario)
        .options(
            selectinload(Solicitud.estado_solicitud),
            selectinload(Solicitud.usuario)
        )
    )
    
    # ========== APLICAR FILTROS ==========
    condiciones = []
    
    # Filtro por estado (nombre)
    if estado:
        condiciones.append(EstadoSolicitud.Nombre.ilike(f"%{estado}%"))
    
    # Filtro por usuario
    if usuario_id:
        condiciones.append(Solicitud.Id_Usuario == usuario_id)
    
    # Filtro por método de entrega
    if metodo_entrega:
        condiciones.append(Solicitud.Metodo_entrega == metodo_entrega)
    
    # Filtro por fecha desde
    if fecha_desde:
        condiciones.append(Solicitud.Fecha_envio >= fecha_desde)
    
    # Filtro por fecha hasta
    if fecha_hasta:
        condiciones.append(Solicitud.Fecha_envio <= fecha_hasta)
    
    # Aplicar condiciones si existen
    if condiciones:
        query = query.where(and_(*condiciones))
    
    # ========== CONTAR TOTAL (antes de paginación) ==========
    count_query = select(func.count()).select_from(query.subquery())
    result_count = await db.execute(count_query)
    total = result_count.scalar() or 0
    
    # ========== ORDENAMIENTO ==========
    if sort == "desc":
        query = query.order_by(Solicitud.Fecha_envio.desc())
    else:
        query = query.order_by(Solicitud.Fecha_envio.asc())
    
    # ========== PAGINACIÓN ==========
    query = query.limit(limit).offset(offset)
    
    # ========== EJECUTAR QUERY ==========
    result = await db.execute(query)
    solicitudes = result.scalars().all()
    
    # ========== CONSTRUIR RESPUESTA CON CONTADORES ==========
    items_con_detalle = []
    
    for solicitud in solicitudes:
        # Contar artículos por estado
        query_articulos = (
            select(
                func.count().label("total"),
                func.sum(
                    func.case(
                        (EstadoArticulo.Nombre.in_(["en evaluacion", "pendiente"]), 1),
                        else_=0
                    )
                ).label("pendientes"),
                func.sum(
                    func.case(
                        (EstadoArticulo.Nombre.in_(["evaluado", "aprobado", "rechazado"]), 1),
                        else_=0
                    )
                ).label("evaluados")
            )
            .select_from(Articulo)
            .join(EstadoArticulo, Articulo.Id_Estado == EstadoArticulo.Id_Estado)
            .where(Articulo.Id_Solicitud == solicitud.Id_Solicitud)
        )
        
        result_articulos = await db.execute(query_articulos)
        contadores = result_articulos.first()
        
        # Construir objeto de respuesta
        solicitud_dict = {
            "Id_Solicitud": solicitud.Id_Solicitud,
            "Id_Usuario": solicitud.Id_Usuario,
            "usuario": {
                "nombre": solicitud.usuario.Nombre if solicitud.usuario else "Desconocido",
                "correo": solicitud.usuario.Correo if solicitud.usuario else ""
            },
            "estado": {
                "id": solicitud.estado_solicitud.Id_Estado,
                "nombre": solicitud.estado_solicitud.Nombre
            },
            "Fecha_envio": solicitud.Fecha_envio,
            "Metodo_entrega": solicitud.Metodo_entrega,
            "Direccion_entrega": solicitud.Direccion_entrega,
            "total_articulos": contadores.total or 0,
            "articulos_pendientes": contadores.pendientes or 0,
            "articulos_evaluados": contadores.evaluados or 0
        }
        
        items_con_detalle.append(SolicitudConDetalleOut(**solicitud_dict))
    
    # ========== RETORNAR RESPUESTA ==========
    return SolicitudListResponse(
        items=items_con_detalle,
        total=total
    )