"""Autoevaluación de diez pasos: guía PMI 2025 y adaptación CENS histórica.

Instrumentos versionados: nunca se cambia la pregunta asociada a una respuesta previa.
Distinta de la madurez institucional anual y la madurez de los 26 servicios.
"""
from __future__ import annotations
import json, uuid, sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .storage import connect, transaction
from .config import database_path

CATALOG_PATH=Path(__file__).parent/'data'/'pmi_step_assessments_cens_v0390.json'
CATALOG=json.loads(CATALOG_PATH.read_text(encoding='utf8')) # Nunca cambia el instrumento histórico.
LEGACY_INSTRUMENT=CATALOG['instrument']
GUIDE_PATH=Path(__file__).parent/'data'/'pmi_guide_2025_exact_v03915.json'
GUIDE=json.loads(GUIDE_PATH.read_text(encoding='utf8'))
INSTRUMENT=GUIDE['id'] # Solo se asigna a nuevas evaluaciones.
COUNTS={i:sum(len(d['questions']) for d in CATALOG['steps'][str(i)]) for i in range(1,11)}
GUIDE_COUNTS={i:GUIDE['steps'][str(i)]['count'] for i in range(1,11)}
assert COUNTS==GUIDE_COUNTS, 'Los cuestionarios publicados deben conservar las 280 preguntas por paso'
assert list(COUNTS.values())==[25,25,25,35,30,35,20,30,25,30]
STEPS=('Generación de conciencia','Evaluación de necesidades','Propuesta de valor',
       'Desarrollo de servicios','Incorporación de servicios','Operación de servicios',
       'Monitoreo de servicios','Mejora de servicios','Entrega de valor','Reconocimiento del valor')

SCHEMA='''
CREATE TABLE IF NOT EXISTS pmi_step_evaluations (
 id TEXT PRIMARY KEY, paso INTEGER NOT NULL CHECK(paso BETWEEN 1 AND 10),
 periodo TEXT NOT NULL, evaluador TEXT NOT NULL, instrumento TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','Finalizada')),
 creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL, finalizado_en TEXT,
 version INTEGER NOT NULL DEFAULT 1, es_demo INTEGER NOT NULL DEFAULT 0 CHECK(es_demo IN (0,1)),
 origen_legacy TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pmi_eval_period_step ON pmi_step_evaluations(periodo,paso,estado);
CREATE TABLE IF NOT EXISTS pmi_step_answers (
 evaluacion_id TEXT NOT NULL REFERENCES pmi_step_evaluations(id) ON DELETE CASCADE,
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 35),
 valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 justificacion TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 actualizado_en TEXT NOT NULL, PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS pmi_step_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 evaluacion_id TEXT NOT NULL REFERENCES pmi_step_evaluations(id),
 paso INTEGER NOT NULL, accion TEXT NOT NULL, actor TEXT NOT NULL,
 detalle TEXT NOT NULL DEFAULT '', datos_previos_json TEXT NOT NULL DEFAULT '{}',
 fecha TEXT NOT NULL
);
'''
class ValidationError(ValueError):pass

def _now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def _text(val,field):
 s=str(val or '').strip()
 if not s:raise ValidationError('Indica '+field)
 return s

def _rows(sql,args=(),path=None):
 with closing(connect(path)) as c:return [dict(r) for r in c.execute(sql,args)]

def initialize(path=None):
 target=Path(path) if path is not None else database_path()
 with closing(connect(target)) as c:
  installed=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pmi_step_evaluations'").fetchone()
  client_table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pmo_clientes'").fetchone()
  # Respaldo único previo a la extensión en instalaciones con clientes existentes.
  if not installed and client_table and c.execute('SELECT 1 FROM pmo_clientes LIMIT 1').fetchone():
   archive=target.parent/'respaldos';archive.mkdir(parents=True,exist_ok=True)
   destination=archive/f'autoevaluaciones_antes_v0390_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")}.sqlite3'
   with sqlite3.connect(str(destination)) as out:c.backup(out)
  c.executescript(SCHEMA);c.commit()

def questions(step,instrument=None):
 """Recupera los enunciados correctos según el instrumento propio de la evaluación."""
 step=int(step)
 if step not in COUNTS:raise ValidationError('Paso fuera de rango')
 if instrument is None or instrument==INSTRUMENT:
  return GUIDE['steps'][str(step)]['sections']
 return CATALOG['steps'][str(step)]

def guide_info(step):
 """Textos y rangos transcritos de la guía proporcionada por el usuario."""
 step=int(step)
 if step not in COUNTS:raise ValidationError('Paso fuera de rango')
 return GUIDE['steps'][str(step)]

def instrument_name(instrument):
 return 'Guía PMI 2025' if instrument==INSTRUMENT else 'CENS adaptada · histórica'

def score_interpretation(step,score,instrument=None):
 """La interpretación PMI solo es equivalente para el cuestionario PMI 2025."""
 if score is None:return None
 data=guide_info(step)
 for r in data['bands']:
  if r['min']<=score<=r['max']:
   return {**r,'score':score,'source_equivalent':instrument==INSTRUMENT,'discrepancy':False}
 # La guía omite el rango 161–175 en el Paso 4; sin inventar una clasificación PMI.
 return {'label':'Sin rango publicado','min':None,'max':None,'score':score,'guidance':'La guía no clasifica esta puntuación; se requiere validar su tabla de interpretación.',
         'source_equivalent':instrument==INSTRUMENT,'discrepancy':True}

def create(step,period,evaluator,demo=False,path=None):
 step=int(step)
 if step not in COUNTS:raise ValidationError('Paso fuera de rango')
 period=_text(period,'el período/ciclo');evaluator=_text(evaluator,'el evaluador')
 eid=uuid.uuid4().hex;now=_now()
 with transaction(path) as c:
  c.execute('INSERT INTO pmi_step_evaluations(id,paso,periodo,evaluador,instrumento,creado_en,actualizado_en,es_demo) VALUES (?,?,?,?,?,?,?,?)',
            (eid,step,period,evaluator,INSTRUMENT,now,now,int(bool(demo))))
  c.execute('INSERT INTO pmi_step_audit(evaluacion_id,paso,accion,actor,detalle,fecha) VALUES (?,?,?,?,?,?)',(eid,step,'crear',evaluator,period,now))
 return eid

def list_evaluations(step=None,period=None,path=None):
 terms=[];args=[]
 if step is not None:terms.append('paso=?');args.append(int(step))
 if period is not None:terms.append('periodo=?');args.append(period)
 w=(' WHERE '+' AND '.join(terms)) if terms else ''
 return _rows('SELECT * FROM pmi_step_evaluations'+w+' ORDER BY actualizado_en DESC,creado_en DESC,id DESC',args,path)

def get(eid,path=None):
 rows=_rows('SELECT * FROM pmi_step_evaluations WHERE id=?',(eid,),path)
 if not rows:raise ValidationError('Autoevaluación inexistente')
 return rows[0]

def responses(eid,path=None):
 return {x['numero']:x for x in _rows('SELECT * FROM pmi_step_answers WHERE evaluacion_id=? ORDER BY numero',(eid,),path)}

def _snapshot(c,eid):
 h=c.execute('SELECT * FROM pmi_step_evaluations WHERE id=?',(eid,)).fetchone()
 return {'evaluation':dict(h), 'answers':[dict(x) for x in c.execute('SELECT * FROM pmi_step_answers WHERE evaluacion_id=? ORDER BY numero',(eid,))]}

def save_dimension(eid,dimension,entries,actor,path=None):
 actor=_text(actor,'el responsable')
 with transaction(path) as c:
  h=c.execute('SELECT * FROM pmi_step_evaluations WHERE id=?',(eid,)).fetchone()
  if not h:raise ValidationError('Autoevaluación inexistente')
  if h['estado']!='Borrador':raise ValidationError('Reabre la evaluación finalizada antes de modificar sus respuestas')
  dims=questions(h['paso'],h['instrumento']);dim=int(dimension)
  if dim<0 or dim>=len(dims):raise ValidationError('Dimensión fuera de rango')
  if not isinstance(entries,(list,tuple)) or len(entries)!=len(dims[dim]['questions']):raise ValidationError('Número de criterios incorrecto')
  before=_snapshot(c,eid)
  start=sum(len(x['questions']) for x in dims[:dim]);now=_now()
  for j,entry in enumerate(entries,1):
   if not isinstance(entry,(list,tuple)) or len(entry)!=3:raise ValidationError('Se requiere valoración, justificación y evidencia')
   value,note,evidence=entry;number=start+j
   if value in (None,'','Sin responder'):
    c.execute('DELETE FROM pmi_step_answers WHERE evaluacion_id=? AND numero=?',(eid,number))
   else:
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=5:raise ValidationError(f'Valor fuera de escala 1–5: criterio {number}')
    c.execute('''INSERT INTO pmi_step_answers(evaluacion_id,numero,valor,justificacion,evidencia,actualizado_en)
      VALUES (?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
      valor=excluded.valor,justificacion=excluded.justificacion,evidencia=excluded.evidencia,actualizado_en=excluded.actualizado_en''',
      (eid,number,value,str(note or '').strip(),str(evidence or '').strip(),now))
  c.execute('UPDATE pmi_step_evaluations SET actualizado_en=?,version=version+1 WHERE id=?',(now,eid))
  c.execute('INSERT INTO pmi_step_audit(evaluacion_id,paso,accion,actor,detalle,datos_previos_json,fecha) VALUES (?,?,?,?,?,?,?)',
            (eid,h['paso'],'guardar_dimension',actor,str(dim+1),json.dumps(before,ensure_ascii=False),now))

def update_metadata(eid,period,evaluator,actor,path=None):
 period=_text(period,'el período');evaluator=_text(evaluator,'el evaluador');actor=_text(actor,'el responsable del cambio')
 now=_now()
 with transaction(path) as c:
  h=c.execute('SELECT * FROM pmi_step_evaluations WHERE id=?',(eid,)).fetchone()
  if not h:raise ValidationError('Evaluación inexistente')
  if h['estado']!='Borrador':raise ValidationError('Reabre la evaluación antes de cambiar sus datos')
  before=_snapshot(c,eid)
  c.execute('UPDATE pmi_step_evaluations SET periodo=?,evaluador=?,actualizado_en=?,version=version+1 WHERE id=?',(period,evaluator,now,eid))
  c.execute('INSERT INTO pmi_step_audit(evaluacion_id,paso,accion,actor,detalle,datos_previos_json,fecha) VALUES (?,?,?,?,?,?,?)',
            (eid,h['paso'],'editar_cabecera',actor,f'{period} · {evaluator}',json.dumps(before,ensure_ascii=False),now))


def complete(eid,actor,path=None):
 actor=_text(actor,'el responsable');now=_now()
 with transaction(path) as c:
  h=c.execute('SELECT * FROM pmi_step_evaluations WHERE id=?',(eid,)).fetchone()
  if not h:raise ValidationError('Evaluación inexistente')
  if h['estado']!='Borrador':raise ValidationError('Esta evaluación ya está finalizada')
  result=c.execute('SELECT COUNT(*),SUM(valor) FROM pmi_step_answers WHERE evaluacion_id=?',(eid,)).fetchone()
  if result[0]!=COUNTS[h['paso']]:raise ValidationError(f'Faltan {COUNTS[h["paso"]]-result[0]} criterios por responder')
  c.execute('UPDATE pmi_step_evaluations SET estado=?,finalizado_en=?,actualizado_en=?,version=version+1 WHERE id=?',('Finalizada',now,now,eid))
  c.execute('INSERT INTO pmi_step_audit(evaluacion_id,paso,accion,actor,detalle,fecha) VALUES (?,?,?,?,?,?)',
            (eid,h['paso'],'finalizar',actor,f'Puntaje {result[1]}/{COUNTS[h["paso"]]*5}',now))
 return result[1]

def reopen(eid,actor,reason,path=None):
 actor=_text(actor,'el responsable');reason=_text(reason,'la justificación de reapertura');now=_now()
 with transaction(path) as c:
  h=c.execute('SELECT * FROM pmi_step_evaluations WHERE id=?',(eid,)).fetchone()
  if not h or h['estado']!='Finalizada':raise ValidationError('Solo se pueden reabrir evaluaciones finalizadas')
  before=_snapshot(c,eid)
  c.execute('UPDATE pmi_step_evaluations SET estado=?,actualizado_en=?,version=version+1 WHERE id=?',('Borrador',now,eid))
  c.execute('INSERT INTO pmi_step_audit(evaluacion_id,paso,accion,actor,detalle,datos_previos_json,fecha) VALUES (?,?,?,?,?,?,?)',
            (eid,h['paso'],'reabrir',actor,reason,json.dumps(before,ensure_ascii=False),now))

def detail(eid,path=None):
 h=get(eid,path);ans=responses(eid,path);n=COUNTS[h['paso']]
 answered=len(ans);score=sum(x['valor'] for x in ans.values()) if answered==n and h['estado']=='Finalizada' else None
 return {**h,'respuestas':ans,'respondidas':answered,'total':n,'puntaje':score,
         'promedio':score/n if score is not None else None,'maximo':n*5,'dimensiones':len(questions(h['paso'],h['instrumento'])),'interpretacion':score_interpretation(h['paso'],score,h['instrumento'])}

def audit(eid,path=None):return _rows('SELECT * FROM pmi_step_audit WHERE evaluacion_id=? ORDER BY id DESC',(eid,),path)

def periods(path=None):return [r['periodo'] for r in _rows('SELECT periodo FROM pmi_step_evaluations GROUP BY periodo ORDER BY MAX(actualizado_en) DESC',path=path)]

def consolidated(period,path=None):
 period=_text(period,'el período/ciclo')
 evaluations=list_evaluations(period=period,path=path)
 steps=[]
 for n in range(1,11):
  candidates=[e for e in evaluations if e['paso']==n and e['estado']=='Finalizada' and not e['es_demo']]
  picked=next((detail(e['id'],path) for e in candidates if detail(e['id'],path)['puntaje'] is not None),None)
  steps.append({'paso':n,'nombre':STEPS[n-1],'cantidad':COUNTS[n],
                'id':picked['id'] if picked else None,'puntaje':picked['puntaje'] if picked else None,
                'promedio':picked['promedio'] if picked else None,'evaluator':picked['evaluador'] if picked else '',
                'fecha':picked['finalizado_en'] if picked else None,
                'instrumento':picked['instrumento'] if picked else None,
                'interpretacion':picked['interpretacion'] if picked else None})
 done=[s for s in steps if s['promedio'] is not None]
 return {'periodo':period,'pasos':steps,'completos':len(done),'respondidas':sum(s['cantidad'] for s in done),
         'total':280,'indice':sum(s['promedio'] for s in done)/len(done) if done else None,
         'final':len(done)==10,'mixed_instruments':len({s['instrumento'] for s in steps if s['instrumento']})>1,
         'escala':'1–5','metodologia':'Promedio simple de los promedios de pasos completos, adaptación CENS; no un índice oficial PMI.'}

def export(eid,path=None):
 v=detail(eid,path)
 return {'schema':'pmo-cens-evaluacion-pmi-v0390','instrumento':v['instrumento'],
         'evaluacion':{k:val for k,val in v.items() if k!='respuestas'},
         'dimensiones':questions(v['paso'],v['instrumento']),'respuestas':list(v['respuestas'].values()),'auditoria':audit(eid,path)}

# Copia supervisada de antecedentes: nunca modifica la evaluación histórica.
# Los orígenes están definidos por código, no se aceptan nombres de tabla externos.
_LEGACY={
 1:('p1_autoevaluaciones','p1_respuestas_autoevaluacion','evaluacion_id','numero','valor','observacion','', 'evaluador','estado','Finalizada','periodo'),
 2:('p2_autoevaluaciones','p2_respuestas_autoevaluacion','evaluacion_id','numero','valor','observacion','evidencia','evaluador','estado','Finalizada',None),
 3:('p3_evaluaciones','p3_respuestas','evaluacion_id','numero','valor','observacion','evidencia','responsable','estado','Finalizada',None),
 4:('p4_evaluations','p4_answers','evaluacion_id','numero','valor','observacion','evidencia','responsable','estado','Finalizada',None),
 5:('p5_evaluations','p5_answers','evaluation_id','number','score','observation','evidence','owner','state','Finalizada',None),
 6:('p6_evaluaciones','p6_respuestas','evaluacion_id','numero','valor','observacion','evidencia','responsable','estado','Finalizada',None),
 7:('p7_evaluaciones','p7_respuestas','evaluacion_id','numero','valor','observacion','evidencia','responsable','estado','Archivada',None),
 9:('p9_evaluaciones','p9_respuestas','evaluacion_id','numero','valor','observacion','evidencia','responsable','estado','Archivada',None),
 10:('p10_evaluaciones','p10_respuestas','evaluacion_id','numero','valor','observacion','evidencia','responsable','estado','Archivada',None),
}

def legacy_available(step,path=None):
    step=int(step)
    if step not in _LEGACY:return []
    table,answers,foreign,num,score,note,evid,owner,status,final,period_col=_LEGACY[step]
    with closing(connect(path)) as c:
        if not c.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():return []
        result=[]
        for r in c.execute(f'SELECT * FROM {table} ORDER BY rowid DESC'):
            marker=f'{table}:{r["id"]}'
            if c.execute('SELECT 1 FROM pmi_step_evaluations WHERE origen_legacy=?',(marker,)).fetchone():continue
            result.append({'id':r['id'],'source':table,'owner':r[owner],
                           'period':r[period_col] if period_col else None,'state':r[status],
                           'score':r['puntaje'] if 'puntaje' in r.keys() else r['score'] if 'score' in r.keys() else None})
        return result

def import_legacy(step,legacy_id,period,actor,path=None):
    """Copia al estándar editable, sin alterar respuestas originales ni su historial."""
    step=int(step)
    if step not in _LEGACY:raise ValidationError('No existe un instrumento anterior importable para este paso')
    period=_text(period,'el período');actor=_text(actor,'el responsable')
    table,ans_table,foreign,num,score,note,evid,owner,status,final,period_col=_LEGACY[step]
    legacy_id=_text(legacy_id,'la evaluación original');marker=f'{table}:{legacy_id}'
    now=_now();new_id=uuid.uuid4().hex
    with transaction(path) as c:
        original=c.execute(f'SELECT * FROM {table} WHERE id=?',(legacy_id,)).fetchone()
        if not original:raise ValidationError('Evaluación histórica inexistente')
        if c.execute('SELECT 1 FROM pmi_step_evaluations WHERE origen_legacy=?',(marker,)).fetchone():
            raise ValidationError('Esta evaluación histórica ya fue copiada; selecciónala en el formulario')
        entries=[dict(r) for r in c.execute(f'SELECT * FROM {ans_table} WHERE {foreign}=? ORDER BY {num}',(legacy_id,))]
        seen=set()
        for r in entries:
            number=int(r[num]);value=int(r[score])
            if number not in range(1,COUNTS[step]+1) or number in seen or value not in range(1,6):
                raise ValidationError('Respuestas históricas incompatibles: no se importó ningún registro')
            seen.add(number)
        complete=len(seen)==COUNTS[step] and original[status]==final
        c.execute('''INSERT INTO pmi_step_evaluations(id,paso,periodo,evaluador,instrumento,estado,creado_en,actualizado_en,finalizado_en,origen_legacy)
                     VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  (new_id,step,period,actor,LEGACY_INSTRUMENT,'Finalizada' if complete else 'Borrador',now,now,now if complete else None,marker))
        for r in entries:
            c.execute('INSERT INTO pmi_step_answers(evaluacion_id,numero,valor,justificacion,evidencia,actualizado_en) VALUES (?,?,?,?,?,?)',
                      (new_id,int(r[num]),int(r[score]),str(r[note] or ''),str(r[evid] or '') if evid else '',now))
        c.execute('INSERT INTO pmi_step_audit(evaluacion_id,paso,accion,actor,detalle,fecha) VALUES (?,?,?,?,?,?)',
                  (new_id,step,'copiar_antecedente',actor,marker,now))
    return new_id
