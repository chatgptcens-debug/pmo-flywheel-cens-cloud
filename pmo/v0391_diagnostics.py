"""V0.39.1 · Nombres uniformes de diagnósticos sin modificar sus IDs o vínculos."""
from __future__ import annotations
from collections import defaultdict
from contextlib import closing
from datetime import datetime
import json
import re
from pathlib import Path

from .storage import connect, transaction
from .clients import ValidationError

PATTERN=re.compile(r'^Diagnóstico\s+(\d+)\s*-\s*(\d{4})\s*-\s*Levantamiento de Necesidades$',re.I)


def diagnostic_year(record: dict) -> int:
    cycle=str(record.get('ciclo') or '')
    found=re.search(r'(?<!\d)(20\d{2})(?!\d)',cycle)
    if found:return int(found.group(1))
    created=str(record.get('creado_en') or '')
    found=re.search(r'(?<!\d)(20\d{2})(?!\d)',created)
    return int(found.group(1)) if found else datetime.now().year


def standard_name(number:int,year:int)->str:
    return f'Diagnóstico {number:02d} - {year} - Levantamiento de Necesidades'


def next_diagnostic_name(cycle:str, path:Path|None=None)->str:
    year=diagnostic_year({'ciclo':cycle})
    with closing(connect(path)) as con:
        records=[dict(r) for r in con.execute('SELECT nombre,ciclo,creado_en FROM p2_diagnosticos')]
    used={int(m.group(1)) for r in records if (m:=PATTERN.match(str(r['nombre'] or ''))) and int(m.group(2))==year}
    number=1
    while number in used:number+=1
    return standard_name(number,year)


def harmonize_diagnostic_names(path:Path|None=None)->dict:
    """Idempotente, sin renumerar etiquetas ya asignadas; registra nombre anterior."""
    from .client_directory import backup_clients_database
    with closing(connect(path)) as con:
        records=[dict(r) for r in con.execute('SELECT rowid,id,nombre,ciclo,creado_en FROM p2_diagnosticos ORDER BY creado_en,rowid')]
    used=defaultdict(set)
    for r in records:
        match=PATTERN.match(str(r['nombre'] or ''))
        if match:used[int(match.group(2))].add(int(match.group(1)))
    changes=[]
    for r in records:
        if PATTERN.match(str(r['nombre'] or '')):continue
        year=diagnostic_year(r)
        index=1
        while index in used[year]:index+=1
        used[year].add(index)
        changes.append((r,standard_name(index,year)))
    if not changes:return {'changed':0}
    backup_clients_database(path)
    with transaction(path) as con:
        for record,new_name in changes:
            # Otra sesión puede haber homologado el registro; evita sobrescritura.
            old=con.execute('SELECT nombre FROM p2_diagnosticos WHERE id=?',(record['id'],)).fetchone()
            if not old or PATTERN.match(old['nombre']):continue
            con.execute('UPDATE p2_diagnosticos SET nombre=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?',(new_name,record['id']))
            con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor)
                           VALUES (?,?,?,?,?,?)''',
                        ('p2_diagnostico',record['id'],'nombre_estandar_v0391',
                         json.dumps({'nombre':old['nombre']},ensure_ascii=False),
                         json.dumps({'nombre':new_name},ensure_ascii=False),
                         'Migración controlada PMO V0.39.1'))
    return {'changed':len(changes)}
