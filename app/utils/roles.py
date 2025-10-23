# app/utils/roles.py
from __future__ import annotations
from typing import Iterable, Union, Any, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# Import opcional para type-hints; no lo usamos directamente
try:
    from app.db.models.user import User  # noqa: F401
except Exception:
    User = Any  # type: ignore


# ============================================================
# 🔹 Helper interno para resolver el ID del usuario
# ============================================================
def _resolve_user_id(usuario: Any) -> int:
    """
    Devuelve el ID del usuario sin importar el tipo de objeto.
    Acepta: int, str (numérica), dict o modelo con atributos comunes.
    """
    if isinstance(usuario, int):
        return usuario
    if isinstance(usuario, str) and usuario.isdigit():
        return int(usuario)

    if isinstance(usuario, dict):
        for k in ("ID_Usuario", "id_usuario", "id", "user_id"):
            v = usuario.get(k)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)

    for k in ("ID_Usuario", "id_usuario", "id", "user_id"):
        v = getattr(usuario, k, None)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)

    raise ValueError("No se pudo resolver el ID del usuario para verificación de roles.")


# ============================================================
# 🔹 Consulta de roles (versión SQL pura)
# ============================================================
async def _fetch_roles_raw(db: AsyncSession, user_id: int) -> Sequence[str]:
    """
    Obtiene los nombres de los roles asociados a un usuario
    desde las tablas legacy Usuario_Rol y Roles.
    """
    q = text("""
        SELECT r.Nombre
        FROM Usuario_Rol ur
        JOIN Roles r ON ur.ID_Rol = r.ID_Rol
        WHERE ur.ID_Usuario = :usuario_id
    """)
    result = await db.execute(q, {"usuario_id": user_id})
    return [row[0] for row in result.fetchall()]


# ============================================================
# 🔹 Funciones públicas (usadas en todo el backend)
# ============================================================
async def usuario_tiene_rol(
    usuario: Union[Any, int, str],
    db: AsyncSession,
    rol_objetivo: str,
) -> bool:
    """
    Retorna True si el usuario tiene el rol indicado (por nombre).
    """
    user_id = _resolve_user_id(usuario)
    roles = await _fetch_roles_raw(db, user_id)
    return any((rol_objetivo or "").lower() == (r or "").lower() for r in roles)


async def usuario_tiene_algun_rol(
    usuario: Union[Any, int, str],
    db: AsyncSession,
    roles_aceptados: Iterable[str],
) -> bool:
    """
    Retorna True si el usuario tiene al menos uno de los roles aceptados.
    """
    user_id = _resolve_user_id(usuario)
    roles = await _fetch_roles_raw(db, user_id)
    roles_lower = {(r or "").lower() for r in roles}
    aceptados = {(r or "").lower() for r in roles_aceptados}
    return bool(roles_lower & aceptados)


async def obtener_roles_usuario(
    usuario: Union[Any, int, str],
    db: AsyncSession,
) -> list[str]:
    """
    Devuelve todos los roles del usuario (lista de strings).
    """
    user_id = _resolve_user_id(usuario)
    return list(await _fetch_roles_raw(db, user_id))


# ============================================================
# 🔹 Helper estándar para los routers (admin o valuador)
# ============================================================
ADMIN_LIKE_ROLES = ("ADMINISTRADOR", "VALUADOR")

async def es_admin_o_valuador(
    usuario: Union[Any, int, str],
    db: AsyncSession,
) -> bool:
    """
    Retorna True si el usuario tiene rol de ADMINISTRADOR o VALUADOR.
    """
    return await usuario_tiene_algun_rol(usuario, db, ADMIN_LIKE_ROLES)
