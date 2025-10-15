# app/api/routers/inventario_venta.py
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.inventario_venta import InventarioVenta
from app.db.models.estado_inventario import EstadoInventario
from app.db.models.comprobante import Comprobante
from app.db.models.articulo import Articulo
from app.db.models.user import User

# Schemas
from app.schemas.inventario_venta import (
    InventarioCrearIn, InventarioCrearOut,
    InventarioActualizarIn, InventarioActualizarOut,
    InventarioVentaIn, InventarioVentaOut, CompradorOut,
    InventarioListItemOut, InventarioListResponse,
    InventarioDetalleOut
)

# Utils
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/inventario", tags=["Inventario"])


# ============================================================
# HELPERS
# ============================================================
def _resolve_user_id(u: User) -> int:
    """Devuelve el id del usuario aunque el atributo se llame ID_Usuario, id_usuario o id."""
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(u, attr, None)
        if isinstance(val, int):
            return val
    raise HTTPException(status_code=500, detail="No se pudo resolver el ID del usuario")


def _ensure_id_usuario_attr(u: User) -> None:
    """Parche para compatibilidad con utils.roles"""
    if not hasattr(u, "id_usuario"):
        setattr(u, "id_usuario", _resolve_user_id(u))


async def _obtener_estado_inventario(db: AsyncSession, nombre: str) -> EstadoInventario:
    """Obtiene un estado de inventario por nombre (case-insensitive)."""
    result = await db.execute(
        select(EstadoInventario).where(func.lower(EstadoInventario.nombre) == nombre.lower())
    )
    estado = result.scalar_one_or_none()
    if not estado:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de inventario '{nombre}' no existe en catálogo"
        )
    return estado


# ============================================================
# POST - CREAR (Ingresar artículo al inventario)
# Permisos: ADMINISTRADOR, SUPERVISOR
# ============================================================
@router.post(
    "",
    response_model=InventarioCrearOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingresar artículo al inventario",
    description=(
        "Crea un nuevo registro de inventario para un artículo. "
        "El artículo debe existir y no tener ya un registro de inventario activo (1:1). "
        "**Permisos:** ADMINISTRADOR, SUPERVISOR"
    )
)
async def crear_inventario(
    payload: InventarioCrearIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Permisos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "SUPERVISOR"]):
        raise HTTPException(status_code=403, detail="Requiere rol ADMINISTRADOR o SUPERVISOR")

    # Validar que el artículo exista
    result_art = await db.execute(
        select(Articulo).where(Articulo.id_articulo == payload.id_articulo)
    )
    articulo = result_art.scalar_one_or_none()
    if not articulo:
        raise HTTPException(status_code=404, detail=f"Artículo {payload.id_articulo} no encontrado")

    # Validar 1:1 - no debe existir inventario previo
    result_inv = await db.execute(
        select(InventarioVenta).where(InventarioVenta.id_articulo == payload.id_articulo)
    )
    if result_inv.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"El artículo {payload.id_articulo} ya tiene un registro de inventario"
        )

    # Estado inicial: disponible
    estado_disponible = await _obtener_estado_inventario(db, "disponible")

    # Precio actual por defecto = precio_base
    precio_actual = payload.precio_actual if payload.precio_actual is not None else payload.precio_base

    # Crear registro
    nuevo_inventario = InventarioVenta(
        id_articulo=payload.id_articulo,
        id_estado=estado_disponible.id_estado_inventario,
        precio_base=payload.precio_base,
        precio_actual=precio_actual,
        dias_en_bodega=0,
        fecha_ingreso=date.today(),
    )
    db.add(nuevo_inventario)
    await db.flush()

    # Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="INVENTARIO_CREAR",
        modulo="Inventario",
        detalle=f"Artículo {payload.id_articulo} ingresado al inventario (ID: {nuevo_inventario.id_inventario})",
        valores_nuevos={
            "id_inventario": nuevo_inventario.id_inventario,
            "id_articulo": payload.id_articulo,
            "precio_base": float(payload.precio_base),
            "precio_actual": float(precio_actual),
            "nota_ingreso": payload.nota_ingreso,
        }
    )

    await db.commit()
    await db.refresh(nuevo_inventario)

    return InventarioCrearOut(
        id_inventario=nuevo_inventario.id_inventario,
        id_articulo=nuevo_inventario.id_articulo,
        estado="disponible",
        precio_base=float(nuevo_inventario.precio_base),
        precio_actual=float(nuevo_inventario.precio_actual),
        dias_en_bodega=nuevo_inventario.dias_en_bodega,
        fecha_ingreso=nuevo_inventario.fecha_ingreso,
    )


# ============================================================
# GET - LISTAR (con filtros y paginación)
# Permisos: ADMINISTRADOR, SUPERVISOR, VALUADOR, CAJERO
# ============================================================
@router.get(
    "",
    response_model=InventarioListResponse,
    summary="Listar inventario con filtros",
    description=(
        "Lista items del inventario con filtros opcionales. "
        "**Permisos:** ADMINISTRADOR, SUPERVISOR, VALUADOR, CAJERO"
    )
)
async def listar_inventario(
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    desde: Optional[date] = Query(None, description="Fecha de ingreso desde"),
    hasta: Optional[date] = Query(None, description="Fecha de ingreso hasta"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Permisos de lectura
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "SUPERVISOR", "VALUADOR", "CAJERO"]):
        raise HTTPException(status_code=403, detail="Sin permisos de lectura")

    # Query base
    stmt = select(InventarioVenta).order_by(InventarioVenta.id_inventario.desc())

    # Filtros
    if estado:
        estado_obj = await _obtener_estado_inventario(db, estado)
        stmt = stmt.where(InventarioVenta.id_estado == estado_obj.id_estado_inventario)

    if desde:
        stmt = stmt.where(InventarioVenta.fecha_ingreso >= desde)

    if hasta:
        stmt = stmt.where(InventarioVenta.fecha_ingreso <= hasta)

    # Total
    count_result = await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )
    total = count_result.scalar() or 0

    # Paginación
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    items_db = result.scalars().all()

    # Construir respuesta
    items = []
    for inv in items_db:
        # Estado
        result_estado = await db.execute(
            select(EstadoInventario).where(EstadoInventario.id_estado_inventario == inv.id_estado)
        )
        estado_obj = result_estado.scalar_one_or_none()
        estado_nombre = estado_obj.nombre if estado_obj else "desconocido"

        # Descripción del artículo
        result_art = await db.execute(
            select(Articulo.descripcion).where(Articulo.id_articulo == inv.id_articulo)
        )
        descripcion = result_art.scalar_one_or_none()

        items.append(
            InventarioListItemOut(
                id_inventario=inv.id_inventario,
                id_articulo=inv.id_articulo,
                estado=estado_nombre,
                precio_base=float(inv.precio_base),
                precio_actual=float(inv.precio_actual),
                dias_en_bodega=inv.dias_en_bodega,
                fecha_ingreso=inv.fecha_ingreso,
                descripcion_articulo=descripcion,
            )
        )

    return InventarioListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )


# ============================================================
# GET - DETALLE (individual)
# Permisos: ADMINISTRADOR, SUPERVISOR, VALUADOR, CAJERO
# ============================================================
@router.get(
    "/{id_inventario}",
    response_model=InventarioDetalleOut,
    summary="Obtener detalle de un item de inventario",
    description="**Permisos:** ADMINISTRADOR, SUPERVISOR, VALUADOR, CAJERO"
)
async def obtener_inventario(
    id_inventario: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_id_usuario_attr(current_user)

    # Permisos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "SUPERVISOR", "VALUADOR", "CAJERO"]):
        raise HTTPException(status_code=403, detail="Sin permisos de lectura")

    # Cargar inventario
    result = await db.execute(
        select(InventarioVenta).where(InventarioVenta.id_inventario == id_inventario)
    )
    inventario = result.scalar_one_or_none()
    if not inventario:
        raise HTTPException(status_code=404, detail="Inventario no encontrado")

    # Estado
    result_estado = await db.execute(
        select(EstadoInventario).where(EstadoInventario.id_estado_inventario == inventario.id_estado)
    )
    estado = result_estado.scalar_one_or_none()
    estado_nombre = estado.nombre if estado else "desconocido"

    # Artículo relacionado
    result_art = await db.execute(
        select(Articulo).where(Articulo.id_articulo == inventario.id_articulo)
    )
    articulo = result_art.scalar_one_or_none()
    articulo_data = None
    if articulo:
        articulo_data = {
            "id_articulo": articulo.id_articulo,
            "descripcion": articulo.descripcion,
            "valor_estimado": float(articulo.valor_estimado) if articulo.valor_estimado else None,
        }

    return InventarioDetalleOut(
        id_inventario=inventario.id_inventario,
        id_articulo=inventario.id_articulo,
        estado=estado_nombre,
        precio_base=float(inventario.precio_base),
        precio_actual=float(inventario.precio_actual),
        dias_en_bodega=inventario.dias_en_bodega,
        fecha_ingreso=inventario.fecha_ingreso,
        articulo=articulo_data,
        ultima_modificacion=None,
    )


# ============================================================
# PATCH - ACTUALIZAR (precio, estado)
# Permisos: ADMINISTRADOR, SUPERVISOR
# ============================================================
@router.patch(
    "/{id_inventario}",
    response_model=InventarioActualizarOut,
    summary="Actualizar inventario (precio, estado)",
    description="**Permisos:** ADMINISTRADOR, SUPERVISOR"
)
async def actualizar_inventario(
    id_inventario: int,
    payload: InventarioActualizarIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Permisos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "SUPERVISOR"]):
        raise HTTPException(status_code=403, detail="Requiere rol ADMINISTRADOR o SUPERVISOR")

    # Cargar inventario con lock
    result = await db.execute(
        select(InventarioVenta)
        .where(InventarioVenta.id_inventario == id_inventario)
        .with_for_update()
    )
    inventario = result.scalar_one_or_none()
    if not inventario:
        raise HTTPException(status_code=404, detail="Inventario no encontrado")

    # Validar que al menos un campo venga
    if all(getattr(payload, f) is None for f in ["precio_actual", "estado", "nota"]):
        raise HTTPException(status_code=400, detail="Debe enviar al menos un campo a actualizar")

    # Guardar valores anteriores
    result_estado = await db.execute(
        select(EstadoInventario).where(EstadoInventario.id_estado_inventario == inventario.id_estado)
    )
    estado_anterior = result_estado.scalar_one_or_none()
    
    valores_anteriores = {
        "precio_actual": float(inventario.precio_actual),
        "estado": estado_anterior.nombre if estado_anterior else None,
    }

    # Aplicar cambios
    cambios = {}

    if payload.precio_actual is not None:
        inventario.precio_actual = payload.precio_actual
        cambios["precio_actual"] = float(payload.precio_actual)

    if payload.estado is not None:
        estado_nuevo = await _obtener_estado_inventario(db, payload.estado)
        inventario.id_estado = estado_nuevo.id_estado_inventario
        cambios["estado"] = estado_nuevo.nombre

    if payload.nota:
        cambios["nota"] = payload.nota

    await db.flush()

    # Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="INVENTARIO_ACTUALIZAR",
        modulo="Inventario",
        detalle=f"Inventario {id_inventario} actualizado",
        valores_anteriores=valores_anteriores,
        valores_nuevos=cambios,
    )

    await db.commit()
    await db.refresh(inventario)

    # Estado final
    result_estado_final = await db.execute(
        select(EstadoInventario).where(EstadoInventario.id_estado_inventario == inventario.id_estado)
    )
    estado_final = result_estado_final.scalar_one_or_none()

    return InventarioActualizarOut(
        id_inventario=inventario.id_inventario,
        estado=estado_final.nombre if estado_final else "desconocido",
        precio_actual=float(inventario.precio_actual),
        dias_en_bodega=inventario.dias_en_bodega,
    )


# ============================================================
# POST - REGISTRAR VENTA
# Permisos: ADMINISTRADOR, SUPERVISOR, CAJERO
# ============================================================
@router.post(
    "/venta",
    response_model=InventarioVentaOut,
    status_code=status.HTTP_200_OK,
    summary="Registrar venta de un artículo del inventario",
    description="**Permisos:** ADMINISTRADOR, SUPERVISOR, CAJERO"
)
async def registrar_venta(
    payload: InventarioVentaIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Permisos
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR", "SUPERVISOR", "CAJERO"]):
        raise HTTPException(status_code=403, detail="Requiere rol ADMINISTRADOR, SUPERVISOR o CAJERO")

    # Cargar inventario con lock
    result = await db.execute(
        select(InventarioVenta)
        .where(InventarioVenta.id_inventario == payload.id_inventario)
        .with_for_update()
    )
    inventario = result.scalar_one_or_none()
    if not inventario:
        raise HTTPException(status_code=404, detail=f"Inventario {payload.id_inventario} no encontrado")

    # Estado actual
    result_estado = await db.execute(
        select(EstadoInventario).where(EstadoInventario.id_estado_inventario == inventario.id_estado)
    )
    estado_actual = result_estado.scalar_one_or_none()
    estado_nombre = estado_actual.nombre.lower() if estado_actual else ""

    # Validación: debe estar disponible o en_venta
    if estado_nombre == "vendido":
        raise HTTPException(status_code=409, detail="El inventario ya está vendido")

    if estado_nombre not in {"disponible", "en_venta"}:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede vender desde estado '{estado_nombre}'"
        )

    # Validar ref_bancaria para transferencia/tarjeta
    medio = (payload.medio_pago or "efectivo").lower()
    if medio in {"transferencia", "tarjeta"} and not payload.ref_bancaria:
        raise HTTPException(status_code=400, detail=f"ref_bancaria requerida para '{medio}'")

    # Estado vendido
    estado_vendido = await _obtener_estado_inventario(db, "vendido")
    fecha_venta = payload.fecha_venta or date.today()

    # Actualizar
    valores_anteriores = {
        "estado": estado_nombre,
        "precio_actual": float(inventario.precio_actual),
    }

    inventario.id_estado = estado_vendido.id_estado_inventario
    inventario.precio_actual = payload.precio_venta
    await db.flush()

    # Comprobante opcional
    if payload.comprobante_url:
        db.add(Comprobante(
            id_inventario=inventario.id_inventario,
            url=str(payload.comprobante_url)
        ))

    # Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="INVENTARIO_VENDER",
        modulo="Inventario",
        detalle=f"Inventario {inventario.id_inventario} vendido por Q{float(payload.precio_venta):.2f}",
        valores_anteriores=valores_anteriores,
        valores_nuevos={
            "estado": "vendido",
            "precio_venta": float(payload.precio_venta),
            "fecha_venta": fecha_venta.isoformat(),
            "medio_pago": medio,
            "comprador": payload.comprador_nombre,
        }
    )

    await db.commit()
    await db.refresh(inventario)

    # Respuesta
    comprador = None
    if payload.comprador_nombre or payload.comprador_nit:
        comprador = CompradorOut(nombre=payload.comprador_nombre, nit=payload.comprador_nit)

    return InventarioVentaOut(
        id_inventario=inventario.id_inventario,
        estado="vendido",
        precio_venta=float(payload.precio_venta),
        fecha_venta=fecha_venta,
        medio_pago=medio,
        ref_bancaria=payload.ref_bancaria,
        comprador=comprador,
        comprobante_url=str(payload.comprobante_url) if payload.comprobante_url else None,
        nota=payload.nota,
    )


# ============================================================
# DELETE - ELIMINAR (solo si no está vendido)
# Permisos: ADMINISTRADOR
# ============================================================
@router.delete(
    "/{id_inventario}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar registro de inventario",
    description="**Permisos:** ADMINISTRADOR únicamente"
)
async def eliminar_inventario(
    id_inventario: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _resolve_user_id(current_user)
    _ensure_id_usuario_attr(current_user)

    # Permisos: solo ADMINISTRADOR
    if not await usuario_tiene_algun_rol(current_user, db, ["ADMINISTRADOR"]):
        raise HTTPException(status_code=403, detail="Requiere rol ADMINISTRADOR")

    # Cargar inventario
    result = await db.execute(
        select(InventarioVenta).where(InventarioVenta.id_inventario == id_inventario)
    )
    inventario = result.scalar_one_or_none()
    if not inventario:
        raise HTTPException(status_code=404, detail="Inventario no encontrado")

    # Validar estado: NO eliminar si está vendido
    result_estado = await db.execute(
        select(EstadoInventario).where(EstadoInventario.id_estado_inventario == inventario.id_estado)
    )
    estado = result_estado.scalar_one_or_none()
    if estado and estado.nombre.lower() == "vendido":
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar un inventario vendido"
        )

    # Guardar datos para auditoría
    valores_anteriores = {
        "id_inventario": inventario.id_inventario,
        "id_articulo": inventario.id_articulo,
        "estado": estado.nombre if estado else None,
        "precio_base": float(inventario.precio_base),
        "precio_actual": float(inventario.precio_actual),
    }

    # Eliminar comprobantes asociados
    await db.execute(
        delete(Comprobante).where(Comprobante.id_inventario == id_inventario)
    )

    # Eliminar inventario
    await db.delete(inventario)

    # Auditoría
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="INVENTARIO_ELIMINAR",
        modulo="Inventario",
        detalle=f"Inventario {id_inventario} eliminado (artículo {inventario.id_articulo})",
        valores_anteriores=valores_anteriores,
        valores_nuevos=None,
    )

    await db.commit()
    return None