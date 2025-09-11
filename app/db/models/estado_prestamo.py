from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoPrestamo(Base):
    __tablename__ = "Estado_Prestamo"

    id_estado_prestamo = Column("Id_Estado_Prestamo", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False)
