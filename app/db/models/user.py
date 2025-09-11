from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, text
from app.db.database import Base 

class User(Base):
    __tablename__ = "Usuario"

    ID_Usuario = Column(Integer, primary_key=True, autoincrement=True)
    Nombre = Column(String(120), nullable=False)
    Correo = Column(String(120), nullable=False, unique=True)
    Contrasena_hash = Column(String(255), nullable=False)

    Telefono = Column(String(30), nullable=True)
    Direccion = Column(String(300), nullable=True)
    Verificado = Column(Boolean, nullable=False, default=False)
    Estado_Activo = Column(Boolean, nullable=False, default=True)

    Created_At = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )
    Updated_At = Column(
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )

    Token_version = Column(Integer, nullable=False, default=0)
