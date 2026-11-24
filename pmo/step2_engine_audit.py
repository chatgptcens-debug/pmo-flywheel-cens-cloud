"""Control de calidad y trazabilidad del motor de priorización del Paso 02.

V0.32: SOLO LECTURA. No modifica la matemática V5, las matrices ni la base.
Los reportes históricos se reproducen desde sus snapshots, nunca desde datos actuales.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .clients import list_clients
from . import step2 as p2
from . import matrix as canonical
from . import v5_engine


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _identities(records: list[dict]) -> list[tuple]:
    """Solo factores que afectan el cálculo; cambios cosméticos no vuelven obsoleta la corrida."""
    return sorted((str(x['id']), str(x['group']), tuple(int(v) for v in x['priorities']))
        for x in records)


def readiness(diagnostic: str, path: Path | None = None) -> dict:
    """Mide la preparación de la muestra sin escribir registros ni inventar respuestas."""
    clients = list_clients(path=path)
    recorded = p2.expectations(diagnostic, path=path)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for entry in recorded:
        by_id[entry['cliente_id']].append(entry)
    rows = []
    totals = Counter()
    groups: dict[str, dict] = {}
    for client in clients:
        ident = client['id']
        lines = sorted(by_id.get(ident, []), key=lambda x: x['posicion'])
        priorities = [int(x['resultado_id']) for x in lines]
        active = bool(client['activo'])
        group = (client.get('segmento') or '').strip()
        if not active:
            status = 'Inactivo'; totals['inactive'] += 1
            if priorities: totals['inactive_with_answers'] += 1
        elif not group:
            status = 'Sin grupo'; totals['no_group'] += 1
        elif len(priorities) == 5 and len(set(priorities)) == 5:
            status = 'Completa'; totals['complete'] += 1
        elif priorities:
            status = 'Parcial'; totals['partial'] += 1
        else:
            status = 'Sin respuesta'; totals['missing'] += 1
        if active:
            totals['active'] += 1
            g = groups.setdefault(group or 'Sin grupo', {'total': 0, 'complete': 0, 'partial': 0, 'missing': 0})
            g['total'] += 1
            if status == 'Completa': g['complete'] += 1
            elif priorities: g['partial'] += 1
            else: g['missing'] += 1
        rows.append({'id': ident, 'codigo': client['codigo'], 'nombre': client['nombre'],
                     'dependencia': client.get('dependencia') or '', 'grupo': group,
                     'estado': status, 'prioridades': priorities, 'activo': active})
    valid = [x for x in rows if x['estado'] == 'Completa']
    partial = [x for x in rows if x['estado'] == 'Parcial']
    no_group = [x for x in rows if x['estado'] == 'Sin grupo' and x['prioridades']]
    return {
        'active_clients': totals['active'], 'total_clients': len(clients),
        'complete': totals['complete'], 'partial': totals['partial'],
        'missing': totals['missing'], 'no_group': totals['no_group'],
        'inactive_with_answers': sum(x['estado'] == 'Inactivo' and x['prioridades'] for x in rows),
        'responding_clients': sum(bool(x['prioridades']) and x['activo'] for x in rows),
        'active_groups_with_complete': sorted({x['grupo'] for x in valid}),
        'all_selected_outcomes': len({oid for x in valid for oid in x['prioridades']}),
        'rows': rows, 'groups': groups,
        'v5_ready': bool(valid) and not partial and not no_group,
        'warnings': (
          ([f'{totals["no_group"]} clientes activos todavía no tienen rol de priorización. Complete su perfil en Paso 01 para poder importar sus respuestas.'] if totals['no_group'] else []) +
          ([f'{len(partial)} participante(s) con prioridades incompletas: V5 no permite procesarlos.'] if partial else []) +
          ([f'{len(no_group)} participante(s) con respuestas y sin grupo: complete el segmento en Clientes internos.'] if no_group else []) +
          ([f'{totals["inactive_with_answers"]} registros de clientes inactivos no se procesarán.'] if totals['inactive_with_answers'] else [])
        ),
    }


def frozen_fingerprint(report: dict) -> str:
    """Huella reproducible de los datos efectivamente guardados en una corrida."""
    return _digest({'participants': _identities(report['respuestas']),
                    'weights': report['pesos'], 'matrix': report['matriz']})


def freshness(diagnostic: str, report: dict, path: Path | None = None) -> dict:
    """Diferencia snapshots históricos y captura actual, SIN invalidar ni modificar la corrida."""
    current = p2._participant_records(diagnostic, path=path)
    saved = report['respuestas']
    changed_responses = _identities(saved) != _identities([x for x in current if len(x['priorities']) == 5])
    # Una respuesta parcial también requiere revisión para V5.
    if report.get('matrix_version_id') == canonical.V5_ID and any(len(x['priorities']) != 5 for x in current):
        changed_responses = True
    current_weights = p2.saved_weights(diagnostic, path=path)
    changed_weights = bool(current_weights) and {
        k: float(v) for k, v in current_weights.items()
    } != {k: float(v) for k, v in report['pesos'].items()}
    return {'responses_changed': changed_responses, 'weights_changed': changed_weights,
            'current': not changed_responses and not changed_weights,
            'message': 'Coincide con las respuestas y pesos actuales' if not changed_responses and not changed_weights
            else 'Corrida histórica: existen cambios posteriores en respuestas o ponderaciones'}


def replay(report: dict) -> dict:
    """Verificación independiente contra snapshots: fórmula 5–4–3–2–1 × pesos × matriz.

    Reproduce la puntuación agregada sin llamar a ``p2.compute`` ni consultar SQLite.
    Los redondeos solo se aplican en la vista, no en los cálculos.
    """
    records = report['respuestas']
    weights = {str(g): float(v) for g, v in report['pesos'].items()}
    matrix = {int(o): {int(s): int(v) for s, v in values.items()}
              for o, values in report['matriz'].items()}
    result = report['resultados']
    problems = []
    if not records: problems.append('La corrida no conserva participantes.')
    if any(len(x['priorities']) != 5 or len(set(x['priorities'])) != 5 for x in records):
        problems.append('Las prioridades del snapshot están incompletas o repetidas.')
    by_group: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        by_group[str(row['group'])].append(row)
    if set(weights) != set(by_group) or not math.isclose(sum(weights.values()), 100.0, abs_tol=1e-6):
        problems.append('Los grupos y los pesos del snapshot son inconsistentes.')
    if set(matrix) != set(range(1, 31)) or any(set(v) != set(range(1, 27)) for v in matrix.values()):
        problems.append('La matriz congelada no conserva los 780 cruces.')
    if problems:
        return {'ok': False, 'issues': problems, 'max_delta_pp': None,
                'hash_snapshot': frozen_fingerprint(report), 'matrix_sha256': None}
    raw = {o: 0.0 for o in range(1, 31)}
    for group, members in by_group.items():
        for member in members:
            for pos, out in enumerate(member['priorities'], start=1):
                raw[int(out)] += (6 - pos) / (15 * len(members)) * weights[group] / 100
    relevance_total = sum(raw.values())
    if relevance_total <= 0:
        return {'ok': False, 'issues': ['Los pesos dejan relevancia nula.'],
                'max_delta_pp': None, 'hash_snapshot': frozen_fingerprint(report), 'matrix_sha256': None}
    outcomes = {o: 100 * raw[o] / relevance_total for o in raw}
    raw_service = {s: sum(raw[o] * matrix[o][s] for o in matrix) for s in range(1, 27)}
    denominator = sum(raw_service.values())
    if denominator <= 0:
        return {'ok': False, 'issues': ['La matriz no genera ningún servicio para la muestra.'],
                'max_delta_pp': None, 'hash_snapshot': frozen_fingerprint(report), 'matrix_sha256': None}
    services = {s: 100 * v / denominator for s, v in raw_service.items()}
    try:
        delta = max(
            [abs(outcomes[x['id']] - float(x['score'])) for x in result['outcomes']] +
            [abs(services[x['id']] - float(x['score'])) for x in result['services']]
        )
    except (KeyError, TypeError, ValueError) as exc:
        return {'ok': False, 'issues': ['El resultado almacenado es ilegible: '+str(exc)],
                'max_delta_pp': None, 'hash_snapshot': frozen_fingerprint(report), 'matrix_sha256': None}
    if len(result['outcomes']) != 30 or len(result['services']) != 26:
        problems.append('El ranking guardado no contiene 30 resultados y 26 servicios.')
    if delta > 1e-8: problems.append('La reproducción del cálculo difiere del resultado guardado.')
    digest = None
    if report.get('matrix_version_id') == canonical.V5_ID:
        digest = v5_engine.hash_matriz([[matrix[o][s] for s in range(1, 27)] for o in range(1, 31)])
        if digest != canonical.V5_HASH:
            problems.append('La huella de la matriz V5 no coincide con la referencia protegida.')
    return {'ok': not problems, 'issues': problems, 'max_delta_pp': delta,
            'hash_snapshot': frozen_fingerprint(report), 'matrix_sha256': digest,
            'sum_outcomes': sum(outcomes.values()), 'sum_services': sum(services.values()),
            'participants': len(records), 'matrix_cells': sum(len(row) for row in matrix.values())}


def service_explanation(report: dict, service_id: int) -> dict:
    """Aportes del servicio seleccionado, a partir SOLO de la corrida almacenada."""
    services = {r['id']: r for r in report['resultados']['services']}
    if service_id not in services: raise ValueError('El servicio no pertenece a la corrida.')
    ranks = {r['id']: i + 1 for i, r in enumerate(report['resultados']['services'])}
    entries = report['resultados'].get('contributions', {}).get(str(service_id), [])
    group_counts: dict[int, Counter] = defaultdict(Counter)
    for person in report['respuestas']:
        for o in person['priorities']:
            group_counts[int(o)][str(person['group'])] += 1
    enriched = []
    for line in entries:
        enriched.append({**line, 'respondents': sum(group_counts[int(line['outcome_id'])].values()),
                         'groups': dict(group_counts[int(line['outcome_id'])])})
    return {'service': services[service_id], 'rank': ranks[service_id], 'drivers': enriched,
            'sum_service_share_pct': sum(x['service_share_pct'] for x in entries),
            'sum_global_share_pp': sum(x['global_share_pct'] for x in entries)}
