from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func

from app.db.database import get_db
from app.db.models.auditoria import Auditoria
from app.db.models.user import User
from app.api.deps import get_current_user
from app.schemas.auditoria import (
    AuditoriaOut, AuditoriaSimple, AuditoriaDetallada,
    AuditoriaRespuesta, AuditoriaAccionesDisponibles
)
from app.utils.roles import usuario_tiene_algun_rol

router = APIRouter(prefix="/auditoria", tags=["auditoria"])

@router.get("", response_model=List[AuditoriaOut])
async def listar_auditoria(
    usuario_id: Optional[int] = Query(None, description="ID del usuario que realizó la acción"),
    accion: Optional[str] = Query(None, description="Tipo de acción realizada"),
    modulo: Optional[str] = Query(None, description="Módulo del sistema"),
    fecha_desde: Optional[date] = Query(None, description="Fecha inicial (YYYY-MM-DD)"),
    fecha_hasta: Optional[date] = Query(None, description="Fecha final (YYYY-MM-DD)"),
    buscar: Optional[str] = Query(None, description="Buscar en detalle, acción o módulo"),
    limite: int = Query(50, ge=1, le=500, description="Cantidad máxima de registros"),
    offset: int = Query(0, ge=0, description="Registros a omitir"),
    orden_por: str = Query("fecha_desc", description="Campo de ordenamiento"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los registros de auditoría con filtros opcionales"""
    
    # Verificar permisos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR", "AUDITOR"]):
        raise HTTPException(status_code=403, detail="Sin permisos para consultar auditoría")

    # Construir la consulta base
    query = select(Auditoria)
    conditions = []
    
    if usuario_id:
        conditions.append(Auditoria.id_usuario == usuario_id)
    if accion:
        conditions.append(Auditoria.accion.ilike(f"%{accion}%"))
    if modulo:
        conditions.append(Auditoria.modulo.ilike(f"%{modulo}%"))
    if fecha_desde:
        conditions.append(Auditoria.fecha_hora >= fecha_desde)
    if fecha_hasta:
        fecha_hasta_end = datetime.combine(fecha_hasta, datetime.max.time())
        conditions.append(Auditoria.fecha_hora <= fecha_hasta_end)
    if buscar:
        buscar_pattern = f"%{buscar}%"
        conditions.append(
            or_(
                Auditoria.detalle.ilike(buscar_pattern),
                Auditoria.accion.ilike(buscar_pattern),
                Auditoria.modulo.ilike(buscar_pattern)
            )
        )
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Ordenamiento
    if orden_por == "fecha_desc":
        query = query.order_by(desc(Auditoria.fecha_hora))
    elif orden_por == "fecha_asc":
        query = query.order_by(asc(Auditoria.fecha_hora))
    else:
        query = query.order_by(desc(Auditoria.fecha_hora))
    
    # Paginación
    query = query.offset(offset).limit(limite)
    
    # Ejecutar consulta
    result = await db.execute(query)
    registros = result.scalars().all()
    
    return [
        AuditoriaOut(
            id_auditoria=r.id_auditoria,
            id_usuario=r.id_usuario,
            accion=r.accion,
            modulo=r.modulo,
            fecha_hora=r.fecha_hora,
            detalle=r.detalle,
            old_values=r.old_values,
            new_values=r.new_values
        )
        for r in registros
    ]


@router.get("/{id_auditoria}", response_model=AuditoriaOut)
async def obtener_auditoria_detalle(
    id_auditoria: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene un registro específico de auditoría por su ID"""
    
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR", "AUDITOR"]):
        raise HTTPException(status_code=403, detail="Sin permisos para consultar auditoría")

    result = await db.execute(
        select(Auditoria).where(Auditoria.id_auditoria == id_auditoria)
    )
    registro = result.scalar_one_or_none()
    
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de auditoría no encontrado")

    return AuditoriaOut(
        id_auditoria=registro.id_auditoria,
        id_usuario=registro.id_usuario,
        accion=registro.accion,
        modulo=registro.modulo,
        fecha_hora=registro.fecha_hora,
        detalle=registro.detalle,
        old_values=registro.old_values,
        new_values=registro.new_values
    )


@router.get("/opciones/disponibles", response_model=AuditoriaAccionesDisponibles)
async def obtener_opciones_disponibles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obtiene las acciones y módulos disponibles para filtrar"""
    
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN", "OPERADOR", "AUDITOR"]):
        raise HTTPException(status_code=403, detail="Sin permisos para consultar auditoría")

    # Obtener acciones únicas
    acciones_result = await db.execute(
        select(Auditoria.accion).distinct().order_by(Auditoria.accion)
    )
    acciones = [row[0] for row in acciones_result.fetchall()]

    # Obtener módulos únicos
    modulos_result = await db.execute(
        select(Auditoria.modulo).distinct().order_by(Auditoria.modulo)
    )
    modulos = [row[0] for row in modulos_result.fetchall()]

    return AuditoriaAccionesDisponibles(
        acciones=acciones,
        modulos=modulos,
        total_acciones=len(acciones),
        total_modulos=len(modulos)
    )