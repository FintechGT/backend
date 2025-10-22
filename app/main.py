# ============================================================
# app/main.py
# ============================================================
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

# Configuración base
from app.core.config import settings
from app.db import models  # noqa: F401  # asegura el registro de modelos SQLAlchemy

# Routers base
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.catalogos import router as catalogos_router
from app.api.routers.cloudinary_sign import router as cloudinary_router

# Solicitudes y artículos
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.routers.solicitudes_completa import router as solicitudes_completa_router
from app.api.routers import solicitudes_articulos

# Recepción de artículos
from app.api.routers.recepciones import router as recepciones_router

# Pagos
from app.api.routers.crear_pagos import router as crear_pagos_router
from app.api.routers.pagos import router as pagos_list_router
from app.api.routers.pagos_validar import router as pagos_validar_router

# Artículos (valuación, rechazo)
from app.api.routers.articulos_valuador import router as articulos_valuador_router
from app.api.routers.articulo_rechazar import router as articulo_rechazar_router

# Seguridad y control de acceso (ACL)
from app.api.routers.modulos import router as modulos_router
from app.api.routers.permisos import router as permisos_router
from app.api.routers.roles import router as roles_router
from app.api.routers.roles_permisos import router as roles_permisos_router
from app.api.routers.usuario_roles import router as usuario_roles_router
from app.api.routers.usuarios_permisos import router as usuarios_permisos_router

# Préstamos
from app.api.routers.prestamos_recalcular import router as prestamos_recalcular_router
from app.api.routers.prestamos_recalcular_bulk import router as prestamos_recalcular_bulk_router
from app.api.routers.prestamos_evaluar_estado import router as prestamos_evaluar_estado_router
from app.api.routers.procesar_incumplidos import router as procesar_incumplidos_router
from app.api.routers.prestamos_activar import router as prestamos_activar_router
from app.api.routers.prestamos_listado import router as prestamos_listado_router

# RBAC
from app.rbac.attach import attach_rbac_guards

# Inventario y administración
from app.api.routers import inventario_venta
from app.api.routers import acl_admin
from app.api.routers import admin_usuarios

# Contratos (unificado)
from app.api.routers.contratos import router_prestamos, router_contratos

# Auditoría
from app.api.routers.auditoria import router as auditoria_router

# Admin de solicitudes
from app.api.routers.admin_solicitudes import router as admin_solicitudes_router

# Seguridad (opcional)
try:
    from app.api.routers.seguridad import router as seguridad_router
except Exception:
    seguridad_router = None

# Reglas
from app.api.routers.regla_tipo_articulo import router as regla_tipo_articulo_router

# Test opcional
try:
    from app.api.routers.test_regla import router as test_regla_router
except Exception:
    test_regla_router = None

# --------------------------------------------------------------------------------------
# CORS — configuración
# --------------------------------------------------------------------------------------
def parse_origins(raw: str | None) -> list[str]:
    """Convierte una cadena separada por comas en lista de orígenes permitidos."""
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]

origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))

# Fallback comunes para desarrollo / producción
fallback = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://frontend-web-rust-nine.vercel.app",
    "http://10.144.119.56:3000",
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
    redirect_slashes=False,  # evita 307/308 que rompen CORS
)

# Middleware CORS global
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)

# --------------------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------------------

# Salud y auth
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(auth_router)

# Catálogos y configuración
app.include_router(catalogos_router)

# Solicitudes y artículos
app.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
app.include_router(solicitudes_completa_router)
app.include_router(solicitudes_articulos.router)
app.include_router(recepciones_router)
app.include_router(cloudinary_router)

# Pagos
app.include_router(pagos_list_router)
app.include_router(pagos_validar_router)
app.include_router(crear_pagos_router)

# Artículos
app.include_router(articulos_valuador_router)
app.include_router(articulo_rechazar_router)

# Seguridad / ACL
app.include_router(modulos_router)
app.include_router(permisos_router)
app.include_router(roles_router)
app.include_router(roles_permisos_router)
app.include_router(usuario_roles_router)
app.include_router(usuarios_permisos_router)

# Préstamos
app.include_router(prestamos_recalcular_router)
app.include_router(prestamos_recalcular_bulk_router)
app.include_router(prestamos_evaluar_estado_router)
app.include_router(procesar_incumplidos_router)
app.include_router(prestamos_activar_router)
app.include_router(prestamos_listado_router)

# RBAC, Inventario, Administración
attach_rbac_guards(app)
app.include_router(inventario_venta.router)
app.include_router(acl_admin.router)
app.include_router(admin_usuarios.router)

# Contratos
app.include_router(router_prestamos)
app.include_router(router_contratos)

# Auditoría y Admin Solicitudes
app.include_router(auditoria_router)
app.include_router(admin_solicitudes_router)

# Seguridad opcional
if seguridad_router:
    app.include_router(seguridad_router)

# Reglas por tipo de artículo
app.include_router(regla_tipo_articulo_router)

# Test opcional
if test_regla_router:
    app.include_router(test_regla_router)

# --------------------------------------------------------------------------------------
# Diagnóstico local
# --------------------------------------------------------------------------------------
_diag = APIRouter()

@_diag.get("/cloudinary/ping-local")
def cloud_ping_local():
    return {"ok": True}

app.include_router(_diag)

# --------------------------------------------------------------------------------------
# Raíz
# --------------------------------------------------------------------------------------
@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}

# --------------------------------------------------------------------------------------
# Log de rutas (solo en desarrollo)
# --------------------------------------------------------------------------------------
try:
    rutas = [r.path for r in app.routes if isinstance(r, APIRoute)]
    print("RUTAS REGISTRADAS:", rutas)
except Exception:
    pass
