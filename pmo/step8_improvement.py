"""V0.39.25 · Ciclo verificable de mejora de servicios, aditivo al Paso 08.

No recalifica los 26 servicios ni modifica retrospectivamente p8_actions.
Las autorizaciones siguen siendo decisiones humanas trazadas.
"""
from __future__ import annotations
import hashlib
import json
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from .storage import connect, transaction
from . import step8 as core

STAGES = ('Propuesta','Aprobada','En ejecución','En verificación','Completada','Cancelada')
MILESTONE_STATES = ('Pendiente','En curso','Bloqueado','Cumplido','Cancelado')
PRIORITIES = ('Crítica','Alta','Media','Baja')
EVIDENCE_TYPES = ('Acta','Indicador','Informe','Documento','Enlace','Otro')
LEGACY_STATE = {'Propuesta':'Pendiente','Aprobada':'Pendiente',
                'En ejecución':'En ejecución','En verificación':'En ejecución',
                'Completada':'Completada','Cancelada':'Cancelada'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS p8_mejora_detalle (
 accion_id TEXT PRIMARY KEY REFERENCES p8_actions(id) ON DELETE CASCADE,
 registro_historico INTEGER NOT NULL DEFAULT 0,
 codigo_publico TEXT NOT NULL DEFAULT '',
 causa_raiz TEXT NOT NULL DEFAULT '',objetivo TEXT NOT NULL DEFAULT '',
 prioridad TEXT NOT NULL DEFAULT 'Media' CHECK(prioridad IN ('Crítica','Alta','Media','Baja')),
 alineacion TEXT NOT NULL DEFAULT '',viabilidad TEXT NOT NULL DEFAULT '',
 recursos TEXT NOT NULL DEFAULT '',dependencias TEXT NOT NULL DEFAULT '',
 riesgos TEXT NOT NULL DEFAULT '',
 criterio_aceptacion TEXT NOT NULL DEFAULT '',
 nivel_objetivo INTEGER CHECK(nivel_objetivo IS NULL OR nivel_objetivo BETWEEN 1 AND 5),
 fase TEXT NOT NULL DEFAULT 'Propuesta' CHECK(fase IN ('Propuesta','Aprobada','En ejecución','En verificación','Completada','Cancelada')),
 registrado_por TEXT NOT NULL,aprobado_por TEXT NOT NULL DEFAULT '',aprobado_en TEXT,
 cerrado_por TEXT NOT NULL DEFAULT '',cerrado_en TEXT,
 actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_p8_mejora_codigo_publico ON p8_mejora_detalle(codigo_publico) WHERE codigo_publico<>'';
CREATE TABLE IF NOT EXISTS p8_mejora_hitos (
 id TEXT PRIMARY KEY,accion_id TEXT NOT NULL REFERENCES p8_actions(id) ON DELETE CASCADE,
 titulo TEXT NOT NULL,fecha_meta TEXT NOT NULL,responsable TEXT NOT NULL,
 estado TEXT NOT NULL CHECK(estado IN ('Pendiente','En curso','Bloqueado','Cumplido','Cancelado')),
 evidencia TEXT NOT NULL DEFAULT '',actualizado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p8_mh_accion ON p8_mejora_hitos(accion_id);
CREATE TABLE IF NOT EXISTS p8_mejora_soportes (
 id TEXT PRIMARY KEY,accion_id TEXT NOT NULL REFERENCES p8_actions(id) ON DELETE CASCADE,
 tipo TEXT NOT NULL CHECK(tipo IN ('Acta','Indicador','Informe','Documento','Enlace','Otro')),
 descripcion TEXT NOT NULL,referencia TEXT NOT NULL,fecha TEXT NOT NULL,
 registrado_por TEXT NOT NULL,creado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p8_ms_accion ON p8_mejora_soportes(accion_id);
CREATE TABLE IF NOT EXISTS p8_mejora_verificaciones (
 id TEXT PRIMARY KEY,accion_id TEXT NOT NULL REFERENCES p8_actions(id) ON DELETE CASCADE,
 resultado TEXT NOT NULL CHECK(resultado IN ('Conforme','No conforme','Requiere ajustes')),
 valor_observado TEXT NOT NULL DEFAULT '',observaciones TEXT NOT NULL,
 evidencia_id TEXT REFERENCES p8_mejora_soportes(id) ON DELETE SET NULL,
 verificador TEXT NOT NULL,fecha TEXT NOT NULL,creado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p8_mv_accion ON p8_mejora_verificaciones(accion_id);
CREATE TABLE IF NOT EXISTS p8_mejora_fuentes (
 accion_id TEXT NOT NULL REFERENCES p8_actions(id) ON DELETE CASCADE,
 ticket_id TEXT NOT NULL,tipo TEXT NOT NULL,fuente TEXT NOT NULL,
 creado_en TEXT NOT NULL,PRIMARY KEY(accion_id,ticket_id,tipo,fuente)
);
CREATE TABLE IF NOT EXISTS p8_mejora_auditoria (
 id TEXT PRIMARY KEY,accion_id TEXT NOT NULL REFERENCES p8_actions(id) ON DELETE CASCADE,
 evento TEXT NOT NULL,actor TEXT NOT NULL,antes_json TEXT NOT NULL,
 despues_json TEXT NOT NULL,fecha TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p8_ma_accion ON p8_mejora_auditoria(accion_id,fecha);
CREATE TABLE IF NOT EXISTS p8_mejora_correspondencias (
 ciclo_id TEXT NOT NULL,servicio_ref INTEGER NOT NULL,servicio_cens TEXT NOT NULL,
 estado TEXT NOT NULL CHECK(estado IN ('Por verificar','Verificada','Rechazada')),
 justificacion TEXT NOT NULL DEFAULT '',verificador TEXT NOT NULL DEFAULT '',
 verificado_en TEXT,PRIMARY KEY(ciclo_id,servicio_ref,servicio_cens),
 FOREIGN KEY(ciclo_id,servicio_ref,servicio_cens)
 REFERENCES p8_service_links(ciclo_id,servicio_ref,servicio_cens) ON DELETE CASCADE
);
'''

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def _uuid():return str(uuid.uuid4())
def _required(value,label):
    if not str(value or '').strip():raise core.ValidationError(label+' es obligatorio')
    return str(value).strip()
def _date(value):
    try:return date.fromisoformat(str(value)).isoformat()
    except (ValueError,TypeError):raise core.ValidationError('Fecha inválida, utiliza AAAA-MM-DD')
def _exists(c,action_id):
    a=c.execute('SELECT * FROM p8_actions WHERE id=?',(action_id,)).fetchone()
    if not a:raise core.ValidationError('La iniciativa no existe')
    return dict(a)
def _code(c,action_id):
    a=_exists(c,action_id)
    cycle=c.execute('SELECT inicio FROM p8_cycles WHERE id=?',(a['ciclo_id'],)).fetchone()
    year=str(cycle['inicio'])[:4]
    used={int(r[0].rsplit('-',1)[1]) for r in c.execute(
        "SELECT codigo_publico FROM p8_mejora_detalle WHERE codigo_publico LIKE ?",
        (f'MEJ-{year}-%',)) if str(r[0]).rsplit('-',1)[-1].isdigit()}
    n=1
    while n in used:n+=1
    return f'MEJ-{year}-{n:03d}'

def _audit(c,key,event,actor,before,after):
    c.execute('INSERT INTO p8_mejora_auditoria VALUES(?,?,?,?,?,?,?)',
        (_uuid(),key,event,_required(actor,'Responsable'),json.dumps(before,ensure_ascii=False,default=str),
         json.dumps(after,ensure_ascii=False,default=str),now()))
def initialize(path=None):
    core.initialize(path)
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        col={r['name'] for r in c.execute('PRAGMA table_info(p8_mejora_detalle)')}
        if 'registro_historico' not in col:
            c.execute('ALTER TABLE p8_mejora_detalle ADD COLUMN registro_historico INTEGER NOT NULL DEFAULT 0')
        if 'codigo_publico' not in col:
            c.execute('ALTER TABLE p8_mejora_detalle ADD COLUMN codigo_publico TEXT NOT NULL DEFAULT \'\'')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_p8_mejora_codigo_publico ON p8_mejora_detalle(codigo_publico) WHERE codigo_publico<>\'\'')
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES(25)')
        c.commit()
def detail(action_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        a=_exists(c,action_id)
        v=c.execute('SELECT * FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone()
        return {**a,'detalle':dict(v) if v else None}
def initiatives(cycle_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        return [dict(r) for r in c.execute('''SELECT a.*,d.fase,d.prioridad,d.codigo_publico,d.objetivo,d.causa_raiz,
            d.criterio_aceptacion,d.actualizado_en AS fecha_detalle,
            (SELECT count(*) FROM p8_mejora_soportes e WHERE e.accion_id=a.id) AS soportes,
            (SELECT count(*) FROM p8_mejora_hitos h WHERE h.accion_id=a.id) AS hitos,
            (SELECT count(*) FROM p8_mejora_verificaciones v WHERE v.accion_id=a.id AND v.resultado='Conforme') AS verificaciones
            FROM p8_actions a LEFT JOIN p8_mejora_detalle d ON d.accion_id=a.id
            WHERE a.ciclo_id=? ORDER BY a.fecha_meta,a.creado_en''',(cycle_id,))]
def _upsert_detail(c,action_id,actor,fields,creation=False):
    before=c.execute('SELECT * FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone()
    before=dict(before) if before else None
    if fields.get('prioridad','Media') not in PRIORITIES:raise core.ValidationError('Prioridad no válida')
    target=fields.get('nivel_objetivo')
    if target not in (None,'') and (str(target) not in '12345' or len(str(target))!=1):
        raise core.ValidationError('El nivel objetivo debe ser 1–5')
    stage=fields.get('fase','Propuesta')
    if stage not in STAGES:raise core.ValidationError('Etapa desconocida')
    vals={k:str(fields.get(k,'')).strip() for k in ('causa_raiz','objetivo','alineacion','viabilidad','recursos','dependencias','riesgos','criterio_aceptacion')}
    vals.update(prioridad=fields.get('prioridad','Media'),nivel_objetivo=int(target) if target not in (None,'') else None)
    if before is None:
        c.execute('''INSERT INTO p8_mejora_detalle(accion_id,causa_raiz,objetivo,prioridad,alineacion,viabilidad,recursos,
        dependencias,riesgos,criterio_aceptacion,nivel_objetivo,registrado_por,actualizado_en)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(action_id,vals['causa_raiz'],vals['objetivo'],vals['prioridad'],
            vals['alineacion'],vals['viabilidad'],vals['recursos'],vals['dependencias'],vals['riesgos'],
            vals['criterio_aceptacion'],vals['nivel_objetivo'],actor,now()))
    else:
        if before['fase'] in ('Completada','Cancelada'):
            raise core.ValidationError('La iniciativa ya finalizó: no se puede reescribir su ficha')
        c.execute('''UPDATE p8_mejora_detalle SET causa_raiz=?,objetivo=?,prioridad=?,alineacion=?,viabilidad=?,
        recursos=?,dependencias=?,riesgos=?,criterio_aceptacion=?,nivel_objetivo=?,actualizado_en=? WHERE accion_id=?''',
        (vals['causa_raiz'],vals['objetivo'],vals['prioridad'],vals['alineacion'],vals['viabilidad'],vals['recursos'],
         vals['dependencias'],vals['riesgos'],vals['criterio_aceptacion'],vals['nivel_objetivo'],now(),action_id))
    if before is None:
        c.execute('UPDATE p8_mejora_detalle SET codigo_publico=? WHERE accion_id=?',(_code(c,action_id),action_id))
    _audit(c,action_id,'Crear iniciativa' if creation else 'Actualizar diseño',actor,before,vals)

def create_initiative(cycle_id,service_ref,title,owner,due,actor,*,description='',impact='Medio',indicator='',
                      causa_raiz='',objetivo='',prioridad='Media',alineacion='',viabilidad='',recursos='',
                      dependencias='',riesgos='',criterio_aceptacion='',nivel_objetivo=None,path=None):
    initialize(path)
    key=core.save_action(cycle_id,int(service_ref),_required(title,'Acción'),_required(owner,'Responsable'),
                         _date(due),description,impact,indicator=indicator,path=path)
    values=locals()
    try:
        with transaction(path) as c:
            _upsert_detail(c,key,_required(actor,'Actor'),values,creation=True)
    except Exception:
        core.delete_action(key,path)
        raise
    return key

def extend_legacy(action_id,actor,path=None):
    initialize(path)
    with transaction(path) as c:
        a=_exists(c,action_id)
        if c.execute('SELECT 1 FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone():return False
        _upsert_detail(c,action_id,_required(actor,'Actor'),{'objetivo':a['titulo']},creation=False)
        c.execute('UPDATE p8_mejora_detalle SET registro_historico=1 WHERE accion_id=?',(action_id,))
    return True

def update_plan(action_id,actor,**kw):
    path=kw.pop('path',None)
    initialize(path)
    with transaction(path) as c:
        _exists(c,action_id)
        if not c.execute('SELECT 1 FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone():
            raise core.ValidationError('Primero incorpora la ficha estructurada')
        _upsert_detail(c,action_id,_required(actor,'Actor'),kw)
    return True

def set_stage(action_id,new_stage,actor,evidence='',path=None):
    initialize(path)
    if new_stage not in STAGES:raise core.ValidationError('Etapa inválida')
    with transaction(path) as c:
        a=_exists(c,action_id)
        before=c.execute('SELECT * FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone()
        if not before:raise core.ValidationError('La iniciativa debe estar estructurada')
        before=dict(before);old=before['fase']
        if old in ('Completada','Cancelada') and new_stage!=old:
            raise core.ValidationError('Las decisiones finales son inmutables; crea una nueva iniciativa')
        legal={'Propuesta':('Aprobada','Cancelada'),
               'Aprobada':('En ejecución','Cancelada'),
               'En ejecución':('En verificación','Cancelada'),
               'En verificación':('En ejecución','Completada','Cancelada'),
               'Completada':(), 'Cancelada':()}
        if new_stage==old:return False
        if new_stage not in legal[old]:raise core.ValidationError('Transición de estado no permitida')
        if new_stage=='Aprobada' and not (before['objetivo'] and before['criterio_aceptacion'] and before['causa_raiz']):
            raise core.ValidationError('Para aprobar define causa, objetivo y criterio de aceptación')
        if new_stage=='Aprobada':
            rv=c.execute('SELECT estado,validado_actual,validado_deseado FROM p8_revisiones WHERE ciclo_id=? AND servicio_ref=?',
                         (a['ciclo_id'],a['servicio_ref'])).fetchone()
            rating=c.execute('SELECT estado,actual,deseado FROM p8_ratings WHERE ciclo_id=? AND servicio_ref=?',
                             (a['ciclo_id'],a['servicio_ref'])).fetchone()
            if not rv or rv['estado']!='Validado' or rating['estado']!='Evaluado' or (rv['validado_actual'],rv['validado_deseado'])!=(rating['actual'],rating['deseado']):
                raise core.ValidationError('La aprobación requiere una evaluación de madurez vigente y validada con evidencia')
        if new_stage=='Completada':
            last=c.execute('SELECT resultado FROM p8_mejora_verificaciones WHERE accion_id=? ORDER BY creado_en DESC,rowid DESC LIMIT 1',(action_id,)).fetchone()
            if not last or last['resultado']!='Conforme':
                raise core.ValidationError('Para completar requiere que la última verificación sea conforme y documentada')
            if c.execute("SELECT count(*) FROM p8_mejora_hitos WHERE accion_id=? AND estado NOT IN ('Cumplido','Cancelado')",(action_id,)).fetchone()[0]:
                raise core.ValidationError('Existen hitos pendientes o bloqueados')
        if new_stage in ('Aprobada','Cancelada'):
            _required(evidence,'Referencia de autorización o decisión')
        c.execute('''UPDATE p8_mejora_detalle SET fase=?,aprobado_por=CASE WHEN ?='Aprobada' THEN ? ELSE aprobado_por END,
          aprobado_en=CASE WHEN ?='Aprobada' THEN ? ELSE aprobado_en END,
          cerrado_por=CASE WHEN ? IN ('Completada','Cancelada') THEN ? ELSE cerrado_por END,
          cerrado_en=CASE WHEN ? IN ('Completada','Cancelada') THEN ? ELSE cerrado_en END,
          actualizado_en=? WHERE accion_id=?''',
          (new_stage,new_stage,actor,new_stage,now(),new_stage,actor,new_stage,now(),now(),action_id))
        if not before['registro_historico']:
            c.execute('UPDATE p8_actions SET estado=?,evidencia=CASE WHEN ?<>\'\' THEN ? ELSE evidencia END, actualizado_en=? WHERE id=?',
                      (LEGACY_STATE[new_stage],str(evidence),str(evidence),now(),action_id))
        _audit(c,action_id,'Transición de etapa',actor,{'fase':old},{'fase':new_stage,'referencia':evidence})
    return True

def milestones(action_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:return [dict(x) for x in c.execute('SELECT * FROM p8_mejora_hitos WHERE accion_id=? ORDER BY fecha_meta,id',(action_id,))]
def save_milestone(action_id,title,owner,due,actor,status='Pendiente',evidence='',key=None,path=None):
    initialize(path)
    if status not in MILESTONE_STATES:raise core.ValidationError('Estado de hito inválido')
    with transaction(path) as c:
        _exists(c,action_id)
        x=c.execute('SELECT fase FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone()
        if not x or x['fase'] in ('Completada','Cancelada'):raise core.ValidationError('Iniciativa finalizada o no estructurada')
        before=dict(c.execute('SELECT * FROM p8_mejora_hitos WHERE id=? AND accion_id=?',(key,action_id)).fetchone()) if key and c.execute('SELECT 1 FROM p8_mejora_hitos WHERE id=? AND accion_id=?',(key,action_id)).fetchone() else None
        if key and not before:raise core.ValidationError('Hito no encontrado')
        if status=='Cumplido' and not str(evidence).strip():raise core.ValidationError('Hito cumplido requiere evidencia')
        values=(_required(title,'Hito'),_date(due),_required(owner,'Responsable'),status,str(evidence).strip(),now())
        if key:c.execute('UPDATE p8_mejora_hitos SET titulo=?,fecha_meta=?,responsable=?,estado=?,evidencia=?,actualizado_en=? WHERE id=? AND accion_id=?',values+(key,action_id))
        else:
            key=_uuid();c.execute('INSERT INTO p8_mejora_hitos VALUES(?,?,?,?,?,?,?,?)',(key,action_id,*values))
        _audit(c,action_id,'Actualizar hito' if before else 'Crear hito',actor,before,{'id':key,'titulo':title,'estado':status,'evidencia':evidence})
    return key

def supports(action_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:return [dict(x) for x in c.execute('SELECT * FROM p8_mejora_soportes WHERE accion_id=? ORDER BY fecha,creado_en',(action_id,))]
def add_support(action_id,kind,description,reference,actor,when=None,path=None):
    initialize(path)
    if kind not in EVIDENCE_TYPES:raise core.ValidationError('Tipo de soporte desconocido')
    with transaction(path) as c:
        _exists(c,action_id)
        if not c.execute('SELECT 1 FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone():
            raise core.ValidationError('Iniciativa no estructurada')
        key=_uuid();c.execute('INSERT INTO p8_mejora_soportes VALUES(?,?,?,?,?,?,?,?)',
            (key,action_id,kind,_required(description,'Descripción'),_required(reference,'Referencia'),
            _date(when or date.today()),_required(actor,'Actor'),now()))
        _audit(c,action_id,'Agregar soporte',actor,{}, {'id':key,'tipo':kind,'referencia':reference})
    return key

def verifications(action_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:return [dict(x) for x in c.execute('SELECT * FROM p8_mejora_verificaciones WHERE accion_id=? ORDER BY creado_en,id',(action_id,))]
def verify(action_id,result,observations,actor,evidence_id,value='',when=None,path=None):
    initialize(path)
    if result not in ('Conforme','No conforme','Requiere ajustes'):raise core.ValidationError('Resultado inválido')
    with transaction(path) as c:
        _exists(c,action_id)
        state=c.execute('SELECT fase FROM p8_mejora_detalle WHERE accion_id=?',(action_id,)).fetchone()
        if not state or state['fase']!='En verificación':raise core.ValidationError('La iniciativa debe encontrarse En verificación')
        if not evidence_id or not c.execute('SELECT 1 FROM p8_mejora_soportes WHERE id=? AND accion_id=?',(evidence_id,action_id)).fetchone():
            raise core.ValidationError('Selecciona soporte registrado de esta iniciativa')
        key=_uuid();c.execute('INSERT INTO p8_mejora_verificaciones VALUES(?,?,?,?,?,?,?,?,?)',
            (key,action_id,result,str(value).strip(),_required(observations,'Conclusión'),evidence_id,
             _required(actor,'Verificador'),_date(when or date.today()),now()))
        _audit(c,action_id,'Verificar resultado',actor,{}, {'id':key,'resultado':result,'soporte':evidence_id})
    return key

def attach_finding(action_id,ticket_id,kind,source,actor,path=None):
    initialize(path)
    with transaction(path) as c:
        _exists(c,action_id)
        if not c.execute('SELECT 1 FROM p8_findings WHERE ticket_id=? AND tipo=? AND fuente=?',(ticket_id,kind,source)).fetchone():
            raise core.ValidationError('Hallazgo inexistente: sincroniza primero Paso 07')
        c.execute('INSERT OR IGNORE INTO p8_mejora_fuentes VALUES(?,?,?,?,?)',(action_id,ticket_id,kind,source,now()))
        _audit(c,action_id,'Vincular hallazgo',actor,{}, {'ticket_id':ticket_id,'tipo':kind,'fuente':source})
    return True

def linked_findings(action_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        return [dict(x) for x in c.execute('''SELECT h.*,f.descripcion,f.estado FROM p8_mejora_fuentes h JOIN p8_findings f
           ON f.ticket_id=h.ticket_id AND f.tipo=h.tipo AND f.fuente=h.fuente WHERE h.accion_id=?''',(action_id,))]
def correspondence(cycle_id,path=None):
    initialize(path)
    with closing(connect(path)) as c:
        return [dict(r) for r in c.execute('''SELECT l.*,COALESCE(v.estado,'Por verificar') AS verificacion,
           COALESCE(v.justificacion,'') AS justificacion,v.verificador
           FROM p8_service_links l LEFT JOIN p8_mejora_correspondencias v
           ON v.ciclo_id=l.ciclo_id AND v.servicio_ref=l.servicio_ref AND v.servicio_cens=l.servicio_cens
           WHERE l.ciclo_id=? ORDER BY l.servicio_ref''',(cycle_id,))]
def verify_correspondence(cycle_id,service_ref,service_id,state,justification,actor,path=None):
    initialize(path)
    if state not in ('Por verificar','Verificada','Rechazada'):raise core.ValidationError('Estado inválido')
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p8_service_links WHERE ciclo_id=? AND servicio_ref=? AND servicio_cens=?',
                         (cycle_id,int(service_ref),service_id)).fetchone():raise core.ValidationError('No existe correspondencia para verificar')
        c.execute('''INSERT INTO p8_mejora_correspondencias VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(ciclo_id,servicio_ref,servicio_cens) DO UPDATE SET estado=excluded.estado,
        justificacion=excluded.justificacion,verificador=excluded.verificador,verificado_en=excluded.verificado_en''',
        (cycle_id,int(service_ref),service_id,state,_required(justification,'Justificación'),_required(actor,'Verificador'),now()))
    return True

def quality(cycle_id,path=None):
    initialize(path)
    from . import step8_documented as doc
    rr=core.report(cycle_id,path)
    counts={'evaluados':0,'validados':0,'sin_soporte':0,'pendientes':0,'no_ofrecidos':0,'discrepancias':0}
    for x in rr['ratings']:
        if x['estado']=='No ofrecido':counts['no_ofrecidos']+=1;continue
        if x['estado']=='Pendiente':counts['pendientes']+=1;continue
        counts['evaluados']+=1
        r=doc.review(cycle_id,x['servicio_ref'],path)
        if r['vigente']:counts['validados']+=1
        if not doc.evidences(cycle_id,x['servicio_ref'],path) and not x['evidencia']:
            counts['sin_soporte']+=1
        if r['estado']=='Validado' and not r['vigente']:counts['discrepancias']+=1
    counts['total']=26
    counts['cobertura_pct']=round(counts['evaluados']/26*100)
    counts['calidad_pct']=round(counts['validados']/counts['evaluados']*100) if counts['evaluados'] else None
    counts['acciones']=len(initiatives(cycle_id,path))
    counts['verificadas']=sum(x['fase']=='Completada' for x in initiatives(cycle_id,path))
    return counts

def priority_view(cycle_id,path=None):
    rr=core.report(cycle_id,path)
    d={x['servicio_ref']:x for x in rr['ratings']}
    out=[]
    for x in initiatives(cycle_id,path):
        rating=d[x['servicio_ref']]
        out.append({**x,'servicio':core.CAT[x['servicio_ref']]['name_es'],
                    'brecha_pp':rating['gap'],
                    'evaluacion_estado':rating['estado']})
    return out

def compare_cycles(before_id,after_id,path=None):
    initialize(path)
    before=core.report(before_id,path);after=core.report(after_id,path)
    if before_id==after_id:raise core.ValidationError('Selecciona dos ciclos diferentes')
    left={x['servicio_ref']:x for x in before['ratings']}
    right={x['servicio_ref']:x for x in after['ratings']}
    out=[]
    for service in core.CATALOG:
        a=left[service['id']];b=right[service['id']]
        comparable=a['estado']=='Evaluado' and b['estado']=='Evaluado'
        out.append({'id':service['id'],'servicio':service['name_es'],
           'categoria':core.CATEGORIES_ES[service['category']],
           'antes':a['actual'] if comparable else None,
           'despues':b['actual'] if comparable else None,
           'delta':(b['actual']-a['actual']) if comparable else None,
           'comparable':comparable,
           'estado_antes':a['estado'],'estado_despues':b['estado']})
    return {'ciclos':(before['cycle'],after['cycle']),
            'filas':out,'comparables':sum(x['comparable'] for x in out),
            'mejoraron':sum(x['delta']>0 for x in out if x['comparable']),
            'sin_cambio':sum(x['delta']==0 for x in out if x['comparable']),
            'retrocedieron':sum(x['delta']<0 for x in out if x['comparable'])}

def evidence_chain(action_id,path=None):
    info=detail(action_id,path)
    rating=next(x for x in core.ratings(info['ciclo_id'],path) if x['servicio_ref']==info['servicio_ref'])
    from . import step8_documented as doc
    review=doc.review(info['ciclo_id'],info['servicio_ref'],path)
    return {'accion':info,'madurez':rating,'evaluacion_validada':review['vigente'],
            'hallazgos':linked_findings(action_id,path),'hitos':milestones(action_id,path),
            'soportes':supports(action_id,path),'verificaciones':verifications(action_id,path),
            'nota':'Completar la iniciativa no recalifica automáticamente el servicio ni demuestra beneficios del Paso 09.'}

def export_improvements(cycle_id,path=None):
    initialize(path)
    cycle=core.cycle(cycle_id,path)
    if not cycle:raise core.ValidationError('Ciclo inexistente')
    data={'schema':'PMO-FLYWHEEL-CENS-paso8-mejoras-v03925-v1','creado_en':now(),
          'ciclo':cycle,'calidad':quality(cycle_id,path),'iniciativas':[]}
    for item in initiatives(cycle_id,path):
        data['iniciativas'].append(evidence_chain(item['id'],path))
    data['correspondencias']=correspondence(cycle_id,path)
    data['sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    return data

# Respaldo integral V0.39.25. El JSON documental v2 sigue disponible como legado,
# pero únicamente esta versión incluye hitos, decisiones y cadena de evidencias.
EXT_TABLES = ('p8_mejora_detalle','p8_mejora_hitos','p8_mejora_soportes',
              'p8_mejora_verificaciones','p8_mejora_fuentes','p8_mejora_auditoria',
              'p8_mejora_correspondencias')

def has_extended_records(path=None):
    initialize(path)
    with closing(connect(path)) as c:
        return any(c.execute('SELECT 1 FROM '+t+' LIMIT 1').fetchone() for t in EXT_TABLES)

def backup_v03925(path=None):
    initialize(path)
    from . import step8_documented as doc
    base=doc.backup_full(path)
    with closing(connect(path)) as c:
        extras={t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in EXT_TABLES}
    payload={'schema':'PMO-FLYWHEEL-CENS-paso8-integral-v03925-v3',
             'documental_v2':base,'tablas_mejora':extras}
    payload['sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')).hexdigest()
    return payload

def _write_rows(c,table,items):
    column_names={r['name'] for r in c.execute('PRAGMA table_info('+table+')')}
    if not isinstance(items,list):raise core.ValidationError('El respaldo contiene una tabla inválida: '+table)
    for item in items:
        if not isinstance(item,dict) or not item or not set(item).issubset(column_names):
            raise core.ValidationError('Columnas no válidas en el respaldo: '+table)
        fields=list(item)
        c.execute('INSERT INTO '+table+' ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',
                  tuple(item[x] for x in fields))

def restore_v03925(payload,confirmed=False,path=None):
    """Restaura SOLO el expediente Paso 08, en transacción y tras validarlo en staging.

    No modifica las tablas de otros pasos y no borra datos ante un JSON inválido.
    """
    if not confirmed:raise core.ValidationError('Debes confirmar la restauración integral del Paso 08')
    if not isinstance(payload,dict) or payload.get('schema')!='PMO-FLYWHEEL-CENS-paso8-integral-v03925-v3':
        raise core.ValidationError('Se requiere el respaldo integral V0.39.25')
    extras=payload.get('tablas_mejora');base=payload.get('documental_v2')
    if not isinstance(extras,dict) or set(extras)!=set(EXT_TABLES) or not isinstance(base,dict):
        raise core.ValidationError('El respaldo no contiene todas las tablas de mejora')
    signed=dict(payload);digest=signed.pop('sha256',None)
    expected=hashlib.sha256(json.dumps(signed,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')).hexdigest()
    if digest!=expected:raise core.ValidationError('La huella de respaldo no coincide; archivo modificado o incompleto')
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from . import step8_documented as doc
    from .storage import initialize as init_storage
    with TemporaryDirectory(prefix='pmo_p8_staging_') as temp:
        scratch=Path(temp)/'stage.sqlite3'
        init_storage(scratch);initialize(scratch);doc.initialize(scratch)
        # La restauración histórica decodifica adjuntos base64 en su entrada; usar copia.
        shadow=json.loads(json.dumps(base))
        doc.restore_full(shadow,confirmed=True,path=scratch)
        with transaction(scratch) as c:
            for table in EXT_TABLES:_write_rows(c,table,extras[table])
            if c.execute('PRAGMA foreign_key_check').fetchall():
                raise core.ValidationError('Existen referencias cruzadas inválidas en el respaldo')
        with closing(connect(scratch)) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise core.ValidationError('Integridad de respaldo inválida')
            rows_to_restore={t:[dict(x) for x in c.execute('SELECT * FROM '+t)]
                             for t in (*doc.BASE_TABLES,*doc.DOC_TABLES,*EXT_TABLES)}
    # No alterar la base en el paso de validación. La aplicación exige confirmación.
    initialize(path);doc.initialize(path)
    delete_order=('p8_mejora_verificaciones','p8_mejora_fuentes','p8_mejora_auditoria',
                  'p8_mejora_correspondencias','p8_mejora_hitos','p8_mejora_soportes','p8_mejora_detalle')
    with transaction(path) as c:
        for table in delete_order:c.execute('DELETE FROM '+table)
        for table in reversed(doc.DOC_TABLES):c.execute('DELETE FROM '+table)
        for table in reversed(doc.BASE_TABLES):c.execute('DELETE FROM '+table)
        for table in (*doc.BASE_TABLES,*doc.DOC_TABLES,*EXT_TABLES):
            _write_rows(c,table,rows_to_restore[table])
        if c.execute('PRAGMA foreign_key_check').fetchall():
            raise core.ValidationError('La restauración produjo referencias inválidas')
    return True
