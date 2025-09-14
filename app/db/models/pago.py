from sqlalchemy import Column, Integer, DECIMAL, DateTime, String, ForeignKey
from app.db.database import Base

class Pago(Base):
    __tablename__ = "Pago"

    id_pago = Column("Id_pago", Integer, primary_key=True, autoincrement=True)
    id_prestamo = Column("Id_prestamo", Integer, ForeignKey("Prestamo.Id_PRESTAMO"), nullable=False)
    id_estado = Column("Id_estado", Integer, ForeignKey("Estado_Pago.Id_Estado_Pago"), nullable=False)
    id_validador = Column("Id_validador", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    fecha_pago = Column("Fecha_pago", DateTime, nullable=False)
    monto = Column("Monto", DECIMAL(12, 2), nullable=False)
    tipo_pago = Column("Tipo_pago", String(200), nullable=True)
    medio_pago = Column("Medio_pago", String(20), nullable=True)
    ref_bancaria = Column("Ref_bancaria", String(60), nullable=True)
