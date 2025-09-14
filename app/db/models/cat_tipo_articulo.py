from sqlalchemy import Column, Integer, String
from app.db.database import Base

class CatTipoArticulo(Base):
    __tablename__ = "Cat_Tipo_Articulo"

    id_tipo = Column("IdTipo", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(100), nullable=False)
