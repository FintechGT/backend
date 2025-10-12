from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime

from app.db.database import get_db
from app.api.deps import get_current_user
from app.schemas.reglas import ReglaArticuloResponse, ReglaArticuloCreate, ReglaArticuloUpdate

# Importar modelos con nombres CORRECTOS
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.regla_tipo_articulo import ReglaTipoArticulo
from app.db.models.auditoria import Auditoria

router = APIRouter(prefix="/reglas", tags=["reglas"])

@router.get("/articulos", response_model=List[ReglaArticuloResponse])
async def listar_reglas_articulos(
    incluir_inactivas: bool = Query(False, description="Incluir reglas inactivas"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Listar todas las reglas vigentes por tipo de artículo
    """
    try:
        # Construir query base - usar nombres correctos de columnas
        query = select(ReglaTipoArticulo, CatTipoArticulo.nombre).join(
            CatTipoArticulo, ReglaTipoArticulo.id_tipo == CatTipoArticulo.id_tipo
        )
        
        if not incluir_inactivas:
            query = query.where(ReglaTipoArticulo.activo == True)
        
        result = await db.execute(query)
        reglas = result.all()
        
        response = []
        for regla, tipo_nombre in reglas:
            response.append(ReglaArticuloResponse(
                id_tipo=regla.id_tipo,
                tipo_nombre=tipo_nombre,
                admite_comprar=bool(regla.admite_comprar),
                admite_recoleccion=bool(regla.admite_recoleccion),
                valor_max_domicilio=float(regla.valor_max_domicilio) if regla.valor_max_domicilio else None,
                requiere_dos_personas=bool(regla.requiere_dos_personas),
                requiere_serie=bool(regla.requiere_serie),
                requiere_prueba=bool(regla.requiere_prueba),
                activo=bool(regla.activo)
            ))
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

@router.get("/articulos/{id_tipo}", response_model=ReglaArticuloResponse)
async def obtener_regla_articulo(
    id_tipo: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Obtener la regla asociada a un tipo específico
    """
    try:
        query = select(ReglaTipoArticulo, CatTipoArticulo.nombre).join(
            CatTipoArticulo, ReglaTipoArticulo.id_tipo == CatTipoArticulo.id_tipo
        ).where(ReglaTipoArticulo.id_tipo == id_tipo)
        
        result = await db.execute(query)
        regla_data = result.first()
        
        if not regla_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe regla para el tipo {id_tipo}"
            )
        
        regla, tipo_nombre = regla_data
        
        return ReglaArticuloResponse(
            id_tipo=regla.id_tipo,
            tipo_nombre=tipo_nombre,
            admite_comprar=bool(regla.admite_comprar),
            admite_recoleccion=bool(regla.admite_recoleccion),
            valor_max_domicilio=float(regla.valor_max_domicilio) if regla.valor_max_domicilio else None,
            requiere_dos_personas=bool(regla.requiere_dos_personas),
            requiere_serie=bool(regla.requiere_serie),
            requiere_prueba=bool(regla.requiere_prueba),
            activo=bool(regla.activo)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor"
        )

# ==================== PASO 1: POST /reglas/articulos ====================
@router.post("/articulos", response_model=ReglaArticuloResponse, status_code=status.HTTP_201_CREATED)
async def crear_regla_articulo(
    regla_data: ReglaArticuloCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Crear la regla para un tipo que aún no la tiene
    """
    try:
        # Validar que el tipo existe en Cat_Tipo_Articulo
        tipo_query = select(CatTipoArticulo).where(CatTipoArticulo.id_tipo == regla_data.id_tipo)
        result_tipo = await db.execute(tipo_query)
        tipo_existente = result_tipo.scalar_one_or_none()
        
        if not tipo_existente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El tipo de artículo {regla_data.id_tipo} no existe en el catálogo"
            )
        
        # Validar que no existe ya una regla para este tipo (unicidad 1:1)
        regla_existente_query = select(ReglaTipoArticulo).where(ReglaTipoArticulo.id_tipo == regla_data.id_tipo)
        result_regla = await db.execute(regla_existente_query)
        regla_existente = result_regla.scalar_one_or_none()
        
        if regla_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una regla para el tipo de artículo {regla_data.id_tipo}"
            )
        
        # Validar valor_max_domicilio ≥ 0 o null
        if regla_data.valor_max_domicilio is not None and regla_data.valor_max_domicilio < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El valor máximo de domicilio debe ser mayor o igual a 0"
            )
        
        # Crear nueva regla
        nueva_regla = ReglaTipoArticulo(
            id_tipo=regla_data.id_tipo,
            admite_comprar=regla_data.admite_comprar,
            admite_recoleccion=regla_data.admite_recoleccion,
            valor_max_domicilio=regla_data.valor_max_domicilio,
            requiere_dos_personas=regla_data.requiere_dos_personas,
            requiere_serie=regla_data.requiere_serie,
            requiere_prueba=regla_data.requiere_prueba,
            activo=regla_data.activo
        )
        
        db.add(nueva_regla)
        
        # Crear registro de auditoría
        auditoria = Auditoria(
            id_usuario=current_user.id,  # Asumiendo que current_user tiene id
            accion="REGLA_ART_CREATE",
            modulo="ReglasArticulos",
            fecha_hora=datetime.now(),
            detalle=f"id_tipo={regla_data.id_tipo}",
            old_values=None,
            new_values=str(regla_data.dict())
        )
        db.add(auditoria)
        
        await db.commit()
        await db.refresh(nueva_regla)
        
        # Obtener nombre del tipo para la respuesta
        query_nombre = select(CatTipoArticulo.nombre).where(CatTipoArticulo.id_tipo == regla_data.id_tipo)
        result_nombre = await db.execute(query_nombre)
        tipo_nombre = result_nombre.scalar_one()
        
        return ReglaArticuloResponse(
            id_tipo=nueva_regla.id_tipo,
            tipo_nombre=tipo_nombre,
            admite_comprar=bool(nueva_regla.admite_comprar),
            admite_recoleccion=bool(nueva_regla.admite_recoleccion),
            valor_max_domicilio=float(nueva_regla.valor_max_domicilio) if nueva_regla.valor_max_domicilio else None,
            requiere_dos_personas=bool(nueva_regla.requiere_dos_personas),
            requiere_serie=bool(nueva_regla.requiere_serie),
            requiere_prueba=bool(nueva_regla.requiere_prueba),
            activo=bool(nueva_regla.activo)
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al crear la regla"
        )

# ==================== PASO 2: PUT /reglas/articulos/{id_tipo} ====================
@router.put("/articulos/{id_tipo}", response_model=ReglaArticuloResponse)
async def actualizar_regla_articulo(
    id_tipo: int,
    regla_data: ReglaArticuloUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Actualizar la regla de un tipo dado (full update)
    """
    try:
        # Obtener regla existente para capturar estado previo
        query = select(ReglaTipoArticulo).where(ReglaTipoArticulo.id_tipo == id_tipo)
        result = await db.execute(query)
        regla_existente = result.scalar_one_or_none()
        
        if not regla_existente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe regla para el tipo {id_tipo}"
            )
        
        # Guardar estado previo para auditoría
        old_values = {
            "admite_comprar": regla_existente.admite_comprar,
            "admite_recoleccion": regla_existente.admite_recoleccion,
            "valor_max_domicilio": float(regla_existente.valor_max_domicilio) if regla_existente.valor_max_domicilio else None,
            "requiere_dos_personas": regla_existente.requiere_dos_personas,
            "requiere_serie": regla_existente.requiere_serie,
            "requiere_prueba": regla_existente.requiere_prueba,
            "activo": regla_existente.activo
        }
        
        # Validar valor_max_domicilio ≥ 0 o null
        if regla_data.valor_max_domicilio is not None and regla_data.valor_max_domicilio < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El valor máximo de domicilio debe ser mayor o igual a 0"
            )
        
        # Actualizar campos
        regla_existente.admite_comprar = regla_data.admite_comprar
        regla_existente.admite_recoleccion = regla_data.admite_recoleccion
        regla_existente.valor_max_domicilio = regla_data.valor_max_domicilio
        regla_existente.requiere_dos_personas = regla_data.requiere_dos_personas
        regla_existente.requiere_serie = regla_data.requiere_serie
        regla_existente.requiere_prueba = regla_data.requiere_prueba
        regla_existente.activo = regla_data.activo
        
        # Crear registro de auditoría
        new_values = regla_data.dict()
        auditoria = Auditoria(
            id_usuario=current_user.id,
            accion="REGLA_ART_UPDATE",
            modulo="ReglasArticulos",
            fecha_hora=datetime.now(),
            detalle=f"id_tipo={id_tipo}",
            old_values=str(old_values),
            new_values=str(new_values)
        )
        db.add(auditoria)
        
        await db.commit()
        await db.refresh(regla_existente)
        
        # Obtener nombre del tipo para la respuesta
        query_nombre = select(CatTipoArticulo.nombre).where(CatTipoArticulo.id_tipo == id_tipo)
        result_nombre = await db.execute(query_nombre)
        tipo_nombre = result_nombre.scalar_one()
        
        return ReglaArticuloResponse(
            id_tipo=regla_existente.id_tipo,
            tipo_nombre=tipo_nombre,
            admite_comprar=bool(regla_existente.admite_comprar),
            admite_recoleccion=bool(regla_existente.admite_recoleccion),
            valor_max_domicilio=float(regla_existente.valor_max_domicilio) if regla_existente.valor_max_domicilio else None,
            requiere_dos_personas=bool(regla_existente.requiere_dos_personas),
            requiere_serie=bool(regla_existente.requiere_serie),
            requiere_prueba=bool(regla_existente.requiere_prueba),
            activo=bool(regla_existente.activo)
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al actualizar la regla"
        )

# ==================== PASO 3: DELETE /reglas/articulos/{id_tipo} ====================
@router.delete("/articulos/{id_tipo}", response_model=ReglaArticuloResponse)
async def eliminar_regla_articulo(
    id_tipo: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Eliminar la regla de un tipo (soft delete - marcar como inactiva)
    """
    try:
        # Obtener regla existente para capturar estado previo
        query = select(ReglaTipoArticulo).where(ReglaTipoArticulo.id_tipo == id_tipo)
        result = await db.execute(query)
        regla_existente = result.scalar_one_or_none()
        
        if not regla_existente:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe regla para el tipo {id_tipo}"
            )
        
        # Verificar si ya está inactiva
        if not regla_existente.activo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La regla para el tipo {id_tipo} ya está inactiva"
            )
        
        # Guardar estado previo para auditoría
        old_values = {
            "admite_comprar": regla_existente.admite_comprar,
            "admite_recoleccion": regla_existente.admite_recoleccion,
            "valor_max_domicilio": float(regla_existente.valor_max_domicilio) if regla_existente.valor_max_domicilio else None,
            "requiere_dos_personas": regla_existente.requiere_dos_personas,
            "requiere_serie": regla_existente.requiere_serie,
            "requiere_prueba": regla_existente.requiere_prueba,
            "activo": regla_existente.activo
        }
        
        # Soft delete: marcar como inactiva en lugar de borrar físicamente
        regla_existente.activo = False
        
        # Crear registro de auditoría (usamos UPDATE porque es soft delete)
        new_values = {**old_values, "activo": False}
        auditoria = Auditoria(
            id_usuario=current_user.id,
            accion="REGLA_ART_UPDATE",  # Usamos UPDATE para soft delete
            modulo="ReglasArticulos",
            fecha_hora=datetime.now(),
            detalle=f"id_tipo={id_tipo} (soft delete)",
            old_values=str(old_values),
            new_values=str(new_values)
        )
        db.add(auditoria)
        
        await db.commit()
        await db.refresh(regla_existente)
        
        # Obtener nombre del tipo para la respuesta
        query_nombre = select(CatTipoArticulo.nombre).where(CatTipoArticulo.id_tipo == id_tipo)
        result_nombre = await db.execute(query_nombre)
        tipo_nombre = result_nombre.scalar_one()
        
        return ReglaArticuloResponse(
            id_tipo=regla_existente.id_tipo,
            tipo_nombre=tipo_nombre,
            admite_comprar=bool(regla_existente.admite_comprar),
            admite_recoleccion=bool(regla_existente.admite_recoleccion),
            valor_max_domicilio=float(regla_existente.valor_max_domicilio) if regla_existente.valor_max_domicilio else None,
            requiere_dos_personas=bool(regla_existente.requiere_dos_personas),
            requiere_serie=bool(regla_existente.requiere_serie),
            requiere_prueba=bool(regla_existente.requiere_prueba),
            activo=bool(regla_existente.activo)
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al eliminar la regla"
        )