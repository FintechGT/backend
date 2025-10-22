# ============================================================
# app/schemas/contratos_get.py
# ============================================================
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, ConfigDict


class ContratoListItem(BaseModel):
    """Resumen de contrato usado en /contratos/mis"""
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
    """Detalle completo de contrato usado en /contratos/{id_contrato}"""
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
