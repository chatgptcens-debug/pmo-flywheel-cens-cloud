"""Paso 5: incorporación de servicios. Tablas SQLite aditivas y referencias inmutables.

La operación de solicitudes pertenece al Paso 6. Las respuestas PMI son juicios
manuales, no puntuaciones inferidas. Las preguntas son paráfrasis funcionales.
"""
from __future__ import annotations
import csv, io, json, uuid
from contextlib import closing
from datetime import datetime, timezone
from .storage import connect, transaction

NAV=('Plan de incorporación','Comunicación y formación','Pilotos y soporte','Adopción y transición','Evaluación metodológica PMI')
CHECKS=(('piloto','Validación del piloto'),('cliente','Aceptación del cliente'),('equipo','Responsables operativos definidos'),('documentos','Documentación y guías disponibles'),('soporte','Canales de soporte habilitados'),('ans','ANS vigentes y validados'),('traspaso','Evidencia del traspaso documentada'))
DIMENSIONS=(
('Preparación y compromiso del cliente',('Se identifican los grupos de clientes que utilizarán los servicios nuevos o mejorados.','La estrategia de compromiso considera necesidades y preocupaciones de cada grupo.','Se comunica oportunamente la oferta y el proceso de incorporación.','La retroalimentación recibida durante la incorporación se registra y se atiende.','Se promueve la participación de personas referentes que apoyan la adopción.')),
('Programa de formación',('Se analizan las necesidades de aprendizaje de los diferentes tipos de clientes.','Se dispone de formación diferenciada según el rol y nivel de experiencia.','Hay guías, tutoriales o materiales prácticos para utilizar los servicios.','Se combinan opciones de autoaprendizaje y sesiones acompañadas.','Se verifica que los usuarios desarrollen las competencias de uso necesarias.')),
('Pilotos y retroalimentación',('Los pilotos incorporan participantes de distintos segmentos de clientes.','Cada piloto cuenta con objetivos, alcance y criterios de éxito definidos.','Se proporciona acompañamiento reforzado a los participantes del piloto.','Se recopilan datos cuantitativos y opiniones de los participantes.','Los hallazgos de los pilotos se analizan y se traducen en mejoras.')),
('Infraestructura de soporte',('Los niveles y canales de apoyo están definidos y son accesibles.','Existe información de consulta para resolver dudas frecuentes.','Se ofrecen canales apropiados para recibir consultas y solicitudes de ayuda.','El equipo responsable de soporte está preparado para atender a los usuarios.','Se promueve el intercambio de experiencias y conocimiento entre usuarios.')),
('Monitoreo y evaluación',('Existen indicadores y criterios de éxito para evaluar la incorporación.','Se visualiza la evolución del uso y adopción mediante reportes o tableros.','Los datos de utilización y participación se recopilan de forma verificable.','Se realizan revisiones con los clientes sobre resultados y dificultades.','Se ajustan los planes de incorporación a partir de datos y opiniones.')),
('Transición a operación',('Se han definido condiciones observables para considerar exitosa la incorporación.','Existe un plan de transición con fechas, recursos y responsables.','Se transfiere el conocimiento necesario al equipo que prestará los servicios.','La continuidad del soporte y del monitoreo posterior está prevista.','Se comunica a los clientes cómo funcionará el servicio después de la transición.')))
QUESTIONS=tuple(question for _,qs in DIMENSIONS for question in qs)
SCHEMA='''
CREATE TABLE IF NOT EXISTS p5_services (
 id TEXT PRIMARY KEY, codigo TEXT NOT NULL UNIQUE COLLATE NOCASE,nombre TEXT NOT NULL,
 descripcion TEXT NOT NULL DEFAULT '', cliente TEXT NOT NULL DEFAULT '', responsable_p4 TEXT NOT NULL DEFAULT '',
 version_p4 TEXT NOT NULL DEFAULT '', source_schema TEXT NOT NULL, source_json TEXT NOT NULL,
 importado_en TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0 CHECK(demo IN (0,1))
);
CREATE TABLE IF NOT EXISTS p5_plans (
 service_id TEXT PRIMARY KEY REFERENCES p5_services(id) ON DELETE CASCADE,
 owner TEXT NOT NULL DEFAULT '', groups_target TEXT NOT NULL DEFAULT '', strategy TEXT NOT NULL DEFAULT '',
 launch_date TEXT NOT NULL DEFAULT '', resources TEXT NOT NULL DEFAULT '', risks TEXT NOT NULL DEFAULT '',
 communication TEXT NOT NULL DEFAULT '', success_criteria TEXT NOT NULL DEFAULT '',
 milestones_json TEXT NOT NULL DEFAULT '[]', approved_by TEXT NOT NULL DEFAULT '',
 approved_at TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p5_preplans (
 service_id TEXT PRIMARY KEY, snapshot_name TEXT NOT NULL DEFAULT '',
 owner TEXT NOT NULL DEFAULT '', groups_target TEXT NOT NULL DEFAULT '', strategy TEXT NOT NULL DEFAULT '',
 launch_date TEXT NOT NULL DEFAULT '', resources TEXT NOT NULL DEFAULT '', risks TEXT NOT NULL DEFAULT '',
 communication TEXT NOT NULL DEFAULT '', success_criteria TEXT NOT NULL DEFAULT '',
 milestones_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p5_activities (
 id TEXT PRIMARY KEY,service_id TEXT NOT NULL REFERENCES p5_services(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('Comunicación','Formación')),title TEXT NOT NULL,
 date TEXT NOT NULL DEFAULT '', audience TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
 invited INTEGER,attendees INTEGER,status TEXT NOT NULL DEFAULT 'Programada',
 materials TEXT NOT NULL DEFAULT '',evidence TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,
 CHECK(invited IS NULL OR invited>=0),CHECK(attendees IS NULL OR attendees>=0),
 CHECK(invited IS NULL OR attendees IS NULL OR attendees<=invited)
);
CREATE TABLE IF NOT EXISTS p5_pilots (
 id TEXT PRIMARY KEY,service_id TEXT NOT NULL REFERENCES p5_services(id) ON DELETE CASCADE,
 title TEXT NOT NULL,client TEXT NOT NULL DEFAULT '',start_date TEXT NOT NULL DEFAULT '',
 end_date TEXT NOT NULL DEFAULT '',owner TEXT NOT NULL DEFAULT '',criteria TEXT NOT NULL DEFAULT '',
 results TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'Planificado',satisfaction INTEGER,
 evidence TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,
 CHECK(satisfaction IS NULL OR satisfaction BETWEEN 1 AND 10)
);
CREATE TABLE IF NOT EXISTS p5_issues (
 id TEXT PRIMARY KEY,service_id TEXT NOT NULL REFERENCES p5_services(id) ON DELETE CASCADE,
 pilot_id TEXT,kind TEXT NOT NULL DEFAULT 'Incidencia',title TEXT NOT NULL,
 owner TEXT NOT NULL DEFAULT '',action TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'Abierta',
 evidence TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p5_adoptions (
 service_id TEXT PRIMARY KEY REFERENCES p5_services(id) ON DELETE CASCADE,
 target_people INTEGER,trained_people INTEGER,enabled_clients INTEGER,active_clients INTEGER,
 checks_json TEXT NOT NULL,exemption_reason TEXT NOT NULL DEFAULT '',evidence TEXT NOT NULL DEFAULT '',
 authorized_by TEXT NOT NULL DEFAULT '',authorized_at TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,
 CHECK(target_people IS NULL OR target_people>=0), CHECK(trained_people IS NULL OR trained_people>=0),
 CHECK(enabled_clients IS NULL OR enabled_clients>=0),CHECK(active_clients IS NULL OR active_clients>=0),
 CHECK(target_people IS NULL OR trained_people IS NULL OR trained_people<=target_people),
 CHECK(enabled_clients IS NULL OR active_clients IS NULL OR active_clients<=enabled_clients)
);
CREATE TABLE IF NOT EXISTS p5_evaluations (
 id TEXT PRIMARY KEY,version INTEGER NOT NULL UNIQUE,owner TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'Borrador' CHECK(state IN ('Borrador','Finalizada')),
 score INTEGER,classification TEXT,created_at TEXT NOT NULL,finished_at TEXT
);
CREATE TABLE IF NOT EXISTS p5_answers (
 evaluation_id TEXT NOT NULL REFERENCES p5_evaluations(id) ON DELETE CASCADE,
 number INTEGER NOT NULL CHECK(number BETWEEN 1 AND 30),score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
 observation TEXT NOT NULL DEFAULT '',evidence TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,
 PRIMARY KEY(evaluation_id,number)
);
CREATE TABLE IF NOT EXISTS p5_routes (
 service_id TEXT PRIMARY KEY REFERENCES p5_services(id) ON DELETE CASCADE,
 route_type TEXT NOT NULL CHECK(route_type IN ('Pilotada','Gradual','Simplificada')),
 rationale TEXT NOT NULL DEFAULT '', rollout TEXT NOT NULL DEFAULT '',
 owner TEXT NOT NULL DEFAULT '',client_groups TEXT NOT NULL DEFAULT '',
 support_notes TEXT NOT NULL DEFAULT '',
 retrospective INTEGER NOT NULL DEFAULT 0 CHECK(retrospective IN (0,1)),
 reconstruction_note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p5_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT,entity TEXT NOT NULL,entity_id TEXT NOT NULL,
 action TEXT NOT NULL,actor TEXT NOT NULL,details TEXT NOT NULL DEFAULT '{}',at TEXT NOT NULL
);
'''
class ValidationError(ValueError):pass

def _uid():return str(uuid.uuid4())
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def _json(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,default=str)
def _text(x):return str(x or '').strip()
def _required(x,label):
 v=_text(x)
 if not v:raise ValidationError(f'Campo requerido: {label}.')
 return v

def _rows(sql,params=(),path=None):
 with closing(connect(path)) as c:return [dict(x) for x in c.execute(sql,params).fetchall()]
def _row(sql,params=(),path=None):
 with closing(connect(path)) as c:
  r=c.execute(sql,params).fetchone();return dict(r) if r else None

def _audit(c,entity,identifier,action,actor='Equipo PMO',details=None):
 c.execute('INSERT INTO p5_audit(entity,entity_id,action,actor,details,at) VALUES(?,?,?,?,?,?)',(entity,identifier,action,_text(actor) or 'Equipo PMO',_json(details or {}),now()))

def initialize(path=None):
 with closing(connect(path)) as c:
  c.executescript(SCHEMA)
  c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (10)')
  c.commit()

def services(path=None):return _rows('SELECT * FROM p5_services ORDER BY codigo',path=path)
def service(id,path=None):return _row('SELECT * FROM p5_services WHERE id=?',(id,),path)
def plan(id,path=None):return _row('SELECT * FROM p5_plans WHERE service_id=?',(id,),path)
def adoption(id,path=None):return _row('SELECT * FROM p5_adoptions WHERE service_id=?',(id,),path)
def activities(path=None):return _rows('SELECT * FROM p5_activities ORDER BY date DESC,id DESC',path=path)
def pilots(path=None):return _rows('SELECT * FROM p5_pilots ORDER BY start_date DESC,id DESC',path=path)
def issues(path=None):return _rows('SELECT * FROM p5_issues ORDER BY updated_at DESC,id DESC',path=path)
def audit(path=None):return _rows('SELECT * FROM p5_audit ORDER BY id DESC',path=path)

def _incoming(payload):
 if not isinstance(payload,dict):raise ValidationError('El expediente debe ser un objeto JSON.')
 schema=payload.get('schema')
 if schema=='PMO-FLYWHEEL-CENS-paso5-input-v1':items=payload.get('services')
 elif schema=='PMO-CENS-P4-CATALOGO-v1':items=payload.get('services')
 elif schema=='PMO-FLYWHEEL-CENS-paso4-catalog-v1':items=payload.get('services')
 else:raise ValidationError('Se espera transferencia Paso 4 o catálogo compatible.')
 if not isinstance(items,list):raise ValidationError('La lista de servicios no es válida.')
 seen=set();out=[]
 for n,s in enumerate(items,1):
  if not isinstance(s,dict):raise ValidationError(f'Fila {n}: servicio inválido.')
  if s.get('estado')!='Aprobado' or s.get('demo') or s.get('demostrativo'):
   raise ValidationError(f'Fila {n}: solo se admiten servicios aprobados, no demostrativos.')
  code=_required(s.get('codigo'),f'código fila {n}');_required(s.get('nombre'),f'nombre fila {n}')
  if code.casefold() in seen:raise ValidationError(f'Código duplicado en el archivo: {code}.')
  seen.add(code.casefold());out.append(s)
 return schema,out

def import_step4(payload,path=None,actor='Equipo PMO'):
 schema,items=_incoming(payload)
 added=existing=0
 with transaction(path) as c:
  for s in items:
   code=_text(s['codigo'])
   if c.execute('SELECT 1 FROM p5_services WHERE codigo=? COLLATE NOCASE',(code,)).fetchone():
    existing+=1;continue
   key=_text(s.get('id')) or _uid()
   if c.execute('SELECT 1 FROM p5_services WHERE id=?',(key,)).fetchone():
    key=_uid()
   c.execute('''INSERT INTO p5_services(id,codigo,nombre,descripcion,cliente,responsable_p4,version_p4,source_schema,source_json,importado_en)
       VALUES(?,?,?,?,?,?,?,?,?,?)''',(key,code,_text(s['nombre']),_text(s.get('descripcion')),_text(s.get('cliente')),_text(s.get('responsable')),
       _text(s.get('actualizado_en') or payload.get('exportedAt')) ,schema,_json(s),now()))
   draft=c.execute('SELECT * FROM p5_preplans WHERE service_id=?',(key,)).fetchone()
   if draft:
    fields=('owner','groups_target','strategy','launch_date','resources','risks','communication','success_criteria')
    vals=[draft[k] for k in fields]
    c.execute('INSERT INTO p5_plans(service_id,'+','.join(fields)+',milestones_json,updated_at) VALUES ('+
              ','.join('?' for _ in range(len(fields)+3))+')', (key,*vals,draft['milestones_json'],now()))
    c.execute('DELETE FROM p5_preplans WHERE service_id=?',(key,))
   else:
    c.execute('INSERT INTO p5_plans(service_id,groups_target,milestones_json,updated_at) VALUES(?,?,?,?)',(key,_text(s.get('cliente')),'[]',now()))
   c.execute('INSERT INTO p5_adoptions(service_id,checks_json,updated_at) VALUES(?,?,?)',(key,_json({k:'pendiente' for k,_ in CHECKS}),now()))
   _audit(c,'service',key,'import-step4',actor,{'source_code':code,'source_schema':schema})
   added+=1
 return {'nuevos':added,'existentes':existing,'total':len(items)}

def import_step4_direct(path=None):
 from . import step4
 return import_step4(step4.step5_transfer(path),path=path,actor='Importación SQLite')

PREPLAN_FIELDS=('owner','groups_target','strategy','launch_date','resources','risks','communication','success_criteria')

def preplan(sid,path=None):
 return _row('SELECT * FROM p5_preplans WHERE service_id=?',(sid,),path)

def preplans(path=None):
 return _rows('SELECT * FROM p5_preplans ORDER BY updated_at DESC',path=path)

def save_preplan(sid,data,path=None):
 """Plan de diseño sin autorización. No crea p5_services ni cambia estados del Paso 4."""
 from . import step4
 origin=step4.service(sid,path)
 if not origin:raise ValidationError('El servicio de origen no existe en Paso 4.')
 if service(sid,path):raise ValidationError('Este servicio ya fue incorporado; edita su plan del Paso 5.')
 old=preplan(sid,path) or {}
 row={key:_text(data.get(key,old.get(key,''))) for key in PREPLAN_FIELDS}
 milestones=data.get('milestones',json.loads(old.get('milestones_json') or '[]'))
 if not isinstance(milestones,list):raise ValidationError('Los hitos deben ser una lista.')
 for item in milestones:
  if not isinstance(item,dict) or not _text(item.get('title')):raise ValidationError('Cada hito debe tener un título.')
 with transaction(path) as c:
  cols=['service_id','snapshot_name',*PREPLAN_FIELDS,'milestones_json','updated_at']
  vals=(sid,origin['nombre'],*(row[k] for k in PREPLAN_FIELDS),_json(milestones),now())
  c.execute('INSERT INTO p5_preplans ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+') ON CONFLICT(service_id) DO UPDATE SET '+
            ','.join(f'{k}=excluded.{k}' for k in cols[1:]), vals)
  _audit(c,'preplan',sid,'save','Equipo PMO',{'preliminar':True})
 return sid

def save_plan(sid,data,path=None,actor='Equipo PMO'):
 if not service(sid,path):raise ValidationError('Servicio no encontrado.')
 old=plan(sid,path)
 if old and old['approved_at']:raise ValidationError('El plan está aprobado. No se modifica sin reabrirlo con trazabilidad.')
 milestones=data.get('milestones',json.loads((old or {}).get('milestones_json') or '[]'))
 if not isinstance(milestones,list):raise ValidationError('Los hitos deben ser una lista.')
 for m in milestones:
  if not isinstance(m,dict) or not _text(m.get('title')):raise ValidationError('Cada hito debe tener un título.')
 record={key:_text(data.get(key,(old or {}).get(key,''))) for key in ('owner','groups_target','strategy','launch_date','resources','risks','communication','success_criteria','evidence')}
 with transaction(path) as c:
  c.execute('''UPDATE p5_plans SET owner=?,groups_target=?,strategy=?,launch_date=?,resources=?,risks=?,communication=?,success_criteria=?,milestones_json=?,evidence=?,updated_at=? WHERE service_id=?''',
   tuple(record[k] for k in ('owner','groups_target','strategy','launch_date','resources','risks','communication','success_criteria'))+(_json(milestones),record['evidence'],now(),sid))
  _audit(c,'plan',sid,'save',actor)

def add_milestone(sid,title,date='',path=None):
 p=plan(sid,path)
 if not p:raise ValidationError('No existe plan.')
 ms=json.loads(p['milestones_json']);ms.append({'id':_uid(),'title':_required(title,'hito'),'date':_text(date),'done':False})
 save_plan(sid,{'milestones':ms},path)
def set_milestone(sid,mid,done,path=None):
 p=plan(sid,path)
 if not p:raise ValidationError('Plan no encontrado.')
 ms=json.loads(p['milestones_json']);found=False
 for m in ms:
  if m['id']==mid:m['done']=bool(done);found=True
 if not found:raise ValidationError('Hito inexistente.')
 save_plan(sid,{'milestones':ms},path)

def approve_plan(sid,approver,evidence,path=None):
 p=plan(sid,path)
 if not p:raise ValidationError('Plan inexistente.')
 for field,title in [('owner','responsable'),('groups_target','clientes destinatarios'),('strategy','estrategia'),('launch_date','fecha de lanzamiento'),('resources','recursos'),('risks','riesgos'),('success_criteria','criterios de éxito')]:
  _required(p.get(field),title)
 ms=json.loads(p['milestones_json'])
 if not ms:raise ValidationError('Registra al menos un hito.')
 by=_required(approver,'responsable de la aprobación');ev=_required(evidence,'evidencia de aprobación')
 with transaction(path) as c:
  c.execute('UPDATE p5_plans SET approved_by=?,approved_at=?,evidence=?,updated_at=? WHERE service_id=?',(by,now(),ev,now(),sid))
  _audit(c,'plan',sid,'approved',by,{'evidence':ev})

def save_activity(data,key=None,path=None):
 sid=_required(data.get('service_id'),'servicio')
 if not service(sid,path):raise ValidationError('Servicio no encontrado.')
 kind=_required(data.get('kind'),'tipo')
 if kind not in ('Formación','Comunicación'):raise ValidationError('Tipo de actividad inválido.')
 invited=data.get('invited');attended=data.get('attendees')
 def nn(v,name):
  if v in (None,''):return None
  try:n=int(v)
  except (ValueError,TypeError):raise ValidationError(f'{name} debe ser entero.')
  if n<0:raise ValidationError(f'{name} no puede ser negativo.')
  return n
 invited=nn(invited,'Convocados');attended=nn(attended,'Asistentes')
 if invited is not None and attended is not None and attended>invited:raise ValidationError('Asistentes no pueden superar convocados.')
 fields=(sid,kind,_required(data.get('title'),'actividad'),_text(data.get('date')),_text(data.get('audience')),_text(data.get('owner')),invited,attended,_text(data.get('status')) or 'Programada',_text(data.get('materials')),_text(data.get('evidence')),now())
 with transaction(path) as c:
  if key:
   if not c.execute('SELECT 1 FROM p5_activities WHERE id=?',(key,)).fetchone():raise ValidationError('Actividad no encontrada.')
   c.execute('''UPDATE p5_activities SET service_id=?,kind=?,title=?,date=?,audience=?,owner=?,invited=?,attendees=?,status=?,materials=?,evidence=?,updated_at=? WHERE id=?''',(*fields,key))
  else:
   key=_uid();c.execute('INSERT INTO p5_activities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(key,*fields))
  _audit(c,'activity',key,'save')
 return key

def save_pilot(data,key=None,path=None):
 sid=_required(data.get('service_id'),'servicio')
 if not service(sid,path):raise ValidationError('Servicio no encontrado.')
 satisfaction=data.get('satisfaction')
 if satisfaction in (None,''):satisfaction=None
 else:
  try:satisfaction=int(satisfaction)
  except (ValueError,TypeError):raise ValidationError('Satisfacción entre 1 y 10.')
  if not 1<=satisfaction<=10:raise ValidationError('Satisfacción entre 1 y 10.')
 fields=(sid,_required(data.get('title'),'piloto'),_text(data.get('client')),_text(data.get('start_date')),_text(data.get('end_date')),
         _text(data.get('owner')),_text(data.get('criteria')),_text(data.get('results')),_text(data.get('status')) or 'Planificado',satisfaction,_text(data.get('evidence')),now())
 with transaction(path) as c:
  if key:
   if not c.execute('SELECT 1 FROM p5_pilots WHERE id=?',(key,)).fetchone():raise ValidationError('Piloto no encontrado.')
   c.execute('''UPDATE p5_pilots SET service_id=?,title=?,client=?,start_date=?,end_date=?,owner=?,criteria=?,results=?,status=?,satisfaction=?,evidence=?,updated_at=? WHERE id=?''',(*fields,key))
  else:key=_uid();c.execute('INSERT INTO p5_pilots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(key,*fields))
  _audit(c,'pilot',key,'save')
 return key

def save_issue(data,key=None,path=None):
 sid=_required(data.get('service_id'),'servicio')
 if not service(sid,path):raise ValidationError('Servicio no encontrado.')
 fields=(sid,_text(data.get('pilot_id')),_text(data.get('kind')) or 'Incidencia',_required(data.get('title'),'incidencia'),
         _text(data.get('owner')),_text(data.get('action')),_text(data.get('status')) or 'Abierta',_text(data.get('evidence')),now())
 with transaction(path) as c:
  if key:
   if not c.execute('SELECT 1 FROM p5_issues WHERE id=?',(key,)).fetchone():raise ValidationError('Incidencia no encontrada.')
   c.execute('''UPDATE p5_issues SET service_id=?,pilot_id=?,kind=?,title=?,owner=?,action=?,status=?,evidence=?,updated_at=? WHERE id=?''',(*fields,key))
  else:key=_uid();c.execute('INSERT INTO p5_issues VALUES(?,?,?,?,?,?,?,?,?,?)',(key,*fields))
  _audit(c,'issue',key,'save')
 return key

def _count(v,name):
 if v in (None,''):return None
 try:x=int(v)
 except (ValueError,TypeError):raise ValidationError(f'{name} debe ser entero.')
 if x<0:raise ValidationError(f'{name} no puede ser negativo.')
 return x

def save_adoption(sid,data,path=None):
 old=adoption(sid,path)
 if not old:raise ValidationError('Servicio no encontrado.')
 if old['authorized_at']:raise ValidationError('La transición está autorizada y congelada. No puede editarse.')
 t=_count(data.get('target_people'),'Población objetivo');trained=_count(data.get('trained_people'),'Personas capacitadas')
 enabled=_count(data.get('enabled_clients'),'Clientes habilitados');active=_count(data.get('active_clients'),'Clientes activos')
 if t is not None and trained is not None and trained>t:raise ValidationError('Capacitados supera población objetivo.')
 if enabled is not None and active is not None and active>enabled:raise ValidationError('Activos supera clientes habilitados.')
 checks=data.get('checks',json.loads(old['checks_json']))
 if set(checks)!=set(dict(CHECKS)) or any(x not in ('pendiente','cumple','na') for x in checks.values()):
  raise ValidationError('Los siete controles de transición deben tener un estado válido.')
 reason=_text(data.get('exemption_reason'));evidence=_text(data.get('evidence'))
 if 'na' in checks.values() and not reason:raise ValidationError('Los controles no aplicables deben justificarse.')
 with transaction(path) as c:
  c.execute('''UPDATE p5_adoptions SET target_people=?,trained_people=?,enabled_clients=?,active_clients=?,checks_json=?,exemption_reason=?,evidence=?,updated_at=? WHERE service_id=?''',
   (t,trained,enabled,active,_json(checks),reason,evidence,now(),sid))
  _audit(c,'adoption',sid,'save')

def readiness(sid,path=None):
 p=plan(sid,path);a=adoption(sid,path);block=[]
 if not p or not p['approved_by'] or not p['approved_at']:block.append('Plan sin aprobación formal')
 if not a:block.append('Sin evaluación de transición')
 else:
  checks=json.loads(a['checks_json'])
  for k,title in CHECKS:
   if checks.get(k) not in ('cumple','na'):block.append(title)
   elif checks[k]=='na' and not a['exemption_reason']:block.append('No aplica sin justificación')
  if not a['evidence']:block.append('Evidencia de transición')
 if any(x['service_id']==sid and x['status'] not in ('Resuelta','Descartada') for x in issues(path)):
  block.append('Incidencias abiertas')
 return {'eligible':not block,'blockers':block,'authorized':bool(a and a['authorized_at'])}

def authorize(sid,actor,path=None):
 sr=service(sid,path)
 if not sr or sr['demo']:raise ValidationError('No se autoriza una demostración como incorporación real.')
 r=readiness(sid,path)
 if not r['eligible']:raise ValidationError('No puede autorizarse: '+', '.join(r['blockers']))
 if r['authorized']:raise ValidationError('La transición ya está autorizada.')
 who=_required(actor,'responsable de autorización')
 with transaction(path) as c:
  c.execute('UPDATE p5_adoptions SET authorized_by=?,authorized_at=?,updated_at=? WHERE service_id=?',(who,now(),now(),sid))
  _audit(c,'adoption',sid,'authorized',who)

def aggregates(path=None):
 ad=_rows('SELECT * FROM p5_adoptions',path=path)
 targets=[x for x in ad if x['target_people'] and x['trained_people'] is not None]
 enabled=[x for x in ad if x['enabled_clients'] and x['active_clients'] is not None]
 ps=pilots(path)
 return {'training':(sum(x['trained_people'] for x in targets),sum(x['target_people'] for x in targets)),
         'adoption':(sum(x['active_clients'] for x in enabled),sum(x['enabled_clients'] for x in enabled)),
         'pilots':(sum(x['status'] in ('Completado','Validado') for x in ps),len(ps)),
         'ready':sum(bool(x['authorized_at']) for x in ad)}

def classification(score):
 if score is None:return None
 if not 30<=score<=150:raise ValidationError('Puntaje fuera del rango 30–150.')
 if score<=58:return 'Crítico'
 if score<=88:return 'Pobre'
 if score<=113:return 'Promedio'
 if score<=133:return 'Bien'
 return 'Excelente'

def evaluations(path=None):return _rows('SELECT * FROM p5_evaluations ORDER BY version DESC',path=path)
def evaluation(eid,path=None):return _row('SELECT * FROM p5_evaluations WHERE id=?',(eid,),path)
def answers(eid,path=None):return _rows('SELECT * FROM p5_answers WHERE evaluation_id=? ORDER BY number',(eid,),path)
def new_evaluation(owner,path=None):
 owner=_required(owner,'responsable')
 with transaction(path) as c:
  v=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM p5_evaluations').fetchone()[0]
  key=_uid();c.execute('INSERT INTO p5_evaluations(id,version,owner,created_at) VALUES(?,?,?,?)',(key,v,owner,now()))
  _audit(c,'evaluation',key,'create',owner)
 return key

def save_answer(eid,num,score,observation='',evidence='',path=None):
 e=evaluation(eid,path)
 if not e or e['state']=='Finalizada':raise ValidationError('Evaluación no encontrada o finalizada.')
 if not 1<=int(num)<=30 or not 1<=int(score)<=5:raise ValidationError('Pregunta o puntuación inválida.')
 with transaction(path) as c:
  c.execute('''INSERT INTO p5_answers(evaluation_id,number,score,observation,evidence,updated_at)
     VALUES(?,?,?,?,?,?) ON CONFLICT(evaluation_id,number) DO UPDATE SET
     score=excluded.score,observation=excluded.observation,evidence=excluded.evidence,updated_at=excluded.updated_at''',
     (eid,int(num),int(score),_text(observation),_text(evidence),now()))

def evaluation_summary(eid,path=None):
 ans=answers(eid,path);values={a['number']:a['score'] for a in ans}
 dims=[{'title':name,'answered':sum(n in values for n in range(i*5+1,i*5+6)),
  'score':sum(values.get(n,0) for n in range(i*5+1,i*5+6))} for i,(name,_) in enumerate(DIMENSIONS)]
 complete=len(values)==30;total=sum(values.values())
 return {'answered':len(values),'score':total if complete else None,'classification':classification(total) if complete else None,'dimensions':dims}

def finish_evaluation(eid,path=None):
 e=evaluation(eid,path)
 if not e or e['state']=='Finalizada':raise ValidationError('Evaluación inexistente o finalizada.')
 result=evaluation_summary(eid,path)
 if result['answered']!=30:raise ValidationError('Deben completarse las 30 preguntas.')
 with transaction(path) as c:
  c.execute('UPDATE p5_evaluations SET state=?,score=?,classification=?,finished_at=? WHERE id=?',('Finalizada',result['score'],result['classification'],now(),eid))
  _audit(c,'evaluation',eid,'finish',e['owner'],result)
 return result

def export_step6(path=None):
 eligible=[]
 for s in services(path):
  if s['demo']:continue
  ready=readiness(s['id'],path)
  if not ready['authorized'] or not ready['eligible']:continue
  a=adoption(s['id'],path)
  original=json.loads(s['source_json'])
  eligible.append({'id':s['id'],'codigo':s['codigo'],'nombre':s['nombre'],'descripcion':s['descripcion'],
    'responsable':s['responsable_p4'],'estado':'Aprobado','actualizado_en':s['version_p4'],
    '_paso5Transition':{'authorizedAt':a['authorized_at'],'authorizedBy':a['authorized_by'],
       'evidence':a['evidence'],'step4Id':original.get('id'),'step4Version':s['version_p4']}})
 return {'schema':'PMO-FLYWHEEL-CENS-paso6-input-v1','exportedAt':now(),
   'source':'Paso 5 · Incorporación de servicios','services':eligible}

def export_csv(kind,path=None):
 catalog={'plans':_rows('SELECT s.codigo,s.nombre,p.* FROM p5_services s JOIN p5_plans p ON s.id=p.service_id',path=path),
  'activities':activities(path),'pilots':pilots(path),'issues':issues(path),
  'adoption':_rows('SELECT s.codigo,s.nombre,a.* FROM p5_services s JOIN p5_adoptions a ON s.id=a.service_id',path=path)}
 if kind not in catalog:raise ValidationError('Reporte desconocido.')
 data=catalog[kind]
 if kind in ('plans','adoption'):
  from .public_codes import code as public_code
  # El ID de Paso 5 es idéntico al de Paso 4 cuando se incorpora directamente.
  for row in data:
   row['codigo_publico']=public_code('servicio',row.get('service_id'),path)
 f=io.StringIO();cols=list(data[0]) if data else ['sin_registros']
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(data)
 return f.getvalue().encode('utf-8-sig')

def backup(path=None):
 tables=('p5_services','p5_plans','p5_preplans','p5_activities','p5_pilots','p5_issues','p5_adoptions','p5_evaluations','p5_answers','p5_routes','p5_audit')
 return {'schema':'PMO-FLYWHEEL-CENS-paso5-backup-v1','createdAt':now(),
         'tables':{t:_rows('SELECT * FROM '+t,path=path) for t in tables}}

def restore_backup(payload,confirm=False,path=None):
 if not confirm:raise ValidationError('La restauración requiere confirmación.')
 if not isinstance(payload,dict) or payload.get('schema')!='PMO-FLYWHEEL-CENS-paso5-backup-v1':raise ValidationError('Respaldo incompatible.')
 data=payload.get('tables')
 if not isinstance(data,dict):raise ValidationError('Datos incompletos.')
 names=('p5_services','p5_plans','p5_preplans','p5_activities','p5_pilots','p5_issues','p5_adoptions','p5_evaluations','p5_answers','p5_routes','p5_audit')
 # Compatible con respaldos anteriores a V0.39.21 sin la tabla de rutas.
 optional={'p5_preplans','p5_routes'}
 if not set(data).issubset(set(names)) or set(names)-set(data)-optional:
  raise ValidationError('El respaldo debe incluir todas las tablas obligatorias Paso 5.')
 data={'p5_preplans':[],'p5_routes':[],**data}
 with transaction(path) as c:
  for name in reversed(names):c.execute('DELETE FROM '+name)
  for name in names:
   cols=[x['name'] for x in c.execute('PRAGMA table_info('+name+')')]
   for item in data[name]:
    if not isinstance(item,dict) or set(item)!=set(cols):raise ValidationError('Estructura de respaldo incompatible: '+name)
    c.execute('INSERT INTO '+name+'('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',tuple(item[col] for col in cols))
 return True

# V0.39.21: API aditiva para rutas por servicio, no altera los gates existentes.
from .step5_routes import ROUTE_TYPES, ROUTE_STAGES, route, save_route, route_summary
