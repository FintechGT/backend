from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from passlib.context import CryptContext

from app.db.models.user import User
from app.schemas.auth import UserRegister

# Config de hashing (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_BCRYPT_LEN = 72  # límite real de bcrypt en bytes


class AuthService:
    @staticmethod
    async def register_user(data: UserRegister, db: AsyncSession) -> User:
        """
        Crea un usuario con contraseña (registro normal).
        - Normaliza email/username
        - Valida longitud máxima soportada por bcrypt (72 bytes)
        - Evita duplicados case-insensitive
        """
        email = (data.email or "").strip().lower()
        username = (data.username or "").strip()

        if len(data.password.encode("utf-8")) > MAX_BCRYPT_LEN:
            raise ValueError("La contraseña no puede superar 72 bytes.")

        # ¿Existe ya el correo? (case-insensitive)
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
            Verificado=True,    # puedes poner False si prefieres verificación por correo
            Estado_Activo=True, # en alta por defecto
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
        - Normaliza email
        - Busca case-insensitive
        - Soporta cuentas creadas por Google (sin hash) devolviendo None
        - Respeta Estado_Activo si existe en el modelo
        """
        email = (email or "").strip().lower()

        result = await db.execute(
            select(User).where(func.lower(User.Correo) == email)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None

        # Si hay flag de estado y está inactiva, no permitir login
        if hasattr(user, "Estado_Activo") and user.Estado_Activo is False:
            return None

        # Cuentas creadas por Google podrían no tener hash "real"
        stored_hash = getattr(user, "Contrasena_hash", None) or ""
        if not stored_hash:
            return None

        try:
            ok = pwd_context.verify(password, stored_hash)
        except Exception:
            # Hash malformado/algoritmo distinto → tratar como credenciales inválidas
            return None

        return user if ok else None
