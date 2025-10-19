# app/api/routers/seguridad.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List

from app.db.database import get_db
from app.core.security import get_current_user  # ← Importar desde security.py
from app.db.models.user import User

router = APIRouter(prefix="/seguridad", tags=["Seguridad"])


@router.get("/mis-roles", response_model=List[str])
async def obtener_mis_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obtiene los roles del usuario actual.
    Retorna un array de strings: ["INVITADO", "CLIENTE"]
    """
    try:
        query = text("""
            SELECT DISTINCT r.Nombre
            FROM Usuario_Rol ur
            JOIN Roles r ON ur.ID_Rol = r.ID_Rol
            WHERE ur.ID_Usuario = :user_id
              AND r.Activo = 1
            ORDER BY r.Nombre
        """)
        
        result = await db.execute(query, {"user_id": current_user.ID_Usuario})
        roles = [row[0] for row in result.fetchall()]
        
        print(f"✅ Roles del usuario {current_user.ID_Usuario}: {roles}")
        
        return roles
        
    except Exception as e:
        print(f"❌ Error obteniendo roles: {str(e)}")
        # Si hay error, devolver array vacío en lugar de fallar
        return []


@router.get("/mis-permisos")
async def obtener_mis_permisos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obtiene los permisos del usuario actual basado en sus roles.
    Retorna: { "permisos": ["solicitudes.view", "solicitudes.create", ...], "total": 3 }
    """
    try:
        query = text("""
            SELECT DISTINCT p.Codigo
            FROM Usuario_Rol ur
            JOIN Rol_Permiso rp ON ur.ID_Rol = rp.Id_Rol
            JOIN Permiso p ON rp.Id_Permiso = p.Id_permiso
            WHERE ur.ID_Usuario = :user_id
              AND rp.Otorgado = 1
              AND p.Activo = 1
            ORDER BY p.Codigo
        """)
        
        result = await db.execute(query, {"user_id": current_user.ID_Usuario})
        permisos = [row[0] for row in result.fetchall()]
        
        print(f"✅ Permisos del usuario {current_user.ID_Usuario}: {permisos}")
        
        return {
            "permisos": permisos,
            "total": len(permisos)
        }
        
    except Exception as e:
        print(f"❌ Error obteniendo permisos: {str(e)}")
        return {
            "permisos": [],
            "total": 0
        }