# ============================================================
# app/api/routers/inventario_completo.py
# ============================================================
"""
Endpoint para obtener el inventario completo de artículos
con toda su información detallada, sin importar el estado.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app.db.database import get_db
from app.db.models.articulo import Articulo
from app.db.models.articulo_foto import ArticuloFoto
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.solicitud import Solicitud
from app.db.models.user import User
from app.db.models.inventario_venta import InventarioVenta
from app.db.models.estado_inventario import EstadoInventario

from app.schemas.inventario_completo import (
    InventarioCompletoListResponse,
    InventarioCompletoItemOut,
)

router = APIRouter(prefix="/inventario-completo", tags=["inventario-completo"])


@router.get("", response_model=InventarioCompletoListResponse)
async def listar_inventario_completo(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    estado_articulo: Optional[str] = Query(default=None, description="Filtrar por estado del artículo"),
    id_tipo: Optional[int] = Query(default=None, description="Filtrar por tipo de artículo"),
    q: Optional[str] = Query(default=None, description="Buscar en descripción del artículo"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista todos los artículos con información completa:
    - Datos del artículo
    - Fotos
    - Tipo de artículo
    - Estado del artículo
    - Información de la solicitud
    - Cliente (usuario que lo solicitó)
    - Información de inventario (si existe)
    
    Sin importar el estado, trae TODA la información disponible.
    """
    # Query base con joins
    stmt = (
        select(Articulo)
        .join(CatTipoArticulo, CatTipoArticulo.id_tipo == Articulo.id_tipo)
        .join(EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .join(User, User.ID_Usuario == Solicitud.id_usuario)
        .outerjoin(InventarioVenta, InventarioVenta.id_articulo == Articulo.id_articulo)
    )

    # Filtros opcionales
    if estado_articulo:
        stmt = stmt.where(func.lower(EstadoArticulo.nombre) == estado_articulo.lower())
    
    if id_tipo:
        stmt = stmt.where(Articulo.id_tipo == id_tipo)
    
    if q:
        like_pattern = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Articulo.descripcion).like(like_pattern))

    # Contar total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    # Aplicar paginación y orden
    stmt = stmt.order_by(Articulo.id_articulo.desc()).limit(limit).offset(offset)
    
    # Ejecutar query
    result = await db.execute(stmt)
    articulos = result.scalars().all()

    # Construir respuesta detallada
    items = []
    for art in articulos:
        # Obtener fotos
        fotos_result = await db.execute(
            select(ArticuloFoto)
            .where(ArticuloFoto.id_articulo == art.id_articulo)
            .order_by(ArticuloFoto.orden.asc())
        )
        fotos = fotos_result.scalars().all()

        # Obtener tipo
        tipo = await db.get(CatTipoArticulo, art.id_tipo)
        
        # Obtener estado
        estado = await db.get(EstadoArticulo, art.id_estado)
        
        # Obtener solicitud y usuario
        solicitud = await db.get(Solicitud, art.id_solicitud)
        usuario = await db.get(User, solicitud.id_usuario) if solicitud else None

        # Obtener info de inventario
        inventario_result = await db.execute(
            select(InventarioVenta, EstadoInventario.nombre)
            .outerjoin(EstadoInventario, EstadoInventario.id_estado_inventario == InventarioVenta.id_estado)
            .where(InventarioVenta.id_articulo == art.id_articulo)
        )
        inventario_row = inventario_result.first()
        
        inventario_info = None
        if inventario_row:
            inv, estado_inv_nombre = inventario_row
            inventario_info = {
                "id_inventario": inv.id_inventario,
                "estado": estado_inv_nombre or "desconocido",
                "precio_base": float(inv.precio_base),
                "precio_actual": float(inv.precio_actual),
                "dias_en_bodega": inv.dias_en_bodega,
                "fecha_ingreso": inv.fecha_ingreso.isoformat() if inv.fecha_ingreso else None,
            }

        # Construir item
        item = InventarioCompletoItemOut(
            id_articulo=art.id_articulo,
            id_solicitud=art.id_solicitud,
            id_tipo=art.id_tipo,
            tipo_nombre=tipo.nombre if tipo else None,
            id_estado=art.id_estado,
            estado_nombre=estado.nombre if estado else None,
            descripcion=art.descripcion,
            valor_estimado=float(art.valor_estimado),
            valor_aprobado=float(art.valor_aprobado) if art.valor_aprobado else None,
            condicion=art.condicion,
            fotos=[foto.url for foto in fotos],
            solicitud_fecha=solicitud.fecha_envio.isoformat() if solicitud and solicitud.fecha_envio else None,
            solicitud_metodo_entrega=solicitud.metodo_entrega if solicitud else None,
            solicitud_estado=solicitud.estado_nombre if solicitud else None,
            cliente_id=usuario.ID_Usuario if usuario else None,
            cliente_nombre=usuario.Nombre if usuario else None,
            cliente_correo=usuario.Correo if usuario else None,
            cliente_telefono=usuario.Telefono if usuario else None,
            inventario=inventario_info,
        )
        items.append(item)

    return InventarioCompletoListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )