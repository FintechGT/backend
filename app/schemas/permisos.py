# app/schemas/permisos.py
from pydantic import BaseModel, Field, conint
from pydantic import ConfigDict

class PermisoBase(BaseModel):
    id_modulo: int
    id_accion: conint(ge=1, le=4)
    codigo: str
    descripcion: str | None = None
    activo: bool = True

class PermisoCreate(PermisoBase):
    pass

class PermisoOut(BaseModel):
    # Pydantic v2: habilita lectura desde objetos ORM (SQLAlchemy)
    model_config = ConfigDict(from_attributes=True)

    id_permiso: int
    id_modulo: int
    id_accion: int
    codigo: str
    descripcion: str | None = None
    activo: bool

class PermisoItemIn(BaseModel):
    id_accion: conint(ge=1, le=4)
    codigo: str
    descripcion: str | None = None
    activo: bool = True

class PermisosBulkIn(BaseModel):
    id_modulo: int
    items: list[PermisoItemIn] = Field(min_length=1)
