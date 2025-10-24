# ============================================================
# app/api/routers/articulos_publicos.py
# ============================================================
"""
Router público/semi-público para artículos.
- Listar artículos (con filtros por estado)
- Ver detalle de artículo con fotos
- Comprar artículo (requiere login)

Permisos:
- ADMINISTRADOR, VALUADOR, CAJERO: Ven TODOS los artículos
- Usuario logueado sin rol especial: Solo artículos en venta
- INVITADO (no logueado): Solo artículos en venta (opcional)
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models.articulo import Articulo
from app.db.models.articulo_foto import Articulo_Foto
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.tipo_articulo import TipoArticulo
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

from datetime import datetime

router = APIRouter(prefix="/articulos", tags=["Articulos Publicos"])


# ============================================================
# Helpers de autorización
# ============================================================
async def get_optional_user(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = None,
) -> Optional[User]:
    """
    Intenta obtener el usuario actual desde el token.
    Si no hay token o es inválido, retorna None (usuario invitado).
    """
    if not authorization:
        return None
    
    try:
        from app.core.security import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials
        
        # Simulamos el esquema Bearer
        if authorization.startswith("Bearer "):
            token = authorization[7:]
            # Aquí deberías validar el token manualmente
            # Por simplicidad, usamos el helper existente si está disponible
            user = await get_current_user(token=token, db=db)
            return user
    except Exception:
        return None
    
    return None


async def _user_has_role(db: AsyncSession, id_usuario: int, role_name: str) -> bool:
    """Verifica si el usuario tiene un rol específico."""
    q = (
        select(func.count())
        .select_from(UsuarioRol)
        .join(Rol, Rol.id_rol == UsuarioRol.id_rol)
        .where(
            UsuarioRol.id_usuario == id_usuario,
            Rol.nombre == role_name,
            Rol.activo.is_(True)
        )
    )
    return (await db.scalar(q) or 0) > 0


async def _puede_ver_todos_articulos(db: AsyncSession, user: Optional[User]) -> bool:
    """
    Retorna True si el usuario puede ver TODOS los artículos.
    Roles permitidos: ADMINISTRADOR, VALUADOR, CAJERO
    """
    if not user:
        return False
    
    uid = user.ID_Usuario
    
    for role in ["ADMINISTRADOR", "VALUADOR", "CAJERO"]:
        if await _user_has_role(db, uid, role):
            return True
    
    return False


# ============================================================
# 1) LISTAR ARTÍCULOS (GET /articulos)
# ============================================================
@router.get("", response_model=ArticuloPublicoListResponse)
async def listar_articulos_publicos(
    estado: Optional[str] = Query(None, description="Filtrar por estado del artículo"),
    id_tipo: Optional[int] = Query(None, description="Filtrar por tipo de artículo"),
    q: Optional[str] = Query(None, description="Buscar en descripción"),
    solo_en_venta: Optional[bool] = Query(
        None,
        description="Si true, solo artículos en inventario disponibles para venta"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Query(None, description="Token Bearer (opcional)"),
):
    """
    Lista artículos con filtros opcionales.
    
    Permisos:
    - ADMINISTRADOR, VALUADOR, CAJERO: Ven todos los artículos
    - Usuario logueado sin rol especial: Solo artículos en venta/inventario
    - INVITADO (no logueado): Solo artículos en venta/inventario
    """
    user = await get_optional_user(db=db, authorization=authorization)
    puede_ver_todos = await _puede_ver_todos_articulos(db, user)
    
    # Construir query base
    stmt = select(Articulo).options(
        selectinload(Articulo.fotos),
        selectinload(Articulo.estado_rel),
        selectinload(Articulo.tipo_rel),
    )
    
    # Filtros de negocio
    if not puede_ver_todos:
        # Usuario normal/invitado: solo artículos en estados "vendibles"
        # Ajusta estos estados según tu negocio
        estados_publicos = ["en_inventario", "en_venta", "disponible"]
        stmt = stmt.join(EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado)
        stmt = stmt.where(func.lower(EstadoArticulo.nombre).in_([e.lower() for e in estados_publicos]))
    
    # Filtros del usuario
    if estado:
        stmt = stmt.join(EstadoArticulo, EstadoArticulo.id_estado_articulo == Articulo.id_estado)
        stmt = stmt.where(func.lower(EstadoArticulo.nombre) == estado.lower())
    
    if id_tipo:
        stmt = stmt.where(Articulo.id_tipo == id_tipo)
    
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Articulo.descripcion).like(like))
    
    if solo_en_venta:
        # Solo artículos que están en Inventario_Venta con estado 'disponible' o 'en_venta'
        stmt = stmt.join(
            InventarioVenta,
            InventarioVenta.id_articulo == Articulo.id_articulo
        ).where(
            or_(
                InventarioVenta.estado == "disponible",
                InventarioVenta.estado == "en_venta"
            )
        )
    
    # Total
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    
    # Paginación
    stmt = stmt.order_by(Articulo.id_articulo.desc()).limit(limit).offset(offset)
    articulos = (await db.execute(stmt)).scalars().all()
    
    # Construir respuesta
    items: List[ArticuloPublicoListItem] = []
    for art in articulos:
        # Obtener estado
        estado_obj = await db.get(EstadoArticulo, art.id_estado)
        estado_nombre = estado_obj.nombre if estado_obj else "desconocido"
        
        # Obtener tipo
        tipo_obj = await db.get(TipoArticulo, art.id_tipo)
        tipo_nombre = tipo_obj.nombre if tipo_obj else "N/A"
        
        # Obtener fotos
        fotos_urls = [f.url for f in art.fotos] if art.fotos else []
        
        # Verificar si está en inventario
        inv = (await db.execute(
            select(InventarioVenta).where(InventarioVenta.id_articulo == art.id_articulo)
        )).scalar_one_or_none()
        
        precio_venta = float(inv.precio_actual) if inv and inv.precio_actual else None
        disponible_compra = bool(inv and inv.estado in ["disponible", "en_venta"])
        
        items.append(ArticuloPublicoListItem(
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
        ))
    
    return ArticuloPublicoListResponse(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
    )


# ============================================================
# 2) DETALLE DE ARTÍCULO (GET /articulos/{id_articulo})
# ============================================================
@router.get("/{id_articulo}", response_model=ArticuloPublicoDetalle)
async def obtener_articulo_detalle(
    id_articulo: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Query(None, description="Token Bearer (opcional)"),
):
    """
    Obtiene el detalle completo de un artículo con todas sus fotos.
    
    Permisos:
    - ADMINISTRADOR, VALUADOR, CAJERO: Pueden ver cualquier artículo
    - Otros usuarios: Solo artículos públicos (en venta/inventario)
    """
    user = await get_optional_user(db=db, authorization=authorization)
    puede_ver_todos = await _puede_ver_todos_articulos(db, user)
    
    # Obtener artículo
    articulo = await db.get(Articulo, id_articulo)
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    
    # Verificar permisos
    if not puede_ver_todos:
        estado_obj = await db.get(EstadoArticulo, articulo.id_estado)
        estados_publicos = ["en_inventario", "en_venta", "disponible"]
        if not estado_obj or estado_obj.nombre.lower() not in [e.lower() for e in estados_publicos]:
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para ver este artículo"
            )
    
    # Obtener estado
    estado_obj = await db.get(EstadoArticulo, articulo.id_estado)
    estado_nombre = estado_obj.nombre if estado_obj else "desconocido"
    
    # Obtener tipo
    tipo_obj = await db.get(TipoArticulo, articulo.id_tipo)
    tipo_nombre = tipo_obj.nombre if tipo_obj else "N/A"
    
    # Obtener fotos (ordenadas)
    fotos = (await db.execute(
        select(Articulo_Foto)
        .where(Articulo_Foto.id_articulo == id_articulo)
        .order_by(Articulo_Foto.orden.asc())
    )).scalars().all()
    fotos_urls = [f.url for f in fotos]
    
    # Obtener info de inventario
    inv = (await db.execute(
        select(InventarioVenta).where(InventarioVenta.id_articulo == id_articulo)
    )).scalar_one_or_none()
    
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
    authorization: str = Query(..., description="Token Bearer (requerido)"),
):
    """
    Registra la compra de un artículo del inventario.
    
    Requisitos:
    - Usuario debe estar logueado
    - Artículo debe estar en inventario con estado 'disponible' o 'en_venta'
    - No puede estar ya vendido
    
    El proceso:
    1. Verifica que el artículo esté disponible
    2. Registra la venta en Inventario_Venta
    3. Actualiza el estado del artículo a 'vendido'
    4. Registra auditoría
    """
    # Verificar usuario logueado
    user = await get_optional_user(db=db, authorization=authorization)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Debes estar logueado para comprar artículos"
        )
    
    # Verificar que el artículo existe
    articulo = await db.get(Articulo, id_articulo)
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    
    # Verificar que está en inventario
    inv = (await db.execute(
        select(InventarioVenta).where(InventarioVenta.id_articulo == id_articulo)
    )).scalar_one_or_none()
    
    if not inv:
        raise HTTPException(
            status_code=400,
            detail="Este artículo no está disponible para venta"
        )
    
    # Verificar estado
    if inv.estado not in ["disponible", "en_venta"]:
        raise HTTPException(
            status_code=409,
            detail=f"Este artículo ya no está disponible (estado: {inv.estado})"
        )
    
    # Actualizar inventario con la venta
    inv.estado = "vendido"
    inv.precio_venta = body.precio_venta or inv.precio_actual
    inv.fecha_venta = body.fecha_venta or datetime.utcnow().date()
    inv.medio_pago = body.medio_pago
    inv.ref_bancaria = body.ref_bancaria
    inv.comprador_nombre = body.comprador_nombre
    inv.comprador_nit = body.comprador_nit
    inv.comprobante_url = str(body.comprobante_url) if body.comprobante_url else None
    inv.nota = body.nota
    
    # Actualizar estado del artículo a 'vendido'
    estado_vendido = (await db.execute(
        select(EstadoArticulo).where(func.lower(EstadoArticulo.nombre) == "vendido")
    )).scalar_one_or_none()
    
    if estado_vendido:
        articulo.id_estado = estado_vendido.id_estado_articulo
    
    # Registrar auditoría
    aud = Auditoria(
        id_usuario=user.ID_Usuario,
        accion="COMPRAR_ARTICULO",
        modulo="ArticulosPublicos",
        fecha_hora=datetime.utcnow(),
        detalle=f"Compra de artículo {id_articulo} por usuario {user.ID_Usuario}",
        old_values=f'{{"estado": "{inv.estado}"}}',
        new_values=f'{{"estado": "vendido", "precio_venta": {float(inv.precio_venta or 0)}}}',
    )
    db.add(aud)
    
    try:
        await db.commit()
        await db.refresh(inv)
        await db.refresh(articulo)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la compra: {str(e)}"
        )
    
    return ComprarArticuloOut(
        id_articulo=id_articulo,
        id_inventario=inv.id_inventario,
        estado="vendido",
        precio_venta=float(inv.precio_venta or 0),
        fecha_venta=inv.fecha_venta.isoformat() if inv.fecha_venta else None,
        mensaje="Compra registrada exitosamente",
    )