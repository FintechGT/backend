# app/schemas/admin_solicitudes.py
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, HttpUrl


# ============================================================
# LISTAR SOLICITUDES (Admin)
# ============================================================
class ArticuloResumenAdmin(BaseModel):
    """Resumen de artículo dentro de una solicitud"""
    id_articulo: int
    descripcion: str
    valor_estimado: float
    valor_aprobado: Optional[float] = None
    estado: str
    condicion: Optional[str] = None
    fotos_count: int = 0


class SolicitudListItemAdmin(BaseModel):
    """Item de solicitud en el listado administrativo"""
    id_solicitud: int
    id_usuario: int
    usuario_nombre: str
    usuario_correo: str
    estado: str
    fecha_envio: str
    metodo_entrega: str
    direccion_entrega: Optional[str] = None
    total_articulos: int
    articulos_aprobados: int
    articulos_rechazados: int
    articulos_pendientes: int


class SolicitudesListResponse(BaseModel):
    """Respuesta paginada de solicitudes"""
    items: List[SolicitudListItemAdmin]
    total: int
    limit: int
    offset: int


# ============================================================
# DETALLE SOLICITUD (Admin)
# ============================================================
class ArticuloFotoAdmin(BaseModel):
    """Foto de un artículo"""
    id_foto: int
    url: str
    orden: int


class ArticuloDetalleAdmin(BaseModel):
    """Detalle completo de artículo para admin"""
    id_articulo: int
    id_tipo: int
    tipo_nombre: Optional[str] = None
    descripcion: str
    valor_estimado: float
    valor_aprobado: Optional[float] = None
    condicion: Optional[str] = None
    estado: str
    fotos: List[ArticuloFotoAdmin] = []
    # Info de préstamo si existe
    tiene_prestamo: bool = False
    prestamo_id: Optional[int] = None
    prestamo_estado: Optional[str] = None


class ClienteInfoAdmin(BaseModel):
    """Información del cliente en detalle de solicitud"""
    id_usuario: int
    nombre: str
    correo: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None


class SolicitudDetalleAdmin(BaseModel):
    """Detalle completo de una solicitud para admin"""
    id_solicitud: int
    estado: str
    fecha_envio: str
    metodo_entrega: str
    direccion_entrega: Optional[str] = None
    cliente: ClienteInfoAdmin
    articulos: List[ArticuloDetalleAdmin]
    resumen: Dict[str, int]  # {"total": N, "aprobados": X, "rechazados": Y, "pendientes": Z}


# ============================================================
# EVALUAR ARTÍCULO (Aprobar/Rechazar)
# ============================================================
class EvaluarArticuloIn(BaseModel):
    """
    Payload para evaluar un artículo.
    Si accion='aprobar' → valor_aprobado es obligatorio
    Si accion='rechazar' → motivo_rechazo es obligatorio
    """
    accion: str = Field(..., description="aprobar | rechazar")
    valor_aprobado: Optional[Decimal] = Field(None, ge=0, description="Valor aprobado (solo si accion=aprobar)")
    plazo_dias: Optional[int] = Field(30, ge=1, le=365, description="Plazo del préstamo en días")
    motivo_rechazo: Optional[str] = Field(None, max_length=500, description="Motivo de rechazo (solo si accion=rechazar)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "accion": "aprobar",
                    "valor_aprobado": 1200.0,
                    "plazo_dias": 30
                },
                {
                    "accion": "rechazar",
                    "motivo_rechazo": "Artículo en mal estado, batería inflada"
                }
            ]
        }
    }


class PrestamoCreadoInfo(BaseModel):
    """Info del préstamo creado al aprobar"""
    id_prestamo: int
    estado: str
    fecha_inicio: date
    fecha_vencimiento: date
    monto_prestamo: float


class EvaluarArticuloOut(BaseModel):
    """Respuesta de evaluación de artículo"""
    id_articulo: int
    accion: str  # aprobado | rechazado
    estado_articulo: str
    valor_aprobado: Optional[float] = None
    motivo_rechazo: Optional[str] = None
    prestamo: Optional[PrestamoCreadoInfo] = None


# ============================================================
# CAMBIAR ESTADO DE SOLICITUD
# ============================================================
class CambiarEstadoSolicitudIn(BaseModel):
    """Payload para cambiar estado de una solicitud manualmente"""
    nuevo_estado: str = Field(
        ..., 
        description="pendiente | en_revision | evaluada | rechazada"
    )
    motivo: Optional[str] = Field(None, max_length=500, description="Motivo del cambio de estado")

    model_config = {
        "json_schema_extra": {
            "example": {
                "nuevo_estado": "evaluada",
                "motivo": "Todos los artículos fueron evaluados"
            }
        }
    }


class CambiarEstadoSolicitudOut(BaseModel):
    """Respuesta al cambiar estado de solicitud"""
    id_solicitud: int
    estado_anterior: str
    estado_nuevo: str
    actualizado_en: str


# ============================================================
# ESTADÍSTICAS RÁPIDAS (Dashboard Admin)
# ============================================================
class EstadisticasSolicitudesOut(BaseModel):
    """Estadísticas generales para dashboard administrativo"""
    total_solicitudes: int
    por_estado: Dict[str, int]  # {"pendiente": 5, "evaluada": 10, ...}
    solicitudes_hoy: int
    solicitudes_semana: int
    articulos_pendientes_evaluacion: int