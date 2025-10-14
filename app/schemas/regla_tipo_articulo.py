from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, condecimal, validator

_DECIMAL_12_2 = condecimal(max_digits=12, decimal_places=2)

class ReglaTipoArticuloBase(BaseModel):
    admite_comprar: bool = Field(...)
    admite_recoleccion: bool = Field(...)
    valor_max_domicilio: Optional[_DECIMAL_12_2] = Field(None, ge=0)
    requiere_dos_personas: bool = Field(...)
    requiere_serie: bool = Field(...)
    requiere_prueba: bool = Field(...)
    activo: bool = Field(...)

    @validator("valor_max_domicilio")
    def _non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("valor_max_domicilio no puede ser negativo")
        return v

class ReglaTipoArticuloCreate(ReglaTipoArticuloBase):
    id_tipo: int = Field(..., gt=0)

class ReglaTipoArticuloUpdate(ReglaTipoArticuloBase):
    pass

class ReglaTipoArticuloOut(ReglaTipoArticuloBase):
    id_tipo: int
    tipo_nombre: Optional[str] = None

    class Config:
        from_attributes = True
