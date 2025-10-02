"""
API de Catálogos (lectura)
Expone todos los catálogos básicos de la aplicación para que el frontend
y la app móvil puedan llenar formularios y listas sin depender de valores escritos a mano.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.db.models import (
    CatTipoArticulo,
    EstadoSolicitud,
    EstadoArticulo,
    EstadoPrestamo,
    EstadoPago,
    EstadoInventario,
)

router = APIRouter(prefix="/catalogos", tags=["catalogos"])


# ========== A) Bootstrap (todos los catálogos en una sola respuesta) ==========
@router.get("/bootstrap", summary="Devuelve todas las listas juntas")
async def bootstrap_catalogos(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Endpoint bootstrap: devuelve todos los catálogos en una sola respuesta.
    Evita múltiples llamadas cuando el frontend carga inicialmente.
    """
    # 1. Métodos de entrega (constantes, no requieren BD)
    metodos_entrega = ["domicilio", "oficina"]

    # 2. Condiciones del artículo (constantes)
    condiciones_articulo = ["nuevo", "seminuevo", "usado", "malo"]

    # 3. Tipos de artículo (BD)
    result_tipos = await db.execute(
        select(CatTipoArticulo.id_tipo, CatTipoArticulo.nombre).order_by(CatTipoArticulo.nombre)
    )
    tipos_articulo = [{"id": row[0], "nombre": row[1]} for row in result_tipos.all()]

    # 4. Estados de solicitud (BD)
    result_sol = await db.execute(
        select(EstadoSolicitud.id_estado_solicitud, EstadoSolicitud.nombre).order_by(EstadoSolicitud.nombre)
    )
    estados_solicitud = [{"id": row[0], "nombre": row[1]} for row in result_sol.all()]

    # 5. Estados de artículo (BD)
    result_art = await db.execute(
        select(EstadoArticulo.id_estado_articulo, EstadoArticulo.nombre).order_by(EstadoArticulo.nombre)
    )
    estados_articulo = [{"id": row[0], "nombre": row[1]} for row in result_art.all()]

    # 6. Estados de préstamo (BD)
    result_pres = await db.execute(
        select(EstadoPrestamo.id_estado_prestamo, EstadoPrestamo.nombre).order_by(EstadoPrestamo.nombre)
    )
    estados_prestamo = [{"id": row[0], "nombre": row[1]} for row in result_pres.all()]

    # 7. Estados de pago (BD)
    result_pago = await db.execute(
        select(EstadoPago.id_estado_pago, EstadoPago.nombre).order_by(EstadoPago.nombre)
    )
    estados_pago = [{"id": row[0], "nombre": row[1]} for row in result_pago.all()]

    # 8. Estados de inventario (BD)
    result_inv = await db.execute(
        select(EstadoInventario.id_estado_inventario, EstadoInventario.nombre).order_by(EstadoInventario.nombre)
    )
    estados_inventario = [{"id": row[0], "nombre": row[1]} for row in result_inv.all()]

    # Validación: si algún catálogo está vacío, retornar 200 OK pero con lista vacía
    # Esto evita que el frontend falle; simplemente mostrará "sin datos"
    return {
        "metodos_entrega": metodos_entrega,
        "condiciones_articulo": condiciones_articulo,
        "tipos_articulo": tipos_articulo,
        "estados": {
            "solicitud": estados_solicitud,
            "articulo": estados_articulo,
            "prestamo": estados_prestamo,
            "pago": estados_pago,
            "inventario": estados_inventario,
        },
    }


# ========== B) Catálogos individuales (uno por vez) ==========
@router.get("/tipos_articulo", summary="Obtener tipos de artículo")
async def obtener_tipos_articulo(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los tipos de artículo disponibles (Electrónica, Joyería, etc.)"""
    result = await db.execute(
        select(CatTipoArticulo.id_tipo, CatTipoArticulo.nombre).order_by(CatTipoArticulo.nombre)
    )
    rows = result.all()
    if not rows:
        # Si la tabla está vacía, devolver 200 OK con lista vacía (no es error)
        return []
    return [{"id": row[0], "nombre": row[1]} for row in rows]


@router.get("/estados/solicitud", summary="Obtener estados de solicitud")
async def obtener_estados_solicitud(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los estados de solicitud (pendiente, evaluada, rechazada, etc.)"""
    result = await db.execute(
        select(EstadoSolicitud.id_estado_solicitud, EstadoSolicitud.nombre).order_by(EstadoSolicitud.nombre)
    )
    rows = result.all()
    if not rows:
        return []
    return [{"id": row[0], "nombre": row[1]} for row in rows]


@router.get("/estados/articulo", summary="Obtener estados de artículo")
async def obtener_estados_articulo(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los estados de artículo (pendiente, avaluado, etc.)"""
    result = await db.execute(
        select(EstadoArticulo.id_estado_articulo, EstadoArticulo.nombre).order_by(EstadoArticulo.nombre)
    )
    rows = result.all()
    if not rows:
        return []
    return [{"id": row[0], "nombre": row[1]} for row in rows]


@router.get("/estados/prestamo", summary="Obtener estados de préstamo")
async def obtener_estados_prestamo(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los estados de préstamo (activo, pagado, vencido, etc.)"""
    result = await db.execute(
        select(EstadoPrestamo.id_estado_prestamo, EstadoPrestamo.nombre).order_by(EstadoPrestamo.nombre)
    )
    rows = result.all()
    if not rows:
        return []
    return [{"id": row[0], "nombre": row[1]} for row in rows]


@router.get("/estados/pago", summary="Obtener estados de pago")
async def obtener_estados_pago(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los estados de pago (pendiente, validado, rechazado, etc.)"""
    result = await db.execute(
        select(EstadoPago.id_estado_pago, EstadoPago.nombre).order_by(EstadoPago.nombre)
    )
    rows = result.all()
    if not rows:
        return []
    return [{"id": row[0], "nombre": row[1]} for row in rows]


@router.get("/estados/inventario", summary="Obtener estados de inventario")
async def obtener_estados_inventario(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los estados de inventario (disponible, en_venta, vendido, etc.)"""
    result = await db.execute(
        select(EstadoInventario.id_estado_inventario, EstadoInventario.nombre).order_by(EstadoInventario.nombre)
    )
    rows = result.all()
    if not rows:
        return []
    return [{"id": row[0], "nombre": row[1]} for row in rows]


# ========== También puedes usar un patrón genérico (opcional) ==========
@router.get("/{nombre}", summary="Patrón genérico para obtener catálogos")
async def obtener_catalogo_generico(nombre: str, db: AsyncSession = Depends(get_db)):
    """
    Endpoint genérico que permite obtener catálogos usando un patrón:
    GET /catalogos/tipos_articulo
    GET /catalogos/estados_solicitud
    etc.
    
    Ejemplos de {nombre}: tipos_articulo, estados_solicitud, estados_articulo, etc.
    """
    # Mapeo de nombres a modelos y columnas
    CATALOGOS = {
        "tipos_articulo": (CatTipoArticulo, CatTipoArticulo.id_tipo, CatTipoArticulo.nombre),
        "estados_solicitud": (EstadoSolicitud, EstadoSolicitud.id_estado_solicitud, EstadoSolicitud.nombre),
        "estados_articulo": (EstadoArticulo, EstadoArticulo.id_estado_articulo, EstadoArticulo.nombre),
        "estados_prestamo": (EstadoPrestamo, EstadoPrestamo.id_estado_prestamo, EstadoPrestamo.nombre),
        "estados_pago": (EstadoPago, EstadoPago.id_estado_pago, EstadoPago.nombre),
        "estados_inventario": (EstadoInventario, EstadoInventario.id_estado_inventario, EstadoInventario.nombre),
    }

    # Validar que el catálogo exista
    if nombre not in CATALOGOS:
        raise HTTPException(status_code=404, detail=f"Catálogo '{nombre}' no encontrado")

    # Obtener modelo y columnas
    model, id_col, name_col = CATALOGOS[nombre]

    # Consultar BD
    result = await db.execute(select(id_col, name_col).order_by(name_col))
    rows = result.all()

    # Devolver lista vacía si no hay datos (200 OK)
    if not rows:
        return []

    return [{"id": row[0], "nombre": row[1]} for row in rows]