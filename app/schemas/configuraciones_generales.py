# app/schemas/configuraciones_generales.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ConfiguracionOut(BaseModel):
    """Schema para devolver una configuración individual"""
    clave: str
    valor: str
    descripcion: Optional[str] = None
    vigente_desde: Optional[datetime] = None
    vigente_hasta: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConfiguracionCreate(BaseModel):
    """Schema para crear una nueva configuración"""
    clave: str = Field(..., min_length=1, max_length=50)
    valor: str = Field(..., min_length=1, max_length=120)
    descripcion: Optional[str] = Field(None, max_length=120)
    vigente_desde: Optional[datetime] = None
    vigente_hasta: Optional[datetime] = None


class ConfiguracionUpdate(BaseModel):
    """Schema para actualizar una configuración existente"""
    valor: Optional[str] = Field(None, min_length=1, max_length=120)
    descripcion: Optional[str] = Field(None, max_length=120)
    vigente_desde: Optional[datetime] = None
    vigente_hasta: Optional[datetime] = None