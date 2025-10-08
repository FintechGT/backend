from pydantic import BaseModel, Field

class RechazoArticulo(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=255, description="Motivo del rechazo del artículo")

class RespuestaRechazo(BaseModel):
    id_articulo: int
    estado: str
    motivo: str
