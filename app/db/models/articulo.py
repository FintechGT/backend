from sqlalchemy import Column, Integer, String, DECIMAL, ForeignKey
from app.db.database import Base

class Articulo(Base):
    __tablename__ = "Articulo"

    id_articulo = Column("Id_articulo", Integer, primary_key=True, autoincrement=True)
    id_solicitud = Column("Id_Solicitud", Integer, ForeignKey("Solicitud.Id_Solicitud"), nullable=False)
    id_tipo = Column("ID_tipo", Integer, ForeignKey("Cat_Tipo_Articulo.IdTipo"), nullable=False)
    id_estado = Column("Id_Estado", Integer, ForeignKey("Estado_Articulo.Id_Estado_Articulo"), nullable=False)
    descripcion = Column("Descripcion", String(800), nullable=False)
    valor_estimado = Column("Valor_Estimado", DECIMAL(12, 2), nullable=False, default=0.00)
    valor_aprobado = Column("Valor_Aprobado", DECIMAL(12, 2), nullable=True)
    condicion = Column("Condicion", String(120), nullable=True)
