from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.schemas.auth import UserRegister, UserLogin, UserResponse
from app.services.auth_service import AuthService
from app.core.security import create_access_token
from app.api.deps import get_current_user
from app.db.models.user import User

router = APIRouter()

@router.post("/register", response_model=UserResponse)
async def register_user(data: UserRegister, db: AsyncSession = Depends(get_db)):
    try:
        user = await AuthService.register_user(data, db)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login_user(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await AuthService.authenticate_user(data.email, data.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

  
    access_token = create_access_token({"sub": str(user.ID_Usuario)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
async def read_profile(current_user: User = Depends(get_current_user)):
    return {
        "usuario": current_user.Nombre,
        "email": current_user.Correo
    }
