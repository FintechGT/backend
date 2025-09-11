from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.models.user import User

async def usuario_tiene_rol(usuario: User, db: AsyncSession, rol_objetivo: str) -> bool:
    query = text("""
        SELECT r.Nombre
        FROM Usuario_Rol ur
        JOIN Roles r ON ur.ID_Rol = r.ID_Rol
        WHERE ur.ID_Usuario = :usuario_id
    """)
    result = await db.execute(query, {"usuario_id": usuario.id_usuario})
    roles = [row[0] for row in result.fetchall()]
    return rol_objetivo.lower() in [r.lower() for r in roles]


async def usuario_tiene_algun_rol(usuario: User, db: AsyncSession, roles_aceptados: list[str]) -> bool:

    query = text("""
        SELECT r.Nombre
        FROM Usuario_Rol ur
        JOIN Roles r ON ur.ID_Rol = r.ID_Rol
        WHERE ur.ID_Usuario = :usuario_id
    """)
    result = await db.execute(query, {"usuario_id": usuario.id_usuario})
    roles_usuario = [row[0].lower() for row in result.fetchall()]
    return any(r.lower() in roles_usuario for r in roles_aceptados)
