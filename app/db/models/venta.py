from sqlalchemy import Column, Integer, DECIMAL, Date, ForeignKey
from app.db.database import Base

class Venta(Base):
    __tablename__ = "Venta"

    id_venta = Column("Id_Venta", Integer, primary_key=True, autoincrement=True)
    id_inventario = Column("Id_Inventario", Integer, ForeignKey("Inventario_Venta.Id_Inventario"), nullable=False)
    id_comprador = Column("Id_Comprador", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    precio_final = Column("Precio_Final", DECIMAL(12, 2), nullable=False)
    fecha_venta = Column("Fecha_Venta", Date, nullable=False)
