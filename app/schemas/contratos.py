# app/schemas/contratos.py
from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import Optional, Literal
from datetime import datetime

# ===========================================================
# ENTRADA: generar contrato
# ===========================================================
class ContratoGenerarIn(BaseModel):
    """
    Payload para generar/regenerar el contrato en PDF.
    - template: variante del HTML (estandar | express | premium)
    - firmar_automaticamente: si True, registra firma de la empresa en el momento
    """
    template: Literal["estandar", "express", "premium"] = Field(default="estandar")
    firmar_automaticamente: bool = Field(
        default=False,
        description="Si true, registra la firma de la empresa ahora."
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "template": "estandar",
            "firmar_automaticamente": False
        }
    })


# ===========================================================
# SALIDA: generar contrato
# ===========================================================
class ContratoGenerarOut(BaseModel):
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: str
    # estado calculado a partir de las marcas de firma:
    #   - pendiente_firma (ninguna)
    #   - firmado_parcial (una de las dos)
    #   - firmado_completo (ambas)
    estado: Literal["pendiente_firma", "firmado_parcial", "firmado_completo"]
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None


# ===========================================================
# ENTRADA: firmar contrato
# ===========================================================
class ContratoFirmarIn(BaseModel):
    """
    Payload para registrar firma.
    - firmante: "cliente" o "empresa"
    - firma_digital: imagen en base64 (puede venir como data URL: data:image/png;base64,....)
    - ip: IP detectada en el front (opcional; el backend también registra la suya)
    """
    firmante: Literal["cliente", "empresa"]
    firma_digital: str = Field(..., description="Base64 del trazo/firma (PNG/JPEG). Acepta data URL.")
    ip: Optional[str] = Field(None, description="IP del firmante (opcional)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "firmante": "cliente",
            "firma_digital": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
            "ip": "192.168.1.100"
        }
    })


# ===========================================================
# SALIDA: firmar contrato
# ===========================================================
class ContratoFirmarOut(BaseModel):
    id_contrato: int
    firmante: Literal["cliente", "empresa"]
    firma_registrada_en: datetime
    contrato_completado: bool
