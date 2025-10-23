from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict

# ===== Módulo =====
class AdminModuloBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=60)
    descripcion: Optional[str] = Field(default=None, max_length=200)
    ruta: Optional[str] = Field(default=None, max_length=120)
    activo: bool = True

class AdminModuloCreate(AdminModuloBase):
    pass

class AdminModuloUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=60)
    descripcion: Optional[str] = Field(default=None, max_length=200)
    ruta: Optional[str] = Field(default=None, max_length=120)
    activo: Optional[bool] = None

class AdminModuloOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_modulo: int
    nombre: str
    descripcion: Optional[str] = None
    ruta: Optional[str] = None
    activo: bool

# ===== Permiso =====
AccionLiteral = Literal[1, 2, 3, 4]  # tu constraint

class AdminPermisoBase(BaseModel):
    id_modulo: int
    id_accion: AccionLiteral
    codigo: str = Field(min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=200)
    activo: bool = True

class AdminPermisoCreate(AdminPermisoBase):
    pass

class AdminPermisoUpdate(BaseModel):
    id_modulo: Optional[int] = None
    id_accion: Optional[AccionLiteral] = None
    codigo: Optional[str] = Field(default=None, min_length=3, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=200)
    activo: Optional[bool] = None

class AdminPermisoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_permiso: int
    id_modulo: int
    id_accion: int
    codigo: str
    descripcion: Optional[str] = None
    activo: bool
    modulo_nombre: Optional[str] = None

# ===== Rol ⇄ Permiso =====
class RolPermisoAssignIn(BaseModel):
    id_permiso: int
    otorgado: bool = True

class RolPermisoOut(BaseModel):
    id_rol: int
    permisos: list[str]
