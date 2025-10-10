# app/main.py
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

# Configuración y modelos base
from app.core.config import settings
from app.db import models  # noqa: F401  # asegura el registro de modelos para SQLAlchemy

# Routers base / negocio
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.routers.cloudinary_sign import router as cloudinary_router
from app.api.routers.solicitudes_completa import router as solicitudes_completa_router
from app.api.routers.recepciones import router as recepciones_router
from app.api.routers.catalogos import router as catalogos_router

# Solicitudes + artículos (agregar/obtener fotos y artículos)
from app.api.routers import solicitudes_articulos  # módulo que expone .router

# Valuador / pagos
from app.api.routers.articulos_valuador import router as articulos_valuador_router
from app.api.routers.pagos_validar import router as pagos_validar_router
from app.api.routers.pagos import router as pagos_list_router

# Artículos: rechazo
from app.api.routers.articulo_rechazar import router as articulo_rechazar_router

# Seguridad: módulos/roles/permisos
from app.api.routers.modulos import router as modulos_router
from app.api.routers.permisos import router as permisos_router
from app.api.routers.roles import router as roles_router
from app.api.routers.roles_permisos import router as roles_permisos_router
from app.api.routers.usuario_roles import router as usuario_roles_router

# Préstamos (recálculo)
from app.api.routers.prestamos_recalcular import router as prestamos_recalcular_router
from app.api.routers.prestamos_recalcular_bulk import router as prestamos_recalcular_bulk_router

# --------------------------------------------------------------------------------------
# Utilidad interna: parseo de orígenes CORS
# --------------------------------------------------------------------------------------
def parse_origins(raw: str | None) -> list[str]:
    """Convierte una cadena separada por comas en lista de orígenes permitidos."""
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]

# --------------------------------------------------------------------------------------
# CORS: lista blanca explícita (sin allow_origin_regex)
# --------------------------------------------------------------------------------------
origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))

# Orígenes de respaldo usados en desarrollo y despliegue
fallback = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://frontend-web-rust-nine.vercel.app",
]
for o in fallback:
    if o not in origins:
        origins.append(o)

# --------------------------------------------------------------------------------------
# Instancia de aplicación
# --------------------------------------------------------------------------------------
app = FastAPI(
    title="API Pignoraticios",
    root_path=getattr(settings, "ROOT_PATH", ""),
    docs_url=getattr(settings, "DOCS_URL", "/docs"),
    redoc_url=None,
)

# El middleware CORS debe ir antes de incluir cualquier router
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------------------
# Registro de routers (agrupados por dominio funcional)
# --------------------------------------------------------------------------------------

# Salud y autenticación
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(auth_router)

# Catálogos / configuración
app.include_router(catalogos_router)

# Flujo de solicitudes y artículos
app.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
app.include_router(solicitudes_completa_router)
app.include_router(solicitudes_articulos.router)
app.include_router(recepciones_router)
app.include_router(cloudinary_router)

# Pagos
app.include_router(pagos_list_router)      # GET  /prestamos/{id_prestamo}/pagos
app.include_router(pagos_validar_router)   # POST /pagos/{id_pago}/validar

# Artículos (valuación y rechazo)
app.include_router(articulos_valuador_router)
app.include_router(articulo_rechazar_router)

# Seguridad y control de acceso
app.include_router(modulos_router)
app.include_router(permisos_router)
app.include_router(roles_router)
app.include_router(roles_permisos_router)
app.include_router(usuario_roles_router)

# Préstamos (recálculo)
app.include_router(prestamos_recalcular_router)      # individual
app.include_router(prestamos_recalcular_bulk_router) # bulk

# Usuarios (si existe el router)
try:
    from app.api.routers import usuarios as usuarios_router_module
    app.include_router(usuarios_router_module.router)
except Exception:
    pass  # ignora si no existe

# --------------------------------------------------------------------------------------
# Utilidades de diagnóstico
# --------------------------------------------------------------------------------------
_diag = APIRouter()

@_diag.get("/cloudinary/ping-local")
def cloud_ping_local():
    return {"ok": True}

app.include_router(_diag)

# --------------------------------------------------------------------------------------
# Raíz de la API
# --------------------------------------------------------------------------------------
@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}

# --------------------------------------------------------------------------------------
# Log de rutas registradas (útil en desarrollo)
# --------------------------------------------------------------------------------------
print("RUTAS REGISTRADAS:", [r.path for r in app.routes if isinstance(r, APIRoute)])
