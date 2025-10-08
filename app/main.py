from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from app.api.routers.pagos_validar import router as pagos_validar_router
from app.core.config import settings
from app.db import models  # noqa

# Routers base
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.routers.cloudinary_sign import router as cloudinary_router
from app.api.routers.solicitudes_completa import router as solicitudes_completa_router
from app.api.routers.recepciones import router as recepciones_router
from app.api.routers.catalogos import router as catalogos_router  # ← agregado

# Nuevo: Rechazar Artículo
from app.api.routers.articulo_rechazar import router as articulo_rechazar_router

# Nuevo: Valuador (agregado desde feature/api_valuador)
from app.api.routers.articulos_valuador import router as articulos_valuador_router

# Módulo-permiso (nuevos)
from app.api.routers.modulos import router as modulos_router
from app.api.routers.permisos import router as permisos_router
from app.api.routers.roles import router as roles_router
from app.api.routers.roles_permisos import router as roles_permisos_router
from app.api.routers.usuario_roles import router as usuario_roles_router


def parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]

# Lista blanca CORS (SIN allow_origin_regex)
origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))
fallback = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://frontend-web-rust-nine.vercel.app",
]
for o in fallback:
    if o not in origins:
        origins.append(o)

app = FastAPI(
    title="API Pignoraticios",
    root_path=getattr(settings, "ROOT_PATH", ""),
    docs_url=getattr(settings, "DOCS_URL", "/docs"),
    redoc_url=None,
)

# 👉 El middleware SIEMPRE antes de registrar routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(auth_router)
app.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
app.include_router(cloudinary_router)
app.include_router(solicitudes_completa_router)
app.include_router(recepciones_router)
app.include_router(catalogos_router)      # ← registrar catálogos

# Seguridad: módulos/roles/permisos
app.include_router(modulos_router)
app.include_router(permisos_router)
app.include_router(roles_router)
app.include_router(roles_permisos_router)
app.include_router(usuario_roles_router)

# Valuador
app.include_router(articulos_valuador_router)
app.include_router(pagos_validar_router)
# Rechazar Artículo (ruta: PATCH /articulo/rechazar/{id_articulo}/rechazar)
app.include_router(articulo_rechazar_router)

# Usuarios (si existe el router)
try:
    from app.api.routers import usuarios as usuarios_router_module
    app.include_router(usuarios_router_module.router)
except Exception:
    pass

# Diagnóstico simple
_diag = APIRouter()

@_diag.get("/cloudinary/ping-local")
def cloud_ping_local():
    return {"ok": True}

app.include_router(_diag)

@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}

print("RUTAS REGISTRADAS:", [r.path for r in app.routes if isinstance(r, APIRoute)])
