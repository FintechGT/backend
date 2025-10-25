# ============================================================
# app/api/routers/articulos_publicos.py (sin dependencias a TipoArticulo)
# ============================================================
"""
Router público/semi-público para artículos.
- Listar artículos (con filtros por estado/tipo/texto)
- Ver detalle de artículo con fotos
- Comprar artículo (requiere login)

Permisos:
- ADMINISTRADOR, VALUADOR, CAJERO: Ven TODOS los artículos
- Usuario logueado sin rol especial: Solo artículos públicos/en venta
- INVITADO (no logueado): Solo artículos públicos/en venta
"""

from __future__ import annotations

from typing import Optional, List
from datetime import datetime, date

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Path,
    status,
    Header,
)
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models.articulo import Articulo

# Fotos: soporta ArticuloFoto o Articulo_Foto sin tocar modelos
try:
    from app.db.models.articulo_foto import ArticuloFoto  # nombre recomendado
except Exception:  # noqa
    try:
        from app.db.models.articulo_foto import Articulo_Foto as ArticuloFoto  # fallback
    except Exception:  # si no hay modelo, trabajaremos solo con Articulo
        ArticuloFoto = None  # type: ignore

from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.inventario_venta import InventarioVenta
from app.db.models.user import User
from app.db.models.roles import Rol
from app.db.models.usuario_rol import UsuarioRol
from app.db.models.auditoria import Auditoria

from app.schemas.articulos_publicos import (
    ArticuloPublicoListItem,
    ArticuloPublicoListResponse,
    ArticuloPublicoDetalle,
    ComprarArticuloIn,
    ComprarArticuloOut,
)

router = APIRouter(prefix="/articulos", tags=["Articulos Publicos"])


# ============================================================
# Helpers de autorización
# ============================================================
async def get_optional_user(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(default=None, convert_underscores=False),
) -> Optional[User]:
    """Intenta obtener el usuario actual desde el header Authorization."""
    if not authorization:
        return None
    try:
        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        from app.core.security import get_current_user  # import local
        user = await get_current_user(token=token, db=db)
        return user
    except Exception:
        return None


async def _user_has_role(db: AsyncSession, id_usuario: int, role_name: str) -> bool:
    q = (
        select(func.count())
        .select_from(UsuarioRol)
        .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
        .where(
            UsuarioRol.id_usuario == id_usuario,
            Rol.nombre == role_name,
            Rol.activo.is_(True),
        )
    )
    return (await db.scalar(q) or 0) > 0


async def _puede_ver_todos_articulos(db: AsyncSession, user: Optional[User]) -> bool:
    if not user:
        return False
    uid = user.ID_Usuario
    for role in ["ADMINISTRADOR", "VALUADOR", "CAJERO"]:
        if await _user_has_role(db, uid, role):
            return True
    return False


# ============================================================
# Helpers de datos sin depender de modelos que faltan
# ============================================================
async def _get_tipo_nombre(db: AsyncSession, id_tipo: int) -> str:
    """
    Obtiene el nombre del tipo desde la tabla Cat_Tipo_Articulo usando SQL crudo,
    para evitar importar un modelo que no existe en tu proyecto.
    """
    try:
        res = await db.execute(
            text("SELECT Nombre FROM Cat_Tipo_Articulo WHERE IdTipo = :id"),
            {"id": id_tipo},
        )
        row = res.first()
        return row[0] if row and row[0] else "N/A"
    except Exception:
        # Si la tabla/columna se llama diferente, al menos no rompemos el API
        return "N/A"


async def _get_fotos_urls(db: AsyncSession, id_articulo: int) -> List[str]:
    """
    Devuelve URLs de fotos. Si no existe el modelo ArticuloFoto, devuelve lista vacía.
    """
    if ArticuloFoto is None:
        return []
    try:
        res = await db.execute(
            select(ArticuloFoto).where(ArticuloFoto.id_articulo == id_articulo).order_by(ArticuloFoto.orden.asc())
        )
        fotos = res.scalars().all()
        return [f.url for f in fotos if getattr(f, "url", None)]
    except Exception:
        return []


# ============================================================
# 1) LISTAR ARTÍCULOS (GET /articulos)
# ============================================================
@router.get("", response_model=ArticuloPublicoListResponse)
async def listar_articulos_publicos(
    estado: Optional[str] = Query(None, description="Filtrar por estado del artículo"),
    id_tipo: Optional[int] = Query(None, description="Filtrar por tipo de artículo"),
    q: Optional[str] = Query(None, description="Buscar en descripción"),
    solo_en_venta: Optional[bool] = Query(
        None, description="Si true, solo artículos disponibles en inventario para venta"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(default=None, convert_underscores=False),
):
    user = await get_optional_user(db=db, authorization=authorization)
    puede_ver_todos = await _puede_ver_todos_articulos(db, user)

    # Query base SIN selectinload de relaciones que podrían no existir
    stmt = select(Articulo)

    # Visibilidad pública
    if not puede_ver_todos:
        estados_publicos = ["en_inventario", "en_venta", "disponible"]
        stmt = (
            stmt.join(
                EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado
            )
            .where(func.lower(EstadoArticulo.nombre).in_([e.lower() for e in estados_publicos]))
        )

    # Filtros explícitos
    if estado:
        stmt = (
            stmt.join(
                EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado
            )
            .where(func.lower(EstadoArticulo.nombre) == estado.lower())
        )

    if id_tipo:
        stmt = stmt.where(Articulo.id_tipo == id_tipo)

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Articulo.descripcion).like(like))

    if solo_en_venta:
        stmt = stmt.join(
            InventarioVenta, InventarioVenta.id_articulo == Articulo.id_articulo
        ).where(
            or_(InventarioVenta.estado == "disponible", InventarioVenta.estado == "en_venta")
        )

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(Articulo.id_articulo.desc()).limit(limit).offset(offset)
    articulos = (await db.execute(stmt)).scalars().all()

    items: List[ArticuloPublicoListItem] = []
    for art in articulos:
        # Estado
        estado_obj = await db.get(EstadoArticulo, art.id_estado)
        estado_nombre = estado_obj.nombre if estado_obj else "desconocido"

        # Tipo (vía SQL crudo)
        tipo_nombre = await _get_tipo_nombre(db, art.id_tipo)

        # Fotos
        fotos_urls = await _get_fotos_urls(db, art.id_articulo)

        # Inventario
        inv = (
            await db.execute(
                select(InventarioVenta).where(InventarioVenta.id_articulo == art.id_articulo)
            )
        ).scalar_one_or_none()

        precio_venta = float(inv.precio_actual) if inv and inv.precio_actual else None
        disponible_compra = bool(inv and inv.estado in ["disponible", "en_venta"])

        items.append(
            ArticuloPublicoListItem(
                id_articulo=art.id_articulo,
                id_tipo=art.id_tipo,
                tipo_nombre=tipo_nombre,
                descripcion=art.descripcion,
                valor_estimado=float(art.valor_estimado),
                valor_aprobado=float(art.valor_aprobado) if art.valor_aprobado else None,
                condicion=art.condicion,
                estado=estado_nombre,
                fotos=fotos_urls,
                precio_venta=precio_venta,
                disponible_compra=disponible_compra,
            )
        )

    return ArticuloPublicoListResponse(items=items, total=int(total), limit=limit, offset=offset)


# ============================================================
# 2) DETALLE DE ARTÍCULO (GET /articulos/{id_articulo})
# ============================================================
@router.get("/{id_articulo}", response_model=ArticuloPublicoDetalle)
async def obtener_articulo_detalle(
    id_articulo: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(default=None, convert_underscores=False),
):
    user = await get_optional_user(db=db, authorization=authorization)
    puede_ver_todos = await _puede_ver_todos_articulos(db, user)

    articulo = await db.get(Articulo, id_articulo)
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    if not puede_ver_todos:
        estado_obj = await db.get(EstadoArticulo, articulo.id_estado)
        estados_publicos = ["en_inventario", "en_venta", "disponible"]
        if not estado_obj or estado_obj.nombre.lower() not in [e.lower() for e in estados_publicos]:
            raise HTTPException(status_code=403, detail="No tienes permiso para ver este artículo")

    estado_obj = await db.get(EstadoArticulo, articulo.id_estado)
    estado_nombre = estado_obj.nombre if estado_obj else "desconocido"

    tipo_nombre = await _get_tipo_nombre(db, articulo.id_tipo)
    fotos_urls = await _get_fotos_urls(db, id_articulo)

    inv = (
        await db.execute(
            select(InventarioVenta).where(InventarioVenta.id_articulo == id_articulo)
        )
    ).scalar_one_or_none()

    precio_venta = float(inv.precio_actual) if inv and inv.precio_actual else None
    disponible_compra = bool(inv and inv.estado in ["disponible", "en_venta"])
    fecha_ingreso_inventario = inv.fecha_ingreso if inv else None

    return ArticuloPublicoDetalle(
        id_articulo=articulo.id_articulo,
        id_solicitud=articulo.id_solicitud,
        id_tipo=articulo.id_tipo,
        tipo_nombre=tipo_nombre,
        descripcion=articulo.descripcion,
        valor_estimado=float(articulo.valor_estimado),
        valor_aprobado=float(articulo.valor_aprobado) if articulo.valor_aprobado else None,
        condicion=articulo.condicion,
        estado=estado_nombre,
        fotos=fotos_urls,
        precio_venta=precio_venta,
        disponible_compra=disponible_compra,
        fecha_ingreso_inventario=fecha_ingreso_inventario.isoformat() if fecha_ingreso_inventario else None,
    )


# ============================================================
# 3) COMPRAR ARTÍCULO (POST /articulos/{id_articulo}/comprar)
# ============================================================
@router.post("/{id_articulo}/comprar", response_model=ComprarArticuloOut)
async def comprar_articulo(
    id_articulo: int = Path(..., ge=1),
    body: ComprarArticuloIn = ...,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(
        default=None, convert_underscores=False, description="Bearer <token>"
    ),
):
    # Usuario
    user = await get_optional_user(db=db, authorization=authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Debes estar logueado para comprar artículos",
        )

    # Artículo
    articulo = await db.get(Articulo, id_articulo)
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    # Inventario
    inv = (
        await db.execute(
            select(InventarioVenta).where(InventarioVenta.id_articulo == id_articulo)
        )
    ).scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=400, detail="Este artículo no está disponible para venta")

    if inv.estado not in ["disponible", "en_venta"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este artículo ya no está disponible (estado: {inv.estado})",
        )

    # Actualizaciones
    inv.estado = "vendido"
    inv.precio_venta = body.precio_venta or inv.precio_actual
    inv.fecha_venta = body.fecha_venta or date.today()
    inv.medio_pago = body.medio_pago
    inv.ref_bancaria = body.ref_bancaria
    inv.comprador_nombre = body.comprador_nombre
    inv.comprador_nit = body.comprador_nit
    inv.comprobante_url = str(body.comprobante_url) if body.comprobante_url else None
    inv.nota = body.nota

    # Estado del artículo a vendido (si existe "vendido" en Estado_Articulo)
    estado_vendido = (
        await db.execute(
            select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == "vendido")
        )
    ).scalar_one_or_none()
    if estado_vendido:
        articulo.id_estado = estado_vendido.id_estado_articulo

    # Auditoría
    aud = Auditoria(
        id_usuario=user.ID_Usuario,
        accion="COMPRAR_ARTICULO",
        modulo="ArticulosPublicos",
        fecha_hora=datetime.utcnow(),
        detalle=f"Compra de artículo {id_articulo} por usuario {user.ID_Usuario}",
        old_values='{"estado":"en_venta"}',
        new_values='{"estado":"vendido","precio_venta":%s}' % (float(inv.precio_venta or 0)),
    )
    db.add(aud)

    try:
        await db.commit()
        await db.refresh(inv)
        await db.refresh(articulo)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al procesar la compra: {str(e)}")

    return ComprarArticuloOut(
        id_articulo=id_articulo,
        id_inventario=inv.id_inventario,
        estado="vendido",
        precio_venta=float(inv.precio_venta or 0),
        fecha_venta=inv.fecha_venta.isoformat() if inv.fecha_venta else None,
        mensaje="Compra registrada exitosamente",
    )
