from pydantic import BaseModel, condecimal
from typing import Optional

class ReglaArticuloBase(BaseModel):
    admite_comprar: bool = True
    admite_recoleccion: bool = True
    valor_max_domicilio: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    requiere_dos_personas: bool = False
    requiere_serie: bool = False
    requiere_prueba: bool = False
    activo: bool = True

class ReglaArticuloCreate(ReglaArticuloBase):
    id_tipo: int

class ReglaArticuloUpdate(ReglaArticuloBase):
    pass

class ReglaArticuloResponse(ReglaArticuloBase):
    id_tipo: int
    tipo_nombre: Optional[str] = None
    
    class Config:
        from_attributes = True