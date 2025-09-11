from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers import health
from app.api.routers import auth
from app.api.routers import solicitudes
app = FastAPI(title="API Pignoraticios")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(solicitudes.router)
