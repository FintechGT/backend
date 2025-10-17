# app/schemas/admin_usuarios.py
from typing import List, Optional
from pydantic import BaseModel


# ============================================================
# LISTADO / RESUMEN
# ============================================================
class UsuarioResumenOut(BaseModel):
    id: int
    nombre: str
    correo: str
    estado_activo: bool
    roles: List[str] = []
    ultimo_login: Optional[str] = None
    fecha_alta: str
    actualizado: str


class UsuariosListResponse(BaseModel):
    total: int
    items: List[UsuarioResumenOut]


# ============================================================
# DETALLE DE USUARIO
# ============================================================
class UsuarioDetalleOut(BaseModel):
    id: int
    nombre: str
    correo: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    verificado: bool = False
    estado_activo: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================
# CAMBIO DE ESTADO
# ============================================================
class UsuarioEstadoIn(BaseModel):
    estado_activo: bool


class UsuarioEstadoOut(BaseModel):
    id: int
    estado_activo: bool
    actualizado: str


# ============================================================
# ROLES / ASIGNACIÓN
# ============================================================
class RolItem(BaseModel):
    id_rol: int
    nombre: str


# ============================================================
# AUDITORÍA / ACTIVIDAD
# ============================================================
class AuditoriaItemOut(BaseModel):
    id_auditoria: int
    fecha_hora: str
    modulo: str
    accion: str
    detalle: Optional[str] = None
    old_values: Optional[str] = None
    new_values: Optional[str] = None


class UsuarioMiniOut(BaseModel):
    id: int
    nombre: str
    correo: str
    roles: List[str]


class ActividadItem(BaseModel):
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


# ============================================================
# RESET PASSWORD
# ============================================================
class ResetPasswordIn(BaseModel):
    motivo: Optional[str] = None


class ResetPasswordOut(BaseModel):
    id: int
    reset_ok: bool
    requires_password_change: bool = True
    mensaje: str
