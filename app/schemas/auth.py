from pydantic import BaseModel, EmailStr, Field


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

    class Config:
        from_attributes = True
        populate_by_name = True
