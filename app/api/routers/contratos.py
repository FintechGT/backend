# ============================================================
# app/api/routers/contratos.py
# ============================================================
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
from datetime import datetime
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
from app.db.models.solicitud import Solicitud
from app.db.models.user import User
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol

import cloudinary
import cloudinary.uploader

# ============================================================
# CLOUDINARY (leer de variables de entorno)
# ============================================================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,  # fuerza HTTPS
)

# ============================================================
# PDF BACKEND (WeasyPrint -> ReportLab -> Mínimo)
# ============================================================
_PDF_BACKEND = "none"

def _pdf_bytes_from_html(html_str: str) -> bytes:
    """Genera PDF bytes desde HTML con el mejor backend disponible sin romper import-time."""
    global _PDF_BACKEND

    # A) WeasyPrint (si está instalado)
    try:
        from weasyprint import HTML
        pdf_io = io.BytesIO()
        HTML(string=html_str, base_url=".").write_pdf(target=pdf_io)
        _PDF_BACKEND = "weasyprint"
        return pdf_io.getvalue()
    except Exception:
        pass

    # B) ReportLab (fallback)
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import cm
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
        c.save()
        _PDF_BACKEND = "reportlab"
        return buf.getvalue()
    except Exception:
        pass

    # C) Mínimo (PDF válido sin dependencias externas)
    content = "Contrato\n\n" + re.sub(r"<[^>]+>", "", html_str)
    safe = content[:1500].replace("(", r"\(").replace(")", r"\)")
    text_stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET"
    pdf = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {len(text_stream)} >> stream
{text_stream}
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000063 00000 n 
0000000116 00000 n 
0000000366 00000 n 
0000000524 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
620
%%EOF
"""
    _PDF_BACKEND = "minimal"
    return pdf.encode("latin-1", errors="ignore")

# ============================================================
# pyHanko opcional (firma X.509)
# ============================================================
_USE_PYHANKO = False
try:
    from pyhanko.sign import signers
    from pyhanko_certvalidator import ValidationContext
    _USE_PYHANKO = True
except Exception:
    _USE_PYHANKO = False

# ============================================================
# Helpers de usuario
# ============================================================
def _resolve_user_id(u: User) -> int:
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")

def _ensure_id_usuario_attr(u: User) -> None:
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))

# ============================================================
# Routers
# ============================================================
router_prestamos = APIRouter(prefix="/prestamos", tags=["Contratos"])
router_contratos = APIRouter(prefix="/contratos", tags=["Contratos"])

# ============================================================
# 1) Generar contrato PDF (ADMIN/VALUADOR)
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
    prestamo = (await db.execute(
        select(Prestamo).where(Prestamo.id_prestamo == id_prestamo)
    )).scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    # Estado válido
    estado = (await db.execute(
        select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
    )).scalar_one_or_none()
    if not estado or estado.nombre.lower() not in {"aprobado_pendiente_entrega", "activo"}:
        raise HTTPException(status_code=400, detail=f"Estado no válido para contrato (actual: {getattr(estado, 'nombre', 'N/A')})")

    # No duplicar
    existente = (await db.execute(
        select(Contrato).where(Contrato.id_prestamo == id_prestamo)
    )).scalar_one_or_none()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un contrato para este préstamo")

    # Artículo
    articulo = (await db.execute(
        select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo)
    )).scalar_one_or_none()

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

    # Generar PDF
    try:
        pdf_bytes = _pdf_bytes_from_html(html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el PDF: {e}")

    hash_doc = hashlib.sha256(pdf_bytes).hexdigest()

    # Subir a Cloudinary (firmado)
    upload_result = cloudinary.uploader.upload(
        pdf_bytes,                       # bytes directos
        folder="contratos",
        public_id=f"contrato_{id_prestamo}",
        resource_type="raw",             # PDF = raw
        overwrite=True,
        format="pdf",
    )
    url_pdf = upload_result.get("secure_url")
    if not url_pdf:
        raise HTTPException(status_code=500, detail="Fallo al subir el PDF a Cloudinary")

    # Guardar contrato
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
        valores_nuevos={"pdf_backend": _PDF_BACKEND, "url_pdf": url_pdf, "hash_doc": f"sha256:{hash_doc}"},
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
#    Reglas:
#      - firmante="cliente"  => solo el dueño de la solicitud
#      - firmante="empresa"  => solo ADMINISTRADOR o VALUADOR
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

    # contrato + dueño (join para identificar owner)
    row = (await db.execute(
        select(Contrato, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Contrato.id_contrato == id_contrato)
    )).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    contrato: Contrato = row[0]
    owner_id: int = row[1]

    es_admin_o_valuador = await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "VALUADOR"])
    es_duenio = owner_id == user_id

    # Reglas de firma
    if firmante == "cliente" and not es_duenio:
        raise HTTPException(status_code=403, detail="Solo el dueño puede firmar como cliente")
    if firmante == "empresa" and not es_admin_o_valuador:
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden firmar como empresa")

    # Subir imagen de firma (Data URL o base64 crudo)
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
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )
    firma_url = upload.get("secure_url")
    if not firma_url:
        raise HTTPException(status_code=500, detail="Fallo al subir la firma a Cloudinary")

    # Guardar timestamp naive (UTC) en DB
    ts_now = datetime.utcnow()
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

    contrato = (await db.execute(
        select(Contrato).where(Contrato.id_contrato == id_contrato)
    )).scalar_one_or_none()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    if not contrato.url_pdf:
        raise HTTPException(status_code=400, detail="Contrato no tiene PDF para firmar")

    # Descargar PDF original
    r = requests.get(contrato.url_pdf, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="No se pudo descargar el PDF original")
    original_pdf = io.BytesIO(r.content)

    # Cargar certificado desde variables de entorno
    pfx_b64 = os.getenv("CERT_PFX_B64")
    pfx_pwd = os.getenv("CERT_PFX_PASSWORD", "")
    if not pfx_b64:
        raise HTTPException(status_code=500, detail="Falta CERT_PFX_B64 en variables de entorno")

    pfx_bytes = base64.b64decode(pfx_b64)
    signer = signers.SimpleSigner.load_pkcs12(pfx_bytes, pfx_pwd.encode("utf-8"))

    # Firma (básica, sin TSA)
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

    # Subir versión firmada
    upload = cloudinary.uploader.upload(
        signed_bytes,
        folder="contratos",
        public_id=f"contrato_{contrato.id_prestamo}_signed",
        resource_type="raw",
        overwrite=True,
        format="pdf",
    )
    url_pdf_signed = upload.get("secure_url")
    if not url_pdf_signed:
        raise HTTPException(status_code=500, detail="Fallo al subir el PDF firmado a Cloudinary")

    # Actualizar contrato
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

# ============================================================
# 4) (Opcional) Self-test para validar Cloudinary y PDF
# ============================================================
@router_contratos.get("/_selftest", summary="Probar PDF + Cloudinary (puedes borrar este endpoint)")
async def contratos_selftest():
    pdf = _pdf_bytes_from_html("<h1>Hola Cloudinary</h1><p>Selftest</p>")
    up = cloudinary.uploader.upload(
        pdf,
        folder="contratos/_selftest",
        public_id="ping",
        resource_type="raw",
        overwrite=True,
        format="pdf",
    )
    return {
        "pdf_backend": _PDF_BACKEND,
        "secure_url": up.get("secure_url"),
        "public_id": up.get("public_id"),
        "resource_type": up.get("resource_type"),
    }
