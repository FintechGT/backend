# ============================================================
# app/api/routers/contratos.py
# ============================================================
from datetime import datetime, timezone
import hashlib
import io
import json

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
# CONFIGURAR CLOUDINARY (usa tu variable CLOUDINARY_URL del .env)
# ============================================================
cloudinary.config(cloud_name=None)  # lo leerá de CLOUDINARY_URL automáticamente

# ============================================================
# PDF BACKEND CON FALLBACK (solo dependencias pip)
# ============================================================
_PDF_BACKEND = None

# --- A) Intentar WeasyPrint (calidad top en Linux/Railway) ---
try:
    from weasyprint import HTML

    def _pdf_bytes_from_html(html_str: str) -> bytes:
        pdf_io = io.BytesIO()
        HTML(string=html_str).write_pdf(target=pdf_io)
        return pdf_io.getvalue()

    _PDF_BACKEND = "weasyprint"
except Exception:
    pass

# --- B) Fallback: xhtml2pdf (sin ejecutables, CSS limitado) ---
if _PDF_BACKEND is None:
    try:
        from xhtml2pdf import pisa

        def _pdf_bytes_from_html(html_str: str) -> bytes:
            src = io.StringIO(html_str)
            out = io.BytesIO()
            result = pisa.CreatePDF(src, dest=out, encoding="utf-8")
            if result.err:
                raise RuntimeError("xhtml2pdf no pudo renderizar el HTML")
            return out.getvalue()

        _PDF_BACKEND = "xhtml2pdf"
    except Exception:
        pass

# --- C) Último recurso: ReportLab (PDF mínimo sin HTML) ---
if _PDF_BACKEND is None:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import cm
    import re

    def _pdf_bytes_from_html(html_str: str) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=LETTER)
        w, h = LETTER
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2 * cm, h - 2 * cm, "Contrato (Fallback ReportLab)")
        c.setFont("Helvetica", 10)
        text = re.sub(r"<[^>]+>", "", html_str)
        y = h - 3 * cm
        for line in text.splitlines()[:50]:
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
# HELPERS
# ============================================================


def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame distinto."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _ensure_id_usuario_attr(u: User) -> None:
    """Parche de compatibilidad para utils.roles"""
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))


# ============================================================
# ROUTER
# ============================================================
router_prestamos = APIRouter(prefix="/prestamos", tags=["Contratos"])
router_contratos = APIRouter(prefix="/contratos", tags=["Contratos"])

# ============================================================
# 1️⃣ POST /prestamos/{id_prestamo}/generar-contrato
# ============================================================
@router_prestamos.post(
    "/{id_prestamo}/generar-contrato",
    status_code=status.HTTP_201_CREATED,
    summary="Generar PDF del contrato y guardarlo en la tabla Contrato",
)
async def generar_contrato(
    id_prestamo: int,
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Permisos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "VALUADOR"]):
        raise HTTPException(status_code=403, detail="Solo ADMINISTRADOR o VALUADOR pueden generar contratos")

    # Validar préstamo
    result = await db.execute(select(Prestamo).where(Prestamo.id_prestamo == id_prestamo))
    prestamo = result.scalar_one_or_none()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    # Validar estado del préstamo
    result_estado = await db.execute(select(EstadoPrestamo).where(EstadoPrestamo.id_estado_prestamo == prestamo.id_estado))
    estado = result_estado.scalar_one_or_none()
    if not estado or estado.nombre.lower() not in {"aprobado_pendiente_entrega", "activo"}:
        raise HTTPException(status_code=400, detail=f"El préstamo no está en un estado válido para contrato (actual: {estado.nombre})")

    # Validar que no exista contrato previo
    result_contrato = await db.execute(select(Contrato).where(Contrato.id_prestamo == id_prestamo))
    contrato_existente = result_contrato.scalar_one_or_none()
    if contrato_existente:
        raise HTTPException(status_code=409, detail="Ya existe un contrato para este préstamo")

    # Obtener datos del artículo
    result_articulo = await db.execute(select(Articulo).where(Articulo.id_articulo == prestamo.id_articulo))
    articulo = result_articulo.scalar_one_or_none()

    # Construir HTML simple del contrato
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
        </style>
      </head>
      <body>
        <h1>Contrato de Préstamo #{id_prestamo}</h1>
        <p>Este contrato se celebra entre la empresa y el cliente registrado en el sistema Pignoraticios.</p>
        <table>
          <tr><th>Artículo</th><td>{articulo.descripcion if articulo else "N/A"}</td></tr>
          <tr><th>Monto del préstamo</th><td>Q {float(prestamo.monto_prestamo):,.2f}</td></tr>
          <tr><th>Fecha de inicio</th><td>{prestamo.fecha_inicio}</td></tr>
          <tr><th>Fecha de vencimiento</th><td>{prestamo.fecha_vencimiento}</td></tr>
        </table>
        <p>Firmas pendientes:</p>
        <ul>
          <li>Cliente</li>
          <li>Empresa</li>
        </ul>
        <small>Generado automáticamente con backend {_PDF_BACKEND}</small>
      </body>
    </html>
    """

    # Generar PDF
    try:
        pdf_bytes = _pdf_bytes_from_html(html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo generar el PDF: {e}")

    # Hash SHA256
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

    # Insertar en DB
    contrato = Contrato(
        id_prestamo=id_prestamo,
        url_pdf=url_pdf,
        hash_doc=hash_doc,
        firma_cliente_en=None,
        firma_empresa_en=None,
    )
    db.add(contrato)
    await db.flush()

    # Auditoría
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
# 2️⃣ POST /contratos/{id_contrato}/firmar
# ============================================================
@router_contratos.post(
    "/{id_contrato}/firmar",
    summary="Registrar firma digital (cliente o empresa)",
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
        raise HTTPException(status_code=400, detail="Firmante debe ser 'cliente' o 'empresa'")

    if not firma_digital:
        raise HTTPException(status_code=400, detail="Debe incluir la firma digital (base64)")

    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Buscar contrato
    result = await db.execute(select(Contrato).where(Contrato.id_contrato == id_contrato))
    contrato = result.scalar_one_or_none()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")

    # Subir firma a Cloudinary
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo subir la firma: {e}")

    # Actualizar contrato
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
        detalle=f"Firma de {firmante} registrada en contrato {id_contrato}",
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
