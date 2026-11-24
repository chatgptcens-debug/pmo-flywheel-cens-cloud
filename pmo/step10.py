"""Paso 10: Reconocimiento del valor; integración SQLite aditiva con Paso 9.

Las encuestas NPS (0..10), percepción (1..10) y autoevaluación PMI (1..5)
son instrumentos diferentes. Nunca se derivan beneficios de encuestas o tickets.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, uuid
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
from .storage import connect, transaction

NAV=('Percepción del valor','Valor entregado frente a reconocido',
     'Historias y reconocimiento','Tablero ejecutivo de reconocimiento','Autoevaluación metodológica PMI')
QUESTIONS_PERCEPTION={
 'confianza':'Confío en la capacidad técnica y profesional de la PMO.',
 'socio':'Considero a la PMO un aliado estratégico para alcanzar los objetivos de CENS.',
 'satisfaccion':'Estoy satisfecho con la contribución general de los servicios de la PMO.',
 'innovacion':'La PMO demuestra capacidad para innovar y adaptarse a nuevas necesidades.',
 'alineacion':'La PMO contribuye a fortalecer la cultura y los valores organizacionales.',
 'aprendizaje':'La PMO fortalece el aprendizaje, las competencias y la madurez en proyectos.',
 'impacto':'Reconozco el aporte de la PMO a los resultados de proyectos e iniciativas de CENS.',
}
DIMENSIONS=(
 ('Encuestas de percepción del valor',(
  '¿Recogemos periódicamente la percepción del valor de los clientes de la PMO?',
  '¿Combinamos preguntas de calificación con comentarios abiertos en las encuestas?',
  '¿Analizamos las respuestas por grupos de clientes para detectar diferencias?',
  '¿Identificamos brechas entre el valor demostrado y el valor que reconocen los clientes?',
  '¿Aplicamos los resultados de las encuestas para orientar decisiones y mejoras?')),
 ('Talleres de reconocimiento',(
  '¿Facilitamos talleres donde los clientes reflexionan sobre los aportes de la PMO?',
  '¿Los talleres promueven diálogo abierto y construcción compartida de valor?',
  '¿Documentamos y socializamos los hallazgos obtenidos en los talleres?',
  '¿Damos seguimiento a los participantes para conocer cambios de percepción?',
  '¿Realizamos talleres con una periodicidad definida?')),
 ('Tablero de reconocimiento del valor',(
  '¿Contamos con un tablero que integre las métricas de reconocimiento de la PMO?',
  '¿Incluimos percepción, uso de servicios y solicitudes de participación de la PMO?',
  '¿El tablero es accesible a la PMO y a sus grupos de clientes pertinentes?',
  '¿Ajustamos el tablero a partir de comentarios y prioridades cambiantes?',
  '¿Difundimos casos concretos de éxito mediante el tablero?')),
 ('Historias de valor',(
  '¿Comunicamos ejemplos comprobables del valor aportado por la PMO?',
  '¿Preparamos al equipo para comunicar las contribuciones mediante historias comprensibles?',
  '¿Utilizamos formatos diversos como casos, presentaciones o material audiovisual?',
  '¿Compartimos los resultados de la PMO en espacios y actividades de divulgación?',
  '¿Evaluamos el alcance y la utilidad de las historias para mejorar su comunicación?')),
 ('Retroalimentación de valor 360°',(
  '¿Recibimos retroalimentación sobre el valor de la PMO en diversos puntos de contacto?',
  '¿Combinamos encuestas breves, entrevistas y mecanismos digitales de opinión?',
  '¿Analizamos las observaciones recibidas para detectar tendencias y oportunidades de mejora?',
  '¿Informamos a los clientes cómo se utilizan sus comentarios para tomar acciones?',
  '¿Revisamos periódicamente que los canales de retroalimentación sigan siendo pertinentes?')),
 ('Eventos de reconocimiento',(
  '¿Organizamos actividades que permitan mostrar y reconocer las contribuciones de la PMO?',
  '¿Utilizamos diversos formatos y espacios para compartir los logros de la PMO?',
  '¿Promovemos una cultura de valoración de la dirección de proyectos?',
  '¿Involucramos a directivos o representantes clave en las actividades de reconocimiento?',
  '¿Medimos asistencia, participación y cambios de percepción tras las actividades?')),
)
QUESTIONS=tuple(q for _,block in DIMENSIONS for q in block)
SCHEMA='''
CREATE TABLE IF NOT EXISTS p10_beneficios(
 id TEXT PRIMARY KEY,servicio TEXT NOT NULL,cliente TEXT NOT NULL,necesidad TEXT NOT NULL DEFAULT '',
 beneficio TEXT NOT NULL,indicador TEXT NOT NULL DEFAULT '',unidad TEXT NOT NULL DEFAULT '',
 linea_base REAL,meta REAL,resultado_real REAL,evidencia TEXT NOT NULL,fecha_validacion TEXT NOT NULL DEFAULT '',
 origen TEXT NOT NULL,origen_version TEXT NOT NULL DEFAULT '',importado_en TEXT NOT NULL,es_demo INTEGER NOT NULL DEFAULT 0,
 vigente INTEGER NOT NULL DEFAULT 1 CHECK(vigente IN (0,1))
);
CREATE TABLE IF NOT EXISTS p10_encuestas(
 id TEXT PRIMARY KEY,periodo TEXT NOT NULL,fecha TEXT NOT NULL,grupo TEXT NOT NULL,area TEXT NOT NULL DEFAULT '',
 nombre TEXT NOT NULL DEFAULT '',codigo_encuestado TEXT NOT NULL DEFAULT '',beneficio_id TEXT REFERENCES p10_beneficios(id) ON DELETE SET NULL,
 nps INTEGER NOT NULL CHECK(nps BETWEEN 0 AND 10),
 confianza INTEGER NOT NULL CHECK(confianza BETWEEN 1 AND 10),
 socio INTEGER NOT NULL CHECK(socio BETWEEN 1 AND 10),
 satisfaccion INTEGER NOT NULL CHECK(satisfaccion BETWEEN 1 AND 10),
 innovacion INTEGER NOT NULL CHECK(innovacion BETWEEN 1 AND 10),
 alineacion INTEGER NOT NULL CHECK(alineacion BETWEEN 1 AND 10),
 aprendizaje INTEGER NOT NULL CHECK(aprendizaje BETWEEN 1 AND 10),
 impacto INTEGER NOT NULL CHECK(impacto BETWEEN 1 AND 10),
 reconocimiento INTEGER CHECK(reconocimiento IS NULL OR reconocimiento BETWEEN 1 AND 10),
 comentario TEXT NOT NULL DEFAULT '',huella_importacion TEXT NOT NULL DEFAULT '',es_demo INTEGER NOT NULL DEFAULT 0,
 creado_en TEXT NOT NULL,actualizado_en TEXT NOT NULL,
 CHECK ((beneficio_id IS NULL AND reconocimiento IS NULL) OR (beneficio_id IS NOT NULL AND reconocimiento IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_p10_encuestado_periodo ON p10_encuestas(periodo,codigo_encuestado) WHERE codigo_encuestado<>'';
CREATE UNIQUE INDEX IF NOT EXISTS idx_p10_encuesta_huella ON p10_encuestas(huella_importacion) WHERE huella_importacion<>'';
CREATE INDEX IF NOT EXISTS idx_p10_encuesta_beneficio ON p10_encuestas(beneficio_id);
CREATE TABLE IF NOT EXISTS p10_historias(
 id TEXT PRIMARY KEY,titulo TEXT NOT NULL,fecha TEXT NOT NULL,grupo TEXT NOT NULL,
 beneficio_id TEXT REFERENCES p10_beneficios(id) ON DELETE SET NULL,
 situacion TEXT NOT NULL,contribucion TEXT NOT NULL,resultado TEXT NOT NULL,
 testimonio TEXT NOT NULL DEFAULT '',evidencia TEXT NOT NULL DEFAULT '',autorizacion INTEGER NOT NULL DEFAULT 0,
 estado TEXT NOT NULL CHECK(estado IN ('Borrador','En revisión','Publicada')),
 responsable TEXT NOT NULL,es_demo INTEGER NOT NULL DEFAULT 0,creado_en TEXT NOT NULL,actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p10_actividades(
 id TEXT PRIMARY KEY,titulo TEXT NOT NULL,tipo TEXT NOT NULL CHECK(tipo IN ('Taller','Campaña','Evento')),
 fecha TEXT NOT NULL,grupo TEXT NOT NULL,responsable TEXT NOT NULL,asistentes INTEGER NOT NULL DEFAULT 0 CHECK(asistentes>=0),
 resultados TEXT NOT NULL DEFAULT '',evidencia TEXT NOT NULL DEFAULT '',estado TEXT NOT NULL DEFAULT 'Programada',
 es_demo INTEGER NOT NULL DEFAULT 0,creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p10_retroalimentacion(
 id TEXT PRIMARY KEY,fecha TEXT NOT NULL,grupo TEXT NOT NULL,canal TEXT NOT NULL,
 observacion TEXT NOT NULL,accion TEXT NOT NULL,responsable TEXT NOT NULL,fecha_compromiso TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL CHECK(estado IN ('Abierta','En gestión','Cerrada')),
 evidencia TEXT NOT NULL DEFAULT '',es_demo INTEGER NOT NULL DEFAULT 0,creado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p10_config(
 id INTEGER PRIMARY KEY CHECK(id=1),poblacion_objetivo INTEGER,umbral INTEGER NOT NULL DEFAULT 7 CHECK(umbral BETWEEN 1 AND 10),
 responsable_informe TEXT NOT NULL DEFAULT '',lectura_ejecutiva TEXT NOT NULL DEFAULT '',actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p10_evaluaciones(
 id TEXT PRIMARY KEY,version INTEGER NOT NULL UNIQUE,responsable TEXT NOT NULL,
 estado TEXT NOT NULL CHECK(estado IN ('Borrador','Archivada')),puntaje INTEGER,clasificacion TEXT,
 creado_en TEXT NOT NULL,archivado_en TEXT
);
CREATE TABLE IF NOT EXISTS p10_respuestas(
 evaluacion_id TEXT NOT NULL REFERENCES p10_evaluaciones(id) ON DELETE CASCADE,
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 30),valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '',evidencia TEXT NOT NULL DEFAULT '',actualizado_en TEXT NOT NULL,
 PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS p10_cierres(
 id TEXT PRIMARY KEY,periodo TEXT NOT NULL,responsable TEXT NOT NULL,
 informe_json TEXT NOT NULL,creado_en TEXT NOT NULL,es_demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS p10_importaciones(
 id TEXT PRIMARY KEY,fuente TEXT NOT NULL,archivo TEXT NOT NULL,agregados INTEGER NOT NULL,
 actualizados INTEGER NOT NULL,omitidos INTEGER NOT NULL,fecha TEXT NOT NULL
);
'''
class ValidationError(ValueError): pass

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def uid():return str(uuid.uuid4())
def txt(v):return str(v if v is not None else '').strip()
def valid_date(v,label='Fecha'):
    try:return date.fromisoformat(str(v)[:10]).isoformat()
    except (ValueError,TypeError):raise ValidationError(f'{label} no es válida (AAAA-MM-DD)')
def integer(v,minimum,maximum,label):
    try:
        if type(v) is bool or not str(v).strip() or not float(v).is_integer():raise ValueError()
        n=int(float(v))
        if minimum<=n<=maximum:return n
    except (ValueError,TypeError,OverflowError):pass
    raise ValidationError(f'{label} debe ser entero entre {minimum} y {maximum}')
def rows(sql,args=(),path=None):
    with closing(connect(path)) as c:return [dict(x) for x in c.execute(sql,args)]
def row(sql,args=(),path=None):
    with closing(connect(path)) as c:
        x=c.execute(sql,args).fetchone();return dict(x) if x else None

def initialize(path=None):
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES(17)')
        c.commit()

def benefits(path=None):return rows('SELECT * FROM p10_beneficios WHERE vigente=1 ORDER BY importado_en DESC,id',path=path)
def benefit(key,path=None):return row('SELECT * FROM p10_beneficios WHERE id=? AND vigente=1',(key,),path)
def surveys(path=None,period='',group=''):
    clause=[];args=[]
    if period:clause.append('periodo=?');args.append(period)
    if group:clause.append('grupo=?');args.append(group)
    return rows('SELECT * FROM p10_encuestas'+(' WHERE '+' AND '.join(clause) if clause else '')+' ORDER BY fecha DESC,creado_en DESC,id',tuple(args),path)
def survey(key,path=None):return row('SELECT * FROM p10_encuestas WHERE id=?',(key,),path)
def stories(path=None):return rows('SELECT * FROM p10_historias ORDER BY fecha DESC,creado_en DESC',path=path)
def activities(path=None):return rows('SELECT * FROM p10_actividades ORDER BY fecha DESC,creado_en DESC',path=path)
def feedback(path=None):return rows('SELECT * FROM p10_retroalimentacion ORDER BY fecha DESC,creado_en DESC',path=path)
def config(path=None):return row('SELECT * FROM p10_config WHERE id=1',path=path) or {'poblacion_objetivo':None,'umbral':7,'responsable_informe':'','lectura_ejecutiva':''}
def save_config(population=None,threshold=7,owner='',reading='',path=None):
    p=None if population in (None,'') else integer(population,1,1_000_000_000,'Población objetivo')
    t=integer(threshold,1,10,'Umbral de reconocimiento')
    with transaction(path) as c:
        c.execute('INSERT INTO p10_config VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET poblacion_objetivo=excluded.poblacion_objetivo,umbral=excluded.umbral,responsable_informe=excluded.responsable_informe,lectura_ejecutiva=excluded.lectura_ejecutiva,actualizado_en=excluded.actualizado_en',(p,t,txt(owner),txt(reading),now()))

# El origen local está confirmado por el propio motor de validación del Paso 9.
def import_from_step9(path=None,include_demo=False):
    from . import step9
    source=step9.overview(path)['detalle'];prepared=[];skipped=0
    for x in source:
        b=x['beneficio']
        if not x['verificado'] or (b['es_demo'] and not include_demo):skipped+=1;continue
        prepared.append({'id':b['id'],'servicio':b['servicio'],'cliente':b['cliente'],'necesidad':b['necesidad'],
          'beneficio':b['beneficio'],'indicador':b['indicador'],'unidad':b['unidad'],'linea_base':b['linea_base'],
          'meta':b['meta'],'resultado_real':x['calculo']['actual'] if x['calculo'] else None,
          'evidencia':b['evidencia_validacion'],'fecha_validacion':b['fecha_validacion'],
          'origen':'SQLite Paso 9','origen_version':b['origen_version'],'es_demo':b['es_demo']})
    result=_import_benefits(prepared,path=path,source='SQLite Paso 9',include_demo=include_demo)
    approved_ids={x['id'] for x in prepared}
    with transaction(path) as c:
        # No borrar encuestas históricas: solo desactivar el beneficio cuya validación
        # dejó de estar vigente en el Paso 9; una nueva importación puede reactivarlo.
        ids=[x[0] for x in c.execute("SELECT id FROM p10_beneficios WHERE origen='SQLite Paso 9' AND vigente=1") if x[0] not in approved_ids]
        for key in ids:c.execute('UPDATE p10_beneficios SET vigente=0 WHERE id=?',(key,))
    result['desactivados']=len(ids)
    result['omitidos']+=skipped
    return result

def _legacy_benefit(x,source='Expediente Paso 9'):
    meas=x.get('measurement') or x.get('resultado') or {}
    if not isinstance(meas,dict):meas={}
    return {'id':txt(x.get('id')),'servicio':txt(x.get('servicio') or x.get('service')),
      'cliente':txt(x.get('cliente') or x.get('client')),'necesidad':txt(x.get('necesidad') or x.get('need')),
      'beneficio':txt(x.get('beneficio') or x.get('benefit')),'indicador':txt(x.get('indicador') or x.get('metric')),
      'unidad':txt(x.get('unidad') or x.get('unit')),
      'linea_base':x.get('linea_base',x.get('baseline')),'meta':x.get('meta',x.get('target')),
      'resultado_real':meas.get('actual',x.get('resultado_real')),
      'evidencia':txt(x.get('evidencia') or x.get('verificationEvidence')),
      'fecha_validacion':txt(x.get('fecha_validacion') or x.get('validationDate')),
      'origen':source,'origen_version':txt(x.get('origen_version') or x.get('version')),
      'es_demo':bool(x.get('es_demo') or x.get('demo'))}

def import_step9_json(obj,filename='Expediente Paso 9',path=None,include_demo=False):
    if not isinstance(obj,dict):raise ValidationError('Se requiere un expediente JSON')
    if obj.get('schema')!='PMO-FLYWHEEL-CENS-paso10-input-v1':raise ValidationError('El JSON no corresponde al expediente Paso 10 exportado desde Paso 9')
    raw=obj.get('verifiedBenefits') if isinstance(obj.get('verifiedBenefits'),list) else obj.get('benefits')
    if not isinstance(raw,list):raise ValidationError('No se encontró lista de beneficios verificados')
    data=[]
    for x in raw:
        if not isinstance(x,dict):raise ValidationError('Registro JSON inválido')
        # El contrato JSON del exportador Streamlit v0.20 usa `benefits` sin atributo verified.
        # El contrato HTML usa verifiedBenefits con verified=true.
        if 'verifiedBenefits' in obj and x.get('verified') is not True:continue
        data.append(_legacy_benefit(x,'JSON Paso 9: '+filename))
    return _import_benefits(data,path=path,source=filename,include_demo=include_demo)

def _finite(x):
    try:
        if x is None or x=='':return None
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def _import_benefits(data,path=None,source='',include_demo=False):
    sanitized=[];skipped=0;seen=set()
    for x in data:
        k=txt(x.get('id'))
        if not k or k in seen:skipped+=1;continue
        seen.add(k)
        if bool(x.get('es_demo')) and not include_demo:skipped+=1;continue
        if not all(txt(x.get(f)) for f in ('servicio','cliente','beneficio','evidencia')):skipped+=1;continue
        sanitized.append((k,txt(x['servicio']),txt(x['cliente']),txt(x.get('necesidad')),txt(x['beneficio']),
          txt(x.get('indicador')),txt(x.get('unidad')),_finite(x.get('linea_base')),_finite(x.get('meta')),
          _finite(x.get('resultado_real')),txt(x['evidencia']),txt(x.get('fecha_validacion')),
          txt(x.get('origen') or source),txt(x.get('origen_version')),now(),int(bool(x.get('es_demo'))),1))
    added=updated=0
    with transaction(path) as c:
        for rec in sanitized:
            existing=c.execute('SELECT 1 FROM p10_beneficios WHERE id=?',(rec[0],)).fetchone()
            # Mantener encuestas vinculadas al ID, actualizar contexto verificado importado.
            c.execute('INSERT INTO p10_beneficios VALUES('+','.join('?'*17)+') ON CONFLICT(id) DO UPDATE SET '
               'servicio=excluded.servicio,cliente=excluded.cliente,necesidad=excluded.necesidad,'
               'beneficio=excluded.beneficio,indicador=excluded.indicador,unidad=excluded.unidad,'
               'linea_base=excluded.linea_base,meta=excluded.meta,resultado_real=excluded.resultado_real,'
               'evidencia=excluded.evidencia,fecha_validacion=excluded.fecha_validacion,'
               'origen=excluded.origen,origen_version=excluded.origen_version,importado_en=excluded.importado_en,vigente=1',rec)
            if existing:updated+=1
            else:added+=1
        c.execute('INSERT INTO p10_importaciones VALUES(?,?,?,?,?,?,?)',(uid(),source,source,added,updated,skipped,now()))
    return {'agregados':added,'actualizados':updated,'omitidos':skipped}

def _clean_survey(data,path=None):
    d={k:txt(data.get(k)) for k in ('periodo','fecha','grupo','area','nombre','codigo_encuestado','beneficio_id','comentario','huella_importacion')}
    for k in ('periodo','grupo'):
        if not d[k]:raise ValidationError(f'El campo {k} es obligatorio')
    d['fecha']=valid_date(d['fecha'])
    d['nps']=integer(data.get('nps'),0,10,'NPS')
    for k in QUESTIONS_PERCEPTION:d[k]=integer(data.get(k),1,10,k)
    if d['beneficio_id']:
        if not benefit(d['beneficio_id'],path):raise ValidationError('El beneficio vinculado no está verificado/importado en Paso 10')
        d['reconocimiento']=integer(data.get('reconocimiento'),1,10,'Reconocimiento')
    else:
        if data.get('reconocimiento') not in (None,''):raise ValidationError('No se puede asignar reconocimiento sin beneficio vinculado')
        d['reconocimiento']=None
        d['beneficio_id']=None
    d['es_demo']=int(bool(data.get('es_demo')))
    return d

def save_survey(data,key=None,path=None):
    d=_clean_survey(data,path)
    cols=('periodo','fecha','grupo','area','nombre','codigo_encuestado','beneficio_id','nps',
          *QUESTIONS_PERCEPTION,'reconocimiento','comentario','huella_importacion','es_demo')
    with transaction(path) as c:
        if key and not c.execute('SELECT 1 FROM p10_encuestas WHERE id=?',(key,)).fetchone():raise ValidationError('Encuesta inexistente')
        key=key or uid()
        try:
            if c.execute('SELECT 1 FROM p10_encuestas WHERE id=?',(key,)).fetchone():
                c.execute('UPDATE p10_encuestas SET '+','.join(f'{x}=?' for x in cols)+',actualizado_en=? WHERE id=?',tuple(d[x] for x in cols)+(now(),key))
            else:
                c.execute('INSERT INTO p10_encuestas(id,'+','.join(cols)+',creado_en,actualizado_en) VALUES('+','.join('?'*(len(cols)+3))+')',(key,*[d[x] for x in cols],now(),now()))
        except __import__('sqlite3').IntegrityError:raise ValidationError('Ya existe respuesta para este código de encuestado y periodo, o fila repetida')
    return key

def delete_survey(key,path=None):
    with transaction(path) as c:
        if not c.execute('DELETE FROM p10_encuestas WHERE id=?',(key,)).rowcount:raise ValidationError('Encuesta inexistente')

def template_csv():
    buf=io.StringIO();writer=csv.writer(buf,delimiter=';')
    writer.writerow(['periodo','fecha','grupo','area','nombre','codigo_encuestado','beneficio_id','nps',*QUESTIONS_PERCEPTION,'reconocimiento','comentario'])
    return ('\ufeff'+buf.getvalue()).encode('utf-8')

def _csv_rows(raw):
    if isinstance(raw,bytes):raw=raw.decode('utf-8-sig')
    if not isinstance(raw,str):raise ValidationError('Contenido CSV inválido')
    sample=raw.lstrip('\ufeff').splitlines()
    if not sample:raise ValidationError('CSV vacío')
    delimiter=';' if sample[0].count(';')>=sample[0].count(',') else ','
    return csv.DictReader(io.StringIO(raw.lstrip('\ufeff')),delimiter=delimiter)

def import_surveys_csv(raw,path=None,include_demo=False):
    reader=_csv_rows(raw)
    required={'periodo','fecha','grupo','nps',*QUESTIONS_PERCEPTION}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValidationError('Faltan columnas de la plantilla: '+', '.join(sorted(required-set(reader.fieldnames or []))))
    prepared=[];rejected=0;seen=set()
    for i,x in enumerate(reader,2):
        if not any(txt(v) for v in x.values() if isinstance(v,str)):continue
        x={k:txt(v) for k,v in x.items() if k is not None}
        if x.get('es_demo','').lower() in ('1','si','sí','true'):x['es_demo']=True
        if x.get('es_demo') and not include_demo:rejected+=1;continue
        try:d=_clean_survey(x,path)
        except ValidationError:rejected+=1;continue
        h=hashlib.sha256(json.dumps({k:d[k] for k in d if k not in ('huella_importacion',)},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        d['huella_importacion']=h
        dedupe=(d['periodo'],d['codigo_encuestado']) if d['codigo_encuestado'] else (h,)
        if dedupe in seen:rejected+=1;continue
        seen.add(dedupe);prepared.append(d)
    if not prepared:raise ValidationError(f'No hay respuestas válidas nuevas. Filas rechazadas: {rejected}')
    inserted=0
    with transaction(path) as c:
        for d in prepared:
            cols=list(d)
            try:
                c.execute('INSERT INTO p10_encuestas(id,'+','.join(cols)+',creado_en,actualizado_en) VALUES('+','.join('?'*(len(cols)+3))+')',(uid(),*[d[k] for k in cols],now(),now()))
                inserted+=1
            except __import__('sqlite3').IntegrityError:rejected+=1
        c.execute('INSERT INTO p10_importaciones VALUES(?,?,?,?,?,?,?)',(uid(),'CSV encuestas','CSV',inserted,0,rejected,now()))
    return {'agregadas':inserted,'rechazadas':rejected}

def nps(list_of_surveys):
    vals=[int(x['nps']) for x in list_of_surveys if isinstance(x.get('nps'),int) and 0<=x['nps']<=10]
    if not vals:return {'total':0,'detractores':0,'pasivos':0,'promotores':0,'puntaje':None}
    d=sum(v<=6 for v in vals);p=sum(v>=9 for v in vals)
    return {'total':len(vals),'detractores':d,'pasivos':len(vals)-d-p,'promotores':p,'puntaje':100*(p-d)/len(vals)}

def average(values):return sum(values)/len(values) if values else None

def coverage(selected,period='',group='',path=None):
    cfg=config(path);pop=cfg['poblacion_objetivo']
    if not pop:return {'porcentaje':None,'razon':'Definir población objetivo'}
    if group:return {'porcentaje':None,'razon':'La población configurada es general, no por grupo'}
    if not period:return {'porcentaje':None,'razon':'Filtre un solo periodo'}
    codes=[txt(x['codigo_encuestado']) for x in selected]
    if not codes or any(not x for x in codes):return {'porcentaje':None,'razon':'Faltan códigos seudónimos para contar personas únicas'}
    return {'porcentaje':100*len(set(codes))/pop,'personas_unicas':len(set(codes)),'poblacion':pop}

def dashboard(period='',group='',path=None):
    selected=surveys(path,period,group);res=nps(selected)
    avg={k:average([x[k] for x in selected]) for k in QUESTIONS_PERCEPTION}
    bs=benefits(path);th=config(path)['umbral']
    linked=defaultdict(list)
    valid_ids={b['id'] for b in bs}
    for s in selected:
        if s['beneficio_id'] in valid_ids and s['reconocimiento'] is not None:linked[s['beneficio_id']].append(s['reconocimiento'])
    recognized={k:average(v) for k,v in linked.items()}
    recognized_count=sum(v>=th for v in recognized.values());under_count=sum(v<th for v in recognized.values())
    missing=len(bs)-len(linked)
    groups=defaultdict(list)
    for s in selected:groups[s['grupo']].append(s)
    monthly=defaultdict(list)
    for s in selected:monthly[s['fecha'][:7]].append(s)
    return {'encuestas':len(selected),'nps':res,'promedios':avg,'beneficios':len(bs),'reconocidos':recognized_count,
       'poco_reconocidos':under_count,'sin_vinculo':missing,'reconocimiento_por_beneficio':recognized,
       'reconocimiento_promedio':average([v for group in linked.values() for v in group]),
       'cobertura':coverage(selected,period,group,path),
       'grupos':{g:{'encuestas':len(v),'nps':nps(v)['puntaje'],'confianza':average([s['confianza'] for s in v]),
                    'socio':average([s['socio'] for s in v]),'satisfaccion':average([s['satisfaccion'] for s in v])} for g,v in sorted(groups.items())},
       'mensual':{g:{k:average([s[k] for s in v]) for k in ('confianza','socio','satisfaccion')} for g,v in sorted(monthly.items())},
       'seleccion':selected,'umbral':th}

def save_story(data,key=None,path=None):
    req=('titulo','grupo','situacion','contribucion','resultado','responsable')
    if any(not txt(data.get(k)) for k in req):raise ValidationError('Título, grupo, situación, contribución, resultado y responsable son obligatorios')
    state=txt(data.get('estado') or 'Borrador')
    if state not in ('Borrador','En revisión','Publicada'):raise ValidationError('Estado de historia inválido')
    bid=txt(data.get('beneficio_id'))
    if bid and not benefit(bid,path):raise ValidationError('Beneficio no importado desde Paso 9')
    if state=='Publicada' and (not bid or not txt(data.get('evidencia')) or not bool(data.get('autorizacion'))):
        raise ValidationError('Para publicar requiere beneficio verificado, evidencia y autorización de divulgación')
    cols=('titulo','fecha','grupo','beneficio_id','situacion','contribucion','resultado','testimonio','evidencia','autorizacion','estado','responsable','es_demo')
    d={k:txt(data.get(k)) for k in cols};d['fecha']=valid_date(d['fecha']);d['beneficio_id']=bid or None
    d['autorizacion']=int(bool(data.get('autorizacion')));d['es_demo']=int(bool(data.get('es_demo')))
    with transaction(path) as c:
        if key:
            if not c.execute('SELECT 1 FROM p10_historias WHERE id=?',(key,)).fetchone():raise ValidationError('Historia inexistente')
            c.execute('UPDATE p10_historias SET '+','.join(f'{k}=?' for k in cols)+',actualizado_en=? WHERE id=?',(*[d[k] for k in cols],now(),key))
        else:
            key=uid();c.execute('INSERT INTO p10_historias(id,'+','.join(cols)+',creado_en,actualizado_en) VALUES('+','.join('?'*(len(cols)+3))+')',(key,*[d[k] for k in cols],now(),now()))
    return key

def delete_story(key,path=None):
    with transaction(path) as c:c.execute('DELETE FROM p10_historias WHERE id=?',(key,))

def save_activity(data,path=None):
    if any(not txt(data.get(k)) for k in ('titulo','tipo','fecha','grupo','responsable')):raise ValidationError('Complete título, tipo, fecha, grupo y responsable')
    if data['tipo'] not in ('Taller','Campaña','Evento'):raise ValidationError('Tipo de actividad inválido')
    n=integer(data.get('asistentes',0),0,1_000_000,'Asistentes')
    with transaction(path) as c:
        key=uid();c.execute('INSERT INTO p10_actividades VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,txt(data['titulo']),txt(data['tipo']),valid_date(data['fecha']),txt(data['grupo']),txt(data['responsable']),n,txt(data.get('resultados')),txt(data.get('evidencia')),txt(data.get('estado') or 'Programada'),int(bool(data.get('es_demo'))),now()))
    return key

def save_feedback(data,path=None):
    if any(not txt(data.get(k)) for k in ('fecha','grupo','canal','observacion','accion','responsable')):raise ValidationError('Fecha, grupo, canal, observación, acción y responsable obligatorios')
    status=txt(data.get('estado') or 'Abierta')
    if status not in ('Abierta','En gestión','Cerrada'):raise ValidationError('Estado inválido')
    with transaction(path) as c:
        key=uid();c.execute('INSERT INTO p10_retroalimentacion VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(key,valid_date(data['fecha']),txt(data['grupo']),txt(data['canal']),txt(data['observacion']),txt(data['accion']),txt(data['responsable']),txt(data.get('fecha_compromiso')),status,txt(data.get('evidencia')),int(bool(data.get('es_demo'))),now()))
    return key

def delete_activity(key,path=None):
    with transaction(path) as c:c.execute('DELETE FROM p10_actividades WHERE id=?',(key,))
def delete_feedback(key,path=None):
    with transaction(path) as c:c.execute('DELETE FROM p10_retroalimentacion WHERE id=?',(key,))

def classification(score):
    if score is None:return None
    if not isinstance(score,int) or score<30 or score>150:raise ValidationError('Puntaje fuera del rango PMI')
    return 'Excelente' if score>=134 else 'Bien' if score>=114 else 'Promedio' if score>=89 else 'Pobre' if score>=59 else 'Crítico'

def evaluations(path=None):return rows('SELECT * FROM p10_evaluaciones ORDER BY version DESC',path=path)
def create_evaluation(owner,path=None):
    if not txt(owner):raise ValidationError('Responsable de evaluación obligatorio')
    with transaction(path) as c:
        if c.execute("SELECT 1 FROM p10_evaluaciones WHERE estado='Borrador'").fetchone():raise ValidationError('Ya existe una autoevaluación en borrador')
        version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM p10_evaluaciones').fetchone()[0];key=uid()
        c.execute('INSERT INTO p10_evaluaciones VALUES(?,?,?,?,?,?,?,?)',(key,version,txt(owner),'Borrador',None,None,now(),None))
    return key

def save_answer(key,num,score,notes='',evidence='',path=None):
    if type(num) is not int or not 1<=num<=30:raise ValidationError('Número de pregunta inválido')
    if score is not None and (type(score) is not int or not 1<=score<=5):raise ValidationError('Valor PMI fuera de escala 1–5')
    with transaction(path) as c:
        record=c.execute('SELECT estado FROM p10_evaluaciones WHERE id=?',(key,)).fetchone()
        if not record or record['estado']!='Borrador':raise ValidationError('Evaluación archivada o inexistente')
        if score is None:c.execute('DELETE FROM p10_respuestas WHERE evaluacion_id=? AND numero=?',(key,num))
        else:c.execute('INSERT INTO p10_respuestas VALUES(?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia,actualizado_en=excluded.actualizado_en',(key,num,score,txt(notes),txt(evidence),now()))

def assessment(key,path=None):
    eva=row('SELECT * FROM p10_evaluaciones WHERE id=?',(key,),path)
    if not eva:raise ValidationError('Evaluación inexistente')
    r={v['numero']:v for v in rows('SELECT * FROM p10_respuestas WHERE evaluacion_id=?',(key,),path)}
    total=sum(r[x]['valor'] for x in range(1,31)) if len(r)==30 else None
    subs=[sum(r[x]['valor'] for x in range(i*5+1,i*5+6)) if all(x in r for x in range(i*5+1,i*5+6)) else None for i in range(6)]
    return {'evaluacion':eva,'respondidas':len(r),'puntaje':total,'clasificacion':classification(total),
            'dimensiones':subs,'respuestas':r}

def archive_evaluation(key,path=None):
    x=assessment(key,path)
    if x['evaluacion']['estado']!='Borrador':raise ValidationError('Evaluación ya archivada')
    if x['puntaje'] is None:raise ValidationError('La evaluación requiere 30 respuestas para archivar')
    with transaction(path) as c:
        c.execute("UPDATE p10_evaluaciones SET estado='Archivada',puntaje=?,clasificacion=?,archivado_en=? WHERE id=?",(x['puntaje'],x['clasificacion'],now(),key))
    return x

TABLES={'beneficios':'p10_beneficios','encuestas':'p10_encuestas','historias':'p10_historias',
        'actividades':'p10_actividades','retroalimentaciones':'p10_retroalimentacion',
        'configuracion':'p10_config','evaluaciones':'p10_evaluaciones','respuestas':'p10_respuestas','cierres':'p10_cierres','importaciones':'p10_importaciones'}

def backup(path=None):
    return {'schema':'PMO-FLYWHEEL-CENS-paso10-backup-v1','generado_en':now(),'tablas':{k:rows('SELECT * FROM '+v,path=path) for k,v in TABLES.items()}}

def restore(obj,confirmed=False,path=None):
    if not confirmed:raise ValidationError('Confirma restauración exclusiva del Paso 10')
    if not isinstance(obj,dict) or obj.get('schema')!='PMO-FLYWHEEL-CENS-paso10-backup-v1':raise ValidationError('No es un respaldo de Paso 10')
    tables=obj.get('tablas')
    if not isinstance(tables,dict) or set(tables)!=set(TABLES) or any(not isinstance(x,list) for x in tables.values()):
        raise ValidationError('Estructura de respaldo incompleta')
    with transaction(path) as c:
        for label in ('respuestas','evaluaciones','cierres','retroalimentaciones','actividades','historias','encuestas','beneficios','configuracion','importaciones'):
            c.execute('DELETE FROM '+TABLES[label])
        for key in ('beneficios','configuracion','encuestas','historias','actividades','retroalimentaciones','evaluaciones','respuestas','cierres','importaciones'):
            table=TABLES[key];valid={x[1] for x in c.execute('PRAGMA table_info('+table+')')}
            for rec in tables[key]:
                if not isinstance(rec,dict) or not set(rec).issubset(valid):raise ValidationError('Columnas desconocidas en '+key)
                cols=list(rec)
                if not cols:raise ValidationError('Registro vacío')
                c.execute('INSERT INTO '+table+' ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',tuple(rec[k] for k in cols))
    return True

def export_surveys_csv(path=None,period='',group=''):
    data=surveys(path,period,group);buf=io.StringIO();w=csv.writer(buf,delimiter=';')
    w.writerow(['periodo','fecha','grupo','area','nombre','codigo_encuestado','beneficio_id','nps',*QUESTIONS_PERCEPTION,'reconocimiento','comentario'])
    for x in data:w.writerow([x.get(k,'') for k in ('periodo','fecha','grupo','area','nombre','codigo_encuestado','beneficio_id','nps',*QUESTIONS_PERCEPTION,'reconocimiento','comentario')])
    return ('\ufeff'+buf.getvalue()).encode('utf-8')

def export_csv_records(data):
    buf=io.StringIO();w=csv.writer(buf,delimiter=';')
    if data:
        w.writerow(list(data[0]));w.writerows([[r.get(k) for k in data[0]] for r in data])
    return ('\ufeff'+buf.getvalue()).encode('utf-8')

def report(period='',group='',path=None):
    x=dashboard(period,group,path)
    return {'schema':'PMO-FLYWHEEL-CENS-paso10-report-v1','generado_en':now(),'periodo':period,'grupo':group,
       'nps':x['nps'],'indicadores':{k:v for k,v in x.items() if k not in ('seleccion','nps')},
       'beneficios':benefits(path),'historias':stories(path),'actividades':activities(path),'retroalimentaciones':feedback(path),
       'configuracion':config(path)}

def close_cycle(period,owner,path=None):
    if not txt(period) or not txt(owner):raise ValidationError('Indica periodo y responsable del cierre')
    obj=report(period=period,path=path)
    if not obj['nps']['total']:raise ValidationError('No hay encuestas para el periodo seleccionado')
    key=uid()
    with transaction(path) as c:
        c.execute('INSERT INTO p10_cierres VALUES(?,?,?,?,?,?)',(key,txt(period),txt(owner),json.dumps(obj,ensure_ascii=False,default=str),now(),0))
    return key

def cycle_history(path=None):return rows('SELECT id,periodo,responsable,creado_en FROM p10_cierres ORDER BY creado_en DESC',path=path)

def cycle(key,path=None):
    x=row('SELECT * FROM p10_cierres WHERE id=?',(key,),path)
    if not x:raise ValidationError('Cierre inexistente')
    return json.loads(x['informe_json'])
