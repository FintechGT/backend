from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from passlib.context import CryptContext  # centraliza el hashing
from app.core.config import settings
from app.db.database import get_db
from app.db.models.user import User


# bcrypt_sha256 por defecto; aún permite verificar bcrypt viejo
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    default="bcrypt_sha256",   # <— importante
    deprecated="auto",
)

def hash_password(password: str) -> str:
    """Genera un hash seguro sin límite de 72 bytes (bcrypt_sha256)."""
    # fuerza el esquema al crear hashes nuevos
    return pwd_context.hash(password, scheme="bcrypt_sha256")

def verify_password(password: str, hashed: str) -> bool:
    """Verifica contra el esquema que indique el hash (bcrypt o bcrypt_sha256)."""
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict, expires_delta: Optional[int] = None) -> str:
    """
    Crea un token JWT con fecha de expiración.
    - data: información a codificar (ej. {"sub": str(user_id)})
    - expires_delta: minutos hasta la expiración (usa settings.ACCESS_TOKEN_EXPIRE_MINUTES por defecto)
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return encoded_jwt


def verify_token(token: str):
    """Decodifica un token JWT y devuelve el payload si es válido, o None si falla."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        return payload
    except JWTError:
        return None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Obtiene el usuario autenticado a partir del token JWT.
    - Si el token es inválido o expiró → lanza HTTP 401.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar el token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception

        try:
            user_id = int(user_id_str)
        except ValueError:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.ID_Usuario == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user
