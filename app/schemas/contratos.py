# ============================================================
# app/schemas/contratos.py
# ============================================================
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

# -------------------------------
# Literales
# -------------------------------
EstadoContrato = Literal["pendiente_firma", "firmado_parcial", "firmado_completo"]
FirmanteLiteral = Literal["cliente", "empresa"]
TemplateLiteral = Literal["estandar", "express", "premium"]

# ============================================================
# INPUTS / OUTPUTS
# ============================================================

class ContratoGenerarIn(BaseModel):
    """Payload de entrada al generar contrato"""
    template: TemplateLiteral = Field(default="estandar")
    firmar_automaticamente: bool = Field(
        default=False,
        description="Si True, registra la firma de la empresa al generar."
    )
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "template": "estandar",
                "firmar_automaticamente": False
            }
        }
    )


class ContratoGenerarOut(BaseModel):
    """Respuesta al generar contrato"""
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: str
    estado: EstadoContrato
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ContratoFirmarIn(BaseModel):
    """Payload de firma digital"""
    firmante: FirmanteLiteral = Field(..., description="'cliente' o 'empresa'")
    firma_digital: str = Field(..., description="PNG/JPEG base64 (puede ser data URL)")
    ip: Optional[str] = Field(None, description="IP del firmante (opcional)")
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "firmante": "cliente",
                "firma_digital": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
                "ip": "192.168.1.100"
            }
        }
    )


class ContratoFirmarOut(BaseModel):
    """Respuesta tras firmar contrato"""
    id_contrato: int
    firmante: FirmanteLiteral
    firma_registrada_en: datetime
    contrato_completado: bool
    model_config = ConfigDict(from_attributes=True)

# ============================================================
# LISTADOS / DETALLES
# ============================================================

class ContratoDetalle(BaseModel):
    """Detalle completo de contrato"""
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    owner_id: Optional[int] = Field(None, description="ID del dueño del contrato (usuario solicitante)")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ContratoListItem(BaseModel):
    """Elemento resumido para listados"""
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ContratoList(BaseModel):
    """Listado de contratos (usuario)"""
    items: List[ContratoListItem]
    model_config = ConfigDict(from_attributes=True)


class ContratoAdminItem(ContratoListItem):
    """Versión extendida con info de dueño"""
    owner_id: Optional[int] = None


class ContratoAdminList(BaseModel):
    """Listado para administración"""
    items: List[ContratoAdminItem]
    total: int
    limit: int
    offset: int
    model_config = ConfigDict(from_attributes=True)
