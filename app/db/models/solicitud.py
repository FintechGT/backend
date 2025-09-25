from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base

class Solicitud(Base):
    __tablename__ = "Solicitud"

    id_solicitud = Column("Id_Solicitud", Integer, primary_key=True, autoincrement=True)
<<<<<<< HEAD
    id_usuario  = Column("Id_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)

    # OJO: atributo del modelo = id_estado  (no id_estado_solicitud)
    id_estado   = Column("Id_Estado_Solicitud", Integer, ForeignKey("Estado_Solicitud.Id_Estado_Solicitud"), nullable=False)

=======
    id_usuario = Column("Id_Usuario", Integer, ForeignKey("Usuario.ID_Usuario"), nullable=False)
    id_estado = Column("Id_estado_Solicitud", Integer, ForeignKey("Estado_Solicitud.Id_Estado_Solicitud"), nullable=False)
>>>>>>> ee46423f7b0accf1469a92eadcc777cd896d299c
    fecha_envio = Column("Fecha_envio", DateTime, nullable=False, server_default=func.now())
    metodo_entrega = Column("Metodo_entrega", String(60), nullable=False)
    direccion_entrega = Column("Direccion_Entrega", String(300), nullable=True)

    estado = relationship("EstadoSolicitud", backref="solicitudes")

    @property
    def estado_nombre(self):
<<<<<<< HEAD
        return self.estado.nombre if self.estado else None
=======
        return self.estado.Nombre if self.estado else None
>>>>>>> ee46423f7b0accf1469a92eadcc777cd896d299c
