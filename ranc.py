#!/usr/bin/env python3
"""
Script para despertar Railway MySQL
"""
import asyncio
import asyncmy
import time

async def wake_railway():
    print("🚂 DESPERTANDO RAILWAY...")
    print("="*30)
    
    max_attempts = 5
    
    for attempt in range(1, max_attempts + 1):
        print(f"🔄 Intento {attempt}/{max_attempts}")
        
        try:
            conn = await asyncmy.connect(
                host="shuttle.proxy.rlwy.net",
                port=30628,
                user="root",
                password="WihJkSWjhKKgiPwIQOqukVIZMwZYAgRw",
                db="railway",
                connect_timeout=60,  # Timeout largo
                charset="utf8mb4"
            )
            
            print("✅ Conexión establecida!")
            
            async with conn.cursor() as cursor:
                # Queries simples para despertar
                await cursor.execute("SELECT 1")
                result = await cursor.fetchone()
                print(f"📋 Test query: {result[0]}")
                
                await cursor.execute("SELECT VERSION()")
                version = await cursor.fetchone()
                print(f"🗄️  MySQL version: {version[0]}")
                
                await cursor.execute("SELECT NOW()")
                now = await cursor.fetchone()
                print(f"🕐 Tiempo servidor: {now[0]}")
                
                # Query para mantener activa
                await cursor.execute("SELECT DATABASE()")
                db = await cursor.fetchone()
                print(f"📊 Base de datos: {db[0]}")
            
            await conn.ensure_closed()
            print("🎉 RAILWAY ESTÁ ACTIVO!")
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Intento {attempt} falló: {error_msg}")
            
            if "timed out" in error_msg.lower():
                print("   ⏱️  Timeout - Railway puede estar iniciando")
            elif "connection refused" in error_msg.lower():
                print("   🚫 Conexión rechazada - Railway reiniciando")
            elif "2003" in error_msg:
                print("   🌐 No se puede conectar al host")
            
            if attempt < max_attempts:
                wait_time = attempt * 10  # 10, 20, 30, 40 segundos
                print(f"   🕐 Esperando {wait_time}s antes del siguiente intento...")
                await asyncio.sleep(wait_time)
    
    print("💥 RAILWAY NO RESPONDE DESPUÉS DE VARIOS INTENTOS")
    print("   💡 Posibles causas:")
    print("   - Railway está en mantenimiento")
    print("   - La base de datos está pausada")
    print("   - Problema con las credenciales")
    return False

async def test_with_optimized_params():
    print("\n🚀 PROBANDO CON PARÁMETROS OPTIMIZADOS...")
    
    try:
        conn = await asyncmy.connect(
            host="shuttle.proxy.rlwy.net",
            port=30628,
            user="root",
            password="WihJkSWjhKKgiPwIQOqukVIZMwZYAgRw",
            db="railway",
            connect_timeout=120,  # 2 minutos
            read_timeout=60,      # 1 minuto  
            write_timeout=60,     # 1 minuto
            charset="utf8mb4",
            autocommit=True
        )
        
        print("✅ Conexión optimizada exitosa!")
        
        async with conn.cursor() as cursor:
            # Test más completo
            await cursor.execute("SHOW TABLES")
            tables = await cursor.fetchall()
            print(f"📋 Tablas encontradas: {len(tables)}")
            
            if len(tables) > 0:
                print("   Tablas:")
                for table in tables[:5]:  # Primeras 5
                    print(f"   - {table[0]}")
        
        await conn.ensure_closed()
        return True
        
    except Exception as e:
        print(f"❌ Parámetros optimizados también fallan: {e}")
        return False

async def main():
    print("🔧 SOLUCIÓN PARA RAILWAY INACTIVO")
    print("="*35)
    
    # 1. Intentar despertar Railway
    railway_active = await wake_railway()
    
    if railway_active:
        # 2. Probar con parámetros optimizados
        optimized_works = await test_with_optimized_params()
        
        if optimized_works:
            print("\n🎯 PRÓXIMOS PASOS:")
            print("1. Instalar pydantic-settings:")
            print("   pip install pydantic-settings")
            print("\n2. Actualizar tu .env con:")
            print("   DB_URL=mysql+asyncmy://root:WihJkSWjhKKgiPwIQOqukVIZMwZYAgRw@shuttle.proxy.rlwy.net:30628/railway?connect_timeout=120&read_timeout=60&write_timeout=60&charset=utf8mb4&autocommit=true")
            print("\n3. Ejecutar tu API:")
            print("   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    else:
        print("\n⚠️  RAILWAY NO ESTÁ DISPONIBLE AHORA")
        print("   🕐 Espera 5-10 minutos y vuelve a intentar")
        print("   🔍 Revisa el dashboard de Railway")

if __name__ == "__main__":
    asyncio.run(main())