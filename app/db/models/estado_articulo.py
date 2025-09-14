from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoArticulo(Base):
    __tablename__ = "Estado_Articulo"

    id_estado_articulo = Column("Id_Estado_Articulo", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False)
