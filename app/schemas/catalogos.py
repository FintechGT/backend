# app/schemas/catalogos.py
from pydantic import BaseModel
from typing import List, Dict, Any


# Schema para un item individual de catálogo (id + nombre)
class CatalogoItem(BaseModel):
    id: int
    nombre: str

    class Config:
        from_attributes = True


# Schema para la respuesta del bootstrap (todos los catálogos juntos)
class BootstrapResponse(BaseModel):
    metodos_entrega: List[str]
    condiciones_articulo: List[str]
    tipos_articulo: List[CatalogoItem]
    estados: Dict[str, List[CatalogoItem]]