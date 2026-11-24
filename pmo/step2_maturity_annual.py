"""Serie histórica de madurez percibida CENS (0-5), separada de p2_madurez (1-5).

No cambia el motor V5, las expectativas de clientes ni evaluaciones de otros pasos.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
from io import BytesIO
import json
import math
import re
import sqlite3
import unicodedata

from .clients import ValidationError
from .config import database_path
from .storage import connect, transaction

CON = 'Con enfoques y metodologías'
SIN = 'Sin enfoques y metodologías'
SCENARIOS = (CON, SIN)
COMMON = ('Estandarización', 'Gobierno', 'Medición', 'Seguimiento y control')
DIMENSIONS = {CON: (*COMMON, 'Enfoques y metodologías'), SIN: COMMON}


def _norm(value):
    norm = unicodedata.normalize('NFKD', str(value or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in norm if not unicodedata.combining(c)).strip()).casefold()


def _value(value):
    import pandas as pd
    if pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _whole_year(value, row):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f'Fila {row}: el Año no es numérico.')
    if not n.is_integer() or not 2000 <= n <= 2100:
        raise ValidationError(f'Fila {row}: el Año debe estar entre 2000 y 2100.')
    return int(n)


def _nonnegative(value, label, row):
    value = _value(value)
    if value is None:
        return None
    try: n = float(value)
    except (TypeError, ValueError): raise ValidationError(f'Fila {row}: {label} debe ser un número entero.')
    if not math.isfinite(n) or n < 0 or not n.is_integer():
        raise ValidationError(f'Fila {row}: {label} debe ser un entero no negativo.')
    return int(n)


def _score(value, label, row):
    value = _value(value)
    if value is None: return None
    try: val = float(value)
    except (TypeError, ValueError): raise ValidationError(f'Fila {row}: {label} no es numérico.')
    if not math.isfinite(val) or not 0 <= val <= 5:
        raise ValidationError(f'Fila {row}: {label} debe estar entre 0 y 5.')
    return round(val, 4)


def _scenario(raw, row):
    norm = _norm(raw)
    if norm in ('con', 'con enfoques y metodologias', 'con metodologias'):
        return CON
    if norm in ('sin', 'sin enfoques y metodologias', 'sin metodologias'):
        return SIN
    raise ValidationError(f'Fila {row}: escenario no reconocido: {raw}.')


def _dimension(raw, scenario, row):
    for canonical in DIMENSIONS[scenario]:
        if _norm(raw) == _norm(canonical): return canonical
    raise ValidationError(f'Fila {row}: dimensión «{raw}» no permitida para {scenario}.')


def parse_excel(contents: bytes) -> dict:
    """Read and validate all sheets before returning changes; no database writes."""
    import pandas as pd
    if not contents: raise ValidationError('Adjunta un Excel con las hojas Periodos, Escenarios y Dimensiones.')
    try: excel = pd.ExcelFile(BytesIO(contents), engine='openpyxl')
    except Exception as exc: raise ValidationError(f'No se pudo abrir el Excel: {exc}') from exc
    required = ('Periodos', 'Escenarios', 'Dimensiones')
    if any(name not in excel.sheet_names for name in required):
        raise ValidationError('El Excel debe contener las hojas Periodos, Escenarios y Dimensiones.')
    def sheet(name, columns):
        frame = pd.read_excel(excel, sheet_name=name, dtype=object)
        mapping = {_norm(col): col for col in frame.columns}
        missing = [c for c in columns if _norm(c) not in mapping]
        if missing: raise ValidationError(f'Hoja {name}: faltan columnas {", ".join(missing)}.')
        frame = frame.rename(columns={mapping[_norm(c)]: c for c in columns})
        return frame
    periods_df = sheet('Periodos', ('Año','Participantes','Encuestas','Equipos','Dependencias','Hallazgos','Fuente','Responsable'))
    scenarios_df = sheet('Escenarios', ('Año','Escenario','Índice','Fuente','Responsable'))
    dimensions_df = sheet('Dimensiones', ('Año','Escenario','Dimensión','Valor'))
    periods = {}
    for ix, raw in periods_df.iterrows():
        row = ix + 2
        if _value(raw['Año']) is None: continue
        year = _whole_year(raw['Año'],row)
        if year in periods: raise ValidationError(f'Año {year} duplicado en Periodos.')
        record = {'ano':year, 'participantes':_nonnegative(raw['Participantes'],'Participantes',row),
                  'encuestas':_nonnegative(raw['Encuestas'],'Encuestas',row),
                  'equipos':_nonnegative(raw['Equipos'],'Equipos',row),
                  'dependencias':_nonnegative(raw['Dependencias'],'Dependencias',row),
                  'hallazgos':str(_value(raw['Hallazgos']) or '').strip(),
                  'fuente':str(_value(raw['Fuente']) or '').strip(),
                  'responsable':str(_value(raw['Responsable']) or '').strip()}
        if not record['fuente'] or not record['responsable']:
            raise ValidationError(f'Fila {row} de Periodos: fuente y responsable son obligatorios.')
        periods[year] = record
    scenarios = {}
    for ix, raw in scenarios_df.iterrows():
        row=ix+2
        if _value(raw['Año']) is None: continue
        year=_whole_year(raw['Año'],row)
        if year not in periods: raise ValidationError(f'Fila {row} de Escenarios: falta {year} en Periodos.')
        scenario=_scenario(raw['Escenario'],row)
        key=(year,scenario)
        if key in scenarios: raise ValidationError(f'Escenario duplicado: {year}, {scenario}.')
        scenarios[key] = {'ano': year,'escenario':scenario, 'indice':_score(raw['Índice'],'Índice',row),
                          'fuente':str(_value(raw['Fuente']) or periods[year]['fuente']).strip(),
                          'responsable':str(_value(raw['Responsable']) or periods[year]['responsable']).strip(),
                          'dimensiones':{}}
    if not scenarios: raise ValidationError('No hay escenarios válidos para importar.')
    for ix, raw in dimensions_df.iterrows():
        row=ix+2
        if _value(raw['Año']) is None: continue
        year=_whole_year(raw['Año'],row);scenario=_scenario(raw['Escenario'],row)
        key=(year,scenario)
        if key not in scenarios:raise ValidationError(f'Fila {row} de Dimensiones: falta escenario {year} / {scenario}.')
        dim=_dimension(raw['Dimensión'],scenario,row)
        if dim in scenarios[key]['dimensiones']:
            raise ValidationError(f'Fila {row}: dimensión repetida ({year}, {scenario}, {dim}).')
        score=_score(raw['Valor'],'Valor',row)
        if score is None:raise ValidationError(f'Fila {row}: el valor de dimensión está vacío.')
        scenarios[key]['dimensiones'][dim]=score
    for key,record in scenarios.items():
        ratings=record['dimensiones']; expected=set(DIMENSIONS[key[1]])
        if ratings and set(ratings)!=expected:
            missing=expected-set(ratings)
            raise ValidationError(f'Año {key[0]}, {key[1]}: faltan dimensiones {", ".join(sorted(missing))}. '
                                  'Para históricos con solo índice, deja sin filas la hoja Dimensiones para ese escenario.')
        if ratings:
            average=round(sum(ratings.values())/len(ratings),2)
            if record['indice'] is not None and abs(record['indice']-average)>0.015:
                raise ValidationError(f'Año {key[0]}, {key[1]}: índice reportado {record["indice"]} difiere del promedio de dimensiones {average}.')
            if record['indice'] is None: record['indice']=average
        if record['indice'] is None:
            raise ValidationError(f'Año {key[0]}, {key[1]}: registra un Índice o todas las dimensiones.')
    return {'periodos':sorted(periods.values(),key=lambda x:x['ano']),
            'escenarios':sorted(scenarios.values(),key=lambda x:(x['ano'],x['escenario'])),
            'mensajes':['Serie histórica en escala 0–5, independiente de la línea base 1–5 del diagnóstico.',
                        'No se calculan radares para años sin todas sus dimensiones.']}


def history(path:Path|None=None) -> dict:
    with closing(connect(path)) as con:
        periods=[dict(r) for r in con.execute('SELECT * FROM p2_madurez_anual_periodos ORDER BY ano DESC')]
        scenarios=[dict(r) for r in con.execute('SELECT * FROM p2_madurez_anual_escenarios ORDER BY ano DESC,escenario')]
        details=[dict(r) for r in con.execute('SELECT * FROM p2_madurez_anual_dimensiones ORDER BY ano DESC,escenario,dimension')]
    for record in scenarios:
        record['dimensiones']={x['dimension']:x['puntaje'] for x in details if x['ano']==record['ano'] and x['escenario']==record['escenario']}
    return {'periodos':periods,'escenarios':scenarios}


def snapshot_for_year(data: dict, year: int) -> dict | None:
    """Lectura de un año: solo índices y dimensiones institucionales persistidos.

    No calcula nada desde PMOGA, expectativas o percepciones 1–5.
    Retorna None si no existe ese año, evitando arrastrar valores de otro ciclo.
    """
    periods = {int(row['ano']): row for row in data.get('periodos', [])}
    if int(year) not in periods:
        return None
    scenarios = {
        row['escenario']: row
        for row in data.get('escenarios', [])
        if int(row['ano']) == int(year)
    }
    with_methods = scenarios.get(CON)
    without_methods = scenarios.get(SIN)
    return {
        'ano': int(year), 'periodo': periods[int(year)],
        'con': with_methods, 'sin': without_methods,
        'dimensiones': dict((with_methods or {}).get('dimensiones') or {}),
    }


def associated_year(diagnostic_id: str, path: Path | None = None) -> int | None:
    """Vínculo contextual expediente→año, sin transferir información ni cálculos."""
    with closing(connect(path)) as con:
        exists=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p2_madurez_anual_vinculos'").fetchone()
        if not exists:
            return None
        row=con.execute('SELECT ano FROM p2_madurez_anual_vinculos WHERE diagnostico_id=?',(diagnostic_id,)).fetchone()
        return int(row['ano']) if row else None


def associate_year(diagnostic_id: str, year: int, actor: str, path: Path | None = None) -> Path:
    """Asociación explícita auditable, con backup y sin tocar puntuaciones."""
    from .step2 import audit
    if not isinstance(year,int) or not 2000<=year<=2100:
        raise ValidationError('El año asociado debe estar entre 2000 y 2100.')
    actor=str(actor or '').strip()
    if not actor:
        raise ValidationError('Indica el responsable que autoriza la asociación.')
    target=Path(path) if path is not None else database_path()
    with closing(connect(target)) as con:
        if not con.execute('SELECT 1 FROM p2_diagnosticos WHERE id=?',(diagnostic_id,)).fetchone():
            raise ValidationError('El expediente no existe en la base activa.')
        if not con.execute('SELECT 1 FROM p2_madurez_anual_periodos WHERE ano=?',(year,)).fetchone():
            raise ValidationError(f'No existe medición anual de madurez para {year}.')
    backup=backup_database(target)
    with transaction(target) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS p2_madurez_anual_vinculos (
            diagnostico_id TEXT PRIMARY KEY REFERENCES p2_diagnosticos(id) ON DELETE CASCADE,
            ano INTEGER NOT NULL CHECK (ano BETWEEN 2000 AND 2100),
            responsable TEXT NOT NULL,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        previous=con.execute('SELECT ano FROM p2_madurez_anual_vinculos WHERE diagnostico_id=?',(diagnostic_id,)).fetchone()
        con.execute('''INSERT INTO p2_madurez_anual_vinculos(diagnostico_id,ano,responsable)
            VALUES (?,?,?) ON CONFLICT(diagnostico_id) DO UPDATE SET
            ano=excluded.ano,responsable=excluded.responsable,actualizado_en=CURRENT_TIMESTAMP''',
            (diagnostic_id,year,actor))
        audit(con,'p2_madurez_anual_vinculo',diagnostic_id,'asociar_ano',actor,
              {'anterior':int(previous['ano']) if previous else None,'nuevo':year})
    return backup


def backup_database(path: Path) -> Path:
    target=Path(path); archive=target.parent/'respaldos'
    archive.mkdir(parents=True,exist_ok=True)
    name=f'{target.stem}_antes_madurez_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.sqlite3'
    destination=archive/name
    with sqlite3.connect(str(target)) as src, sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
    return destination


def import_history(parsed:dict, actor:str, path:Path|None=None, overwrite:bool=False, backup=True) -> dict:
    actor=str(actor or '').strip()
    if not actor:raise ValidationError('Indique el responsable de la carga.')
    target=Path(path) if path else database_path()
    # Protection: calculate conflicts before any update (copy-on-write snapshot only for changes).
    with closing(connect(target)) as con:
        old_periods={r['ano']:dict(r) for r in con.execute('SELECT * FROM p2_madurez_anual_periodos')}
        old_scenarios={(r['ano'],r['escenario']):dict(r) for r in con.execute('SELECT * FROM p2_madurez_anual_escenarios')}
        old_dims={(r['ano'],r['escenario']):{} for r in con.execute('SELECT ano,escenario FROM p2_madurez_anual_escenarios')}
        for r in con.execute('SELECT * FROM p2_madurez_anual_dimensiones'):
            old_dims.setdefault((r['ano'],r['escenario']),{})[r['dimension']]=r['puntaje']
    conflicts=[];changed=0
    for p in parsed['periodos']:
        prev=old_periods.get(p['ano']);fields=('participantes','encuestas','equipos','dependencias','hallazgos','fuente','responsable')
        if prev and any(prev[k]!=p[k] for k in fields):conflicts.append(f'Indicadores {p["ano"]}')
        if not prev or any(prev[k]!=p[k] for k in fields):changed+=1
    for s in parsed['escenarios']:
        key=(s['ano'],s['escenario']);prev=old_scenarios.get(key)
        if prev and (abs(prev['indice']-s['indice'])>1e-9 or prev['fuente']!=s['fuente'] or prev['responsable']!=s['responsable'] or old_dims.get(key,{})!=s['dimensiones']):
            conflicts.append(f'{s["ano"]}: {s["escenario"]}')
        if not prev or (abs(prev['indice']-s['indice'])>1e-9 or prev['fuente']!=s['fuente'] or prev['responsable']!=s['responsable'] or old_dims.get(key,{})!=s['dimensiones']):changed+=1
    if conflicts and not overwrite:
        raise ValidationError('Hay información previamente guardada que difiere del Excel: '+', '.join(conflicts)+'. '
                              'Activa «Reemplazar resultados existentes» después de revisar el detalle.')
    if changed==0:return {'cambios':0,'respaldo':None,'conflictos':[]}
    saved_backup=backup_database(target) if backup else None
    with transaction(target) as con:
        for p in parsed['periodos']:
            con.execute('''INSERT INTO p2_madurez_anual_periodos
              (ano,participantes,encuestas,equipos,dependencias,hallazgos,fuente,responsable) VALUES (?,?,?,?,?,?,?,?)
              ON CONFLICT(ano) DO UPDATE SET participantes=excluded.participantes,encuestas=excluded.encuestas,
              equipos=excluded.equipos,dependencias=excluded.dependencias,hallazgos=excluded.hallazgos,
              fuente=excluded.fuente,responsable=excluded.responsable,actualizado_en=CURRENT_TIMESTAMP''',
              (p['ano'],p['participantes'],p['encuestas'],p['equipos'],p['dependencias'],p['hallazgos'],p['fuente'],p['responsable']))
        for s in parsed['escenarios']:
            con.execute('''INSERT INTO p2_madurez_anual_escenarios(ano,escenario,indice,fuente,responsable)
              VALUES (?,?,?,?,?) ON CONFLICT(ano,escenario) DO UPDATE SET indice=excluded.indice,
              fuente=excluded.fuente,responsable=excluded.responsable,actualizado_en=CURRENT_TIMESTAMP''',
              (s['ano'],s['escenario'],s['indice'],s['fuente'],s['responsable']))
            con.execute('DELETE FROM p2_madurez_anual_dimensiones WHERE ano=? AND escenario=?',(s['ano'],s['escenario']))
            for dim,val in s['dimensiones'].items():
                con.execute('INSERT INTO p2_madurez_anual_dimensiones(ano,escenario,dimension,puntaje) VALUES (?,?,?,?)',
                            (s['ano'],s['escenario'],dim,val))
        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor,despues_json) VALUES (?,?,?,?,?)',
            ('p2_madurez_anual',str(','.join(str(p['ano']) for p in parsed['periodos'])),'carga_excel',actor,
             json.dumps({'escenarios':len(parsed['escenarios']),'conflictos_reemplazados':conflicts,'respaldo':str(saved_backup) if saved_backup else None},ensure_ascii=False)))
    return {'cambios':changed,'respaldo':str(saved_backup) if saved_backup else None,'conflictos':conflicts}


SUMMARY_COLUMNS = ('Año','Participantes','Encuestas','Equipos','Dependencias','Estandarización','Gobierno',
                   'Medición','Seguimiento y control','Enfoques y metodologías',
                   'Índice con enfoques','Índice sin enfoques','Hallazgos','Fuente','Responsable')


def parse_summary_excel(contents: bytes) -> dict:
    """Una fila de resultados agregados por año; formato V0.36 continúa admitido."""
    import pandas as pd
    if not contents: raise ValidationError('Adjunta un Excel consolidado de madurez.')
    try: book=pd.ExcelFile(BytesIO(contents),engine='openpyxl')
    except Exception as exc: raise ValidationError(f'No se pudo leer el Excel: {exc}') from exc
    if 'Resumen anual' not in book.sheet_names:
        return parse_excel(contents)
    table=pd.read_excel(book,sheet_name='Resumen anual',dtype=object)
    lookup={_norm(c):c for c in table.columns}
    missing=[c for c in SUMMARY_COLUMNS if _norm(c) not in lookup]
    if missing:raise ValidationError('Hoja Resumen anual: faltan columnas '+', '.join(missing))
    table=table.rename(columns={lookup[_norm(c)]:c for c in SUMMARY_COLUMNS})
    periods=[];scenarios=[];seen=set()
    for idx,row in table.iterrows():
        n=idx+2
        if _value(row['Año']) is None:continue
        yr=_whole_year(row['Año'],n)
        if yr in seen:raise ValidationError(f'Año {yr} duplicado en Resumen anual.')
        seen.add(yr)
        source=str(_value(row['Fuente']) or '').strip();owner=str(_value(row['Responsable']) or '').strip()
        if not source or not owner:raise ValidationError(f'Fila {n}: fuente y responsable obligatorios.')
        period={'ano':yr,'hallazgos':str(_value(row['Hallazgos']) or '').strip(),
                'fuente':source,'responsable':owner}
        for k,label in (('participantes','Participantes'),('encuestas','Encuestas'),
                        ('equipos','Equipos'),('dependencias','Dependencias')):
            period[k]=_nonnegative(row[label],label,n)
        periods.append(period)
        common_scores={dim:_score(row[dim],dim,n) for dim in DIMENSIONS[CON]}
        for scenario,dims,score_label in ((CON,DIMENSIONS[CON],'Índice con enfoques'),
                                          (SIN,DIMENSIONS[SIN],'Índice sin enfoques')):
            available={dim:common_scores[dim] for dim in dims if common_scores[dim] is not None}
            if available and len(available)!=len(dims):
                raise ValidationError(f'Fila {n}: si hay dimensiones, debe completarlas para {scenario}.')
            supplied=_score(row[score_label],score_label,n)
            computed=round(sum(available.values())/len(available),2) if available else None
            if computed is not None and supplied is not None and abs(computed-supplied)>0.015:
                raise ValidationError(f'Fila {n}: índice {score_label} no coincide con las dimensiones.')
            score=supplied if supplied is not None else computed
            if score is None:raise ValidationError(f'Fila {n}: falta el índice de {scenario}.')
            scenarios.append({'ano':yr,'escenario':scenario,'indice':score,'fuente':source,
                              'responsable':owner,'dimensiones':available})
    if not periods:raise ValidationError('La hoja Resumen anual está vacía.')
    return {'periodos':periods,'escenarios':scenarios,
            'mensajes':['Solo resultados agregados, sin información de encuestados ni relación con PMOGA.']}
