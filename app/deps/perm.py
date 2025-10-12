# app/deps/perm.py
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models.permiso import Permiso
from app.db.models.rol_permiso import RolPermiso
from app.db.models.usuario_rol import UsuarioRol


async def _user_codes(db: AsyncSession, id_usuario: int) -> set[str]:
    """
    Obtiene todos los códigos de permisos activos y otorgados para un usuario.
    Normaliza códigos a minúsculas para comparación case-insensitive.
    """
    q = (
        select(Permiso.codigo)
        .join(RolPermiso, RolPermiso.id_permiso == Permiso.id_permiso)
        .join(UsuarioRol, UsuarioRol.id_rol == RolPermiso.id_rol)
        .where(UsuarioRol.id_usuario == id_usuario)
        .where(RolPermiso.otorgado == True)  # noqa: E712
        .where(Permiso.activo == True)  # noqa: E712
    )
    rows = (await db.execute(q)).scalars().all()
    return {(c or "").lower() for c in rows}


def perm(code: str):
    """
    Factory de dependency para proteger endpoints con permisos.
    
    Uso:
        @router.get("/ruta", dependencies=[Depends(perm("modulo.accion"))])
        async def endpoint_protegido(): ...
    """
    required = code.lower()
    
    async def _check(
        db: AsyncSession = Depends(get_db),
        me=Depends(get_current_user)
    ):
        # Resolver id_usuario del modelo User (soporta ID_Usuario, id_usuario, id)
        user_id = None
        for attr in ("ID_Usuario", "id_usuario", "id"):
            val = getattr(me, attr, None)
            if isinstance(val, int):
                user_id = val
                break
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No se pudo resolver el ID del usuario"
            )
        
        codes = await _user_codes(db, user_id)
        
        if required not in codes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso insuficiente: requiere '{code}'"
            )
    
    return _check