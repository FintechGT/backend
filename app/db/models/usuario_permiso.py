from sqlalchemy import Column, Integer, ForeignKey, String, TIMESTAMP, text
from app.db.database import Base

class UsuarioPermiso(Base):
    __tablename__ = "Usuario_Permiso"

    id_usuario = Column("Id_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), primary_key=True)
    id_permiso = Column("Id_Permiso", Integer, ForeignKey("Permiso.Id_permiso"), primary_key=True)
    decision = Column("Decision", String(10), nullable=False)  # ALLOW o DENY
    motivo = Column("Motivo", String(200), nullable=True)
    asignado_en = Column("Asignado_en", TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
