# app/main.py
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
import logging
import traceback
from app.api.routers import health
from app.api.routers import auth
from app.api.routers import solicitudes
app = FastAPI(title="API Pignoraticios")


from app.core.config import settings
from app.db import models  # Importa todos los modelos para que SQLAlchemy los registre

# Importar routers
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.routers.cloudinary_sign import router as cloudinary_router
from app.api.routers.solicitudes_completa import router as solicitudes_completa_router

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_origins(raw: str | None) -> list[str]:
    """Parsea los orígenes CORS desde la configuración"""
    if not raw:
        return []
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return [o for o in origins if o != "*"]

# Configurar orígenes CORS
origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))

# Orígenes por defecto para desarrollo
fallback_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://frontend-web-rust-nine.vercel.app",
]

for origin in fallback_origins:
    if origin not in origins:
        origins.append(origin)

# Regex para permitir subdominios de Vercel
allow_origin_regex = r"https://.*\.vercel\.app"

# Crear aplicación FastAPI
app = FastAPI(
    title="API Pignoraticios",
    description="API REST para sistema de préstamos pignoraticios",
    version="1.0.0",
    root_path=getattr(settings, "ROOT_PATH", ""),
    docs_url=getattr(settings, "DOCS_URL", "/docs"),
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Middleware para manejo de errores global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Maneja errores globales de la aplicación"""
    logger.error(f"Error no manejado en {request.url}: {str(exc)}")
    logger.error(traceback.format_exc())
    
    # En desarrollo, mostrar el error completo
    if settings.DOCS_URL:  # Asumimos que si docs está habilitado, es desarrollo
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Error interno del servidor",
                "error": str(exc),
                "type": type(exc).__name__
            }
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"}
        )

# Middleware para logging de requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log de todas las requests para debugging"""
    start_time = __import__('time').time()
    
    # Procesar request
    response = await call_next(request)
    
    # Calcular tiempo de procesamiento
    process_time = __import__('time').time() - start_time
    
    # Log de la request
    logger.info(
        f"{request.method} {request.url} - {response.status_code} - {process_time:.4f}s"
    )
    
    return response

# ======================= ROUTERS PRINCIPALES =======================

# Health check (siempre primero)
app.include_router(
    health_router,
    prefix="/health",
    tags=["health"]
)

# Autenticación
app.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"]
)

# Solicitudes básicas
app.include_router(
    solicitudes_router,
    prefix="/solicitudes",
    tags=["solicitudes"]
)

# Solicitudes completas (con artículos y fotos)
app.include_router(
    solicitudes_completa_router,
    tags=["solicitudes-completa"]
)

# Cloudinary (utilidades para imágenes)
app.include_router(
    cloudinary_router,
    tags=["cloudinary"]
)

# ======================= ROUTERS OPCIONALES =======================

# Router de usuarios (gestión de perfiles)
try:
    from app.api.routers.usuarios import router as usuarios_router
    app.include_router(usuarios_router, tags=["usuarios"])
    logger.info("✅ Router de usuarios cargado correctamente")
except ImportError as e:
    logger.warning(f"⚠️  No se pudo cargar el router de usuarios: {e}")
except Exception as e:
    logger.error(f"❌ Error cargando router de usuarios: {e}")

# Router de auditoría (nuevo sistema de auditoría)
try:
    from app.api.routers.auditoria import router as auditoria_router
    app.include_router(auditoria_router, tags=["auditoria"])
    logger.info("✅ Router de auditoría cargado correctamente")
except ImportError as e:
    logger.warning(f"⚠️  No se pudo cargar el router de auditoría: {e}")
except Exception as e:
    logger.error(f"❌ Error cargando router de auditoría: {e}")

# ======================= ROUTERS DE DESARROLLO =======================

# Router de diagnóstico para desarrollo
if settings.DOCS_URL:  # Solo en desarrollo
    diag_router = APIRouter(prefix="/dev", tags=["desarrollo"])
    
    @diag_router.get("/ping")
    def ping():
        """Ping simple para verificar que la API responde"""
        return {"status": "pong", "timestamp": __import__('datetime').datetime.now().isoformat()}
    
    @diag_router.get("/config")
    def get_config():
        """Información de configuración (sin datos sensibles)"""
        return {
            "docs_url": settings.DOCS_URL,
            "cors_origins_count": len(origins),
            "database_configured": bool(settings.DB_URL),
            "jwt_configured": bool(settings.JWT_SECRET),
            "google_oauth_configured": bool(getattr(settings, "GOOGLE_CLIENT_ID", "")),
            "cloudinary_configured": bool(
                getattr(settings, "CLOUDINARY_CLOUD_NAME", "") and
                getattr(settings, "CLOUDINARY_API_KEY", "")
            )
        }
    
    @diag_router.get("/routes")
    def list_routes():
        """Lista todas las rutas disponibles"""
        routes = []
        for route in app.routes:
            if isinstance(route, APIRoute):
                routes.append({
                    "path": route.path,
                    "methods": list(route.methods),
                    "name": route.name,
                    "tags": getattr(route, "tags", [])
                })
        return {"routes": routes, "total": len(routes)}
    
    app.include_router(diag_router)

# Router adicional de Cloudinary para desarrollo
@app.get("/cloudinary/ping-local")
def cloudinary_ping_local():
    """Ping específico para Cloudinary"""
    return {"ok": True, "service": "cloudinary"}

# ======================= ENDPOINTS PRINCIPALES =======================

@app.get("/", tags=["root"])
def read_root():
    """Endpoint raíz con información de la API"""
    return {
        "name": "API Pignoraticios",
        "version": "1.0.0",
        "status": "running",
        "docs": f"{settings.DOCS_URL}" if settings.DOCS_URL else None,
        "endpoints": {
            "health": "/health",
            "auth": "/auth",
            "solicitudes": "/solicitudes",
            "solicitudes_completa": "/solicitudes-completa",
            "auditoria": "/auditoria",
            "usuarios": "/usuarios"
        }
    }

@app.get("/info", tags=["info"])
def api_info():
    """Información detallada de la API"""
    total_routes = len([r for r in app.routes if isinstance(r, APIRoute)])
    
    return {
        "api": {
            "name": "API Pignoraticios",
            "version": "1.0.0",
            "description": "API REST para sistema de préstamos pignoraticios"
        },
        "features": [
            "Autenticación JWT con soporte Google OAuth",
            "Gestión completa de solicitudes con artículos y fotos",
            "Sistema de auditoría avanzado",
            "Gestión de usuarios y perfiles",
            "Integración con Cloudinary para imágenes",
            "Documentación automática con OpenAPI/Swagger"
        ],
        "stats": {
            "total_endpoints": total_routes,
            "cors_origins": len(origins),
            "environment": "development" if settings.DOCS_URL else "production"
        },
        "support": {
            "documentation": f"{settings.DOCS_URL}" if settings.DOCS_URL else "Deshabilitada",
            "health_check": "/health"
        }
    }

# ======================= STARTUP EVENT =======================

@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación"""
    logger.info("🚀 Iniciando API Pignoraticios...")
    logger.info(f"📚 Documentación disponible en: {settings.DOCS_URL}")
    logger.info(f"🌐 CORS configurado para {len(origins)} orígenes")
    logger.info(f"🔗 Total de endpoints: {len([r for r in app.routes if isinstance(r, APIRoute)])}")
    
    # Verificar configuración crítica
    if not settings.DB_URL:
        logger.warning("⚠️  DB_URL no configurada")
    if not settings.JWT_SECRET:
        logger.error("❌ JWT_SECRET no configurada - La autenticación no funcionará")
    
    logger.info("✅ API iniciada correctamente")

@app.on_event("shutdown")
async def shutdown_event():
    """Evento de cierre de la aplicación"""
    logger.info("👋 Cerrando API Pignoraticios...")

# ======================= DEBUG INFO =======================

# Log de rutas registradas para debugging
if __name__ == "__main__":
    print("🔍 RUTAS REGISTRADAS:")
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = ", ".join(route.methods)
            print(f"   {methods:20} {route.path}")
    print(f"\n📊 Total de endpoints: {len([r for r in app.routes if isinstance(r, APIRoute)])}")
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(solicitudes.router)
