from sqlalchemy import Column, Integer, String, Boolean
from app.db.database import Base

class Accion(Base):
    __tablename__ = "Accion"

    id_accion = Column("Id_accion", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(60), nullable=False)
    descripcion = Column("Descripcion", String(200), nullable=True)
    activo = Column("Activo", Boolean, nullable=False, default=True)
