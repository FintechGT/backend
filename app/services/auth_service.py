# app/services/auth_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models.user import User
from app.schemas.auth import UserRegister
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

MAX_BCRYPT_LEN = 72  

class AuthService:
    @staticmethod
    async def register_user(data: UserRegister, db: AsyncSession) -> User:
        email = data.email.strip().lower()
        username = data.username.strip()

        if len(data.password.encode("utf-8")) > MAX_BCRYPT_LEN:
            raise ValueError("La contraseña no puede superar 72 bytes.")

        exists = await db.execute(
            select(User).where(func.lower(User.Correo) == email)
        )
        if exists.scalar_one_or_none():
            raise ValueError("El correo ya está en uso")

        hashed_password = pwd_context.hash(data.password)
        new_user = User(
            Nombre=username,
            Correo=email,
            Contrasena_hash=hashed_password,
            Verificado=True,      
            Estado_Activo=True,    
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    @staticmethod
    async def authenticate_user(email: str, password: str, db: AsyncSession) -> User | None:
        # normalizar
        email = (email or "").strip().lower()

        result = await db.execute(
            select(User).where(func.lower(User.Correo) == email)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None

        stored_hash = getattr(user, "Contrasena_hash", None) or ""
        try:
            ok = pwd_context.verify(password, stored_hash)
        except Exception:
            ok = False

        if not ok:
            return None

        # chequeos opcionales
        if hasattr(user, "Estado_Activo") and user.Estado_Activo is False:
            return None
        return user
