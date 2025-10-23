# ============================================================
# app/api/routers/prestamo_detalle_completo.py
# ============================================================
"""
API unificada para obtener el detalle completo de un préstamo.
Control de visibilidad según rol del usuario.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.articulo_foto import ArticuloFoto
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.solicitud import Solicitud
from app.db.models.user import User
from app.db.models.pago import Pago
from app.db.models.estado_pago import EstadoPago
from app.db.models.comprobante import Comprobante
from app.db.models.contrato import Contrato
from app.db.models.prestamo_movimiento import PrestamoMovimiento

# Schemas
from app.schemas.prestamo_detalle_completo import (
    PrestamoDetalleCompletoOut,
    EstadoMini,
    ClienteMini,
    ArticuloMini,
    PagoItem,
    ContratoMini,
    MovimientoItem,
)

# Utils
from app.utils.roles import obtener_roles_usuario


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Detalle Completo"])


# ============================================================
# HELPERS
# ============================================================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario"""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _es_rol_admin(roles: list[str]) -> bool:
    """Verifica si el usuario tiene un rol administrativo"""
    roles_admin = {"ADMINISTRADOR", "CAJERO", "VALUADOR", "SUPERVISOR"}
    roles_lower = {r.lower() for r in roles}
    return bool(roles_admin & {r.upper() for r in roles_lower})


def _calcular_dias_mora(fecha_venc: date) -> int:
    """Calcula días de mora desde fecha_vencimiento"""
    hoy = date.today()
    if hoy > fecha_venc:
        return (hoy - fecha_venc).days
    return 0


def _determinar_estado_contrato(c: Contrato) -> str:
    """Determina el estado del contrato según firmas"""
    if not c:
        return "sin_contrato"
    if c.firma_cliente_en and c.firma_empresa_en:
        return "firmado_completo"
    if c.firma_cliente_en or c.firma_empresa_en:
        return "firmado_parcial"
    return "pendiente_firma"


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================
@router.get(
    "/{id_prestamo}/detalle-completo",
    response_model=PrestamoDetalleCompletoOut,
    summary="Detalle completo de un préstamo (rol-aware)",
    description=(
        "Devuelve TODA la información de un préstamo según el rol del usuario:\n\n"
        "**INVITADO:**\n"
        "- Solo puede ver sus propios préstamos\n"
        "- No ve info del cliente ni evaluador\n"
        "- No ve movimientos detallados\n\n"
        "**ADMIN/CAJERO/VALUADOR/SUPERVISOR:**\n"
        "- Ve todos los préstamos\n"
        "- Ve info completa del cliente y evaluador\n"
        "- Ve historial de movimientos (interés/mora)\n"
        "- Ve todos los pagos y comprobantes"
    )
)
async def obtener_detalle_completo_prestamo(
    id_prestamo: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtiene el detalle completo de un préstamo con control de visibilidad según rol.
    """
    user_id = _resolve_user_id(current_user)
    roles = await obtener_roles_usuario(current_user, db)
    es_admin = _es_rol_admin(roles)

    # ============================================================
    # 1. OBTENER PRÉSTAMO BASE
    # ============================================================
    stmt_prestamo = (
        select(
            Prestamo,
            EstadoPrestamo.id_estado_prestamo.label("estado_id"),
            EstadoPrestamo.nombre.label("estado_nombre"),
            Solicitud.id_usuario.label("owner_id"),
        )
        .join(Articulo, Articulo.id_articulo == Prestamo.id_articulo)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .join(EstadoPrestamo, EstadoPrestamo.id_estado_prestamo == Prestamo.id_estado, isouter=True)
        .where(Prestamo.id_prestamo == id_prestamo)
    )
    row = (await db.execute(stmt_prestamo)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    prestamo: Prestamo = row[0]
    estado_id: int = row.estado_id
    estado_nombre: str = row.estado_nombre or "desconocido"
    owner_id: int = row.owner_id

    # Validar permisos
    if not es_admin and owner_id != user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este préstamo")

    # ============================================================
    # 2. OBTENER ARTÍCULO + FOTOS
    # ============================================================
    stmt_articulo = (
        select(
            Articulo,
            EstadoArticulo.nombre.label("estado_articulo"),
            CatTipoArticulo.nombre.label("tipo_nombre"),
            Solicitud.id_solicitud,
        )
        .join(EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado, isouter=True)
        .join(CatTipoArticulo, CatTipoArticulo.id_tipo == Articulo.id_tipo, isouter=True)
        .join(Solicitud, Solicitud.id_solicitud == Articulo.id_solicitud)
        .where(Articulo.id_articulo == prestamo.id_articulo)
    )
    art_row = (await db.execute(stmt_articulo)).one_or_none()
    if not art_row:
        raise HTTPException(status_code=500, detail="Artículo no encontrado")

    articulo: Articulo = art_row[0]
    estado_articulo: str = art_row.estado_articulo or "desconocido"
    tipo_nombre: Optional[str] = art_row.tipo_nombre
    id_solicitud: int = art_row.id_solicitud

    # Fotos del artículo
    stmt_fotos = select(ArticuloFoto.url).where(ArticuloFoto.id_articulo == articulo.id_articulo).order_by(ArticuloFoto.orden)
    fotos_urls = (await db.execute(stmt_fotos)).scalars().all()

    articulo_mini = ArticuloMini(
        id_articulo=articulo.id_articulo,
        id_solicitud=id_solicitud,
        id_tipo=articulo.id_tipo,
        tipo_nombre=tipo_nombre,
        descripcion=articulo.descripcion,
        valor_estimado=float(articulo.valor_estimado),
        valor_aprobado=float(articulo.valor_aprobado) if articulo.valor_aprobado else None,
        condicion=articulo.condicion,
        estado=estado_articulo,
        fotos=list(fotos_urls),
    )

    # ============================================================
    # 3. CLIENTE (solo para admin)
    # ============================================================
    cliente_mini: Optional[ClienteMini] = None
    if es_admin:
        stmt_cliente = select(User).where(User.ID_Usuario == owner_id)
        cliente_obj = (await db.execute(stmt_cliente)).scalar_one_or_none()
        if cliente_obj:
            cliente_mini = ClienteMini(
                id=cliente_obj.ID_Usuario,
                nombre=cliente_obj.Nombre,
                correo=cliente_obj.Correo,
                telefono=cliente_obj.Telefono,
                direccion=cliente_obj.Direccion,
            )

    # ============================================================
    # 4. EVALUADOR (solo para admin)
    # ============================================================
    evaluador_id: Optional[int] = None
    evaluador_nombre: Optional[str] = None
    if es_admin:
        stmt_eval = select(User).where(User.ID_Usuario == prestamo.id_usuario_evaluador)
        eval_obj = (await db.execute(stmt_eval)).scalar_one_or_none()
        if eval_obj:
            evaluador_id = eval_obj.ID_Usuario
            evaluador_nombre = eval_obj.Nombre

    # ============================================================
    # 5. PAGOS + COMPROBANTES
    # ============================================================
    stmt_pagos = (
        select(
            Pago,
            EstadoPago.nombre.label("estado_pago"),
            User.Nombre.label("validador_nombre"),
        )
        .join(EstadoPago, EstadoPago.id_estado_pago == Pago.id_estado, isouter=True)
        .join(User, User.ID_Usuario == Pago.id_validador, isouter=True)
        .where(Pago.id_prestamo == id_prestamo)
        .order_by(Pago.fecha_pago.desc())
    )
    pagos_rows = (await db.execute(stmt_pagos)).all()

    pagos_items = []
    total_pagado = 0.0

    for pago_row in pagos_rows:
        pago: Pago = pago_row[0]
        estado_pago: str = pago_row.estado_pago or "desconocido"
        validador_nombre: Optional[str] = pago_row.validador_nombre

        # Comprobantes del pago
        stmt_comp = select(Comprobante.imagen).where(Comprobante.id_pago == pago.id_pago)
        comp_urls = (await db.execute(stmt_comp)).scalars().all()

        pagos_items.append(
            PagoItem(
                id_pago=pago.id_pago,
                fecha_pago=pago.fecha_pago.isoformat() if pago.fecha_pago else None,
                monto=float(pago.monto),
                estado=estado_pago,
                tipo_pago=pago.tipo_pago,
                medio_pago=pago.medio_pago,
                ref_bancaria=pago.ref_bancaria,
                validador_id=pago.id_validador if es_admin else None,
                validador_nombre=validador_nombre if es_admin else None,
                comprobantes=list(comp_urls),
            )
        )

        # Sumar solo pagos validados
        if estado_pago.lower() == "validado":
            total_pagado += float(pago.monto)

    # ============================================================
    # 6. CONTRATO (si existe)
    # ============================================================
    stmt_contrato = select(Contrato).where(Contrato.id_prestamo == id_prestamo)
    contrato_obj = (await db.execute(stmt_contrato)).scalar_one_or_none()

    contrato_mini: Optional[ContratoMini] = None
    if contrato_obj:
        contrato_mini = ContratoMini(
            id_contrato=contrato_obj.id_contrato,
            url_pdf=contrato_obj.url_pdf,
            hash_doc=contrato_obj.hash_doc,
            firma_cliente_en=contrato_obj.firma_cliente_en,
            firma_empresa_en=contrato_obj.firma_empresa_en,
            estado=_determinar_estado_contrato(contrato_obj),
        )

    # ============================================================
    # 7. MOVIMIENTOS (solo para admin)
    # ============================================================
    movimientos_items: Optional[list[MovimientoItem]] = None
    if es_admin:
        stmt_movs = (
            select(PrestamoMovimiento)
            .where(PrestamoMovimiento.id_prestamo == id_prestamo)
            .order_by(PrestamoMovimiento.fecha.desc())
            .limit(100)  # Últimos 100 movimientos
        )
        movs_objs = (await db.execute(stmt_movs)).scalars().all()

        movimientos_items = [
            MovimientoItem(
                id_mov=m.id_mov,
                tipo=m.tipo,
                monto=float(m.monto),
                nota=m.nota,
                fecha=m.fecha,
            )
            for m in movs_objs
        ]

    # ============================================================
    # 8. METADATOS
    # ============================================================
    # Estados que permiten pagos
    estados_pago_permitidos = {"activo", "en_mora_parcial", "en_mora_grave"}
    puede_pagar = estado_nombre.lower() in estados_pago_permitidos

    # Puede liquidar si hay deuda y acepta pagos
    puede_liquidar = puede_pagar and float(prestamo.deuda_actual) > 0

    dias_mora = _calcular_dias_mora(prestamo.fecha_vencimiento)

    # ============================================================
    # 9. RESPUESTA
    # ============================================================
    return PrestamoDetalleCompletoOut(
        id_prestamo=prestamo.id_prestamo,
        estado=EstadoMini(id=estado_id, nombre=estado_nombre),
        fecha_inicio=prestamo.fecha_inicio,
        fecha_vencimiento=prestamo.fecha_vencimiento,
        monto_prestamo=float(prestamo.monto_prestamo),
        deuda_actual=float(prestamo.deuda_actual),
        mora_acumulada=float(prestamo.mora_acumulada),
        interes_acumulada=float(prestamo.interes_acumulada),
        ultimo_calculo_en=prestamo.ultimo_calculo_en,
        created_at=prestamo.created_at,
        updated_at=prestamo.updated_at,
        articulo=articulo_mini,
        cliente=cliente_mini,
        evaluador_id=evaluador_id,
        evaluador_nombre=evaluador_nombre,
        pagos=pagos_items,
        total_pagado=total_pagado,
        contrato=contrato_mini,
        movimientos=movimientos_items,
        puede_pagar=puede_pagar,
        puede_liquidar=puede_liquidar,
        dias_mora=dias_mora,
    )