from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict
import json

# ============ ESQUEMAS BÁSICOS ============

class AuditoriaBase(BaseModel):
    """Esquema base para auditoría"""
    id_auditoria: int
    id_usuario: int
    accion: str
    modulo: str
    fecha_hora: datetime
    detalle: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditoriaOut(AuditoriaBase):
    """Esquema de salida compatible con el router existente"""
    old_values: Optional[str] = None
    new_values: Optional[str] = None


class AuditoriaSimple(AuditoriaBase):
    """Esquema simple para listas (sin old_values/new_values)"""
    pass


class AuditoriaDetallada(AuditoriaBase):
    """Esquema detallado con valores parseados"""
    valores_anteriores: Optional[Dict[str, Any]] = None
    valores_nuevos: Optional[Dict[str, Any]] = None

    @classmethod
    def from_orm_with_parsed_values(cls, auditoria_orm):
        """Crea instancia desde ORM parseando los valores JSON"""
        valores_anteriores = None
        valores_nuevos = None
        
        # Parsear old_values
        if auditoria_orm.old_values:
            try:
                valores_anteriores = json.loads(auditoria_orm.old_values)
            except (json.JSONDecodeError, TypeError):
                valores_anteriores = {"raw": auditoria_orm.old_values}
        
        # Parsear new_values  
        if auditoria_orm.new_values:
            try:
                valores_nuevos = json.loads(auditoria_orm.new_values)
            except (json.JSONDecodeError, TypeError):
                valores_nuevos = {"raw": auditoria_orm.new_values}
        
        return cls(
            id_auditoria=auditoria_orm.id_auditoria,
            id_usuario=auditoria_orm.id_usuario,
            accion=auditoria_orm.accion,
            modulo=auditoria_orm.modulo,
            fecha_hora=auditoria_orm.fecha_hora,
            detalle=auditoria_orm.detalle,
            valores_anteriores=valores_anteriores,
            valores_nuevos=valores_nuevos
        )


# ============ ESQUEMAS DE FILTROS ============

class AuditoriaFiltros(BaseModel):
    """Esquema para filtros de búsqueda"""
    # Filtros principales
    usuario_id: Optional[int] = Field(None, description="ID del usuario")
    accion: Optional[str] = Field(None, description="Tipo de acción")
    modulo: Optional[str] = Field(None, description="Módulo del sistema")
    
    # Filtros de fecha
    fecha_desde: Optional[date] = Field(None, description="Fecha inicial")
    fecha_hasta: Optional[date] = Field(None, description="Fecha final")
    hoy: Optional[bool] = Field(False, description="Solo registros de hoy")
    esta_semana: Optional[bool] = Field(False, description="Solo registros de esta semana")
    
    # Búsqueda de texto
    buscar: Optional[str] = Field(None, description="Buscar en detalle, acción o módulo")
    
    # Paginación
    pagina: int = Field(1, ge=1, description="Número de página")
    limite: int = Field(50, ge=1, le=500, description="Registros por página")
    
    # Ordenamiento
    orden_por: str = Field("fecha_desc", description="Campo de ordenamiento")

    @property
    def offset(self) -> int:
        """Calcula el offset basado en la página"""
        return (self.pagina - 1) * self.limite


# ============ ESQUEMAS DE RESPUESTA ============

class AuditoriaRespuesta(BaseModel):
    """Esquema de respuesta paginada"""
    registros: List[AuditoriaSimple] = []
    total: int = 0
    pagina: int = 1
    limite: int = 50
    total_paginas: int = 0
    tiene_siguiente: bool = False
    tiene_anterior: bool = False


class AuditoriaResumen(BaseModel):
    """Esquema para estadísticas y resumen"""
    total_registros: int
    registros_hoy: int = 0
    registros_semana: int = 0
    acciones_frecuentes: List[Dict[str, Any]] = []
    modulos_activos: List[Dict[str, Any]] = []
    usuarios_mas_activos: List[Dict[str, Any]] = []
    actividad_por_hora: List[Dict[str, Any]] = []


class AuditoriaAccionesDisponibles(BaseModel):
    """Esquema para opciones disponibles"""
    acciones: List[str] = []
    modulos: List[str] = []
    total_acciones: int = 0
    total_modulos: int = 0


class AuditoriaContador(BaseModel):
    """Esquema para contar registros"""
    total: int
    filtros_aplicados: Dict[str, Any] = {}


class AuditoriaUltimaActividad(BaseModel):
    """Esquema para última actividad"""
    ultimo_registro: Optional[AuditoriaSimple] = None
    total_hoy: int = 0
    total_semana: int = 0
    usuarios_activos_hoy: int = 0


# ============ ESQUEMAS AVANZADOS ============

class AuditoriaCambio(BaseModel):
    """Esquema para cambios específicos"""
    campo: str
    valor_anterior: Any
    valor_nuevo: Any
    tipo_cambio: str  # 'creacion', 'modificacion', 'eliminacion'


class AuditoriaDetalladaConCambios(AuditoriaDetallada):
    """Esquema detallado con análisis de cambios"""
    cambios: List[AuditoriaCambio] = []
    es_creacion: bool = False
    es_modificacion: bool = False
    es_eliminacion: bool = False

    def analizar_cambios(self):
        """Analiza los cambios entre valores anteriores y nuevos"""
        self.cambios = []
        
        if not self.valores_anteriores and self.valores_nuevos:
            self.es_creacion = True
            for campo, valor in self.valores_nuevos.items():
                self.cambios.append(AuditoriaCambio(
                    campo=campo,
                    valor_anterior=None,
                    valor_nuevo=valor,
                    tipo_cambio='creacion'
                ))
        elif self.valores_anteriores and not self.valores_nuevos:
            self.es_eliminacion = True
            for campo, valor in self.valores_anteriores.items():
                self.cambios.append(AuditoriaCambio(
                    campo=campo,
                    valor_anterior=valor,
                    valor_nuevo=None,
                    tipo_cambio='eliminacion'
                ))
        elif self.valores_anteriores and self.valores_nuevos:
            self.es_modificacion = True
            todos_campos = set(self.valores_anteriores.keys()) | set(self.valores_nuevos.keys())
            for campo in todos_campos:
                valor_ant = self.valores_anteriores.get(campo)
                valor_nuevo = self.valores_nuevos.get(campo)
                if valor_ant != valor_nuevo:
                    self.cambios.append(AuditoriaCambio(
                        campo=campo,
                        valor_anterior=valor_ant,
                        valor_nuevo=valor_nuevo,
                        tipo_cambio='modificacion'
                    ))