# ============================================================
# app/api/routers/contratos.py
# ============================================================
from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import io
import os
import re
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user
from app.db.models.contrato import Contrato
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.user import User
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol

import cloudinary
import cloudinary.uploader

# ============================================================
# CLOUDINARY
# ============================================================
cloudinary.config(cloud_name=None)  # lee CLOUDINARY_URL del entorno

# ============================================================
# PDF BACKEND (WeasyPrint -> ReportLab)
# ============================================================
_PDF_BACKEND = None

try:
    from weasyprint import HTML  # A) preferido

    def _pdf_bytes_from_html(html_str: str) -> bytes:
        pdf_io = io.BytesIO()
        HTML(string=html_str, base_url=".").write_pdf(target=pdf_io)
        return pdf_io.getvalue()

    _PDF_BACKEND = "weasyprint"
except Exception:
    pass

if _PDF_BACKEND is None:
    # C) Fallback mínimo: ReportLab (sin HTML/CSS real)
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import cm

    def _pdf_bytes_from_html(html_str: str) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=LETTER)
        w, h = LETTER
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, h - 2 * cm, "Contrato (Fallback ReportLab)")
        c.setFont("Helvetica", 10)
        text = re.sub(r"<[^>]+>", "", html_str)
        y = h - 3 * cm
        for line in text.splitlines()[:70]:
            c.drawString(2 * cm, y, line[:110])
            y -= 12
            if y < 2 * cm:
                c.showPage()
                y = h - 2 * cm
        c.showPage()
        c.save()
        return buf.getvalue()

    _PDF_BACKEND = "reportlab"

# ============================================================
# Firma criptográfica (pyHanko) - opcional
# Requiere:
# - CERT_PFX_B64: certificado .p12/.pfx en base64
# - CERT_PFX_PASSWORD: contraseña del .p12
# ============================================================
_USE_PYHANKO = False
try:
    from pyhanko.sign import signers
    from pyhanko_certvalidator import ValidationContext
    _USE_PYHANKO = True
except Exception:
    _USE_PYHANKO = False


def _resolve_user_id(u: User) -> int:
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _ensure_id_usuario_attr(u: User) -> None:
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))


router_prestamos = APIRouter(prefix="/prestamos", tags=["Contratos"])
router_contratos = APIRouter(prefix="/contratos", tags=["Contratos"])


# ============================================================
# 1) Generar contrato PDF
# ============================================================
@router_prestamos.post(
    "/{id_prestamo}/generar-contrato",
    status_code=status.HTTP_201_CREATED,
    summary="Generar PDF del contrato y guardarlo en la tabla Contrato",
)
async def generar_contrato(
    id_prestamo: int,
    body: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Roles permitidos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "VALUADOR"]):
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden generar contratos")

    # Prestamo
    res = await db.execute(select(Prestamo).where(Prestamo.id_prestamo == id_prestamo))
    prestamo = res.scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    # Estado válido
    res = await db.execute(select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado))
    estado = res.scalar_one_or_none()
    if not estado or estado.nombre.lower() not in {"aprobado_pendiente_entrega", "activo"}:
        raise HTTPException(status_code=400, detail=f"Estado no válido para contrato (actual: {getattr(estado,'nombre', 'N/A')})")

    # No duplicar
    res = await db.execute(select(Contrato).where(Contrato.id_prestamo == id_prestamo))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un contrato para este préstamo")

    # Artículo
    res = await db.execute(select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo))
    articulo = res.scalar_one_or_none()

    html = f"""
    <html>
      <head>
        <meta charset="utf-8">
        <title>Contrato #{id_prestamo}</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 2cm; }}
          h1 {{ text-align:center; color:#333; }}
          table {{ width:100%; border-collapse:collapse; margin-top:1em; }}
          td, th {{ border:1px solid #888; padding:6px; }}
          th {{ background:#eee; }}
          .foot {{ margin-top: 10px; color:#666; font-size: 11px; }}
        </style>
      </head>
      <body>
        <h1>Contrato de Préstamo #{id_prestamo}</h1>
        <p>Este contrato se celebra entre la empresa y el cliente registrado en el sistema Pignoraticios.</p>
        <table>
          <tr><th>Artículo</th><td>{getattr(articulo, "descripcion", "N/A")}</td></tr>
          <tr><th>Monto del préstamo</th><td>Q {float(prestamo.monto_prestamo):,.2f}</td></tr>
          <tr><th>Fecha de inicio</th><td>{prestamo.fecha_inicio}</td></tr>
          <tr><th>Fecha de vencimiento</th><td>{prestamo.fecha_vencimiento}</td></tr>
        </table>
        <p class="foot">Generado con backend: {_PDF_BACKEND}</p>
      </body>
    </html>
    """

    try:
        pdf_bytes = _pdf_bytes_from_html(html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el PDF: {e}")

    hash_doc = hashlib.sha256(pdf_bytes).hexdigest()

    # Subir a Cloudinary
    upload_result = cloudinary.uploader.upload(
        io.BytesIO(pdf_bytes),
        folder="contratos",
        public_id=f"contrato_{id_prestamo}",
        resource_type="raw",
        overwrite=True,
        format="pdf",
    )
    url_pdf = upload_result.get("secure_url")

    contrato = Contrato(
        id_prestamo=id_prestamo,
        url_pdf=url_pdf,
        hash_doc=hash_doc,
        firma_cliente_en=None,
        firma_empresa_en=None,
    )
    db.add(contrato)
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="GENERAR_CONTRATO",
        modulo="Contrato",
        detalle=f"Contrato generado para préstamo {id_prestamo}",
        valores_nuevos={"pdf_backend": _PDF_BACKEND, "url_pdf": url_pdf, "hash_doc": hash_doc},
    )

    await db.commit()
    await db.refresh(contrato)

    return {
        "id_contrato": contrato.id_contrato,
        "id_prestamo": id_prestamo,
        "url_pdf": url_pdf,
        "hash_doc": f"sha256:{hash_doc}",
        "estado": "pendiente_firma",
        "firma_cliente_en": contrato.firma_cliente_en,
        "firma_empresa_en": contrato.firma_empresa_en,
    }


# ============================================================
# 2) Registrar firma "dibujada" (imagen base64)
# ============================================================
@router_contratos.post(
    "/{id_contrato}/firmar",
    summary="Registrar firma digital (cliente o empresa) con imagen base64",
    status_code=status.HTTP_200_OK,
)
async def firmar_contrato(
    id_contrato: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    firmante = body.get("firmante")
    firma_digital = body.get("firma_digital")
    ip = body.get("ip", "0.0.0.0")

    if firmante not in {"cliente", "empresa"}:
        raise HTTPException(status_code=400, detail="firmante debe ser 'cliente' o 'empresa'")
    if not firma_digital:
        raise HTTPException(status_code=400, detail="Debe incluir la firma digital (base64)")

    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    res = await db.execute(select(Contrato).where(Contrato.id_contrato == id_contrato))
    contrato = res.scalar_one_or_none()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    # Subir imagen de firma
    upload = cloudinary.uploader.upload(
        firma_digital,
        folder="contratos/firmas",
        public_id=f"firma_{id_contrato}_{firmante}",
        overwrite=True,
        format="png",
        resource_type="image",
        context={
            "id_contrato": str(id_contrato),
            "firmante": firmante,
            "ip": ip,
            "pdf_hash": contrato.hash_doc,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    firma_url = upload.get("secure_url")

    ts_now = datetime.now(timezone.utc)
    if firmante == "cliente":
        contrato.firma_cliente_en = ts_now
    else:
        contrato.firma_empresa_en = ts_now

    await db.flush()

    contrato_completado = bool(contrato.firma_cliente_en and contrato.firma_empresa_en)

    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="FIRMAR_CONTRATO",
        modulo="Contrato",
        detalle=f"Firma {firmante} registrada",
        valores_nuevos={
            "id_contrato": id_contrato,
            "firmante": firmante,
            "firma_img_url": firma_url,
            "pdf_hash": contrato.hash_doc,
            "ip": ip,
            "pdf_backend": _PDF_BACKEND,
            "contrato_completado": contrato_completado,
        },
    )

    await db.commit()
    await db.refresh(contrato)

    return {
        "id_contrato": contrato.id_contrato,
        "firmante": firmante,
        "firma_registrada_en": ts_now.isoformat(),
        "contrato_completado": contrato_completado,
    }


# ============================================================
# 3) (Opcional) Firma CRIPTOGRÁFICA X.509 del PDF (pyHanko)
#    Requiere CERT_PFX_B64 y CERT_PFX_PASSWORD en el entorno.
#    Sobrescribe contrato.url_pdf con la versión firmada.
# ============================================================
@router_contratos.post(
    "/{id_contrato}/firmar-cripto",
    summary="Firmar criptográficamente el PDF del contrato con un certificado .p12/.pfx",
    status_code=status.HTTP_200_OK,
)
async def firmar_cripto(
    id_contrato: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _USE_PYHANKO:
        raise HTTPException(status_code=500, detail="pyHanko no disponible. Verifica dependencias.")

    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Busca contrato
    res = await db.execute(select(Contrato).where(Contrato.id_contrato == id_contrato))
    contrato = res.scalar_one_or_none()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    if not contrato.url_pdf:
        raise HTTPException(status_code=400, detail="Contrato no tiene PDF para firmar")

    # Descarga PDF
    r = requests.get(contrato.url_pdf, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="No se pudo descargar el PDF original")
    original_pdf = io.BytesIO(r.content)

    # Carga certificado
    pfx_b64 = os.getenv("CERT_PFX_B64")
    pfx_pwd = os.getenv("CERT_PFX_PASSWORD", "")
    if not pfx_b64:
        raise HTTPException(status_code=500, detail="Falta CERT_PFX_B64 en variables de entorno")

    pfx_bytes = base64.b64decode(pfx_b64)
    signer = signers.SimpleSigner.load_pkcs12(pfx_bytes, pfx_pwd.encode("utf-8"))

    # Firma (firma básica, sin TSA)
    vc = ValidationContext(allow_fetching=True)
    pdf_signer = signers.PdfSigner(
        signers.PdfSignatureMetadata(field_name="Signature1"),
        signer=signer,
        validation_context=vc,
    )
    out = io.BytesIO()
    pdf_signer.sign_pdf(original_pdf, output=out)

    signed_bytes = out.getvalue()
    hash_signed = hashlib.sha256(signed_bytes).hexdigest()

    # Sube firmado
    upload = cloudinary.uploader.upload(
        io.BytesIO(signed_bytes),
        folder="contratos",
        public_id=f"contrato_{contrato.id_prestamo}_signed",
        resource_type="raw",
        overwrite=True,
        format="pdf",
    )
    url_pdf_signed = upload.get("secure_url")

    # Actualiza contrato (sobrescribo url_pdf)
    contrato.url_pdf = url_pdf_signed
    contrato.hash_doc = hash_signed
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="FIRMAR_CRIPTO",
        modulo="Contrato",
        detalle=f"PDF firmado criptográficamente (contrato {id_contrato})",
        valores_nuevos={
            "url_pdf": url_pdf_signed,
            "hash_doc": f"sha256:{hash_signed}",
        },
    )

    await db.commit()
    await db.refresh(contrato)

    return {
        "id_contrato": contrato.id_contrato,
        "url_pdf": contrato.url_pdf,
        "hash_doc": f"sha256:{contrato.hash_doc}",
        "firmado_cripto": True,
    }
