# app/api/routers/procesar_incumplidos.py
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.core.security import get_current_user

# Modelos
from app.db.models.prestamo import Prestamo
from app.db.models.estado_prestamo import EstadoPrestamo
from app.db.models.articulo import Articulo
from app.db.models.estado_articulo import EstadoArticulo
from app.db.models.inventario_venta import InventarioVenta
from app.db.models.estado_inventario import EstadoInventario
from app.db.models.configuraciones_generales import ConfiguracionesGenerales
from app.db.models.user import User

# Schemas
from app.schemas.procesar_incumplidos import (
    ProcesarIncumplidosIn,
    ProcesarIncumplidosOut,
    ProcesarIncumplidosItem
)

# Utilidades
from app.utils.auditoria import registrar_auditoria
from app.utils.roles import usuario_tiene_algun_rol


router = APIRouter(prefix="/prestamos", tags=["Préstamos - Procesar Incumplidos"])


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


async def _obtener_config_int(
    db: AsyncSession,
    clave: str,
    default: int
) -> int:
    """Obtiene un valor de configuración como int."""
    result = await db.execute(
        select(ConfiguracionesGenerales).where(
            func.lower(ConfiguracionesGenerales.clave) == clave.lower()
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        return default
    try:
        return int(config.valor)
    except (ValueError, TypeError):
        return default


async def _obtener_estado_prestamo(
    db: AsyncSession,
    nombre: str
) -> EstadoPrestamo | None:
    """Obtiene un estado de préstamo por nombre (case-insensitive)."""
    res = await db.execute(
        select(EstadoPrestamo).where(
            func.lower(EstadoPrestamo.nombre) == nombre.lower()
        )
    )
    return res.scalar_one_or_none()


async def _obtener_estado_articulo(
    db: AsyncSession,
    nombre: str
) -> EstadoArticulo | None:
    """Obtiene un estado de artículo por nombre (case-insensitive)."""
    res = await db.execute(
        select(EstadoArticulo).where(
            func.lower(EstadoArticulo.nombre) == nombre.lower()
        )
    )
    return res.scalar_one_or_none()


async def _obtener_estado_inventario(
    db: AsyncSession,
    nombre: str
) -> EstadoInventario | None:
    """Obtiene un estado de inventario por nombre (case-insensitive)."""
    res = await db.execute(
        select(EstadoInventario).where(
            func.lower(EstadoInventario.nombre) == nombre.lower()
        )
    )
    return res.scalar_one_or_none()


async def _es_estado_inventario(
    db: AsyncSession,
    id_estado_articulo: int
) -> bool:
    """
    Verifica si el estado del artículo YA corresponde a inventario/venta/vendido.
    Evita 'downgrade' de 'en_venta' o 'vendido' a 'en_inventario'.
    """
    res = await db.execute(
        select(EstadoArticulo).where(
            EstadoArticulo.id_estado_articulo == id_estado_articulo
        )
    )
    estado = res.scalar_one_or_none()
    if not estado:
        return False
    return estado.nombre.lower() in {"en_inventario", "en_venta", "vendido"}


def _to_decimal_seguro(raw) -> Decimal:
    """
    Convierte valor_aprobado (VARCHAR en BD) a Decimal sin reventar.
    Si viene None o texto no numérico, devuelve 0.00
    """
    if raw is None:
        return Decimal("0.00")
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _normalizar_nombre_estado_prestamo(nombre: str) -> str:
    """
    Normaliza nombres legados a los nombres oficiales del catálogo.
    - 'incumplido' → 'incobrable'
    - 'en_mora'    → 'en_mora_parcial'
    """
    n = (nombre or "").strip().lower()
    if n == "incumplido":
        return "incobrable"
    if n == "en_mora":
        return "en_mora_parcial"
    return n


# ============================================================
# ENDPOINT PRINCIPAL
# ============================================================
@router.post(
    "/procesar-incumplidos",
    response_model=ProcesarIncumplidosOut,
    status_code=status.HTTP_200_OK,
    summary="Procesar préstamos incobrables y trasladar artículos al inventario (masivo)",
    description=(
        "Detecta todos los préstamos que cumplen condición de incobrables según fechas y saldos, "
        "y traslada automáticamente sus artículos al inventario. "
        "\n\n**Proceso:**\n"
        "1. Filtra préstamos en estado 'incobrable' con deuda activa\n"
        "2. Valida que superaron el umbral de días (vencimiento + gracia + umbral)\n"
        "3. Mueve artículos a estado de artículo 'en_inventario'\n"
        "4. (Opcional) Crea registros en Inventario_Venta con estado 'disponible'\n"
        "5. Registra auditoría completa\n"
        "\n**Idempotente**: ejecutar varias veces el mismo día no duplica inventario."
    )
)
async def procesar_prestamos_incumplidos(
    payload: ProcesarIncumplidosIn = Body(default=ProcesarIncumplidosIn()),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Procesa préstamos **incobrables** y traslada sus artículos al inventario.
    No modifica estructura de BD. Solo opera con registros existentes.
    """
    # 1) Verificar permisos
    user_id = _resolve_user_id(current_user)
    if not hasattr(current_user, "id_usuario"):
        setattr(current_user, "id_usuario", user_id)

    roles_permitidos = ["ADMIN", "OPERADOR"]
    tiene_permiso = await usuario_tiene_algun_rol(current_user, db, roles_permitidos)
    if not tiene_permiso:
        raise HTTPException(
            status_code=403,
            detail=f"Requiere uno de estos roles: {', '.join(roles_permitidos)}"
        )

    # 2) Fecha de corte
    fecha_corte = payload.fecha_corte or date.today()

    # 3) Configuraciones (si vienen en DB se usan; si no, defaults del payload)
    dias_gracia = (
        payload.dias_gracia if payload.dias_gracia is not None
        else await _obtener_config_int(db, "GRACIA_DIAS", 3)
    )
    umbral_incumplido_dias = (
        payload.umbral_incumplido_dias if payload.umbral_incumplido_dias is not None
        else await _obtener_config_int(db, "UMBRAL_INCUMPLIDO_DIAS", 15)
    )
    dias_totales = dias_gracia + umbral_incumplido_dias

    # 4) Estados requeridos (prestamo = incobrable; articulo = en_inventario; inventario = disponible)
    #    Aceptamos el nombre legado 'incumplido' y lo normalizamos a 'incobrable'
    nombre_estado_prestamo = _normalizar_nombre_estado_prestamo(
        getattr(payload, "estado_prestamo_incumplido", "incobrable")
    )
    if nombre_estado_prestamo != "incobrable":
        # Forzamos el estado objetivo a 'incobrable' para coherencia del flujo
        nombre_estado_prestamo = "incobrable"

    estado_prestamo_incobrable = await _obtener_estado_prestamo(db, nombre_estado_prestamo)
    if not estado_prestamo_incobrable:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de préstamo '{nombre_estado_prestamo}' no existe en catálogo"
        )

    # Estado de ARTÍCULO al pasar a inventario
    nombre_estado_art_objetivo = getattr(payload, "estado_articulo_inventario", "en_inventario")
    estado_art_inventario = await _obtener_estado_articulo(db, nombre_estado_art_objetivo)
    if not estado_art_inventario:
        raise HTTPException(
            status_code=500,
            detail=f"Estado de artículo '{nombre_estado_art_objetivo}' no existe en catálogo (debe existir)."
        )

    estado_inv_disponible = None
    if payload.insertar_en_tabla_inventario:
        estado_inv_disponible = await _obtener_estado_inventario(db, "disponible")
        if not estado_inv_disponible:
            raise HTTPException(
                status_code=500,
                detail="Estado de inventario 'disponible' no existe en catálogo"
            )

    # 5) Seleccionar préstamos candidatos por estado y deuda
    res = await db.execute(
        select(Prestamo).where(
            Prestamo.id_estado == estado_prestamo_incobrable.id_estado_prestamo,
            Prestamo.deuda_actual > 0
        )
    )
    prestamos_candidatos = res.scalars().all()

    # Filtrar por frontera de fecha en Python
    prestamos_filtrados: List[Prestamo] = []
    for p in prestamos_candidatos:
        # p.fecha_vencimiento debe existir
        if not getattr(p, "fecha_vencimiento", None):
            continue
        frontera = p.fecha_vencimiento + timedelta(days=dias_totales)
        if fecha_corte > frontera:
            prestamos_filtrados.append(p)

    total_candidatos = len(prestamos_filtrados)

    # 6) Procesar cada préstamo/artículo
    trasladados = 0
    omitidos = 0
    errores = 0
    detalle: List[ProcesarIncumplidosItem] = []

    for prestamo in prestamos_filtrados:
        try:
            # Lock del artículo para evitar carreras
            res_art = await db.execute(
                select(Articulo)
                .where(Articulo.id_articulo == prestamo.id_articulo)
                .with_for_update()
            )
            articulo = res_art.scalar_one_or_none()

            if not articulo:
                errores += 1
                detalle.append(ProcesarIncumplidosItem(
                    id_prestamo=prestamo.id_prestamo,
                    id_articulo=prestamo.id_articulo,
                    accion="omitido",
                    motivo="Artículo no encontrado"
                ))
                continue

            # Si ya está en inventario/venta/vendido => omitir (idempotencia real)
            if await _es_estado_inventario(db, articulo.id_estado):
                omitidos += 1
                detalle.append(ProcesarIncumplidosItem(
                    id_prestamo=prestamo.id_prestamo,
                    id_articulo=articulo.id_articulo,
                    accion="omitido",
                    motivo="Artículo ya está en inventario/venta/vendido"
                ))
                continue

            # a) Actualizar estado del artículo -> en_inventario
            articulo.id_estado = estado_art_inventario.id_estado_articulo

            # b) Insertar en Inventario_Venta (si aplica) sólo si no existe uno previo
            if payload.insertar_en_tabla_inventario:
                res_inv = await db.execute(
                    select(InventarioVenta).where(
                        InventarioVenta.id_articulo == articulo.id_articulo
                    )
                )
                inv_existente = res_inv.scalar_one_or_none()

                if not inv_existente:
                    # valor_aprobado en BD es VARCHAR → convertir seguro a Decimal
                    precio_base = _to_decimal_seguro(getattr(articulo, "valor_aprobado", None))

                    nuevo_inventario = InventarioVenta(
                        id_articulo=articulo.id_articulo,
                        id_estado=estado_inv_disponible.id_estado_inventario,
                        precio_base=precio_base,
                        precio_actual=precio_base,
                        dias_en_bodega=0,
                        fecha_ingreso=fecha_corte
                    )
                    db.add(nuevo_inventario)

            # c) Auditoría por artículo movido
            await registrar_auditoria(
                db=db,
                usuario_id=user_id,
                accion="ARTICULO_A_INVENTARIO_POR_INCOBRABLE",
                modulo="Inventario",
                detalle=(
                    f"Artículo {articulo.id_articulo} movido a inventario. "
                    f"Préstamo {prestamo.id_prestamo} superó {umbral_incumplido_dias} días "
                    f"tras período de gracia ({dias_gracia} días)"
                ),
                valores_nuevos={
                    "id_articulo": articulo.id_articulo,
                    "id_prestamo": prestamo.id_prestamo,
                    "fecha_ingreso": fecha_corte.isoformat(),
                    "ubicacion": getattr(payload, "ubicacion_default", None)
                }
            )

            trasladados += 1
            detalle.append(ProcesarIncumplidosItem(
                id_prestamo=prestamo.id_prestamo,
                id_articulo=articulo.id_articulo,
                accion="trasladado",
                motivo=f"Superó {umbral_incumplido_dias} días después del período de gracia",
                fecha_ingreso=fecha_corte
            ))

        except Exception as e:
            errores += 1
            # rollback de la unidad de trabajo del ítem y seguir
            await db.rollback()
            detalle.append(ProcesarIncumplidosItem(
                id_prestamo=prestamo.id_prestamo,
                id_articulo=prestamo.id_articulo,
                accion="omitido",
                motivo=f"Error: {str(e)}"
            ))
            continue

    # 7) Auditoría consolidada
    await registrar_auditoria(
        db=db,
        usuario_id=user_id,
        accion="PROCESAR_INCOBRABLES_MASIVO",
        modulo="Prestamo",
        detalle=(
            f"Procesamiento masivo de incobrables del {fecha_corte.isoformat()}. "
            f"Candidatos: {total_candidatos}, Trasladados: {trasladados}, "
            f"Omitidos: {omitidos}, Errores: {errores}"
        ),
        valores_nuevos={
            "fecha_corte": fecha_corte.isoformat(),
            "dias_gracia": dias_gracia,
            "umbral_incumplido_dias": umbral_incumplido_dias,
            "total_candidatos": total_candidatos,
            "articulos_trasladados": trasladados,
            "ya_en_inventario": omitidos,
            "errores": errores
        }
    )

    # 8) Commit final
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al confirmar transacción: {str(e)}"
        )

    # 9) Respuesta
    return ProcesarIncumplidosOut(
        total_candidatos=total_candidatos,
        articulos_trasladados=trasladados,
        prestamos_actualizados=trasladados,  # préstamos impactados
        ya_en_inventario=omitidos,
        errores=errores,
        detalle=detalle
    )
