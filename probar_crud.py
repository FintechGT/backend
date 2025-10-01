import asyncio
from app.db.database import get_db
from app.crud.configuraciones_generales import CRUDConfiguracionGeneral
from app.schemas.configuraciones_generales import ConfiguracionGeneralCreate

def probar_crud():
    # Obtener sesión de base de datos
    db = next(get_db())
    
    try:
        # Crear una configuración de prueba
        nueva_config = ConfiguracionGeneralCreate(
            nombre="TASA_INTERES",
            valor="5.5",
            descripcion="Tasa de interés anual"
        )
        
        # Probar creación
        config_creada = configuracion_general.crear(db, nueva_config)
        print(f"✅ Configuración creada: {config_creada.nombre}")
        
        # Probar obtención por ID
        config_obtenida = configuracion_general.obtener_por_id(db, config_creada.id)
        print(f"✅ Configuración obtenida: {config_obtenida.nombre}")
        
        # Probar obtención de todas
        todas = configuracion_general.obtener_todas(db)
        print(f"✅ Total configuraciones: {len(todas)}")
        
        print("🎉 CRUD probado exitosamente!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    probar_crud()