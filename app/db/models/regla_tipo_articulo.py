from sqlalchemy import Column, Integer, DECIMAL, Boolean, ForeignKey
from app.db.database import Base

class ReglaTipoArticulo(Base):
    __tablename__ = "Regla_Tipo_Articulo"

    id_tipo = Column("Id_tipo", Integer, ForeignKey("Cat_Tipo_Articulo.IdTipo"), primary_key=True)
    admite_comprar = Column("Admite_comprar", Boolean, nullable=False, default=False)
    admite_recoleccion = Column("Admite_recoleccion", Boolean, nullable=False, default=False)
    valor_max_domicilio = Column("Valor_max_domicilio", DECIMAL(12, 2), nullable=True)
    requiere_dos_personas = Column("Requiere_dos_personas", Boolean, nullable=False, default=False)
    requiere_serie = Column("Requiere_serie", Boolean, nullable=False, default=False)
    requiere_prueba = Column("Requiere_prueba", Boolean, nullable=False, default=False)
    activo = Column("Activo", Boolean, nullable=False, default=True)
