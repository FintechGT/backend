from pydantic import BaseModel, Field

class SolicitudCreate(BaseModel):
    metodo_entrega: str = Field(..., description="domicilio | oficina")
    direccion_entrega: str | None = Field(None, max_length=300)

class SolicitudUpdate(BaseModel):
    metodo_entrega: str | None = Field(None, description="domicilio | oficina")
    direccion_entrega: str | None = Field(None, max_length=300)

from pydantic import BaseModel


class SolicitudOut(BaseModel):
    id_solicitud: int
    estado: str
    metodo_entrega: str
    direccion_entrega: str | None

    class Config:
        from_attributes = True
