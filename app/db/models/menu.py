from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.database import Base

class Menu(Base):
    __tablename__ = "Menu"

    id_menu = Column("Id_menu", Integer, primary_key=True, autoincrement=True)
    id_modulo = Column("Id_modulo", Integer, ForeignKey("Modulo.Id_modulo"), nullable=False)
    id_padre = Column("Id_padre", Integer, ForeignKey("Menu.Id_menu"), nullable=True)
    etiqueta = Column("Etiqueta", String(200), nullable=False)
    icono = Column("Icono", String(40), nullable=True)
    orden = Column("Orden", Integer, nullable=False, default=1)
