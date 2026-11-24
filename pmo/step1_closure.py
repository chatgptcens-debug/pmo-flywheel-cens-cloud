"""V0.31 · Cierre documentado del Paso 01 y paquete de antecedentes del Paso 02.

No valida necesidades ni modifica p2_necesidades. Almacena instantáneas inmutables
que pueden revisarse y transferirse posteriormente al diagnóstico del Paso 02.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import json
import sqlite3
import uuid

from .clients import ValidationError
from .storage import connect, transaction
from .awareness_dashboard import snapshot
from . import assessment

STATUSES = ('Pendiente', 'En curso', 'Cumplida', 'Cancelada')
SCHEMA = """
CREATE TABLE IF NOT EXISTS p1_acciones_mejora (
 id TEXT PRIMARY KEY,
 evaluacion_id TEXT REFERENCES p1_autoevaluaciones(id),
 dimension TEXT NOT NULL,
 hallazgo TEXT NOT NULL,
 accion TEXT NOT NULL,
 responsable TEXT NOT NULL,
 fecha_objetivo TEXT,
 estado TEXT NOT NULL DEFAULT 'Pendiente'
   CHECK(estado IN ('Pendiente','En curso','Cumplida','Cancelada')),
 evidencia TEXT NOT NULL DEFAULT '',
 verificacion TEXT NOT NULL DEFAULT '',
 creado_por TEXT NOT NULL,
 creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_p1_acciones_mejora_estado ON p1_acciones_mejora(estado,fecha_objetivo);
CREATE TABLE IF NOT EXISTS p1_transferencias_p2 (
 id TEXT PRIMARY KEY,
 periodo TEXT NOT NULL,
 responsable TEXT NOT NULL,
 observaciones TEXT NOT NULL DEFAULT '',
 registros_json TEXT NOT NULL,
 estado TEXT NOT NULL DEFAULT 'Preparada' CHECK(estado IN ('Preparada','Entregada')),
 creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 entregado_en TEXT
);
CREATE TABLE IF NOT EXISTS p1_cierres (
 id TEXT PRIMARY KEY,
 periodo TEXT NOT NULL,
 evaluacion_id TEXT NOT NULL REFERENCES p1_autoevaluaciones(id),
 transferencia_id TEXT REFERENCES p1_transferencias_p2(id),
 responsable TEXT NOT NULL,
 sintesis TEXT NOT NULL,
 pendientes TEXT NOT NULL DEFAULT '',
 decisiones TEXT NOT NULL DEFAULT '',
 resumen_json TEXT NOT NULL,
 creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_p1_cierres_periodo ON p1_cierres(periodo,creado_en);
"""


def _text(value, label, required=True, limit=6000):
    s = str(value or '').strip()
    if required and not s:
        raise ValidationError(f'Indique {label}.')
    if len(s)>limit:
        raise ValidationError(f'{label}: máximo {limit} caracteres.')
    return s


def initialize(path:Path|None=None):
    # CREATE IF NOT EXISTS no altera las tablas históricas ni sus registros.
    with closing(connect(path)) as con:
        con.executescript(SCHEMA)
        con.commit()


def _audit(con, entity, identifier, action, actor):
    con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor) VALUES(?,?,?,?)',
                (entity,identifier,action,actor))


def add_action(dimension, finding, action, owner, actor, due=None, assessment_id=None, evidence='',path=None):
    dimension=_text(dimension,'la dimensión',limit=160)
    if dimension not in [d[0] for d in assessment.DIMENSIONS]+['Transversal']:
        raise ValidationError('Seleccione una dimensión metodológica válida.')
    finding=_text(finding,'el hallazgo')
    action=_text(action,'la acción')
    owner=_text(owner,'el responsable',limit=180)
    actor=_text(actor,'quién registra',limit=180)
    evidence=_text(evidence,'la evidencia',False)
    due=(due.isoformat() if isinstance(due,date) else str(due).strip()) if due else None
    if due:
        try:date.fromisoformat(due)
        except ValueError as exc:raise ValidationError('Fecha objetivo inválida.') from exc
    key=uuid.uuid4().hex
    with transaction(path) as con:
        if assessment_id and not con.execute('SELECT 1 FROM p1_autoevaluaciones WHERE id=?',(assessment_id,)).fetchone():
            raise ValidationError('La autoevaluación seleccionada no existe.')
        con.execute('''INSERT INTO p1_acciones_mejora
            (id,evaluacion_id,dimension,hallazgo,accion,responsable,fecha_objetivo,evidencia,creado_por)
            VALUES(?,?,?,?,?,?,?,?,?)''',
            (key,assessment_id or None,dimension,finding,action,owner,due,evidence,actor))
        _audit(con,'p1_accion_mejora',key,'crear',actor)
    return key


def update_action(key,state,evidence,verification,actor,path=None):
    if state not in STATUSES:raise ValidationError('Estado no válido.')
    actor=_text(actor,'el responsable de la actualización',limit=180)
    evidence=_text(evidence,'la evidencia',False)
    verification=_text(verification,'la verificación',False)
    if state=='Cumplida' and not verification:
        raise ValidationError('Para marcar Cumplida registre la verificación del resultado.')
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM p1_acciones_mejora WHERE id=?',(key,)).fetchone():
            raise ValidationError('Acción de mejora inexistente.')
        con.execute('''UPDATE p1_acciones_mejora SET estado=?,evidencia=?,verificacion=?,
                   actualizado_en=CURRENT_TIMESTAMP WHERE id=?''',
                   (state,evidence,verification,key))
        _audit(con,'p1_accion_mejora',key,'actualizar',actor)


def list_actions(path=None):
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('SELECT * FROM p1_acciones_mejora ORDER BY creado_en DESC,id DESC')]


def preliminary_records(path=None):
    """Candidatos seleccionables: solo insumos expresos, nunca necesidades validadas."""
    with closing(connect(path)) as con:
        interactions=[dict(r) for r in con.execute('''SELECT i.id,i.cliente_id,i.fecha,
          i.necesidad_preliminar,c.codigo,c.nombre,d.nombre AS dependencia
          FROM p1_interacciones i JOIN pmo_clientes c ON c.id=i.cliente_id
          JOIN pmo_dependencias d ON d.id=c.dependencia_id
          WHERE i.insumo_paso2=1 AND TRIM(i.necesidad_preliminar)<>''
          ORDER BY i.fecha DESC,i.id DESC''')]
        clients=[dict(r) for r in con.execute('''SELECT c.id,c.codigo,c.nombre,c.necesidades_preliminares,
          d.nombre AS dependencia FROM pmo_clientes c JOIN pmo_dependencias d ON d.id=c.dependencia_id
          WHERE c.activo=1 AND TRIM(c.necesidades_preliminares)<>'' ORDER BY c.codigo''')]
    results=[]
    for r in interactions:
        results.append({'clave':'interaccion:'+r['id'],'tipo':'Interacción','origen_id':r['id'],
            'cliente_id':r['cliente_id'],'codigo_cliente':r['codigo'],
            'cliente':r['nombre'],'dependencia':r['dependencia'],
            'fecha_origen':r['fecha'],'texto':r['necesidad_preliminar'],
            'clasificacion':'Antecedente preliminar · no validado'})
    for r in clients:
        results.append({'clave':'cliente:'+r['id'],'tipo':'Caracterización','origen_id':r['id'],
            'cliente_id':r['id'],'codigo_cliente':r['codigo'],
            'cliente':r['nombre'],'dependencia':r['dependencia'],'fecha_origen':None,
            'texto':r['necesidades_preliminares'],
            'clasificacion':'Antecedente preliminar · no validado'})
    return results


def prepare_transfer(period,owner,keys,notes='',path=None):
    period=_text(period,'el periodo',limit=60)
    owner=_text(owner,'el responsable',limit=180)
    notes=_text(notes,'las observaciones',False)
    if not isinstance(keys,(list,tuple,set)):
        raise ValidationError('Seleccione los antecedentes de forma explícita.')
    # La selección es explícita, nunca incluye silenciosamente a todos los clientes.
    selected=set(keys)
    available={r['clave']:r for r in preliminary_records(path)}
    unknown=selected-set(available)
    if unknown:raise ValidationError('Algunos antecedentes seleccionados ya no existen. Actualice la lista.')
    records=[available[k] for k in sorted(selected)]
    key=uuid.uuid4().hex
    with transaction(path) as con:
        con.execute('''INSERT INTO p1_transferencias_p2
            (id,periodo,responsable,observaciones,registros_json) VALUES(?,?,?,?,?)''',
            (key,period,owner,notes,json.dumps(records,ensure_ascii=False)))
        _audit(con,'p1_transferencia_p2',key,'preparar',owner)
    return key


def list_transfers(path=None):
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('SELECT * FROM p1_transferencias_p2 ORDER BY creado_en DESC,id DESC')]


def get_transfer(key,path=None):
    with closing(connect(path)) as con:
        row=con.execute('SELECT * FROM p1_transferencias_p2 WHERE id=?',(key,)).fetchone()
    if not row:raise ValidationError('Paquete de transferencia inexistente.')
    data=dict(row)
    data['antecedentes']=json.loads(data.pop('registros_json'))
    data['nota_metodologica']='Insumos no validados; evaluar y priorizar en Paso 02 antes de convertirlos en necesidades.'
    return data


def mark_transferred(key,actor,path=None):
    actor=_text(actor,'el responsable de la entrega',limit=180)
    with transaction(path) as con:
        row=con.execute('SELECT estado FROM p1_transferencias_p2 WHERE id=?',(key,)).fetchone()
        if not row:raise ValidationError('Transferencia inexistente.')
        if row['estado']=='Entregada':raise ValidationError('La transferencia ya figura como entregada.')
        con.execute("UPDATE p1_transferencias_p2 SET estado='Entregada', entregado_en=CURRENT_TIMESTAMP WHERE id=?",(key,))
        _audit(con,'p1_transferencia_p2',key,'entregar',actor)


def closure_preview(period,path=None):
    period=_text(period,'el periodo',limit=60)
    year = period if len(period)==4 and period.isdigit() else None
    data=snapshot(path, start=f'{year}-01-01' if year else '', end=f'{year}-12-31' if year else '')
    evals=[r for r in assessment.list_assessments(path) if r['estado']=='Finalizada' and r['periodo']==period]
    actions=[a for a in list_actions(path) if not year or (a['creado_en'] or '').startswith(year)]
    transfers=[r for r in list_transfers(path) if r['periodo']==period]
    return {'periodo':period,'indicadores':{
        'clientes_activos':data['active'],'clientes_alcanzados':data['reached'],
        'cobertura_pct':data['coverage'],'interacciones':data['interactions'],
        'consultas':data['consultations'],'asistentes_unicos':data['attendance_unique'],
        'eventos_realizados':data['events_realized'],'familiaridad':data['familiarity'],
        'encuestas_posteriores':data['survey_after_count'],'pares_comparables':data['paired_count'],
        'compromisos_pendientes':data['commitments_pending']},
        'matriz_evidencias':data['evidence'],
        'autoevaluaciones_finalizadas':[{'id':e['id'],'puntaje':e['puntaje'],
           'clasificacion':e['clasificacion'],'finalizada_en':e['finalizada_en']} for e in evals],
        'acciones_mejora':{'total':len(actions),'pendientes':sum(x['estado'] in ('Pendiente','En curso') for x in actions),
             'detalle':[{'id':a['id'],'dimension':a['dimension'],'hallazgo':a['hallazgo'],
              'accion':a['accion'],'responsable':a['responsable'],'estado':a['estado'],
              'fecha_objetivo':a['fecha_objetivo'],'verificacion':a['verificacion']} for a in actions]},
        'alcance_temporal':f'Actividades del año {year}' if year else 'Todas las actividades del ciclo (periodo sin año YYYY)',
        'transferencias_preparadas':len(transfers),
        'advertencia':'Los resultados reflejan registros disponibles al corte de elaboración; no certifican beneficios ni cierre obligatorio del Paso 01.'}


def create_closure(period,assessment_id,owner,summary,pending='',decisions='',transfer_id=None,path=None):
    period=_text(period,'el periodo',limit=60)
    owner=_text(owner,'el responsable',limit=180)
    summary=_text(summary,'la síntesis ejecutiva')
    pending=_text(pending,'los pendientes',False)
    decisions=_text(decisions,'las decisiones',False)
    view=closure_preview(period,path)
    eligible={v['id'] for v in view['autoevaluaciones_finalizadas']}
    if assessment_id not in eligible:
        raise ValidationError('Seleccione una autoevaluación finalizada del mismo periodo.')
    if transfer_id:
        matches=[x for x in list_transfers(path) if x['id']==transfer_id and x['periodo']==period]
        if not matches:raise ValidationError('Seleccione un paquete de antecedentes del mismo periodo.')
    key=uuid.uuid4().hex
    payload={**view,'autoevaluacion_seleccionada':assessment_id,
             'autoevaluacion_dimensiones':assessment.dimension_summary(assessment_id,path),
             'transferencia_seleccionada':transfer_id,
             'sintesis':summary,'pendientes':pending,'decisiones':decisions,
             'elaborado_por':owner,'elaborado_fecha':datetime.now().isoformat(timespec='seconds')}
    with transaction(path) as con:
        con.execute('''INSERT INTO p1_cierres
           (id,periodo,evaluacion_id,transferencia_id,responsable,sintesis,pendientes,decisiones,resumen_json)
           VALUES(?,?,?,?,?,?,?,?,?)''',
           (key,period,assessment_id,transfer_id,owner,summary,pending,decisions,
            json.dumps(payload,ensure_ascii=False,default=str)))
        _audit(con,'p1_cierre',key,'documentar',owner)
    return key


def list_closures(path=None):
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('''SELECT id,periodo,evaluacion_id,transferencia_id,responsable,
          sintesis,creado_en FROM p1_cierres ORDER BY creado_en DESC,id DESC''')]


def get_closure(key,path=None):
    with closing(connect(path)) as con:
        row=con.execute('SELECT * FROM p1_cierres WHERE id=?',(key,)).fetchone()
    if not row:raise ValidationError('Cierre inexistente.')
    data=dict(row)
    data['resumen']=json.loads(data.pop('resumen_json'))
    return data


def report_html(record:dict)->bytes:
    """Informe ejecutivo imprimible, escapa datos de usuario para evitar HTML activo."""
    import html
    def h(v):return html.escape(str(v if v is not None else 'Sin medición'))
    r=record['resumen']; k=r['indicadores']
    rows=''.join('<tr><td>'+h(n)+'</td><td>'+h(v)+'</td></tr>' for n,v in [
       ('Clientes activos',k['clientes_activos']),('Clientes alcanzados',k['clientes_alcanzados']),
       ('Cobertura (%)',f"{k['cobertura_pct']:.0f}%" if k['cobertura_pct'] is not None else 'Sin denominador'),
       ('Interacciones',k['interacciones']),('Consultas',k['consultas']),
       ('Eventos realizados',k['eventos_realizados']),('Asistentes únicos',k['asistentes_unicos']),
       ('Familiaridad',f"{k['familiaridad']:.2f}/5" if k['familiaridad'] is not None else 'Sin medición'),
       ('Pares comparables',k['pares_comparables']),('Compromisos pendientes',k['compromisos_pendientes'])])
    evidence=''.join('<tr><td>'+h(x.get('Actividad PMI'))+'</td><td>'+h(x.get('Estado'))+'</td><td>'+h(x.get('Evidencia'))+'</td></tr>' for x in r['matriz_evidencias'])
    actions=''.join('<tr><td>'+h(a['dimension'])+'</td><td>'+h(a['accion'])+'</td><td>'+h(a['estado'])+'</td></tr>' for a in r['acciones_mejora']['detalle'])
    ev=next((x for x in r['autoevaluaciones_finalizadas'] if x['id']==record['evaluacion_id']),None)
    ev_text=f"{ev['puntaje']}/125 · {ev['clasificacion']}" if ev else 'No disponible'
    dimensions=''.join('<tr><td>'+h(x['Dimensión'])+'</td><td>'+h(x['Puntaje'])+'/25</td></tr>' for x in r.get('autoevaluacion_dimensiones',[]))
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
    <title>PMO CENS · Cierre Paso 01</title><style>
    body{{font:14px Arial,sans-serif;max-width:900px;margin:38px auto;color:#203648;line-height:1.55}}
    h1,h2{{color:#10374B}} .header{{background:#10374B;color:white;padding:24px;border-radius:10px}}
    .header h1{{color:white;margin:0}} table{{border-collapse:collapse;width:100%;margin:14px 0 28px}}
    td,th{{padding:9px;border-bottom:1px solid #dde7eb;text-align:left;vertical-align:top}}
    th{{background:#eef6f7}} .note{{border-left:4px solid #0C989B;padding:10px;background:#f1f8f9}}
    @media print{{body{{margin:10mm}}}}</style></head><body>
    <div class="header"><h1>PMO FLYWHEEL CENS</h1>Cierre documentado · Paso 01 · Generación de conciencia</div>
    <p><b>Periodo:</b> {h(record['periodo'])} · <b>Responsable:</b> {h(record['responsable'])} · <b>Corte:</b> {h(record['creado_en'])}</p>
    <h2>Síntesis ejecutiva</h2><p>{h(record['sintesis'])}</p>
    <h2>Indicadores verificables</h2><table><tbody>{rows}</tbody></table>
    <p><b>Alcance temporal:</b> {h(r['alcance_temporal'])}</p>
    <h2>Autoevaluación metodológica CENS (adaptada)</h2><p>{h(ev_text)}</p>
    <table><thead><tr><th>Dimensión</th><th>Puntaje</th></tr></thead><tbody>{dimensions}</tbody></table>
    <h2>Evidencias por actividad PMI</h2><table><thead><tr><th>Actividad</th><th>Estado</th><th>Registros</th></tr></thead><tbody>{evidence}</tbody></table>
    <h2>Acciones de mejora al corte</h2><table><thead><tr><th>Dimensión</th><th>Acción</th><th>Estado</th></tr></thead><tbody>{actions}</tbody></table>
    <h2>Pendientes y decisiones</h2><p><b>Pendientes:</b> {h(record['pendientes'])}</p><p><b>Decisiones:</b> {h(record['decisiones'])}</p>
    <p><b>Paquete para Paso 02:</b> {h(record.get('transferencia_id') or 'No asociado')}</p>
    <div class="note">La generación de conciencia continúa durante el ciclo. Este informe no acredita impacto ni convierte antecedentes en necesidades validadas.</div>
    </body></html>'''.encode('utf-8')
