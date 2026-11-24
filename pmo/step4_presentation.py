"""Resumen visual de las fichas del Paso 04, sin alterar persistencia ni cálculos.

Solo utiliza los registros ya guardados. No transforma hipótesis en validaciones.
"""
from __future__ import annotations
from collections import defaultdict
import re


def brief(value, limit=108, empty='Por definir'):
    if isinstance(value, (list, tuple)):
        value = ', '.join(str(item) for item in value if str(item).strip())
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return empty
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(' ', 1)[0].rstrip('.,;:') + '…'


def service_summary(service, details, metrics):
    """Seis descriptores derivados únicamente de la ficha editable del servicio."""
    activation = (details.get('activacion_detalle') or details.get('activaciones') or details.get('solicitud'))
    sla_parts = [details.get(k, '') for k in ('sla_respuesta', 'sla_entrega', 'sla_calidad', 'sla_aceptacion')]
    sla_parts = [str(v).strip() for v in sla_parts if str(v or '').strip()]
    metrics_names = [x.get('nombre', '') for x in metrics if x.get('servicio_id') == service.get('id')]
    indicators = '; '.join(metrics_names[:2]) or details.get('indicadores') or ''
    if len(metrics_names) > 2:
        indicators += f' (+{len(metrics_names) - 2} más)'
    return [
        ('Clientes / destinatarios', brief(service.get('cliente'), 87), 'users', 'blue'),
        ('Entregables', brief([x.get('Entregable','') for x in details.get('entregables_items',[]) if isinstance(x,dict)] or details.get('entregables'), 87), 'package', 'green'),
        ('Responsable', brief(service.get('responsable'), 87), 'user-round', 'purple'),
        ('Activación', brief(activation, 87), 'zap', 'orange'),
        ('ANS', brief('; '.join(sla_parts), 87), 'clipboard-list', 'blue'),
        ('Métricas', brief(indicators, 87), 'chart-no-axes-column-increasing', 'teal'),
    ]


def metric_state(metric):
    """Estado de definición, no de cumplimiento de metas."""
    required = ('formula', 'meta', 'responsable', 'fuente')
    number = sum(bool(str(metric.get(k) or '').strip()) for k in required)
    if number == 4:
        return ('Con medición' if str(metric.get('real') or '').strip() else 'Definido · sin medición', 'ready')
    if number == 0:
        return ('Por definir', 'neutral')
    return ('Pendiente', 'pending')


def metric_groups(services, metrics, selected='Todos', order='Servicio y nombre'):
    """Agrupa por ID estable, usa el orden del catálogo y aplica filtros de presentación."""
    active_services = [svc for svc in services if selected == 'Todos' or svc['id'] == selected]
    by_service = defaultdict(list)
    for metric in metrics:
        by_service[metric.get('servicio_id')].append(metric)
    order_kind = {'Eficiencia': 0, 'Salida': 1, 'Resultado': 2}
    for svc in active_services:
        records = by_service.get(svc['id'], [])
        if not records:
            continue
        if order == 'Tipo y nombre':
            records = sorted(records, key=lambda x: (order_kind.get(x.get('tipo'), 9), x.get('nombre', '').casefold()))
        elif order == 'Estado de definición':
            records = sorted(records, key=lambda x: (['neutral', 'pending', 'ready'].index(metric_state(x)[1]), x.get('nombre', '').casefold()))
        else:
            records = sorted(records, key=lambda x: x.get('nombre', '').casefold())
        yield svc, records
