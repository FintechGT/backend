from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, text
from app.db.database import Base

class Comprobante(Base):
    __tablename__ = "Comprobante"

    id_comprobante = Column("Id_Comprobante", Integer, primary_key=True, autoincrement=True)
    id_pago = Column("Id_Pago", Integer, ForeignKey("Pago.Id_pago"), nullable=False)
    imagen = Column("Imagen", String(300), nullable=False)
    fecha_subida = Column("Fecha_subida", TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
