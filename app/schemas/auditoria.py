from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict
from datetime import datetime

class UsuarioMini(BaseModel):
    id: Optional[int] = None
    nombre: Optional[str] = None

class AuditoriaItem(BaseModel):
    id_auditoria: int
    usuario: Optional[UsuarioMini] = None
    modulo: str
    accion: str
    fecha_hora: datetime
    detalle: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None

class AuditoriaListOut(BaseModel):
    items: List[AuditoriaItem]
    total: int
    limit: int
    offset: int
    sort: str = Field(default="-fecha_hora")

    class Config:
        from_attributes = True
