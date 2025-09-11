from sqlalchemy import Column, Integer, DECIMAL, Date, TIMESTAMP, ForeignKey
from app.db.database import Base

class Prestamo(Base):
    __tablename__ = "Prestamo"

    id_prestamo = Column("Id_PRESTAMO", Integer, primary_key=True, autoincrement=True)
    id_articulo = Column("Id_Articulo", Integer, ForeignKey("Articulo.Id_articulo"), nullable=False)
    id_usuario_evaluador = Column("Id_Usuario_Evaluador", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    id_estado = Column("Id_Estado", Integer, ForeignKey("Estado_Prestamo.Id_Estado_Prestamo"), nullable=False)
    fecha_inicio = Column("Fecha_inicio", Date, nullable=False)
    fecha_vencimiento = Column("Fecha_Vencimiento", Date, nullable=False)
    monto_prestamo = Column("Monto_prestamo", DECIMAL(12, 2), nullable=False)
    deuda_actual = Column("Deuda_actual", DECIMAL(12, 2), nullable=False, default=0.00)
    mora_acumulada = Column("Mora_acumulada", DECIMAL(12, 2), nullable=False, default=0.00)
    interes_acumulada = Column("Interes_acumulada", DECIMAL(12, 2), nullable=False, default=0.00)
    created_at = Column("Created_At", TIMESTAMP, nullable=False)
    updated_at = Column("Updated_At", TIMESTAMP, nullable=False)
    ultimo_calculo_en = Column("Ultimo_Calculo_en", Date, nullable=True)
