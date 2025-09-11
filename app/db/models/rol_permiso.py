from sqlalchemy import Column, Integer, ForeignKey, Boolean, TIMESTAMP, text
from app.db.database import Base

class RolPermiso(Base):
    __tablename__ = "Rol_Permiso"

    id_rol = Column("Id_Rol", Integer, ForeignKey("Roles.ID_Rol"), primary_key=True)
    id_permiso = Column("Id_Permiso", Integer, ForeignKey("Permiso.Id_permiso"), primary_key=True)
    otorgado = Column("Otorgado", Boolean, nullable=False, default=True)
    asignado_en = Column("Asignado_en", TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
