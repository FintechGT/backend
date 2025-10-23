
# ============================================================
# app/api/routers/contratos.py — UNIFICADO
# ============================================================
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
from datetime import datetime, date
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.contrato import Contrato
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.solicitud import Solicitud
from app.db.models.user import User

# Utils
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol

# --------- Cloudinary ----------
import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# ---------- Helpers Cloudinary ----------
def _cld_normalize_pdf_url(url: str) -> str:
    """Si la URL quedó con /raw/upload/ intenta usar /image/upload/ para vista embebida."""
    if not url:
        return url
    return url.replace("/raw/upload/", "/image/upload/")

def _cld_upload_with_preset_fallback(file_or_bytes, **options):
    """
    1) Si CLOUDINARY_UPLOAD_PRESET existe -> intenta unsigned con preset.
    2) Si falla -> intenta firmado sin preset.
    """
    preset = os.getenv("CLOUDINARY_UPLOAD_PRESET")

    if preset:
        try:
            return cloudinary.uploader.upload(
                file_or_bytes,
                upload_preset=preset,
                unsigned=True,
                **options,
            )
        except CloudinaryError as e:
            print(f"[Cloudinary] unsigned '{preset}' falló: {e}. Reintentando firmado...")

    prev_env = os.environ.get("CLOUDINARY_UPLOAD_PRESET", None)
    cfg_before = cloudinary.config()
    try:
        if prev_env is not None:
            os.environ.pop("CLOUDINARY_UPLOAD_PRESET", None)
        cloudinary.config(upload_preset=None)
        options.pop("upload_preset", None)
        options["unsigned"] = False
        return cloudinary.uploader.upload(file_or_bytes, **options)
    finally:
        if prev_env is not None:
            os.environ["CLOUDINARY_UPLOAD_PRESET"] = prev_env
        cloudinary.config(
            cloud_name=cfg_before.cloud_name,
            api_key=cfg_before.api_key,
            api_secret=cfg_before.api_secret,
            secure=cfg_before.secure,
            upload_preset=getattr(cfg_before, "upload_preset", None),
        )

# --------- PDF BACKENDS ----------
_PDF_BACKEND = "none"

def _pdf_bytes_from_html(html_str: str) -> bytes:
    """Genera PDF desde HTML. Preferimos ReportLab por estabilidad en Windows."""
    global _PDF_BACKEND

    # 1) ReportLab primero
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import cm
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=LETTER)
        w, h = LETTER
        c.setTitle("Contrato")
        c.setAuthor("Pignoraticios")
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, h - 2 * cm, "Contrato de Préstamo")
        c.setFont("Helvetica", 10)
        text = re.sub(r"<[^>]+>", "", html_str)
        y = h - 3 * cm
        for line in text.splitlines():
            for chunk in [line[i:i+100] for i in range(0, len(line), 100)]:
                c.drawString(2 * cm, y, chunk)
                y -= 12
                if y < 2 * cm:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = h - 2 * cm
        c.showPage()
        c.save()
        _PDF_BACKEND = "reportlab"
        pdf = buf.getvalue()
        if not (pdf.startswith(b"%PDF-") and len(pdf) > 800):
            raise RuntimeError("PDF inválido tras ReportLab")
        return pdf
    except Exception:
        pass

    # 2) Luego intenta WeasyPrint (si lo tienes instalado con Cairo/Pango)
    try:
        from weasyprint import HTML
        pdf_io = io.BytesIO()
        HTML(string=html_str, base_url=".").write_pdf(target=pdf_io)
        pdf = pdf_io.getvalue()
        _PDF_BACKEND = "weasyprint"
        if not (pdf.startswith(b"%PDF-") and len(pdf) > 800):
            raise RuntimeError("PDF inválido tras WeasyPrint")
        return pdf
    except Exception:
        pass

    # 3) Fallback mínimo (último recurso)
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
    pdf_bytes = pdf.encode("latin-1", errors="ignore")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise RuntimeError("Fallback mínimo generó bytes no PDF")
    return pdf_bytes

# --------- Firma X.509 opcional ----------
_USE_PYHANKO = False
try:
    from pyhanko.sign import signers
    from pyhanko_certvalidator import ValidationContext
    _USE_PYHANKO = True
except Exception:
    _USE_PYHANKO = False

# --------- Helpers de auth/rol ----------
def _resolve_user_id(u: User) -> int:
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")

def _ensure_id_usuario_attr(u: User) -> None:
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))

async def _es_admin_valuador(user: User, db: AsyncSession) -> bool:
    return await usuario_tiene_algun_rol(user, db, ["ADMINISTRADOR", "VALUADOR"])

def _ensure_data_url_png(b64_or_dataurl: str) -> str:
    if not b64_or_dataurl:
        return b64_or_dataurl
    if b64_or_dataurl.startswith("data:image"):
        return b64_or_dataurl
    return "data:image/png;base64," + b64_or_dataurl

# --------- Routers ---------
router_prestamos = APIRouter(prefix="/prestamos", tags=["Contratos"])
router_contratos = APIRouter(prefix="/contratos", tags=["Contratos"])

# ============================================================
# 1) Generar contrato PDF
# ============================================================
@router_prestamos.post(
    "/{id_prestamo}/generar-contrato",
    status_code=status.HTTP_201_CREATED,
    summary="Generar PDF del contrato para un préstamo aprobado",
)
async def generar_contrato(
    id_prestamo: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    if not await _es_admin_valuador(current_user, db):
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden generar contratos")

    prestamo = (await db.execute(select(Prestamo).where(Prestamo.id_prestamo == id_prestamo))).scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    estado = (await db.execute(
        select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado)
    )).scalar_one_or_none()
    if not estado or estado.nombre.lower() not in {"aprobado_pendiente_entrega", "activo"}:
        raise HTTPException(status_code=400, detail=f"Estado no válido para contrato (actual: {getattr(estado, 'nombre', 'N/A')})")

    existente = (await db.execute(select(Contrato).where(Contrato.id_prestamo == id_prestamo))).scalar_one_or_none()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un contrato para este préstamo")

    articulo = (await db.execute(select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo))).scalar_one_or_none()

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
        <p>Este contrato se celebra entre la empresa y el cliente registrado.</p>
        <table>
          <tr><th>Artículo</th><td>{getattr(articulo, "descripcion", "N/A")}</td></tr>
          <tr><th>Monto del préstamo</th><td>Q {float(prestamo.monto_prestamo):,.2f}</td></tr>
          <tr><th>Fecha de inicio</th><td>{prestamo.fecha_inicio}</td></tr>
          <tr><th>Fecha de vencimiento</th><td>{prestamo.fecha_vencimiento}</td></tr>
        </table>
        <p class="foot">Generado automáticamente por el sistema</p>
      </body>
    </html>
    """

    pdf_bytes = _pdf_bytes_from_html(html)
    hash_doc = hashlib.sha256(pdf_bytes).hexdigest()

    # Subimos como IMAGE para que Cloudinary permita vista embebida de PDF
    upload_result = _cld_upload_with_preset_fallback(
        pdf_bytes,
        folder="contratos",
        public_id=f"contrato_{id_prestamo}",
        resource_type="image",   # <--- clave
        overwrite=True,
        format="pdf",
        type="upload",
    )
    url_pdf = upload_result.get("secure_url")
    if not url_pdf:
        raise HTTPException(status_code=500, detail="Fallo al subir el PDF a Cloudinary")

    url_pdf = _cld_normalize_pdf_url(url_pdf)

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
# 2) Firmar contrato (cliente/empresa)
# ============================================================
@router_contratos.post(
    "/{id_contrato}/firmar",
    summary="Registrar firma digital (cliente o empresa)",
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
    es_admin_o_valuador = await _es_admin_valuador(current_user, db)
    es_duenio = owner_id == user_id

    if firmante == "cliente" and not es_duenio:
        raise HTTPException(status_code=403, detail="Solo el dueño puede firmar como cliente")
    if firmante == "empresa" and not es_admin_o_valuador:
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden firmar como empresa")

    firma_data_url = _ensure_data_url_png(firma_digital)

    upload = _cld_upload_with_preset_fallback(
        firma_data_url,
        folder="contratos/firmas",
        public_id=f"firma_{id_contrato}_{firmante}",
        overwrite=True,
        format="png",
        resource_type="image",
        context={
            "id_contrato": str(id_contrato),
            "firmante": firmante,
            "ip": ip,
            "pdf_hash": contrato.hash_doc or "",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )
    firma_url = upload.get("secure_url")
    if not firma_url:
        raise HTTPException(status_code=500, detail="Fallo al subir la firma a Cloudinary")

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
# 3) Firma CRIPTOGRÁFICA X.509 del PDF (opcional)
# ============================================================
@router_contratos.post(
    "/{id_contrato}/firmar-cripto",
    summary="Firmar criptográficamente el PDF del contrato con un certificado .p12/.pfx",
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

    contrato = (await db.execute(select(Contrato).where(Contrato.id_contrato == id_contrato))).scalar_one_or_none()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    if not contrato.url_pdf:
        raise HTTPException(status_code=400, detail="Contrato no tiene PDF para firmar")

    r = requests.get(contrato.url_pdf, timeout=30)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="No se pudo descargar el PDF original")
    original_pdf = io.BytesIO(r.content)

    pfx_b64 = os.getenv("CERT_PFX_B64")
    pfx_pwd = os.getenv("CERT_PFX_PASSWORD", "")
    if not pfx_b64:
        raise HTTPException(status_code=500, detail="Falta CERT_PFX_B64 en variables de entorno")

    pfx_bytes = base64.b64decode(pfx_b64)
    signer = signers.SimpleSigner.load_pkcs12(pfx_bytes, pfx_pwd.encode("utf-8"))

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

    upload = _cld_upload_with_preset_fallback(
        signed_bytes,
        folder="contratos",
        public_id=f"contrato_{contrato.id_prestamo}_signed",
        resource_type="image",   # subir como image para previsualizar
        overwrite=True,
        format="pdf",
        type="upload",
    )
    url_pdf_signed = upload.get("secure_url")
    if not url_pdf_signed:
        raise HTTPException(status_code=500, detail="Fallo al subir el PDF firmado a Cloudinary")

    url_pdf_signed = _cld_normalize_pdf_url(url_pdf_signed)

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
# 4) Self-test PDF + Cloudinary (puedes borrarlo en prod)
# ============================================================
@router_contratos.get("/_selftest", summary="Probar PDF + Cloudinary")
@router_contratos.get("/_selftest/", include_in_schema=False)
async def contratos_selftest():
    pdf = _pdf_bytes_from_html("<h1>Hola Cloudinary</h1><p>Selftest</p>")
    up = _cld_upload_with_preset_fallback(
        pdf,
        folder="contratos/_selftest",
        public_id="ping",
        resource_type="image",
        overwrite=True,
        format="pdf",
        type="upload",
    )
    return {
        "pdf_backend": _PDF_BACKEND,
        "secure_url": _cld_normalize_pdf_url(up.get("secure_url")),
        "public_id": up.get("public_id"),
        "resource_type": up.get("resource_type"),
    }

# ============================================================
# 5) Listar contratos (rol-aware) con filtros básicos
# ============================================================
@router_contratos.get("", summary="Listar contratos visibles según rol con filtros")
@router_contratos.get("/", include_in_schema=False)
async def listar_contratos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(None, description="Busca por descripción de artículo o por IDs"),
    usuario_id: Optional[int] = Query(None, description="Filtra por dueño (solo admin/valuador)"),
    prestamo_id: Optional[int] = Query(None),
    estado_firma: Optional[str] = Query(None),  # "pendiente" | "parcial" | "completo"
    fecha_desde: Optional[date] = Query(None, description="YYYY-MM-DD (created_at si existe)"),
    fecha_hasta: Optional[date] = Query(None, description="YYYY-MM-DD (created_at si existe)"),
    orden: str = Query("reciente"),  # "reciente" | "antiguo"
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    uid = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)
    es_admin = await _es_admin_valuador(current_user, db)

    # columnas opcionales creadas/actualizadas
    has_created = hasattr(Contrato, "created_at")
    has_updated = hasattr(Contrato, "updated_at")

    select_cols = [
        Contrato.id_contrato,
        Contrato.url_pdf,
        Contrato.hash_doc,
        Contrato.firma_cliente_en,
        Contrato.firma_empresa_en,
        Prestamo.id_prestamo,
        Prestamo.monto_prestamo,
        Prestamo.fecha_inicio,
        Prestamo.fecha_vencimiento,
        Articulo.descripcion.label("articulo_descripcion"),
        Solicitud.id_usuario.label("owner_id"),
    ]
    if has_created:
        select_cols.append(Contrato.created_at)
    if has_updated:
        select_cols.append(Contrato.updated_at)

    base = (
        select(*select_cols)
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
    )

    conds = []
    if not es_admin:
        conds.append(Solicitud.id_usuario == uid)

    if prestamo_id is not None:
        conds.append(Prestamo.id_prestamo == prestamo_id)

    if q:
        q_like = f"%{q.strip()}%"
        try:
            q_num = int(q)
            conds.append(or_(
                Articulo.descripcion.ilike(q_like),
                Contrato.id_contrato == q_num,
                Prestamo.id_prestamo == q_num,
            ))
        except ValueError:
            conds.append(Articulo.descripcion.ilike(q_like))

    if usuario_id is not None:
        if es_admin:
            conds.append(Solicitud.id_usuario == usuario_id)
        else:
            conds.append(Solicitud.id_usuario == uid)

    if estado_firma:
        if estado_firma == "pendiente":
            conds.append(and_(Contrato.firma_cliente_en.is_(None), Contrato.firma_empresa_en.is_(None)))
        elif estado_firma == "parcial":
            conds.append(or_(
                and_(Contrato.firma_cliente_en.is_not(None), Contrato.firma_empresa_en.is_(None)),
                and_(Contrato.firma_cliente_en.is_(None), Contrato.firma_empresa_en.is_not(None)),
            ))
        elif estado_firma == "completo":
            conds.append(and_(Contrato.firma_cliente_en.is_not(None), Contrato.firma_empresa_en.is_not(None)))

    fecha_campo = Contrato.created_at if has_created else Prestamo.fecha_inicio
    if fecha_desde:
        conds.append(fecha_campo >= datetime.combine(fecha_desde, datetime.min.time()))
    if fecha_hasta:
        conds.append(fecha_campo < datetime.combine(fecha_hasta, datetime.max.time()))

    stmt = base.where(and_(*conds)) if conds else base

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    order_col = Contrato.id_contrato.desc() if orden == "reciente" else Contrato.id_contrato.asc()
    rows = (await db.execute(stmt.order_by(order_col).limit(limit).offset(offset))).all()

    items = []
    for r in rows:
        item = {
            "id_contrato": r.id_contrato,
            "id_prestamo": r.id_prestamo,
            "articulo": r.articulo_descripcion,
            "url_pdf": _cld_normalize_pdf_url(r.url_pdf),
            "hash_doc": r.hash_doc,
            "monto_prestamo": float(getattr(r, "monto_prestamo", 0) or 0),
            "fecha_inicio": r.fecha_inicio,
            "fecha_vencimiento": r.fecha_vencimiento,
            "firma_cliente_en": r.firma_cliente_en,
            "firma_empresa_en": r.firma_empresa_en,
        }
        if has_created:
            item["created_at"] = getattr(r, "created_at", None)
        if has_updated:
            item["updated_at"] = getattr(r, "updated_at", None)
        if es_admin:
            item["owner_id"] = r.owner_id
        items.append(item)

    return {"total": total, "limit": limit, "offset": offset, "es_admin": es_admin, "items": items}

# ============================================================
# 6) Mis contratos (solo dueño)
# ============================================================
@router_contratos.get("/mis", summary="Listar mis contratos (usuario autenticado)")
async def listar_mis_contratos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)

    stmt = (
        select(Contrato, Prestamo.id_prestamo, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Solicitud.id_usuario == user_id)
        .order_by(Contrato.id_contrato.desc())
    )
    rows = (await db.execute(stmt)).all()

    items = []
    for row in rows:
        contrato: Contrato = row[0]
        items.append(
            {
                "id_contrato": contrato.id_contrato,
                "id_prestamo": contrato.id_prestamo,
                "url_pdf": _cld_normalize_pdf_url(contrato.url_pdf),
                "hash_doc": contrato.hash_doc,
                "firma_cliente_en": contrato.firma_cliente_en,
                "firma_empresa_en": contrato.firma_empresa_en,
                "created_at": getattr(contrato, "created_at", None),
                "updated_at": getattr(contrato, "updated_at", None),
            }
        )
    return items

# ============================================================
# 7) Detalle de contrato (dueño o ADMIN/VALUADOR)
# ============================================================
@router_contratos.get("/{id_contrato}", summary="Detalle de contrato (dueño o ADMIN/VALUADOR)")
async def obtener_contrato(
    id_contrato: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)

    stmt = (
        select(Contrato, Prestamo.id_prestamo, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Contrato.id_contrato == id_contrato)
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    contrato: Contrato = row[0]
    owner_id: int = row[2]

    if owner_id != user_id and not (await _es_admin_valuador(current_user, db)):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este contrato")

    return {
        "id_contrato": contrato.id_contrato,
        "id_prestamo": contrato.id_prestamo,
        "url_pdf": _cld_normalize_pdf_url(contrato.url_pdf),
        "hash_doc": contrato.hash_doc,
        "firma_cliente_en": contrato.firma_cliente_en,
        "firma_empresa_en": contrato.firma_empresa_en,
        "owner_id": owner_id,
        "created_at": getattr(contrato, "created_at", None),
        "updated_at": getattr(contrato, "updated_at", None),
    }

# ============================================================
# 8) Abrir PDF normalizado (redirige al visor/descarga)
# ============================================================
@router_contratos.get("/{id_contrato}/abrir", summary="Redirige al PDF del contrato (normalizado)")
async def abrir_pdf_contrato(
    id_contrato: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Contrato, Prestamo.id_prestamo, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Contrato.id_contrato == id_contrato)
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    contrato: Contrato = row[0]
    owner_id: int = row[2]
    user_id = _resolve_user_id(current_user)

    if owner_id != user_id and not (await _es_admin_valuador(current_user, db)):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este contrato")

    if not contrato.url_pdf:
        raise HTTPException(status_code=404, detail="Contrato sin PDF")

    url = _cld_normalize_pdf_url(contrato.url_pdf)
    return RedirectResponse(url=url, status_code=302)
# en la cabecera del archivo
from fastapi.responses import StreamingResponse

@router_contratos.get("/{id_contrato}/ver", summary="Renderiza el PDF del contrato vía backend")
async def ver_pdf_contrato(
    id_contrato: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1) auth y fetch del contrato (igual que en /{id_contrato})
    stmt = (
        select(Contrato, Prestamo.id_prestamo, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Contrato.id_contrato == id_contrato)
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    contrato: Contrato = row[0]
    owner_id: int = row[2]
    user_id = _resolve_user_id(current_user)
    if owner_id != user_id and not (await _es_admin_valuador(current_user, db)):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este contrato")

    if not contrato.url_pdf:
        raise HTTPException(status_code=404, detail="Contrato sin PDF")

    # 2) normalizar por si quedó /raw/
    url = contrato.url_pdf.replace("/raw/upload/", "/image/upload/")

    # 3) descarga y stream con headers de PDF
    r = requests.get(url, stream=True, timeout=30)
    if r.status_code != 200:
        # intenta segunda ruta por si el CDN exige raw
        url_alt = contrato.url_pdf.replace("/image/upload/", "/raw/upload/")
        r = requests.get(url_alt, stream=True, timeout=30)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"No se pudo obtener el PDF (HTTP {r.status_code})")

    # valida firma mínima
    first = next(r.iter_content(chunk_size=5))
    if first[:5] != b"%PDF-":
        # si el primer chunk no trae firma, vuelve a descargar sin stream para validar
        r2 = requests.get(url, timeout=30)
        if r2.status_code == 200 and r2.content[:5] != b"%PDF-":
            raise HTTPException(status_code=500, detail="El archivo remoto no es un PDF válido")
        # si sí es PDF, construye stream con ese contenido
        return StreamingResponse(
            io.BytesIO(r2.content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="contrato_{contrato.id_prestamo}.pdf"',
                "Cache-Control": "private, max-age=0, no-cache",
            },
        )

    # re-construye un generador que incluya los bytes ya leídos
    def gen():
        yield first
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                yield chunk

    return StreamingResponse(
        gen(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="contrato_{contrato.id_prestamo}.pdf"',
            "Cache-Control": "private, max-age=0, no-cache",
        },
    )
