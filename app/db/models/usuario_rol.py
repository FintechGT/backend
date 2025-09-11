from sqlalchemy import Column, Integer, ForeignKey, TIMESTAMP, text
from app.db.database import Base

class UsuarioRol(Base):
    __tablename__ = "Usuario_Rol"

    id_usuario = Column("ID_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), primary_key=True)
    id_rol = Column("ID_Rol", Integer, ForeignKey("Roles.ID_Rol"), primary_key=True)
    asignado_en = Column("Asignado_en", TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
