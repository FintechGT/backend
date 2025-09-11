from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey
from app.db.database import Base

class RecepcionArticulo(Base):
    __tablename__ = "RecepcionArticulo"

    id_recepcion = Column("Id_recepcion", Integer, primary_key=True, autoincrement=True)
    id_articulo = Column("Id_articulo", Integer, ForeignKey("Articulo.Id_articulo"), nullable=False)
    id_usuario = Column("Id_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    metodo_entrega = Column("Metodo_Entrega", String(60), nullable=True)
    gps = Column("gps", String(60), nullable=True)
    estado_verificacion = Column("Estado_verificacion", String(20), nullable=True)
    fecha_recepcion = Column("Fecha_Recepcion", TIMESTAMP, nullable=False)
