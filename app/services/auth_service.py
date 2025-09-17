from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.user import User
from app.schemas.auth import UserRegister
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    @staticmethod
    async def register_user(data: UserRegister, db: AsyncSession):
        exists = await db.execute(select(User).where(User.Correo == data.email))
        if exists.scalar_one_or_none():
            raise ValueError("El correo ya está en uso")

        hashed_password = pwd_context.hash(data.password)
        new_user = User(
            Nombre=data.username,
            Correo=data.email,
            Contrasena_hash=hashed_password,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user

    @staticmethod
    async def authenticate_user(email: str, password: str, db: AsyncSession):
        result = await db.execute(select(User).where(User.Correo == email))
        user = result.scalar_one_or_none()
        if not user or not pwd_context.verify(password, user.Contrasena_hash):
            return None
        return user
