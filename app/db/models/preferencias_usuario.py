from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, text
from app.db.database import Base

class PreferenciasUsuario(Base):
    __tablename__ = "Preferencias_Usuario"

    id_usuario = Column("Id_usuario", Integer, ForeignKey("Usuario.ID_Usuario"), primary_key=True)
    clave = Column("Clave", String(60), primary_key=True)
    valor = Column("Valor", String(200), nullable=True)
    actualizado_en = Column(
        "Actualizado_en",
        TIMESTAMP,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )
