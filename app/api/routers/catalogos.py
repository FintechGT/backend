# -*- coding: utf-8 -*-
"""
API de Catálogos (Lectura)
========================
Endpoints para exponer los catálogos básicos de la aplicación.
Los catálogos permiten que el frontend y la app móvil puedan llenar formularios
y listas sin depender de valores escritos a mano.

Características:
- No requiere autenticación (es pública)
- Se puede cachear en el cliente por algunos minutos
- Devuelve listas vacías con 200 OK si no hay datos
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.estado_pago import EstadoPago
from app.db.models.estado_inventario import EstadoInventario
from app.schemas.catalogos import (
    MetodoEntregaOut,
    CondicionArticuloOut,
    TipoArticuloOut,
    EstadoSolicitudOut,
    EstadoArticuloOut,
    EstadoPrestamoOut,
    EstadoPagoOut,
    EstadoInventarioOut,
    CatalogosBootstrapOut,
    CatalogoVacioOut
)

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])


# ========== CATÁLOGOS ESTÁTICOS (CONSTANTES) ==========

def get_metodos_entrega() -> List[MetodoEntregaOut]:
    """Devuelve los métodos de entrega disponibles (constante)"""
    return [
        MetodoEntregaOut(valor="domicilio", etiqueta="Domicilio"),
        MetodoEntregaOut(valor="oficina", etiqueta="Oficina")
    ]


def get_condiciones_articulo() -> List[CondicionArticuloOut]:
    """Devuelve las condiciones del artículo disponibles (constante)"""
    return [
        CondicionArticuloOut(valor="nuevo", etiqueta="Nuevo"),
        CondicionArticuloOut(valor="seminuevo", etiqueta="Seminuevo"),
        CondicionArticuloOut(valor="usado", etiqueta="Usado"),
        CondicionArticuloOut(valor="malo", etiqueta="Malo")
    ]


# ========== A) ENDPOINT BOOTSTRAP (TODOS LOS CATÁLOGOS) ==========

@router.get(
    "/bootstrap",
    response_model=CatalogosBootstrapOut,
    summary="Obtener todos los catálogos en una sola respuesta",
    description="Devuelve todos los catálogos básicos de la aplicación para que el frontend "
                "y la app móvil puedan llenar formularios y listas sin depender de valores escritos a mano."
)
async def get_catalogos_bootstrap(
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint Bootstrap: Devuelve todos los catálogos en una sola respuesta.
    
    Reglas de negocio:
    - Si un catálogo está vacío en la BD, devuelve lista vacía (no falla)
    - Los registros se devuelven ordenados por nombre, incluyendo solo id y nombre
    - Se puede cachear en cliente por algunos minutos
    """
    
    # Configurar cache header (5 minutos)
    response.headers["Cache-Control"] = "public, max-age=300"
    
    # Obtener catálogos estáticos
    metodos_entrega = get_metodos_entrega()
    condiciones_articulo = get_condiciones_articulo()
    
    # Obtener catálogos desde BD con manejo de errores
    try:
        # Tipos de artículo
        result_tipos = await db.execute(
            select(CatTipoArticulo).order_by(CatTipoArticulo.nombre)
        )
        tipos_db = result_tipos.scalars().all()
        tipos_articulo = [
            TipoArticuloOut(id_tipo=t.id_tipo, nombre=t.nombre)
            for t in tipos_db
        ]

        # Estados de solicitud
        result_estados_sol = await db.execute(
            select(EstadoSolicitud).order_by(EstadoSolicitud.nombre)
        )
        estados_sol_db = result_estados_sol.scalars().all()
        estados_solicitud = [
            EstadoSolicitudOut(id_estado=e.id_estado_solicitud, nombre=e.nombre)
            for e in estados_sol_db
        ]

        # Estados de artículo
        result_estados_art = await db.execute(
            select(EstadoArticulo).order_by(EstadoArticulo.nombre)
        )
        estados_art_db = result_estados_art.scalars().all()
        estados_articulo = [
            EstadoArticuloOut(id_estado=e.id_estado_articulo, nombre=e.nombre)
            for e in estados_art_db
        ]

        # Estados de préstamo
        result_estados_prest = await db.execute(
            select(EstadoPrestamo).order_by(EstadoPrestamo.nombre)
        )
        estados_prest_db = result_estados_prest.scalars().all()
        estados_prestamo = [
            EstadoPrestamoOut(id_estado=e.id_estado_prestamo, nombre=e.nombre)
            for e in estados_prest_db
        ]

        # Estados de pago
        result_estados_pago = await db.execute(
            select(EstadoPago).order_by(EstadoPago.nombre)
        )
        estados_pago_db = result_estados_pago.scalars().all()
        estados_pago = [
            EstadoPagoOut(id_estado=e.id_estado_pago, nombre=e.nombre)
            for e in estados_pago_db
        ]

        # Estados de inventario
        result_estados_inv = await db.execute(
            select(EstadoInventario).order_by(EstadoInventario.nombre)
        )
        estados_inv_db = result_estados_inv.scalars().all()
        estados_inventario = [
            EstadoInventarioOut(id_estado=e.id_estado_inventario, nombre=e.nombre)
            for e in estados_inv_db
        ]
    except Exception as e:
        # Manejo de error genérico
        raise HTTPException(status_code=500, detail=f"Error al obtener catálogos: {str(e)}")

    return CatalogosBootstrapOut(
        metodos_entrega=metodos_entrega,
        condiciones_articulo=condiciones_articulo,
        tipos_articulo=tipos_articulo,
        estados_solicitud=estados_solicitud,
        estados_articulo=estados_articulo,
        estados_prestamo=estados_prestamo,
        estados_pago=estados_pago,
        estados_inventario=estados_inventario
    )


# ========== B) ENDPOINTS INDIVIDUALES (UNO POR CATÁLOGO) ==========

@router.get(
    "/metodos-entrega",
    response_model=List[MetodoEntregaOut],
    summary="Obtener catálogo de métodos de entrega"
)
async def get_metodos_entrega_endpoint(response: Response):
    """Devuelve los métodos de entrega disponibles (constante)"""
    response.headers["Cache-Control"] = "public, max-age=300"
    return get_metodos_entrega()


@router.get(
    "/condiciones-articulo",
    response_model=List[CondicionArticuloOut],
    summary="Obtener catálogo de condiciones del artículo"
)
async def get_condiciones_articulo_endpoint(response: Response):
    """Devuelve las condiciones del artículo disponibles (constante)"""
    response.headers["Cache-Control"] = "public, max-age=300"
    return get_condiciones_articulo()


@router.get(
    "/tipos-articulo",
    response_model=List[TipoArticuloOut],
    summary="Obtener catálogo de tipos de artículo"
)
async def get_tipos_articulo(
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Devuelve todos los tipos de artículo ordenados por nombre"""
    response.headers["Cache-Control"] = "public, max-age=300"
    
    result = await db.execute(
        select(CatTipoArticulo).order_by(CatTipoArticulo.nombre)
    )
    tipos = result.scalars().all()
    
    if not tipos:
        return []
    
    return [
        TipoArticuloOut(id_tipo=t.id_tipo, nombre=t.nombre)
        for t in tipos
    ]
async def get_catalogo_generico(
    nombre: str = Path(..., description="Nombre del catálogo a obtener"),
    response: Response = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint genérico para obtener catálogos individuales por nombre.
    
    Catálogos disponibles:
    - metodos_entrega
    - condiciones_articulo
    - tipos_articulo
    - estados_solicitud
    - estados_articulo
    - estados_prestamo
    - estados_pago
    - estados_inventario
    
    También funciona con variantes:
    - Con guiones: estados-solicitud
    - Con puntos: estados.solicitud
    """
    
    # Normalizar el nombre del catálogo
    nombre_normalizado = nombre.lower().replace("-", "_").replace(".", "_")
    
    # Configurar cache
    if response:
        response.headers["Cache-Control"] = "public, max-age=300"
    
    # Router interno para catálogos
    if nombre_normalizado == "metodos_entrega":
        return get_metodos_entrega()
    
    elif nombre_normalizado == "condiciones_articulo":
        return get_condiciones_articulo()
    
    elif nombre_normalizado == "tipos_articulo":
        result = await db.execute(
            select(CatTipoArticulo).order_by(CatTipoArticulo.nombre)
        )
        tipos = result.scalars().all()
        return [
            {"id_tipo": t.id_tipo, "nombre": t.nombre}
            for t in tipos
        ]
    
    elif nombre_normalizado == "estados_solicitud":
        result = await db.execute(
            select(EstadoSolicitud).order_by(EstadoSolicitud.nombre)
        )
        estados = result.scalars().all()
        return [
            {"id_estado": e.id_estado_solicitud, "nombre": e.nombre}
            for e in estados
        ]
    
    elif nombre_normalizado == "estados_articulo":
        result = await db.execute(
            select(EstadoArticulo).order_by(EstadoArticulo.nombre)
        )
        estados = result.scalars().all()
        return [
            {"id_estado": e.id_estado_articulo, "nombre": e.nombre}
            for e in estados
        ]
    
    elif nombre_normalizado == "estados_prestamo":
        result = await db.execute(
            select(EstadoPrestamo).order_by(EstadoPrestamo.nombre)
        )
        estados = result.scalars().all()
        return [
            {"id_estado": e.id_estado_prestamo, "nombre": e.nombre}
            for e in estados
        ]
    
    elif nombre_normalizado == "estados_pago":
        result = await db.execute(
            select(EstadoPago).order_by(EstadoPago.nombre)
        )
        estados = result.scalars().all()
        return [
            {"id_estado": e.id_estado_pago, "nombre": e.nombre}
            for e in estados
        ]
    
    elif nombre_normalizado == "estados_inventario":
        result = await db.execute(
            select(EstadoInventario).order_by(EstadoInventario.nombre)
        )
        estados = result.scalars().all()
        return [
            {"id_estado": e.id_estado_inventario, "nombre": e.nombre}
            for e in estados
        ]
    
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Catálogo '{nombre}' no encontrado"
        )