"""V0.39.3 · Diagnóstico institucional por pregunta, aislado de V5/PMI.

Conserva datos exclusivamente agregados. No almacena personas, correos ni respuestas
individuales. Los resultados históricos consolidados de madurez no se recalculan.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re

from .clients import ValidationError
from .config import database_path
from .storage import connect, transaction

DIMENSIONS = (
    ('Estandarización', 13),
    ('Gobierno', 9),
    ('Medición', 7),
    ('Seguimiento y control', 9),
    ('Enfoques y metodologías', 15),
)


TITLES = (
    'Identificación de proyectos', 'Formulación de proyectos', 'Evaluación financiera',
    'Planeación de la ejecución', 'Diseño durante la ejecución', 'Ejecución de proyectos',
    'Puesta en servicio', 'Presupuesto de proyectos', 'Contratación estandarizada',
    'Control del desempeño y cambios', 'Cierre de proyectos', 'Metas y criterios de éxito',
    'Hitos y puntos de control', 'Rol de líder de proyectos', 'Estructura de gobierno',
    'Roles y responsabilidades', 'Estructura de programas',
    'Participación activa de directivos', 'Participación de usuarios de entregables',
    'Procedimientos de toma de decisiones', 'Revisión y aprobación por la dirección',
    'Alineación con la estrategia', 'Priorización estratégica',
    'Medición del costo de proyectos', 'Mejora continua de informes',
    'Repositorio de información y lecciones', 'Seguimiento a la contratación',
    'Monitoreo de riesgos y controles', 'Indicadores de éxito',
    'Socialización de lecciones aprendidas', 'Herramientas informáticas',
    'Protocolos de información', 'Banco de proyectos', 'Existencia del rol de PMO',
    'Orientación, herramientas y plantillas de la PMO', 'Modelo de gestión de proyectos',
    'Reporte de desempeño a la alta dirección', 'Decisiones correctivas basadas en desempeño',
    'Principios y valores ágiles', 'Proyectos con metodologías ágiles',
    'Herramientas y ceremonias ágiles', 'Enfoques híbridos de gestión',
    'Tableros Kanban y Scrum', 'Colaboración entre interesados',
    'Autonomía del equipo', 'Entregas tempranas de valor',
    'Adaptación ante cambios', 'Resultados frente a documentación',
    'Inspección y mejora continua', 'OKR para alinear objetivos',
    'OKR para evaluar desempeño', 'Planificación periódica',
    'Retroalimentación temprana a interesados',
)
assert len(TITLES) == 53

SCHEMA = """
CREATE TABLE IF NOT EXISTS p2_madurez_preguntas_fuentes (
  ano INTEGER PRIMARY KEY CHECK(ano BETWEEN 2000 AND 2100),
  fuente TEXT NOT NULL, captura_inicio TEXT NOT NULL DEFAULT '',
  captura_fin TEXT NOT NULL DEFAULT '', participantes INTEGER NOT NULL,
  total_preguntas INTEGER NOT NULL,
  huella_sha256 TEXT NOT NULL,
  observaciones TEXT NOT NULL DEFAULT '',
  responsable TEXT NOT NULL,
  actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p2_madurez_preguntas_resumen (
  ano INTEGER NOT NULL REFERENCES p2_madurez_preguntas_fuentes(ano) ON DELETE CASCADE,
  numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 53),
  dimension TEXT NOT NULL, pregunta TEXT NOT NULL, titulo TEXT NOT NULL,
  promedio REAL NOT NULL CHECK(promedio BETWEEN 0 AND 5),
  respuestas INTEGER NOT NULL CHECK(respuestas >= 1),
  frecuencias_json TEXT NOT NULL,
  PRIMARY KEY(ano,numero)
);
"""


def dimension_for(number:int) -> str:
    if not 1 <= number <= 53:
        raise ValidationError(f'Pregunta {number}: número fuera del instrumento de 53 preguntas.')
    for dimension, length in DIMENSIONS:
        if number <= length: return dimension
        number -= length
    raise AssertionError('Dimensión faltante')


def _captured_date(value):
    import pandas as pd
    if value is None or pd.isna(value) or str(value).strip() == '':
        return None
    try:
        num=float(value)
        if 35000 <= num <= 80000:
            return (datetime(1899,12,30)+timedelta(days=num)).date().isoformat()
    except (ValueError, TypeError): pass
    parsed=pd.to_datetime(value,errors='coerce',dayfirst=False)
    return parsed.date().isoformat() if pd.notna(parsed) else None


def parse_survey(contents:bytes, filename:str, year:int, source:str, responsible:str) -> dict:
    """Interpreta TXT/TSV/CSV/XLSX de Forms; conserva 0 y valida 53 columnas.

    Identifica preguntas por la posición de cada columna de puntuación, no su
    etiqueta Columna29/Columna30 (que difiere en archivos históricos).
    """
    import pandas as pd
    if not 2000 <= int(year) <= 2100:
        raise ValidationError('El año debe estar entre 2000 y 2100.')
    if not source.strip() or not responsible.strip():
        raise ValidationError('Indica la fuente de la encuesta y el responsable del registro.')
    name=filename.casefold()
    try:
        if name.endswith('.xlsx'):
            frame=pd.read_excel(BytesIO(contents),dtype=object,engine='openpyxl')
        elif name.endswith(('.tsv','.txt')):
            frame=pd.read_csv(BytesIO(contents),sep='\t',dtype=object)
        elif name.endswith('.csv'):
            frame=pd.read_csv(BytesIO(contents),sep=None,engine='python',dtype=object)
        else:
            raise ValidationError('Formato no admitido; adjunta XLSX, TSV, TXT o CSV.')
    except ValidationError: raise
    except Exception as exc:
        raise ValidationError('No se pudo leer el archivo de respuestas. Comprueba el formato.') from exc
    columns=list(frame.columns)
    score_cols=[(j,c) for j,c in enumerate(columns) if re.fullmatch(r'Columna\s*\d+',str(c).strip(),flags=re.I)]
    if len(score_cols) != 53:
        raise ValidationError(f'Instrumento esperado: 53 preguntas; identificadas: {len(score_cols)}. La carga se rechazó.')
    dates=[]
    if 'Hora de finalización' in frame:
        dates=[v for v in (_captured_date(x) for x in frame['Hora de finalización']) if v]
    questions=[]
    participants=0
    unique_rows=set()
    for n,(j,col) in enumerate(score_cols,1):
        if j<1 or not str(columns[j-1]).strip():
            raise ValidationError(f'Pregunta {n}: no se identificó el enunciado previo a {col}.')
        question=' '.join(str(columns[j-1]).split())
        if len(question)<15:
            raise ValidationError(f'Pregunta {n}: texto demasiado corto.')
        numeric=pd.to_numeric(frame[col],errors='coerce')
        invalid=frame[col].notna() & frame[col].astype(str).str.strip().ne('') & numeric.isna()
        if invalid.any():
            raise ValidationError(f'Pregunta {n}: hay {int(invalid.sum())} puntuaciones no numéricas.')
        valid=numeric.dropna()
        if valid.empty:
            raise ValidationError(f'Pregunta {n}: no tiene respuestas válidas.')
        if ((valid<0)|(valid>5)).any():
            raise ValidationError(f'Pregunta {n}: existen valores fuera de 0 a 5.')
        if ((valid % 1) != 0).any():
            raise ValidationError(f'Pregunta {n}: la respuesta categórica debe estar codificada con un entero de 0 a 5.')
        unique_rows.update(int(x) for x in valid.index)
        freqs={str(i):int((valid==i).sum()) for i in range(6)}
        questions.append({'numero':n,'dimension':dimension_for(n),
                          'pregunta':question, 'titulo':TITLES[n-1],
                          'promedio':round(float(valid.mean()),6),
                          'respuestas':int(len(valid)), 'frecuencias':freqs})
    participants=len(unique_rows)
    if participants==0: raise ValidationError('No se detectaron respuestas.')
    return {'ano':int(year),'fuente':source.strip(),'responsable':responsible.strip(),
            'captura_inicio':min(dates) if dates else '',
            'captura_fin':max(dates) if dates else '',
            'participantes':participants,'total_preguntas':53,
            'huella_sha256':hashlib.sha256(contents).hexdigest(),
            'observaciones':'Fuente del instrumento por pregunta; no modifica índices consolidados anuales.',
            'preguntas':questions}


def _insert(con, payload:dict):
    con.execute('''INSERT INTO p2_madurez_preguntas_fuentes
       (ano,fuente,captura_inicio,captura_fin,participantes,total_preguntas,
        huella_sha256,observaciones,responsable)
       VALUES(?,?,?,?,?,?,?,?,?)''',
       (payload['ano'],payload['fuente'],payload['captura_inicio'],payload['captura_fin'],
        payload['participantes'],len(payload['preguntas']),payload['huella_sha256'],
        payload.get('observaciones',''),payload['responsable']))
    con.executemany('''INSERT INTO p2_madurez_preguntas_resumen
       (ano,numero,dimension,pregunta,titulo,promedio,respuestas,frecuencias_json)
       VALUES(?,?,?,?,?,?,?,?)''',
       [(payload['ano'],q['numero'],q['dimension'],q['pregunta'],q['titulo'],
         q['promedio'],q['respuestas'],json.dumps(q['frecuencias'],ensure_ascii=False))
        for q in payload['preguntas']])


def initialize(path:Path|None=None, seed_path:Path|None=None):
    """Migración aditiva V0.39.3 ejecutada una sola vez por base de datos.

    Las respuestas agregadas precargadas se incorporan solo a años sin registro.
    Una vez registrada la migración 393, las ejecuciones de Streamlit son read-only.
    """
    with closing(connect(path)) as con:
        migrated=con.execute('SELECT 1 FROM schema_migrations WHERE version=393').fetchone()
        if migrated: return
        con.executescript(SCHEMA)
    bundled=(seed_path if seed_path is not None else
             Path(__file__).resolve().parents[1]/'datos_iniciales'/'madurez_preguntas_2024_2026_v0393.json')
    payloads=json.loads(bundled.read_text(encoding='utf-8')) if bundled.is_file() else []
    with transaction(path) as con:
        for payload in payloads:
            if not con.execute('SELECT 1 FROM p2_madurez_preguntas_fuentes WHERE ano=?',(payload['ano'],)).fetchone():
                _insert(con,payload)
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (393)')


def history(path:Path|None=None):
    with closing(connect(path)) as con:
        sources=[dict(x) for x in con.execute('SELECT * FROM p2_madurez_preguntas_fuentes ORDER BY ano')]
        questions=[dict(x) for x in con.execute('SELECT * FROM p2_madurez_preguntas_resumen ORDER BY ano,numero')]
    for item in questions:
        item['frecuencias']=json.loads(item.pop('frecuencias_json'))
    return {'fuentes':sources,'preguntas':questions}


def import_survey(payload:dict, overwrite:bool=False, path:Path|None=None):
    """Confirmación de una carga anual; crea respaldo antes de reemplazar."""
    from .step2_maturity_annual import backup_database
    target=Path(path) if path is not None else database_path()
    initialize(target,seed_path=Path('/no-seeds'))
    if len(payload.get('preguntas',()))!=53:
        raise ValidationError('Se requieren las 53 preguntas evaluadas.')
    with closing(connect(target)) as con:
        prev=con.execute('SELECT 1 FROM p2_madurez_preguntas_fuentes WHERE ano=?',(payload['ano'],)).fetchone()
        if prev and not overwrite:
            raise ValidationError(f'El año {payload["ano"]} ya tiene preguntas registradas. Requiere reemplazo autorizado.')
    backup=backup_database(target)
    with transaction(target) as con:
        if prev:
            con.execute('DELETE FROM p2_madurez_preguntas_resumen WHERE ano=?',(payload['ano'],))
            con.execute('DELETE FROM p2_madurez_preguntas_fuentes WHERE ano=?',(payload['ano'],))
        _insert(con,payload)
        con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,despues_json,actor)
                        VALUES(?,?,?,?,?)''',
                    ('madurez_institucional_preguntas',str(payload['ano']),
                     'reemplazar' if prev else 'crear',
                     json.dumps({'fuente':payload['fuente'],'preguntas':53,
                                 'participantes':payload['participantes'],
                                 'huella_sha256':payload['huella_sha256']},ensure_ascii=False),
                     payload['responsable']))
    return {'ano':payload['ano'],'respaldo':str(backup)}


def export_rank_csv(rows:list[dict]) -> bytes:
    import csv
    from io import StringIO
    out=StringIO()
    w=csv.writer(out,delimiter=';')
    w.writerow(['Año','N.º','Dimensión','Pregunta completa','Nombre corto','Promedio (0 a 5)','Respuestas','0','1','2','3','4','5'])
    for q in rows:
        freq=q['frecuencias']
        w.writerow([q['ano'],q['numero'],q['dimension'],q['pregunta'],q['titulo'],
                    f'{q["promedio"]:.4f}'.replace('.',','),q['respuestas'],
                    *(freq.get(str(i),0) for i in range(6))])
    return ('\ufeff'+out.getvalue()).encode('utf-8')
