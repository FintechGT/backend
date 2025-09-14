from sqlalchemy import Column, Integer, Date, ForeignKey
from app.db.database import Base

class RutaCobranza(Base):
    __tablename__ = "Ruta_Cobranza"

    id_ruta = Column("Id_Ruta", Integer, primary_key=True, autoincrement=True)
    id_usuario_cobrador = Column("Id_Usuario_Cobrador", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    fecha_asignacion = Column("Fecha_asignacion", Date, nullable=False)
