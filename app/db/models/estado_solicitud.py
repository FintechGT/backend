from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoSolicitud(Base):
<<<<<<< HEAD
    __tablename__ = "Estado_Solicitud"  

    id_estado_solicitud = Column("Id_Estado_Solicitud", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False) 
=======
    __tablename__ = "Estado_Solicitud"

    Id_Estado_Solicitud = Column(Integer, primary_key=True, autoincrement=True)
    Nombre = Column(String(50), nullable=False)
>>>>>>> ee46423f7b0accf1469a92eadcc777cd896d299c
