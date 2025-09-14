from sqlalchemy import Column, Integer, String, Boolean
from app.db.database import Base

class Rol(Base):
    __tablename__ = "Roles"

    id_rol = Column("ID_Rol", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False, unique=True)
    descripcion = Column("Descripcion", String(200), nullable=True)
    activo = Column("Activo", Boolean, nullable=False, default=True)
