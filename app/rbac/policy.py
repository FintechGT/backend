# app/rbac/policy.py
from __future__ import annotations
from typing import Dict, Iterable, Tuple
import re

# CRUD por verbo
METHOD_TO_ACTION = {
    "GET": "view",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}

# Rutas públicas (no piden token ni permiso)
PUBLIC_PATHS: Iterable[str] = (
    "/", "/health",                 # tu root y health
    "/auth/login", "/auth/register", "/auth/google",
    "/openapi.json", "/docs", "/redoc", "/favicon.ico",
)

# Reglas especiales (sobrescriben CRUD por defecto)
# Ajustado a tus routers del main.py
SPECIAL_RULES: Dict[Tuple[str, str], str] = {
    # Pagos
    ("POST", r"^/pagos/\d+/validar$"): "pagos.validar",
    ("POST", r"^/pagos/\d+/aplicar$"): "pagos.aplicar",
    ("POST", r"^/pagos/\d+/reversar$"): "pagos.reversar",
    ("POST", r"^/crear-pagos$"):       "pagos.crear",  # según tu router crear_pagos

    # Listado de pagos por préstamo
    ("GET",  r"^/prestamos/\d+/pagos$"): "pagos.view",

    # Préstamos
    ("POST", r"^/prestamos/\d+/recalcular$"): "prestamos.recalcular",
    ("POST", r"^/prestamos/recalcular$"):     "prestamos.recalcular",
    ("POST", r"^/prestamos/\d+/evaluar-estado$"): "prestamos.evaluar_estado",
    ("POST", r"^/prestamos/procesar-incumplidos$"): "prestamos.cerrar",
    ("POST", r"^/prestamos/\d+/generar-contrato$"): "prestamos.generar_contrato",

    # Artículos / Valuación / Rechazo
    ("POST", r"^/articulos/\d+/aprobar$"):  "valuacion.aprobar",
    ("POST", r"^/articulos/\d+/rechazar$"): "valuacion.rechazar",
    ("POST", r"^/articulos/\d+/cotizar$"):  "valuacion.cotizar",
    ("POST", r"^/articulos/\d+/fotos$"):    "articulos.fotos.crud",

    # Recepciones
    ("POST", r"^/recepciones$"):            "recepciones.crear",
    ("PUT",  r"^/recepciones/\d+$"):        "recepciones.actualizar",
    ("POST", r"^/recepciones/\d+/devolver$"): "recepciones.devolver_temporal",

    # Cloudinary (firma) — ping queda público
    ("GET", r"^/cloudinary/signature$"): "solicitudes.create",

    # Seguridad / RBAC
    ("GET",    r"^/modulos$"):                 "seguridad.view",
    ("POST",   r"^/modulos$"):                 "seguridad.modulos.crud",
    ("PATCH",  r"^/modulos/\d+$"):             "seguridad.modulos.crud",
    ("DELETE", r"^/modulos/\d+$"):             "seguridad.modulos.crud",

    ("GET",    r"^/permisos$"):                "seguridad.view",
    ("POST",   r"^/permisos$"):                "seguridad.permisos.crud",
    ("POST",   r"^/permisos/bulk$"):           "seguridad.permisos.crud",
    ("DELETE", r"^/permisos/\d+$"):            "seguridad.permisos.crud",
    ("DELETE", r"^/permisos/modulo/\d+$"):     "seguridad.permisos.crud",

    ("GET",    r"^/roles$"):                   "seguridad.view",
    ("POST",   r"^/roles$"):                   "seguridad.roles.crud",
    ("GET",    r"^/roles/\d+$"):               "seguridad.roles.crud",
    ("PATCH",  r"^/roles/\d+$"):               "seguridad.roles.crud",
    ("DELETE", r"^/roles/\d+$"):               "seguridad.roles.crud",

    ("GET",    r"^/roles/\d+/permisos$"):      "seguridad.roles.crud",
    ("POST",   r"^/roles/\d+/permisos$"):      "seguridad.asignar_permisos",
    ("DELETE", r"^/roles/\d+/permisos$"):      "seguridad.asignar_permisos",
    ("DELETE", r"^/roles/\d+/permisos/\d+$"):  "seguridad.asignar_permisos",

    ("GET",    r"^/usuarios/\d+/roles$"):      "usuarios.view",
    ("POST",   r"^/usuarios/\d+/roles$"):      "usuarios.cambiar_rol",
    ("DELETE", r"^/usuarios/\d+/roles$"):      "usuarios.cambiar_rol",
    ("DELETE", r"^/usuarios/\d+/roles/\d+$"):  "usuarios.cambiar_rol",

    # Perfil actual
    ("GET",   r"^/usuarios/me$"):              "usuarios.view",
    ("PATCH", r"^/usuarios/me$"):              "usuarios.update",

    # Permisos efectivos para el frontend
    ("GET",   r"^/usuarios/me/permisos$"):     "seguridad.view",
}

def match_special(method: str, path: str) -> str | None:
    for (m, pat), perm_code in SPECIAL_RULES.items():
        if m == method and re.match(pat, path):
            return perm_code
    return None

def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS

def path_slug(path: str) -> str | None:
    parts = [p for p in path.split("/") if p]
    return parts[0].lower() if parts else None

def default_permission(method: str, path: str) -> str | None:
    slug = path_slug(path)
    if not slug:
        return None
    action = METHOD_TO_ACTION.get(method.upper())
    if not action:
        return None
    return f"{slug}.{action}"
