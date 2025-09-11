from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoSolicitud(Base):
    __tablename__ = "Estado_Solicitud"

    Id_Estado_Solicitud = Column(Integer, primary_key=True, autoincrement=True)
    Nombre = Column(String(50), nullable=False)
