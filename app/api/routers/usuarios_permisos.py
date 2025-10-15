# app/api/routers/usuarios_permisos.py
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional, Set

from app.db.database import get_db
from app.core.security import get_current_user
from app.schemas.acl import MisPermisosOut

# Modelos
from app.db.models.permiso import Permiso
from app.db.models.rol_permiso import RolPermiso
from app.db.models.usuario_rol import UsuarioRol

router = APIRouter(prefix="/usuarios", tags=["usuarios_permisos"])


async def _resolver_user_id(user) -> Optional[int]:
    """
    Intenta obtener el id numérico del usuario admitiendo variantes de atributo:
    ID_Usuario, id_usuario, id.
    """
    for attr in ("ID_Usuario", "id_usuario", "id"):
        val = getattr(user, attr, None)
        if isinstance(val, int):
            return val
    return None


@router.get("/me/permisos", response_model=MisPermisosOut, summary="Obtener mis permisos efectivos")
async def obtener_mis_permisos(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    debug: bool = Query(False, description="Si true, incluye mapping de origen rol → permiso"),
):
    """
    Devuelve permisos efectivos (códigos) del usuario autenticado.
    
    **Características:**
    - Unión de permisos de todos sus roles
    - Solo permisos activos y relaciones otorgadas=true
    - Normalizados a minúsculas, sin duplicados y ordenados ascendente
    - Con `?debug=true` incluye el mapeo de qué roles aportan cada permiso
    
    **Uso típico:**
    ```javascript
    const { permisos } = await fetch('/usuarios/me/permisos', {
      headers: { 'Authorization': 'Bearer ' + token }
    }).then(r => r.json());
    
    // permisos = ["dashboard.view", "pagos.view", "solicitudes.create", ...]
    ```
    """
    user_id = await _resolver_user_id(current_user)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo resolver el ID del usuario autenticado",
        )

    # Consulta: Usuario_Rol -> RolPermiso -> Permiso (solo activos/otorgados)
    q = (
        select(
            Permiso.codigo,
            UsuarioRol.id_rol,
        )
        .join(RolPermiso, RolPermiso.id_permiso == Permiso.id_permiso)
        .join(UsuarioRol, UsuarioRol.id_rol == RolPermiso.id_rol)
        .where(UsuarioRol.id_usuario == user_id)
        .where(RolPermiso.otorgado == True)  # noqa: E712
        .where(Permiso.activo == True)  # noqa: E712
    )
    rows = (await db.execute(q)).all()  # List[Tuple[codigo, id_rol]]

    codes: Set[str] = set()
    origen: Dict[str, List[int]] = {}

    for codigo, id_rol in rows:
        if not codigo:
            continue
        norm = str(codigo).strip().lower()
        if not norm:
            continue
        codes.add(norm)
        if debug:
            origen.setdefault(norm, [])
            if id_rol not in origen[norm]:
                origen[norm].append(id_rol)

    permisos = sorted(codes)

    if debug:
        # Ordena listas de roles para estabilidad
        for k in origen:
            origen[k].sort()
        return MisPermisosOut(permisos=permisos, origen=origen)

    return MisPermisosOut(permisos=permisos)
