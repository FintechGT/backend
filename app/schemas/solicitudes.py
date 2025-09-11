from pydantic import BaseModel

class SolicitudOut(BaseModel):
    id_solicitud: int
    estado: str
    metodo_entrega: str
    direccion_entrega: str | None

    class Config:
        from_attributes = True
