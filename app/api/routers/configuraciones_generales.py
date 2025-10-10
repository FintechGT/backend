"""
API de Configuraciones Generales
Permite gestionar parámetros del sistema de forma dinámica (CRUD completo con auditoría)

⚠️ NOTA: La autenticación está temporalmente DESACTIVADA para pruebas.
TODO: Reactivar autenticación antes de producción.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.inspection import inspect

from app.db.database import get_db
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
# from app.db.models.user import User
from app.schemas.configuraciones_generales import (
    ConfiguracionOut,
    ConfiguracionCreate,
    ConfiguracionUpdate,
)
# from app.core.security import get_current_user
# from app.utils.auditoria import registrar_auditoria
# from app.utils.roles import usuario_tiene_algun_rol

router = APIRouter(prefix="/configuraciones", tags=["configuraciones"])


def _cols_dict(obj):
    """Helper para obtener todas las columnas de un objeto ORM como diccionario"""
    m = inspect(obj)
    return {c.key: getattr(obj, c.key) for c in m.mapper.column_attrs}


# ========== 1) GET /configuraciones - Listar todas las configuraciones ==========
@router.get("", summary="Obtener todas las configuraciones como objeto clave-valor")
async def obtener_configuraciones(
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # Temporalmente desactivado
) -> Dict[str, Any]:
    """
    Devuelve todas las configuraciones generales como un diccionario clave-valor.
    Similar al endpoint bootstrap de catálogos.
    """
    result = await db.execute(
        select(ConfiguracionesGenerales).order_by(ConfiguracionesGenerales.clave)
    )
    configs = result.scalars().all()
    
    # Devolver como diccionario clave: valor
    config_dict = {cfg.clave: cfg.valor for cfg in configs}
    
    return config_dict


# ========== 2) GET /configuraciones/{clave} - Obtener configuración específica ==========
@router.get("/{clave}", response_model=ConfiguracionOut, summary="Obtener configuración por clave")
async def obtener_configuracion(
    clave: str,
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # Temporalmente desactivado
):
    """
    Devuelve una configuración específica con todos sus detalles.
    """
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            func.upper(ConfiguracionesGenerales.clave) == clave.upper()
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Configuración '{clave}' no encontrada"
        )
    
    return config


# ========== 3) POST /configuraciones - Crear nueva configuración ==========
@router.post("", response_model=ConfiguracionOut, status_code=status.HTTP_201_CREATED)
async def crear_configuracion(
    payload: ConfiguracionCreate,
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # Temporalmente desactivado
):
    """
    Crea una nueva clave de configuración.
    
    Validaciones:
    - clave debe ser única (sin espacios finales/iniciales, no repetida)
    - valor obligatorio (como string)
    - Fechas de vigencia coherentes si las incluyes
    """
    # Validar permisos (solo ADMIN puede crear configuraciones)
    # TEMPORALMENTE DESACTIVADO PARA PRUEBAS
    # if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN"]):
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Solo administradores pueden crear configuraciones"
    #     )
    
    # Normalizar clave (sin espacios, uppercase para chequeo)
    clave_norm = payload.clave.strip()
    
    # Verificar que no exista
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            func.upper(ConfiguracionesGenerales.clave) == clave_norm.upper()
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una configuración con la clave '{clave_norm}'"
        )
    
    # Validar fechas de vigencia si están presentes
    if payload.vigente_desde and payload.vigente_hasta:
        if payload.vigente_desde >= payload.vigente_hasta:
            raise HTTPException(
                status_code=400,
                detail="vigente_desde debe ser anterior a vigente_hasta"
            )
    
    # Crear configuración
    nueva = ConfiguracionesGenerales(
        clave=clave_norm,
        valor=payload.valor,
        descripcion=payload.descripcion,
        vigente_desde=payload.vigente_desde,
        vigente_hasta=payload.vigente_hasta,
    )
    db.add(nueva)
    await db.flush()
    
    # Auditoría - TEMPORALMENTE DESACTIVADA
    # await registrar_auditoria(
    #     db=db,
    #     usuario_id=current_user.ID_Usuario,
    #     accion="CONFIG_CREATE",
    #     modulo="Configuraciones",
    #     detalle=f"clave={nueva.clave}",
    #     valores_nuevos=nueva,
    # )
    
    await db.commit()
    await db.refresh(nueva)
    
    return nueva


# ========== 4) PUT /configuraciones/{clave} - Actualizar configuración ==========
@router.put("/{clave}", response_model=ConfiguracionOut)
async def actualizar_configuracion(
    clave: str,
    payload: ConfiguracionUpdate,
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # Temporalmente desactivado
):
    """
    Actualiza valor y/o descripción de una configuración existente.
    """
    # Validar permisos - TEMPORALMENTE DESACTIVADO
    # if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN"]):
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Solo administradores pueden actualizar configuraciones"
    #     )
    
    # Buscar configuración
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            func.upper(ConfiguracionesGenerales.clave) == clave.upper()
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Configuración '{clave}' no encontrada"
        )
    
    # Guardar valores anteriores para auditoría
    old_values = _cols_dict(config)
    
    # Aplicar cambios solo si se enviaron
    if payload.valor is not None:
        config.valor = payload.valor
    if payload.descripcion is not None:
        config.descripcion = payload.descripcion
    if payload.vigente_desde is not None:
        config.vigente_desde = payload.vigente_desde
    if payload.vigente_hasta is not None:
        config.vigente_hasta = payload.vigente_hasta
    
    # Validar fechas de vigencia
    if config.vigente_desde and config.vigente_hasta:
        if config.vigente_desde >= config.vigente_hasta:
            raise HTTPException(
                status_code=400,
                detail="vigente_desde debe ser anterior a vigente_hasta"
            )
    
    await db.flush()
    
    # Auditoría - TEMPORALMENTE DESACTIVADA
    # await registrar_auditoria(
    #     db=db,
    #     usuario_id=current_user.ID_Usuario,
    #     accion="CONFIG_UPDATE",
    #     modulo="Configuraciones",
    #     detalle=f"clave={config.clave}",
    #     valores_anteriores=old_values,
    #     valores_nuevos=config,
    # )
    
    await db.commit()
    await db.refresh(config)
    
    return config


# ========== 5) DELETE /configuraciones/{clave} - Eliminar configuración ==========
@router.delete("/{clave}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_configuracion(
    clave: str,
    db: AsyncSession = Depends(get_db),
    # current_user: User = Depends(get_current_user),  # Temporalmente desactivado
):
    """
    Elimina una configuración del sistema.
    """
    # Validar permisos - TEMPORALMENTE DESACTIVADO
    # if not await usuario_tiene_algun_rol(current_user, db, ["ADMIN"]):
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Solo administradores pueden eliminar configuraciones"
    #     )
    
    # Buscar configuración
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            func.upper(ConfiguracionesGenerales.clave) == clave.upper()
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Configuración '{clave}' no encontrada"
        )
    
    # Guardar valores para auditoría
    old_values = _cols_dict(config)
    
    # Eliminar
    await db.delete(config)
    
    # Auditoría - TEMPORALMENTE DESACTIVADA
    # await registrar_auditoria(
    #     db=db,
    #     usuario_id=current_user.ID_Usuario,
    #     accion="CONFIG_DELETE",
    #     modulo="Configuraciones",
    #     detalle=f"clave={clave}",
    #     valores_anteriores=old_values,
    # )
    
    await db.commit()
    
    return None