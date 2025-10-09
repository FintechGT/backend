from pydantic import BaseModel, Field, ConfigDict


class CatTipoArticuloBase(BaseModel):
    """Esquema base con campos comunes para un tipo de artículo."""
    nombre: str = Field(..., min_length=3, max_length=100, description="Nombre del tipo de artículo, ej: Joyería")
    descripcion: str | None = Field(None, max_length=255, description="Descripción opcional del tipo de artículo")


class CatTipoArticuloCreate(CatTipoArticuloBase):
    """Esquema para crear un nuevo tipo de artículo."""
    pass


class CatTipoArticuloUpdate(BaseModel):
    """Esquema para actualizar un tipo de artículo. Todos los campos son opcionales."""
    nombre: str | None = Field(None, min_length=3, max_length=100)
    descripcion: str | None = Field(None, max_length=255)


class CatTipoArticuloOut(CatTipoArticuloBase):
    """Esquema para devolver un tipo de artículo desde la API."""
    id_tipo: int

    model_config = ConfigDict(from_attributes=True)