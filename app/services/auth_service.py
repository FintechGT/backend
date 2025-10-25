# app/services/auth_service.py
from typing import Optional

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.db.models.user import User
from app.schemas.auth import UserRegister
from app.core.security import hash_password, verify_password  # helpers centralizados

logger = logging.getLogger(__name__)
MAX_BCRYPT_WARN = 72  # solo diagnóstico, no bloquea


def _norm(s: str) -> str:
    return (s or "").strip()


class AuthService:
    @staticmethod
    async def register_user(data: UserRegister, db: AsyncSession) -> User:
        """
        Registro normal con contraseña.
        - Normaliza email/username
        - Evita duplicados case-insensitive
        - Hashea con bcrypt_sha256 (definido en core/security.py)
        - Maneja IntegrityError por índice único
        """
        email = _norm(data.email).lower()
        username = _norm(data.username)
        password = data.password or ""

        # Diagnóstico opcional (no bloquea)
        try:
            b = len(password.encode("utf-8"))
            if b > MAX_BCRYPT_WARN:
                logger.warning("[AuthService.register_user] password tiene %d bytes (>72).", b)
        except Exception:
            pass

        # Chequeo previo (no confiamos solo en esto; también manejamos IntegrityError)
        exists = await db.execute(select(User).where(func.lower(User.Correo) == email))
        if exists.scalar_one_or_none():
            # Puedes elegir devolver None y que el router lance HTTP 409
            # Aquí preferimos lanzar y que el router lo convierta si quiere.
            raise ValueError("El correo ya está en uso")

        hashed_password = hash_password(password)  # bcrypt_sha256 forzado en security.py

        new_user = User(
            Nombre=username,
            Correo=email,
            Contrasena_hash=hashed_password,  # <-- asegúrate que el nombre de columna sea este
            Verificado=True,      # ajusta según tu flujo
            Estado_Activo=True,   # alta por defecto
        )

        db.add(new_user)
        try:
            await db.commit()
        except IntegrityError as ie:
            # Concurrencia o duplicado de correo
            await db.rollback()
            logger.info("Registro duplicado detectado para email=%s: %s", email, ie)
            raise ValueError("El correo ya está en uso") from ie

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
        - Respeta Estado_Activo (si existe)
        - Soporta bcrypt y bcrypt_sha256 en verify()
        """
        email_n = _norm(email).lower()

        result = await db.execute(select(User).where(func.lower(User.Correo) == email_n))
        user = result.scalar_one_or_none()
        if not user:
            return None

        if hasattr(user, "Estado_Activo") and user.Estado_Activo is False:
            return None

        stored_hash = getattr(user, "Contrasena_hash", None) or ""
        if not stored_hash:
            # cuentas Google-only o datos incompletos
            return None

        try:
            ok = verify_password(password, stored_hash)  # detecta esquema por el hash
        except Exception as ex:
            logger.warning("Fallo verificando hash para user_id=%s: %s", getattr(user, "ID_Usuario", None), ex)
            return None

        return user if ok else None
