from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.db.database import get_db
from app.schemas.configuraciones_generales import (
    ConfiguracionGeneralCreate, 
    ConfiguracionGeneralUpdate, 
    ConfiguracionGeneralResponse
)
from app.crud.configuraciones_generales import (
    get_configuraciones_generales as get_configuraciones,
    get_configuracion_by_id,
    create_configuracion,
    update_configuracion,
    desactivar_configuracion
)
from app.core.security import get_current_user

router = APIRouter(prefix="/configuraciones", tags=["configuraciones"])

@router.get("", response_model=list[ConfiguracionGeneralResponse])
def listar_configuraciones(
    clave: Optional[str] = Query(None, description="Filtrar por clave exacta"),
    vigentes: bool = Query(True, description="Filtrar por configuraciones vigentes"),
    limit: int = Query(50, ge=1, le=200, description="Límite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtener lista de configuraciones con filtros opcionales"""
    return get_configuraciones(db, clave, vigentes, limit, offset)

@router.get("/{id_config}", response_model=ConfiguracionGeneralResponse)
def obtener_configuracion(
    id_config: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtener una configuración específica por ID"""
    config = get_configuracion_by_id(db, id_config)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración no encontrada"
        )
    return config

@router.post("", response_model=ConfiguracionGeneralResponse, status_code=status.HTTP_201_CREATED)
def crear_configuracion(
    config_data: ConfiguracionGeneralCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Crear una nueva configuración (solo ADMIN)"""
    # Verificar rol de administrador
    if current_user.get('rol') != 'ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador"
        )
    
    try:
        return create_configuracion(db, config_data.dict())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.patch("/{id_config}", response_model=ConfiguracionGeneralResponse)
def actualizar_configuracion(
    id_config: int,
    config_data: ConfiguracionGeneralUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Actualizar una configuración existente (solo ADMIN)"""
    if current_user.get('rol') != 'ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador"
        )
    
    updated_config = update_configuracion(db, id_config, config_data.dict(exclude_unset=True))
    if not updated_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración no encontrada"
        )
    return updated_config

@router.delete("/{id_config}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_configuracion_endpoint(
    id_config: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Desactivar una configuración (solo ADMIN)"""
    if current_user.get('rol') != 'ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador"
        )
    
    config = desactivar_configuracion(db, id_config)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración no encontrada o ya está inactiva"
        )
