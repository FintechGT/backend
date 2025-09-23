from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict 

class UserProfileOut(BaseModel):
    id_usuario: int
    nombre: str
    correo: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    verificado: bool
    estado_activo: bool
    created_at: datetime
    updated_at: datetime  

    model_config = ConfigDict(from_attributes=True)

class UserProfilePatch(BaseModel):
    nombre: Optional[str]    = Field(default=None, min_length=1, max_length=120)
    telefono: Optional[str]  = Field(default=None, min_length=3, max_length=30)
    direccion: Optional[str] = Field(default=None, min_length=3, max_length=300)

