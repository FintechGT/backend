# app/schemas/usuarios_roles.py
from pydantic import BaseModel, Field
from typing import List

class RolesIdsIn(BaseModel):
    items: List[int] = Field(min_length=1, description="IDs de roles a procesar")
