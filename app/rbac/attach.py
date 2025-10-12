# app/rbac/attach.py
from __future__ import annotations
from typing import Iterable
from fastapi import Depends
from fastapi.routing import APIRoute
from starlette.routing import Mount
from app.deps.perm import perm
from app.rbac.policy import is_public, match_special, default_permission

def attach_rbac_guards(app) -> None:
    """
    Recorre todas las rutas y agrega Depends(perm(...)) según:
      - SPECIAL_RULES
      - CRUD por convención (slug + verbo)
      - Lista de rutas públicas
    Llamar DESPUÉS de include_router(...)
    """
    for route in app.routes:
        if isinstance(route, APIRoute):
            _attach_to_route(route)
        elif isinstance(route, Mount):
            for r in route.routes or []:
                if isinstance(r, APIRoute):
                    _attach_to_route(r)

def _attach_to_route(route: APIRoute) -> None:
    path = route.path
    if is_public(path):
        return

    methods: Iterable[str] = route.methods or []
    new_deps = []

    for m in methods:
        m = m.upper()
        code = match_special(m, path) or default_permission(m, path)
        if not code:
            continue
        new_deps.append(Depends(perm(code)))

    if new_deps:
        route.dependencies.extend(new_deps)
