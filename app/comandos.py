#!/usr/bin/env python3
"""
Comandos rápidos para gestionar la API de Pignoraticios
Uso: python comandos.py <comando>
"""
import sys
import asyncio
import subprocess
import json
from datetime import datetime

def print_help():
    """Muestra la ayuda de comandos disponibles"""
    print("🛠️  COMANDOS DISPONIBLES PARA API PIGNORATICIOS")
    print("=" * 50)
    
    comandos = [
        ("setup", "Configuración inicial completa (BD + datos)"),
        ("run", "Ejecutar servidor de desarrollo"),
        ("test", "Verificar que la API funcione correctamente"),
        ("reset-db", "⚠️  RESETEAR base de datos (PELIGROSO)"),
        ("create-admin", "Crear usuario administrador"),
        ("routes", "Listar todas las rutas disponibles"),
        ("logs", "Ver logs de la aplicación"),
        ("backup-db", "Hacer backup de la base de datos"),
        ("install", "Instalar dependencias"),
        ("clean", "Limpiar archivos temporales"),
        ("status", "Estado actual de la API"),
        ("help", "Mostrar esta ayuda"),
    ]
    
    for comando, descripcion in comandos:
        print(f"  {comando:15} - {descripcion}")
    
    print("\n📚 EJEMPLOS DE USO:")
    print("  python comandos.py setup     # Configuración inicial")
    print("  python comandos.py run       # Ejecutar servidor")
    print("  python comandos.py test      # Verificar API")

async def setup_completo():
    """Configuración inicial completa"""
    print("🚀 CONFIGURACIÓN INICIAL COMPLETA")
    print("=" * 40)
    
    try:
        # 1. Instalar dependencias
        print("📦 1/4 - Instalando dependencias...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Error instalando dependencias: {result.stderr}")
            return False
        print("✅ Dependencias instaladas")
        
        # 2. Configurar base de datos
        print("🗄️  2/4 - Configurando base de datos...")
        result = subprocess.run([sys.executable, "setup.py"], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Error configurando BD: {result.stderr}")
            return False
        print("✅ Base de datos configurada")
        
        # 3. Verificar configuración
        print("🔍 3/4 - Verificando configuración...")
        result = subprocess.run([sys.executable, "verificar_api.py"], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print("⚠️  Verificación encontró problemas")
        else:
            print("✅ Configuración verificada")
        
        # 4. Mostrar resumen
        print("📋 4/4 - Configuración completada")
        print("\n🎉 ¡LISTO PARA USAR!")
        print("   • Para ejecutar: python comandos.py run")
        print("   • Documentación: http://localhost:8000/docs")
        print("   • Admin: admin@pignoraticios.com / admin123")
        
        return True
        
    except Exception as e:
        print(f"💥 Error durante la configuración: {e}")
        return False

def ejecutar_servidor():
    """Ejecutar el servidor de desarrollo"""
    print("🚀 Ejecutando servidor...")
    try:
        subprocess.run([sys.executable, "run.py"])
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido")
    except Exception as e:
        print(f"💥 Error: {e}")

def verificar_api():
    """Verificar que la API funcione"""
    print("🔍 Verificando API...")
    try:
        result = subprocess.run([sys.executable, "verificar_api.py"], 
                              capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"💥 Error verificando API: {e}")
        return False

async def resetear_base_datos():
    """RESETEAR base de datos - PELIGROSO"""
    print("⚠️  RESETEO DE BASE DE DATOS")
    print("=" * 30)
    print("🚨 ESTO BORRARÁ TODOS LOS DATOS")
    print("🚨 NO HAY VUELTA ATRÁS")
    
    confirmacion = input("\n¿Estás COMPLETAMENTE seguro? Escribe 'RESETEAR': ")
    if confirmacion != "RESETEAR":
        print("❌ Operación cancelada")
        return False
    
    confirmacion2 = input("¿REALMENTE seguro? Escribe 'SI BORRAR TODO': ")
    if confirmacion2 != "SI BORRAR TODO":
        print("❌ Operación cancelada")
        return False
    
    try:
        print("🗄️  Reseteando base de datos...")
        
        # Aquí iría el código de reseteo
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.core.config import settings
        from app.db.database import Base
        
        engine = create_async_engine(settings.DB_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        
        print("✅ Base de datos reseteada")
        print("🔄 Ejecutando configuración inicial...")
        
        # Re-ejecutar setup
        result = subprocess.run([sys.executable, "setup.py"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Configuración inicial completada")
            return True
        else:
            print(f"❌ Error en configuración: {result.stderr}")
            return False
        
    except Exception as e:
        print(f"💥 Error durante el reseteo: {e}")
        return False

async def crear_usuario_admin():
    """Crear usuario administrador adicional"""
    print("👤 CREAR USUARIO ADMINISTRADOR")
    print("=" * 30)
    
    try:
        nombre = input("Nombre completo: ").strip()
        email = input("Email: ").strip()
        password = input("Contraseña: ").strip()
        
        if not all([nombre, email, password]):
            print("❌ Todos los campos son requeridos")
            return False
        
        # Crear usuario
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy import text
        from app.core.config import settings
        from passlib.context import CryptContext
        
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        engine = create_async_engine(settings.DB_URL)
        SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
        
        async with SessionLocal() as session:
            # Verificar si el email ya existe
            result = await session.execute(
                text("SELECT ID_Usuario FROM Usuario WHERE Correo = :email"), 
                {"email": email}
            )
            if result.fetchone():
                print("❌ Este email ya existe")
                return False
            
            # Crear usuario
            hashed_password = pwd_context.hash(password)
            await session.execute(text("""
                INSERT INTO Usuario (Nombre, Correo, Contrasena_hash, Verificado, Estado_Activo)
                VALUES (:nombre, :email, :password, 1, 1)
            """), {"nombre": nombre, "email": email, "password": hashed_password})
            
            # Obtener ID del usuario
            result = await session.execute(
                text("SELECT ID_Usuario FROM Usuario WHERE Correo = :email"), 
                {"email": email}
            )
            user_id = result.fetchone()[0]
            
            # Asignar rol ADMIN
            result = await session.execute(
                text("SELECT ID_Rol FROM Roles WHERE Nombre = 'ADMIN'")
            )
            admin_role_id = result.fetchone()[0]
            
            await session.execute(text("""
                INSERT INTO Usuario_Rol (ID_Usuario, ID_Rol) 
                VALUES (:user_id, :role_id)
            """), {"user_id": user_id, "role_id": admin_role_id})
            
            await session.commit()
        
        await engine.dispose()
        
        print("✅ Usuario administrador creado exitosamente")
        print(f"   📧 Email: {email}")
        print(f"   👤 Nombre: {nombre}")
        
        return True
        
    except Exception as e:
        print(f"💥 Error creando usuario: {e}")
        return False

def listar_rutas():
    """Listar todas las rutas disponibles"""
    print("📋 RUTAS DISPONIBLES")
    print("=" * 20)
    
    try:
        import requests
        response = requests.get("http://localhost:8000/dev/routes", timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            routes_by_tag = {}
            for route in data["routes"]:
                tags = route.get("tags", ["sin-tag"])
                for tag in tags:
                    if tag not in routes_by_tag:
                        routes_by_tag[tag] = []
                    routes_by_tag[tag].append(route)
            
            for tag, routes in routes_by_tag.items():
                print(f"\n🏷️  {tag.upper()}:")
                for route in routes:
                    methods = ", ".join(route["methods"])
                    print(f"   {methods:20} {route['path']}")
            
            print(f"\n📊 Total: {data['total']} endpoints")
        else:
            print("❌ No se pudo conectar a la API")
            print("   Asegúrate de que esté ejecutándose en http://localhost:8000")
    
    except Exception as e:
        print(f"💥 Error: {e}")
        print("   Ejecuta 'python comandos.py run' primero")

def ver_estado():
    """Ver estado actual de la API"""
    print("📊 ESTADO ACTUAL DE LA API")
    print("=" * 25)
    
    try:
        import requests
        
        # Health check
        try:
            response = requests.get("http://localhost:8000/health", timeout=5)
            if response.status_code == 200:
                print("✅ API: Funcionando")
                print("✅ Base de datos: Conectada")
            else:
                print("❌ API: Con problemas")
        except:
            print("❌ API: No responde")
            print("   Ejecuta: python comandos.py run")
        
        # Información general
        try:
            response = requests.get("http://localhost:8000/info", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"📊 Endpoints: {data['stats']['total_endpoints']}")
                print(f"🌐 CORS Origins: {data['stats']['cors_origins']}")
                print(f"🔧 Entorno: {data['stats']['environment']}")
        except:
            pass
        
        # Verificar archivos importantes
        import os
        files_to_check = [
            (".env", "Configuración"),
            ("app/main.py", "Aplicación principal"),
            ("requirements.txt", "Dependencias"),
        ]
        
        print("\n📁 ARCHIVOS:")
        for file_path, description in files_to_check:
            if os.path.exists(file_path):
                print(f"✅ {description}: {file_path}")
            else:
                print(f"❌ {description}: {file_path} (faltante)")
        
    except Exception as e:
        print(f"💥 Error verificando estado: {e}")

def limpiar_archivos():
    """Limpiar archivos temporales"""
    print("🧹 Limpiando archivos temporales...")
    
    import os
    import shutil
    
    patterns_to_clean = [
        "**/__pycache__",
        "**/*.pyc",
        "**/*.pyo",
        ".pytest_cache",
        "*.log"
    ]
    
    cleaned = 0
    
    # Limpiar __pycache__
    for root, dirs, files in os.walk("."):
        for dirname in dirs:
            if dirname == "__pycache__":
                dir_path = os.path.join(root, dirname)
                try:
                    shutil.rmtree(dir_path)
                    cleaned += 1
                    print(f"🗑️  {dir_path}")
                except:
                    pass
    
    # Limpiar archivos .pyc
    for root, dirs, files in os.walk("."):
        for filename in files:
            if filename.endswith(('.pyc', '.pyo')):
                file_path = os.path.join(root, filename)
                try:
                    os.remove(file_path)
                    cleaned += 1
                except:
                    pass
    
    print(f"✅ Limpieza completada - {cleaned} elementos eliminados")

def instalar_dependencias():
    """Instalar o actualizar dependencias"""
    print("📦 Instalando dependencias...")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--upgrade"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Dependencias instaladas correctamente")
            return True
        else:
            print(f"❌ Error: {result.stderr}")
            return False
    
    except Exception as e:
        print(f"💥 Error: {e}")
        return False

async def main():
    """Función principal"""
    if len(sys.argv) < 2:
        print_help()
        return
    
    comando = sys.argv[1].lower()
    
    if comando == "help" or comando == "--help" or comando == "-h":
        print_help()
    
    elif comando == "setup":
        await setup_completo()
    
    elif comando == "run":
        ejecutar_servidor()
    
    elif comando == "test":
        verificar_api()
    
    elif comando == "reset-db":
        await resetear_base_datos()
    
    elif comando == "create-admin":
        await crear_usuario_admin()
    
    elif comando == "routes":
        listar_rutas()
    
    elif comando == "status":
        ver_estado()
    
    elif comando == "clean":
        limpiar_archivos()
    
    elif comando == "install":
        instalar_dependencias()
    
    elif comando == "logs":
        print("📋 Para ver logs, ejecuta la API y revisa la consola")
        print("   O usa: tail -f *.log (si tienes archivos de log)")
    
    elif comando == "backup-db":
        print("💾 Funcionalidad de backup pendiente de implementar")
        print("   Por ahora, usa mysqldump manualmente:")
        print("   mysqldump -u user -p database > backup.sql")
    
    else:
        print(f"❌ Comando '{comando}' no reconocido")
        print("   Usa 'python comandos.py help' para ver comandos disponibles")

if __name__ == "__main__":
    asyncio.run(main())