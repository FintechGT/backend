# ============================================================
# app/schemas/contratos.py
# ============================================================
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# ------------------------------------------------------------
# Literales y tipos base
# ------------------------------------------------------------
EstadoContrato = Literal["pendiente_firma", "firmado_parcial", "firmado_completo"]
FirmanteLiteral = Literal["cliente", "empresa"]
TemplateLiteral = Literal["estandar", "express", "premium"]


# ------------------------------------------------------------
# Entrada y salida: Generar contrato
# ------------------------------------------------------------
class ContratoGenerarIn(BaseModel):
    """Datos de entrada para generar un contrato."""
    template: TemplateLiteral = Field(default="estandar")
    firmar_automaticamente: bool = Field(
        default=False,
        description="Si True, registra la firma de la empresa automáticamente al generar."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"template": "estandar", "firmar_automaticamente": False}
        }
    )


class ContratoGenerarOut(BaseModel):
    """Datos de salida al generar un contrato."""
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: str
    estado: EstadoContrato
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------
# Entrada: Firma de contrato
# ------------------------------------------------------------
class ContratoFirmarIn(BaseModel):
    """Entrada para registrar la firma digital (cliente o empresa)."""
    firmante: FirmanteLiteral
    firma_digital: str = Field(..., description="Imagen base64 o data URL de la firma.")
    ip: Optional[str] = Field(None, description="Dirección IP del firmante (opcional).")


class ContratoFirmarOut(BaseModel):
    """Respuesta al registrar una firma."""
    id_contrato: int
    firmante: FirmanteLiteral
    firma_registrada_en: datetime
    contrato_completado: bool


# ------------------------------------------------------------
# Resúmenes y detalle
# ------------------------------------------------------------
class ContratoListItem(BaseModel):
    """Resumen de contrato (lista general o /mis)."""
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ContratoDetalle(BaseModel):
    """Detalle completo de un contrato."""
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = None
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None
    owner_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
