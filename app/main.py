# app/main.py
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.core.config import settings
from app.db import models 
from app.api.routers.health import router as health_router
from app.api.routers.auth import router as auth_router
from app.api.routers.solicitudes import router as solicitudes_router
from app.api.routers.cloudinary_sign import router as cloudinary_router
from app.api.routers.solicitudes_completa import router as solicitudes_completa_router
def parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return [o for o in origins if o != "*"]

origins = parse_origins(getattr(settings, "CORS_ORIGINS", ""))

fallback = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://frontend-web-rust-nine.vercel.app",
]
for o in fallback:
    if o not in origins:
        origins.append(o)
allow_origin_regex = r"https://.*\.vercel\.app"
app = FastAPI(
    title="API Pignoraticios",
    root_path=getattr(settings, "ROOT_PATH", ""),
    docs_url=getattr(settings, "DOCS_URL", "/docs"),
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router,      prefix="/health",      tags=["health"])
app.include_router(auth_router,        prefix="/auth",        tags=["auth"])
app.include_router(solicitudes_router, prefix="/solicitudes", tags=["solicitudes"])
app.include_router(cloudinary_router)
app.include_router(solicitudes_completa_router) 
try:
    from app.api.routers import usuarios as usuarios_router_module
    app.include_router(usuarios_router_module.router)
except Exception:
    pass
_diag = APIRouter()
@_diag.get("/cloudinary/ping-local")
def cloud_ping_local():
    return {"ok": True}
app.include_router(_diag)

@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}

print("RUTAS REGISTRADAS:", [r.path for r in app.routes if isinstance(r, APIRoute)])
