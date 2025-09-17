from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import health, auth, solicitudes
from app.core.config import settings

def parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # Evita '*' cuando allow_credentials=True
    return [o for o in origins if o != "*"]

# Orígenes desde ENV (+ fallback útiles para dev/preview)
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

app.include_router(health.router,      prefix="/health",      tags=["health"])
app.include_router(auth.router,        prefix="/auth",        tags=["auth"])
app.include_router(solicitudes.router, prefix="/solicitudes", tags=["solicitudes"])

@app.get("/")
def root():
    return {"ok": True, "name": "API Pignoraticios"}
