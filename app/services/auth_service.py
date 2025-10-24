# app/services/auth_service.py
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models.user import User
from app.schemas.auth import UserRegister
from app.core.security import hash_password, verify_password  # usar helpers centralizados

MAX_BCRYPT_WARN = 72  # solo advertencia (no bloquea)


class AuthService:
    @staticmethod
    async def register_user(data: UserRegister, db: AsyncSession) -> User:
        """
        Crea un usuario con contraseña (registro normal).
        - Normaliza email/username
        - Evita duplicados case-insensitive
        - Hashea con bcrypt_sha256 (definido en app/core/security.py)
        """
        email = (data.email or "").strip().lower()
        username = (data.username or "").strip()
        password = data.password or ""

        # (Opcional) Advertencia de diagnóstico si supera 72 bytes (no bloquea)
        try:
            b = len(password.encode("utf-8"))
            if b > MAX_BCRYPT_WARN:
                print(f"[AuthService.register_user] Advertencia: password con {b} bytes (>72).")
        except Exception:
            pass

        # ¿Existe ya el correo? (case-insensitive)
        exists = await db.execute(
            select(User).where(func.lower(User.Correo) == email)
        )
        if exists.scalar_one_or_none():
            raise ValueError("El correo ya está en uso")

        # Hash con política central (bcrypt_sha256 preferido)
        hashed_password = hash_password(password)

        new_user = User(
            Nombre=username,
            Correo=email,
            Contrasena_hash=hashed_password,
            Verificado=True,     # ajusta según tu flujo
            Estado_Activo=True,  # en alta por defecto
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
            # Verificación con política central (soporta bcrypt_sha256 y bcrypt legado)
            ok = verify_password(password, stored_hash)
        except Exception:
            # Hash malformado/algoritmo distinto → tratar como credenciales inválidas
            return None

        return user if ok else None
