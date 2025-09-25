#!/usr/bin/env python3
"""
Script para verificar que la API esté funcionando correctamente
después de los cambios de auditoría
"""
import asyncio
import requests
import json
from datetime import datetime
import sys

API_BASE = "http://localhost:8000"

def print_status(message, status="info"):
    """Imprime mensajes con colores"""
    colors = {
        "info": "\033[94m",     # Azul
        "success": "\033[92m",  # Verde
        "warning": "\033[93m",  # Amarillo
        "error": "\033[91m",    # Rojo
        "reset": "\033[0m"      # Reset
    }
    
    icons = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌"
    }
    
    print(f"{colors[status]}{icons[status]} {message}{colors['reset']}")

def test_endpoint(method, url, data=None, headers=None, description=""):
    """Prueba un endpoint específico"""
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=10)
        else:
            response = requests.request(method, url, json=data, headers=headers, timeout=10)
        
        if response.status_code < 400:
            print_status(f"{method} {url} - {response.status_code} ✓", "success")
            if description:
                print(f"   📝 {description}")
            return True, response
        else:
            print_status(f"{method} {url} - {response.status_code} ✗", "error")
            try:
                error_detail = response.json().get("detail", "Sin detalle")
                print(f"   💬 Error: {error_detail}")
            except:
                print(f"   💬 Error: {response.text[:100]}...")
            return False, response
    except requests.exceptions.RequestException as e:
        print_status(f"{method} {url} - Error de conexión", "error")
        print(f"   💬 {str(e)}")
        return False, None

def main():
    """Función principal de verificación"""
    print("🚀 VERIFICANDO API PIGNORATICIOS")
    print("=" * 50)
    
    success_count = 0
    total_tests = 0
    
    # ==================== TESTS BÁSICOS ====================
    print_status("Probando endpoints básicos...", "info")
    
    tests_basicos = [
        ("GET", f"{API_BASE}/", "Endpoint raíz"),
        ("GET", f"{API_BASE}/info", "Información de la API"),
        ("GET", f"{API_BASE}/health", "Health check con BD"),
    ]
    
    for method, url, desc in tests_basicos:
        total_tests += 1
        success, _ = test_endpoint(method, url, description=desc)
        if success:
            success_count += 1
    
    print()
    
    # ==================== TESTS DE DESARROLLO ====================
    print_status("Probando endpoints de desarrollo...", "info")
    
    tests_dev = [
        ("GET", f"{API_BASE}/dev/ping", "Ping de desarrollo"),
        ("GET", f"{API_BASE}/dev/config", "Configuración de la API"),
        ("GET", f"{API_BASE}/dev/routes", "Lista de rutas disponibles"),
        ("GET", f"{API_BASE}/docs", "Documentación Swagger"),
    ]
    
    for method, url, desc in tests_dev:
        total_tests += 1
        success, _ = test_endpoint(method, url, description=desc)
        if success:
            success_count += 1
    
    print()
    
    # ==================== TESTS DE AUTENTICACIÓN ====================
    print_status("Probando autenticación...", "info")
    
    # Test registro
    total_tests += 1
    test_user = {
        "username": "test_user",
        "email": "test@ejemplo.com",
        "password": "password123"
    }
    
    success, response = test_endpoint(
        "POST", 
        f"{API_BASE}/auth/register", 
        data=test_user,
        description="Registro de usuario de prueba"
    )
    if success:
        success_count += 1
    
    # Test login
    total_tests += 1
    login_data = {
        "email": "test@ejemplo.com",
        "password": "password123"
    }
    
    success, response = test_endpoint(
        "POST", 
        f"{API_BASE}/auth/login", 
        data=login_data,
        description="Login de usuario de prueba"
    )
    
    token = None
    if success and response:
        try:
            token_data = response.json()
            token = token_data.get("access_token")
            if token:
                success_count += 1
                print(f"   🔑 Token obtenido: {token[:20]}...")
        except:
            pass
    
    # Test perfil (requiere token)
    if token:
        total_tests += 1
        headers = {"Authorization": f"Bearer {token}"}
        success, _ = test_endpoint(
            "GET", 
            f"{API_BASE}/auth/me", 
            headers=headers,
            description="Obtener perfil actual"
        )
        if success:
            success_count += 1
    
    print()
    
    # ==================== TESTS DE AUDITORÍA ====================
    print_status("Probando endpoints de auditoría...", "info")
    
    # Primero intentar login como admin
    admin_token = None
    total_tests += 1
    admin_login = {
        "email": "admin@pignoraticios.com",
        "password": "admin123"
    }
    
    success, response = test_endpoint(
        "POST", 
        f"{API_BASE}/auth/login", 
        data=admin_login,
        description="Login como administrador"
    )
    
    if success and response:
        try:
            token_data = response.json()
            admin_token = token_data.get("access_token")
            if admin_token:
                success_count += 1
                print(f"   👑 Token admin obtenido: {admin_token[:20]}...")
        except:
            pass
    
    # Tests de auditoría (requieren token de admin)
    if admin_token:
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        tests_auditoria = [
            ("GET", f"{API_BASE}/auditoria", "Listar auditoría"),
            ("GET", f"{API_BASE}/auditoria/opciones/disponibles", "Opciones disponibles"),
            ("GET", f"{API_BASE}/auditoria/stats/contador", "Contador de registros"),
            ("GET", f"{API_BASE}/auditoria/stats/ultima-actividad", "Última actividad"),
            ("GET", f"{API_BASE}/auditoria/stats/resumen", "Resumen estadístico"),
        ]
        
        for method, url, desc in tests_auditoria:
            total_tests += 1
            success, _ = test_endpoint(method, url, headers=headers, description=desc)
            if success:
                success_count += 1
    else:
        print_status("Sin token de admin - saltando tests de auditoría", "warning")
    
    print()
    
    # ==================== TESTS DE SOLICITUDES ====================
    print_status("Probando endpoints de solicitudes...", "info")
    
    if token:  # Token de usuario normal
        headers = {"Authorization": f"Bearer {token}"}
        
        tests_solicitudes = [
            ("GET", f"{API_BASE}/solicitudes/mis", "Mis solicitudes básicas"),
            ("GET", f"{API_BASE}/solicitudes-completa", "Mis solicitudes completas"),
        ]
        
        for method, url, desc in tests_solicitudes:
            total_tests += 1
            success, _ = test_endpoint(method, url, headers=headers, description=desc)
            if success:
                success_count += 1
        
        # Test crear solicitud básica
        total_tests += 1
        solicitud_data = {
            "metodo_entrega": "oficina",
            "direccion_entrega": None
        }
        
        success, _ = test_endpoint(
            "POST", 
            f"{API_BASE}/solicitudes", 
            data=solicitud_data,
            headers=headers,
            description="Crear solicitud básica"
        )
        if success:
            success_count += 1
    
    print()
    
    # ==================== TESTS DE CLOUDINARY ====================
    print_status("Probando utilidades de Cloudinary...", "info")
    
    tests_cloudinary = [
        ("GET", f"{API_BASE}/cloudinary/ping", "Ping de Cloudinary"),
        ("GET", f"{API_BASE}/cloudinary/debug", "Debug de configuración"),
        ("GET", f"{API_BASE}/cloudinary/ping-local", "Ping local de Cloudinary"),
    ]
    
    for method, url, desc in tests_cloudinary:
        total_tests += 1
        success, _ = test_endpoint(method, url, description=desc)
        if success:
            success_count += 1
    
    print()
    
    # ==================== RESUMEN FINAL ====================
    print("📊 RESUMEN DE VERIFICACIÓN")
    print("=" * 50)
    
    percentage = (success_count / total_tests * 100) if total_tests > 0 else 0
    
    if percentage >= 80:
        print_status(f"Tests exitosos: {success_count}/{total_tests} ({percentage:.1f}%)", "success")
        print_status("¡API funcionando correctamente! 🎉", "success")
    elif percentage >= 60:
        print_status(f"Tests exitosos: {success_count}/{total_tests} ({percentage:.1f}%)", "warning")
        print_status("API funcionando con algunos problemas ⚠️", "warning")
    else:
        print_status(f"Tests exitosos: {success_count}/{total_tests} ({percentage:.1f}%)", "error")
        print_status("API tiene problemas serios ❌", "error")
    
    print("\n📝 RECOMENDACIONES:")
    
    if success_count < total_tests:
        print("   • Revisa los logs del servidor para ver errores específicos")
        print("   • Verifica que la base de datos esté configurada correctamente")
        print("   • Asegúrate de que el archivo .env tenga las variables correctas")
    
    print("   • Accede a la documentación en: http://localhost:8000/docs")
    print("   • Revisa el health check en: http://localhost:8000/health")
    print("   • Para desarrollo usa: http://localhost:8000/dev/routes")
    
    return percentage >= 80

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print_status("\nVerificación cancelada por el usuario", "warning")
        sys.exit(1)
    except Exception as e:
        print_status(f"Error durante la verificación: {str(e)}", "error")
        sys.exit(1)