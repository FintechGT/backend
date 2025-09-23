from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoSolicitud(Base):
    __tablename__ = "Estado_Solicitud"  

    id_estado_solicitud = Column("Id_Estado_Solicitud", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False) 
