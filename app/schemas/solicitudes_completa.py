from pydantic import BaseModel, HttpUrl, conint, condecimal, field_validator
from typing import List, Optional

class FotoIn(BaseModel):
    url: HttpUrl
    orden: conint(ge=1)

class ArticuloIn(BaseModel):
    id_tipo: conint(ge=1)
    descripcion: str
    valor_estimado: condecimal(ge=0, max_digits=12, decimal_places=2)
    condicion: Optional[str] = None
    fotos: List[FotoIn] = []

class SolicitudCompletaIn(BaseModel):
    metodo_entrega: str
    direccion_entrega: Optional[str] = None
    articulos: List[ArticuloIn]

    @field_validator("articulos")
    @classmethod
    def _min_1_articulo(cls, v):
        if not v:
            raise ValueError("Debe enviar al menos 1 artículo.")
        return v

class FotoOut(BaseModel):
    id_foto: int
    url: str
    orden: int

class ArticuloOut(BaseModel):
    id_articulo: int
    id_tipo: int
    descripcion: str
    valor_estimado: float
    condicion: Optional[str] = None
    fotos: List[FotoOut] = []

class SolicitudCompletaOut(BaseModel):
    id_solicitud: int
    estado: str
    metodo_entrega: str
    direccion_entrega: Optional[str] = None
    articulos: List[ArticuloOut]
