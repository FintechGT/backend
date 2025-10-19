# ============================================================
# PASO 1: Script SQL para configurar permisos base
# ============================================================
"""
-- Ejecuta esto en tu base de datos MySQL

-- 1. Crear permisos básicos de solicitudes si no existen
INSERT IGNORE INTO Permiso (Id_modulo, Id_accion, Codigo, Descripcion, Activo)
SELECT 
    (SELECT Id_modulo FROM Modulo WHERE LOWER(Nombre) = 'solicitudes' LIMIT 1),
    1, 
    'solicitudes.view',
    'Ver solicitudes propias',
    1
WHERE NOT EXISTS (SELECT 1 FROM Permiso WHERE Codigo = 'solicitudes.view');

INSERT IGNORE INTO Permiso (Id_modulo, Id_accion, Codigo, Descripcion, Activo)
SELECT 
    (SELECT Id_modulo FROM Modulo WHERE LOWER(Nombre) = 'solicitudes' LIMIT 1),
    2, 
    'solicitudes.create',
    'Crear nuevas solicitudes',
    1
WHERE NOT EXISTS (SELECT 1 FROM Permiso WHERE Codigo = 'solicitudes.create');

INSERT IGNORE INTO Permiso (Id_modulo, Id_accion, Codigo, Descripcion, Activo)
SELECT 
    (SELECT Id_modulo FROM Modulo WHERE LOWER(Nombre) = 'solicitudes' LIMIT 1),
    3, 
    'solicitudes.update',
    'Editar solicitudes propias',
    1
WHERE NOT EXISTS (SELECT 1 FROM Permiso WHERE Codigo = 'solicitudes.update');

INSERT IGNORE INTO Permiso (Id_modulo, Id_accion, Codigo, Descripcion, Activo)
SELECT 
    (SELECT Id_modulo FROM Modulo WHERE LOWER(Nombre) = 'solicitudes' LIMIT 1),
    4, 
    'solicitudes.delete',
    'Eliminar solicitudes propias',
    1
WHERE NOT EXISTS (SELECT 1 FROM Permiso WHERE Codigo = 'solicitudes.delete');

-- 2. Asignar permisos al rol INVITADO (o CLIENTE)
-- Encuentra el ID del rol
SET @rol_invitado = (SELECT ID_Rol FROM Roles WHERE LOWER(Nombre) IN ('invitado', 'cliente') LIMIT 1);

-- Asignar permisos
INSERT IGNORE INTO Rol_Permiso (Id_Rol, Id_Permiso, Otorgado)
SELECT @rol_invitado, Id_permiso, 1
FROM Permiso 
WHERE Codigo IN ('solicitudes.view', 'solicitudes.create', 'solicitudes.update', 'solicitudes.delete')
AND @rol_invitado IS NOT NULL;

-- 3. Verificar
SELECT 
    r.Nombre as Rol,
    p.Codigo as Permiso,
    p.Descripcion,
    rp.Otorgado
FROM Roles r
JOIN Rol_Permiso rp ON r.ID_Rol = rp.Id_Rol
JOIN Permiso p ON rp.Id_Permiso = p.Id_permiso
WHERE LOWER(r.Nombre) IN ('invitado', 'cliente')
ORDER BY r.Nombre, p.Codigo;
"""

# ============================================================
# PASO 2: Modificar solicitudes.py para validar por permisos
# ============================================================

# Reemplaza app/api/routers/solicitudes.py con esto:

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload
from sqlalchemy.inspection import inspect

from app.db.database import get_db
from app.db.models.solicitud import Solicitud
from app.db.models.estado_solicitud import EstadoSolicitud
from app.db.models.user import User
from app.schemas.solicitudes import SolicitudCreate, SolicitudUpdate, SolicitudOut
from app.core.security import get_current_user
from app.utils.auditoria import registrar_auditoria

# ============= NUEVO: Importar validación de permisos =============
from app.deps.perm import perm

router = APIRouter(tags=["Solicitudes"])

def _cols_dict(obj):
    m = inspect(obj)
    return {c.key: getattr(obj, c.key) for c in m.mapper.column_attrs}

# -----------------
# Helpers de estados
# -----------------
ESTADOS_SOLICITUD_VALIDOS = {"pendiente", "en_revision", "evaluada", "rechazada"}

async def _get_estado_solicitud_by_name(db: AsyncSession, nombre: str) -> EstadoSolicitud | None:
    """Obtiene EstadoSolicitud por nombre (case-insensitive)."""
    return (
        await db.execute(
            select(EstadoSolicitud).where(func.lower(EstadoSolicitud.Nombre) == nombre.lower())
        )
    ).scalar_one_or_none()

def _to_std_estado_nombre(estado: EstadoSolicitud | None) -> str:
    return (estado.Nombre if estado else "").lower()

# -----------------
# CREATE - AHORA CON PERMISOS
# -----------------
@router.post(
    "",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(perm("solicitudes.create"))]  # ✅ Valida permiso
)
async def crear_solicitud(
    payload: SolicitudCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cualquier usuario con permiso 'solicitudes.create' puede crear"""
    metodo = (payload.metodo_entrega or "").lower()
    if metodo not in {"domicilio", "oficina"}:
        raise HTTPException(status_code=400, detail="Método de entrega inválido (domicilio | oficina)")
    if metodo == "domicilio" and not payload.direccion_entrega:
        raise HTTPException(status_code=400, detail="Debe proporcionar una dirección si el método es domicilio")

    estado = await _get_estado_solicitud_by_name(db, "pendiente")
    if not estado:
        raise HTTPException(status_code=500, detail="Estado 'pendiente' no existe en el catálogo")

    nueva = Solicitud(
        id_usuario=current_user.ID_Usuario,
        id_estado=estado.Id_Estado_Solicitud,
        metodo_entrega=metodo,
        direccion_entrega=payload.direccion_entrega,
    )
    db.add(nueva)
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CREAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {nueva.id_solicitud} creada",
        valores_nuevos=nueva,
    )
    await db.commit()
    await db.refresh(nueva)
    await db.refresh(estado)

    return SolicitudOut(
        id_solicitud=nueva.id_solicitud,
        estado=_to_std_estado_nombre(estado),
        metodo_entrega=nueva.metodo_entrega,
        direccion_entrega=nueva.direccion_entrega,
    )

# -----------------
# READ (mis solicitudes) - CON PERMISOS
# -----------------
@router.get(
    "/mis",
    response_model=list[SolicitudOut],
    dependencies=[Depends(perm("solicitudes.view"))]  # ✅ Valida permiso
)
async def listar_mis_solicitudes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuario solo ve sus propias solicitudes"""
    result = await db.execute(
        select(Solicitud)
        .options(selectinload(Solicitud.estado))
        .where(Solicitud.id_usuario == current_user.ID_Usuario)
    )
    solicitudes = result.scalars().all()
    return [
        SolicitudOut(
            id_solicitud=s.id_solicitud,
            estado=_to_std_estado_nombre(s.estado),
            metodo_entrega=s.metodo_entrega,
            direccion_entrega=s.direccion_entrega,
        )
        for s in solicitudes
    ]

# -----------------
# READ (detalle) - CON PERMISOS
# -----------------
@router.get(
    "/{id_solicitud}",
    response_model=SolicitudOut,
    dependencies=[Depends(perm("solicitudes.view"))]  # ✅ Valida permiso
)
async def obtener_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuario solo puede ver sus propias solicitudes"""
    result = await db.execute(
        select(Solicitud).options(selectinload(Solicitud.estado)).where(Solicitud.id_solicitud == id_solicitud)
    )
    s = result.scalar_one_or_none()
    if not s or s.id_usuario != current_user.ID_Usuario:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=_to_std_estado_nombre(s.estado),
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )

# -----------------
# UPDATE - CON PERMISOS
# -----------------
@router.put(
    "/{id_solicitud}",
    response_model=SolicitudOut,
    dependencies=[Depends(perm("solicitudes.update"))]  # ✅ Valida permiso
)
async def actualizar_solicitud(
    id_solicitud: int,
    payload: SolicitudUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuario solo puede editar sus propias solicitudes"""
    result = await db.execute(
        select(Solicitud).options(selectinload(Solicitud.estado)).where(
            Solicitud.id_solicitud == id_solicitud, Solicitud.id_usuario == current_user.ID_Usuario
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    old = _cols_dict(s)
    if payload.metodo_entrega is not None:
        m = payload.metodo_entrega.lower()
        if m not in {"domicilio", "oficina"}:
            raise HTTPException(status_code=400, detail="Método de entrega inválido")
        s.metodo_entrega = m
    if payload.direccion_entrega is not None:
        s.direccion_entrega = payload.direccion_entrega

    await db.flush()
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="ACTUALIZAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {s.id_solicitud} actualizada",
        valores_anteriores=old,
        valores_nuevos=s,
    )
    await db.commit()
    await db.refresh(s)

    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=_to_std_estado_nombre(s.estado),
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )

# -----------------
# DELETE - CON PERMISOS
# -----------------
@router.delete(
    "/{id_solicitud}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(perm("solicitudes.delete"))]  # ✅ Valida permiso
)
async def eliminar_solicitud(
    id_solicitud: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Usuario solo puede eliminar sus propias solicitudes"""
    result = await db.execute(
        select(Solicitud).where(Solicitud.id_solicitud == id_solicitud, Solicitud.id_usuario == current_user.ID_Usuario)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    old = _cols_dict(s)
    await db.delete(s)
    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="ELIMINAR_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {id_solicitud} eliminada",
        valores_anteriores=old,
    )
    await db.commit()
    return None

# -----------------
# PATCH estado (solo admin/operadores) - CON PERMISOS
# -----------------
@router.patch(
    "/{id_solicitud}/estado/{nuevo}",
    response_model=SolicitudOut,
    dependencies=[Depends(perm("solicitudes.cambiar_estado"))]  # ✅ Nuevo permiso
)
async def cambiar_estado(
    id_solicitud: int,
    nuevo: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Solo usuarios con permiso especial pueden cambiar estados"""
    # Normalizar y validar destino
    nuevo_std = (nuevo or "").lower()
    if nuevo_std not in ESTADOS_SOLICITUD_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Válidos: {sorted(ESTADOS_SOLICITUD_VALIDOS)}")

    # Cargar solicitud
    result = await db.execute(
        select(Solicitud).options(selectinload(Solicitud.estado)).where(Solicitud.id_solicitud == id_solicitud)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    # Resolver estado destino
    est_dest = await _get_estado_solicitud_by_name(db, nuevo_std)
    if not est_dest:
        raise HTTPException(status_code=400, detail=f"Estado '{nuevo_std}' no existe en catálogo")

    old = _cols_dict(s)
    s.id_estado = est_dest.Id_Estado_Solicitud
    await db.flush()

    await registrar_auditoria(
        db=db,
        usuario_id=current_user.ID_Usuario,
        accion="CAMBIAR_ESTADO_SOLICITUD",
        modulo="Solicitud",
        detalle=f"Solicitud {s.id_solicitud} -> {nuevo_std}",
        valores_anteriores=old,
        valores_nuevos=s,
    )
    await db.commit()
    await db.refresh(s)

    return SolicitudOut(
        id_solicitud=s.id_solicitud,
        estado=nuevo_std,
        metodo_entrega=s.metodo_entrega,
        direccion_entrega=s.direccion_entrega,
    )


# ============================================================
# PASO 3: Guía para el Frontend
# ============================================================
"""
IMPLEMENTACIÓN EN FRONTEND (React/Vue/Angular)

1. Al hacer login, llama a GET /usuarios/me/permisos
   
   fetch('/usuarios/me/permisos', {
     headers: { 'Authorization': 'Bearer ' + token }
   })
   .then(r => r.json())
   .then(data => {
     // data.permisos = ["solicitudes.view", "solicitudes.create", ...]
     localStorage.setItem('permisos', JSON.stringify(data.permisos))
   })

2. Crea un helper para validar permisos:

   function tienePermiso(permiso) {
     const permisos = JSON.parse(localStorage.getItem('permisos') || '[]')
     return permisos.includes(permiso.toLowerCase())
   }

3. Usa en componentes:

   // Mostrar botón solo si tiene permiso
   {tienePermiso('solicitudes.create') && (
     <button onClick={crearSolicitud}>Nueva Solicitud</button>
   )}

   // Proteger rutas
   const ProtectedRoute = ({ permiso, children }) => {
     if (!tienePermiso(permiso)) {
       return <Navigate to="/sin-acceso" />
     }
     return children
   }

4. Ejemplo completo:

   <Route path="/solicitudes">
     <Route index element={
       <ProtectedRoute permiso="solicitudes.view">
         <ListaSolicitudes />
       </ProtectedRoute>
     } />
     <Route path="nueva" element={
       <ProtectedRoute permiso="solicitudes.create">
         <NuevaSolicitud />
       </ProtectedRoute>
     } />
   </Route>

5. IMPORTANTE: El backend SIEMPRE valida. El frontend solo oculta/muestra.
"""