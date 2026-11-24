"""V0.30: tablero ejecutivo de concienciación, solo lectura.

Consolida registros ya existentes, sin modificar esquemas ni almacenar copias.
Alcance: cliente activo con asistencia confirmada a evento REALIZADO,
interacción registrada, consulta formal o consulta de biblioteca atribuida.
No se considera una descarga anónima ni una actividad programada como alcance.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path
import csv
from io import StringIO

from .storage import connect

DIMENSIONS = [
    ('familiaridad', 'Familiaridad'), ('proposito', 'Propósito'),
    ('servicios', 'Servicios'), ('utilidad', 'Utilidad percibida'),
    ('interes', 'Interés futuro'),
]


def _in_period(value, start='', end=''):
    day = str(value or '')[:10]
    if not day or len(day) != 10:
        return False
    return (not start or day >= start) and (not end or day <= end)


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args)]


def snapshot(path: Path | None = None, *, dependency: str = '', team: str = '',
             start: str = '', end: str = '') -> dict:
    """Devuelve indicadores rastreables sin escribir en SQLite.

    Los filtros de fecha acotan ACTIVIDADES, no la población activa del directorio.
    Las métricas de conocimiento usan las cinco respuestas del cuestionario de
    sensibilización, NO la autoevaluación metodológica de 25 criterios.
    """
    if start: date.fromisoformat(start)
    if end: date.fromisoformat(end)
    if start and end and start > end:
        raise ValueError('La fecha inicial debe ser anterior o igual a la final.')

    with closing(connect(path)) as con:
        clients = _rows(con, '''SELECT c.id,c.codigo,c.nombre,c.equipo_trabajo,c.cargo,
                   c.influencia,c.interes,c.segmento,d.nombre AS dependencia
                   FROM pmo_clientes c JOIN pmo_dependencias d ON d.id=c.dependencia_id
                   WHERE c.activo=1 ORDER BY d.nombre,c.nombre''')
        population = [c for c in clients if (not dependency or c['dependencia']==dependency)
                      and (not team or c['equipo_trabajo']==team)]
        ids = {c['id'] for c in population}
        by_id = {c['id']: c for c in population}

        ev_rows = _rows(con, '''SELECT a.cliente_id,e.id AS evento_id,e.fecha
             FROM p1_asistencias a JOIN p1_eventos e ON e.id=a.evento_id
             WHERE a.asistio=1 AND e.estado='Realizado' ''')
        interactions = _rows(con, 'SELECT cliente_id,fecha,motivo,insumo_paso2 FROM p1_interacciones')
        consultations = _rows(con, 'SELECT cliente_id,creado_en,estado FROM p1_consultas')
        resource_interactions = _rows(con, '''SELECT cliente_id,creado_en,accion
             FROM p1_recurso_interacciones WHERE cliente_id IS NOT NULL''')
        surveys = _rows(con, '''SELECT cliente_id,evento_id,fase,familiaridad,
             proposito,servicios,utilidad,interes,creado_en,id FROM p1_encuestas
             ORDER BY creado_en,id''')
        commitments = _rows(con, 'SELECT cliente_id,estado,vence_en,creado_en,cerrado_en FROM p1_compromisos')
        activities = _rows(con, "SELECT id,fecha,estado FROM p1_eventos")
        published = _rows(con, "SELECT id,tipo,estado,creado_en FROM p1_recursos")
        assessment = _rows(con, """SELECT puntaje,clasificacion,periodo,finalizada_en FROM p1_autoevaluaciones
                                  WHERE estado='Finalizada' ORDER BY finalizada_en DESC,id DESC""")

    attendance = [r for r in ev_rows if r['cliente_id'] in ids and _in_period(r['fecha'], start, end)]
    ints = [r for r in interactions if r['cliente_id'] in ids and _in_period(r['fecha'],start,end)]
    tickets = [r for r in consultations if r['cliente_id'] in ids and _in_period(r['creado_en'],start,end)]
    resource_visits = [r for r in resource_interactions if r['cliente_id'] in ids
                       and r['accion']=='Consulta registrada' and _in_period(r['creado_en'],start,end)]
    survey_rows = [r for r in surveys if r['cliente_id'] in ids and _in_period(r['creado_en'],start,end)]
    commitments_period = [r for r in commitments if r['cliente_id'] in ids and _in_period(r['creado_en'],start,end)]
    # Los eventos y materiales no tienen dependencia individual; no atribuirlos a un área específica.
    scope_all = not dependency and not team
    realized = sum(r['estado']=='Realizado' and _in_period(r['fecha'],start,end) for r in activities) if scope_all else len({r['evento_id'] for r in attendance})
    publications = sum(r['tipo']!='Servicio' and r['estado']=='Publicado' and _in_period(r['creado_en'],start,end) for r in published) if scope_all else None

    attended_ids = {r['cliente_id'] for r in attendance}
    contacted_ids = {r['cliente_id'] for r in ints} | {r['cliente_id'] for r in tickets}
    visited_ids = {r['cliente_id'] for r in resource_visits}
    reached_ids = attended_ids | contacted_ids | visited_ids
    pending = [r for r in commitments_period if r['estado'] in ('Pendiente','En curso')]
    overdue = sum(bool(r['vence_en'] and r['vence_en'] < date.today().isoformat()) for r in pending)

    dep_groups = defaultdict(list)
    team_groups = defaultdict(list)
    for c in population:
        dep_groups[c['dependencia']].append(c['id'])
        team_groups[c['equipo_trabajo'] or 'Sin equipo registrado'].append(c['id'])
    def _coverage(groups, label):
        result=[]
        for name, people in sorted(groups.items(), key=lambda x:x[0].casefold()):
            hits=len(set(people)&reached_ids)
            result.append({label:name,'Objetivo':len(people),'Alcanzados':hits,
                           'Pendientes':len(people)-hits,'Cobertura (%)':round(100*hits/len(people),1)})
        return result
    dep_coverage = _coverage(dep_groups,'Dependencia')
    team_coverage = _coverage(team_groups,'Equipo de trabajo')

    # Pareamiento por ID del cliente y contexto de evento (None = sin evento).
    # La última medición de cada fase prevalece para evitar doble conteo de encuestas.
    pairs_data={}
    for r in survey_rows:
        pairs_data.setdefault((r['cliente_id'],r['evento_id']),{})[r['fase']]=r
    comparable=[(v['Antes'],v['Después']) for v in pairs_data.values()
                if 'Antes' in v and 'Después' in v]
    post=[r for r in survey_rows if r['fase']=='Después']
    knowledge = []
    for key,title in DIMENSIONS:
        before=[a[key] for a,b in comparable]
        after=[b[key] for a,b in comparable]
        knowledge.append({'Dimensión':title,
             'Antes':round(sum(before)/len(before),2) if before else None,
             'Después':round(sum(after)/len(after),2) if after else None,
             'Cambio':round(sum(after)/len(after)-sum(before)/len(before),2) if before else None})
    familiarity=sum(r['familiaridad'] for r in post)/len(post) if post else None
    # La gráfica mensual muestra personas distintas de cada MES (no es acumulativa).
    months=defaultdict(lambda:dict(Asistencias=0,Interacciones=0,Consultas=0,Portal=0,clients=set()))
    for series, rows, key in [
        ('Asistencias',attendance,'fecha'),('Interacciones',ints,'fecha'),
        ('Consultas',tickets,'creado_en'),('Portal',resource_visits,'creado_en')]:
        for r in rows:
            m=r[key][:7];months[m][series]+=1;months[m]['clients'].add(r['cliente_id'])
    monthly=[{'Mes':m,'Clientes únicos del mes':len(v['clients']),
              **{s:v[s] for s in ('Asistencias','Interacciones','Consultas','Portal')}}
             for m,v in sorted(months.items())][-12:]

    # Matriz descriptiva, no puntaje ni certificado de cumplimiento.
    characterized=sum(bool(c['segmento'] and c['segmento']!='Sin evaluar') or
                      (c['influencia'] or '').casefold() in ('alta','media','baja') or
                      (c['interes'] or '').casefold() in ('alto','medio','bajo')
                      for c in population)
    completed=sum(r['estado']=='Cumplido' for r in commitments_period)
    prelim=sum(r['insumo_paso2']==1 for r in ints)
    matrix=[
      {'Actividad PMI':'Identificar clientes','Evidencia':f'{len(population)} clientes activos; {characterized} con caracterización parcial',
       'Estado':'Con registros' if characterized else ('En desarrollo' if population else 'Sin registros'),
       'Observación':'El directorio por sí solo no prueba una segmentación completa.'},
      {'Actividad PMI':'Puntos de contacto regulares','Evidencia':f'{len(ints)} interacciones; {len(tickets)} consultas',
       'Estado':'Con registros' if (ints or tickets) else 'Sin registros',
       'Observación':'La regularidad requiere revisar continuidad y canales a lo largo del tiempo.'},
      {'Actividad PMI':'Educar sobre el valor','Evidencia':f'{realized} eventos realizados; '+(f'{publications} recursos publicados' if publications is not None else 'recursos sin atribución por dependencia'),
       'Estado':'Con registros' if realized or (publications or 0)>0 else 'Sin registros',
       'Observación':'La realización de actividades no demuestra aprendizaje.'},
      {'Actividad PMI':'Medir la efectividad','Evidencia':f'{len(survey_rows)} encuestas; {len(comparable)} pares comparables',
       'Estado':'Con registros comparables' if comparable else ('En desarrollo' if survey_rows else 'Sin registros'),
       'Observación':'Las comparaciones usan cliente y evento; muestras y fecha deben revisarse.'},
      {'Actividad PMI':'Mejora continua','Evidencia':f'{completed} compromisos cumplidos; {prelim} antecedentes Paso 02',
       'Estado':'En desarrollo' if completed or prelim else 'Sin registros',
       'Observación':'Los compromisos no acreditan por sí solos mejoras de sensibilización.'},
    ]
    assessment_current=next((r for r in assessment if _in_period(r['finalizada_en'],start,end)),None)
    return {
        'period':(start,end), 'dependency':dependency,'team':team,
        'active':len(population),'reached':len(reached_ids),
        'coverage':round(100*len(reached_ids)/len(population),1) if population else None,
        'attendance_unique':len(attended_ids),'attendance_total':len(attendance),
        'contacts_unique':len(contacted_ids), 'interactions':len(ints),
        'consultations':len(tickets), 'tickets_pending':sum(r['estado'] not in ('Respondida','Cerrada') for r in tickets),
        'resource_clients':len(visited_ids),'resource_visits':len(resource_visits),
        'publications':publications, 'events_realized':realized,
        'commitments_pending':len(pending),'commitments_overdue':overdue,
        'commitments_completed':completed,'needs_preliminary':prelim,
        'familiarity':round(familiarity,2) if familiarity is not None else None,
        'survey_after_count':len(post),'survey_after_clients':len({r['cliente_id'] for r in post}),
        'surveys_total':len(survey_rows),'paired_count':len(comparable),
        'paired_clients':len({a['cliente_id'] for a,b in comparable}),
        'knowledge':knowledge,'department_coverage':dep_coverage,
        'team_coverage':team_coverage,'monthly':monthly,'evidence':matrix,
        'assessment':assessment_current,
        'sources':{'attendance':len(attendance),'interactions':len(ints),'consultations':len(tickets),'portal':len(resource_visits)},
    }


def coverage_csv(data: dict) -> bytes:
    out=StringIO(); w=csv.DictWriter(out,fieldnames=('Dependencia','Objetivo','Alcanzados','Pendientes','Cobertura (%)'))
    w.writeheader();w.writerows(data['department_coverage'])
    return ('\ufeff'+out.getvalue()).encode('utf-8')


def executive_report(data: dict) -> bytes:
    """Informe descargable Markdown: producto separado de la medición de beneficios."""
    start,end=data['period']
    scope=f"{start or 'Inicio del ciclo'} a {end or 'Fecha actual'}"
    pct='No calculable' if data['coverage'] is None else f"{data['coverage']:.0f}%"
    assess=data['assessment']
    lines=[
      '# Informe ejecutivo — Generación de conciencia · Paso 01',
      f'**Periodo:** {scope}',
      f"**Dependencia:** {data['dependency'] or 'Todas'} | **Equipo:** {data['team'] or 'Todos'}",
      '', '## Alcance y actividad',
      f"- Clientes activos en población objetivo: {data['active']}",
      f"- Clientes únicos alcanzados: {data['reached']} ({pct})",
      f"- Asistentes únicos: {data['attendance_unique']}; asistencias verificadas: {data['attendance_total']}",
      f"- Interacciones: {data['interactions']}; consultas: {data['consultations']}",
      f"- Consultas registradas al portal: {data['resource_visits']}; clientes identificados: {data['resource_clients']}",
      f"- Compromisos pendientes: {data['commitments_pending']}; vencidos: {data['commitments_overdue']}",
      '', '## Comprensión y valor',
      f"- Encuestas posteriores: {data['survey_after_count']} de {data['survey_after_clients']} clientes distintos",
      f"- Pares antes/después comparables: {data['paired_count']} ({data['paired_clients']} clientes distintos)",
      f"- Familiaridad posterior: {data['familiarity'] if data['familiarity'] is not None else 'Sin medición'} / 5",
      f"- Autoevaluación finalizada del Paso 01: {str(assess['puntaje'])+'/125' if assess and assess['puntaje'] is not None else 'Sin evaluación finalizada en el periodo'}",
      '', '## Evidencias metodológicas'
    ]
    for r in data['evidence']:
        lines.append(f"- **{r['Actividad PMI']}** — {r['Estado']}. {r['Evidencia']}. {r['Observación']}")
    lines += [
      '', '## Criterio de medición',
      'Alcance = unión de clientes activos con asistencia confirmada a evento realizado, contacto documentado, consulta formal o consulta del portal vinculada por ID. Una persona se cuenta una sola vez en el periodo.',
      'El alcance no equivale a aprendizaje, satisfacción ni beneficio demostrado. Las descargas sin identificación del cliente no se contabilizan como clientes alcanzados.',
      'Las actividades metodológicas no se declaran cumplidas automáticamente; la matriz describe registros y brechas para revisión profesional.',
      'Los indicadores no atribuibles a una dependencia se omiten del filtro organizacional en lugar de asignarlos arbitrariamente.',
    ]
    return ('\n'.join(lines)+'\n').encode('utf-8')


def executive_html(data: dict) -> bytes:
    """Informe ejecutivo HTML autocontenido listo para impresión o guardado como PDF.

    El HTML es documento de salida, no forma parte de la interfaz ni ejecuta JS.
    """
    from html import escape
    def clean(value):return escape(str(value if value is not None else '—'))
    start,end=data['period']
    period=f"{start or 'Inicio del ciclo'} — {end or 'Sin fecha de fin'}"
    coverage='No calculable' if data['coverage'] is None else f"{data['coverage']:.0f}%"
    ass=data['assessment']
    auto=(f"{ass['puntaje']} / 125" if ass and ass['puntaje'] is not None
          else 'Sin evaluación finalizada en el periodo')
    boxes=[
       ('Clientes activos',data['active'],'Población objetivo'),
       ('Clientes alcanzados',data['reached'],f'Cobertura: {coverage}'),
       ('Interacciones',data['interactions'],'Contactos registrados'),
       ('Familiaridad PMO',f"{data['familiarity']:.1f}/5" if data['familiarity'] is not None else 'Sin medición',
        f"{data['survey_after_clients']} clientes con encuesta posterior"),
    ]
    cards=''.join(f'<div class="kpi"><div class="klabel">{clean(n)}</div><div class="kvalue">{clean(v)}</div><div class="kdesc">{clean(d)}</div></div>' for n,v,d in boxes)
    by_dep=''.join(f'<tr><td>{clean(r["Dependencia"])}</td><td>{r["Objetivo"]}</td><td>{r["Alcanzados"]}</td><td>{r["Pendientes"]}</td><td>{r["Cobertura (%)"]:.0f}%</td></tr>' for r in data['department_coverage'])
    matrix=''.join('<tr><td>'+clean(r['Actividad PMI'])+'</td><td>'+clean(r['Estado'])+'</td><td>'+clean(r['Evidencia'])+'</td></tr>' for r in data['evidence'])
    content=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>PMO CENS · Informe Paso 01</title>
    <style>
    @page{{size:A4;margin:16mm}}
    body{{font-family:Arial,Helvetica,sans-serif;color:#203748;margin:0;background:white;font-size:11px;line-height:1.55}}
    .top{{background:#10374B;color:white;padding:24px 30px;border-radius:12px}}
    .tag{{color:#8CE0D7;font-size:11px;font-weight:750;letter-spacing:1.3px}}
    h1{{font-size:23px;margin:8px 0 7px;color:white}}
    h2{{font-size:15px;margin:25px 0 8px;color:#10374B;border-bottom:1px solid #dbe6e9;padding-bottom:6px}}
    .sub{{color:#CCDFE8}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0}}
    .kpi{{border:1px solid #dbe7eb;border-radius:10px;padding:12px;break-inside:avoid}}
    .klabel{{color:#638095;font-size:10px;font-weight:bold}}
    .kvalue{{font-size:20px;color:#10374B;font-weight:800;margin-top:4px}}
    .kdesc{{font-size:10px;color:#748B96}}
    table{{border-collapse:collapse;width:100%;font-size:10px;margin:9px 0}}
    th{{text-align:left;background:#E8F4F4;color:#10374B}}
    td,th{{border:1px solid #dbe5ea;padding:7px;vertical-align:top}}
    .note{{background:#EAF6F6;border-left:3px solid #0C989B;padding:10px 12px;margin-top:13px}}
    .foot{{color:#708394;font-size:10px;margin-top:26px}}
    @media print{{.top,.kpi,.note{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}}}
    </style></head><body>
    <div class="top"><div class="tag">PMO FLYWHEEL CENS · CICLO 01</div>
    <h1>Tablero ejecutivo de concienciación</h1><div class="sub">Paso 01 · Generación de conciencia</div></div>
    <p><b>Periodo:</b> {clean(period)} &nbsp; <b>Dependencia:</b> {clean(data['dependency'] or 'Todas')}
    &nbsp; <b>Equipo:</b> {clean(data['team'] or 'Todos')}</p>
    <div class="cards">{cards}</div>
    <h2>Participación y seguimiento</h2>
    <p><b>Asistentes únicos:</b> {data['attendance_unique']} &nbsp; <b>Asistencias:</b> {data['attendance_total']}
    &nbsp; <b>Consultas:</b> {data['consultations']} &nbsp; <b>Consultas de portal identificadas:</b> {data['resource_visits']}</p>
    <p><b>Compromisos pendientes:</b> {data['commitments_pending']} &nbsp; <b>Vencidos:</b> {data['commitments_overdue']}
    &nbsp; <b>Antecedentes potenciales para Paso 02:</b> {data['needs_preliminary']}</p>
    <h2>Cobertura por dependencia</h2>
    <table><thead><tr><th>Dependencia</th><th>Objetivo</th><th>Alcanzados</th><th>Pendientes</th><th>Cobertura</th></tr></thead><tbody>{by_dep or '<tr><td colspan="5">Sin población activa para el filtro</td></tr>'}</tbody></table>
    <h2>Aprendizaje y medición</h2>
    <p><b>Encuestas posteriores:</b> {data['survey_after_count']} ({data['survey_after_clients']} clientes).
    <b>Pares comparables:</b> {data['paired_count']} de {data['paired_clients']} clientes.
    <b>Autoevaluación:</b> {clean(auto)}.</p>
    <h2>Evidencias de las cinco actividades metodológicas</h2>
    <table><thead><tr><th>Actividad</th><th>Estado descriptivo</th><th>Registros disponibles</th></tr></thead><tbody>{matrix}</tbody></table>
    <div class="note"><b>Criterio:</b> el alcance es la unión de clientes identificados por ID en eventos realizados,
    interacciones, consultas formales y consultas al portal. Se cuenta cada cliente una vez.
    El alcance no demuestra aprendizaje ni beneficio; una campaña no es requisito independiente de cumplimiento.</div>
    <div class="foot">Informe local generado desde la base SQLite de PMO CENS. Las cifras corresponden exclusivamente a los filtros indicados.
    Los estados de evidencia no son calificaciones oficiales del PMI ni reemplazan una evaluación metodológica.</div>
    </body></html>'''
    return content.encode('utf-8')
