from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey
from app.db.database import Base

class Contrato(Base):
    __tablename__ = "Contrato"

    id_contrato = Column("Id_Contrato", Integer, primary_key=True, autoincrement=True)
    id_prestamo = Column("Id_prestamo", Integer, ForeignKey("Prestamo.Id_PRESTAMO"), nullable=False)
    url_pdf = Column("URL_pdf", String(300), nullable=False)
    hash_doc = Column("hash_doc", String(128), nullable=True)
    firma_cliente_en = Column("Firma_cliente_en", TIMESTAMP, nullable=True)
    firma_empresa_en = Column("Firma_empresa_en", TIMESTAMP, nullable=True)
