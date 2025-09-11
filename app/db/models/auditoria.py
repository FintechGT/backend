from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey
from app.db.database import Base

class Auditoria(Base):
    __tablename__ = "Auditoria"

    id_auditoria = Column("Id_Auditoria", Integer, primary_key=True, autoincrement=True)
    id_usuario = Column("Id_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    accion = Column("accion", String(120), nullable=False)
    modulo = Column("modulo", String(128), nullable=False)
    fecha_hora = Column("Fecha_hora", TIMESTAMP, nullable=False)
    detalle = Column("Detalle", Text, nullable=True)
    old_values = Column("old_values", Text, nullable=True)
    new_values = Column("New_values", Text, nullable=True)
