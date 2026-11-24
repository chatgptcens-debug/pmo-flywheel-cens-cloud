"""Paso 9: Entrega de valor — SQLite aditivo, medición y verificación explícitas.

Transfiere compromisos de Paso 3 sin cambiar sus registros; Paso 6/7 solo aportan
contexto. No convierte ANS, volumen de tickets ni notas de satisfacción en beneficios.
Reglas de impacto y clasificación conservadas del prototipo HTML suministrado.
"""
from __future__ import annotations
import csv, hashlib, io, json, math, uuid
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from .storage import connect, transaction

MODULES=('Matriz de beneficios y compromisos','Medición de impacto','Realización de beneficios','Tablero ejecutivo de valor','Autoevaluación metodológica PMI')
DIMENSIONS=(
 ('Marco integral de medición del valor',(
 '¿Definimos resultados específicos y medibles para cada servicio de la PMO?',
 '¿Recopilamos datos consistentes y fiables para evaluar el impacto de los servicios?',
 '¿Nuestros informes de valor son claros y adaptados a los distintos clientes?',
 '¿Revisamos periódicamente los indicadores de valor y su alineación organizacional?',
 '¿Existe una periodicidad definida para recopilar datos y reportar valor entregado?')),
 ('Análisis de impacto cuantitativo',(
 '¿Analizamos sistemáticamente datos cuantitativos sobre la contribución de la PMO?',
 '¿Cuantificamos impactos financieros con fuentes y supuestos verificables?',
 '¿Realizamos análisis de tendencias del valor generado por los servicios?',
 '¿Los informes incluyen visualizaciones claras de los resultados?',
 '¿Documentamos los métodos y supuestos usados para calcular el valor?')),
 ('Realización de beneficios para los clientes',(
 '¿Revisamos los beneficios comprometidos para cada grupo de clientes?',
 '¿Seguimos los beneficios a lo largo del tiempo mediante indicadores?',
 '¿Comparamos la línea base con mediciones posteriores a las intervenciones?',
 '¿Documentamos casos representativos de alto valor entregado?',
 '¿Reportamos periódicamente los beneficios logrados por la PMO?')),
 ('Síntesis y comunicación del valor',(
 '¿Integramos evidencias cuantitativas y cualitativas del valor generado?',
 '¿Explicamos claramente la contribución de los servicios a los objetivos organizacionales?',
 '¿Adaptamos los informes a la dirección, líderes de proyectos y otros clientes?',
 '¿Utilizamos visualizaciones para comunicar resultados complejos?',
 '¿Reportamos conforme a los ciclos organizacionales de decisión?')),
 ('Perfeccionamiento y reajuste',(
 '¿Analizamos las diferencias entre beneficios prometidos y resultados reales?',
 '¿Investigamos las causas de incumplimientos significativos de valor?',
 '¿Definimos acciones para ajustar propuestas, servicios o procesos cuando se requiere?',
 '¿Perfeccionamos los indicadores y los métodos de medición con base en evidencias?',
 '¿Gestionamos y comunicamos formalmente los cambios derivados de las mejoras?')),
)
QUESTIONS=tuple(q for _,qs in DIMENSIONS for q in qs)
IMPACTS=('Eficiencia','Calidad','Financiero','Estratégico','Otro','Económico / financiero','Eficiencia operativa / tiempo','Mitigación de riesgos','Calidad del dato / gobernanza','Satisfacción directa')
DIRECTIONS=('Disminuir','Aumentar')
FORMULA_TYPES=('Porcentaje / tasa','Tiempo promedio','Conteo absoluto','Índice / puntaje','Monto monetario','Otro')
MEASUREMENT_FREQUENCIES=('Por evento','Semanal','Mensual','Trimestral','Semestral','Anual')
CAPTURE_METHODS=('Manual','Carga Excel verificada','Fuente de datos integrada','Mixto')
SCHEMA='''
CREATE TABLE IF NOT EXISTS p9_beneficios(
 id TEXT PRIMARY KEY,origen_p3 TEXT NOT NULL DEFAULT '',origen_version TEXT NOT NULL DEFAULT '',
 origen_archivo TEXT NOT NULL DEFAULT '',servicio_id TEXT NOT NULL DEFAULT '',servicio TEXT NOT NULL,
 cliente_id TEXT NOT NULL DEFAULT '',cliente TEXT NOT NULL,dependencia TEXT NOT NULL DEFAULT '',
 necesidad TEXT NOT NULL,entregable TEXT NOT NULL DEFAULT '',beneficio TEXT NOT NULL,
 indicador TEXT NOT NULL,unidad TEXT NOT NULL DEFAULT '',sentido TEXT NOT NULL CHECK(sentido IN ('Disminuir','Aumentar')),
 linea_base REAL,meta REAL,fuente TEXT NOT NULL DEFAULT '',responsable TEXT NOT NULL DEFAULT '',
 fecha_meta TEXT NOT NULL DEFAULT '',tipo_impacto TEXT NOT NULL,observaciones TEXT NOT NULL DEFAULT '',
 monto_bruto REAL,atribucion REAL NOT NULL DEFAULT 100 CHECK(atribucion BETWEEN 0 AND 100),
 clave_economica TEXT NOT NULL DEFAULT '',fuente_economica TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK(estado IN ('Pendiente','En medición','Validado')),
 validador TEXT NOT NULL DEFAULT '',fecha_validacion TEXT NOT NULL DEFAULT '',evidencia_validacion TEXT NOT NULL DEFAULT '',
 medicion_validada_id TEXT,es_demo INTEGER NOT NULL DEFAULT 0,creado_en TEXT NOT NULL,actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_p9_origen_p3 ON p9_beneficios(origen_p3) WHERE origen_p3<>'';
CREATE TABLE IF NOT EXISTS p9_mediciones(
 id TEXT PRIMARY KEY,beneficio_id TEXT NOT NULL REFERENCES p9_beneficios(id) ON DELETE CASCADE,
 fecha TEXT NOT NULL,valor REAL NOT NULL,fuente TEXT NOT NULL,responsable TEXT NOT NULL,
 evidencia TEXT NOT NULL DEFAULT '',observacion TEXT NOT NULL DEFAULT '',creado_en TEXT NOT NULL,
 UNIQUE(beneficio_id,fecha,fuente,valor)
);
CREATE INDEX IF NOT EXISTS idx_p9_mediciones_beneficio ON p9_mediciones(beneficio_id,fecha);
CREATE TABLE IF NOT EXISTS p9_casos(
 id TEXT PRIMARY KEY,beneficio_id TEXT REFERENCES p9_beneficios(id),titulo TEXT NOT NULL,
 resumen TEXT NOT NULL,fecha TEXT NOT NULL,responsable TEXT NOT NULL,fuente TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS p9_contexto(
 tipo TEXT NOT NULL CHECK(tipo IN ('ticket','hallazgo')),id_origen TEXT NOT NULL,
 payload_json TEXT NOT NULL,fuente TEXT NOT NULL,registrado_en TEXT NOT NULL,
 PRIMARY KEY(tipo,id_origen)
);
CREATE TABLE IF NOT EXISTS p9_importaciones(
 id TEXT PRIMARY KEY,fuente TEXT NOT NULL,hash_sha256 TEXT NOT NULL,
 agregados INTEGER NOT NULL,omitidos INTEGER NOT NULL,fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p9_informe(
 id INTEGER PRIMARY KEY CHECK(id=1),responsable TEXT NOT NULL DEFAULT '',
 fecha_desde TEXT NOT NULL DEFAULT '',fecha_hasta TEXT NOT NULL DEFAULT '',
 observaciones TEXT NOT NULL DEFAULT '',actualizado_en TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS p9_evaluaciones(
 id TEXT PRIMARY KEY,version INTEGER NOT NULL UNIQUE,responsable TEXT NOT NULL,
 estado TEXT NOT NULL CHECK(estado IN ('Borrador','Archivada')),
 puntaje INTEGER,clasificacion TEXT,creado_en TEXT NOT NULL,archivado_en TEXT
);
CREATE TABLE IF NOT EXISTS p9_respuestas(
 evaluacion_id TEXT NOT NULL REFERENCES p9_evaluaciones(id) ON DELETE CASCADE,
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 25),valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '',evidencia TEXT NOT NULL DEFAULT '',actualizado_en TEXT NOT NULL,
 PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS p9_indicadores_beneficio(
 beneficio_id TEXT PRIMARY KEY REFERENCES p9_beneficios(id) ON DELETE CASCADE,
 codigo TEXT NOT NULL UNIQUE,objetivo TEXT NOT NULL DEFAULT '',tipo_formula TEXT NOT NULL,
 expresion TEXT NOT NULL DEFAULT '',frecuencia TEXT NOT NULL,
 metodo_captura TEXT NOT NULL,estado TEXT NOT NULL CHECK(estado IN ('Borrador','Definido')),
 creado_en TEXT NOT NULL,actualizado_en TEXT NOT NULL
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
        c.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES(16)')
        c.commit()

def _number(v,label='valor',optional=True):
    if v is None or (isinstance(v,str) and not v.strip()):
        if optional:return None
        raise ValidationError(f'{label} es obligatorio')
    try:
        if isinstance(v,str):
            v=v.strip().replace(' ','')
            if ',' in v:v=v.replace('.','').replace(',','.')
        a=float(v)
        if not math.isfinite(a):raise ValueError()
        return a
    except (ValueError,TypeError):raise ValidationError(f'{label}: número no válido')

def _date(v,label='Fecha',optional=True):
    if not v and optional:return ''
    try:return date.fromisoformat(str(v)[:10]).isoformat()
    except (ValueError,TypeError):raise ValidationError(f'{label} no es válida')

def _text(x):return str(x if x is not None else '').strip()

def _clean(data):
    keys=('origen_p3','origen_version','origen_archivo','servicio_id','servicio','cliente_id',
      'cliente','dependencia','necesidad','entregable','beneficio','indicador','unidad','fuente',
      'responsable','observaciones','clave_economica','fuente_economica')
    d={k:_text(data.get(k)) for k in keys}
    for field in ('servicio','cliente','necesidad','beneficio'):
        if not d[field]:raise ValidationError(f'Falta {field}')
    d['sentido']=_text(data.get('sentido') or 'Disminuir')
    if d['sentido'] not in DIRECTIONS:raise ValidationError('Sentido: elija Aumentar o Disminuir')
    d['tipo_impacto']=_text(data.get('tipo_impacto') or 'Eficiencia')
    if d['tipo_impacto'] not in IMPACTS:raise ValidationError('Tipo de impacto no reconocido')
    d['fecha_meta']=_date(data.get('fecha_meta'),'Fecha meta')
    d['linea_base']=_number(data.get('linea_base'),'Línea base')
    d['meta']=_number(data.get('meta'),'Meta')
    if d['linea_base'] is not None and d['meta'] is not None:
        if d['linea_base']==d['meta']:raise ValidationError('La meta debe diferir de la línea base')
        if d['sentido']=='Disminuir' and d['meta']>d['linea_base']:raise ValidationError('Meta incompatible con el sentido Disminuir')
        if d['sentido']=='Aumentar' and d['meta']<d['linea_base']:raise ValidationError('Meta incompatible con el sentido Aumentar')
    d['monto_bruto']=_number(data.get('monto_bruto'),'Valor económico')
    if d['monto_bruto'] is not None and d['monto_bruto']<0:raise ValidationError('El monto económico no puede ser negativo')
    d['atribucion']=_number(data.get('atribucion',0),'Atribución')
    if d['atribucion'] is None:d['atribucion']=0.0
    if not 0<=d['atribucion']<=100:raise ValidationError('Atribución fuera de 0–100%')
    d['es_demo']=int(bool(data.get('es_demo')))
    return d

def benefits(path=None):return rows('SELECT * FROM p9_beneficios ORDER BY creado_en DESC,id',path=path)
def benefit(key,path=None):return row('SELECT * FROM p9_beneficios WHERE id=?',(key,),path)

def approved_services(path=None):
    """Servicios aprobados del Paso 04; no equivale a autorización operativa."""
    try:
        return rows("SELECT id,codigo,nombre,estado FROM p4_services WHERE estado='Aprobado' ORDER BY codigo",path=path)
    except __import__('sqlite3').OperationalError:
        return []

def benefit_indicator(benefit_id,path=None):
    return row('SELECT * FROM p9_indicadores_beneficio WHERE beneficio_id=?',(benefit_id,),path)

def indicators(path=None):
    return rows('SELECT * FROM p9_indicadores_beneficio ORDER BY codigo',path=path)

def save_benefit_indicator(benefit_id,objective,formula_type,expression,frequency,method,
                           name,unit,direction,baseline,target,source,owner,status='Borrador',path=None):
    """Indicador principal del compromiso. No genera mediciones ni valida beneficios."""
    if formula_type not in FORMULA_TYPES or frequency not in MEASUREMENT_FREQUENCIES or method not in CAPTURE_METHODS:
        raise ValidationError('Catálogo de indicador no reconocido')
    if status not in ('Borrador','Definido'):raise ValidationError('Estado de indicador no reconocido')
    if not _text(name):raise ValidationError('Nombre del indicador obligatorio')
    if status=='Definido' and not all(_text(v) for v in (objective,expression,unit,source,owner)):
        raise ValidationError('Para definir indicador complete objetivo, fórmula, unidad, fuente y responsable')
    old=benefit(benefit_id,path)
    if not old:raise ValidationError('Beneficio inexistente')
    clean=_clean({**old,'indicador':name,'unidad':unit,'sentido':direction,
                  'linea_base':baseline,'meta':target,'fuente':source,'responsable':owner})
    with transaction(path) as c:
        old_catalog=c.execute('SELECT * FROM p9_indicadores_beneficio WHERE beneficio_id=?',(benefit_id,)).fetchone()
        changes=any(old[k]!=clean[k] for k in ('indicador','unidad','sentido','linea_base','meta','fuente'))
        catalog_changes=(not old_catalog and status=='Definido') or bool(old_catalog and (old_catalog['estado']!=status or any(old_catalog[k]!=v for k,v in {'objetivo':_text(objective),'tipo_formula':formula_type,'expresion':_text(expression),'frecuencia':frequency,'metodo_captura':method}.items())))
        c.execute('UPDATE p9_beneficios SET indicador=?,unidad=?,sentido=?,linea_base=?,meta=?,fuente=?,responsable=?,actualizado_en=? WHERE id=?',
                  (clean['indicador'],clean['unidad'],clean['sentido'],clean['linea_base'],clean['meta'],clean['fuente'],clean['responsable'],now(),benefit_id))
        if changes or catalog_changes:
            c.execute("UPDATE p9_beneficios SET estado='En medición',validador='',fecha_validacion='',evidencia_validacion='',medicion_validada_id=NULL WHERE id=?",(benefit_id,))
        if old_catalog:
            code=old_catalog['codigo']
            c.execute('UPDATE p9_indicadores_beneficio SET objetivo=?,tipo_formula=?,expresion=?,frecuencia=?,metodo_captura=?,estado=?,actualizado_en=? WHERE beneficio_id=?',
                      (_text(objective),formula_type,_text(expression),frequency,method,status,now(),benefit_id))
        else:
            seq=c.execute("SELECT COALESCE(MAX(CAST(SUBSTR(codigo,5) AS INTEGER)),0)+1 FROM p9_indicadores_beneficio WHERE codigo LIKE 'IBN-%'").fetchone()[0]
            code=f'IBN-{seq:04d}'
            c.execute('INSERT INTO p9_indicadores_beneficio(beneficio_id,codigo,objetivo,tipo_formula,expresion,frecuencia,metodo_captura,estado,creado_en,actualizado_en) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (benefit_id,code,_text(objective),formula_type,_text(expression),frequency,method,status,now(),now()))
    return code

def measurements(key,path=None):return rows('SELECT * FROM p9_mediciones WHERE beneficio_id=? ORDER BY fecha,creado_en,id',(key,),path)
def all_measurements(path=None):return rows('SELECT * FROM p9_mediciones ORDER BY fecha',path=path)
def cases(path=None):return rows('SELECT * FROM p9_casos ORDER BY fecha DESC',path=path)
def context(kind=None,path=None):
    if kind:return rows('SELECT * FROM p9_contexto WHERE tipo=? ORDER BY registrado_en DESC',(kind,),path)
    return rows('SELECT * FROM p9_contexto ORDER BY registrado_en DESC',path=path)

def save_benefit(data,key=None,path=None):
    d=_clean(data)
    cols=list(d)
    with transaction(path) as c:
        old=c.execute('SELECT * FROM p9_beneficios WHERE id=?',(key,)).fetchone() if key else None
        if key and not old:raise ValidationError('El beneficio no existe')
        if not key:key=uid()
        # Si cambia el compromiso se exige una nueva verificación. Nunca borrar sus mediciones.
        material=('servicio','cliente','necesidad','beneficio','indicador','unidad','sentido','linea_base','meta','fuente','monto_bruto','atribucion','clave_economica','fuente_economica')
        changed=bool(old and any(old[k]!=d[k] for k in material))
        if old:
            sql=', '.join(f'{k}=?' for k in cols)
            c.execute(f'UPDATE p9_beneficios SET {sql},actualizado_en=? WHERE id=?',(*[d[k] for k in cols],now(),key))
            if changed:c.execute("UPDATE p9_beneficios SET estado='En medición',validador='',fecha_validacion='',evidencia_validacion='',medicion_validada_id=NULL WHERE id=?",(key,))
        else:
            c.execute('INSERT INTO p9_beneficios(id,'+','.join(cols)+',creado_en,actualizado_en) VALUES('+','.join('?' for _ in range(len(cols)+3))+')',(key,*[d[k] for k in cols],now(),now()))
    return key

def delete_benefit(key,path=None):
    with transaction(path) as c:
        if not c.execute('DELETE FROM p9_beneficios WHERE id=?',(key,)).rowcount:raise ValidationError('Beneficio inexistente')

def add_measurement(key,value,when,source,owner,evidence='',observation='',path=None):
    v=_number(value,'Resultado observado',optional=False)
    day=_date(when,'Fecha de medición',optional=False)
    if not _text(source) or not _text(owner):raise ValidationError('Fuente y responsable de medición son obligatorios')
    with transaction(path) as c:
        if not c.execute('SELECT id FROM p9_beneficios WHERE id=?',(key,)).fetchone():raise ValidationError('Beneficio inexistente')
        mid=uid()
        try:c.execute('INSERT INTO p9_mediciones VALUES(?,?,?,?,?,?,?,?,?)',(mid,key,day,v,_text(source),_text(owner),_text(evidence),_text(observation),now()))
        except __import__('sqlite3').IntegrityError:raise ValidationError('Ya existe una medición idéntica para esa fecha y fuente')
        # Una nueva medición deja la validación previa como histórica, no vigente.
        c.execute("UPDATE p9_beneficios SET estado='En medición',validador='',fecha_validacion='',evidencia_validacion='',medicion_validada_id=NULL,actualizado_en=? WHERE id=?",(now(),key))
    return mid

def latest(key,path=None):
    return row('SELECT * FROM p9_mediciones WHERE beneficio_id=? ORDER BY fecha DESC,creado_en DESC,id DESC LIMIT 1',(key,),path)

def calc(b,m):
    if not m or b['linea_base'] is None or b['meta'] is None:return None
    base,target,actual=float(b['linea_base']),float(b['meta']),float(m['valor'])
    if target==base:return None
    advance=(actual-base)/(target-base)*100
    improvement=None if base==0 else ((base-actual) if b['sentido']=='Disminuir' else (actual-base))/abs(base)*100
    achieved=actual<=target if b['sentido']=='Disminuir' else actual>=target
    return {'avance':advance,'variacion_favorable':improvement,'cumple_meta':achieved,
            'actual':actual,'fecha':m['fecha'],'id_medicion':m['id'],'avance_visual':max(0,min(100,advance))}

def is_verified(b,m=None,cut=None,path=None):
    if not b or b['estado']!='Validado' or not all(b[k] for k in ('validador','fecha_validacion','evidencia_validacion','medicion_validada_id')):return False
    if cut and b['fecha_validacion']>cut:return False
    m=m or latest(b['id'],path)
    return bool(m and m['id']==b['medicion_validada_id'] and b['linea_base'] is not None and b['meta'] is not None and b['fuente'])

def verify(key,validator,when,evidence,path=None):
    b=benefit(key,path)
    if not b:raise ValidationError('Beneficio inexistente')
    m=latest(key,path)
    missing=[k for k in ('servicio','cliente','necesidad','beneficio','indicador','fuente') if not b[k]]
    if b['linea_base'] is None or b['meta'] is None:missing.append('línea base y meta')
    if missing or not m:raise ValidationError('Faltan datos de compromiso o medición: '+', '.join(missing or ['medición']))
    if not _text(validator) or not _text(evidence):raise ValidationError('Validador y evidencia formal son obligatorios')
    day=_date(when,'Fecha de validación',optional=False)
    if day<m['fecha']:raise ValidationError('La fecha de validación no puede preceder la medición')
    with transaction(path) as c:
        c.execute("UPDATE p9_beneficios SET estado='Validado',validador=?,fecha_validacion=?,evidencia_validacion=?,medicion_validada_id=?,actualizado_en=? WHERE id=?",(_text(validator),day,_text(evidence),m['id'],now(),key))

def invalidate(key,path=None):
    with transaction(path) as c:
        c.execute("UPDATE p9_beneficios SET estado='En medición',validador='',fecha_validacion='',evidencia_validacion='',medicion_validada_id=NULL,actualizado_en=? WHERE id=?",(now(),key))

def overview(path=None,cut=None):
    bs=[b for b in benefits(path) if not b['es_demo']];ms=all_measurements(path);by=defaultdict(list)
    for m in ms:
        if not cut or m['fecha']<=cut:by[m['beneficio_id']].append(m)
    measured=verified=comparable=achieved=0;financial={};duplicate=0;details=[];financial_details={}
    for b in bs:
        m=by[b['id']][-1] if by[b['id']] else None
        # No contar verificación como vigente para un corte anterior a la última medida validada.
        v=is_verified(b,m,cut= cut,path=path) if m else False
        p=calc(b,m)
        measured+=bool(m);comparable+=bool(p);verified+=v;achieved+=bool(v and p and p['cumple_meta'])
        if v and b['monto_bruto'] is not None and b['fuente_economica'] and b['atribucion']>0:
            key=b['clave_economica'] or b['id']
            if key in financial:
                duplicate+=1
                if financial_details[key]['servicio'] != b['servicio']:
                    financial_details[key]['servicio']='Clave compartida · asignación por servicio pendiente'
            else:
                financial[key]=b['monto_bruto']*b['atribucion']/100
                financial_details[key]={'servicio':b['servicio'],'concepto':key,'valor_atribuible':financial[key]}
        details.append({'beneficio':b,'medicion':m,'calculo':p,'verificado':v})
    return {'total':len(bs),'medidos':measured,'comparables':comparable,'verificados':verified,'metas_cumplidas':achieved,
       'cobertura':100*measured/len(bs) if bs else None,
       'cumplimiento':100*achieved/verified if verified else None,
       'valor_neto':sum(financial.values()),'valor_atribuible':sum(financial.values()),'detalle_economico':list(financial_details.values()),'conceptos_economicos':len(financial),'duplicados_excluidos':duplicate,'detalle':details}

def add_case(title,summary,when,owner,benefit_id=None,source='',path=None):
    if not _text(title) or not _text(summary) or not _text(owner):raise ValidationError('Título, resumen y responsable son obligatorios')
    with transaction(path) as c:
        if benefit_id and not c.execute('SELECT id FROM p9_beneficios WHERE id=?',(benefit_id,)).fetchone():raise ValidationError('Beneficio vinculado inexistente')
        key=uid();c.execute('INSERT INTO p9_casos VALUES(?,?,?,?,?,?,?)',(key,benefit_id,_text(title),_text(summary),_date(when,'Fecha',False),_text(owner),_text(source)))
    return key

def _legacy_record(x):
    """Mapeo explícito HTML Paso 9, expediente JSON Paso 3 y filas de SQLite Paso 3."""
    sid=_text(x.get('origen_p3') or x.get('originId') or x.get('id') or '')
    return {'origen_p3':sid,'servicio_id':x.get('servicio_id') or x.get('serviceId') or '',
       'servicio':x.get('servicio') or x.get('service') or x.get('nombre_servicio') or '',
       'cliente':x.get('cliente') or x.get('client') or x.get('dependencia') or '',
       'dependencia':x.get('dependencia') or '',
       'necesidad':x.get('necesidad') or x.get('need') or '',
       'entregable':x.get('entregable') or x.get('deliverable') or '',
       'beneficio':x.get('beneficio') or x.get('benefit') or '',
       'indicador':x.get('indicador') or x.get('metrica') or x.get('metric') or '',
       'unidad':x.get('unidad') or x.get('unit') or '',
       'linea_base':x.get('linea_base') or x.get('baseline') or None,
       'meta':x.get('meta') or x.get('target') or None,
       'sentido':x.get('sentido') or ('Aumentar' if x.get('direction')=='higher' else 'Disminuir'),
       'fuente':x.get('fuente') or x.get('source') or '',
       'tipo_impacto':x.get('tipo_impacto') or x.get('impactType') or 'Eficiencia',
       'responsable':x.get('responsable') or x.get('owner') or '',
       'origen_version':x.get('version_origen') or x.get('version') or '',
       'monto_bruto':x.get('monto_bruto') or x.get('financialAmount') or None,
       'atribucion':x.get('atribucion') if x.get('atribucion') is not None else x.get('attribution',100),
       'clave_economica':x.get('clave_economica') or x.get('financialKey') or '',
       'fuente_economica':x.get('fuente_economica') or x.get('financialSource') or ''}

def import_from_step3(path=None,include_demo=False):
    """Usa la misma SQLite: importa compromisos de p3_beneficios; no modifica Paso 3.
    Solo incorpora filas con beneficio e indicador definidos; informa omitidos.
    """
    source=rows('SELECT * FROM p3_beneficios ORDER BY creado_en,id',path=path)
    solutions=rows("SELECT * FROM p3_soluciones ORDER BY (estado='Aprobada') DESC,creado_en DESC",path=path)
    groups=defaultdict(list)
    for sol in solutions:
        if sol.get('necesidad_id'):groups[sol['necesidad_id']].append(sol)
        try:
            for need in json.loads(sol.get('necesidades_json') or '[]'):
                nid=need if isinstance(need,str) else need.get('id') if isinstance(need,dict) else None
                if nid:groups[nid].append(sol)
        except (ValueError,TypeError):pass
    prepared=[]
    for b in source:
        s=[v for v in groups.get(b['id'],[]) if v['estado']=='Aprobada']
        if not s:continue  # No transferir borradores ni soluciones sin aprobación
        approved=s[0]
        d=_legacy_record(b)
        d['servicio']=approved['nombre'];d['servicio_id']=approved['id']
        d['es_demo']=int(approved['codigo'].upper().startswith(('DEMO','PRACTICA')))
        prepared.append(d)
    result=import_records(prepared,source='SQLite Paso 3',path=path,include_demo=include_demo)
    result['sin_solucion_vinculada']=len(source)-len(prepared)
    return result

def import_records(records,source='Archivo',path=None,include_demo=False):
    if not isinstance(records,list):raise ValidationError('Se requiere una lista de beneficios')
    prepared=[];omitted=0;seen=set()
    for i,x in enumerate(records,1):
        if not isinstance(x,dict):raise ValidationError(f'Fila {i}: no es un registro')
        if bool(x.get('es_demo') or x.get('demo')) and not include_demo:omitted+=1;continue
        try:d=_clean(x)
        except ValidationError:
            # En Paso 3 hay borradores incompletos; se excluyen sin fabricar métricas.
            if source=='SQLite Paso 3':omitted+=1;continue
            raise
        origin=d['origen_p3']
        if origin and origin in seen:raise ValidationError(f'Identificador repetido en el origen: {origin}')
        if origin:seen.add(origin)
        prepared.append(d)
    with transaction(path) as c:
        imported=0
        for d in prepared:
            if d['origen_p3'] and c.execute('SELECT 1 FROM p9_beneficios WHERE origen_p3=?',(d['origen_p3'],)).fetchone():omitted+=1;continue
            if not d['origen_p3'] and c.execute('SELECT 1 FROM p9_beneficios WHERE servicio=? AND cliente=? AND necesidad=? AND beneficio=? AND indicador=?',(d['servicio'],d['cliente'],d['necesidad'],d['beneficio'],d['indicador'])).fetchone():omitted+=1;continue
            key=uid();cols=list(d)
            d['origen_archivo']=source
            cols=list(d)
            c.execute('INSERT INTO p9_beneficios(id,'+','.join(cols)+',creado_en,actualizado_en) VALUES('+','.join('?' for _ in range(len(cols)+3))+')',(key,*[d[k] for k in cols],now(),now()))
            imported+=1
        c.execute('INSERT INTO p9_importaciones VALUES(?,?,?,?,?,?)',(uid(),source,hashlib.sha256(json.dumps(prepared,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),imported,omitted,now()))
    return {'agregados':imported,'omitidos':omitted}

def import_json(payload,source='JSON',path=None,include_demo=False):
    if not isinstance(payload,dict):raise ValidationError('El JSON no es un objeto')
    schema=payload.get('schema','')
    if schema=='PMO-CENS-paso9-local-v1':
        state=payload.get('state',payload)
        data=state.get('benefits',[])
    elif schema=='pmo-cens-paso3-backup-v1':data=(payload.get('state') or {}).get('rows',[])
    elif schema in ('PMO-FLYWHEEL-CENS-paso9-input-v1','PMO-FLYWHEEL-CENS-paso9-backup-v1'):
        data=payload.get('benefits',[])
    else:data=payload.get('rows') or payload.get('benefits') or payload.get('proposals')
    if not isinstance(data,list):raise ValidationError('Expediente JSON sin lista de beneficios compatible')
    return import_records([_legacy_record(x) for x in data],source,path,include_demo)

def import_context_from_steps(path=None,include_demo=False):
    """Lee copias informativas de Paso 6 y hallazgos Paso 7; no los interpreta como beneficios."""
    tickets=rows('SELECT * FROM p6_tickets',path=path)
    finds=rows('SELECT * FROM p7_hallazgos',path=path)
    accepted=0;excluded=0
    with transaction(path) as c:
        for t in tickets:
            if t.get('demo') and not include_demo:excluded+=1;continue
            payload=json.dumps(t,ensure_ascii=False,default=str)
            c.execute('INSERT INTO p9_contexto(tipo,id_origen,payload_json,fuente,registrado_en) VALUES(?,?,?,?,?) ON CONFLICT(tipo,id_origen) DO UPDATE SET payload_json=excluded.payload_json,registrado_en=excluded.registrado_en',('ticket',t['id'],payload,'SQLite Paso 6',now()));accepted+=1
        for f in finds:
            t=next((x for x in tickets if x['id']==f['ticket_id']),None)
            if t and t.get('demo') and not include_demo:excluded+=1;continue
            key=f['ticket_id']+':'+f['tipo'];payload=json.dumps(f,ensure_ascii=False,default=str)
            c.execute('INSERT INTO p9_contexto(tipo,id_origen,payload_json,fuente,registrado_en) VALUES(?,?,?,?,?) ON CONFLICT(tipo,id_origen) DO UPDATE SET payload_json=excluded.payload_json,registrado_en=excluded.registrado_en',('hallazgo',key,payload,'SQLite Paso 7',now()));accepted+=1
    return {'contexto':accepted,'excluidos':excluded}

def import_context_json(payload,source='Expediente JSON',path=None,include_demo=False):
    tickets=payload.get('tickets',[]) if isinstance(payload,dict) else []
    findings=payload.get('findings',[]) if isinstance(payload,dict) else []
    # No crear beneficios a partir de la satisfacción o el ANS.
    accepted=0
    with transaction(path) as c:
        for kind,items in (('ticket',tickets),('hallazgo',findings)):
            if not isinstance(items,list):raise ValidationError('Estructura de contexto inválida')
            for x in items:
                if not isinstance(x,dict):raise ValidationError('Elemento de contexto inválido')
                if x.get('demo') and not include_demo:continue
                key=str(x.get('id') or x.get('ticket_id') or x.get('ticketId') or '').strip()
                if not key:raise ValidationError('Contexto sin identificador')
                if kind=='hallazgo':key+=':'+str(x.get('tipo') or x.get('kind') or 'general')
                c.execute('INSERT INTO p9_contexto VALUES(?,?,?,?,?) ON CONFLICT(tipo,id_origen) DO UPDATE SET payload_json=excluded.payload_json,registrado_en=excluded.registrado_en',(kind,key,json.dumps(x,ensure_ascii=False),source,now()));accepted+=1
    return accepted

def save_report(owner,from_date='',to_date='',notes='',path=None):
    a=_date(from_date,'Desde');b=_date(to_date,'Hasta')
    if a and b and a>b:raise ValidationError('Periodo de informe inválido')
    with transaction(path) as c:
        c.execute('INSERT INTO p9_informe VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET responsable=excluded.responsable,fecha_desde=excluded.fecha_desde,fecha_hasta=excluded.fecha_hasta,observaciones=excluded.observaciones,actualizado_en=excluded.actualizado_en',(_text(owner),a,b,_text(notes),now()))
def report_config(path=None):return row('SELECT * FROM p9_informe WHERE id=1',path=path) or {'responsable':'','fecha_desde':'','fecha_hasta':'','observaciones':''}

def classification(score):
    if not 25<=score<=125:raise ValidationError('Puntaje fuera de escala')
    if score>=113:return 'Excelente'
    if score>=98:return 'Bien'
    if score>=77:return 'Promedio'
    if score>=51:return 'Pobre'
    return 'Crítico'

def evaluations(path=None):return rows('SELECT * FROM p9_evaluaciones ORDER BY version DESC',path=path)
def answers(key,path=None):return rows('SELECT * FROM p9_respuestas WHERE evaluacion_id=? ORDER BY numero',(key,),path=path)
def create_evaluation(owner,path=None):
    if not _text(owner):raise ValidationError('Indica el responsable de la autoevaluación')
    with transaction(path) as c:
        version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM p9_evaluaciones').fetchone()[0]
        key=uid();c.execute('INSERT INTO p9_evaluaciones VALUES(?,?,?,?,?,?,?,?)',(key,version,_text(owner),'Borrador',None,None,now(),None))
    return key

def save_answer(key,num,score,observation='',evidence='',path=None):
    if num not in range(1,26):raise ValidationError('Pregunta fuera del cuestionario')
    if score is not None and (type(score) is not int or score not in range(1,6)):raise ValidationError('Respuesta debe ser entero de 1 a 5')
    with transaction(path) as c:
        rec=c.execute('SELECT estado FROM p9_evaluaciones WHERE id=?',(key,)).fetchone()
        if not rec or rec['estado']!='Borrador':raise ValidationError('La evaluación está archivada o no existe')
        if score is None:c.execute('DELETE FROM p9_respuestas WHERE evaluacion_id=? AND numero=?',(key,num))
        else:c.execute('INSERT INTO p9_respuestas VALUES(?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia,actualizado_en=excluded.actualizado_en',(key,num,score,_text(observation),_text(evidence),now()))

def assessment(key,path=None):
    v=row('SELECT * FROM p9_evaluaciones WHERE id=?',(key,),path)
    if not v:raise ValidationError('Evaluación inexistente')
    a={r['numero']:r for r in answers(key,path)};n=len(a)
    totals=[sum(a[i]['valor'] for i in range(d*5+1,d*5+6)) if all(i in a for i in range(d*5+1,d*5+6)) else None for d in range(5)]
    score=sum(x['valor'] for x in a.values()) if n==25 else None
    return {'evaluacion':v,'respondidas':n,'puntaje':score,'clasificacion':classification(score) if score is not None else None,'dimensiones':totals,'respuestas':a}

def archive_evaluation(key,path=None):
    d=assessment(key,path)
    if d['evaluacion']['estado']!='Borrador':raise ValidationError('Esta evaluación ya está archivada')
    if d['puntaje'] is None:raise ValidationError('Se requieren las 25 respuestas completas para archivar')
    with transaction(path) as c:c.execute("UPDATE p9_evaluaciones SET estado='Archivada',puntaje=?,clasificacion=?,archivado_en=? WHERE id=?",(d['puntaje'],d['clasificacion'],now(),key))
    return d

def export_step10(path=None):
    summary=overview(path);v=[{'id':x['beneficio']['id'],'origen_p3':x['beneficio']['origen_p3'],'servicio_id':x['beneficio']['servicio_id'],
             'servicio':x['beneficio']['servicio'],'cliente':x['beneficio']['cliente'],'necesidad':x['beneficio']['necesidad'],
             'beneficio':x['beneficio']['beneficio'],'indicador':x['beneficio']['indicador'],
             'linea_base':x['beneficio']['linea_base'],'meta':x['beneficio']['meta'],
             'resultado':x['calculo'],'evidencia':x['beneficio']['evidencia_validacion'],
             'validador':x['beneficio']['validador'],'fecha_validacion':x['beneficio']['fecha_validacion']}
           for x in summary['detalle'] if x['verificado']]
    return {'schema':'PMO-FLYWHEEL-CENS-paso10-input-v1','version':'0.20','generado_en':now(),
      'benefits':v,'summary':{k:summary[k] for k in ('total','medidos','verificados','metas_cumplidas','valor_neto','conceptos_economicos')},
      'cases':cases(path),'context':context(path=path),'assessments':[x for x in evaluations(path) if x['estado']=='Archivada']}

def backup(path=None):
    return {'schema':'PMO-FLYWHEEL-CENS-paso9-backup-v1','exportedAt':now(),
      'benefits':benefits(path),'measurements':all_measurements(path),'cases':cases(path),'context':context(path=path),
      'evaluations':evaluations(path),'answers':rows('SELECT * FROM p9_respuestas',path=path),'indicators':indicators(path),'report':report_config(path)}

def export_csv(path=None):
    data=overview(path)['detalle'];out=io.StringIO();w=csv.writer(out,delimiter=';')
    w.writerow(['Código','Servicio','Cliente','Necesidad','Beneficio','Indicador','Línea base','Meta','Última medición','Variación favorable (%)','Avance a meta (%)','Validado','Evidencia'])
    for x in data:
        b=x['beneficio'];m=x['medicion'];p=x['calculo']
        w.writerow([b['id'],b['servicio'],b['cliente'],b['necesidad'],b['beneficio'],b['indicador'],b['linea_base'],b['meta'],m['valor'] if m else '',p['variacion_favorable'] if p else '',p['avance'] if p else '', 'Sí' if x['verificado'] else 'No',b['evidencia_validacion']])
    return ('\ufeff'+out.getvalue()).encode('utf-8')

def restore_backup(payload,confirm=False,path=None):
    """Restaura exclusivamente tablas Paso 9 en transacción; no afecta Pasos 1–8."""
    if not confirm:raise ValidationError('Confirma la restauración del Paso 9')
    if not isinstance(payload,dict) or payload.get('schema')!='PMO-FLYWHEEL-CENS-paso9-backup-v1':raise ValidationError('No es un respaldo del Paso 9')
    for k in ('benefits','measurements','cases','context','evaluations','answers'):
        if not isinstance(payload.get(k),list):raise ValidationError(f'El respaldo no contiene {k}')
    if 'indicators' in payload and not isinstance(payload['indicators'],list):raise ValidationError('Catálogo de indicadores inválido')
    if 'indicators' not in payload and indicators(path):raise ValidationError('El respaldo antiguo carece de indicadores actuales. Descarga un respaldo integral antes de restaurar.')
    with transaction(path) as c:
        for tbl in ('p9_indicadores_beneficio','p9_respuestas','p9_evaluaciones','p9_casos','p9_mediciones','p9_contexto','p9_beneficios','p9_informe'):
            c.execute('DELETE FROM '+tbl)
        tables={'benefits':'p9_beneficios','measurements':'p9_mediciones','cases':'p9_casos','context':'p9_contexto','evaluations':'p9_evaluaciones','answers':'p9_respuestas','indicators':'p9_indicadores_beneficio'}
        for source,target in tables.items():
            if source=='indicators' and 'indicators' not in payload:continue
            cols=[x['name'] for x in c.execute(f'PRAGMA table_info({target})')]
            for record in payload[source]:
                if not isinstance(record,dict):raise ValidationError(f'Registro inválido en {source}')
                present=[k for k in cols if k in record]
                if not present:raise ValidationError(f'Campos desconocidos en {source}')
                c.execute('INSERT INTO '+target+'('+','.join(present)+') VALUES('+','.join('?' for _ in present)+')',tuple(record[k] for k in present))
        config=payload.get('report') or {}
        if config and isinstance(config,dict):
            c.execute('INSERT INTO p9_informe(id,responsable,fecha_desde,fecha_hasta,observaciones,actualizado_en) VALUES(1,?,?,?,?,?)',tuple(config.get(x,'') for x in ('responsable','fecha_desde','fecha_hasta','observaciones','actualizado_en')))
    return len(payload['benefits'])

def export_xlsx(path=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    out=io.BytesIO();wb=Workbook();wb.remove(wb.active)
    definitions=[('Beneficios',benefits(path)),('Mediciones',all_measurements(path)),('Casos de valor',cases(path)),('Contexto',context(path=path)),('Evaluaciones',evaluations(path)),('Indicadores de beneficio',indicators(path))]
    for name,data in definitions:
        ws=wb.create_sheet(name)
        if data:
            cols=list(data[0]);ws.append(cols)
            for rec in data:ws.append([rec.get(x) for x in cols])
            ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
            for cel in ws[1]:cel.font=Font(color='FFFFFF',bold=True);cel.fill=PatternFill('solid',fgColor='10374B')
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width=min(42,max(14,max(len(str(c.value or '')) for c in col[:min(100,len(col))])+2))
        else:ws['A1']='Sin registros'
    wb.save(out);return out.getvalue()

def template_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill
    wb=Workbook();ws=wb.active;ws.title='Beneficios'
    cols=['Servicio PMO','Cliente / dependencia','Necesidad original','Entregable','Beneficio comprometido','Indicador','Unidad','Sentido (Aumentar/Disminuir)','Línea base','Meta','Fuente','Dimensión','Responsable']
    ws.append(cols)
    for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='10374B')
    for key in 'ABCDEFGHIJKLM':ws.column_dimensions[key].width=29
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    buf=io.BytesIO();wb.save(buf);return buf.getvalue()

def parse_excel(raw,filename='entrada.xlsx'):
    import pandas as pd
    if filename.lower().endswith('.csv'):
        text=raw.decode('utf-8-sig');sep=';' if text.splitlines()[0].count(';')>text.splitlines()[0].count(',') else ','
        data=pd.read_csv(io.StringIO(text),sep=sep,dtype=str).fillna('')
    else:data=pd.read_excel(io.BytesIO(raw),dtype=str).fillna('')
    import unicodedata
    def normalize(s):return ''.join(x for x in unicodedata.normalize('NFKD',str(s).lower()) if x.isalnum() and not unicodedata.combining(x))
    look={normalize(x):x for x in data.columns}
    alias={
     'servicio':['servicio pmo','servicio','service'],
     'cliente':['cliente / dependencia','cliente','client'],
     'necesidad':['necesidad original','necesidad','need'],
     'entregable':['entregable','output'],
     'beneficio':['beneficio comprometido','beneficio','benefit'],
     'indicador':['indicador','metrica','métrica de beneficio','metric'],
     'unidad':['unidad','unit'],
     'sentido':['sentido (aumentar/disminuir)','sentido','direction'],
     'linea_base':['línea base','linea_base','baseline'],
     'meta':['meta','target'],
     'fuente':['fuente','source'],
     'tipo_impacto':['dimensión','dimension','impacttype'],
     'responsable':['responsable','owner'],
    }
    chosen={k:next((look[normalize(a)] for a in als if normalize(a) in look),None) for k,als in alias.items()}
    for field in ('servicio','cliente','necesidad','beneficio','indicador'):
        if not chosen[field]:raise ValidationError(f'Falta columna obligatoria: {field}')
    result=[]
    for i,(_,r) in enumerate(data.iterrows(),2):
        d={k:str(r[v]).strip() if v else '' for k,v in chosen.items()}
        if not any(d.values()):continue
        if d['sentido'].lower() in ('lower','disminución','disminuir'):d['sentido']='Disminuir'
        elif d['sentido'].lower() in ('higher','aumento','aumentar'):d['sentido']='Aumentar'
        d['linea_base']=d['linea_base'] or None;d['meta']=d['meta'] or None
        try:_clean(d)
        except ValidationError as e:raise ValidationError(f'Fila {i}: {e}')
        result.append(d)
    if not result:raise ValidationError('No hay beneficios en la plantilla')
    return result
