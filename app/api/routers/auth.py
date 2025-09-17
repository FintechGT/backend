from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.schemas.auth import UserRegister, UserLogin, UserResponse, GoogleToken
from app.services.auth_service import AuthService
from app.core.security import create_access_token
from app.api.deps import get_current_user
from app.db.models.user import User
from app.core.config import settings

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

import secrets
from passlib.context import CryptContext

from app.utils.email_validators import is_disposable_domain, has_mx_records

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register_user(data: UserRegister, db: AsyncSession = Depends(get_db)):
    if getattr(settings, "AUTH_GOOGLE_ONLY", False):
        raise HTTPException(status_code=400, detail="El registro es solo con Google")

    email = data.email.strip().lower()
    domain = email.split("@")[-1] if "@" in email else ""

    if getattr(settings, "ALLOWED_EMAIL_DOMAIN", ""):
        allowed = settings.ALLOWED_EMAIL_DOMAIN.lower()
        if not (email.endswith(f"@{allowed}") or (allowed == "gmail.com" and email.endswith("@googlemail.com"))):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Solo correos @{allowed}")

    if is_disposable_domain(domain):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se permiten correos temporales/desechables")

    if not has_mx_records(domain):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dominio de correo inválido (sin registros MX)")

    try:
        user = await AuthService.register_user(data, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
async def login_user(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await AuthService.authenticate_user(data.email, data.password, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    access_token = create_access_token({"sub": str(user.ID_Usuario)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/google")
async def login_with_google(payload: GoogleToken, db: AsyncSession = Depends(get_db)):
    try:
        info = google_id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de Google inválido")

    if info.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Issuer inválido")

    if not bool(info.get("email_verified")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email no verificado por Google")

    email = str(info.get("email", "")).lower()
    nombre = (info.get("name") or info.get("given_name") or email.split("@")[0])[:30]

    if getattr(settings, "ALLOWED_EMAIL_DOMAIN", ""):
        allowed = settings.ALLOWED_EMAIL_DOMAIN.lower()
        if not (email.endswith(f"@{allowed}") or (allowed == "gmail.com" and email.endswith("@googlemail.com"))):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Solo correos @{allowed}")

    result = await db.execute(select(User).where(User.Correo == email))
    user = result.scalar_one_or_none()
    if user is None:
        dummy = pwd_context.hash(secrets.token_urlsafe(16))
        user = User(
            Nombre=nombre,
            Correo=email,
            Contrasena_hash=dummy,
            Verificado=True,
            Estado_Activo=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access_token = create_access_token({"sub": str(user.ID_Usuario)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_profile(current_user: User = Depends(get_current_user)):
    return {"usuario": current_user.Nombre, "email": current_user.Correo}
