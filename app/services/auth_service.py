# app/services/auth_service.py
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext

from app.db.models.user import User
from app.schemas.auth import UserRegister

# Config de hashing (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    @staticmethod
    async def register_user(data: UserRegister, db: AsyncSession) -> User:
        """Crea un usuario con contraseña (registro normal)."""
        # ¿Existe ya el correo?
        exists = await db.execute(select(User).where(User.Correo == data.email))
        if exists.scalar_one_or_none():
            raise ValueError("El correo ya está en uso")

        hashed_password = pwd_context.hash(data.password)

        new_user = User(
            Nombre=data.username,
            Correo=data.email.lower().strip(),
            Contrasena_hash=hashed_password,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    @staticmethod
    async def authenticate_user(
        email: str, password: str, db: AsyncSession
    ) -> Optional[User]:
        """
        Devuelve el usuario si la contraseña es válida.
        No levanta excepciones por hash inválido/ausente (cuentas creadas por Google).
        """
        result = await db.execute(select(User).where(User.Correo == email.lower().strip()))
        user = result.scalar_one_or_none()
        if not user:
            return None

        # Si la cuenta fue creada por Google puede no tener hash real
        hashed = getattr(user, "Contrasena_hash", None)
        if not hashed:
            return None

        try:
            ok = pwd_context.verify(password, hashed)
        except Exception:
            # Hash malformado/algoritmo distinto → tratar como credenciales inválidas
            return None

        return user if ok else None
