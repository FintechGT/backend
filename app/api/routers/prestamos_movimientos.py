from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from typing import List, Optional
from datetime import date

from app.db.database import get_db
from app.api.deps import get_current_user
from app.schemas.prestamos_movimientos import KardexPrestamoResponse, MovimientoResponse, ResumenMovimientos

# Importar modelos con nombres CORRECTOS
from app.db.models.prestamo_movimiento import PrestamoMovimiento
from app.db.models.prestamo import Prestamo
from app.db.models.articulo import Articulo
from app.db.models.solicitud import Solicitud

router = APIRouter()

@router.get("/prestamos/{id_prestamo}/movimientos", response_model=KardexPrestamoResponse)
async def obtener_kardex_prestamo(
    id_prestamo: int,
    tipo: Optional[str] = Query(None, description="Filtro por tipo: interes, mora, abono, desembolso, ajuste_ejecucion"),
    fecha_desde: Optional[date] = Query(None, description="Filtro por fecha desde"),
    fecha_hasta: Optional[date] = Query(None, description="Filtro por fecha hasta"),
    limit: int = Query(100, ge=1, le=500, description="Límite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación"),
    sort: str = Query("desc", description="Orden: asc o desc"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Obtener el kardex (historial de movimientos) de un préstamo
    """
    try:
        # Verificar que el préstamo existe
        prestamo_query = select(Prestamo).where(Prestamo.id_prestamo == id_prestamo)
        result_prestamo = await db.execute(prestamo_query)
        prestamo = result_prestamo.scalar_one_or_none()
        
        if not prestamo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Préstamo {id_prestamo} no encontrado"
            )
        
        # VERIFICACIÓN DE PERMISOS
        # Si el usuario es cliente, verificar que es dueño del préstamo
        user_roles = getattr(current_user, 'roles', [])
        is_admin_operator = any(role in ['admin', 'operador', 'cobrador'] for role in user_roles)
        
        if not is_admin_operator:
            # Cliente: verificar que es dueño del préstamo
            # Articulo → Solicitud → Usuario
            query_verificacion = select(Solicitud.id_usuario).select_from(Prestamo).join(
                Articulo, Prestamo.id_articulo == Articulo.id_articulo
            ).join(
                Solicitud, Articulo.id_solicitud == Solicitud.id_solicitud
            ).where(Prestamo.id_prestamo == id_prestamo)
            
            result_verificacion = await db.execute(query_verificacion)
            id_usuario_propietario = result_verificacion.scalar_one_or_none()
            
            if id_usuario_propietario != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tienes permisos para ver los movimientos de este préstamo"
                )
        
        # Construir query base para movimientos
        query = select(PrestamoMovimiento).where(
            PrestamoMovimiento.id_prestamo == id_prestamo
        )
        
        # Aplicar filtros
        if tipo:
            query = query.where(PrestamoMovimiento.tipo == tipo)
        
        if fecha_desde:
            query = query.where(PrestamoMovimiento.fecha >= fecha_desde)
        
        if fecha_hasta:
            query = query.where(PrestamoMovimiento.fecha <= fecha_hasta)
        
        # Aplicar ordenamiento
        if sort == "asc":
            query = query.order_by(PrestamoMovimiento.fecha.asc())
        else:
            query = query.order_by(PrestamoMovimiento.fecha.desc())
        
        # Aplicar paginación
        query = query.offset(offset).limit(limit)
        
        # Ejecutar query para movimientos
        result = await db.execute(query)
        movimientos = result.scalars().all()
        
        # Contar total de movimientos (sin paginación)
        count_query = select(func.count(PrestamoMovimiento.id_mov)).where(
            PrestamoMovimiento.id_prestamo == id_prestamo
        )
        
        if tipo:
            count_query = count_query.where(PrestamoMovimiento.tipo == tipo)
        if fecha_desde:
            count_query = count_query.where(PrestamoMovimiento.fecha >= fecha_desde)
        if fecha_hasta:
            count_query = count_query.where(PrestamoMovimiento.fecha <= fecha_hasta)
        
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()
        
        # Calcular resumen usando CASE statements (corregido)
        resumen_query = select(
            func.sum(
                case((PrestamoMovimiento.tipo == 'interes', PrestamoMovimiento.monto), else_=0)
            ).label('total_intereses'),
            func.sum(
                case((PrestamoMovimiento.tipo == 'mora', PrestamoMovimiento.monto), else_=0)
            ).label('total_mora'),
            func.sum(
                case((PrestamoMovimiento.tipo == 'abono', PrestamoMovimiento.monto), else_=0)
            ).label('total_abonos')
        ).where(PrestamoMovimiento.id_prestamo == id_prestamo)
        
        resumen_result = await db.execute(resumen_query)
        resumen_data = resumen_result.first()
        
        # Usar deuda_actual del préstamo como saldo actual
        saldo_actual = float(prestamo.deuda_actual) if prestamo.deuda_actual else 0.0
        
        # Construir respuesta
        movimientos_response = []
        for mov in movimientos:
            movimientos_response.append(MovimientoResponse(
                id_mov=mov.id_mov,
                tipo=mov.tipo,
                monto=float(mov.monto),
                nota=mov.nota,
                fecha=mov.fecha
            ))
        
        resumen = ResumenMovimientos(
            total_intereses=float(resumen_data.total_intereses or 0),
            total_mora=float(resumen_data.total_mora or 0),
            total_abonos=float(resumen_data.total_abonos or 0),
            saldo_actual=saldo_actual
        )
        
        return KardexPrestamoResponse(
            id_prestamo=id_prestamo,
            movimientos=movimientos_response,
            total=total,
            resumen=resumen
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )