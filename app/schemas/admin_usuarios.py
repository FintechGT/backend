from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


# =========================
# LISTADO DE USUARIOS
# =========================
class UsuarioResumenOut(BaseModel):
    id: int
    nombre: str
    correo: str
    estado_activo: bool
    roles: List[str] = []
    ultimo_login: Optional[str] = None  # si lo manejas en tu esquema / logs
    fecha_alta: str
    actualizado: str

class UsuariosListResponse(BaseModel):
    total: int
    items: List[UsuarioResumenOut]


# =========================
# PATCH ESTADO
# =========================
class UsuarioEstadoIn(BaseModel):
    estado_activo: bool = Field(..., description="true = activar, false = desactivar")

class UsuarioEstadoOut(BaseModel):
    id: int
    estado_activo: bool
    actualizado: str


# =========================
# ACTIVIDAD / AUDITORÍA
# =========================
class UsuarioMiniOut(BaseModel):
    id: int
    nombre: str
    correo: str
    roles: List[str]

class AuditoriaItemOut(BaseModel):
    id_auditoria: int
    fecha_hora: str
    modulo: str
    accion: str
    detalle: Optional[str] = None
    old_values: Optional[str] = None
    new_values: Optional[str] = None

class ActividadResponse(BaseModel):
    usuario: UsuarioMiniOut
    total: int
    items: List[AuditoriaItemOut]


# =========================
# RESETEAR PASSWORD
# =========================
class ResetPasswordIn(BaseModel):
    motivo: Optional[str] = None

class ResetPasswordOut(BaseModel):
    id: int
    reset_ok: bool
    requires_password_change: bool = True
    mensaje: str = "Se reseteó la contraseña y se invalidaron las sesiones activas."
