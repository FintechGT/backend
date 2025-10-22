# ============================================================
# app/api/routers/contratos.py  (actualizado)
# ============================================================
from __future__ import annotations
from datetime import datetime, timezone
import base64, hashlib, io, os, re, requests
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user
from app.db.models import Contrato, Prestamo, EstadoPrestamo, Articulo, Solicitud, User
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol
import cloudinary, cloudinary.uploader

# ============================================================
# CLOUDINARY
# ============================================================
cloudinary.config(cloud_name=None)  # usa CLOUDINARY_URL del entorno

# ============================================================
# PDF BACKEND (WeasyPrint o ReportLab)
# ============================================================
try:
    from weasyprint import HTML
    def _pdf_bytes_from_html(html_str: str) -> bytes:
        pdf_io = io.BytesIO()
        HTML(string=html_str, base_url=".").write_pdf(target=pdf_io)
        return pdf_io.getvalue()
    _PDF_BACKEND = "weasyprint"
except Exception:
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
                c.showPage(); y = h - 2 * cm
        c.save()
        return buf.getvalue()
    _PDF_BACKEND = "reportlab"

# ============================================================
# Helpers
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
# 1) Generar contrato PDF (ADMIN o VALUADOR)
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
    _ensure_id_usuario_attr(current_user)
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "VALUADOR"]):
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden generar contratos")

    prestamo = (await db.execute(select(Prestamo).where(Prestamo.id_prestamo == id_prestamo))).scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    estado = (await db.execute(select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado))).scalar_one_or_none()
    if not estado or estado.nombre.lower() not in {"aprobado_pendiente_entrega", "activo"}:
        raise HTTPException(status_code=400, detail=f"Estado no válido para contrato (actual: {getattr(estado, 'nombre', 'N/A')})")

    if (await db.execute(select(Contrato).where(Contrato.id_prestamo == id_prestamo))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un contrato para este préstamo")

    articulo = (await db.execute(select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo))).scalar_one_or_none()

    html = f"""
    <html><head><meta charset="utf-8"><title>Contrato #{id_prestamo}</title></head>
    <body>
      <h1 style='text-align:center'>Contrato de Préstamo #{id_prestamo}</h1>
      <p>Este contrato se celebra entre la empresa y el cliente registrado en el sistema Pignoraticios.</p>
      <table border='1' cellspacing='0' cellpadding='4'>
        <tr><th>Artículo</th><td>{getattr(articulo, "descripcion", "N/A")}</td></tr>
        <tr><th>Monto</th><td>Q {float(prestamo.monto_prestamo):,.2f}</td></tr>
        <tr><th>Inicio</th><td>{prestamo.fecha_inicio}</td></tr>
        <tr><th>Vencimiento</th><td>{prestamo.fecha_vencimiento}</td></tr>
      </table>
    </body></html>
    """

    pdf_bytes = _pdf_bytes_from_html(html)
    hash_doc = hashlib.sha256(pdf_bytes).hexdigest()

    upload = cloudinary.uploader.upload(
        io.BytesIO(pdf_bytes),
        folder="contratos",
        public_id=f"contrato_{id_prestamo}",
        resource_type="raw",
        overwrite=True,
        format="pdf",
    )
    url_pdf = upload.get("secure_url")

    contrato = Contrato(id_prestamo=id_prestamo, url_pdf=url_pdf, hash_doc=hash_doc)
    db.add(contrato); await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.id_usuario,
        accion="GENERAR_CONTRATO",
        modulo="Contrato",
        detalle=f"Contrato generado para préstamo {id_prestamo}",
        valores_nuevos={"url_pdf": url_pdf, "hash_doc": hash_doc},
    )
    await db.commit(); await db.refresh(contrato)

    return {
        "id_contrato": contrato.id_contrato,
        "id_prestamo": id_prestamo,
        "url_pdf": url_pdf,
        "hash_doc": f"sha256:{hash_doc}",
        "estado": "pendiente_firma",
    }

# ============================================================
# 2) Firmar contrato (cliente o empresa)
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
        raise HTTPException(status_code=400, detail="Debe incluir firma_digital (base64)")

    # Obtener contrato + dueño
    stmt = (
        select(Contrato, Solicitud.id_usuario.label("owner_id"))
        .join(Prestamo, Prestamo.id_prestamo == Contrato.id_prestamo)
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Contrato.id_contrato == id_contrato)
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    contrato: Contrato = row[0]
    owner_id: int = row[1]

    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    es_admin_o_valuador = await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "VALUADOR"])
    es_duenio = owner_id == user_id

    # Reglas de firma
    if firmante == "cliente" and not es_duenio:
        raise HTTPException(status_code=403, detail="Solo el dueño puede firmar como cliente")
    if firmante == "empresa" and not es_admin_o_valuador:
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden firmar como empresa")

    # Subir firma
    upload = cloudinary.uploader.upload(
        firma_digital,
        folder="contratos/firmas",
        public_id=f"firma_{id_contrato}_{firmante}",
        overwrite=True,
        format="png",
        resource_type="image",
        context={"id_contrato": str(id_contrato), "firmante": firmante, "ip": ip},
    )
    firma_url = upload.get("secure_url")

    ts_now = datetime.now(timezone.utc)
    if firmante == "cliente": contrato.firma_cliente_en = ts_now
    else: contrato.firma_empresa_en = ts_now
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
            "ip": ip,
            "contrato_completado": contrato_completado,
        },
    )

    await db.commit(); await db.refresh(contrato)
    return {
        "id_contrato": contrato.id_contrato,
        "firmante": firmante,
        "firma_registrada_en": ts_now.isoformat(),
        "contrato_completado": contrato_completado,
    }
