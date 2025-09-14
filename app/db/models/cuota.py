from sqlalchemy import Column, Integer, DECIMAL, Date, ForeignKey
from app.db.database import Base

class Cuota(Base):
    __tablename__ = "Cuota"

    id_cuota = Column("Id_cuota", Integer, primary_key=True, autoincrement=True)
    id_prestamo = Column("Id_prestamo", Integer, ForeignKey("Prestamo.Id_PRESTAMO"), nullable=False)
    numero = Column("Numero", Integer, nullable=False)
    fecha_venc = Column("Fecha_venc", Date, nullable=False)
    monto = Column("Monto", DECIMAL(12, 2), nullable=False)
    pagada = Column("Pagada", Integer, nullable=False, default=0)  # 0 = false, 1 = true
