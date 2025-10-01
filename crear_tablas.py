import asyncio
from app.db.database import Base, engine
from app.db.models.configuraciones_generales import ConfiguracionGeneral

async def crear_tablas():
    print('Creando tablas...')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('✅ Tablas creadas exitosamente')

if __name__ == "__main__":
    asyncio.run(crear_tablas())