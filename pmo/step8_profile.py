"""Paso 8: perfil transversal de los diez pasos, adicional al modelo de 26 servicios.

El índice global normalizado es una ADAPTACIÓN ANALÍTICA CENS; no es un índice
normativo/certificación PMI. Una evaluación parcial no equivale a puntuación cero.
"""
from __future__ import annotations
import json, math, uuid
from contextlib import closing
from datetime import datetime, timezone
from .storage import connect, transaction
from .step8 import ValidationError

STEPS = (
 (1,'Generación de conciencia','Sensibilización',25),
 (2,'Evaluación de necesidades','Necesidades',25),
 (3,'Propuesta de valor','Propuesta de valor',25),
 (4,'Desarrollo de servicios','Desarrollo',35),
 (5,'Incorporación de servicios','Incorporación',30),
 (6,'Operación de servicios','Operación',35),
 (7,'Monitoreo de servicios','Monitoreo',20),
 (8,'Mejora de servicios','Mejora',30),
 (9,'Entrega de valor','Entrega de valor',25),
 (10,'Reconocimiento del valor','Reconocimiento',30)
)
COUNTS = {x[0]:x[3] for x in STEPS}
assert sum(COUNTS.values()) == 280
SCALES=('zero5','direct')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS p8_profiles (
 id TEXT PRIMARY KEY, nombre TEXT NOT NULL, responsable TEXT NOT NULL,
 escala TEXT NOT NULL CHECK(escala IN ('zero5','direct')),
 es_demo INTEGER NOT NULL DEFAULT 0, creado_en TEXT NOT NULL,
 actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p8_profile_steps (
 perfil_id TEXT NOT NULL REFERENCES p8_profiles(id) ON DELETE CASCADE,
 paso INTEGER NOT NULL CHECK(paso BETWEEN 1 AND 10),
 puntaje INTEGER, respuestas_json TEXT NOT NULL DEFAULT '[]',
 peso INTEGER NOT NULL CHECK(peso BETWEEN 0 AND 100),
 meta REAL CHECK(meta IS NULL OR (meta>=0 AND meta<=5)),
 fuente TEXT NOT NULL DEFAULT '', observacion TEXT NOT NULL DEFAULT '',
 evidencia TEXT NOT NULL DEFAULT '', registrado_en TEXT,
 PRIMARY KEY(perfil_id,paso)
);
CREATE TABLE IF NOT EXISTS p8_profile_history (
 id TEXT PRIMARY KEY, perfil_id TEXT NOT NULL REFERENCES p8_profiles(id) ON DELETE CASCADE,
 version INTEGER NOT NULL, responsable TEXT NOT NULL,
 registrado_en TEXT NOT NULL, snapshot_json TEXT NOT NULL,
 UNIQUE(perfil_id,version)
);
'''

def _now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def _uid():return str(uuid.uuid4())
def _rows(sql,args=(),path=None):
    with closing(connect(path)) as c:return [dict(v) for v in c.execute(sql,args)]
def _one(sql,args=(),path=None):
    with closing(connect(path)) as c:
        v=c.execute(sql,args).fetchone();return dict(v) if v else None

def initialize(path=None):
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES(12)')
        c.commit()

def create_profile(name='Perfil de madurez PMO',owner='Equipo PMO',scale='zero5',demo=False,path=None):
    if scale not in SCALES:raise ValidationError('Escala no reconocida')
    if not str(name).strip() or not str(owner).strip():raise ValidationError('Nombre y responsable son obligatorios')
    pid=_uid()
    with transaction(path) as c:
        c.execute('INSERT INTO p8_profiles VALUES(?,?,?,?,?,?,?)',(pid,str(name).strip(),str(owner).strip(),scale,int(bool(demo)),_now(),_now()))
        for n,_,_,_ in STEPS:
            c.execute('INSERT INTO p8_profile_steps(perfil_id,paso,peso) VALUES(?,?,10)',(pid,n))
    return pid

def profiles(path=None):return _rows('SELECT * FROM p8_profiles ORDER BY creado_en DESC,id DESC',path=path)
def histories(pid,path=None):return _rows('SELECT * FROM p8_profile_history WHERE perfil_id=? ORDER BY version DESC',(pid,),path)

def _int_score(v,lo,hi,what):
    if v is None or v=='':return None
    if isinstance(v,bool):raise ValidationError(what+' debe ser un entero')
    try:f=float(v)
    except (TypeError,ValueError):raise ValidationError(what+' no numérico')
    if not math.isfinite(f) or not f.is_integer() or not lo<=f<=hi:raise ValidationError(f'{what} fuera de rango ({lo}–{hi})')
    return int(f)

def _prepare(step,score=None,answers=None,source='',note='',evidence='',target=None):
    if step not in COUNTS:raise ValidationError('Número de paso fuera de rango')
    n=COUNTS[step]
    # Dos modalidades exclusivas: desglose íntegro, o total validado documentalmente.
    if answers is not None:
        if not isinstance(answers,list) or len(answers)!=n:raise ValidationError(f'El Paso {step} requiere {n} respuestas')
        clean=[_int_score(v,1,5,'Respuesta PMI') for v in answers]
        if any(v is not None for v in clean):
            if score not in (None,''):raise ValidationError('No combines un total manual con respuestas individuales')
            raw=sum(clean) if all(v is not None for v in clean) else None
        else:raw=None
    else:
        clean=[]
        raw=_int_score(score,n,n*5,'Total PMI')
        if raw is not None and not str(source).strip():raise ValidationError('Para el total manual identifica el instrumento o la fuente')
    if target in ('',None):target=None
    else:
        try:target=float(target)
        except (ValueError,TypeError):raise ValidationError('Meta del perfil no numérica')
        if not math.isfinite(target) or not 0<=target<=5:raise ValidationError('La meta debe estar entre 0 y 5')
    return raw,json.dumps(clean),str(source).strip(),str(note).strip(),str(evidence).strip(),target

def save_step(pid,step,score=None,answers=None,source='',note='',evidence='',target=None,path=None):
    step=int(step)
    vals=_prepare(step,score,answers,source,note,evidence,target)
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p8_profiles WHERE id=?',(pid,)).fetchone():raise ValidationError('Perfil inexistente')
        c.execute('''UPDATE p8_profile_steps SET puntaje=?,respuestas_json=?,fuente=?,observacion=?,evidencia=?,meta=?,registrado_en=?
        WHERE perfil_id=? AND paso=?''',(*vals[:5],vals[5],_now(),pid,step))
        c.execute('UPDATE p8_profiles SET actualizado_en=? WHERE id=?',(_now(),pid))

def save_weights(pid,weights,scale=None,path=None):
    if not isinstance(weights,(list,tuple)) or len(weights)!=10:raise ValidationError('Se requieren diez pesos')
    clean=[_int_score(w,0,100,'Peso') for w in weights]
    if any(x is None for x in clean) or sum(clean)!=100:raise ValidationError('Los diez pesos deben sumar 100%')
    if scale is not None and scale not in SCALES:raise ValidationError('Escala no reconocida')
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p8_profiles WHERE id=?',(pid,)).fetchone():raise ValidationError('Perfil inexistente')
        for n,w in enumerate(clean,1):c.execute('UPDATE p8_profile_steps SET peso=? WHERE perfil_id=? AND paso=?',(w,pid,n))
        if scale is not None:c.execute('UPDATE p8_profiles SET escala=? WHERE id=?',(scale,pid))
        c.execute('UPDATE p8_profiles SET actualizado_en=? WHERE id=?',(_now(),pid))

def calculate_from_rows(header,records):
    steps=[]
    for meta in STEPS:
        n,name,short,count=meta
        r=next((x for x in records if int(x['paso'])==n),None)
        if r is None:raise ValidationError('Falta el Paso '+str(n))
        raw=r['puntaje'];weight=int(r['peso']);score=None
        if raw is not None:
            if not count<=raw<=count*5:raise ValidationError('Total fuera de escala para Paso '+str(n))
            avg=raw/count
            score=(avg-1)*1.25 if header['escala']=='zero5' else avg
        steps.append({**r,'name':name,'short':short,'count':count,'max':count*5,'level':score,'answers':json.loads(r['respuestas_json'])})
    total=sum(r['peso'] for r in steps)
    if total!=100:raise ValidationError('Pesos inválidos: deben sumar 100%')
    avail=[x for x in steps if x['level'] is not None]
    covered=sum(x['peso'] for x in avail)
    index=sum(x['level']*x['peso'] for x in avail)/covered if covered else None
    return {'profile':header,'steps':steps,'completed':len(avail),'coverage':10*len(avail),
            'covered_weight':covered,'total_weight':total,'index':index,
            'is_final':len(avail)==10, 'scale':header['escala']}

def report(pid,path=None):
    header=_one('SELECT * FROM p8_profiles WHERE id=?',(pid,),path)
    if not header:raise ValidationError('Perfil inexistente')
    return calculate_from_rows(header,_rows('SELECT * FROM p8_profile_steps WHERE perfil_id=? ORDER BY paso',(pid,),path))

def snapshot(pid,owner='',path=None):
    data=report(pid,path)
    if data['completed']==0:raise ValidationError('Registra por lo menos una autoevaluación antes de archivar')
    actor=(owner or data['profile']['responsable']).strip()
    if not actor:raise ValidationError('Responsable del corte requerido')
    raw=json.dumps(data,ensure_ascii=False,default=str)
    with transaction(path) as c:
        ver=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM p8_profile_history WHERE perfil_id=?',(pid,)).fetchone()[0]
        c.execute('INSERT INTO p8_profile_history VALUES(?,?,?,?,?,?)',(_uid(),pid,ver,actor,_now(),raw))
    return ver

def export_json(pid,path=None):
    v=report(pid,path)
    return {'schema':'pmo-cens-pmo-profile-v1','exportDate':_now(),'scale':v['scale'],
            'formula':('(rawScore/itemCount - 1)*1.25' if v['scale']=='zero5' else 'rawScore/itemCount'),
            'status':'final' if v['is_final'] else 'provisional','assessedSteps':v['completed'],
            'weightedMaturity':v['index'],'weightsTotal':v['total_weight'],
            'steps':[{'step':x['paso'],'name':x['name'],'questionCount':x['count'],'totalScore':x['puntaje'],
                     'maxScore':x['max'],'maturity0to5':x['level'],'weightPercent':x['peso'],
                     'source':x['fuente'],'date':x['registrado_en'],'notes':x['observacion'],
                     'evidence':x['evidencia'],'answers':x['answers'],'desired':x['meta']} for x in v['steps']],
            'methodology':'Síntesis CENS; no índice oficial prescrito por PMI'}

def _parse_import(obj):
    if not isinstance(obj,dict) or obj.get('schema') not in ('pmo-cens-pmo-profile-v1','PMO-FLYWHEEL-CENS-paso8-profile-v1'):
        raise ValidationError('El JSON debe ser un perfil de los diez pasos (pmo-cens-pmo-profile-v1)')
    data=obj.get('steps')
    if not isinstance(data,list) or len(data)!=10:raise ValidationError('El perfil debe incluir exactamente diez pasos')
    prepared=[];used=set()
    for x in data:
        if not isinstance(x,dict):raise ValidationError('Paso JSON inválido')
        n=_int_score(x.get('step',x.get('n')),1,10,'Número de paso')
        if n in used:raise ValidationError('Paso duplicado')
        used.add(n)
        count=x.get('questionCount',COUNTS[n])
        if _int_score(count,COUNTS[n],COUNTS[n],'Cantidad de preguntas')!=COUNTS[n]:raise ValidationError('Cantidad incorrecta')
        ans=x.get('answers')
        if isinstance(ans,list) and len(ans)==COUNTS[n] and any(a is not None for a in ans):
            # Un archivo incompleto no puede presentarse como total definitivo.
            if x.get('totalScore') is not None and not all(a is not None for a in ans):
                raise ValidationError('No se admite total definitivo con respuestas parciales')
            vals=_prepare(n,answers=ans,source=x.get('source',''),note=x.get('notes',''),evidence=x.get('evidence',''),target=x.get('desired'))
            if x.get('totalScore') is not None and vals[0]!=_int_score(x['totalScore'],COUNTS[n],5*COUNTS[n],'Puntaje reportado'):
                raise ValidationError('El total no coincide con las respuestas del Paso '+str(n))
        else:
            vals=_prepare(n,score=x.get('totalScore',x.get('total')),source=x.get('source') or 'Importación perfil JSON',note=x.get('notes',''),evidence=x.get('evidence',''),target=x.get('desired'))
        weight=_int_score(x.get('weightPercent',10),0,100,'Peso')
        prepared.append((n,vals,weight))
    if sum(x[2] for x in prepared)!=100:raise ValidationError('Los pesos importados deben sumar 100%')
    scale=obj.get('scale','zero5')
    if scale not in SCALES:raise ValidationError('Escala importada no compatible')
    return sorted(prepared),scale

def import_json(obj,name='Perfil PMO importado',owner='Equipo PMO',demo=False,path=None):
    prepared,scale=_parse_import(obj)
    if not str(name).strip() or not str(owner).strip():raise ValidationError('Nombre y responsable requeridos')
    with transaction(path) as c:
        pid=_uid();c.execute('INSERT INTO p8_profiles VALUES(?,?,?,?,?,?,?)',(pid,name.strip(),owner.strip(),scale,int(bool(demo)),_now(),_now()))
        for n,vals,w in prepared:
            c.execute('''INSERT INTO p8_profile_steps(perfil_id,paso,puntaje,respuestas_json,peso,meta,fuente,observacion,evidencia,registrado_en)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',(pid,n,vals[0],vals[1],w,vals[5],vals[2],vals[3],vals[4],_now()))
    return pid

def backup(path=None):
    return {'schema':'PMO-FLYWHEEL-CENS-paso8-profile-backup-v1','tables':{
        t:_rows('SELECT * FROM '+t,path=path) for t in ('p8_profiles','p8_profile_steps','p8_profile_history')}}

def restore(obj,confirmed=False,path=None):
    names=('p8_profiles','p8_profile_steps','p8_profile_history')
    if not confirmed:raise ValidationError('Confirma la restauración específica del perfil')
    if not isinstance(obj,dict) or obj.get('schema')!='PMO-FLYWHEEL-CENS-paso8-profile-backup-v1' or set(obj.get('tables',{}))!=set(names):
        raise ValidationError('Respaldo de perfil no compatible')
    with transaction(path) as c:
        for t in reversed(names):c.execute('DELETE FROM '+t)
        for t in names:
            columns={x[1] for x in c.execute(f'PRAGMA table_info({t})')}
            for x in obj['tables'][t]:
                if not isinstance(x,dict) or not set(x).issubset(columns):raise ValidationError('Columnas no válidas en respaldo')
                keys=list(x)
                if keys:c.execute('INSERT INTO '+t+' ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',[x[k] for k in keys])
    return True

# Lectura exclusivamente de autoevaluaciones finalizadas de los Pasos 1–7 y 9.
# No infiere una nota metodológica de la madurez de servicios del Paso 8.
_ORIGINS = {
 1:('p1_autoevaluaciones','estado','Finalizada','puntaje','finalizada_en','evaluador'),
 2:('p2_autoevaluaciones','estado','Finalizada','puntaje','finalizada_en','evaluador'),
 3:('p3_evaluaciones','estado','Finalizada','puntaje','finalizada_en','responsable'),
 4:('p4_evaluations','estado','Finalizada','puntaje','finalizado_en','responsable'),
 5:('p5_evaluations','state','Finalizada','score','finished_at','owner'),
 6:('p6_evaluaciones','estado','Finalizada','puntaje','finalizado_en','responsable'),
 7:('p7_evaluaciones','estado','Archivada','puntaje','archivado_en','responsable'),
 9:('p9_evaluaciones','estado','Archivada','puntaje','archivado_en','responsable'),
 10:('p10_evaluaciones','estado','Archivada','puntaje','archivado_en','responsable'),
}

def available_completed_assessments(path=None):
    found=[]
    with closing(connect(path)) as c:
        for n,(table,status_col,status,score_col,date_col,owner_col) in _ORIGINS.items():
            if not c.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():continue
            query=(f'SELECT id,{score_col} as score,{date_col} as assessed_at,{owner_col} as owner '
                   f'FROM {table} WHERE {status_col}=? AND {score_col} IS NOT NULL ORDER BY {date_col} DESC')
            for r in c.execute(query,(status,)):
                raw=r['score']
                if isinstance(raw,int) and COUNTS[n]<=raw<=COUNTS[n]*5:
                    found.append({'step':n,'id':r['id'],'score':raw,'date':r['assessed_at'],
                                  'owner':r['owner'],'source':table,'count':COUNTS[n]})
    return found

def sync_completed_assessment(pid,step,source_id,replace=False,path=None):
    matching=[x for x in available_completed_assessments(path) if x['step']==int(step) and x['id']==source_id]
    if not matching:raise ValidationError('La evaluación original no está finalizada o no tiene 100% de respuestas')
    r=matching[0]
    current=next(x for x in report(pid,path)['steps'] if x['paso']==r['step'])
    if current['puntaje'] is not None and not replace:raise ValidationError('Este paso ya contiene una evaluación. Confirma reemplazo.')
    save_step(pid,r['step'],score=r['score'],source=f"{r['source']} · {r['id']}",
              note=f"Copia de consulta, finalizada {r['date']}; responsable original: {r['owner']}",
              evidence=f"SQLite:{r['source']}:{r['id']}",target=current['meta'],path=path)
    return r['step']
