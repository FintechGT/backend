# app/schemas/acl.py
from pydantic import BaseModel
from typing import Dict, List, Optional


class MisPermisosOut(BaseModel):
    """
    Respuesta de permisos efectivos del usuario.
    - permisos: lista de códigos (normalizados a minúsculas, ordenados)
    - origen: (opcional, solo si debug=true) mapea código → lista de id_rol que lo aportan
    """
    permisos: List[str]
    origen: Optional[Dict[str, List[int]]] = None