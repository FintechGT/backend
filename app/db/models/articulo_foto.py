from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.database import Base

class ArticuloFoto(Base):
    __tablename__ = "Articulo_Foto"

    id_foto = Column("Id_foto", Integer, primary_key=True, autoincrement=True)
    id_articulo = Column("Id_articulo", Integer, ForeignKey("Articulo.Id_articulo"), nullable=False)
    url = Column("Url", String(300), nullable=False)
    orden = Column("Orden", Integer, nullable=False, default=1)
