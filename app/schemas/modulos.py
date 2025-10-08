from pydantic import BaseModel, Field
from typing import Optional

class ModuloIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60)
    descripcion: Optional[str] = Field(None, max_length=200)
    ruta: Optional[str] = Field(None, max_length=120)
    activo: bool = True

class ModuloUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=60)
    descripcion: Optional[str] = Field(None, max_length=200)
    ruta: Optional[str] = Field(None, max_length=120)
    activo: Optional[bool] = None

class ModuloOut(BaseModel):
    id_modulo: int
    nombre: str
    descripcion: Optional[str]
    ruta: Optional[str]
    activo: bool
    class Config:
        from_attributes = True
