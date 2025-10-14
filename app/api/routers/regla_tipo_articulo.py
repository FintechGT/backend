# app/api/routers/regla_tipo_articulo.py
from typing import Any, Dict, Optional
from datetime import datetime
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Session async
from app.db.session import get_db

# Auth actual de tu proyecto
from app.api.routers.auth import get_current_user

# Modelos EXACTOS
from app.db.models.auditoria import Auditoria
from app.db.models.cat_tipo_articulo import CatTipoArticulo
from app.db.models.regla_tipo_articulo import ReglaTipoArticulo

router = APIRouter(prefix="/reglas/articulos", tags=["Regla Tipo Artículo"])


# ====================== Helpers ======================

def _get_user_id(user: Any) -> int:
    """
    Intenta obtener el id del usuario con varios nombres posibles.
    Ajusta la lista si tu modelo usa otro nombre.
    """
    for attr in ("id_usuario", "ID_Usuario", "id", "user_id", "usuario_id"):
        if hasattr(user, attr):
            val = getattr(user, attr)
            if val is not None:
                return int(val)
    raise HTTPException(
        status_code=500,
        detail="No se pudo determinar el id del usuario autenticado (revisa get_current_user)."
    )

def _json_default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)

def _to_out(obj: ReglaTipoArticulo, tipo_nombre: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id_tipo": obj.id_tipo,
        "tipo_nombre": tipo_nombre,
        "admite_comprar": bool(obj.admite_comprar),
        "admite_recoleccion": bool(obj.admite_recoleccion),
        "valor_max_domicilio": obj.valor_max_domicilio,
        "requiere_dos_personas": bool(obj.requiere_dos_personas),
        "requiere_serie": bool(obj.requiere_serie),
        "requiere_prueba": bool(obj.requiere_prueba),
        "activo": bool(obj.activo),
    }

def _regla_dict(obj: ReglaTipoArticulo) -> Dict[str, Any]:
    return _to_out(obj, None)

async def _audit(
    db: AsyncSession,
    *,
    id_usuario: int,
    accion: str,
    detalle: str,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
):
    """
    Inserta en Auditoria (no hace commit; el endpoint lo hace).
    Columnas reales del modelo: id_usuario, accion, modulo, fecha_hora, detalle, old_values, new_values
    """
    db.add(
        Auditoria(
            id_usuario=id_usuario,
            accion=accion,
            modulo="ReglasArticulos",
            fecha_hora=datetime.utcnow(),
            detalle=detalle,
            old_values=json.dumps(old_values, default=_json_default) if old_values is not None else None,
            new_values=json.dumps(new_values, default=_json_default) if new_values is not None else None,
        )
    )


# ====================== Endpoints (ASYNC) ======================

# 1) GET /reglas/articulos
@router.get("", status_code=status.HTTP_200_OK)
async def listar_reglas(
    incluir_inactivas: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stmt = (
        select(ReglaTipoArticulo, CatTipoArticulo.nombre.label("tipo_nombre"))
        .join(CatTipoArticulo, CatTipoArticulo.id_tipo == ReglaTipoArticulo.id_tipo)
    )
    if not incluir_inactivas:
        stmt = stmt.where(ReglaTipoArticulo.activo == True)  # noqa: E712

    rows = (await db.execute(stmt)).all()

    await _audit(
        db,
        id_usuario=_get_user_id(current_user),
        accion="REGLA_ART_READ",
        detalle="*",
    )
    await db.commit()

    return [_to_out(r[0], r.tipo_nombre) for r in rows]


# 2) GET /reglas/articulos/{id_tipo}
@router.get("/{id_tipo}", status_code=status.HTTP_200_OK)
async def obtener_regla(
    id_tipo: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stmt = (
        select(ReglaTipoArticulo, CatTipoArticulo.nombre.label("tipo_nombre"))
        .join(CatTipoArticulo, CatTipoArticulo.id_tipo == ReglaTipoArticulo.id_tipo)
        .where(ReglaTipoArticulo.id_tipo == id_tipo)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="No existe regla para ese tipo.")

    regla, tipo_nombre = row
    await _audit(
        db,
        id_usuario=_get_user_id(current_user),
        accion="REGLA_ART_READ",
        detalle=f"id_tipo={id_tipo}",
    )
    await db.commit()
    return _to_out(regla, tipo_nombre)


# 3) POST /reglas/articulos
@router.post("", status_code=status.HTTP_201_CREATED)
async def crear_regla(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Validaciones mínimas
    if "id_tipo" not in payload:
        raise HTTPException(status_code=400, detail="id_tipo es requerido.")
    if "valor_max_domicilio" in payload and payload["valor_max_domicilio"] is not None:
        try:
            if float(payload["valor_max_domicilio"]) < 0:
                raise HTTPException(status_code=400, detail="valor_max_domicilio no puede ser negativo.")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="valor_max_domicilio inválido.")

    id_tipo_value = payload["id_tipo"]

    # Validar id_tipo existe
    tipo = (await db.execute(
        select(CatTipoArticulo).where(CatTipoArticulo.id_tipo == id_tipo_value)
    )).scalar_one_or_none()
    if not tipo:
        raise HTTPException(status_code=404, detail="El id_tipo no existe en Cat_Tipo_Articulo.")

    # Validar 1:1
    existente = (await db.execute(
        select(ReglaTipoArticulo).where(ReglaTipoArticulo.id_tipo == id_tipo_value)
    )).scalar_one_or_none()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe una regla para ese id_tipo.")

    # Crear
    nueva = ReglaTipoArticulo(**payload)
    db.add(nueva)
    await db.flush()

    await _audit(
        db,
        id_usuario=_get_user_id(current_user),
        accion="REGLA_ART_CREATE",
        detalle=f"id_tipo={id_tipo_value}",
        new_values=_regla_dict(nueva),
    )
    await db.commit()

    return _to_out(nueva, tipo.nombre)


# 4) PUT /reglas/articulos/{id_tipo}
@router.put("/{id_tipo}", status_code=status.HTTP_200_OK)
async def actualizar_regla(
    id_tipo: int,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stmt = (
        select(ReglaTipoArticulo, CatTipoArticulo.nombre.label("tipo_nombre"))
        .join(CatTipoArticulo, CatTipoArticulo.id_tipo == ReglaTipoArticulo.id_tipo)
        .where(ReglaTipoArticulo.id_tipo == id_tipo)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="La regla no existe.")

    regla, tipo_nombre = row
    old_values = _regla_dict(regla)

    # Full update (no cambiamos id_tipo desde aquí)
    for k, v in payload.items():
        setattr(regla, k, v)

    # Validación de valor_max_domicilio si vino
    if regla.valor_max_domicilio is not None:
        try:
            if float(regla.valor_max_domicilio) < 0:
                raise HTTPException(status_code=400, detail="valor_max_domicilio no puede ser negativo.")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="valor_max_domicilio inválido.")

    await db.flush()

    await _audit(
        db,
        id_usuario=_get_user_id(current_user),
        accion="REGLA_ART_UPDATE",
        detalle=f"id_tipo={id_tipo}",
        old_values=old_values,
        new_values=_regla_dict(regla),
    )
    await db.commit()

    return _to_out(regla, tipo_nombre)


# 5) DELETE /reglas/articulos/{id_tipo}  (Soft delete)
@router.delete("/{id_tipo}", status_code=status.HTTP_200_OK)
async def eliminar_regla(
    id_tipo: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stmt = (
        select(ReglaTipoArticulo, CatTipoArticulo.nombre.label("tipo_nombre"))
        .join(CatTipoArticulo, CatTipoArticulo.id_tipo == ReglaTipoArticulo.id_tipo)
        .where(ReglaTipoArticulo.id_tipo == id_tipo)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="La regla no existe.")

    regla, tipo_nombre = row
    old_values = _regla_dict(regla)

    # Soft delete
    regla.activo = False

    await db.flush()
    await _audit(
        db,
        id_usuario=_get_user_id(current_user),
        accion="REGLA_ART_DELETE",
        detalle=f"id_tipo={id_tipo}",
        old_values=old_values,
        new_values=_regla_dict(regla),
    )
    await db.commit()

    return _to_out(regla, tipo_nombre)
