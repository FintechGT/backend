from sqlalchemy import Column, Integer, String, TIMESTAMP
from app.db.database import Base

class ConfiguracionesGenerales(Base):
    __tablename__ = "Configuraciones_Generales"

    id_config = Column("Id_Config", Integer, primary_key=True, autoincrement=True)
    clave = Column("Clave", String(50), nullable=False, unique=True)
    valor = Column("Valor", String(120), nullable=False)
    descripcion = Column("Descripcion", String(120), nullable=True)
    vigente_desde = Column("Vigente_desde", TIMESTAMP, nullable=True)
    vigente_hasta = Column("Vigente_hasta", TIMESTAMP, nullable=True)
