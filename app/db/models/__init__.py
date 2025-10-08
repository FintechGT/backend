from .cat_tipo_articulo import CatTipoArticulo
from .estado_articulo import EstadoArticulo
from .estado_solicitud import EstadoSolicitud
from .estado_prestamo import EstadoPrestamo      # ← Debe estar
from .estado_pago import EstadoPago              # ← Debe estar
from .estado_inventario import EstadoInventario  # ← Debe estar
from .solicitud import Solicitud
from .articulo import Articulo
from .articulo_foto import ArticuloFoto

# (Opcional) Si usas auditoría / usuario en este arranque:
from .auditoria import Auditoria
from .user import User