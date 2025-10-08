# app/schemas/roles_permisos.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List

class RolPermisoItemIn(BaseModel):
    id_permiso: int
    otorgado: bool = True

class RolPermisoBulkIn(BaseModel):
    items: List[RolPermisoItemIn] = Field(min_length=1)

class IdsPermisosIn(BaseModel):
    items: List[int] = Field(min_length=1)

# Para listar permisos del rol (solo los otorgados)
from app.schemas.permisos import PermisoOut  # reutilizamos tu esquema existente

class PermisosDeRolOut(PermisoOut):
    model_config = ConfigDict(from_attributes=True)
