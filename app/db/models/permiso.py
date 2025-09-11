from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.db.database import Base

class Permiso(Base):
    __tablename__ = "Permiso"

    id_permiso = Column("Id_permiso", Integer, primary_key=True, autoincrement=True)
    id_modulo = Column("Id_modulo", Integer, ForeignKey("Modulo.Id_modulo"), nullable=False)
    id_accion = Column("Id_accion", Integer, ForeignKey("Accion.Id_accion"), nullable=False)
    codigo = Column("Codigo", String(120), nullable=False, unique=True)
    descripcion = Column("Descripcion", String(200), nullable=True)
    activo = Column("Activo", Boolean, nullable=False, default=True)
