from pydantic import BaseModel, validator
from datetime import datetime
from typing import Optional

class ConfiguracionGeneralBase(BaseModel):
    clave: str
    valor: str
    descripcion: Optional[str] = None
    vigente_desde: Optional[datetime] = None

class ConfiguracionGeneralCreate(ConfiguracionGeneralBase):
    pass

class ConfiguracionGeneralUpdate(BaseModel):
    valor: Optional[str] = None
    descripcion: Optional[str] = None
    vigente_desde: Optional[datetime] = None
    vigente_hasta: Optional[datetime] = None

    @validator('vigente_hasta')
    def validate_fechas(cls, v, values):
        if v and 'vigente_desde' in values and values['vigente_desde']:
            if values['vigente_desde'] >= v:
                raise ValueError('vigente_desde debe ser anterior a vigente_hasta')
        return v

class ConfiguracionGeneralResponse(ConfiguracionGeneralBase):
    id_config: int
    vigente_hasta: Optional[datetime] = None

    class Config:
        from_attributes = True
