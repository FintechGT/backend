from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class Cliente(Base):
    __tablename__ = "Cliente"

    id_cliente = Column("Id_cliente", Integer, primary_key=True, autoincrement=True)
    id_usuario = Column("Id_usuario", Integer, ForeignKey("Usuario.ID_Usuario"), unique=True, nullable=False)
    
    # Puedes añadir más campos específicos del cliente aquí
    # Por ejemplo, la dirección de cobro que usas en el router.
    direccion_particular = Column("Direccion_particular", String(300), nullable=True)
    
    # Relaciones
    usuario = relationship("User")
    prestamos = relationship("Prestamo", back_populates="cliente")