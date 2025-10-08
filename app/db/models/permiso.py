# app/db/models/permiso.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint
from app.db.database import Base

class Permiso(Base):
    __tablename__ = "Permiso"

    id_permiso = Column("Id_permiso", Integer, primary_key=True, autoincrement=True)
    id_modulo  = Column("Id_modulo", Integer, ForeignKey("Modulo.Id_modulo"), nullable=False, index=True)
    # SIN FK a Accion; solo número 1..4
    id_accion  = Column("Id_accion", Integer, nullable=False, index=True)

    # IMPORTANTE: quitar unique=True aquí
    codigo       = Column("Codigo", String(120), nullable=False)
    descripcion  = Column("Descripcion", String(200), nullable=True)
    activo       = Column("Activo", Boolean, nullable=False, default=True)

    __table_args__ = (
        # tu regla de negocio: no repetir la misma acción dentro del mismo módulo
        UniqueConstraint("Id_modulo", "Id_accion", name="uq_permiso_modulo_accion"),
        # valida que id_accion ∈ {1,2,3,4} (MySQL 8+ la aplica; igual lo validamos en API)
        CheckConstraint("Id_accion IN (1,2,3,4)", name="ck_permiso_id_accion_1_4"),
        # Si quisieras además que 'codigo' sea único por módulo (opcional):
        # UniqueConstraint("Id_modulo", "Codigo", name="uq_permiso_modulo_codigo"),
    )
