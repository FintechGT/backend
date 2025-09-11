from sqlalchemy import Column, Integer, DECIMAL, Date, ForeignKey
from app.db.database import Base

class InventarioVenta(Base):
    __tablename__ = "Inventario_Venta"

    id_inventario = Column("Id_Inventario", Integer, primary_key=True, autoincrement=True)
    id_articulo = Column("Id_articulo", Integer, ForeignKey("Articulo.Id_articulo"), nullable=False)
    id_estado = Column("Id_estado", Integer, ForeignKey("Estado_Inventario.Id_Estado_Inventario"), nullable=False)
    precio_base = Column("Precio_Base", DECIMAL(12, 2), nullable=False)
    precio_actual = Column("Precio_Actual", DECIMAL(12, 2), nullable=False)
    dias_en_bodega = Column("Dias_en_bodega", Integer, nullable=False, default=0)
    fecha_ingreso = Column("Fecha_Ingreso", Date, nullable=False)
