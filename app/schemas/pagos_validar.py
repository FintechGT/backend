from typing import Optional
from pydantic import BaseModel, Field, AliasChoices


class ValidarPagoRequest(BaseModel):
    """
    Payload opcional para validar un pago.
    Acepta 'nota' o 'motivo' (alias) para mayor comodidad en Postman.
    """
    nota: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Nota opcional para trazabilidad (ej: 'Caja central, ref BT-123456')",
        validation_alias=AliasChoices("nota", "motivo"),
    )

    model_config = {
        "extra": "ignore",  # ignora campos desconocidos
        "json_schema_extra": {
            "examples": [
                {"nota": "Validado en ventanilla 3"},
                {"motivo": "Pago de prueba local"},   # alias aceptado
                {},  # Sin nota también es válido
            ]
        }
    }


class AplicacionPago(BaseModel):
    """Desglose de cómo se aplicó el pago."""
    mora: float = Field(description="Monto aplicado a mora")
    interes: float = Field(description="Monto aplicado a intereses")
    capital: float = Field(description="Monto aplicado al capital")


class PrestamoResumenValidacion(BaseModel):
    """Resumen del préstamo después de la validación."""
    id: int = Field(description="ID del préstamo")
    estado: str = Field(description="Estado actual del préstamo")
    deuda_actual: float = Field(description="Saldo de capital restante")
    mora_acumulada: float = Field(description="Mora acumulada restante")
    interes_acumulada: float = Field(description="Interés acumulado restante")


class ValidarPagoResponse(BaseModel):
    """Respuesta exitosa de la validación de un pago."""
    id_pago: int = Field(description="ID del pago validado")
    estado: str = Field(description="Estado del pago (validado)")
    aplicacion: AplicacionPago = Field(description="Desglose de aplicación del pago")
    prestamo: PrestamoResumenValidacion = Field(description="Estado actualizado del préstamo")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id_pago": 8001,
                "estado": "validado",
                "aplicacion": {"mora": 2.40, "interes": 2.40, "capital": 295.20},
                "prestamo": {
                    "id": 5001,
                    "estado": "activo",
                    "deuda_actual": 304.80,
                    "mora_acumulada": 0.00,
                    "interes_acumulada": 0.00
                }
            }
        }
    }
