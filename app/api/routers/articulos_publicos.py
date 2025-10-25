# ============================================================
# app/api/routers/articulos_publicos.py
# ============================================================
from __future__ import annotations

from typing import Optional, List, Dict
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
from sqlalchemy import select, func, or_, text, literal
from sqlalchemy.orm import aliased
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

# Prefijo público no conflictivo
router = APIRouter(prefix="/articulos-publicos", tags=["Articulos Publicos"])

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
# Helpers de datos
# ============================================================
async def _get_tipos_nombres_batch(db: AsyncSession, id_tipos: List[int]) -> Dict[int, str]:
    """Batch por SQL crudo para no depender del modelo Cat_Tipo_Articulo."""
    if not id_tipos:
        return {}
    try:
        res = await db.execute(
            text("SELECT IdTipo, Nombre FROM Cat_Tipo_Articulo WHERE IdTipo IN :ids"),
            {"ids": tuple(set(id_tipos))},
        )
        rows = res.fetchall()
        mapa = {int(r[0]): (r[1] or "N/A") for r in rows if r and r[0] is not None}
        for t in id_tipos:
            mapa.setdefault(int(t), "N/A")
        return mapa
    except Exception:
        return {int(t): "N/A" for t in id_tipos}


async def _get_fotos_urls_batch(db: AsyncSession, ids: List[int]) -> Dict[int, List[str]]:
    """Devuelve URLs de fotos por artículo en batch."""
    if ArticuloFoto is None or not ids:
        return {i: [] for i in ids}
    res = await db.execute(
        select(ArticuloFoto).where(ArticuloFoto.id_articulo.in_(ids)).order_by(ArticuloFoto.orden.asc())
    )
    out: Dict[int, List[str]] = {i: [] for i in ids}
    for f in res.scalars().all():
        if getattr(f, "url", None):
            out.setdefault(f.id_articulo, []).append(f.url)
    return out


async def _get_inventarios_batch(db: AsyncSession, ids: List[int]) -> Dict[int, InventarioVenta]:
    """Carga InventarioVenta por artículo en batch."""
    if not ids:
        return {}
    res = await db.execute(select(InventarioVenta).where(InventarioVenta.id_articulo.in_(ids)))
    invs = res.scalars().all()
    return {inv.id_articulo: inv for inv in invs}


# ============================================================
# 1) LISTAR ARTÍCULOS (GET /articulos-publicos)
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

    EA = aliased(EstadoArticulo)
    stmt = select(Articulo)

    need_estado_join = (not puede_ver_todos) or bool(estado)
    if need_estado_join:
        stmt = stmt.join(EA, EA.id_estado_articulo == Articulo.id_estado, isouter=True)

    condiciones = []

    if not puede_ver_todos:
        estados_publicos = ["en_inventario", "en_venta", "disponible"]
        condiciones.append(func.lower(EA.nombre).in_([e.lower() for e in estados_publicos]))

    if estado:
        condiciones.append(func.lower(EA.nombre) == estado.lower())

    if id_tipo:
        condiciones.append(Articulo.id_tipo == id_tipo)

    if q:
        like = f"%{q.lower()}%"
        condiciones.append(func.lower(Articulo.descripcion).like(like))

    if solo_en_venta:
        sub = (
            select(literal(1))
            .select_from(InventarioVenta)
            .where(
                InventarioVenta.id_articulo == Articulo.id_articulo,
                or_(InventarioVenta.estado == "disponible", InventarioVenta.estado == "en_venta"),
            )
            .limit(1)
        )
        condiciones.append(sub.exists())

    if condiciones:
        stmt = stmt.where(*condiciones)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(Articulo.id_articulo.desc()).limit(limit).offset(offset)
    articulos = (await db.execute(stmt)).scalars().all()

    if not articulos:
        return ArticuloPublicoListResponse(items=[], total=int(total), limit=limit, offset=offset)

    ids = [a.id_articulo for a in articulos]
    id_tipos = [a.id_tipo for a in articulos if getattr(a, "id_tipo", None) is not None]
    id_estados = list({a.id_estado for a in articulos if getattr(a, "id_estado", None) is not None})

    estados_map: Dict[int, str] = {}
    if id_estados:
        res_e = await db.execute(
            select(EstadoArticulo.id_estado_articulo, EstadoArticulo.nombre)
            .where(EstadoArticulo.id_estado_articulo.in_(id_estados))
        )
        for ide, nom in res_e.fetchall():
            estados_map[int(ide)] = nom or "desconocido"

    inv_map = await _get_inventarios_batch(db, ids)
    fotos_map = await _get_fotos_urls_batch(db, ids)
    tipos_map = await _get_tipos_nombres_batch(db, id_tipos)

    items: List[ArticuloPublicoListItem] = []
    for art in articulos:
        estado_nombre = estados_map.get(getattr(art, "id_estado", 0), "desconocido")
        tipo_nombre = tipos_map.get(getattr(art, "id_tipo", 0), "N/A")
        fotos_urls = fotos_map.get(art.id_articulo, [])

        inv = inv_map.get(art.id_articulo)
        precio_venta = float(inv.precio_actual) if inv and getattr(inv, "precio_actual", None) else None
        disponible_compra = bool(inv and getattr(inv, "estado", None) in ["disponible", "en_venta"])

        items.append(
            ArticuloPublicoListItem(
                id_articulo=art.id_articulo,
                id_tipo=getattr(art, "id_tipo", None),
                tipo_nombre=tipo_nombre,
                descripcion=art.descripcion,
                valor_estimado=float(art.valor_estimado),
                valor_aprobado=float(art.valor_aprobado) if getattr(art, "valor_aprobado", None) else None,
                condicion=getattr(art, "condicion", None),
                estado=estado_nombre,
                fotos=fotos_urls,
                precio_venta=precio_venta,
                disponible_compra=disponible_compra,
            )
        )

    return ArticuloPublicoListResponse(items=items, total=int(total), limit=limit, offset=offset)


# ============================================================
# 2) DETALLE DE ARTÍCULO (GET /articulos-publicos/{id_articulo})
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

    # Tipo (vía SQL crudo, pero aquí solo 1)
    tipos_map = await _get_tipos_nombres_batch(db, [articulo.id_tipo] if getattr(articulo, "id_tipo", None) else [])
    tipo_nombre = tipos_map.get(getattr(articulo, "id_tipo", 0), "N/A")

    # Fotos
    fotos_map = await _get_fotos_urls_batch(db, [id_articulo])
    fotos_urls = fotos_map.get(id_articulo, [])

    # Inventario
    inv = (
        await db.execute(
            select(InventarioVenta).where(InventarioVenta.id_articulo == id_articulo)
        )
    ).scalar_one_or_none()

    precio_venta = float(inv.precio_actual) if inv and getattr(inv, "precio_actual", None) else None
    disponible_compra = bool(inv and getattr(inv, "estado", None) in ["disponible", "en_venta"])
    fecha_ingreso_inventario: Optional[date] = getattr(inv, "fecha_ingreso", None) if inv else None

    return ArticuloPublicoDetalle(
        id_articulo=articulo.id_articulo,
        id_solicitud=getattr(articulo, "id_solicitud", None),
        id_tipo=getattr(articulo, "id_tipo", None),
        tipo_nombre=tipo_nombre,
        descripcion=articulo.descripcion,
        valor_estimado=float(articulo.valor_estimado),
        valor_aprobado=float(articulo.valor_aprobado) if getattr(articulo, "valor_aprobado", None) else None,
        condicion=getattr(articulo, "condicion", None),
        estado=estado_nombre,
        fotos=fotos_urls,
        precio_venta=precio_venta,
        disponible_compra=disponible_compra,
        fecha_ingreso_inventario=fecha_ingreso_inventario,
    )


# ============================================================
# 3) COMPRAR ARTÍCULO (POST /articulos-publicos/{id_articulo}/comprar)
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

    if getattr(inv, "estado", None) not in ["disponible", "en_venta"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este artículo ya no está disponible (estado: {getattr(inv, 'estado', None)})",
        )

    # Actualizaciones
    inv.estado = "vendido"
    inv.precio_venta = body.precio_venta or getattr(inv, "precio_actual", None)
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
        fecha_venta=inv.fecha_venta,
        mensaje="Compra registrada exitosamente",
    )


# ============================================================
# (Opcional) Alias GET en /articulos para frontend sin cambios
# ============================================================
public_alias = APIRouter(prefix="/articulos", tags=["Articulos Publicos (alias)"])

@public_alias.get("", response_model=ArticuloPublicoListResponse)
async def _alias_listar_articulos_publicos(
    estado: Optional[str] = Query(None),
    id_tipo: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    solo_en_venta: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(default=None, convert_underscores=False),
):
    return await listar_articulos_publicos(
        estado=estado,
        id_tipo=id_tipo,
        q=q,
        solo_en_venta=solo_en_venta,
        limit=limit,
        offset=offset,
        db=db,
        authorization=authorization,
    )

@public_alias.get("/{id_articulo}", response_model=ArticuloPublicoDetalle)
async def _alias_obtener_articulo_detalle(
    id_articulo: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(default=None, convert_underscores=False),
):
    return await obtener_articulo_detalle(
        id_articulo=id_articulo,
        db=db,
        authorization=authorization,
    )
