from app.db.models.auditoria import Auditoria
from datetime import datetime

async def registrar_auditoria(
    db,
    usuario_id: int,
    accion: str,
    modulo: str,
    detalle: str,
    valores_anteriores: dict = None,
    valores_nuevos: dict = None,
):
    auditoria = Auditoria(
        id_usuario=usuario_id,
        accion=accion,
        modulo=modulo,
        detalle=detalle,
        fecha_hora=datetime.now(),
        old_values=str(valores_anteriores) if valores_anteriores else None,
        new_values=str(valores_nuevos) if valores_nuevos else None,
    )
    db.add(auditoria)
