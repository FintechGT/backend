from sqlalchemy import Column, Integer, String, Boolean
from app.db.database import Base

class Modulo(Base):
    __tablename__ = "Modulo"

    id_modulo = Column("Id_modulo", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(60), nullable=False)
    descripcion = Column("Descripcion", String(200), nullable=True)
    ruta = Column("Ruta", String(120), nullable=True)
    activo = Column("Activo", Boolean, nullable=False, default=True)
