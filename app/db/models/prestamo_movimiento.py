from sqlalchemy import Column, Integer, DECIMAL, String, TIMESTAMP, ForeignKey, text
from app.db.database import Base

class PrestamoMovimiento(Base):
    __tablename__ = "Prestamo_Movimiento"

    id_mov = Column("Id_mov", Integer, primary_key=True, autoincrement=True)
    id_prestamo = Column("Id_prestamo", Integer, ForeignKey("Prestamo.Id_PRESTAMO"), nullable=False)
    tipo = Column("Tipo", String(20), nullable=False)
    monto = Column("Monto", DECIMAL(12, 2), nullable=False)
    nota = Column("Nota", String(200), nullable=True)
    fecha = Column("Fecha", TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
