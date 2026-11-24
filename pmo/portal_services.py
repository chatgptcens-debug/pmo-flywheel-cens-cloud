"""Vista del catálogo aprobado en el Portal, sin replicación ni escritura."""
from . import step4

def approved_services(path=None):
    """Servicios con aprobación de diseño en Paso 04; no implica autorización Paso 05."""
    return [s for s in step4.services(path) if s.get('estado')=='Aprobado']
