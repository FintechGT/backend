from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserRegister(BaseModel):
    """
    Esquema para el registro de usuarios.
    - Se aumentó la longitud máxima del password (bcrypt_sha256 ya no tiene límite de 72B)
    - Se normalizan las longitudes de username/email acorde al modelo.
    """
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=256) 

class UserLogin(BaseModel):
    """
    Esquema de login normal.
    """
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=256)


class UserResponse(BaseModel):
    """
    Esquema de respuesta para /auth/register y /auth/me
    """
    id: int = Field(..., alias="ID_Usuario")
    username: str = Field(..., alias="Nombre")
    email: EmailStr = Field(..., alias="Correo")

    # ✅ Permite mapear desde ORM (atributos de SQLAlchemy)
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GoogleToken(BaseModel):
    """
    Token OAuth2 de Google (para /auth/google)
    """
    id_token: str
