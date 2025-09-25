#!/usr/bin/env python3
"""
Diagnóstico simple para Railway sin alterar archivos existentes
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_current_config():
    """Probar con la configuración actual (sin cambios)"""
    print("🔍 PROBANDO CONFIGURACIÓN ACTUAL...")
    
    try:
        # Usar exactamente la misma configuración que tu app
        from app.db.database import engine
        from sqlalchemy import text
        
        print("🔄 Usando tu configuración actual de database.py...")
        
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test"))
            test_val = result.fetchone()[0]
            print(f"✅ Test básico exitoso: {test_val}")
            
            # Info del servidor
            result = await conn.execute(text("SELECT VERSION()"))
            version = result.fetchone()[0]
            print(f"🗄️  MySQL: {version}")
            
            # Base de datos actual
            result = await conn.execute(text("SELECT DATABASE()"))
            db_name = result.fetchone()[0]
            print(f"📊 BD actual: {db_name}")
            
        print("✅ TU CONFIGURACIÓN ACTUAL FUNCIONA!")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error con configuración actual: {error_msg}")
        
        # Diagnóstico específico
        if "2013" in error_msg:
            print("\n💡 PROBLEMA: Conexión perdida durante query")
            print("   ⚡ SOLUCIÓN RÁPIDA: Solo agregar parámetros a DB_URL")
            
        elif "1045" in error_msg:
            print("\n💡 PROBLEMA: Credenciales incorrectas")
            print("   🔑 Verificar usuario/contraseña en Railway")
            
        elif "2003" in error_msg:
            print("\n💡 PROBLEMA: No se puede conectar al host")
            print("   🌐 Verificar host/puerto de Railway")
            
        return False

async def test_optimized_url():
    """Probar con URL optimizada (temporal)"""
    print("\n🚀 PROBANDO URL OPTIMIZADA (TEMPORAL)...")
    
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        # URL optimizada para Railway
        optimized_url = "mysql+asyncmy://root:WihJkSWjhKKgiPwIQOqukVIZMwZYAgRw@shuttle.proxy.rlwy.net:30628/railway?charset=utf8mb4&connect_timeout=60&read_timeout=30&write_timeout=30&pool_recycle=3600&pool_pre_ping=true&autocommit=true"
        
        # Engine temporal solo para prueba
        temp_engine = create_async_engine(optimized_url, pool_pre_ping=True)
        
        async with temp_engine.begin() as conn:
            result = await conn.execute(text("SELECT 'OPTIMIZADA FUNCIONA' as test"))
            test_msg = result.fetchone()[0]
            print(f"✅ {test_msg}")
            
            # Test de timeout
            result = await conn.execute(text("SELECT SLEEP(1), 'timeout_ok'"))
            timeout_test = result.fetchone()[1]
            print(f"✅ Test timeout: {timeout_test}")
            
        await temp_engine.dispose()
        print("✅ URL OPTIMIZADA FUNCIONA!")
        
        print("\n🎯 RECOMENDACIÓN:")
        print("   Actualiza solo la DB_URL en tu .env con los parámetros adicionales")
        
        return True
        
    except Exception as e:
        print(f"❌ URL optimizada también falla: {e}")
        return False

async def railway_status_check():
    """Verificar estado de Railway"""
    print("\n🚂 VERIFICANDO ESTADO DE RAILWAY...")
    
    try:
        import asyncmy
        
        # Conexión directa a Railway
        conn = await asyncmy.connect(
            host="shuttle.proxy.rlwy.net",
            port=30628,
            user="root",
            password="WihJkSWjhKKgiPwIQOqukVIZMwZYAgRw",
            db="railway",
            connect_timeout=30
        )
        
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT CONNECTION_ID(), NOW()")
            conn_id, now = await cursor.fetchone()
            print(f"✅ Railway activo - Conexión ID: {conn_id}, Hora: {now}")
            
            # Verificar variables de sistema
            await cursor.execute("SHOW VARIABLES LIKE 'wait_timeout'")
            timeout_info = await cursor.fetchone()
            print(f"⏱️  Wait timeout: {timeout_info[1]} segundos")
        
        await conn.ensure_closed()
        return True
        
    except Exception as e:
        print(f"❌ Railway no responde: {e}")
        print("   💡 Railway puede estar reiniciando o inactivo")
        return False

def show_solution():
    """Mostrar la solución recomendada"""
    print("\n" + "="*50)
    print("🎯 SOLUCIÓN RECOMENDADA (SIN ALTERAR CÓDIGO)")
    print("="*50)
    
    print("\n1️⃣  ACTUALIZAR SOLO .env:")
    print("   Reemplaza tu DB_URL con esta línea:")
    print("   DB_URL=mysql+asyncmy://root:WihJkSWjhKKgiPwIQOqukVIZMwZYAgRw@shuttle.proxy.rlwy.net:30628/railway?charset=utf8mb4&connect_timeout=60&read_timeout=30&write_timeout=30&pool_recycle=3600&pool_pre_ping=true&autocommit=true")
    
    print("\n2️⃣  REINICIAR API:")
    print("   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    
    print("\n3️⃣  SI AÚN FALLA:")
    print("   - Verificar que Railway esté activo")
    print("   - Revisar dashboard de Railway")
    print("   - Esperar unos minutos y reintentar")
    
    print("\n✅ TU CÓDIGO PERMANECE SIN CAMBIOS")

async def main():
    print("🚂 DIAGNÓSTICO RAILWAY - SIN ALTERAR TU CÓDIGO")
    print("="*50)
    
    # 1. Probar configuración actual
    current_works = await test_current_config()
    
    if current_works:
        print("\n🎉 ¡TU CONFIGURACIÓN ACTUAL YA FUNCIONA!")
        print("   No necesitas cambiar nada")
        return
    
    # 2. Verificar estado de Railway
    railway_ok = await railway_status_check()
    
    if not railway_ok:
        print("\n⚠️  Railway parece estar inactivo o reiniciando")
        print("   Espera unos minutos y vuelve a intentar")
        return
    
    # 3. Probar URL optimizada
    optimized_works = await test_optimized_url()
    
    # 4. Mostrar solución
    show_solution()
    
    print(f"\nRESULTADO: {'✅ Solución encontrada' if optimized_works else '❌ Problema persiste'}")

if __name__ == "__main__":
    asyncio.run(main())