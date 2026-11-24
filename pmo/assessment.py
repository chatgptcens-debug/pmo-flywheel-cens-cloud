"""Autoevaluación de prácticas del Paso 1: adaptación CENS original (NO texto PMI)."""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import uuid
from typing import Any
from .clients import ValidationError
from .storage import connect, transaction

DIMENSIONS = [
 ('Identificación de clientes', [
  'Se mantiene un directorio actualizado de clientes potenciales.',
  'Se clasifican los perfiles que requieren comunicación diferenciada.',
  'Se identifican las áreas donde la PMO podría aportar valor.',
  'Se identifican los referentes que participan en decisiones relevantes.',
  'Se documentan desafíos preliminares manifestados por los clientes.'
 ]),
 ('Puntos de contacto', [
  'Se definen canales de contacto apropiados para cada audiencia.',
  'Se comprueban las preferencias de comunicación de los grupos objetivo.',
  'Existe una periodicidad acordada de interacción con clientes.',
  'Se mantiene evidencia de los encuentros y comunicaciones realizados.',
  'Se revisa la oportunidad y utilidad de los contactos establecidos.'
 ]),
 ('Educación sobre el valor', [
  'Existe contenido propio que explica el propósito de la PMO.',
  'Se realizan actividades educativas adaptadas a la audiencia.',
  'Se presentan ejemplos verificables de contribuciones de la PMO.',
  'Se promueve la participación de referentes internos autorizados.',
  'Los colaboradores tienen acceso a materiales vigentes de consulta.'
 ]),
 ('Medición de la eficacia', [
  'Se distinguen alcance y comprensión en los indicadores.',
  'Se dispone de mecanismos para medir familiaridad y utilidad percibida.',
  'Se identifican cambios de conocimiento mediante mediciones comparables.',
  'Se reportan resultados con fuente y tamaño de muestra.',
  'Se revisan resultados con responsables de las actividades.'
 ]),
 ('Mejora continua', [
  'Se recogen y analizan inquietudes sobre las acciones de sensibilización.',
  'Los mensajes se ajustan según comentarios y evidencia.',
  'Se revisan experiencias externas pertinentes y aplicables.',
  'Se comunican oportunidades de mejora a los responsables.',
  'Las acciones de ajuste se documentan y se verifica su resultado.'
 ])
]
INSTRUMENT_VERSION = 'CENS-ADAPTADA-2026.1'
RANGES=[(113,125,'Excelente'),(98,112,'Bien'),(77,97,'Promedio'),(51,76,'Pobre'),(25,50,'Crítico')]


def classification(score:int | None) -> str | None:
    if score is None:
        return None
    for lower,upper,label in RANGES:
        if lower<=score<=upper:
            return label
    return None


def create(period: str, evaluator: str, path: Path | None = None) -> str:
    if not period.strip() or not evaluator.strip():
        raise ValidationError('Indique periodo y evaluador.')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        con.execute('''INSERT INTO p1_autoevaluaciones(id,periodo,evaluador,instrumento)
                       VALUES (?,?,?,?)''',(key,period.strip(),evaluator.strip(),INSTRUMENT_VERSION))
        con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor)
                       VALUES (?,?,?,?)''',('autoevaluacion',key,'crear',evaluator.strip()))
    return key


def list_assessments(path:Path | None=None) -> list[dict]:
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('SELECT * FROM p1_autoevaluaciones ORDER BY creado_en DESC')]


def responses(assessment_id:str,path:Path|None=None) -> dict[int,dict]:
    with closing(connect(path)) as con:
        return {r['numero']:dict(r) for r in con.execute('SELECT * FROM p1_respuestas_autoevaluacion WHERE evaluacion_id=?',(assessment_id,))}


def save(assessment_id:str, number:int, rating:int|None, note:str, actor:str,path:Path|None=None)->None:
    if not 1<=number<=25:
        raise ValidationError('Criterio fuera de rango.')
    if rating is not None and (not isinstance(rating,int) or not 1<=rating<=5):
        raise ValidationError('La valoración debe estar entre 1 y 5.')
    if not actor.strip():
        raise ValidationError('Indique el responsable.')
    with transaction(path) as con:
        state=con.execute('SELECT estado FROM p1_autoevaluaciones WHERE id=?',(assessment_id,)).fetchone()
        if not state:
            raise ValidationError('Evaluación inexistente.')
        if state['estado']=='Finalizada':
            raise ValidationError('No es posible modificar evaluaciones finalizadas.')
        if rating is None:
            con.execute('DELETE FROM p1_respuestas_autoevaluacion WHERE evaluacion_id=? AND numero=?',(assessment_id,number))
        else:
            con.execute('''INSERT INTO p1_respuestas_autoevaluacion(evaluacion_id,numero,valor,observacion)
                           VALUES(?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
                           valor=excluded.valor, observacion=excluded.observacion''',
                        (assessment_id,number,rating,note.strip()))
        con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor)
                       VALUES(?,?,?,?)''',('autoevaluacion',assessment_id,'guardar_respuesta',actor.strip()))


def finalize(assessment_id:str,actor:str,path:Path|None=None) -> tuple[int,str]:
    if not actor.strip():
        raise ValidationError('Indique el responsable.')
    with transaction(path) as con:
        a=con.execute('SELECT estado FROM p1_autoevaluaciones WHERE id=?',(assessment_id,)).fetchone()
        if not a:raise ValidationError('Evaluación inexistente.')
        if a['estado']=='Finalizada':raise ValidationError('La evaluación ya está finalizada.')
        count,total=con.execute('''SELECT COUNT(*),SUM(valor) FROM p1_respuestas_autoevaluacion
                                   WHERE evaluacion_id=?''',(assessment_id,)).fetchone()
        if count!=25:
            raise ValidationError(f'Faltan {25-count} criterios por valorar. Guarde todas las respuestas antes de finalizar.')
        state=classification(total)
        con.execute('''UPDATE p1_autoevaluaciones SET estado='Finalizada', puntaje=?,clasificacion=?,
                       finalizada_en=CURRENT_TIMESTAMP WHERE id=?''',(total,state,assessment_id))
        con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor)
                       VALUES(?,?,?,?)''',('autoevaluacion',assessment_id,'finalizar',actor.strip()))
    return total,state

# V0.31: la evidencia se almacena separada de observaciones. Las funciones
# históricas anteriores siguen vigentes para no romper los módulos existentes.
def initialize(path:Path|None=None)->None:
    """Migración idempotente con respaldo previo de SQLite si falta la columna."""
    from datetime import datetime
    import sqlite3
    from .config import database_path
    target=Path(path) if path is not None else database_path()
    with closing(connect(target)) as con:
        fields={r['name'] for r in con.execute('PRAGMA table_info(p1_respuestas_autoevaluacion)')}
    if 'evidencia' in fields:return
    folder=target.parent/'respaldos_migracion'
    folder.mkdir(parents=True,exist_ok=True)
    filename=folder / f'{target.stem}_pre_v031_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.sqlite3'
    with closing(connect(target)) as source,closing(sqlite3.connect(str(filename))) as destination:
        source.backup(destination)
    with transaction(target) as con:
        fields={r['name'] for r in con.execute('PRAGMA table_info(p1_respuestas_autoevaluacion)')}
        if 'evidencia' not in fields:
            con.execute("ALTER TABLE p1_respuestas_autoevaluacion ADD COLUMN evidencia TEXT NOT NULL DEFAULT ''")


def save_dimension(assessment_id:str, dimension:int, values:list[tuple], actor:str,
                   path:Path|None=None)->None:
    """Guarda 5 preguntas o ninguna; evita guardar una dimensión incompleta a medias."""
    if not isinstance(dimension,int) or not 0<=dimension<5:
        raise ValidationError('Dimensión fuera de rango.')
    if len(values)!=5 or {r[0] for r in values}!={dimension*5+j for j in range(1,6)}:
        raise ValidationError('El formulario debe enviar las cinco preguntas de la dimensión.')
    actor=str(actor or '').strip()
    if not actor:raise ValidationError('Indique el responsable.')
    clean=[]
    for number,rating,note,evidence in values:
        if rating is not None and (not isinstance(rating,int) or not 1<=rating<=5):
            raise ValidationError('La valoración debe estar entre 1 y 5.')
        note=str(note or '').strip();evidence=str(evidence or '').strip()
        if len(note)>3000 or len(evidence)>3000:
            raise ValidationError('Observación y evidencia: máximo 3.000 caracteres.')
        clean.append((number,rating,note,evidence))
    initialize(path)
    with transaction(path) as con:
        status=con.execute('SELECT estado FROM p1_autoevaluaciones WHERE id=?',(assessment_id,)).fetchone()
        if not status:raise ValidationError('Evaluación inexistente.')
        if status['estado']=='Finalizada':raise ValidationError('La evaluación finalizada no puede modificarse.')
        for number,rating,note,evidence in clean:
            if rating is None:
                con.execute('DELETE FROM p1_respuestas_autoevaluacion WHERE evaluacion_id=? AND numero=?',(assessment_id,number))
            else:
                con.execute('''INSERT INTO p1_respuestas_autoevaluacion(evaluacion_id,numero,valor,observacion,evidencia)
                  VALUES(?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
                  valor=excluded.valor, observacion=excluded.observacion,evidencia=excluded.evidencia''',
                  (assessment_id,number,rating,note,evidence))
        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor) VALUES(?,?,?,?)',
                    ('autoevaluacion',assessment_id,f'guardar_dimension_{dimension+1}',actor))


def dimension_summary(assessment_id:str,path:Path|None=None)->list[dict]:
    data=responses(assessment_id,path)
    result=[]
    for idx,(name,_) in enumerate(DIMENSIONS):
        values=[data[n]['valor'] for n in range(idx*5+1,idx*5+6) if n in data]
        result.append({'Dimensión':name,'Respondidas':len(values),'Puntaje':sum(values) if len(values)==5 else None,
                       'Máximo':25,'Porcentaje':round(sum(values)/25*100) if len(values)==5 else None})
    return result


def assessment_export(assessment_id:str,path:Path|None=None)->dict:
    items=[r for r in list_assessments(path) if r['id']==assessment_id]
    if not items:raise ValidationError('Autoevaluación inexistente.')
    return {'evaluacion':items[0],'instrumento':'Adaptación interna CENS (no transcripción literal PMI)',
            'dimensiones':dimension_summary(assessment_id,path),
            'respuestas':[{'numero':n,'dimension':DIMENSIONS[(n-1)//5][0],
                'criterio':DIMENSIONS[(n-1)//5][1][(n-1)%5],**r}
                for n,r in sorted(responses(assessment_id,path).items())]}
