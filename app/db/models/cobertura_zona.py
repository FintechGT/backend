from sqlalchemy import Column, Integer, String, DECIMAL, Boolean, TIME
from app.db.database import Base

class CoberturaZona(Base):
    __tablename__ = "Cobertura_Zona"

    id_zona = Column("Id_Zona", Integer, primary_key=True, autoincrement=True)
    departamento = Column("Departamento", String(60), nullable=True)
    municipio = Column("Municipio", String(60), nullable=True)
    zona = Column("Zona", String(20), nullable=True)
    colonia_barrio = Column("Colonia_barrio", String(80), nullable=True)
    permite_recoleccion = Column("Permite_recoleccion", Boolean, nullable=False, default=False)
    limite_valor = Column("Limite_valor", DECIMAL(12, 2), nullable=True)
    horario_inicio = Column("Horario_inicio", TIME, nullable=True)
    horario_fin = Column("Horario_fin", TIME, nullable=True)
    dias_habiles = Column("Dias_habiles", String(20), nullable=True)
    riesgo = Column("Riesgo", String(30), nullable=True)
    observaciones = Column("Observaciones", String(200), nullable=True)
    activo = Column("Activo", Boolean, nullable=False, default=True)
