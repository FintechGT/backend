# app/schemas/contratos.py
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

# -------------------------------------------------------------------
# Literales comunes
# -------------------------------------------------------------------
EstadoContrato = Literal["pendiente_firma", "firmado_parcial", "firmado_completo"]
FirmanteLiteral = Literal["cliente", "empresa"]
TemplateLiteral = Literal["estandar", "express", "premium"]

# -------------------------------------------------------------------
# GENERAR CONTRATO
# -------------------------------------------------------------------
class ContratoGenerarIn(BaseModel):
    """
    Payload para generar/regenerar contrato en PDF.
    """
    template: TemplateLiteral = Field(default="estandar")
    firmar_automaticamente: bool = Field(
        default=False,
        description="Si True, registra la firma de la empresa al generar."
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "template": "estandar",
            "firmar_automaticamente": False
        }
    })

class ContratoGenerarOut(BaseModel):
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: str
    estado: EstadoContrato
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    # opcionales, solo si tu modelo/tabla los tiene:
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# -------------------------------------------------------------------
# FIRMAR CONTRATO
# -------------------------------------------------------------------
class ContratoFirmarIn(BaseModel):
    """
    Registrar firma dibujada (imagen base64, acepta data URL).
    """
    firmante: FirmanteLiteral = Field(..., description="'cliente' o 'empresa'")
    firma_digital: str = Field(..., description="PNG/JPEG base64 (puede ser data URL)")
    ip: Optional[str] = Field(None, description="IP del firmante (opcional)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "firmante": "cliente",
            "firma_digital": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
            "ip": "192.168.1.100"
        }
    })

class ContratoFirmarOut(BaseModel):
    id_contrato: int
    firmante: FirmanteLiteral
    firma_registrada_en: datetime
    contrato_completado: bool

# -------------------------------------------------------------------
# DETALLE DE CONTRATO
# -------------------------------------------------------------------
class ContratoDetalle(BaseModel):
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    owner_id: Optional[int] = Field(
        None, description="ID del dueño del contrato (usuario solicitante)"
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# -------------------------------------------------------------------
# LISTA (Mis contratos)
# -------------------------------------------------------------------
class ContratoListItem(BaseModel):
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ContratoList(BaseModel):
    items: List[ContratoListItem]

# -------------------------------------------------------------------
# LISTA ADMIN
# -------------------------------------------------------------------
class ContratoAdminItem(ContratoListItem):
    owner_id: Optional[int] = None

class ContratoAdminList(BaseModel):
    items: List[ContratoAdminItem]
    total: int
    limit: int
    offset: int
