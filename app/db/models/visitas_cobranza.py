from sqlalchemy import Column, Integer, String, DECIMAL, TIMESTAMP, ForeignKey, text
from app.db.database import Base

class VisitasCobranza(Base):
    __tablename__ = "Visitas_Cobranza"

    id_visita = Column("Id_visita", Integer, primary_key=True, autoincrement=True)
    id_ruta = Column("Id_ruta", Integer, ForeignKey("Ruta_Cobranza.Id_Ruta"), nullable=False)
    id_prestamo = Column("Id_prestamo", Integer, ForeignKey("Prestamo.Id_PRESTAMO"), nullable=False)
    id_pago = Column("Id_pago", Integer, ForeignKey("Pago.Id_pago"), nullable=True)
    resultado = Column("Resultado", String(30), nullable=True)
    comentario = Column("Comentario", String(200), nullable=True)
    gps = Column("gps", String(60), nullable=True)
    monto_pagado = Column("Monto_pagado", DECIMAL(12, 2), nullable=True)
    fecha_visita = Column("Fecha_visita", TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
