# app/api/routers/inventario.py
from fastapi import APIRouter, HTTPException, Query, Depends, Path, status
from typing import Optional
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_

from app.schemas.inventario import (
    InventarioQueryParams,
    InventarioResponse,
    InventarioItem,
    ResumenInventario,
    AjustarPrecioRequest,
    AjustarPrecioResponse,
    ArticuloBase,
    EstadoBase,
    PrestamoOrigenBase
)
from app.api.deps import get_db, get_current_user_admin
from app.db.models.inventario_venta import InventarioVenta
from app.db.models.estado_inventario import EstadoInventario

router = APIRouter(prefix="/inventario", tags=["inventario"])


# ===================== GET /inventario =====================
@router.get("/", response_model=InventarioResponse)
async def listar_inventario(
    estado: Optional[str] = Query(None, description="Estado: disponible, en_venta, vendido"),
    dias_en_bodega_min: Optional[int] = Query(None, ge=0),
    dias_en_bodega_max: Optional[int] = Query(None, ge=0),
    precio_min: Optional[float] = Query(None, ge=0),
    precio_max: Optional[float] = Query(None, ge=0),
    tipo_articulo: Optional[int] = Query(None, description="ID del tipo de artículo"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("fecha_ingreso", regex="^(fecha_ingreso|precio_actual|dias_en_bodega)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_admin)  # Solo Admin/Operador
):
    """
    Listar artículos físicos en inventario/bodega
    
    Permisos: Admin/Operador
    """
    try:
        # Query base con todos los joins necesarios
        query = """
            SELECT 
                iv.Id_Inventario,
                iv.Precio_Base,
                iv.Precio_Actual,
                iv.Fecha_Ingreso,
                DATEDIFF(CURDATE(), iv.Fecha_Ingreso) as dias_en_bodega,
                
                -- Datos del artículo
                a.Id_articulo,
                a.Descripcion,
                t.Nombre as tipo_nombre,
                c.Nombre as condicion_nombre,
                
                -- Estado del inventario
                ei.Id_Estado_Inventario,
                ei.Nombre as estado_nombre,
                
                -- Prestamo origen (si existe)
                p.Id_prestamo,
                u.Nombre as cliente_nombre,
                p.Monto_Total as monto_original,
                p.Motivo_Ingreso
                
            FROM Inventario_Venta iv
            JOIN Articulo a ON a.Id_articulo = iv.Id_articulo
            JOIN Cat_Tipo_Articulo t ON t.IdTipo = a.ID_tipo
            JOIN Cat_Condicion_Articulo c ON c.IdCondicion = a.Id_condicion
            JOIN Estado_Inventario ei ON ei.Id_Estado_Inventario = iv.Id_estado
            LEFT JOIN Prestamo p ON p.Id_Articulo = a.Id_articulo
            LEFT JOIN Solicitud s ON s.Id_Solicitud = a.Id_Solicitud
            LEFT JOIN Usuario u ON u.ID_Usuario = s.Id_Usuario
            WHERE 1=1
        """
        
        # Parámetros para la query
        params = {}
        
        # Aplicar filtros
        if estado:
            query += " AND LOWER(ei.Nombre) = LOWER(:estado)"
            params["estado"] = estado
            
        if tipo_articulo:
            query += " AND a.ID_tipo = :tipo_articulo"
            params["tipo_articulo"] = tipo_articulo
            
        if dias_en_bodega_min is not None:
            query += " AND DATEDIFF(CURDATE(), iv.Fecha_Ingreso) >= :dias_min"
            params["dias_min"] = dias_en_bodega_min
            
        if dias_en_bodega_max is not None:
            query += " AND DATEDIFF(CURDATE(), iv.Fecha_Ingreso) <= :dias_max"
            params["dias_max"] = dias_en_bodega_max
            
        if precio_min is not None:
            query += " AND iv.Precio_Actual >= :precio_min"
            params["precio_min"] = precio_min
            
        if precio_max is not None:
            query += " AND iv.Precio_Actual <= :precio_max"
            params["precio_max"] = precio_max
        
        # Query para el total antes de aplicar limit/offset
        count_query = f"SELECT COUNT(*) as total FROM ({query}) as subq"
        total = db.execute(text(count_query), params).scalar()
        
        # Aplicar ordenamiento
        order_column = {
            "fecha_ingreso": "iv.Fecha_Ingreso",
            "precio_actual": "iv.Precio_Actual",
            "dias_en_bodega": "dias_en_bodega"
        }.get(sort_by, "iv.Fecha_Ingreso")
        
        query += f" ORDER BY {order_column} {sort_order.upper()}"
        
        # Aplicar paginación
        query += " LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        # Ejecutar query principal
        result = db.execute(text(query), params).fetchall()
        
        # Procesar resultados
        items = []
        for row in result:
            # Obtener fotos del artículo
            fotos_query = """
                SELECT Url 
                FROM Articulo_Foto 
                WHERE Id_articulo = :id_articulo 
                ORDER BY Orden
            """
            fotos = db.execute(
                text(fotos_query), 
                {"id_articulo": row.Id_articulo}
            ).fetchall()
            fotos_list = [f.Url for f in fotos] if fotos else []
            
            # Construir objeto de respuesta
            item = InventarioItem(
                id_inventario=row.Id_Inventario,
                articulo=ArticuloBase(
                    id=row.Id_articulo,
                    descripcion=row.Descripcion,
                    tipo=row.tipo_nombre,
                    condicion=row.condicion_nombre,
                    fotos=fotos_list
                ),
                estado=EstadoBase(
                    id=row.Id_Estado_Inventario,
                    nombre=row.estado_nombre
                ),
                precio_base=row.Precio_Base,
                precio_actual=row.Precio_Actual,
                dias_en_bodega=row.dias_en_bodega,
                fecha_ingreso=row.Fecha_Ingreso,
                prestamo_origen=(
                    PrestamoOrigenBase(
                        id=row.Id_prestamo,
                        cliente=row.cliente_nombre,
                        monto_original=row.monto_original,
                        motivo_ingreso=row.Motivo_Ingreso or "incumplimiento"
                    ) if row.Id_prestamo else None
                )
            )
            items.append(item)
        
        # Calcular resumen
        resumen_query = """
            SELECT 
                SUM(iv.Precio_Actual) as valor_total,
                SUM(CASE WHEN LOWER(ei.Nombre) = 'disponible' THEN 1 ELSE 0 END) as disponibles,
                SUM(CASE WHEN LOWER(ei.Nombre) = 'vendido' THEN 1 ELSE 0 END) as vendidos,
                AVG(DATEDIFF(CURDATE(), iv.Fecha_Ingreso)) as promedio_dias
            FROM Inventario_Venta iv
            JOIN Estado_Inventario ei ON ei.Id_Estado_Inventario = iv.Id_estado
        """
        resumen_result = db.execute(text(resumen_query)).first()
        
        resumen = ResumenInventario(
            valor_total_inventario=resumen_result.valor_total or 0,
            articulos_disponibles=resumen_result.disponibles or 0,
            articulos_vendidos=resumen_result.vendidos or 0,
            promedio_dias_bodega=round(resumen_result.promedio_dias or 0, 2)
        )
        
        return InventarioResponse(
            items=items,
            total=total or 0,
            resumen=resumen
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener inventario: {str(e)}"
        )


# ===================== PATCH /inventario/{id}/ajustar-precio =====================
@router.patch("/{id_inventario}/ajustar-precio", response_model=AjustarPrecioResponse)
async def ajustar_precio_inventario(
    id_inventario: int = Path(..., gt=0),
    request: AjustarPrecioRequest = ...,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_admin)  # Solo Admin
):
    """
    Ajustar precio de un artículo en inventario (descuentos por tiempo en bodega)
    
    Permisos: Solo Admin
    """
    try:
        # Verificar que existe el item en inventario
        check_query = """
            SELECT 
                Id_Inventario,
                Precio_Base,
                Precio_Actual
            FROM Inventario_Venta
            WHERE Id_Inventario = :id_inventario
        """
        
        inventario = db.execute(
            text(check_query), 
            {"id_inventario": id_inventario}
        ).first()
        
        if not inventario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artículo de inventario {id_inventario} no encontrado"
            )
        
        # Validaciones de negocio
        if request.precio_nuevo > inventario.Precio_Base:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El precio nuevo ({request.precio_nuevo}) no puede ser mayor al precio base ({inventario.Precio_Base})"
            )
        
        precio_anterior = inventario.Precio_Actual
        
        # Iniciar transacción
        db.begin()
        
        try:
            # Actualizar precio
            update_query = """
                UPDATE Inventario_Venta 
                SET 
                    Precio_Actual = :precio_nuevo,
                    Fecha_Modificacion = NOW()
                WHERE Id_Inventario = :id_inventario
            """
            
            db.execute(text(update_query), {
                "precio_nuevo": request.precio_nuevo,
                "id_inventario": id_inventario
            })
            
            # Registrar en auditoría
            audit_query = """
                INSERT INTO Auditoria (
                    Id_Usuario,
                    Accion,
                    Tabla_Afectada,
                    Id_Registro,
                    Valor_Anterior,
                    Valor_Nuevo,
                    Fecha_Hora,
                    Descripcion
                ) VALUES (
                    :id_usuario,
                    'AJUSTAR_PRECIO_INVENTARIO',
                    'Inventario_Venta',
                    :id_inventario,
                    :valor_anterior,
                    :valor_nuevo,
                    NOW(),
                    :descripcion
                )
            """
            
            descripcion = f"{request.motivo}. Precio: {precio_anterior} -> {request.precio_nuevo}"
            
            db.execute(text(audit_query), {
                "id_usuario": current_user.id,
                "id_inventario": id_inventario,
                "valor_anterior": str(precio_anterior),
                "valor_nuevo": str(request.precio_nuevo),
                "descripcion": descripcion
            })
            
            # Confirmar transacción
            db.commit()
            
            # Calcular descuento
            descuento = float(precio_anterior) - float(request.precio_nuevo)
            porcentaje = (descuento / float(precio_anterior)) * 100 if precio_anterior > 0 else 0
            
            return AjustarPrecioResponse(
                id_inventario=id_inventario,
                precio_anterior=precio_anterior,
                precio_actual=request.precio_nuevo,
                descuento_aplicado=Decimal(str(descuento)),
                porcentaje_descuento=round(porcentaje, 2)
            )
            
        except Exception as e:
            db.rollback()
            raise e
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al ajustar precio: {str(e)}"
        )