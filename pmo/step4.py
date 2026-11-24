"""Paso 4 · Desarrollo de servicios. Módulo independiente, SQLite aditiva.

Los datos de Pasos 1–3 son de solo lectura; la importación de Paso 3 no
recalcula priorización V5 ni autoriza servicios. Las 35 preguntas se basan en
paráfrasis funcionales del instrumento (no reproducción literal PMI).
"""
from __future__ import annotations
import csv
import io
import json
import uuid
import hashlib
from contextlib import closing
from datetime import datetime, timezone, date
from pathlib import Path
from .storage import connect, transaction
from .step4_catalogos_ficha import EXTRA_FIELDS, LIST_EXTRA_FIELDS, NATURALEZAS, DOMINIOS
from .step4_ans import enforce_snapshot_integrity

MODULES=('Catálogo y fichas de servicios','Métricas de servicios','Recursos y competencias','Evaluación metodológica PMI')
METRIC_TYPES=('Eficiencia','Salida','Resultado')
STATUSES=('Borrador','En diseño','En validación','Validado','Aprobado','Suspendido')
ACTIVATIONS=('Solicitud del cliente','Por evento','Por regla','Proactivo de la PMO')
DELIVERY_MODELS=('Consultivo','De apoyo','Facilitador','Directivo','Híbrido','Control','Gestión Tecnológica')
SKILLS=('Dirección de proyectos','Gestión de portafolios','Análisis de datos','Gestión de riesgos',
        'Gobernanza','Metodologías ágiles','Facilitación y comunicación','Gestión del cambio',
        'Herramientas digitales','Gestión de beneficios')
DIMENSIONS=(
('Enfoque de prestación',(
'Se comparan opciones de prestación según la necesidad, madurez y cultura de cada cliente.',
'La modalidad de prestación define responsabilidades, roles e interacción entre PMO y clientes.',
'Los clientes participan en la validación y ajuste del enfoque de prestación.',
'Se anticipa cómo debe evolucionar el enfoque a medida que cambien las capacidades.',
'Los modelos de prestación se revisan para mantener su utilidad y efectividad.')),
('Diseño y adaptación de procesos',(
'Cada servicio cuenta con un proceso de principio a fin que muestra decisiones y traspasos.',
'Se prevén variantes para distintos tipos, tamaños y complejidades de proyectos.',
'Los riesgos que afectan la prestación se identifican y cuentan con acciones de tratamiento.',
'Existen orientaciones para adaptar procesos a las particularidades de los clientes.',
'Los procesos disponen de diagramas, responsabilidades RACI e instrucciones documentadas.')),
('Catálogo de servicios',(
'El catálogo identifica los servicios disponibles y describe sus principales características.',
'Los servicios están segmentados o adaptados según las necesidades de los clientes.',
'Los clientes conocen cómo solicitar, utilizar y acceder a cada servicio.',
'El catálogo se actualiza ante cambios de necesidades, mejoras o nuevas ofertas.',
'La oferta de servicios se comunica activamente a los grupos de clientes relevantes.')),
('Objetivos e indicadores',(
'Para cada servicio se han definido métricas de eficiencia, entregables y resultados.',
'Los indicadores cuentan con fórmula, fuente, frecuencia y responsable definidos.',
'Las metas se establecen con participación de los clientes y usando líneas base.',
'Los tableros presentan métricas y metas apropiadas para cada cliente.',
'La PMO revisa los indicadores con los clientes y ajusta metas según la evidencia.')),
('Recursos y competencias',(
'Se identifican las competencias técnicas y relacionales requeridas por cada servicio.',
'Las habilidades actuales del equipo se comparan con las competencias requeridas.',
'Los roles especifican responsabilidades, aptitudes y expectativas de desempeño.',
'Las asignaciones se actualizan al cambiar la demanda o disponibilidad del equipo.',
'Existe un plan para cerrar brechas de habilidades y fortalecer la capacidad futura.')),
('ANS y validación de clientes',(
'Cada servicio cuenta con ANS que establecen alcance, plazos, calidad y desempeño.',
'Las metas de los ANS corresponden a recursos reales y expectativas alcanzables.',
'Los compromisos se adaptan, cuando corresponda, a distintos tipos de clientes.',
'Los clientes revisan y validan los ANS antes de su formalización.',
'Se prevé el monitoreo y la revisión periódica del cumplimiento de los ANS.')),
('Planificación de implementación',(
'Existen hojas de ruta con hitos, dependencias y tiempos de desarrollo del servicio.',
'Los planes de implementación identifican recursos, presupuesto y riesgos.',
'El traspaso de incorporación a operación tiene requisitos y responsables definidos.',
'Se consideran pilotos y despliegues graduales para servicios complejos o críticos.',
'Existe gobernanza para supervisar implementación, incorporación y operación.')),
)
QUESTIONS=tuple(q for _, qs in DIMENSIONS for q in qs)
DETAIL_FIELDS=('caracteristicas','tecnologia','alcance','exclusiones','solicitud','plazos','recursos',
'indicadores','retroalimentacion','formacion','entregables','activaciones','activacion_detalle',
'proceso','raci','variantes','riesgos','sla_respuesta','sla_entrega','sla_calidad','sla_aceptacion',
'sla_escalamiento','sla_seguimiento','validacion_cliente','validacion_fecha','validacion_evidencia',
'plan','hitos','presupuesto','piloto','transicion',*EXTRA_FIELDS)

SCHEMA='''
CREATE TABLE IF NOT EXISTS p4_services(
 id TEXT PRIMARY KEY, codigo TEXT NOT NULL UNIQUE COLLATE NOCASE,
 nombre TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
 propuesta_valor TEXT NOT NULL DEFAULT '', cliente TEXT NOT NULL DEFAULT '',
 responsable TEXT NOT NULL DEFAULT '', modelo TEXT NOT NULL DEFAULT 'Consultivo',
 estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','En diseño','En validación','Validado','Aprobado','Suspendido')),
 necesidad TEXT NOT NULL DEFAULT '', beneficio TEXT NOT NULL DEFAULT '',
 source_step3_id TEXT NOT NULL DEFAULT '', source_step3_code TEXT NOT NULL DEFAULT '',
 source_step3_version TEXT NOT NULL DEFAULT '', source_step3_json TEXT NOT NULL DEFAULT '{}',
 detalles_json TEXT NOT NULL DEFAULT '{}', creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS p4_source_step3_unique ON p4_services(source_step3_id) WHERE source_step3_id<>'';
CREATE TABLE IF NOT EXISTS p4_metrics(
 id TEXT PRIMARY KEY, servicio_id TEXT NOT NULL REFERENCES p4_services(id) ON DELETE CASCADE,
 nombre TEXT NOT NULL, tipo TEXT NOT NULL CHECK(tipo IN ('Eficiencia','Salida','Resultado')),
 formula TEXT NOT NULL DEFAULT '', unidad TEXT NOT NULL DEFAULT '',
 linea_base TEXT NOT NULL DEFAULT '', meta TEXT NOT NULL DEFAULT '', real TEXT NOT NULL DEFAULT '',
 sentido TEXT NOT NULL DEFAULT 'mayor' CHECK(sentido IN ('mayor','menor')),
 frecuencia TEXT NOT NULL DEFAULT 'Mensual', responsable TEXT NOT NULL DEFAULT '',
 fuente TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 fecha_medicion TEXT NOT NULL DEFAULT '', actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p4_team(
 id TEXT PRIMARY KEY, nombre TEXT NOT NULL, rol TEXT NOT NULL,
 capacidad INTEGER NOT NULL DEFAULT 100 CHECK(capacidad BETWEEN 0 AND 100),
 habilidades_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS p4_team_profiles(
 integrante_id TEXT PRIMARY KEY REFERENCES p4_team(id) ON DELETE CASCADE,
 dependencia TEXT NOT NULL DEFAULT '', equipo TEXT NOT NULL DEFAULT '', correo TEXT NOT NULL DEFAULT '',
 dedicacion_referente TEXT NOT NULL DEFAULT '', formacion TEXT NOT NULL DEFAULT '',
 experiencia TEXT NOT NULL DEFAULT '', certificaciones TEXT NOT NULL DEFAULT '',
 especialidades TEXT NOT NULL DEFAULT '', evidencia_competencias TEXT NOT NULL DEFAULT '',
 disponibilidad TEXT NOT NULL DEFAULT '', observaciones TEXT NOT NULL DEFAULT '',
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p4_requirements(
 servicio_id TEXT NOT NULL REFERENCES p4_services(id) ON DELETE CASCADE,
 competencia TEXT NOT NULL, nivel INTEGER NOT NULL CHECK(nivel BETWEEN 1 AND 5),
 PRIMARY KEY(servicio_id,competencia)
);
CREATE TABLE IF NOT EXISTS p4_allocations(
 id TEXT PRIMARY KEY, integrante_id TEXT NOT NULL REFERENCES p4_team(id) ON DELETE CASCADE,
 servicio_id TEXT NOT NULL REFERENCES p4_services(id) ON DELETE CASCADE,
 porcentaje INTEGER NOT NULL CHECK(porcentaje BETWEEN 0 AND 100),
 UNIQUE(integrante_id,servicio_id)
);
CREATE TABLE IF NOT EXISTS p4_training(
 id TEXT PRIMARY KEY, integrante_id TEXT NOT NULL REFERENCES p4_team(id),
 competencia TEXT NOT NULL, accion TEXT NOT NULL, meta_fecha TEXT NOT NULL DEFAULT '',
 estado TEXT NOT NULL DEFAULT 'Pendiente', responsable TEXT NOT NULL DEFAULT '',
 evidencia TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS p4_evaluations(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE, responsable TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','Finalizada')),
 puntaje INTEGER, clasificacion TEXT,
 creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finalizado_en TEXT
);
CREATE TABLE IF NOT EXISTS p4_answers(
 evaluacion_id TEXT NOT NULL REFERENCES p4_evaluations(id),
 numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 35),
 valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),
 observacion TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',
 responsable TEXT NOT NULL DEFAULT '', fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS p4_audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, entidad TEXT NOT NULL, objeto_id TEXT NOT NULL,
 accion TEXT NOT NULL, actor TEXT NOT NULL, detalle TEXT NOT NULL DEFAULT '{}',
 fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
'''
class ValidationError(ValueError):pass

def _id():return str(uuid.uuid4())
def _json(data):return json.dumps(data,ensure_ascii=False,sort_keys=True,default=str)
def _req(v,field):
    s=str(v or '').strip()
    if not s:raise ValidationError(f'Se requiere {field}.')
    return s

def _rows(sql,args=(),path=None):
    with closing(connect(path)) as con:return [dict(r) for r in con.execute(sql,args).fetchall()]
def _row(sql,args=(),path=None):
    with closing(connect(path)) as con:
        r=con.execute(sql,args).fetchone();return dict(r) if r else None

def _audit(con,entity,key,action,actor,detail=None):
    con.execute('INSERT INTO p4_audit(entidad,objeto_id,accion,actor,detalle) VALUES(?,?,?,?,?)',
                (entity,key,action,actor or 'Equipo PMO',_json(detail or {})))

def initialize(path=None):
    with closing(connect(path)) as con:
        con.executescript(SCHEMA)
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (8)')
        con.commit()
    from .step4_metrics import initialize as initialize_metric_definitions
    initialize_metric_definitions(path)

def services(path=None):return _rows('SELECT * FROM p4_services ORDER BY codigo',path=path)
def service(key,path=None):return _row('SELECT * FROM p4_services WHERE id=?',(key,),path)
def details(item):
    d=json.loads(item.get('detalles_json') or '{}') if item else {}
    return {k:(d.get(k) if isinstance(d.get(k),list) else []) if k in ('activaciones',*LIST_EXTRA_FIELDS) else d.get(k,'') for k in DETAIL_FIELDS}
def next_code(path=None):
    codes={x['codigo'] for x in services(path)}
    i=1
    while f'CENS-SRV-{i:03d}' in codes:i+=1
    return f'CENS-SRV-{i:03d}'

def save_service(data,actor='Equipo PMO',key=None,path=None):
    name=_req(data.get('nombre'),'nombre del servicio');code=_req(data.get('codigo'),'código')
    state=data.get('estado') or 'Borrador'
    if state not in STATUSES:raise ValidationError('Estado de servicio inválido.')
    d={k:data.get(k,'') for k in ('descripcion','propuesta_valor','cliente','responsable','modelo','necesidad','beneficio')}
    d={k:str(v or '').strip() for k,v in d.items()}
    d['modelo']=d['modelo'] or 'Consultivo'
    d['details']=data.get('detalles',{})
    if not isinstance(d['details'],dict):raise ValidationError('Ficha del servicio inválida.')
    d['details']={k:d['details'].get(k,[] if k in ('activaciones',*LIST_EXTRA_FIELDS) else '') for k in DETAIL_FIELDS}
    d['details']=enforce_snapshot_integrity(d['details'])
    if not isinstance(d['details']['activaciones'],list) or any(x not in ACTIVATIONS for x in d['details']['activaciones']):
        raise ValidationError('Modo de activación inválido.')
    for field in LIST_EXTRA_FIELDS:
        if d['details'][field] is None or d['details'][field]=='':
            d['details'][field]=[]
        if not isinstance(d['details'][field],list):raise ValidationError(f'Campo de selección múltiple inválido: {field}.')
    if d['details']['naturaleza'] and d['details']['naturaleza'] not in NATURALEZAS:
        raise ValidationError('Naturaleza del servicio inválida.')
    if any(x not in DOMINIOS for x in d['details']['dominios']):
        raise ValidationError('Dominio del servicio inválido.')
    with transaction(path) as con:
        if key:
            old=con.execute('SELECT * FROM p4_services WHERE id=?',(key,)).fetchone()
            if not old:raise ValidationError('Servicio inexistente.')
            # Los campos de origen son inmutables al editar la ficha.
            con.execute('''UPDATE p4_services SET codigo=?,nombre=?,descripcion=?,propuesta_valor=?,cliente=?,
              responsable=?,modelo=?,estado=?,necesidad=?,beneficio=?,detalles_json=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?''',
              (code,name,d['descripcion'],d['propuesta_valor'],d['cliente'],d['responsable'],d['modelo'],state,
               d['necesidad'],d['beneficio'],_json(d['details']),key))
        else:
            key=_id()
            con.execute('''INSERT INTO p4_services(id,codigo,nombre,descripcion,propuesta_valor,cliente,responsable,modelo,estado,
               necesidad,beneficio,detalles_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
               (key,code,name,d['descripcion'],d['propuesta_valor'],d['cliente'],d['responsable'],d['modelo'],state,
                d['necesidad'],d['beneficio'],_json(d['details'])))
        _audit(con,'servicio',key,'actualizar' if data.get('id') or data.get('key') else 'guardar',actor)
    return key

def remove_service(key,actor,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p4_services WHERE id=?',(key,)).rowcount:raise ValidationError('Servicio inexistente.')
        _audit(con,'servicio',key,'eliminar',actor)

def import_step3(payload,actor='Equipo PMO',path=None):
    if not isinstance(payload,dict) or payload.get('schema')!='PMO-FLYWHEEL-CENS-paso4-input-v1':
        raise ValidationError('JSON de Paso 3 incompatible. Se requiere esquema paso4-input-v1.')
    proposals=payload.get('proposals')
    if not isinstance(proposals,list):raise ValidationError('Expediente sin propuestas válidas.')
    if len(proposals)>1000:raise ValidationError('Máximo 1.000 propuestas por carga.')
    # Prevalidar toda la carga; no se deja información parcialmente importada.
    prepared=[];seen=set()
    for i,p in enumerate(proposals,1):
        if not isinstance(p,dict):raise ValidationError(f'Propuesta {i} no es un objeto.')
        if p.get('estado')!='Aprobada':raise ValidationError(f'Propuesta {i}: debe estar aprobada en Paso 3.')
        origin=_req(p.get('id'),f'ID de propuesta {i}')
        if origin in seen:raise ValidationError(f'Propuesta duplicada dentro del archivo: {origin}.')
        seen.add(origin)
        needed=('cliente','beneficio','decision','validador','fecha_validacion','evidencia_validacion','necesidad_id')
        missing=[k for k in needed if not str(p.get(k) or '').strip()]
        if missing:raise ValidationError(f'Propuesta {i} sin aprobación completa: {", ".join(missing)}.')
        prepared.append(p)
    result={'nuevos':0,'existentes':0,'codigos':[]}
    with transaction(path) as con:
        used={r[0] for r in con.execute('SELECT codigo FROM p4_services')}
        next_n=1
        for p in prepared:
            old=con.execute('SELECT id FROM p4_services WHERE source_step3_id=?',(p['id'],)).fetchone()
            if old:result['existentes']+=1;continue
            while f'CENS-SRV-{next_n:03d}' in used:next_n+=1
            code=f'CENS-SRV-{next_n:03d}';used.add(code)
            key=_id();name=_req(p.get('nombre'),'nombre de la propuesta')
            source=p.get('version_origen') or payload.get('source',{}).get('implementation','')
            con.execute('''INSERT INTO p4_services(id,codigo,nombre,descripcion,propuesta_valor,cliente,modelo,estado,
              necesidad,beneficio,source_step3_id,source_step3_code,source_step3_version,source_step3_json,detalles_json)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (key,code,name,str(p.get('descripcion') or ''),str(p.get('beneficio') or ''),
               str(p.get('cliente') or ''),'Consultivo','En diseño',str(p.get('necesidad_id') or ''),
               str(p.get('beneficio') or ''),p['id'],p.get('codigo',''),source,_json(p),
               _json(details(None))))
            _audit(con,'servicio',key,'importar_paso3',actor,{'origen':p['id'],'codigo':p.get('codigo')})
            result['nuevos']+=1;result['codigos'].append(code)
    return result

def import_step3_direct(actor='Equipo PMO',path=None):
    from .step3 import step4_transfer
    return import_step3(step4_transfer(path),actor,path)

def metric_list(service_id=None,path=None):
    return _rows('SELECT * FROM p4_metrics'+(' WHERE servicio_id=?' if service_id else '')+' ORDER BY rowid',
                 (service_id,) if service_id else (),path)
def metric(key,path=None):return _row('SELECT * FROM p4_metrics WHERE id=?',(key,),path)
def save_metric(data,actor='Equipo PMO',key=None,path=None):
    service_id=_req(data.get('servicio_id'),'servicio');name=_req(data.get('nombre'),'indicador')
    kind=data.get('tipo')
    if kind not in METRIC_TYPES:raise ValidationError('Tipo de indicador inválido.')
    sentido=data.get('sentido') or 'mayor'
    if sentido not in ('mayor','menor'):raise ValidationError('Sentido de indicador inválido.')
    d={k:str(data.get(k) or '').strip() for k in ('formula','unidad','linea_base','meta','real','frecuencia','responsable','fuente','evidencia','fecha_medicion')}
    d['frecuencia']=d['frecuencia'] or 'Mensual'
    if d['real'] and not d['fecha_medicion']:raise ValidationError('Una medición real requiere fecha.')
    with transaction(path) as con:
        if not con.execute('SELECT id FROM p4_services WHERE id=?',(service_id,)).fetchone():raise ValidationError('Servicio inexistente.')
        vals=(service_id,name,kind,d['formula'],d['unidad'],d['linea_base'],d['meta'],d['real'],sentido,
              d['frecuencia'],d['responsable'],d['fuente'],d['evidencia'],d['fecha_medicion'])
        if key:
            if not con.execute('SELECT id FROM p4_metrics WHERE id=?',(key,)).fetchone():raise ValidationError('Indicador inexistente.')
            con.execute('''UPDATE p4_metrics SET servicio_id=?,nombre=?,tipo=?,formula=?,unidad=?,linea_base=?,
              meta=?,real=?,sentido=?,frecuencia=?,responsable=?,fuente=?,evidencia=?,fecha_medicion=?,
              actualizado_en=CURRENT_TIMESTAMP WHERE id=?''',vals+(key,))
        else:
            key=_id()
            con.execute('''INSERT INTO p4_metrics(id,servicio_id,nombre,tipo,formula,unidad,linea_base,meta,real,
              sentido,frecuencia,responsable,fuente,evidencia,fecha_medicion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (key,)+vals)
        _audit(con,'indicador',key,'guardar',actor)
    return key

def remove_metric(key,actor,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p4_metrics WHERE id=?',(key,)).rowcount:raise ValidationError('Indicador inexistente.')
        _audit(con,'indicador',key,'eliminar',actor)

def members(path=None):return _rows('SELECT * FROM p4_team ORDER BY nombre',path=path)
def member(key,path=None):return _row('SELECT * FROM p4_team WHERE id=?',(key,),path)
PROFILE_FIELDS=('dependencia','equipo','correo','dedicacion_referente','formacion','experiencia',
 'certificaciones','especialidades','evidencia_competencias','disponibilidad','observaciones')

def member_profile(key,path=None):
    row=_row('SELECT * FROM p4_team_profiles WHERE integrante_id=?',(key,),path)
    return {field:(row or {}).get(field,'') for field in PROFILE_FIELDS}

def member_file(key,path=None):
    data=member(key,path)
    if not data:return None
    from .public_codes import code
    return {**data,'codigo_publico':code('integrante',key,path),
            'perfil':member_profile(key,path),
            'asignaciones':[a for a in allocations(path) if a['integrante_id']==key],
            'formacion_pendiente':[a for a in training_list(path) if a['integrante_id']==key]}

def save_member(data,key=None,path=None):
    name=_req(data.get('nombre'),'nombre del integrante');role=_req(data.get('rol'),'rol')
    capacity=int(data.get('capacidad',100))
    if not 0<=capacity<=100:raise ValidationError('Capacidad fuera de 0–100%.')
    skills=data.get('habilidades',{})
    if not isinstance(skills,dict) or any(type(v)!=int or not 1<=v<=5 for v in skills.values()):
        raise ValidationError('Las competencias del integrante deben ser enteros 1–5.')
    profile=data.get('perfil',{})
    if not isinstance(profile,dict):raise ValidationError('Ficha ampliada de integrante inválida.')
    profile={k:str(profile.get(k,'') or '').strip()[:4000] for k in PROFILE_FIELDS}
    with transaction(path) as con:
        if key:
            if not con.execute('SELECT 1 FROM p4_team WHERE id=?' ,(key,)).fetchone():raise ValidationError('Integrante inexistente.')
            assigned=con.execute('SELECT COALESCE(SUM(porcentaje),0) FROM p4_allocations WHERE integrante_id=?',(key,)).fetchone()[0]
            if assigned>capacity:raise ValidationError(f'Capacidad propuesta {capacity}% inferior a asignación vigente {assigned}%.')
            con.execute('UPDATE p4_team SET nombre=?,rol=?,capacidad=?,habilidades_json=? WHERE id=?',
                        (name,role,capacity,_json(skills),key))
        else:
            key=_id();con.execute('INSERT INTO p4_team(id,nombre,rol,capacidad,habilidades_json) VALUES(?,?,?,?,?)',
                                  (key,name,role,capacity,_json(skills)))
        if 'perfil' in data:
            cols=['integrante_id',*PROFILE_FIELDS]
            updates=','.join(f'{k}=excluded.{k}' for k in PROFILE_FIELDS)
            con.execute('INSERT INTO p4_team_profiles ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')'
                        +' ON CONFLICT(integrante_id) DO UPDATE SET '+updates+',actualizado_en=CURRENT_TIMESTAMP',
                        (key,)+tuple(profile[k] for k in PROFILE_FIELDS))
    return key

def save_requirement(service_id,skill,level,path=None):
    skill=_req(skill,'competencia');level=int(level)
    if not 1<=level<=5:raise ValidationError('Nivel requerido fuera de 1–5.')
    with transaction(path) as con:
        con.execute('''INSERT INTO p4_requirements(servicio_id,competencia,nivel) VALUES(?,?,?)
                       ON CONFLICT(servicio_id,competencia) DO UPDATE SET nivel=excluded.nivel''',
                    (service_id,skill,level))

def requirements(service_id=None,path=None):
    return _rows('SELECT * FROM p4_requirements'+(' WHERE servicio_id=?' if service_id else '')+' ORDER BY competencia',
                 (service_id,) if service_id else (),path)
# Plantilla inicial por servicio del taller (hipótesis de diseño; NO evaluación de personas).
SUGGESTED_REQUIREMENTS={
 1:{'Gobernanza':4,'Gestión de portafolios':4,'Facilitación y comunicación':4},
 2:{'Gestión de beneficios':5,'Análisis de datos':4,'Gestión de portafolios':3},
 3:{'Facilitación y comunicación':5,'Gestión del cambio':4,'Metodologías ágiles':3},
 4:{'Gobernanza':5,'Gestión de portafolios':4},
 5:{'Gestión del cambio':5,'Facilitación y comunicación':4},
 6:{'Gestión de portafolios':5,'Análisis de datos':4,'Gobernanza':4},
 7:{'Gestión de portafolios':5,'Gestión de beneficios':4},
 8:{'Herramientas digitales':4,'Facilitación y comunicación':4},
 9:{'Dirección de proyectos':5,'Metodologías ágiles':4,'Gobernanza':4},
 10:{'Gestión de portafolios':4,'Dirección de proyectos':4,'Análisis de datos':3},
 11:{'Herramientas digitales':5,'Análisis de datos':4},
 12:{'Facilitación y comunicación':5,'Dirección de proyectos':4},
 13:{'Gobernanza':4,'Gestión de riesgos':4},
 14:{'Dirección de proyectos':4,'Gestión de riesgos':4,'Gobernanza':4},
 15:{'Facilitación y comunicación':5,'Gestión del cambio':4},
 16:{'Análisis de datos':5,'Herramientas digitales':4},
 17:{'Gestión de riesgos':4,'Facilitación y comunicación':4},
 18:{'Facilitación y comunicación':5,'Dirección de proyectos':4},
 19:{'Análisis de datos':5,'Dirección de proyectos':4,'Gestión de beneficios':4},
 20:{'Dirección de proyectos':5,'Gestión de portafolios':4},
 21:{'Dirección de proyectos':5,'Gestión de riesgos':4},
 22:{'Dirección de proyectos':4,'Facilitación y comunicación':4},
 23:{'Gobernanza':4,'Dirección de proyectos':4,'Gestión de riesgos':4},
 24:{'Gestión de riesgos':5,'Análisis de datos':3},
 25:{'Gestión de riesgos':4,'Análisis de datos':4},
 26:{'Facilitación y comunicación':5,'Gestión del cambio':4}}

def _taller_number(item):
    import re
    found=re.fullmatch(r'TVAL26-SRV-(\d{1,3})',item.get('codigo',''))
    return int(found.group(1)) if found else None

def preview_requirements(path=None):
    existing={(r['servicio_id'],r['competencia']) for r in requirements(path=path)}
    return [{'servicio_id':s['id'],'servicio':s['nombre'],'competencia':skill,'nivel_sugerido':level,
             'origen':'Hipótesis PMO V0.39.9 · validar por experto'}
        for s in services(path)
        for skill,level in SUGGESTED_REQUIREMENTS.get(_taller_number(s),{}).items()
        if (s['id'],skill) not in existing]

def add_suggested_requirements(path=None):
    proposed=preview_requirements(path)
    if not proposed:return 0
    with transaction(path) as con:
        for row in proposed:
            con.execute('INSERT OR IGNORE INTO p4_requirements(servicio_id,competencia,nivel) VALUES(?,?,?)',
                        (row['servicio_id'],row['competencia'],row['nivel_sugerido']))
        _audit(con,'requisitos','taller','propuesta_competencias','Equipo PMO',
               {'cantidad':len(proposed),'origen':'Hipótesis PMO V0.39.9; requiere validación'})
    return len(proposed)

def allocations(path=None):return _rows('SELECT * FROM p4_allocations ORDER BY rowid',path=path)
def save_allocation(member_id,service_id,percent,path=None):
    percent=int(percent)
    if not 0<=percent<=100:raise ValidationError('Porcentaje fuera de 0–100.')
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM p4_team WHERE id=?',(member_id,)).fetchone():raise ValidationError('Integrante inexistente.')
        if not con.execute('SELECT 1 FROM p4_services WHERE id=?',(service_id,)).fetchone():raise ValidationError('Servicio inexistente.')
        existing=con.execute('SELECT COALESCE(SUM(porcentaje),0) FROM p4_allocations WHERE integrante_id=? AND servicio_id<>?',
                             (member_id,service_id)).fetchone()[0]
        cap=con.execute('SELECT capacidad FROM p4_team WHERE id=?',(member_id,)).fetchone()[0]
        if existing+percent>cap:raise ValidationError(f'Sobrecarga: {existing+percent}% asignado supera capacidad {cap}%.')
        con.execute('''INSERT INTO p4_allocations(id,integrante_id,servicio_id,porcentaje) VALUES(?,?,?,?)
                       ON CONFLICT(integrante_id,servicio_id) DO UPDATE SET porcentaje=excluded.porcentaje''',
                    (_id(),member_id,service_id,percent))

def capacity_summary(path=None):
    team=members(path);alloc=allocations(path)
    return [{**m,'asignado':sum(a['porcentaje'] for a in alloc if a['integrante_id']==m['id']),
             'restante':m['capacidad']-sum(a['porcentaje'] for a in alloc if a['integrante_id']==m['id'])}
            for m in team]

def competency_gaps(service_id,path=None):
    need=requirements(service_id,path);alloc=allocations(path)
    assigned={a['integrante_id'] for a in alloc if a['servicio_id']==service_id and a['porcentaje']>0}
    people=[m for m in members(path) if m['id'] in assigned]
    result=[]
    for req in need:
        available=max((json.loads(m['habilidades_json']).get(req['competencia'],0) for m in people),default=0)
        result.append({'competencia':req['competencia'],'requerido':req['nivel'],
                       'disponible':available if people else None,
                       'brecha':max(0,req['nivel']-available) if people else None,
                       'sin_asignacion':not bool(people)})
    return result

def training_list(path=None):return _rows('SELECT * FROM p4_training ORDER BY rowid DESC',path=path)
def add_training(member_id,skill,action,date_target='',status='Pendiente',owner='',evidence='',path=None):
    action=_req(action,'acción de formación')
    if status not in ('Pendiente','En curso','Completada'):raise ValidationError('Estado de formación inválido.')
    with transaction(path) as con:
        key=_id();con.execute('INSERT INTO p4_training(id,integrante_id,competencia,accion,meta_fecha,estado,responsable,evidencia) VALUES(?,?,?,?,?,?,?,?)',
                              (key,member_id,_req(skill,'competencia'),action,date_target,status,owner,evidence))
    return key

def readiness_report(item,path=None,details_override=None):
    """Fuente única de elegibilidad a Paso 05 (sin confundirlo con operar).

    Los estados de la ficha, ANS y aprobación institucional son independientes.
    Cumplir la lista no marca ningún estado ni registra una aprobación.
    """
    d=details_override if details_override is not None else details(item)
    ms=metric_list(item['id'],path) if item.get('id') else []
    kinds={m.get('tipo') for m in ms if all(str(m.get(k) or '').strip() for k in ('tipo','formula','meta','responsable','fuente'))}
    files=[x for x in d.get('ans_versiones',[]) if isinstance(x,dict)] if isinstance(d.get('ans_versiones'),list) else []
    alloc=allocations(path) if item.get('id') else []
    req=requirements(item['id'],path) if item.get('id') else []
    p4_attachments=bool(d.get('ans_archivo')) or bool(d.get('validacion_evidencia'))
    process_defined=bool(d.get('proceso_actividades')) or bool(str(d.get('proceso') or '').strip())
    raci_defined=bool(d.get('raci_registro')) or bool(d.get('raci_matriz_propuesta')) or bool(str(d.get('raci') or '').strip())
    def is_text(key):return bool(str(d.get(key) or '').strip())
    def is_item(key):return bool(str(item.get(key) or '').strip())
    records=[
      ('IDENTIDAD','Identificación y propuesta de valor',all(is_item(k) for k in ('nombre','descripcion','propuesta_valor')),'Ficha general','Nombre, descripción y propuesta de valor'),
      ('CLIENTES','Cliente, propietario y modelo',all(is_item(k) for k in ('cliente','responsable','modelo')),'Ficha general','Destinatarios, responsable y modelo de prestación'),
      ('ACTIVACION','Activación del servicio',bool(d.get('activaciones')) or is_text('solicitud'),'Activación y proceso','Modo o instrucciones de solicitud'),
      ('PROCESO','Proceso y RACI',process_defined and raci_defined,'Activación y proceso','Proceso y matriz de responsabilidades documentados'),
      ('RACI_AVAL','RACI aprobado con evidencia',is_text('evidencia_raci_aprobado'),'Activación y proceso','Acta o documento que formaliza la matriz RACI'),
      ('ANS_DEFINICION','ANS, alcance y aceptación',all(is_text(k) for k in ('alcance','sla_respuesta','sla_entrega','sla_aceptacion','sla_calidad')),'ANS y validación','Alcance, plazos, calidad y aceptación configurados'),
      ('ANS_VALIDADO','ANS validado con evidencia',str(d.get('ans_estado') or '')=='Validado' and bool(files) and bool(d.get('ans_cliente_id')) and is_text('validacion_cliente') and is_text('validacion_fecha') and p4_attachments,'ANS y validación','Validación formal, cliente y versión documental conservada'),
      ('METRICAS','Indicadores de eficiencia, salida y resultado',set(METRIC_TYPES).issubset(kinds),'Métricas de servicios','Al menos un indicador por tipo con fórmula, meta, responsable y fuente; sin exigir mediciones reales'),
      ('RECURSOS','Recursos y competencias',bool(req) and any(a['servicio_id']==item.get('id') and a['porcentaje']>0 for a in alloc),'Recursos y competencias','Competencias requeridas y capacidad asignada'),
      ('RUTA','Plan de implementación y transición',is_text('plan') and is_text('transicion'),'Implementación','Hoja de ruta y requisitos de transición definidos'),
      ('ESTADO','Estado aprobado',item.get('estado')=='Aprobado','Ficha general','Estado aprobado registrado; por sí solo no habilita la transferencia'),
      ('AVAL','Aprobación institucional documentada',bool(d.get('evidencia_aprobacion_institucional')) and d.get('estado_aprobacion_institucional')=='Aprobación Institucional Definitiva','Implementación','Decisión institucional y evidencia vinculadas'),
    ]
    return [{'codigo':code,'nombre':title,'cumplido':bool(ok),'modulo':module,'detalle':desc}
            for code,title,ok,module,desc in records]

def service_readiness(item,path=None):
    """Compatibilidad con importador Paso 05 y paneles existentes."""
    return [x['nombre'] for x in readiness_report(item,path) if not x['cumplido']]

def step5_transfer(path=None):
    ready=[];blocked=[]
    for item in services(path):
        missing=service_readiness(item,path)
        if missing:blocked.append({'codigo':item['codigo'],'faltan':missing});continue
        x={**item,'detalles':details(item),'indicadores':metric_list(item['id'],path),
           'competencias_requeridas':requirements(item['id'],path),
           'asignaciones':[a for a in allocations(path) if a['servicio_id']==item['id']]}
        ready.append(x)
    return {'schema':'PMO-FLYWHEEL-CENS-paso5-input-v1','exportedAt':datetime.now(timezone.utc).isoformat(),
            'source':{'step':'Paso 4','implementation':'Streamlit V0.13','evaluation':'independiente'},
            'services':ready,'blocked':blocked,
            'note':'La transferencia no implementa ni pone en operación los servicios del Paso 5.'}

def evaluation_list(path=None):return _rows('SELECT * FROM p4_evaluations ORDER BY version DESC',path=path)
def evaluation(key,path=None):return _row('SELECT * FROM p4_evaluations WHERE id=?',(key,),path)
def answers(key,path=None):return _rows('SELECT * FROM p4_answers WHERE evaluacion_id=? ORDER BY numero',(key,),path)
def create_evaluation(owner,path=None):
    owner=_req(owner,'responsable')
    with transaction(path) as con:
        v=con.execute('SELECT COALESCE(MAX(version),0)+1 FROM p4_evaluations').fetchone()[0]
        key=_id();con.execute('INSERT INTO p4_evaluations(id,version,responsable) VALUES(?,?,?)',(key,v,owner))
    return key

def save_answer(eid,num,score,observation='',evidence='',owner='',path=None):
    num=int(num)
    if not 1<=num<=35:raise ValidationError('Pregunta fuera de 1–35.')
    if score is not None and (type(score)!=int or not 1<=score<=5):raise ValidationError('La puntuación debe ser 1–5.')
    with transaction(path) as con:
        ev=con.execute('SELECT estado FROM p4_evaluations WHERE id=?',(eid,)).fetchone()
        if not ev:raise ValidationError('Evaluación inexistente.')
        if ev['estado']=='Finalizada':raise ValidationError('La evaluación finalizada es inmutable. Crea un nuevo corte.')
        if score is None:con.execute('DELETE FROM p4_answers WHERE evaluacion_id=? AND numero=?',(eid,num))
        else:con.execute('''INSERT INTO p4_answers(evaluacion_id,numero,valor,observacion,evidencia,responsable)
             VALUES(?,?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET
             valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia,
             responsable=excluded.responsable,fecha=CURRENT_TIMESTAMP''',(eid,num,score,observation,evidence,owner))

def classification(score):
    if not 35<=score<=175:raise ValidationError('Puntaje PMI fuera de rango.')
    if score>=154:return 'Excelente'
    if score>=131:return 'Bien'
    if score>=102:return 'Promedio'
    if score>=68:return 'Pobre'
    return 'Crítico'

def evaluation_summary(eid,path=None):
    ev=evaluation(eid,path)
    if not ev:raise ValidationError('Evaluación inexistente.')
    aa=answers(eid,path);points={a['numero']:a['valor'] for a in aa}
    dims=[]
    for i,(title,_) in enumerate(DIMENSIONS):
        values=[points.get(i*5+j+1) for j in range(5)]
        observed=[v for v in values if v is not None]
        dims.append({'nombre':title,'respondidas':len(observed),'subtotal':sum(observed),
                     'promedio':round(sum(observed)/len(observed),2) if observed else None})
    complete=len(aa)==35
    return {**ev,'respondidas':len(aa),'subtotal_parcial':sum(points.values()),
            'puntaje':sum(points.values()) if complete else None,
            'clasificacion':classification(sum(points.values())) if complete else None,'dimensiones':dims}

def finish_evaluation(eid,actor,path=None):
    summary=evaluation_summary(eid,path)
    if summary['respondidas']!=35:raise ValidationError('Se requieren 35 respuestas antes de finalizar.')
    with transaction(path) as con:
        if summary['estado']=='Finalizada':raise ValidationError('Evaluación ya finalizada.')
        con.execute('''UPDATE p4_evaluations SET estado='Finalizada',puntaje=?,clasificacion=?,
                       finalizado_en=CURRENT_TIMESTAMP WHERE id=?''',
                    (summary['puntaje'],summary['clasificacion'],eid))
        _audit(con,'autoevaluacion',eid,'finalizar',actor,{'puntaje':summary['puntaje']})
    return summary

def assessment_export(eid,path=None):
    return {'schema':'PMO-CENS-P4-EVALUACION-v1','evaluacion':evaluation_summary(eid,path),
            'respuestas':answers(eid,path),'dimensiones':DIMENSIONS,'preguntas':QUESTIONS}

def export_catalog_json(path=None):
    from .public_codes import code
    return {'schema':'PMO-CENS-P4-CATALOGO-v1',
            'services':[dict(s,codigo_publico=code('servicio',s['id'],path),detalles=details(s)) for s in services(path)]}
def export_metrics_csv(path=None):
    columns=('servicio_id','nombre','tipo','formula','unidad','linea_base','meta','real','sentido','frecuencia','responsable','fuente','evidencia','fecha_medicion')
    o=io.StringIO();w=csv.DictWriter(o,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(metric_list(path=path))
    return o.getvalue().encode('utf-8-sig')

def import_catalog(records,actor='Equipo PMO',path=None):
    """Carga transaccional de catálogo. Los códigos existentes se omiten sin sobrescribir."""
    if not isinstance(records,list) or not records:raise ValidationError('El archivo no tiene registros.')
    if len(records)>1000:raise ValidationError('Máximo 1.000 servicios por carga.')
    normalized=[];seen=set()
    for i,item in enumerate(records,1):
        if not isinstance(item,dict):raise ValidationError(f'Fila {i} no válida.')
        name=_req(item.get('nombre'),f'nombre en fila {i}')
        code=_req(item.get('codigo'),f'código en fila {i}')
        if code.casefold() in seen:raise ValidationError(f'Código duplicado en Excel: {code}.')
        seen.add(code.casefold())
        state=item.get('estado') or 'Borrador'
        if state not in STATUSES:raise ValidationError(f'Estado no válido en fila {i}.')
        raw_details=item.get('detalles_json') or item.get('detalles') or '{}'
        if isinstance(raw_details,str):
            try:raw_details=json.loads(raw_details)
            except json.JSONDecodeError:raise ValidationError(f'JSON de ficha inválido, fila {i}.')
        if not isinstance(raw_details,dict):raise ValidationError(f'Detalles inválidos, fila {i}.')
        normalized.append((code,name,str(item.get('descripcion') or ''),str(item.get('propuesta_valor') or ''),
                           str(item.get('cliente') or ''),str(item.get('responsable') or ''),
                           str(item.get('modelo') or 'Consultivo'),state,str(item.get('necesidad') or ''),
                           str(item.get('beneficio') or ''),_json(raw_details)))
    result={'nuevos':0,'existentes':0}
    with transaction(path) as con:
        existing={r[0].casefold() for r in con.execute('SELECT codigo FROM p4_services')}
        for v in normalized:
            if v[0].casefold() in existing:result['existentes']+=1;continue
            key=_id()
            con.execute('''INSERT INTO p4_services(id,codigo,nombre,descripcion,propuesta_valor,cliente,responsable,
                modelo,estado,necesidad,beneficio,detalles_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(key,)+v)
            _audit(con,'servicio',key,'importar_catalogo',actor,{'codigo':v[0]})
            result['nuevos']+=1
    return result


def remove_requirement(service_id,skill,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p4_requirements WHERE servicio_id=? AND competencia=?',
                           (service_id,skill)).rowcount:raise ValidationError('Competencia requerida inexistente.')

def remove_allocation(member_id,service_id,path=None):
    with transaction(path) as con:
        if not con.execute('DELETE FROM p4_allocations WHERE integrante_id=? AND servicio_id=?',
                           (member_id,service_id)).rowcount:raise ValidationError('Asignación inexistente.')

def remove_member(member_id,path=None):
    with transaction(path) as con:
        if con.execute('SELECT 1 FROM p4_allocations WHERE integrante_id=? LIMIT 1',(member_id,)).fetchone():
            raise ValidationError('Retira sus asignaciones antes de eliminar este integrante.')
        if con.execute('SELECT 1 FROM p4_training WHERE integrante_id=? LIMIT 1',(member_id,)).fetchone():
            raise ValidationError('El integrante tiene acciones de formación asociadas.')
        if not con.execute('DELETE FROM p4_team WHERE id=?',(member_id,)).rowcount:
            raise ValidationError('Integrante inexistente.')

BACKUP_TABLES=('p4_services','p4_team','p4_team_profiles','p4_metrics','p4_requirements','p4_allocations',
               'p4_training','p4_evaluations','p4_answers','p4_audit')

def backup_step4(path=None):
    with closing(connect(path)) as con:
        tables={name:[dict(r) for r in con.execute('SELECT * FROM '+name)] for name in BACKUP_TABLES}
    return {'schema':'PMO-CENS-P4-BACKUP-v1','exportedAt':datetime.now(timezone.utc).isoformat(),
            'note':'Respalda únicamente las tablas p4_*; no incluye Pasos 1, 2 y 3.',
            'tables':tables}

def restore_step4(payload,confirm=False,path=None):
    """Restauración explícita y atómica SOLO de tablas p4_*; nunca altera P1–P3."""
    if not confirm:raise ValidationError('Para restaurar debes confirmar la sustitución de datos del Paso 4.')
    if not isinstance(payload,dict) or payload.get('schema')!='PMO-CENS-P4-BACKUP-v1':
        raise ValidationError('El archivo no es un respaldo del Paso 4 compatible.')
    tables=payload.get('tables')
    if not isinstance(tables,dict) or (set(tables)!=set(BACKUP_TABLES) and set(tables)!=(set(BACKUP_TABLES)-{'p4_team_profiles'})):
        raise ValidationError('El respaldo no contiene las tablas necesarias.')
    tables={'p4_team_profiles':[],**tables}
    if any(not isinstance(tables[t],list) or len(tables[t])>20000 for t in BACKUP_TABLES):
        raise ValidationError('Respaldo inválido o superior al máximo permitido.')
    with transaction(path) as con:
        for name in reversed(BACKUP_TABLES):con.execute('DELETE FROM '+name)
        for name in BACKUP_TABLES:
            cols={r[1] for r in con.execute('PRAGMA table_info('+name+')')}
            for item in tables[name]:
                if not isinstance(item,dict) or set(item)!=cols:
                    raise ValidationError('Columnas incompatibles en '+name)
                keys=list(item)
                con.execute(f'INSERT INTO {name} ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',
                            tuple(item[k] for k in keys))
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValidationError('El respaldo contiene relaciones inexistentes.')
        _audit(con,'respaldo','paso4','restaurar','Usuario',{'tablas':len(BACKUP_TABLES)})
    return {'restaurados':sum(len(tables[t]) for t in BACKUP_TABLES),'tablas':len(BACKUP_TABLES)}
