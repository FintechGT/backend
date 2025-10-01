from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.models.configuraciones_generales import ConfiguracionGeneral
from app.schemas.configuraciones_generales import ConfiguracionGeneralCreate, ConfiguracionGeneralUpdate
from typing import List, Optional

class CRUDConfiguracionGeneral:
    
    # Crear una nueva configuración
    def crear(self, db: Session, configuracion: ConfiguracionGeneralCreate) -> ConfiguracionGeneral:
        db_configuracion = ConfiguracionGeneral(
            nombre=configuracion.nombre,
            valor=configuracion.valor,
            descripcion=configuracion.descripcion
        )
        db.add(db_configuracion)
        db.commit()
        db.refresh(db_configuracion)
        return db_configuracion
    
    # Obtener configuración por ID
    def obtener_por_id(self, db: Session, id: int) -> Optional[ConfiguracionGeneral]:
        return db.query(ConfiguracionGeneral).filter(ConfiguracionGeneral.id == id).first()
    
    # Obtener configuración por nombre
    def obtener_por_nombre(self, db: Session, nombre: str) -> Optional[ConfiguracionGeneral]:
        return db.query(ConfiguracionGeneral).filter(ConfiguracionGeneral.nombre == nombre).first()
    
    # Obtener todas las configuraciones
    def obtener_todas(self, db: Session, skip: int = 0, limit: int = 100) -> List[ConfiguracionGeneral]:
        return db.query(ConfiguracionGeneral).offset(skip).limit(limit).all()
    
    # Actualizar configuración
    def actualizar(self, db: Session, id: int, configuracion: ConfiguracionGeneralUpdate) -> Optional[ConfiguracionGeneral]:
        db_configuracion = self.obtener_por_id(db, id)
        if db_configuracion:
            update_data = configuracion.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_configuracion, field, value)
            db.commit()
            db.refresh(db_configuracion)
        return db_configuracion
    
    # Eliminar configuración
    def eliminar(self, db: Session, id: int) -> bool:
        db_configuracion = self.obtener_por_id(db, id)
        if db_configuracion:
            db.delete(db_configuracion)
            db.commit()
            return True
        return False

# Instancia del CRUD para importar
configuracion_general = CRUDConfiguracionGeneral()

# ... después de tu clase CRUDConfiguracionGeneral

# Funciones de conveniencia para compatibilidad con el router
def get_configuraciones_generales(
    db: Session, 
    clave: Optional[str] = None, 
    vigentes: bool = True, 
    limit: int = 50, 
    offset: int = 0
):
    """Obtener configuraciones con filtros"""
    query = db.query(ConfiguracionGeneral)
    
    if clave:
        query = query.filter(ConfiguracionGeneral.nombre == clave)
    
    #if vigentes:
     #   query = query.filter(ConfiguracionGeneral.activo == True)
    
    return query.offset(offset).limit(limit).all()

def get_configuracion_by_id(db: Session, id_config: int):
    """Obtener configuración por ID"""
    return configuracion_general.obtener_por_id(db, id_config)

def create_configuracion(db: Session, config_data: dict):
    """Crear nueva configuración"""
    # Convertir dict a schema
    from app.schemas.configuraciones_generales import ConfiguracionGeneralCreate
    config_schema = ConfiguracionGeneralCreate(**config_data)
    return configuracion_general.crear(db, config_schema)

def update_configuracion(db: Session, id_config: int, config_data: dict):
    """Actualizar configuración existente"""
    # Convertir dict a schema
    from app.schemas.configuraciones_generales import ConfiguracionGeneralUpdate
    config_schema = ConfiguracionGeneralUpdate(**config_data)
    return configuracion_general.actualizar(db, id_config, config_schema)

def desactivar_configuracion(db: Session, id_config: int):
    """Desactivar configuración (marcar como inactiva)"""
    db_config = configuracion_general.obtener_por_id(db, id_config)
    if db_config:
        db_config.activo = False
        db.commit()
        db.refresh(db_config)
        return db_config
    return None