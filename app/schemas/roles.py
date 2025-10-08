# app/schemas/roles.py
from pydantic import BaseModel, Field
from pydantic import ConfigDict

class RolBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=50)
    descripcion: str | None = Field(default=None, max_length=200)
    activo: bool = True

class RolCreate(RolBase):
    pass

class RolUpdate(BaseModel):
    # PATCH: todos opcionales
    nombre: str | None = Field(default=None, min_length=2, max_length=50)
    descripcion: str | None = Field(default=None, max_length=200)
    activo: bool | None = None

class RolOut(BaseModel):
    # Pydantic v2: leer desde objetos ORM de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    id_rol: int
    nombre: str
    descripcion: str | None = None
    activo: bool
