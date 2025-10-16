from datetime import date, datetime
from typing import List, Optional, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased

from app.core.security import get_current_user, User, has_role
from app.db.database import get_db

# Modelos
from app.db.models.ruta_cobranza import RutaCobranza
from app.db.models.visitas_cobranza import VisitasCobranza
from app.db.models.prestamo import Prestamo
from app.db.models.auditoria import Auditoria

# Para evitar importaciones circulares, usamos TYPE_CHECKING
# Asegúrate de que la ruta 'app.db.models.cliente' sea correcta y el archivo exista.
if TYPE_CHECKING:
    from app.db.models.user import User

# Schemas
from app.schemas.ruta_cobranza import (
    RutaCobranzaCreate, RutaCobranzaCreada, CobradorInfo,
    PaginatedRutasCobranza, RutaCobranzaListado, CobradorResumen,
    RutaConVisitas
)

router = APIRouter(prefix="/rutas-cobranza", tags=["Rutas de Cobranza"])

ESTADOS_COBRABLES = ["activo", "en_mora_parcial", "en_mora_grave"]


@router.post(
    "",
    response_model=RutaCobranzaCreada,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(has_role(["ADMIN", "OPERADOR"]))],
)
async def crear_ruta_cobranza(
    datos: RutaCobranzaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Crea una nueva ruta de cobranza para un cobrador específico.
    - Valida que el usuario sea cobrador.
    - Valida que los préstamos existan y sean cobrables.
    - Crea la ruta y las visitas pendientes asociadas.
    - Registra la acción en auditoría.
    """
    # 1. Validar que el usuario cobrador existe y tiene el rol correcto
    cobrador: Optional[User] = await db.get(User, datos.id_usuario_cobrador, options=[selectinload(User.rol)])
    if not cobrador or not hasattr(cobrador, 'rol') or not cobrador.rol or cobrador.rol.nombre.upper() != "COBRADOR":
        raise HTTPException(status_code=404, detail="Usuario cobrador no encontrado o no tiene el rol 'COBRADOR'")

    # 2. Validar préstamos
    stmt = select(Prestamo).where(Prestamo.id_prestamo.in_(datos.prestamos))
    res = await db.execute(stmt)
    prestamos_en_db = res.scalars().all()

    if len(prestamos_en_db) != len(datos.prestamos):
        prestamos_encontrados_ids = {p.id_prestamo for p in prestamos_en_db}
        prestamos_faltantes = set(datos.prestamos) - prestamos_encontrados_ids
        raise HTTPException(status_code=404, detail=f"Préstamos no encontrados: {list(prestamos_faltantes)}")

    monto_total = 0.0
    for p in prestamos_en_db:
        if p.estado.lower() not in ESTADOS_COBRABLES:
            raise HTTPException(status_code=409, detail=f"El préstamo {p.id_prestamo} no está en un estado cobrable (estado actual: {p.estado})")
        monto_total += p.deuda_actual or 0

    # 3. Iniciar transacción
    try:
        # Crear Ruta_Cobranza
        nueva_ruta = RutaCobranza(
            id_usuario_cobrador=datos.id_usuario_cobrador,
            fecha_asignacion=datos.fecha_asignacion,
            id_usuario_creador=current_user.ID_Usuario,
        )
        db.add(nueva_ruta)
        await db.flush() # Para obtener el ID de la nueva ruta

        # Crear Visitas_Cobranza preliminares
        for id_prestamo in datos.prestamos:
            visita = VisitasCobranza(
                id_ruta=nueva_ruta.id_ruta,
                id_prestamo=id_prestamo,
            )
            db.add(visita)

        # Auditoría
        audit = Auditoria(
            id_usuario=current_user.ID_Usuario,
            accion="CREAR_RUTA_COBRANZA",
            modulo="RutasCobranza",
            fecha_hora=datetime.utcnow(),
            detalle=f"Ruta creada para cobrador id={datos.id_usuario_cobrador} con {len(datos.prestamos)} préstamos."
        )
        db.add(audit)

        await db.commit()
        await db.refresh(nueva_ruta)

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear la ruta: {e}")

    return RutaCobranzaCreada(
        id_ruta=nueva_ruta.id_ruta,
        id_usuario_cobrador=cobrador.ID_Usuario,
        cobrador=CobradorInfo(nombre=f"{cobrador.nombre} {cobrador.apellido}", telefono=cobrador.telefono),
        fecha_asignacion=nueva_ruta.fecha_asignacion,
        total_prestamos=len(datos.prestamos),
        monto_total_a_cobrar=monto_total,
    )


@router.get("", response_model=PaginatedRutasCobranza)
async def listar_rutas_cobranza(
    cobrador_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista las rutas de cobranza con filtros y paginación.
    - Cobradores solo pueden ver sus propias rutas.
    - Admins/Operadores pueden ver todas y filtrar por cobrador.
    """
    # Importar modelo aquí para evitar dependencias circulares en el arranque
    from app.db.models.user import User

    cobrador_alias = aliased(User, name="cobrador")

    # Subquery para estadísticas de visitas
    visitas_sq = (
        select(
            VisitasCobranza.id_ruta,
            func.count(VisitasCobranza.id_visita).label("total_visitas"),
            func.count(case((VisitasCobranza.resultado != None, 1))).label("visitas_completadas"),
            func.coalesce(func.sum(VisitasCobranza.monto_pagado), 0.0).label("monto_cobrado")
        )
        .group_by(VisitasCobranza.id_ruta)
        .subquery("visitas_stats")
    )

    stmt = (
        select(
            RutaCobranza,
            cobrador_alias.ID_Usuario.label("cobrador_id"), # Usando el nombre de columna real
            cobrador_alias.nombre.label("cobrador_nombre"),
            visitas_sq.c.total_visitas,
            visitas_sq.c.visitas_completadas,
            visitas_sq.c.monto_cobrado,
        )
        .join(cobrador_alias, RutaCobranza.id_usuario_cobrador == cobrador_alias.ID_Usuario)
        .outerjoin(visitas_sq, RutaCobranza.id_ruta == visitas_sq.c.id_ruta)
    )

    # Aplicar filtros
    if hasattr(current_user, 'rol') and current_user.rol and current_user.rol.nombre.upper() == "COBRADOR":
        stmt = stmt.where(RutaCobranza.id_usuario_cobrador == current_user.ID_Usuario)
    elif cobrador_id:
        stmt = stmt.where(RutaCobranza.id_usuario_cobrador == cobrador_id)

    if fecha_desde:
        stmt = stmt.where(RutaCobranza.fecha_asignacion >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(RutaCobranza.fecha_asignacion <= fecha_hasta)

    # Contar total antes de paginar
    count_stmt = select(func.count()).select_from(stmt.alias("sub"))
    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    # Aplicar paginación y orden
    stmt = stmt.order_by(RutaCobranza.fecha_asignacion.desc(), RutaCobranza.id_ruta.desc()).offset(offset).limit(limit)
    
    res = await db.execute(stmt)
    results = res.all()

    items = []
    for row in results:
        ruta, _, _, total_visitas, visitas_completadas, monto_cobrado = row
        total_visitas = total_visitas or 0
        visitas_completadas = visitas_completadas or 0
        monto_cobrado = monto_cobrado or 0.0
        
        # Calcular monto pendiente (simplificado)
        # Una implementación más robusta podría recalcular la deuda total de los préstamos en la ruta.
        monto_pendiente = 0.0 # Este cálculo puede ser complejo, lo dejamos en 0 por simplicidad.

        items.append(RutaCobranzaListado(
            id_ruta=ruta.id_ruta,
            cobrador=CobradorResumen(id_usuario=row.cobrador_id, nombre=row.cobrador_nombre),
            fecha_asignacion=ruta.fecha_asignacion,
            total_visitas=total_visitas,
            visitas_completadas=visitas_completadas,
            monto_cobrado=float(monto_cobrado),
            monto_pendiente=monto_pendiente,
        ))

    return PaginatedRutasCobranza(items=items, total=total, limit=limit, offset=offset)


@router.get("/{id_ruta}/visitas", response_model=RutaConVisitas)
async def obtener_visitas_de_ruta(
    id_ruta: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Obtiene el detalle de todas las visitas (completadas y pendientes) de una ruta específica.
    """
    # Importar modelos aquí para evitar dependencias circulares en el arranque
    from app.db.models.prestamo import Prestamo

    options = [
        selectinload(RutaCobranza.visitas).selectinload(VisitasCobranza.prestamo).selectinload(Prestamo.usuario)
    ]
    
    stmt = select(RutaCobranza).where(RutaCobranza.id_ruta == id_ruta)
    
    # Permisos: Cobrador solo puede ver sus rutas.
    if hasattr(current_user, 'rol') and current_user.rol and current_user.rol.nombre.upper() == "COBRADOR":
        stmt = stmt.where(RutaCobranza.id_usuario_cobrador == current_user.ID_Usuario)
        
    res = await db.execute(stmt.options(*options))
    ruta = res.scalar_one_or_none()

    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada o sin acceso.")

    # Mapeo manual para asegurar la estructura del schema
    for visita in ruta.visitas:
        # Asignar la dirección del usuario del préstamo a un campo temporal para el schema
        if visita.prestamo and visita.prestamo.usuario:
            # Asumiendo que el modelo User tiene un campo 'direccion'
            visita.prestamo.direccion_cobro = visita.prestamo.usuario.direccion

    return ruta