# app/main.py
from __future__ import annotations

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

# ------------------------------------------------------------------
# Config / modelos base
# ------------------------------------------------------------------
from app.core.config import settings
from app.db import models  # noqa: F401  (asegura registro de modelos)

# ---------------- Routers núcleo ----------------
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router

# Solicitudes & artículos
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.routers.solicitudes_completa import router as solicitudes_completa_router
from app.api.routers import solicitudes_articulos  # expone .router
from app.api.routers.recepciones import router as recepciones_router
from app.api.routers.cloudinary_sign import router as cloudinary_router

# Catálogos
from app.api.routers.catalogos import router as catalogos_router

# Pagos / préstamos
from app.api.routers.crear_pagos import router as crear_pagos_router
from app.api.routers.pagos_validar import router as pagos_validar_router
from app.api.routers.pagos import router as pagos_list_router

# Valuación / Artículos
from app.api.routers.articulos_valuador import router as articulos_valuador_router
from app.api.routers.articulo_rechazar import router as articulo_rechazar_router

# Seguridad / RBAC (mod/perm/roles/usuarios/ACL)
from app.api.routers.modulos import router as modulos_router
from app.api.routers.permisos import router as permisos_router
from app.api.routers.roles import router as roles_router
from app.api.routers.roles_permisos import router as roles_permisos_router
from app.api.routers.usuario_roles import router as usuario_roles_router
from app.api.routers.usuarios_permisos import router as usuarios_permisos_router
from app.rbac.attach import attach_rbac_guards

# Préstamos (procesos/listado)
from app.api.routers.prestamos_recalcular import router as prestamos_recalcular_router
from app.api.routers.prestamos_recalcular_bulk import router as prestamos_recalcular_bulk_router
from app.api.routers.prestamos_evaluar_estado import router as prestamos_evaluar_estado_router
from app.api.routers.procesar_incumplidos import router as procesar_incumplidos_router
from app.api.routers.prestamos_activar import router as prestamos_activar_router
from app.api.routers.prestamos_listado import router as prestamos_listado_router

# Inventario y administración
from app.api.routers import inventario_venta
from app.api.routers import acl_admin
from app.api.routers import admin_usuarios

# Contratos
from app.api.routers.contratos import router_prestamos, router_contratos
from app.api.routers.contratos_get import router as router_contratos_get

# Auditoría / Admin solicitudes
from app.api.routers.auditoria import router as auditoria_router
from app.api.routers.admin_solicitudes import router as admin_solicitudes_router

# (opcionales)
try:
    from app.api.routers.seguridad import router as seguridad_router
except Exception:
    seguridad_router = None

try:
    from app.api.routers.test_regla import router as test_regla_router
except Exception:
    test_regla_router = None


# ------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------
def parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]

origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))

# fallback para dev y vercel
fallback = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://frontend-web-rust-nine.vercel.app",
    "http://10.144.119.56:3000",
]
for o in fallback:
    if o not in origins:
        origins.append(o)

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(
    title="API Pignoraticios",
    root_path=getattr(settings, "ROOT_PATH", ""),
    docs_url=getattr(settings, "DOCS_URL", "/docs"),
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Guards / ACL primero (para que envuelvan rutas)
# ------------------------------------------------------------------
attach_rbac_guards(app)

# ------------------------------------------------------------------
# Include routers
# ------------------------------------------------------------------
# Salud / auth
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(auth_router)

# Catálogos
app.include_router(catalogos_router)

# Solicitudes & artículos
app.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
app.include_router(solicitudes_completa_router)
app.include_router(solicitudes_articulos.router)
app.include_router(recepciones_router)
app.include_router(cloudinary_router)

# Pagos
app.include_router(pagos_list_router)          # GET  /prestamos/{id_prestamo}/pagos
app.include_router(pagos_validar_router)       # POST /pagos/{id_pago}/validar
app.include_router(crear_pagos_router)         # POST /pagos

# Valuación / artículos
app.include_router(articulos_valuador_router)
app.include_router(articulo_rechazar_router)

# Seguridad (modelo de datos de permisos/roles)
app.include_router(modulos_router)
app.include_router(permisos_router)
app.include_router(roles_router)
app.include_router(roles_permisos_router)
app.include_router(usuario_roles_router)
app.include_router(usuarios_permisos_router)

# Préstamos (procesos/listas)
app.include_router(prestamos_recalcular_router)
app.include_router(prestamos_recalcular_bulk_router)
app.include_router(prestamos_evaluar_estado_router)
app.include_router(procesar_incumplidos_router)
app.include_router(prestamos_activar_router)
app.include_router(prestamos_listado_router)

# Inventario / administración
app.include_router(inventario_venta.router)
app.include_router(acl_admin.router)
app.include_router(admin_usuarios.router)

# Contratos
app.include_router(router_prestamos)     # /prestamos/{id}/generar-contrato
app.include_router(router_contratos)     # /contratos (POST firmar, GET list, etc.)
app.include_router(router_contratos_get) # /contratos (GET mis / detalle con schemas)

# Auditoría / admin solicitudes
app.include_router(auditoria_router)
app.include_router(admin_solicitudes_router)

# Seguridad (environments donde exista)
if seguridad_router:
    app.include_router(seguridad_router)

# Usuarios (NO silenciar errores; loguea si falla)
try:
    from app.api.routers.usuarios import router as usuarios_router
    app.include_router(usuarios_router)
    print("[ROUTER] /usuarios registrado")
except Exception as e:
    print("[ROUTER] /usuarios NO registrado:", repr(e))
    # opcional: descomenta para detectar en deploy
    # raise

# Reglas (opcional)
if test_regla_router:
    app.include_router(test_regla_router)

# ------------------------------------------------------------------
# Diagnóstico / root
# ------------------------------------------------------------------
_diag = APIRouter()

@_diag.get("/cloudinary/ping-local")
def cloud_ping_local():
    return {"ok": True}

app.include_router(_diag)

@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}

# Log de rutas al arrancar
try:
    rutas = [f"{r.methods} {r.path}" for r in app.routes if isinstance(r, APIRoute)]
    print("RUTAS REGISTRADAS: ", len(rutas))
    for rp in sorted(rutas):
        print(" -", rp)
except Exception:
    pass
