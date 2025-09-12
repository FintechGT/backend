from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import health, auth, solicitudes
from app.core.config import settings  

app = FastAPI(
    title="API Pignoraticios",
    root_path=getattr(settings, "ROOT_PATH", ""),        
    docs_url=getattr(settings, "DOCS_URL", "/docs"),     
    redoc_url=None
)

# CORS
origins_env = getattr(settings, "CORS_ORIGINS", "*")
allow_origins = ["*"] if origins_env == "*" else [o.strip() for o in origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router,   prefix="/auth",   tags=["auth"])
app.include_router(solicitudes.router, prefix="/solicitudes", tags=["solicitudes"])


@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}
