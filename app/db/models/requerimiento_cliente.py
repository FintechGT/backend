from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey
from app.db.database import Base

class RequerimientoCliente(Base):
    __tablename__ = "Requerimiento_Cliente"

    id_req = Column("ID_req", Integer, primary_key=True, autoincrement=True)
    id_usuario = Column("Id_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    id_estado = Column("Id_estado", Integer, nullable=False)
    asunto = Column("Asunto", String(200), nullable=False)
    detalle = Column("Detalle", Text, nullable=True)
    creado_en = Column("Creado_en", TIMESTAMP, nullable=False)
    cerrado_en = Column("Cerrado_en", TIMESTAMP, nullable=True)
