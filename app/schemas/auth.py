from pydantic import BaseModel, EmailStr, Field
from pydantic import ConfigDict  # Pydantic v2


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: int = Field(..., alias="ID_Usuario")
    username: str = Field(..., alias="Nombre")
    email: EmailStr = Field(..., alias="Correo")

    # En Pydantic v2 se usa model_config (reemplaza a Config)
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GoogleToken(BaseModel):
    id_token: str
