from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoPago(Base):
    __tablename__ = "Estado_Pago"

    id_estado_pago = Column("Id_Estado_Pago", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False)
