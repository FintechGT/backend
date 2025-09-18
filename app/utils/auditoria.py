from __future__ import annotations
from typing import Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
import json
from app.db.models.auditoria import Auditoria

def _to_plain_dict(obj: Any) -> dict:
    try:
        m = inspect(obj)
        return {c.key: getattr(obj, c.key) for c in m.mapper.column_attrs}
    except Exception:
        if isinstance(obj, dict):
            return obj
    return {"value": str(obj)}

def _dumps_or_none(d: dict | None) -> str | None:
    if not d:
        return None
    return json.dumps(d, ensure_ascii=False, default=str)

async def registrar_auditoria(
    db: AsyncSession,
    usuario_id: int,
    accion: str,
    modulo: str,
    detalle: str,
    valores_anteriores: dict | object | None = None,
    valores_nuevos: dict | object | None = None,
) -> None:
    old_values = _to_plain_dict(valores_anteriores) if valores_anteriores is not None else None
    new_values = _to_plain_dict(valores_nuevos) if valores_nuevos is not None else None
    auditoria = Auditoria(
        id_usuario=usuario_id,
        accion=accion,
        modulo=modulo,
        detalle=detalle,
        fecha_hora=datetime.now(),
        old_values=_dumps_or_none(old_values),
        new_values=_dumps_or_none(new_values),
    )
    db.add(auditoria)
    await db.flush()
