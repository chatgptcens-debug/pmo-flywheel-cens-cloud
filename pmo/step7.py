"""Paso 07 · Monitoreo conectado al Paso 06, sin alterar su operación.
Cortes de informes congelados, métricas con denominador y ANS compartidos.
"""
from __future__ import annotations
import csv, io, json, math, uuid, hashlib, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .storage import connect, transaction
from contextlib import closing

MODULES=('Desempeño integral','Control de ANS y alertas','Informes de desempeño','Satisfacción y voz del cliente','Evaluación metodológica PMI')
QUESTIONS=json.loads((Path(__file__).parent/'data'/'step7_questions.json').read_text(encoding='utf-8'))
GUIDE_QUESTIONS=json.loads((Path(__file__).parent/'data'/'step7_questions_pmi_2025.json').read_text(encoding='utf-8'))
BANDS=((20,38,'Crítico'),(39,58,'Pobre'),(59,75,'Promedio'),(76,88,'Bien'),(89,100,'Excelente'))
SCHEMA='''
CREATE TABLE IF NOT EXISTS p7_tickets (
 id TEXT PRIMARY KEY,folio TEXT NOT NULL,servicio_id TEXT NOT NULL,
 servicio_nombre TEXT NOT NULL, titulo TEXT NOT NULL DEFAULT '', cliente TEXT NOT NULL DEFAULT '',
 dependencia TEXT NOT NULL DEFAULT '', responsable TEXT NOT NULL DEFAULT '',
 creado_en TEXT NOT NULL,primera_respuesta_en TEXT,terminado_en TEXT,cerrado_en TEXT,
 estado TEXT NOT NULL DEFAULT '',ans_respuesta_h REAL,ans_resolucion_h REAL,
 calificacion INTEGER CHECK(calificacion BETWEEN 1 AND 10 OR calificacion IS NULL),
 comentario TEXT NOT NULL DEFAULT '',aceptacion TEXT NOT NULL DEFAULT '',calificado_en TEXT,
 origen TEXT NOT NULL DEFAULT '',version TEXT NOT NULL DEFAULT '',origen_demo INTEGER NOT NULL DEFAULT 0,
 origen_actualizado_en TEXT NOT NULL DEFAULT '',importado_en TEXT NOT NULL,
 fuente TEXT NOT NULL DEFAULT '',payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_p7_tickets_servicio ON p7_tickets(servicio_id);
CREATE INDEX IF NOT EXISTS idx_p7_tickets_creado ON p7_tickets(creado_en);
CREATE TABLE IF NOT EXISTS p7_catalog (
 id TEXT PRIMARY KEY,codigo TEXT NOT NULL,nombre TEXT NOT NULL,origen TEXT NOT NULL,
 payload_json TEXT NOT NULL DEFAULT '{}',actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p7_metrics_ref (
 id TEXT PRIMARY KEY,servicio_id TEXT NOT NULL,nombre TEXT NOT NULL,tipo TEXT NOT NULL,
 meta TEXT NOT NULL DEFAULT '',real TEXT NOT NULL DEFAULT '',fuente TEXT NOT NULL DEFAULT '',
 payload_json TEXT NOT NULL DEFAULT '{}',actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p7_imports (
 id INTEGER PRIMARY KEY AUTOINCREMENT,origen TEXT NOT NULL,fecha TEXT NOT NULL,
 creados INTEGER NOT NULL,actualizados INTEGER NOT NULL,excluidos INTEGER NOT NULL,
 catalogo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS p7_monitoreo (
 servicio_id TEXT PRIMARY KEY,responsable TEXT NOT NULL,frecuencia TEXT NOT NULL,
 fuente TEXT NOT NULL,actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p7_hallazgos (
 ticket_id TEXT NOT NULL REFERENCES p7_tickets(id) ON DELETE CASCADE,
 tipo TEXT NOT NULL CHECK(tipo IN ('respuesta','resolucion','cliente')),
 descripcion TEXT NOT NULL,accion TEXT NOT NULL DEFAULT '',responsable TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL CHECK(estado IN ('Pendiente','En seguimiento','Resuelto')),
 fecha TEXT NOT NULL,PRIMARY KEY(ticket_id,tipo)
);
CREATE TABLE IF NOT EXISTS p7_informes (
 id INTEGER PRIMARY KEY CHECK(id=1),responsable TEXT NOT NULL DEFAULT '',
 observaciones TEXT NOT NULL DEFAULT '',actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p7_evaluaciones (
 id TEXT PRIMARY KEY,version INTEGER NOT NULL UNIQUE,responsable TEXT NOT NULL,
 estado TEXT NOT NULL CHECK(estado IN ('Borrador','Archivada')),
 puntaje INTEGER,clasificacion TEXT,creado_en TEXT NOT NULL,archivado_en TEXT
);
CREATE TABLE IF NOT EXISTS p7_respuestas (
 evaluacion_id TEXT NOT NULL REFERENCES p7_evaluaciones(id) ON DELETE CASCADE,
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 20),
 valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '',evidencia TEXT NOT NULL DEFAULT '',
 fecha TEXT NOT NULL,PRIMARY KEY(evaluacion_id,numero)
);
'''
class ValidationError(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def rows(query,args=(),path=None):
    with closing(connect(path)) as c:return [dict(x) for x in c.execute(query,args)]
def row(query,args=(),path=None):
    with closing(connect(path)) as c:
        x=c.execute(query,args).fetchone();return dict(x) if x else None

def initialize(path=None):
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        c.executescript("""
        CREATE TABLE IF NOT EXISTS p7_sync_state(
          fuente TEXT PRIMARY KEY,huella TEXT NOT NULL,actualizado_en TEXT NOT NULL,registros INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS p7_report_cortes(
          id TEXT PRIMARY KEY,creado_en TEXT NOT NULL,responsable TEXT NOT NULL,
          desde TEXT NOT NULL DEFAULT '',hasta TEXT NOT NULL DEFAULT '',criterio_fecha TEXT NOT NULL,
          filtros_json TEXT NOT NULL,snapshot_json TEXT NOT NULL,huella_sha256 TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_p7_report_cortes_fecha ON p7_report_cortes(creado_en);
        """)
        ev_fields={x['name'] for x in c.execute('PRAGMA table_info(p7_evaluaciones)')}
        if 'instrumento' not in ev_fields:
            c.execute("ALTER TABLE p7_evaluaciones ADD COLUMN instrumento TEXT NOT NULL DEFAULT 'CENS-v1'")
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (24)')
        c.commit()

def _date(v):
    if not v:return None
    try:
        x=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    except (TypeError,ValueError):return None

def elapsed(start,end):
    a,b=_date(start),_date(end)
    return (b-a).total_seconds()/3600 if a and b and b>=a else None

def positive(v):
    if v is None or v=='':return None
    try:r=float(v)
    except (TypeError,ValueError):return None
    return r if math.isfinite(r) and r>0 else None

def score_value(v):
    if v is None or v=='':return None
    try:n=int(v)
    except (TypeError,ValueError):return None
    return n if str(v).strip() in (str(n),str(n)+'.0') and 1<=n<=10 else None

def normalize_ticket(x):
    if not isinstance(x,dict):raise ValidationError('Registro de ticket inválido')
    sid=str(x.get('id') or x.get('folio') or '').strip()
    created=x.get('creado_en') or x.get('createdAt')
    if not sid or not _date(created):raise ValidationError('Ticket sin ID o fecha de creación válida')
    serviceid=str(x.get('servicio_id') or x.get('serviceId') or '').strip()
    if not serviceid:raise ValidationError('Ticket sin servicio identificado')
    return dict(id=sid,folio=str(x.get('folio') or sid),servicio_id=serviceid,
       servicio_nombre=str(x.get('servicio_nombre') or x.get('serviceName') or x.get('servicio') or serviceid),
       titulo=str(x.get('titulo') or x.get('title') or ''),cliente=str(x.get('cliente') or x.get('client') or ''),
       dependencia=str(x.get('dependencia') or x.get('department') or ''),
       responsable=str(x.get('responsable') or x.get('owner') or ''),
       creado_en=str(created),primera_respuesta_en=x.get('primera_respuesta_en') or x.get('firstResponseAt'),
       terminado_en=x.get('terminado_en') or x.get('completedAt'),cerrado_en=x.get('cerrado_en') or x.get('closedAt'),
       estado=str(x.get('estado') or x.get('status') or ''),
       ans_respuesta_h=positive(x.get('ans_respuesta_h',x.get('slaResponseHours'))),
       ans_resolucion_h=positive(x.get('ans_resolucion_h',x.get('slaResolutionHours'))),
       calificacion=score_value(x.get('calificacion',x.get('score'))),
       comentario=str(x.get('calificacion_comentario') or x.get('scoreComment') or ''),
       aceptacion=str(x.get('aceptacion') or x.get('acceptance') or ''),
       calificado_en=x.get('calificado_en') or x.get('scoreAt'),
       origen=str(x.get('origen') or ''),version=str(x.get('version_servicio') or ''),
       origen_demo=int(bool(x.get('demo') or x.get('isDemo'))),
       origen_actualizado_en=str(x.get('actualizado_en') or x.get('updatedAt') or ''),
       importado_en=now())

def ticket_list(query='',service='',area='',owner='',date_from='',date_to='',path=None,
                date_field='creado_en',include_demo=True):
    if date_field not in ('creado_en','primera_respuesta_en','terminado_en','cerrado_en'):
        raise ValidationError('Criterio de fecha inválido')
    recs=rows('SELECT * FROM p7_tickets ORDER BY creado_en DESC,folio',path=path)
    if date_from and date_to and date_from>date_to:raise ValidationError('Rango de fechas inválido')
    def include(t):
        if service and t['servicio_id']!=service:return False
        if area and t['dependencia']!=area:return False
        if owner and t['responsable']!=owner:return False
        if not include_demo and t.get('origen_demo'):return False
        date_value=(t[date_field] or '')[:10]
        if (date_from or date_to) and not date_value:return False
        if date_from and date_value<date_from:return False
        if date_to and date_value>date_to:return False
        if query and query.casefold() not in ' '.join(str(t.get(k) or '') for k in ('folio','titulo','cliente','dependencia','responsable','servicio_nombre')).casefold():return False
        return True
    return [t for t in recs if include(t)]

def _merge(tickets,services=(),metrics=(),source='',include_demo=False,path=None):
    if not isinstance(tickets,list):raise ValidationError('El expediente no contiene tickets válidos')
    accepted=[];excluded=0
    for x in tickets:
        if x.get('demo') or x.get('isDemo'):
            if not include_demo:excluded+=1;continue
        item=normalize_ticket(x)
        # Conserva todos los campos de origen para auditoría sin editar ticket original.
        item['payload_json']=json.dumps(x,ensure_ascii=False,default=str)
        item['fuente']=source
        accepted.append(item)
    if len({x['id'] for x in accepted})!=len(accepted):raise ValidationError('El archivo contiene tickets con ID duplicado')
    created=updated=0
    with transaction(path) as c:
        for item in accepted:
            exists=c.execute('SELECT id FROM p7_tickets WHERE id=?',(item['id'],)).fetchone()
            columns=tuple(item)
            if exists:
                c.execute('UPDATE p7_tickets SET '+','.join(f'{k}=?' for k in columns if k!='id')+' WHERE id=?',
                          (*[item[k] for k in columns if k!='id'],item['id']));updated+=1
            else:
                c.execute('INSERT INTO p7_tickets ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(item.values()));created+=1
        for sv in services:
            if not isinstance(sv,dict):continue
            sid=str(sv.get('id') or sv.get('codigo') or '').strip()
            if not sid or (sv.get('demo') and not include_demo):continue
            c.execute('''INSERT INTO p7_catalog(id,codigo,nombre,origen,payload_json,actualizado_en) VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET codigo=excluded.codigo,nombre=excluded.nombre,
                origen=excluded.origen,payload_json=excluded.payload_json,actualizado_en=excluded.actualizado_en''',
               (sid,str(sv.get('codigo') or sid),str(sv.get('nombre') or sv.get('name') or sid),source,
                json.dumps(sv,ensure_ascii=False,default=str),now()))
        for m in metrics:
            if not isinstance(m,dict):continue
            mid=str(m.get('id') or '').strip()
            if not mid:continue
            c.execute('''INSERT INTO p7_metrics_ref(id,servicio_id,nombre,tipo,meta,real,fuente,payload_json,actualizado_en)
              VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET servicio_id=excluded.servicio_id,
              nombre=excluded.nombre,tipo=excluded.tipo,meta=excluded.meta,real=excluded.real,
              fuente=excluded.fuente,payload_json=excluded.payload_json,actualizado_en=excluded.actualizado_en''',
             (mid,str(m.get('servicio_id') or m.get('serviceId') or ''),str(m.get('nombre') or ''),
              str(m.get('tipo') or ''),str(m.get('meta') or ''),str(m.get('real') or ''),
              str(m.get('fuente') or ''),json.dumps(m,ensure_ascii=False,default=str),now()))
        c.execute('INSERT INTO p7_imports(origen,fecha,creados,actualizados,excluidos,catalogo) VALUES(?,?,?,?,?,?)',
                  (source,now(),created,updated,excluded,len(services)))
    return {'nuevos':created,'actualizados':updated,'ejemplos_excluidos':excluded,'servicios':len(services),'indicadores':len(metrics)}

def import_step6_direct(path=None,include_demo=False):
    from . import step6
    all_=step6.tickets(path)
    sr={x['id']:x for x in step6.catalog(path)}
    data=[]
    for x in all_:
        raw=dict(x);raw['servicio_nombre']=sr.get(x['servicio_id'],{}).get('nombre',x['servicio_id']);data.append(raw)
    return _merge(data,list(sr.values()),source='Paso 6 · SQLite compartida',include_demo=include_demo,path=path)

def import_step6_json(payload,path=None,include_demo=False):
    if not isinstance(payload,dict):raise ValidationError('Expediente JSON inválido')
    schema=payload.get('schema')
    if schema=='PMO-FLYWHEEL-CENS-paso7-input-v1':
        data=payload.get('tickets');catalog=payload.get('services',[])
    elif schema=='PMO-FLYWHEEL-CENS-paso6-backup-v1':
        obj=payload.get('tables') or payload.get('state') or {}
        data=obj.get('p6_tickets',obj.get('tickets'))
        catalog=obj.get('p6_catalog',obj.get('catalog',[]))
    elif schema=='PMO-FLYWHEEL-CENS-paso6-state-v1':
        data=payload.get('tickets');catalog=payload.get('catalog',[])
    else:raise ValidationError('Esquema incompatible con el expediente del Paso 6')
    if not isinstance(catalog,list):catalog=[]
    return _merge(data,catalog,source=f'Paso 6 · JSON {schema}',include_demo=include_demo,path=path)

def import_catalog_direct(path=None,include_demo=False):
    from . import step4
    services=[x for x in step4.services(path) if include_demo or not x.get('demo')]
    with closing(connect(path)) as c:
        metrics=[dict(x) for x in c.execute('SELECT * FROM p4_metrics')]
    ids={x['id'] for x in services}
    return _merge([],services,[m for m in metrics if m['servicio_id'] in ids],source='Paso 4 · SQLite compartida',path=path)

def import_catalog_json(payload,path=None):
    if not isinstance(payload,dict):raise ValidationError('Catálogo inválido')
    if payload.get('schema') not in ('PMO-CENS-P4-CATALOGO-v1','PMO-FLYWHEEL-CENS-paso4-catalog-v1'):
        raise ValidationError('El JSON no corresponde al catálogo del Paso 4')
    return _merge([],[x for x in payload.get('services',[]) if not x.get('demo')],
                 payload.get('metrics',[]),source='Paso 4 · JSON',path=path)

def sla(item,kind,at=None):
    """Única regla ANS: delega en Paso 06 y lee el calendario congelado del ticket.

    Los expedientes antiguos sin unidad conservan horas calendario. Sin dato o
    calendario confirmado no se inventa cumplimiento.
    """
    if kind not in ('respuesta','resolucion'):raise ValidationError('Tipo de ANS inválido')
    from . import step6
    data=dict(item)
    try:
        raw=json.loads(item.get('payload_json') or '{}')
        if isinstance(raw,dict):
            for key in ('ans_tipo','ans_calendario_json','ans_respuesta_h','ans_resolucion_h',
                        'primera_respuesta_en','terminado_en','creado_en'):
                if key not in data or data.get(key) in ('',None):
                    if key in raw:data[key]=raw[key]
    except (ValueError,TypeError):pass
    # El paso 6 normaliza la duración; para datos heredados se rechazan marcas
    # anteriores a la creación antes de llamarlo, sin alterar su código.
    mark=data.get('primera_respuesta_en' if kind=='respuesta' else 'terminado_en')
    if mark and elapsed(data.get('creado_en'),mark) is None:
        return {'estado':'Fecha inválida','evaluable':False,'consumido':None,
                'plazo':positive(data.get('ans_respuesta_h' if kind=='respuesta' else 'ans_resolucion_h')),
                'cerrado':True,'unidad':data.get('ans_tipo') or 'Calendario'}
    result=step6.sla_state(data,kind,at)
    state=result.get('estado')
    if state=='Cumple ANS':state='Cumplió'
    elif state=='Vencido' and mark:state='Incumplió'
    return {'estado':state,'evaluable':bool(result.get('evaluable')),
            'consumido':result.get('horas'),'plazo':result.get('plazo'),
            'cerrado':bool(mark),'unidad':result.get('unidad',data.get('ans_tipo') or 'Calendario'),
            'porcentaje':result.get('porcentaje'),'semaforo':result.get('semaforo'),
            'detalle':result.get('detalle','')}

def stats(items,at=None):
    items=list(items)
    comp=[x for x in items if _date(x['terminado_en']) is not None]
    closed=[x for x in items if x['estado']=='Finalizado' or _date(x['cerrado_en']) is not None]
    resp=[sla(x,'respuesta',at) for x in items]
    resol=[sla(x,'resolucion',at) for x in items]
    re=[v for v in resp if v['evaluable']];se=[v for v in resol if v['evaluable']]
    scores=[x['calificacion'] for x in items if score_value(x['calificacion']) is not None]
    open_=[x for x in items if not x['terminado_en']]
    late=[x for x in open_ if sla(x,'resolucion',at)['estado']=='Vencido' or (not x['primera_respuesta_en'] and sla(x,'respuesta',at)['estado']=='Vencido')]
    risk=[x for x in open_ if x not in late and (sla(x,'resolucion',at)['estado']=='En riesgo' or (not x['primera_respuesta_en'] and sla(x,'respuesta',at)['estado']=='En riesgo'))]
    pct=lambda a,b:100*a/b if b else None
    mean=lambda vals:sum(vals)/len(vals) if vals else None
    return {'recibidas':len(items),'atendidas':len(comp),'finalizadas':len(closed),'abiertas':len(open_),
      'servicios_atendidos':len({x['servicio_id'] for x in comp}),
      'cumplen_respuesta':sum(v['estado']=='Cumplió' for v in re),'base_respuesta':len(re),
      'ans_respuesta':pct(sum(v['estado']=='Cumplió' for v in re),len(re)),
      'cumplen_resolucion':sum(v['estado']=='Cumplió' for v in se),'base_resolucion':len(se),
      'ans_resolucion':pct(sum(v['estado']=='Cumplió' for v in se),len(se)),
      'sin_ans_respuesta':sum(v['estado']=='Sin ANS' for v in resp),
      'sin_ans_resolucion':sum(v['estado']=='Sin ANS' for v in resol),
      'calificacion':mean(scores),'evaluaciones':len(scores),
      'cobertura_satisfaccion':pct(len(scores),len(comp)),
      'notas_altas':sum(x>=9 for x in scores),'notas_bajas':sum(x<=6 for x in scores),
      'tiempo_medio':mean([x for t in comp if (x:=elapsed(t['creado_en'],t['terminado_en'])) is not None]),
      'vencidos':late,'riesgo':risk}

def by_service(items,at=None):
    d={}
    for t in items:d.setdefault(t['servicio_id'],[]).append(t)
    return [{'servicio_id':k,'servicio':ls[0]['servicio_nombre'],**stats(ls,at)} for k,ls in d.items()]

def save_monitor(service_id,owner,cadence,source,path=None):
    if cadence not in ('Diaria','Semanal','Mensual','Trimestral'):raise ValidationError('Frecuencia inválida')
    with transaction(path) as c:
        c.execute('INSERT INTO p7_monitoreo VALUES(?,?,?,?,?) ON CONFLICT(servicio_id) DO UPDATE SET responsable=excluded.responsable,frecuencia=excluded.frecuencia,fuente=excluded.fuente,actualizado_en=excluded.actualizado_en',
                  (service_id,owner.strip(),cadence,source.strip(),now()))

def monitoring(path=None):return rows('SELECT * FROM p7_monitoreo ORDER BY servicio_id',path=path)
def catalogue(path=None):return rows('SELECT * FROM p7_catalog ORDER BY nombre',path=path)
def reference_metrics(path=None):return rows('SELECT * FROM p7_metrics_ref ORDER BY nombre',path=path)
def imports(path=None):return rows('SELECT * FROM p7_imports ORDER BY id DESC',path=path)

def save_finding(ticket_id,kind,description,action='',owner='',status='Pendiente',path=None):
    if kind not in ('respuesta','resolucion','cliente'):raise ValidationError('Tipo de hallazgo inválido')
    if status not in ('Pendiente','En seguimiento','Resuelto'):raise ValidationError('Estado inválido')
    if not description.strip():raise ValidationError('El hallazgo requiere descripción')
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p7_tickets WHERE id=?',(ticket_id,)).fetchone():raise ValidationError('El ticket no existe en monitoreo')
        c.execute('''INSERT INTO p7_hallazgos VALUES(?,?,?,?,?,?,?) ON CONFLICT(ticket_id,tipo) DO UPDATE SET
        descripcion=excluded.descripcion,accion=excluded.accion,responsable=excluded.responsable,estado=excluded.estado,fecha=excluded.fecha''',
        (ticket_id,kind,description.strip(),action.strip(),owner.strip(),status,now()))

def findings(path=None):return rows('SELECT * FROM p7_hallazgos ORDER BY fecha DESC',path=path)
def report_config(path=None):return row('SELECT * FROM p7_informes WHERE id=1',path=path) or {'responsable':'','observaciones':''}
def save_report(owner,notes,path=None):
    with transaction(path) as c:c.execute('INSERT INTO p7_informes VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET responsable=excluded.responsable,observaciones=excluded.observaciones,actualizado_en=excluded.actualizado_en',(owner.strip(),notes.strip(),now()))

def classification(value):
    if value is None:return None
    for a,b,label in BANDS:
        if a<=value<=b:return label
    raise ValidationError('Puntaje fuera de rango 20–100')

def evaluations(path=None):return rows('SELECT * FROM p7_evaluaciones ORDER BY version DESC',path=path)
def answers(key,path=None):return rows('SELECT * FROM p7_respuestas WHERE evaluacion_id=? ORDER BY numero',(key,),path)
def new_evaluation(owner,path=None):
    if not owner.strip():raise ValidationError('Registra responsable de la evaluación')
    key=str(uuid.uuid4())
    with transaction(path) as c:
        version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM p7_evaluaciones').fetchone()[0]
        c.execute('''INSERT INTO p7_evaluaciones(id,version,responsable,estado,puntaje,clasificacion,creado_en,archivado_en,instrumento)
            VALUES(?,?,?,?,?,?,?,?,?)''',(key,version,owner.strip(),'Borrador',None,None,now(),None,'PMI-2025-guia'))
    return key

def save_answer(key,num,value,observation='',evidence='',path=None):
    if not isinstance(num,int) or not 1<=num<=20 or not isinstance(value,int) or not 1<=value<=5:raise ValidationError('Ítem o puntuación fuera de rango')
    with transaction(path) as c:
        ev=c.execute('SELECT estado FROM p7_evaluaciones WHERE id=?',(key,)).fetchone()
        if not ev or ev['estado']!='Borrador':raise ValidationError('Evaluación archivada o inexistente')
        c.execute('''INSERT INTO p7_respuestas(evaluacion_id,numero,valor,observacion,evidencia,fecha)
        VALUES(?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
        valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia,fecha=excluded.fecha''',
        (key,num,value,observation,evidence,now()))

def evaluation_summary(key,path=None):
    ev=row('SELECT * FROM p7_evaluaciones WHERE id=?',(key,),path)
    if not ev:raise ValidationError('Evaluación inexistente')
    all_=answers(key,path);by={x['numero']:x for x in all_}
    questions=GUIDE_QUESTIONS if ev.get('instrumento')=='PMI-2025-guia' else QUESTIONS
    subs=[]
    for d,dim in enumerate(questions):
        vals=[by[j]['valor'] for j in range(d*5+1,d*5+6) if j in by]
        subs.append({'dimension':dim['name'],'respondidas':len(vals),'subtotal':sum(vals),'promedio':sum(vals)/len(vals) if vals else None})
    total=sum(x['valor'] for x in all_)
    return {**ev,'respondidas':len(all_),'puntaje_parcial':total,'puntaje_final':total if len(all_)==20 else None,
            'clasificacion_final':classification(total) if len(all_)==20 else None,'dimensiones':subs}

def archive_evaluation(key,path=None):
    summary=evaluation_summary(key,path)
    if summary['respondidas']!=20:raise ValidationError('Faltan preguntas por responder')
    with transaction(path) as c:
        cur=c.execute('SELECT estado FROM p7_evaluaciones WHERE id=?',(key,)).fetchone()
        if cur['estado']!='Borrador':raise ValidationError('La evaluación ya se archivó')
        c.execute('UPDATE p7_evaluaciones SET estado=?,puntaje=?,clasificacion=?,archivado_en=? WHERE id=?',
                  ('Archivada',summary['puntaje_final'],summary['clasificacion_final'],now(),key))
    return summary

def csv_bytes(head,rows_):
    f=io.StringIO();w=csv.writer(f,delimiter=';');w.writerow(head);w.writerows(rows_);return ('\ufeff'+f.getvalue()).encode('utf-8')

def metrics_csv(items):
    m=by_service(items)
    return csv_bytes(['Servicio','Recibidas','Atendidas','Finalizadas','ANS respuesta (%)','ANS resolución (%)','Evaluaciones','Satisfacción','Alertas abiertas'],[
        (x['servicio'],x['recibidas'],x['atendidas'],x['finalizadas'],x['ans_respuesta'],x['ans_resolucion'],x['evaluaciones'],x['calificacion'],len(x['vencidos'])+len(x['riesgo'])) for x in m])

def ans_csv(items,at=None,path=None):
    data=[];note_map={(x['ticket_id'],x['tipo']):x for x in findings(path)}
    for t in items:
        for kind in ('respuesta','resolucion'):
            a=sla(t,kind,at);note=note_map.get((t['id'],kind),{})
            data.append((t['folio'],t['servicio_nombre'],kind,a['estado'],a['consumido'],a['plazo'],t['responsable'],note.get('descripcion',''),note.get('accion','')))
    return csv_bytes(['Ticket','Servicio','Tipo ANS','Estado','Horas consumidas','Plazo h','Responsable','Hallazgo','Acción'],data)

def feedback_csv(items,path=None):
    notes={(x['ticket_id'],x['tipo']):x for x in findings(path)}
    return csv_bytes(['Ticket','Servicio','Cliente','Dependencia','Nota 1–10','Aceptación','Comentario','Seguimiento'],[
        (t['folio'],t['servicio_nombre'],t['cliente'],t['dependencia'],t['calificacion'],t['aceptacion'],t['comentario'],notes.get((t['id'],'cliente'),{}).get('descripcion',''))
        for t in items if t['calificacion'] is not None])

def step8_export(items,path=None):
    ids={t['id']:t for t in items}
    notes=[{**n,'folio':ids[n['ticket_id']]['folio'],'servicio_id':ids[n['ticket_id']]['servicio_id']} for n in findings(path) if n['ticket_id'] in ids]
    return {'schema':'PMO-FLYWHEEL-CENS-paso8-input-v1','exportedAt':now(),'source':'Paso 7 · CENS Streamlit',
            'findings':notes,'summary':stats(items),'ticket_ids':list(ids),
            'informacion_operativa':{'experiencia':{k:v for k,v in client_feedback(items,path).items() if k!='filas'},
                                    'alertas_registradas':len(recorded_alerts(items,path)),
                                    'calidad':quality_summary(items,path)}}


def sync_live(path=None,include_demo=False):
    '''Sincronización idempotente en apertura de vista; Paso 06 nunca se modifica.
    Un SHA evita escrituras y duplicados del registro de importaciones por rerun.
    '''
    from . import step6
    source=step6.tickets(path)
    catalog=step6.catalog(path)
    raw=json.dumps({'tickets':source,'catalog':catalog,'include_demo':bool(include_demo)},
                   sort_keys=True,ensure_ascii=False,default=str)
    digest=hashlib.sha256(raw.encode('utf-8')).hexdigest()
    key='p6-live-'+('demo' if include_demo else 'real')
    previous=row('SELECT huella,actualizado_en FROM p7_sync_state WHERE fuente=?',(key,),path)
    if previous and previous['huella']==digest:
        return {'sin_cambios':True,'registros_origen':len(source),'actualizado_en':previous['actualizado_en']}
    lookup={c['id']:c for c in catalog}
    enriched=[]
    for t in source:
        d=dict(t)
        d['servicio_nombre']=lookup.get(t['servicio_id'],{}).get('nombre',t['servicio_id'])
        enriched.append(d)
    result=_merge(enriched,catalog,source='Paso 6 · SQLite compartida',
                  include_demo=include_demo,path=path)
    with transaction(path) as c:
        c.execute('''INSERT INTO p7_sync_state(fuente,huella,actualizado_en,registros)
           VALUES(?,?,?,?) ON CONFLICT(fuente) DO UPDATE SET
           huella=excluded.huella,actualizado_en=excluded.actualizado_en,
           registros=excluded.registros''',(key,digest,now(),len(source)))
    return {'sin_cambios':False,'registros_origen':len(source),**result}


def client_feedback(items,path=None):
    '''CSAT, NPS y conformidad de respuestas V0.39.23; no usa nota histórica como NPS.'''
    ids={x['id'] for x in items}
    if not ids:return {'csat':None,'nps':None,'base_csat':0,'base_nps':0,
                         'conformes':0,'ajustes':0,'filas':[]}
    try:
        records=rows('SELECT * FROM p6_respuestas_cliente WHERE vigente=1 ORDER BY fecha DESC',path=path)
    except sqlite3.OperationalError:
        records=[]
    distinct={}
    for r in records:
        if r['ticket_id'] in ids:distinct.setdefault(r['ticket_id'],r)
    records=list(distinct.values())
    cs=[r['csat'] for r in records if r.get('csat') is not None]
    np=[r['nps'] for r in records if r.get('nps') is not None]
    return {'csat':round(sum(cs)/len(cs),2) if cs else None,
            'base_csat':len(cs),
            'nps':round(100*(sum(v>=9 for v in np)-sum(v<=6 for v in np))/len(np),1) if np else None,
            'base_nps':len(np),
            'conformes':sum(x['decision']=='Conforme' for x in records),
            'ajustes':sum(x['decision']=='Solicita ajustes' for x in records),
            'filas':records}


def recorded_alerts(items,path=None):
    ids={x['id'] for x in items}
    if not ids:return []
    try:recs=rows('SELECT * FROM p6_alertas_ans ORDER BY fecha DESC',path=path)
    except sqlite3.OperationalError:return []
    return [x for x in recs if x['ticket_id'] in ids]


def quality_summary(items,path=None):
    items=list(items)
    f=client_feedback(items,path)
    return {'total':len(items),'sin_ans_resolucion':sum(x.get('ans_resolucion_h') is None for x in items),
            'sin_ans_respuesta':sum(x.get('ans_respuesta_h') is None for x in items),
            'sin_responsable':sum(not str(x.get('responsable') or '').strip() for x in items),
            'evaluacion_legacy':sum(x.get('calificacion') is not None for x in items),
            'base_csat':f['base_csat'],'base_nps':f['base_nps'],
            'conformidades':f['conformes'],'ajustes':f['ajustes'],
            'con_demo':sum(bool(x.get('origen_demo')) for x in items)}



def metric_measurements(path=None,service_ids=None):
    # Mediciones registradas en el Paso 04; sin volver a capturarlas.
    try:
        records=rows('''SELECT m.id as metrica_id,m.nombre,m.tipo,m.unidad,m.frecuencia,
               m.servicio_id as p4_id,r.periodo,r.revision,r.resultado,r.rag,
               r.registrado_en,r.evidencia_url,sp.estado as estado_definicion
          FROM p4_metric_measurements r JOIN p4_metrics m ON m.id=r.metric_id
          LEFT JOIN p4_metric_specs sp ON sp.metric_id=m.id
          ORDER BY r.metric_id,r.periodo,r.revision DESC''',path=path)
        catalog=rows('SELECT id,p4_id FROM p6_catalog',path=path)
    except sqlite3.OperationalError:return []
    mapping={x['p4_id']:x['id'] for x in catalog if x.get('p4_id')}
    chosen=[];seen=set()
    for r in records:
        key=(r['metrica_id'],r['periodo'])
        if key in seen:continue
        seen.add(key)
        linked=mapping.get(r['p4_id'])
        if service_ids is not None and linked not in service_ids:continue
        chosen.append({**r,'servicio_catalogo_id':linked})
    return chosen

def report_cut(items,owner,notes,filters=None,path=None):
    '''Corte reproducible y de solo lectura; guarda valores, denominadores y fuente.'''
    if not owner or not owner.strip():raise ValidationError('Registra el responsable del corte')
    if not items:raise ValidationError('No se puede generar un corte sin tickets')
    filters=dict(filters or {})
    ids=[x['id'] for x in items]
    now_=now()
    report={'creado_en':now_,'criterio_fecha':filters.get('criterio_fecha','creado_en'),
            'periodo':{'desde':filters.get('desde',''),'hasta':filters.get('hasta','')},
            'responsable':owner.strip(),'observaciones':notes.strip(),
            'fuente':'Paso 06 · SQLite compartida / Paso 07 · hallazgos',
            'indicadores':stats(items,at=now_),
            'comparativo':by_service(items,at=now_),
            'ticket_ids':ids,
            'tickets':[{'id':t['id'],'folio':t['folio'],'servicio':t['servicio_nombre'],
                        'estado':t['estado'],'creado_en':t['creado_en'],
                        'terminado_en':t['terminado_en'],'cerrado_en':t['cerrado_en'],
                        'ans_respuesta':sla(t,'respuesta',now_),
                        'ans_resolucion':sla(t,'resolucion',now_)} for t in items],
            'experiencia':client_feedback(items,path),
            'alertas':recorded_alerts(items,path),
            'hallazgos':[x for x in findings(path) if x['ticket_id'] in ids],
            'mediciones_paso04':metric_measurements(path,{x['servicio_id'] for x in items})}
    payload=json.dumps(report,ensure_ascii=False,sort_keys=True,default=str)
    digest=hashlib.sha256(payload.encode('utf-8')).hexdigest()
    key=str(uuid.uuid4())
    with transaction(path) as c:
        c.execute('''INSERT INTO p7_report_cortes
            (id,creado_en,responsable,desde,hasta,criterio_fecha,filtros_json,snapshot_json,huella_sha256)
            VALUES(?,?,?,?,?,?,?,?,?)''',
            (key,now_,owner.strip(),str(filters.get('desde') or ''),str(filters.get('hasta') or ''),
             report['criterio_fecha'],json.dumps(filters,ensure_ascii=False),payload,digest))
    return key


def report_cuts(path=None):
    return rows('''SELECT id,creado_en,responsable,desde,hasta,criterio_fecha,huella_sha256
                  FROM p7_report_cortes ORDER BY creado_en DESC,id DESC''',path=path)

def report_cut_data(key,path=None):
    r=row('SELECT * FROM p7_report_cortes WHERE id=?',(key,),path)
    if not r:raise ValidationError('Corte inexistente')
    if hashlib.sha256(r['snapshot_json'].encode('utf-8')).hexdigest()!=r['huella_sha256']:
        raise ValidationError('El corte no superó la verificación de integridad')
    return json.loads(r['snapshot_json'])


def report_excel(report):
    '''Libro de indicadores del corte y tickets, sin recalcular medidas.'''
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill
    from openpyxl.utils import get_column_letter
    w=Workbook();ws=w.active;ws.title='Resumen'
    m=report['indicadores']
    rows_=[('Indicador','Valor','Base') ,
           ('Solicitudes recibidas',m['recibidas'],m['recibidas']),
           ('ANS respuesta (%)',m['ans_respuesta'],m['base_respuesta']),
           ('ANS resolución (%)',m['ans_resolucion'],m['base_resolucion']),
           ('Satisfacción histórica (1-10)',m['calificacion'],m['evaluaciones']),
           ('CSAT (1-5)',report['experiencia']['csat'],report['experiencia']['base_csat']),
           ('NPS (-100 a +100)',report['experiencia']['nps'],report['experiencia']['base_nps'])]
    excel_safe=lambda value:("'"+value if isinstance(value,str) and value.lstrip()[:1] in ('=','+','-','@') else value)
    for r in rows_:ws.append([excel_safe(v) for v in r])
    sheet=w.create_sheet('Tickets');sheet.append(['Folio','Servicio','Estado','Creación','Entrega','Cierre','ANS respuesta','ANS resolución'])
    for x in report['tickets']:
        sheet.append([excel_safe(v) for v in [x['folio'],x['servicio'],x['estado'],x['creado_en'],x['terminado_en'],x['cerrado_en'],
                      x['ans_respuesta']['estado'],x['ans_resolucion']['estado']]])
    for sheet in w:
        sheet.freeze_panes='A2'
        for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='153B57')
        for col in sheet.columns:
            letter=get_column_letter(col[0].column)
            sheet.column_dimensions[letter].width=min(58,max(14,max(len(str(c.value or '')) for c in col)+3))
    buf=io.BytesIO();w.save(buf);return buf.getvalue()


def report_pdf(report):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.enums import TA_LEFT
    from xml.sax.saxutils import escape
    fontfile=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    family='Helvetica'
    if fontfile.exists():
        if 'PMODejaVu' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('PMODejaVu',str(fontfile)))
        family='PMODejaVu'
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PMO',fontName=family,fontSize=9,leading=14,textColor=colors.HexColor('#17394F')))
    styles.add(ParagraphStyle(name='PMOHead',parent=styles['PMO'],fontSize=17,leading=23,spaceAfter=12))
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=37,leftMargin=37,topMargin=38,bottomMargin=38)
    m=report['indicadores'];feedback=report['experiencia']
    esc=lambda x:escape(str(x if x is not None else '—'))
    story=[Paragraph('PMO CENS · Informe de desempeño de servicios',styles['PMOHead']),
      Paragraph('Corte: '+esc(report['creado_en'])+' · Responsable: '+esc(report['responsable']),styles['PMO']),
      Paragraph('Fuente: '+esc(report['fuente'])+' · Criterio temporal: '+esc(report['criterio_fecha']),styles['PMO']),Spacer(1,15)]
    shown=lambda x,suffix='':('—' if x is None else str(x)+suffix)
    table=[['Indicador','Valor','Base'],['Solicitudes',str(m['recibidas']),str(m['recibidas'])],
      ['ANS primera respuesta',shown(m['ans_respuesta'],'%'),str(m['base_respuesta'])],
      ['ANS resolución',shown(m['ans_resolucion'],'%'),str(m['base_resolucion'])],
      ['CSAT (1–5)',shown(feedback['csat']),str(feedback['base_csat'])],
      ['NPS (−100 a +100)',shown(feedback['nps']),str(feedback['base_nps'])]]
    t=Table(table,colWidths=[250,130,120]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E8F1F6')),
       ('FONTNAME',(0,0),(-1,-1),family),('FONTSIZE',(0,0),(-1,-1),8),
       ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#CDDCE6')),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.append(t);story.append(Spacer(1,18))
    story.append(Paragraph('Observaciones y decisiones',styles['PMOHead']))
    story.append(Paragraph(esc(report.get('observaciones') or 'Sin observaciones registradas'),styles['PMO']))
    story.append(Spacer(1,13))
    story.append(Paragraph('Informe congelado. No representa certificación institucional ni medición de beneficios estratégicos.',styles['PMO']))
    doc.build(story);return out.getvalue()

def backup(path=None):
    names=('p7_tickets','p7_catalog','p7_metrics_ref','p7_imports','p7_monitoreo','p7_hallazgos','p7_informes','p7_evaluaciones','p7_respuestas','p7_sync_state','p7_report_cortes')
    return {'schema':'PMO-FLYWHEEL-CENS-paso7-backup-v1','exportedAt':now(),'tables':{x:rows('SELECT * FROM '+x,path=path) for x in names}}

def restore(data,confirmed=False,path=None):
    if not confirmed:raise ValidationError('Confirma la restauración')
    schema='PMO-FLYWHEEL-CENS-paso7-backup-v1'
    names=('p7_tickets','p7_catalog','p7_metrics_ref','p7_imports','p7_monitoreo','p7_hallazgos','p7_informes','p7_evaluaciones','p7_respuestas','p7_sync_state','p7_report_cortes')
    legacy_names=names[:-2]
    if not isinstance(data,dict) or data.get('schema')!=schema or not isinstance(data.get('tables'),dict) or set(data['tables']) not in (set(names),set(legacy_names)):raise ValidationError('Respaldo incompatible')
    with transaction(path) as c:
        for n in reversed(names):c.execute('DELETE FROM '+n)
        for n in names:
            if n not in data['tables']:continue
            if not isinstance(data['tables'][n],list):raise ValidationError('Registros inválidos')
            columns={x[1] for x in c.execute('PRAGMA table_info('+n+')')}
            for it in data['tables'][n]:
                if not isinstance(it,dict) or not set(it).issubset(columns):raise ValidationError('Columnas no válidas')
                if it:
                    keys=tuple(it)
                    c.execute('INSERT INTO '+n+' ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(it.values()))
    return True
