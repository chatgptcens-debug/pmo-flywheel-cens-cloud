"""Paso 8 · Mejora de servicios. Madurez PMO-GA de 26 servicios (1–5).

Aditivo y auditable: las calificaciones son juicios del evaluador, NUNCA
se infieren del catálogo del Paso 4 ni de los tickets del Paso 7.
Media de categorías con igual peso reproduce el archivo PMO-GA recibido;
se presenta separadamente la media ponderada por cantidad de servicios.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, re, uuid
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from .storage import connect, transaction

CATALOG = json.loads((Path(__file__).parent / 'data' / 'step8_catalog.json').read_text(encoding='utf-8'))
CAT = {x['id']: x for x in CATALOG}
CATEGORIES = ('Strategic','Tactical','Operational')
CATEGORIES_ES = {'Strategic':'Estratégicos','Tactical':'Tácticos','Operational':'Operativos'}
MODULES = ('Evaluación de madurez','Perfil de madurez PMO','Resultados y brechas','Plan de mejora','Evolución e historial')
STATUS = ('Pendiente','Evaluado','No ofrecido')
STATES = ('Pendiente','En ejecución','Completada','Cancelada')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS p8_cycles (
 id TEXT PRIMARY KEY, nombre TEXT NOT NULL, inicio TEXT NOT NULL, fin TEXT NOT NULL,
 responsable TEXT NOT NULL, fuente TEXT NOT NULL, es_demo INTEGER NOT NULL DEFAULT 0,
 estado TEXT NOT NULL CHECK(estado IN ('Borrador','Cerrado')),
 creado_en TEXT NOT NULL, cerrado_en TEXT, hash_origen TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS p8_ratings (
 ciclo_id TEXT NOT NULL REFERENCES p8_cycles(id) ON DELETE CASCADE,
 servicio_ref INTEGER NOT NULL CHECK(servicio_ref BETWEEN 1 AND 26),
 estado TEXT NOT NULL CHECK(estado IN ('Pendiente','Evaluado','No ofrecido')),
 actual INTEGER CHECK(actual BETWEEN 1 AND 5),
 deseado INTEGER CHECK(deseado BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 revisado_por TEXT NOT NULL DEFAULT '', revisado_en TEXT,
 PRIMARY KEY(ciclo_id,servicio_ref),
 CHECK ((estado='Evaluado' AND actual IS NOT NULL AND deseado IS NOT NULL)
   OR (estado<>'Evaluado' AND actual IS NULL AND deseado IS NULL))
);
CREATE TABLE IF NOT EXISTS p8_actions (
 id TEXT PRIMARY KEY, ciclo_id TEXT NOT NULL REFERENCES p8_cycles(id) ON DELETE CASCADE,
 servicio_ref INTEGER NOT NULL CHECK(servicio_ref BETWEEN 1 AND 26),
 titulo TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
 responsable TEXT NOT NULL, fecha_meta TEXT NOT NULL, impacto TEXT NOT NULL CHECK(impacto IN ('Bajo','Medio','Alto')),
 estado TEXT NOT NULL CHECK(estado IN ('Pendiente','En ejecución','Completada','Cancelada')),
 evidencia TEXT NOT NULL DEFAULT '', indicador TEXT NOT NULL DEFAULT '',
 creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_p8_actions_ciclo ON p8_actions(ciclo_id);
CREATE TABLE IF NOT EXISTS p8_service_links (
 ciclo_id TEXT NOT NULL REFERENCES p8_cycles(id) ON DELETE CASCADE,
 servicio_ref INTEGER NOT NULL CHECK(servicio_ref BETWEEN 1 AND 26),
 servicio_cens TEXT NOT NULL, creado_en TEXT NOT NULL,
 PRIMARY KEY(ciclo_id,servicio_ref,servicio_cens)
);
CREATE TABLE IF NOT EXISTS p8_findings (
 ticket_id TEXT NOT NULL, tipo TEXT NOT NULL, servicio_origen TEXT NOT NULL DEFAULT '',
 descripcion TEXT NOT NULL, accion TEXT NOT NULL DEFAULT '', responsable TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL DEFAULT '', fecha TEXT NOT NULL DEFAULT '', fuente TEXT NOT NULL,
 importado_en TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(ticket_id,tipo,fuente)
);
CREATE TABLE IF NOT EXISTS p8_imports (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ciclo_id TEXT REFERENCES p8_cycles(id),
 fuente TEXT NOT NULL, firma TEXT NOT NULL, registrado_en TEXT NOT NULL,
 detalles TEXT NOT NULL
);
'''

class ValidationError(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def uid():return str(uuid.uuid4())
def rows(sql,args=(),path=None):
    with closing(connect(path)) as c:return [dict(r) for r in c.execute(sql,args)]
def row(sql,args=(),path=None):
    with closing(connect(path)) as c:
        r=c.execute(sql,args).fetchone();return dict(r) if r else None

def initialize(path=None):
    with closing(connect(path)) as c:
        c.executescript(SCHEMA)
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES(11)')
        c.commit()

def cycles(path=None):return rows('SELECT * FROM p8_cycles ORDER BY creado_en DESC,id DESC',path=path)
def cycle(key,path=None):return row('SELECT * FROM p8_cycles WHERE id=?',(key,),path)
def ratings(key,path=None):return rows('SELECT * FROM p8_ratings WHERE ciclo_id=? ORDER BY servicio_ref',(key,),path)
def actions(key,path=None):return rows('SELECT * FROM p8_actions WHERE ciclo_id=? ORDER BY fecha_meta,id',(key,),path)
def links(key,path=None):return rows('SELECT * FROM p8_service_links WHERE ciclo_id=? ORDER BY servicio_ref',(key,),path)
def findings(path=None):return rows('SELECT * FROM p8_findings ORDER BY importado_en DESC',path=path)
def imports(path=None):return rows('SELECT * FROM p8_imports ORDER BY id DESC LIMIT 30',path=path)

def _valid_dates(start,end):
    try:a=date.fromisoformat(str(start));b=date.fromisoformat(str(end))
    except (TypeError,ValueError):raise ValidationError('El periodo debe contener fechas ISO válidas')
    if b<=a:raise ValidationError('La fecha final debe ser posterior a la fecha inicial')
    return str(a),str(b)

def _score(x):
    if x is None or x=='':return None
    if isinstance(x,bool):raise ValidationError('Las calificaciones deben ser enteras de 1 a 5')
    try:v=float(x)
    except (ValueError,TypeError):raise ValidationError(f'Calificación inválida: {x}')
    if not math.isfinite(v) or not v.is_integer() or not 1<=v<=5:raise ValidationError(f'Calificación fuera de escala 1–5: {x}')
    return int(v)

def _create(c,name,start,end,owner,source,demo=False,origin_hash='',copy_from=None):
    if not name.strip() or not owner.strip():raise ValidationError('Nombre y responsable del ciclo son obligatorios')
    start,end=_valid_dates(start,end)
    key=uid()
    c.execute('''INSERT INTO p8_cycles(id,nombre,inicio,fin,responsable,fuente,es_demo,estado,creado_en,hash_origen)
                 VALUES(?,?,?,?,?,?,?,?,?,?)''',(key,name.strip(),start,end,owner.strip(),source,int(demo),'Borrador',now(),origin_hash))
    old={}
    if copy_from:
        if not c.execute('SELECT 1 FROM p8_cycles WHERE id=?',(copy_from,)).fetchone():raise ValidationError('Ciclo de origen no existe')
        old={r['servicio_ref']:r for r in c.execute('SELECT * FROM p8_ratings WHERE ciclo_id=?',(copy_from,))}
    for service in CATALOG:
        prev=old.get(service['id'])
        # Reevaluar siempre con evidencia del ciclo nuevo; nunca heredar una calificación como verificada.
        reminder=(f"Referencia del ciclo anterior: actual {prev['actual']}/5; meta {prev['deseado']}/5. Validar nuevamente." if prev and prev['estado']=='Evaluado' else '')
        vals=('Pendiente',None,None,reminder,'')
        c.execute('''INSERT INTO p8_ratings(ciclo_id,servicio_ref,estado,actual,deseado,observacion,evidencia)
                 VALUES(?,?,?,?,?,?,?)''',(key,service['id'],*vals))
    return key

def create_cycle(name,start,end,owner='Equipo PMO',source='Registro manual',demo=False,copy_from=None,path=None):
    with transaction(path) as c:return _create(c,name,start,end,owner,source,demo,copy_from=copy_from)

def save_rating(key,ref,status,current=None,desired=None,observation='',evidence='',actor='',path=None):
    if status not in STATUS:raise ValidationError('Estado de evaluación no válido')
    ref=int(ref)
    if ref not in CAT:raise ValidationError('Servicio de referencia inexistente')
    cval=_score(current) if status=='Evaluado' else None
    dval=_score(desired) if status=='Evaluado' else None
    if status=='Evaluado' and (cval is None or dval is None):raise ValidationError('El servicio evaluado requiere niveles actual y deseado')
    if status=='Evaluado' and not actor.strip():raise ValidationError('Identifica al evaluador de la madurez')
    with transaction(path) as c:
        cy=c.execute('SELECT estado FROM p8_cycles WHERE id=?',(key,)).fetchone()
        if not cy or cy['estado']!='Borrador':raise ValidationError('El ciclo no está disponible para edición')
        c.execute('''UPDATE p8_ratings SET estado=?,actual=?,deseado=?,observacion=?,evidencia=?,
           revisado_por=?,revisado_en=? WHERE ciclo_id=? AND servicio_ref=?''',
           (status,cval,dval,observation,evidence,actor,now(),key,ref))

def _validate_import_records(records,strict_catalog=True):
    if not isinstance(records,list) or len(records)!=26:raise ValidationError('Se requieren 26 filas: una por cada servicio de referencia')
    seen=set();result=[]
    for n,x in enumerate(records,start=2):
        if not isinstance(x,dict):raise ValidationError(f'Fila {n} no es un registro válido')
        try:
            ident=int(x.get('id') or x.get('serviceId'))
        except (ValueError,TypeError):raise ValidationError(f'Fila {n}: ID inválido')
        if ident not in CAT or ident in seen:raise ValidationError(f'Fila {n}: servicio duplicado o inexistente ({ident})')
        seen.add(ident);master=CAT[ident]
        category=str(x.get('category') or '').strip()
        title=str(x.get('name') or x.get('serviceName') or '').strip()
        if strict_catalog and (category.casefold()!=master['category'].casefold() or title.casefold()!=master['name'].casefold()):
            raise ValidationError(f'Fila {n}: el ID {ident} no coincide con nombre y categoría del catálogo de 26 servicios')
        current=_score(x.get('current'))
        desired=_score(x.get('desired'))
        if (current is None)!=(desired is None):raise ValidationError(f'Fila {n}: diligencia ambos niveles o deja ambos vacíos')
        result.append({'id':ident,'status':'Evaluado' if current is not None else 'No ofrecido','current':current,'desired':desired})
    return sorted(result,key=lambda a:a['id'])

def parse_xlsx(data):
    """Lee tanto la plantilla PMO-GA original como la plantilla bilingüe de CENS."""
    if len(data)>7_000_000:raise ValidationError('El archivo Excel supera 7 MB')
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException
    try:wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    except (InvalidFileException,ValueError,OSError,KeyError) as exc:raise ValidationError(f'Excel inválido: {exc}')
    try:
        expected_en=['Service ID','Service Name','Category','Current Maturity (1-5)','Desired Maturity (1-5)']
        expected_es=['ID del servicio','Nombre del servicio','Categoría','Madurez actual (1-5)','Madurez deseada (1-5)']
        if 'Maturity Assessment' in wb.sheetnames:
            sheet='Maturity Assessment';spanish=False
        elif 'Evaluación CENS' in wb.sheetnames:
            sheet='Evaluación CENS';spanish=True
        elif 'Compatible PMOGA' in wb.sheetnames:
            sheet='Compatible PMOGA';spanish=False
        else:raise ValidationError('No se encuentra una hoja de evaluación compatible con CENS / PMO-GA')
        w=wb[sheet]
        header=[str(c.value or '').strip() for c in next(w.iter_rows(min_row=1,max_row=1,max_col=5))]
        if header!=(expected_es if spanish else expected_en):
            raise ValidationError('El encabezado Excel no corresponde a la plantilla de CENS o PMO-GA')
        raw=[]
        for cells in w.iter_rows(min_row=2,max_col=5,values_only=True):
            if all(v is None or str(v).strip()=='' for v in cells):continue
            ident,name,category,current,desired=cells
            if spanish:
                try:code=int(ident)
                except (ValueError,TypeError):raise ValidationError('La hoja en español contiene un ID inválido')
                if code not in CAT or str(name).strip()!=CAT[code]['name_es'] or str(category).strip()!=CATEGORIES_ES[CAT[code]['category']]:
                    raise ValidationError(f'El servicio o su categoría no coincide con el catálogo CENS: {code}')
                name=CAT[code]['name'];category=CAT[code]['category']
            raw.append({'id':ident,'name':name,'category':category,'current':current,'desired':desired})
        return _validate_import_records(raw)
    finally:wb.close()

def _fill_cycle(c,key,prepared,actor):
    for x in prepared:
        c.execute('''UPDATE p8_ratings SET estado=?,actual=?,deseado=?,revisado_por=?,revisado_en=?
             WHERE ciclo_id=? AND servicio_ref=?''',
             (x['status'],x['current'],x['desired'],actor if x['status']=='Evaluado' else '',now(),key,x['id']))

def _log(c,key,source,raw,details):
    digest=hashlib.sha256(raw).hexdigest()
    c.execute('INSERT INTO p8_imports(ciclo_id,fuente,firma,registrado_en,detalles) VALUES(?,?,?,?,?)',
              (key,source,digest,now(),json.dumps(details,ensure_ascii=False)))
    return digest

def import_excel(data,name,start,end,owner,demo=False,path=None):
    prepared=parse_xlsx(data)
    if not any(r['status']=='Evaluado' for r in prepared):raise ValidationError('El archivo no tiene ningún servicio evaluado')
    with transaction(path) as c:
        digest=hashlib.sha256(data).hexdigest()
        key=_create(c,name,start,end,owner,'Plantilla Excel · PMO GA',demo,digest)
        _fill_cycle(c,key,prepared,owner)
        _log(c,key,'Excel PMO-GA',data,{'evaluados':sum(x['status']=='Evaluado' for x in prepared),'no_ofrecidos':sum(x['status']=='No ofrecido' for x in prepared)})
    return key

def parse_results_json(obj):
    if not isinstance(obj,dict) or not isinstance(obj.get('serviceResults'),list):raise ValidationError('JSON de resultados incompatible con PMO Service Maturity App')
    results=obj['serviceResults']
    if len(results)>26:raise ValidationError('JSON contiene demasiados servicios')
    mapped={}
    for r in results:
        try:ref=int(r['serviceId'])
        except (ValueError,TypeError,KeyError):raise ValidationError('Un resultado JSON no tiene ID de servicio válido')
        if ref not in CAT or ref in mapped:raise ValidationError('Servicio duplicado o ajeno al catálogo en JSON')
        if r.get('serviceName')!=CAT[ref]['name'] or r.get('category')!=CAT[ref]['category']:
            raise ValidationError(f'Catálogo incompatible para servicio {ref}')
        mapped[ref]=(r.get('currentMaturity'),r.get('desiredMaturity'))
    prepared=[{'id':v['id'],'name':v['name'],'category':v['category'],
            'current':mapped[v['id']][0] if v['id'] in mapped else None,
            'desired':mapped[v['id']][1] if v['id'] in mapped else None} for v in CATALOG]
    parsed=_validate_import_records(prepared)
    proposed=obj.get('summary',{})
    calc=compute_summary(parsed)
    if proposed:
        count=proposed.get('totalServicesAssessed')
        if count is not None and count!=calc['assessed']:raise ValidationError('El JSON presenta un número de servicios evaluados inconsistente')
        for orig,local in [('overallCurrentPercentage','current'),('overallDesiredPercentage','desired'),('overallGapPercentage','gap')]:
            if proposed.get(orig) is not None and (calc[local] is None or abs(float(proposed[orig])-calc[local])>.06):
                raise ValidationError(f'El resultado JSON no coincide con el cálculo de referencia: {orig}')
    return parsed

def import_results_json(obj,owner='Equipo PMO',demo=False,path=None):
    prepared=parse_results_json(obj)
    if not prepared or not any(r['status']=='Evaluado' for r in prepared):raise ValidationError('No hay calificaciones válidas')
    cy=obj.get('cycle') or {}
    a=str(cy.get('startDate') or '')[:10];b=str(cy.get('endDate') or '')[:10]
    a,b=_valid_dates(a,b)
    raw=json.dumps(obj,sort_keys=True,ensure_ascii=False).encode('utf-8')
    with transaction(path) as c:
        dig=hashlib.sha256(raw).hexdigest()
        key=_create(c,'Evaluación importada PMO-GA '+a,a,b,owner,'Resultados JSON PMO-GA',demo,dig)
        _fill_cycle(c,key,prepared,owner)
        _log(c,key,'Resultado JSON PMO-GA',raw,{'evaluados':sum(x['status']=='Evaluado' for x in prepared)})
    return key

def compute_summary(prepared):
    """Promedio macro de categorías NO ponderado = resultado PMO-GA recibido.
    Global micro = suma de puntuaciones / (número de servicios x 5).
    En ausencia de servicios no se muestra 0% ficticio.
    """
    categories=[];rated=[]
    for category in CATEGORIES:
        sub=[x for x in prepared if x.get('status',x.get('estado'))=='Evaluado'
             and CAT[x.get('id',x.get('servicio_ref'))]['category']==category]
        n=len(sub);rated.extend(sub)
        current=sum(x.get('current',x.get('actual')) for x in sub) / (n*5)*100 if n else None
        desired=sum(x.get('desired',x.get('deseado')) for x in sub) / (n*5)*100 if n else None
        categories.append({'category':category,'name':CATEGORIES_ES[category],'count':n,'total':sum(1 for x in CATALOG if x['category']==category),
                           'current':current,'desired':desired,'gap':(desired-current) if n else None})
    available=[x for x in categories if x['count']]
    macro_current=sum(x['current'] for x in available)/len(available) if available else None
    macro_desired=sum(x['desired'] for x in available)/len(available) if available else None
    n=len(rated)
    micro_current=(sum(x.get('current',x.get('actual')) for x in rated)/(5*n)*100) if n else None
    micro_desired=(sum(x.get('desired',x.get('deseado')) for x in rated)/(5*n)*100) if n else None
    return {'assessed':n,'not_offered':sum(x.get('status',x.get('estado'))=='No ofrecido' for x in prepared),
            'pending':sum(x.get('status',x.get('estado'))=='Pendiente' for x in prepared),
            'current':macro_current,'desired':macro_desired,'gap':macro_desired-macro_current if n else None,
            'weighted_current':micro_current,'weighted_desired':micro_desired,
            'weighted_gap':micro_desired-micro_current if n else None,'categories':categories}

def report(key,path=None):
    cy=cycle(key,path)
    if not cy:raise ValidationError('Ciclo inexistente')
    scored=[]
    for x in ratings(key,path):
        m=CAT[x['servicio_ref']]
        scored.append({**x,'id':x['servicio_ref'],'name':m['name'],'name_es':m['name_es'],'category':m['category'],
                       'gap':(x['deseado']-x['actual'])*20 if x['estado']=='Evaluado' else None})
    return {'cycle':cy,'ratings':scored,'summary':compute_summary(scored),'actions':actions(key,path),'links':links(key,path)}

def close_cycle(key,path=None):
    r=report(key,path)
    if r['summary']['assessed']==0 or r['summary']['pending']>0:
        raise ValidationError('Para cerrar el ciclo clasifica los 26 servicios como Evaluados o No ofrecidos; debe existir al menos uno evaluado')
    with transaction(path) as c:
        if r['cycle']['estado']!='Borrador':raise ValidationError('El ciclo ya fue cerrado')
        c.execute('UPDATE p8_cycles SET estado=?,cerrado_en=? WHERE id=?',('Cerrado',now(),key))

def gap_band(gap):
    if gap is None:return 'Sin evaluar'
    if gap>=30:return 'Crítica'
    if gap>=15:return 'Alerta'
    if gap<0:return 'Meta reducida'
    return 'Moderada'

def ranked(key,path=None):
    rr=report(key,path)['ratings'];return sorted([x for x in rr if x['estado']=='Evaluado'],key=lambda x:(-x['gap'],x['servicio_ref']))

def save_action(cycle_id,ref,title,owner,due,description='',impact='Medio',status='Pendiente',evidence='',indicator='',key=None,path=None):
    if ref not in CAT:raise ValidationError('Servicio de referencia no válido')
    if not title.strip() or not owner.strip():raise ValidationError('Título y responsable son obligatorios')
    if impact not in ('Bajo','Medio','Alto') or status not in STATES:raise ValidationError('Estado o impacto no válido')
    try:date.fromisoformat(str(due))
    except (TypeError,ValueError):raise ValidationError('Fecha meta inválida')
    with transaction(path) as c:
        cy=c.execute('SELECT id FROM p8_cycles WHERE id=?',(cycle_id,)).fetchone()
        if not cy:raise ValidationError('Ciclo inexistente')
        if not c.execute("SELECT 1 FROM p8_ratings WHERE ciclo_id=? AND servicio_ref=? AND estado='Evaluado'",(cycle_id,ref)).fetchone():
            raise ValidationError('La acción requiere un servicio evaluado')
        if key:
            if not c.execute('SELECT 1 FROM p8_actions WHERE id=? AND ciclo_id=?',(key,cycle_id)).fetchone():raise ValidationError('Acción inexistente')
            c.execute('''UPDATE p8_actions SET titulo=?,descripcion=?,responsable=?,fecha_meta=?,impacto=?,estado=?,
                     evidencia=?,indicador=?,actualizado_en=? WHERE id=?''',
                     (title.strip(),description,owner.strip(),str(due),impact,status,evidence,indicator,now(),key))
        else:
            key=uid();c.execute('''INSERT INTO p8_actions(id,ciclo_id,servicio_ref,titulo,descripcion,responsable,fecha_meta,
                 impacto,estado,evidencia,indicador,creado_en,actualizado_en) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                 (key,cycle_id,ref,title.strip(),description,owner.strip(),str(due),impact,status,evidence,indicator,now(),now()))
    return key

def delete_action(key,path=None):
    with transaction(path) as c:c.execute('DELETE FROM p8_actions WHERE id=?',(key,))

def link_service(cycle_id,ref,service_id,path=None):
    if ref not in CAT:raise ValidationError('Servicio de referencia inexistente')
    from . import step4
    if not step4.service(service_id,path):raise ValidationError('No existe el servicio corporativo en el catálogo del Paso 4')
    with transaction(path) as c:
        if not c.execute('SELECT 1 FROM p8_cycles WHERE id=?',(cycle_id,)).fetchone():raise ValidationError('Ciclo inexistente')
        c.execute('INSERT OR IGNORE INTO p8_service_links(ciclo_id,servicio_ref,servicio_cens,creado_en) VALUES(?,?,?,?)',
                  (cycle_id,ref,service_id,now()))

def unlink_service(cycle_id,ref,service_id,path=None):
    with transaction(path) as c:c.execute('DELETE FROM p8_service_links WHERE ciclo_id=? AND servicio_ref=? AND servicio_cens=?',(cycle_id,ref,service_id))

def import_step7(obj,path=None,source='Expediente Paso 7'):
    if not isinstance(obj,dict) or obj.get('schema')!='PMO-FLYWHEEL-CENS-paso8-input-v1' or not isinstance(obj.get('findings'),list):
        raise ValidationError('Se requiere el expediente de hallazgos Paso 7 para Paso 8')
    prepared=[];seen=set()
    for x in obj['findings']:
        if not isinstance(x,dict):raise ValidationError('Un hallazgo no es un registro')
        key=(str(x.get('ticket_id') or '').strip(),str(x.get('tipo') or '').strip(),source)
        if not all(key) or key in seen:raise ValidationError('Hallazgo sin identificador o duplicado')
        seen.add(key)
        prepared.append((key[0],key[1],str(x.get('servicio_id') or ''),str(x.get('descripcion') or ''),
             str(x.get('accion') or ''),str(x.get('responsable') or ''),str(x.get('estado') or ''),str(x.get('fecha') or ''),
             source,now(),json.dumps(x,ensure_ascii=False,default=str)))
    raw=json.dumps(obj,sort_keys=True,ensure_ascii=False).encode('utf-8')
    with transaction(path) as c:
        for item in prepared:
            c.execute('''INSERT INTO p8_findings(ticket_id,tipo,servicio_origen,descripcion,accion,responsable,estado,fecha,fuente,importado_en,payload_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id,tipo,fuente) DO UPDATE SET
            servicio_origen=excluded.servicio_origen,descripcion=excluded.descripcion,accion=excluded.accion,
            responsable=excluded.responsable,estado=excluded.estado,fecha=excluded.fecha,importado_en=excluded.importado_en,
            payload_json=excluded.payload_json''',item)
        _log(c,None,source,raw,{'hallazgos':len(prepared)})
    return len(prepared)

def import_step7_direct(path=None):
    from . import step7
    return import_step7(step7.step8_export(step7.ticket_list(path=path),path=path),path=path,source='Paso 7 · SQLite compartida')

def export_json(key,path=None):
    r=report(key,path)
    return {'schema':'PMO-FLYWHEEL-CENS-paso8-maturity-v1','exportedAt':now(),**r,
            'note':'El método macro conserva igual peso por categoría; la media micro pondera servicios. No son calificaciones oficiales PMOGA.'}

def export_csv(key,path=None):
    f=io.StringIO();writer=csv.writer(f,delimiter=';')
    writer.writerow(['ID','Nombre técnico PMO-GA','Servicio CENS','Categoría','Estado','Actual','Deseado','Brecha pts%','Evidencia'])
    for x in report(key,path)['ratings']:
        writer.writerow([x['id'],x['name'],x['name_es'],CATEGORIES_ES[x['category']],x['estado'],x['actual'],x['deseado'],x['gap'],x['evidencia']])
    return ('\ufeff'+f.getvalue()).encode('utf-8')

def export_xlsx(key,path=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment,Font,PatternFill
    r=report(key,path);wb=Workbook();ws=wb.active;ws.title='Evaluación 26 servicios'
    ws.append(['ID','Nombre técnico PMO-GA','Servicio CENS','Categoría','Estado','Actual','Deseado','Brecha (%)','Evidencia','Responsable'])
    for x in r['ratings']:
        ws.append([x['id'],x['name'],x['name_es'],CATEGORIES_ES[x['category']],x['estado'],x['actual'],x['deseado'],x['gap'],x['evidencia'],x['revisado_por']])
    sh=wb.create_sheet('Resumen');sh.append(['Indicador','Valor']);z=r['summary']
    for a,b in [('Servicios evaluados',z['assessed']),('Servicios no ofrecidos',z['not_offered']),('Pendientes',z['pending']),
      ('Madurez actual macro (%)',z['current']),('Meta macro (%)',z['desired']),('Brecha macro (%)',z['gap']),
      ('Madurez actual ponderada (%)',z['weighted_current']),('Meta ponderada (%)',z['weighted_desired'])]:sh.append([a,b])
    for c in z['categories']:sh.append([c['name']+' actual (%)',c['current']]);sh.append([c['name']+' meta (%)',c['desired']])
    ar=wb.create_sheet('Acciones');ar.append(['Servicio ref','Título','Responsable','Vencimiento','Impacto','Estado','Indicador','Evidencia'])
    for x in r['actions']:ar.append([x['servicio_ref'],x['titulo'],x['responsable'],x['fecha_meta'],x['impacto'],x['estado'],x['indicador'],x['evidencia']])
    # V0.19: exportaciones documentales en español; las tres hojas anteriores se conservan.
    from . import step8_documented as documented
    revision=wb.create_sheet('Evaluaciones documentadas')
    revision.append(['ID servicio','Servicio de CENS','Estado','Madurez actual','Madurez deseada',
       'Estado de revisión','Validación vigente','Justificación actual','Evaluador','Fecha',
       'Justificación de la meta','Capacidades requeridas','Recursos','Horizonte',
       'Responsable de meta','Acciones previstas','Número de evidencias'])
    evidence=wb.create_sheet('Evidencias de madurez')
    evidence.append(['ID servicio','Servicio de CENS','Nivel','Tipo','Descripción',
        'Referencia documental','Nombre de archivo','Responsable','Fecha','Ciclo'])
    levels=wb.create_sheet('Criterios 130 niveles')
    levels.append(['ID servicio','Servicio de CENS','Categoría','Nivel','Nombre del nivel','Criterio metodológico en español'])
    for item in CATALOG:
        for level in item['levels_es']:
            levels.append([item['id'],item['name_es'],CATEGORIES_ES[item['category']],
             level['level'],level['title'],level['description']])
        rev=documented.review(key,item['id'],path)
        evs=documented.evidences(key,item['id'],path)
        original=next(x for x in r['ratings'] if x['servicio_ref']==item['id'])
        revision.append([item['id'],item['name_es'],original['estado'],original['actual'],
           original['deseado'],rev['estado'],'Sí' if rev['vigente'] else 'No',
           rev['justificacion'],rev['evaluador'],rev['fecha'],rev['meta_justificacion'],
           rev['capacidades'],rev['recursos'],rev['horizonte'],rev['responsable_meta'],
           rev['acciones'],len(evs)])
        for ev in evs:
            evidence.append([item['id'],item['name_es'],ev['nivel'],ev['tipo'],ev['descripcion'],
               ev['referencia'],ev['archivo_nombre'],ev['responsable'],ev['fecha'],key])
    # V0.39.25 · Anexos operativos, sin modificar la lectura de ciclos ni la fórmula de madurez.
    from . import step8_improvement as improvement
    improvement.initialize(path)
    enhanced=improvement.initiatives(key,path)
    if enhanced:
        a=wb.create_sheet('Mejoras y seguimiento')
        a.append(['Código','Servicio','Acción','Fase documental','Estado legado','Prioridad',
          'Responsable','Fecha meta','Causa','Objetivo','Aceptación','Soportes','Hitos','Verificaciones'])
        h=wb.create_sheet('Hitos de mejora')
        h.append(['Código iniciativa','Hito','Responsable','Fecha objetivo','Estado','Evidencia'])
        ev=wb.create_sheet('Soportes de mejora')
        ev.append(['Código iniciativa','Tipo','Descripción','Referencia','Fecha','Responsable'])
        v=wb.create_sheet('Verificación de mejora')
        v.append(['Código iniciativa','Resultado','Valor observado','Observaciones','Soporte ID','Verificador','Fecha'])
        for item in enhanced:
            detail=improvement.detail(item['id'],path)['detalle'] or {}
            code=detail.get('codigo_publico') or 'Histórica sin estructurar'
            a.append([code,CAT[item['servicio_ref']]['name_es'],item['titulo'],
                detail.get('fase','Sin ficha'),item['estado'],detail.get('prioridad',''),
                item['responsable'],item['fecha_meta'],detail.get('causa_raiz',''),
                detail.get('objetivo',''),detail.get('criterio_aceptacion',''),
                item['soportes'],item['hitos'],item['verificaciones']])
            for m in improvement.milestones(item['id'],path):
                h.append([code,m['titulo'],m['responsable'],m['fecha_meta'],m['estado'],m['evidencia']])
            for d in improvement.supports(item['id'],path):
                ev.append([code,d['tipo'],d['descripcion'],d['referencia'],d['fecha'],d['registrado_por']])
            for d in improvement.verifications(item['id'],path):
                v.append([code,d['resultado'],d['valor_observado'],d['observaciones'],
                    d['evidencia_id'],d['verificador'],d['fecha']])
    for ws in wb:
        for cell in ws[1]:cell.fill=PatternFill('solid',fgColor='10374B');cell.font=Font(bold=True,color='FFFFFF');cell.alignment=Alignment(wrap_text=True)
        ws.freeze_panes='A2'
        for col in ws.columns:
            letter=col[0].column_letter
            ws.column_dimensions[letter].width=min(42,max(14,max(len(str(c.value or '')) for c in list(col)[:70])+3))
    buf=io.BytesIO();wb.save(buf);return buf.getvalue()

def pdf_report(key,path=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    r=report(key,path);s=r['summary'];b=io.BytesIO()
    doc=SimpleDocTemplate(b,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=42,bottomMargin=40)
    styles=getSampleStyleSheet();styles['Title'].textColor=colors.HexColor('#10374B')
    story=[Paragraph('PMO FLYWHEEL CENS | Paso 8',styles['Title']),Paragraph('Evaluación de madurez y mejora de servicios',styles['Heading2']),
           Paragraph(f"Ciclo: {r['cycle']['nombre']} · {r['cycle']['inicio']} a {r['cycle']['fin']}",styles['Normal']),Spacer(1,14),
           Paragraph('Madurez actual (promedio por categorías): '+(f"{s['current']:.2f}%" if s['current'] is not None else 'Sin datos'),styles['Heading3']),
           Paragraph('Madurez deseada (promedio por categorías): '+(f"{s['desired']:.2f}%" if s['desired'] is not None else 'Sin datos'),styles['Heading3']),
           Paragraph(f"Servicios evaluados: {s['assessed']} | No ofrecidos: {s['not_offered']} | Pendientes: {s['pending']}",styles['Normal']),Spacer(1,12)]
    arr=[['Categoría','Servicios','Actual','Deseado','Brecha']]+[[q['name'],str(q['count']),f"{q['current']:.1f}%" if q['current'] is not None else '—',f"{q['desired']:.1f}%" if q['desired'] is not None else '—',f"{q['gap']:.1f} pp" if q['gap'] is not None else '—'] for q in s['categories']]
    t=Table(arr,colWidths=[130,70,85,85,85]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#10374B')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#DBE4EA')),('BOTTOMPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),9)]));story.extend([t,Spacer(1,15)])
    story.append(Paragraph('Brechas priorizadas',styles['Heading3']))
    for x in ranked(key,path)[:10]:story.append(Paragraph(f"{x['id']:02d}. {x['name_es']} — brecha {x['gap']:.0f} pp (actual {x['actual']}/5 · meta {x['deseado']}/5)",styles['Normal']))
    story.extend([Spacer(1,12),Paragraph('Acciones de mejora',styles['Heading3'])])
    if not r['actions']:story.append(Paragraph('Aún no se registran acciones de mejora.',styles['Normal']))
    for a in r['actions']:
        story.append(Paragraph(f"{a['titulo']} — {a['responsable']} — {a['fecha_meta']} — {a['estado']}",styles['Normal']))
    from . import step8_documented as documented
    from xml.sax.saxutils import escape as escape_pdf
    story.extend([Spacer(1,12),Paragraph('Revisión documental de madurez',styles['Heading3'])])
    total_evidences=0
    for service in CATALOG:
        rev=documented.review(key,service['id'],path)
        evs=documented.evidences(key,service['id'],path)
        total_evidences+=len(evs)
        if rev['justificacion'] or evs:
            detail=f"{service['id']:02d}. {service['name_es']}: "
            detail+=('Validado' if rev['vigente'] else 'Pendiente de validación')
            detail+=f" · {len(evs)} evidencia(s)"
            story.append(Paragraph(escape_pdf(detail),styles['Normal']))
            if rev['justificacion']:
                story.append(Paragraph(escape_pdf(rev['justificacion'][:350]),styles['Normal']))
    if not total_evidences:
        story.append(Paragraph('No hay evidencias registradas en este ciclo.',styles['Normal']))
    story.extend([Spacer(1,14),Paragraph('Nota: el resultado no es una certificación PMOGA. Se trata de una autoevaluación de servicios que requiere respaldo documental. La madurez del Paso 8 es diferente de la calificación de clientes del Paso 6.',styles['Normal'])])
    doc.build(story);return b.getvalue()

def backup(path=None):
    names=('p8_cycles','p8_ratings','p8_actions','p8_service_links','p8_findings','p8_imports')
    return {'schema':'PMO-FLYWHEEL-CENS-paso8-backup-v1','tables':{t:rows('SELECT * FROM '+t,path=path) for t in names}}

def restore(obj,confirmed=False,path=None):
    names=('p8_cycles','p8_ratings','p8_actions','p8_service_links','p8_findings','p8_imports')
    if not confirmed:raise ValidationError('Confirma la restauración de los datos del Paso 8')
    if not isinstance(obj,dict) or obj.get('schema')!='PMO-FLYWHEEL-CENS-paso8-backup-v1' or set(obj.get('tables',{}))!=set(names):
        raise ValidationError('Archivo de respaldo incompatible')
    with transaction(path) as c:
        for t in reversed(names):c.execute('DELETE FROM '+t)
        for t in names:
            col={r[1] for r in c.execute(f'PRAGMA table_info({t})')}
            for x in obj['tables'][t]:
                if not isinstance(x,dict) or not set(x).issubset(col):raise ValidationError('Columnas no válidas en respaldo')
                if x:
                    keys=list(x);c.execute('INSERT INTO '+t+' ('+','.join(keys)+') VALUES ('+','.join('?'*len(keys))+')',[x[k] for k in keys])
    return True

# V0.18: captura masiva, completamente transaccional y compatible con el editor individual.
def save_ratings_batch(cycle_id,entries,actor,path=None):
    """Actualiza los 26 estados en un solo commit, manteniendo evidencias previas."""
    if not str(actor).strip():raise ValidationError('Indica el evaluador responsable de la matriz')
    if not isinstance(entries,list) or len(entries)!=26:raise ValidationError('La matriz debe tener exactamente los 26 servicios')
    prepared=[];seen=set()
    for x in entries:
        try:ident=int(x['id'])
        except (KeyError,TypeError,ValueError):raise ValidationError('Identificador de servicio inválido')
        if ident in seen or ident not in CAT:raise ValidationError('Identificador de servicio duplicado o inexistente')
        seen.add(ident)
        status=str(x.get('estado') or '').strip()
        if status not in STATUS:raise ValidationError(f'Servicio {ident}: estado inválido')
        current=_score(x.get('actual'));desired=_score(x.get('deseado'))
        if status=='Evaluado':
            if current is None or desired is None:raise ValidationError(f'Servicio {ident}: Evaluado requiere niveles actual y deseado')
        elif current is not None or desired is not None:
            raise ValidationError(f'Servicio {ident}: si está {status}, deja ambos niveles vacíos')
        prepared.append((status,current,desired,actor.strip(),now(),cycle_id,ident))
    with transaction(path) as c:
        cy=c.execute('SELECT estado FROM p8_cycles WHERE id=?',(cycle_id,)).fetchone()
        if not cy or cy['estado']!='Borrador':raise ValidationError('El ciclo no permite modificaciones')
        for vals in prepared:
            c.execute('''UPDATE p8_ratings SET estado=?,actual=?,deseado=?,revisado_por=?,revisado_en=?
                         WHERE ciclo_id=? AND servicio_ref=?''',vals)
    return len(prepared)
