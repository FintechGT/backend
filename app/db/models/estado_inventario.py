from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoInventario(Base):
    __tablename__ = "Estado_Inventario"

    id_estado_inventario = Column("Id_Estado_Inventario", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False)
