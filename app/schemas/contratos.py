# ============================================================
# app/schemas/contratos.py
# ============================================================
from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, HttpUrl, constr, validator


# -----------------------------
# Bases
# -----------------------------
class ContratoBase(BaseModel):
    id_contrato: int = Field(..., example=123)
    id_prestamo: int = Field(..., example=456)
    url_pdf: HttpUrl = Field(..., example="https://res.cloudinary.com/.../contrato_456.pdf")
    hash_doc: Optional[str] = Field(
        None,
        example="sha256:3e23e8160039594a33894f6564e1b134..."
    )
    firma_cliente_en: Optional[datetime] = Field(None, example="2025-10-22T15:04:05Z")
    firma_empresa_en: Optional[datetime] = Field(None, example="2025-10-22T15:05:11Z")
    created_at: Optional[datetime] = Field(None, example="2025-10-22T15:00:00Z")
    updated_at: Optional[datetime] = Field(None, example="2025-10-22T16:00:00Z")

    class Config:
        orm_mode = True


# -----------------------------
# Listado “mis contratos”
# -----------------------------
class ContratoListItem(ContratoBase):
    """
    Row simple para /contratos/mis
    """
    pass


# -----------------------------
# Detalle
# -----------------------------
class ContratoDetalle(ContratoBase):
    owner_id: Optional[int] = Field(None, example=789)


# -----------------------------
# Listado admin / rol-aware
# -----------------------------
class ContratoListRowAdmin(ContratoBase):
    """
    Row usado en GET /contratos (admin o dueño).
    Incluye metadata del préstamo / artículo; owner_id solo cuando es admin.
    """
    articulo: Optional[str] = Field(None, example="iPhone 12 128GB")
    monto_prestamo: float = Field(0, example=2500.0)
    fecha_inicio: Optional[date] = Field(None, example="2025-10-01")
    fecha_vencimiento: Optional[date] = Field(None, example="2025-12-30")
    owner_id: Optional[int] = Field(None, example=789)


class ContratoListResponse(BaseModel):
    total: int = Field(..., example=120)
    limit: int = Field(..., example=20)
    offset: int = Field(..., example=0)
    es_admin: bool = Field(..., example=True)
    items: List[ContratoListRowAdmin]

    class Config:
        orm_mode = True


# -----------------------------
# Bodies / Responses de acciones
# -----------------------------
# POST /prestamos/{id_prestamo}/generar-contrato
class GenerarContratoBody(BaseModel):
    """
    De momento no exigimos campos (placeholder para futura customización).
    """
    pass


class GenerarContratoResponse(BaseModel):
    id_contrato: int
    id_prestamo: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = Field(None, example="sha256:...")
    estado: Literal["pendiente_firma", "parcial", "completo"] = "pendiente_firma"
    firma_cliente_en: Optional[datetime] = None
    firma_empresa_en: Optional[datetime] = None


# POST /contratos/{id_contrato}/firmar
class FirmarContratoBody(BaseModel):
    firmante: Literal["cliente", "empresa"]
    # dataURL base64 (png) o raw base64; no validamos el prefijo para ser flexibles
    firma_digital: constr(min_length=10)
    ip: Optional[str] = Field(None, example="200.12.34.56")

    @validator("firma_digital")
    def _looks_like_b64(cls, v: str) -> str:
        # Validación liviana para ayudar a debuggear inputs vacíos
        if "," in v:
            # dataURL style: "data:image/png;base64,AAAA..."
            head, b64 = v.split(",", 1)
            if not b64 or len(b64) < 10:
                raise ValueError("firma_digital no contiene datos base64 válidos")
        else:
            if len(v) < 10:
                raise ValueError("firma_digital parece demasiado corta")
        return v


class FirmarContratoResponse(BaseModel):
    id_contrato: int
    firmante: Literal["cliente", "empresa"]
    firma_registrada_en: datetime
    contrato_completado: bool


# POST /contratos/{id_contrato}/firmar-cripto
class FirmarCriptoResponse(BaseModel):
    id_contrato: int
    url_pdf: HttpUrl
    hash_doc: Optional[str] = Field(None, example="sha256:...")
    firmado_cripto: bool = True


# -----------------------------
# __all__ para import explícito
# -----------------------------
__all__ = [
    "ContratoListItem",
    "ContratoDetalle",
    "ContratoListRowAdmin",
    "ContratoListResponse",
    "GenerarContratoBody",
    "GenerarContratoResponse",
    "FirmarContratoBody",
    "FirmarContratoResponse",
    "FirmarCriptoResponse",
]
