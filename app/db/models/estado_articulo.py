from sqlalchemy import Column, Integer, String
from app.db.database import Base

class EstadoArticulo(Base):
<<<<<<< HEAD
    __tablename__ = "Estado_Articulo" 

    id_estado_articulo = Column("Id_Estado_Articulo", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False)  
=======
    __tablename__ = "Estado_Articulo"

    id_estado_articulo = Column("Id_Estado_Articulo", Integer, primary_key=True, autoincrement=True)
    nombre = Column("Nombre", String(50), nullable=False)
>>>>>>> ee46423f7b0accf1469a92eadcc777cd896d299c
