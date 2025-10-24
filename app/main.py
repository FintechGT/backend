# ============================================================
# app/main.py  — versión revisada con CORS fix y preflight OPTIONS
# ============================================================

from fastapi import FastAPI, APIRouter, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
import re

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
from app.api.routers.crear_pagos import router as crear_pagos_router  # POST /pagos
from app.api.routers.pagos_listar import router as pagos_listar_router

# Solicitudes + artículos (agregar/obtener fotos y artículos)
from app.api.routers import solicitudes_articulos

# Valuador / pagos
from app.api.routers.articulos_valuador import router as articulos_valuador_router
from app.api.routers.pagos_validar import router as pagos_validar_router
from app.api.routers.pagos import router as pagos_list_router

# Artículos: rechazo
from app.api.routers.articulo_rechazar import router as articulo_rechazar_router
from app.api.routers.prestamo_detalle_completo import router as prestamo_detalle_completo_router

# Seguridad: módulos/roles/permisos
from app.api.routers.modulos import router as modulos_router
from app.api.routers.permisos import router as permisos_router
from app.api.routers.roles import router as roles_router
from app.api.routers.roles_permisos import router as roles_permisos_router
from app.api.routers.usuario_roles import router as usuario_roles_router
from app.api.routers.usuarios_permisos import router as usuarios_permisos_router
from app.api.routers.mis_prestamos_pagos import router as mis_prestamos_pagos_router

# Préstamos (recálculo / estado / listado / activar)
from app.api.routers.prestamos_recalcular import router as prestamos_recalcular_router
from app.api.routers.prestamos_recalcular_bulk import router as prestamos_recalcular_bulk_router
from app.api.routers.prestamos_evaluar_estado import router as prestamos_evaluar_estado_router
from app.api.routers.procesar_incumplidos import router as procesar_incumplidos_router
from app.api.routers.prestamos_activar import router as prestamos_activar_router
from app.api.routers.prestamos_listado import router as prestamos_listado_router

# RBAC y ACL
from app.rbac.attach import attach_rbac_guards
from app.api.routers import inventario_venta, acl_admin, admin_usuarios

# Contratos / Préstamos (UNIFICADO)
from app.api.routers.contratos import router_prestamos, router_contratos

# Admin solicitudes
from app.api.routers.admin_solicitudes import router as admin_solicitudes_router
from app.api.routers.articulos_publicos import router as articulos_publicos_router
# Auditoría
from app.api.routers.auditoria import router as auditoria_router

# Seguridad (opcional)
try:
    from app.api.routers.seguridad import router as seguridad_router
except Exception:
    seguridad_router = None

# Test de reglas (opcional)
try:
    from app.api.routers.test_regla import router as test_regla_router
except Exception:
    test_regla_router = None

# Reglas por Tipo de Artículo
from app.api.routers.regla_tipo_articulo import router as regla_tipo_articulo_router


# ============================================================
# CORS
# ============================================================

def parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    out = []
    for o in re.split(r"[,\s]+", raw.strip()):
        o = o.strip().rstrip("/")
        if o and o not in out:
            out.append(o)
    return out

origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))

# Fallbacks seguros
for o in [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://frontend-web-rust-nine.vercel.app",
]:
    if o not in origins:
        origins.append(o)

app = FastAPI(
    title="API Pignoraticios",
    root_path=getattr(settings, "ROOT_PATH", ""),
    docs_url=getattr(settings, "DOCS_URL", "/docs"),
    redoc_url=None,
)

# Middleware CORS — DEBE IR ANTES DE ROUTERS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,                            # Dominios explícitos
    allow_origin_regex=r"^https://.*\.vercel\.app$",  # Permitir previews de Vercel
    allow_credentials=True,
    allow_methods=["*"],                              # Incluye OPTIONS
    allow_headers=["*"],                              # Authorization, Content-Type, etc.
)

# Catch-all para preflight OPTIONS (previene bloqueos)
@app.options("/{rest_of_path:path}")
async def cors_preflight(rest_of_path: str):
    return Response(status_code=204)


# ============================================================
# Registro de Routers
# ============================================================

app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(auth_router)
app.include_router(catalogos_router)
app.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
app.include_router(solicitudes_completa_router)
app.include_router(solicitudes_articulos.router)
app.include_router(recepciones_router)
app.include_router(cloudinary_router)
app.include_router(prestamo_detalle_completo_router)
app.include_router(pagos_list_router)
app.include_router(pagos_validar_router)
app.include_router(crear_pagos_router)
app.include_router(articulos_valuador_router)
app.include_router(articulo_rechazar_router)
app.include_router(modulos_router)
app.include_router(permisos_router)
app.include_router(roles_router)
app.include_router(roles_permisos_router)
app.include_router(usuario_roles_router)
app.include_router(usuarios_permisos_router)
app.include_router(prestamos_recalcular_router)
app.include_router(prestamos_recalcular_bulk_router)
app.include_router(prestamos_evaluar_estado_router)
app.include_router(procesar_incumplidos_router)
app.include_router(prestamos_activar_router)
app.include_router(prestamos_listado_router)
attach_rbac_guards(app)
app.include_router(inventario_venta.router)
app.include_router(acl_admin.router)
app.include_router(admin_usuarios.router)
app.include_router(router_prestamos)
app.include_router(router_contratos)
app.include_router(mis_prestamos_pagos_router)
app.include_router(auditoria_router)
app.include_router(admin_solicitudes_router)
app.include_router(articulos_publicos_router)
if seguridad_router:
    app.include_router(seguridad_router)
try:
    from app.api.routers import usuarios as usuarios_router_module
    app.include_router(usuarios_router_module.router)
except Exception:
    pass
app.include_router(pagos_listar_router)
app.include_router(regla_tipo_articulo_router)
if test_regla_router:
    app.include_router(test_regla_router)


# ============================================================
# Diagnóstico interno / raíz
# ============================================================

_diag = APIRouter()

@_diag.get("/cloudinary/ping-local")
def cloud_ping_local():
    return {"ok": True}

app.include_router(_diag)

@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}

# Log de rutas (solo para depurar)
try:
    rutas = [r.path for r in app.routes if isinstance(r, APIRoute)]
    print("RUTAS REGISTRADAS:", rutas)
except Exception:
    pass
