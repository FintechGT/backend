from sqlalchemy import Column, Integer, ForeignKey
from app.db.database import Base

class RolMenu(Base):
    __tablename__ = "Rol_Menu"

    id_rol = Column("Id_Rol", Integer, ForeignKey("Roles.ID_Rol"), primary_key=True)
    id_menu = Column("Id_menu", Integer, ForeignKey("Menu.Id_menu"), primary_key=True)
