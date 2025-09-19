from typing import Dict, Any
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Body, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.db.models.user import User
from app.db.models.auditoria import Auditoria
from app.schemas.usuarios import UserProfileOut, UserProfilePatch


from app.core.security import get_current_user 

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

def _to_out(user: User) -> UserProfileOut:
    """Mapea el modelo ORM User a la respuesta pública."""
    return UserProfileOut(
        id_usuario=user.ID_Usuario,
        nombre=user.Nombre,
        correo=user.Correo,
        telefono=user.Telefono,
        direccion=user.Direccion,
        verificado=bool(user.Verificado),
        estado_activo=bool(user.Estado_Activo),
        created_at=user.Created_At,
        updated_at=user.Updated_At,
    )

@router.get(
    "/me",
    response_model=UserProfileOut,
    response_model_exclude={"updated_at"}, 
    summary="Obtener mi perfil (solo usuarios activos)"
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserProfileOut:
    if not bool(current_user.Estado_Activo):
        raise HTTPException(status_code=403, detail="Usuario inactivo")
    return _to_out(current_user)

@router.patch(
    "/me",
    response_model=UserProfileOut, 
    summary="Actualizar mi perfil (nombre, teléfono, dirección; solo usuarios activos)"
)
async def patch_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: Dict[str, Any] = Body(
        ...,
        examples={
            "ok": {
                "summary": "Actualización básica",
                "value": {
                    "nombre": "Ana Pérez",
                    "telefono": "+502 5555-1234",
                    "direccion": "6a avenida 10-22, Zona 1, Ciudad de Guatemala"
                }
            }
        }
    ),
):
    # Solo usuarios activos pueden modificar
    if not bool(current_user.Estado_Activo):
        raise HTTPException(status_code=403, detail="Usuario inactivo")

    # 400 si body vacío
    if not body:
        raise HTTPException(status_code=400, detail="Body vacío")

    # Permitir únicamente estos campos
    allowed = {"nombre", "telefono", "direccion"}
    extra = set(body.keys()) - allowed
    if extra:
        raise HTTPException(
            status_code=403,
            detail=f"Campos no permitidos: {', '.join(sorted(extra))}"
        )

    # Validar formato con Pydantic (longitudes, tipos)
    patch = UserProfilePatch(**body)

    # Debe venir al menos un campo editable
    if all(getattr(patch, f) is None for f in ["nombre", "telefono", "direccion"]):
        raise HTTPException(status_code=400, detail="Debe enviar al menos un campo editable")

    # Construir old/new para auditoría y aplicar cambios
    old_vals: dict[str, Any] = {}
    new_vals: dict[str, Any] = {}

    if patch.nombre is not None and patch.nombre != current_user.Nombre:
        old_vals["nombre"] = current_user.Nombre
        new_vals["nombre"] = patch.nombre
        current_user.Nombre = patch.nombre

    if patch.telefono is not None and patch.telefono != current_user.Telefono:
        old_vals["telefono"] = current_user.Telefono
        new_vals["telefono"] = patch.telefono
        current_user.Telefono = patch.telefono

    if patch.direccion is not None and patch.direccion != current_user.Direccion:
        old_vals["direccion"] = current_user.Direccion
        new_vals["direccion"] = patch.direccion
        current_user.Direccion = patch.direccion

    # Si no hubo cambios efectivos, devolvemos el estado actual
    if not new_vals:
        return _to_out(current_user)

    # Registrar auditoría en tu tabla Auditoria
    audit = Auditoria(
        id_usuario=current_user.ID_Usuario,
        accion="ACTUALIZAR_PERFIL",
        modulo="USUARIOS",
        fecha_hora=datetime.now(timezone.utc),  # TIMESTAMP; usa UTC
        detalle="Actualización de perfil básico (nombre/telefono/direccion)",
        old_values=json.dumps(old_vals, ensure_ascii=False),
        new_values=json.dumps(new_vals, ensure_ascii=False),
    )
    db.add(audit)

    # Persistir usuario + auditoría
    await db.flush()
    await db.commit()
    await db.refresh(current_user)

    return _to_out(current_user)
