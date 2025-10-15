
# Solo modelos Pydantic:
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

class UsuarioOut(BaseModel):
    nombre: str
    correo: str

class EstadoOut(BaseModel):
    id: int
    nombre: str

class SolicitudConDetalleOut(BaseModel):
    id_solicitud: int
    id_usuario: int
    usuario: UsuarioOut
    estado: EstadoOut
    fecha_envio: datetime
    metodo_entrega: str
    direccion_entrega: Optional[str]
    total_articulos: int
    articulos_pendientes: int
    articulos_evaluados: int

class SolicitudListResponse(BaseModel):
    items: List[SolicitudConDetalleOut]
    total: int