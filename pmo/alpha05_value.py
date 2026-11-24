"""Alpha05: vistas consultivas. Sin nuevas escrituras ni decisiones automáticas."""
from collections import defaultdict, Counter
from datetime import date
from math import isfinite
from .alpha04_operations import read_data
from . import step7, step9, step10


def month(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime('%Y-%m')
    except (ValueError, TypeError):
        return None


def performance(items, feedback):
    """Cohorte de tickets filtrada; ANS por evento completado, CSAT por fecha de respuesta."""
    real = [t for t in items if not t.get('origen_demo')]
    ids = {t['id'] for t in real}
    monthly = defaultdict(lambda: {'Recibidas':0, 'Entregadas':0, 'Base respuesta':0,
        'Cumple respuesta':0, 'Base resolución':0, 'Cumple resolución':0, 'CSAT valores':[]})
    for t in real:
        for field, name in [('creado_en','Recibidas'), ('terminado_en','Entregadas')]:
            if m := month(t.get(field)): monthly[m][name] += 1
        for kind, field, label in [('respuesta','primera_respuesta_en','respuesta'),('resolucion','terminado_en','resolución')]:
            if m := month(t.get(field)):
                r = step7.sla(t, kind)
                if r['evaluable']:
                    monthly[m]['Base '+label] += 1
                    monthly[m]['Cumple '+label] += int(r['estado']=='Cumplió')
    seen=set()
    for f in sorted(feedback, key=lambda x:(str(x.get('fecha') or ''),str(x.get('id') or '')), reverse=True):
        if f.get('ticket_id') not in ids or f['ticket_id'] in seen or not f.get('vigente',1): continue
        seen.add(f['ticket_id'])
        v=f.get('csat'); m=month(f.get('fecha'))
        if m and isinstance(v,(int,float)) and isfinite(v) and 1<=v<=5: monthly[m]['CSAT valores'].append(v)
    rows=[]
    for m,d in sorted(monthly.items()):
        cs=d.pop('CSAT valores'); d['Base CSAT']=len(cs); d['CSAT /5']=sum(cs)/len(cs) if cs else None
        for label in ('respuesta','resolución'):
            base=d['Base '+label];d['ANS '+label+' %']=100*d['Cumple '+label]/base if base else None
        rows.append({'Mes':m,**d})
    return rows


def maturity_rows(report):
    return [{'Código':x['servicio_ref'],'Servicio':x['name_es'],'Estado':x['estado'],
             'Actual':x['actual'] if x['estado']=='Evaluado' else None,
             'Meta':x['deseado'] if x['estado']=='Evaluado' else None,
             'Brecha pp':x['gap'] if x['estado']=='Evaluado' else None}
            for x in report['ratings']]


def maturity_comparison(before,after):
    if before['cycle']['id']==after['cycle']['id']:raise ValueError('Selecciona dos ciclos distintos.')
    if before['cycle']['es_demo'] or after['cycle']['es_demo']:raise ValueError('No se comparan ciclos demostrativos en la vista institucional.')
    old={r['Código']:r for r in maturity_rows(before)}
    rows=[]
    for r in maturity_rows(after):
        a=old.get(r['Código']); b=r['Actual']; av=a['Actual'] if a else None
        rows.append({'Código':r['Código'],'Servicio':r['Servicio'],'Antes':av,'Después':b,
                     'Cambio niveles':b-av if av is not None and b is not None else None,
                     'Estado anterior':a['Estado'] if a else 'Sin registro','Estado posterior':r['Estado']})
    return rows


def improvement_data(path=None):
    return read_data({
        'actions':'''SELECT a.*,c.nombre AS ciclo,d.fase,d.prioridad,d.codigo_publico,d.criterio_aceptacion
          FROM p8_actions a JOIN p8_cycles c ON c.id=a.ciclo_id LEFT JOIN p8_mejora_detalle d ON d.accion_id=a.id
          WHERE c.es_demo=0 ORDER BY a.fecha_meta,a.id''',
        'checks':'''SELECT v.*,CASE WHEN e.id IS NULL THEN 0 ELSE 1 END AS soporte_vigente
          FROM p8_mejora_verificaciones v JOIN p8_actions a ON a.id=v.accion_id JOIN p8_cycles c ON c.id=a.ciclo_id
          LEFT JOIN p8_mejora_soportes e ON e.id=v.evidencia_id AND e.accion_id=a.id
          WHERE c.es_demo=0 ORDER BY v.creado_en DESC,v.id DESC''',
        'origins':'''SELECT f.* FROM p8_mejora_fuentes f JOIN p8_actions a ON a.id=f.accion_id
          JOIN p8_cycles c ON c.id=a.ciclo_id WHERE c.es_demo=0''',
    },path)


def backlog(actions,checks,origins,today=None):
    today=today or date.today(); latest={}; source=Counter(x['accion_id'] for x in (origins or []))
    for x in sorted(checks or [],key=lambda r:(r['creado_en'],r['id']),reverse=True):latest.setdefault(x['accion_id'],x)
    out=[]
    for a in actions:
        v=latest.get(a['id']); phase=a.get('fase') or a['estado']
        try: overdue=date.fromisoformat(a['fecha_meta'])<today and phase not in ('Completada','Cancelada')
        except (TypeError,ValueError):overdue=None
        out.append({'ID':a['id'],'Código':a.get('codigo_publico') or 'Histórico','Ciclo':a['ciclo'],'Servicio ref.':a['servicio_ref'],
            'Iniciativa':a['titulo'],'Responsable':a['responsable'],'Fecha meta':a['fecha_meta'],'Fase':phase,
            'Vencida':overdue,'Hallazgos vinculados':source[a['id']] if origins is not None else None,
            'Última verificación':v['resultado'] if v else ('Sin registro' if checks is not None else 'Fuente no disponible'),
            'Soporte de última verificación':bool(v['soporte_vigente']) if v else None,
            'Valor observado':v['valor_observado'] if v else None,'Criterio':a.get('criterio_aceptacion')})
    return out


def benefit_data(path=None):
    return read_data({'benefits':'SELECT * FROM p9_beneficios WHERE es_demo=0 ORDER BY creado_en DESC,id',
      'measures':'''SELECT m.* FROM p9_mediciones m JOIN p9_beneficios b ON b.id=m.beneficio_id WHERE b.es_demo=0 ORDER BY m.fecha,m.creado_en,m.id''',
      'indicators':'''SELECT i.* FROM p9_indicadores_beneficio i JOIN p9_beneficios b ON b.id=i.beneficio_id WHERE b.es_demo=0'''},path)


def benefit_rows(data):
    if data['benefits'] is None or data['measures'] is None:return None
    latest={}; counts=Counter(); indicators={x['beneficio_id']:x for x in data['indicators'] or []}
    for m in sorted(data['measures'],key=lambda x:(x['fecha'],x['creado_en'],x['id'])):
        latest[m['beneficio_id']]=m;counts[m['beneficio_id']]+=1
    result=[]
    for b in data['benefits']:
        if b.get('es_demo'):continue
        m=latest.get(b['id']);p=step9.calc(b,m);v=bool(m and step9.is_verified(b,m))
        i=indicators.get(b['id'],{})
        result.append({'ID':b['id'],'Servicio ID':b['servicio_id'],'Servicio':b['servicio'],'Cliente':b['cliente'],'Dependencia':b['dependencia'],
            'Beneficio':b['beneficio'],'Indicador':b['indicador'],'Unidad':b['unidad'],'Línea base':b['linea_base'],'Meta':b['meta'],
            'Resultado':m['valor'] if m else None,'Fecha medición':m['fecha'] if m else None,'Mediciones':counts[b['id']],
            'Avance %':p['avance'] if p else None,'Meta observada':p['cumple_meta'] if p else None,
            'Situación':'Verificado' if v else 'Medido sin verificación vigente' if m else 'Sin medición',
            'Fecha validación':b['fecha_validacion'] if v else None,'Evidencia validación':b['evidencia_validacion'] if v else None,
            'Fuente medición':m['fuente'] if m else None,'Responsable':b['responsable'],'Fecha meta':b['fecha_meta'],
            'Objetivo del indicador':i.get('objetivo'),'Estado indicador':i.get('estado'),'Origen P3':b['origen_p3'], 'Impacto':b['tipo_impacto']})
    return result


def recognition_data(path=None):
    return read_data({'benefits':'SELECT * FROM p10_beneficios WHERE vigente=1 AND es_demo=0 ORDER BY id',
      'surveys':'SELECT * FROM p10_encuestas WHERE es_demo=0 ORDER BY fecha DESC,id',
      'stories':'SELECT * FROM p10_historias WHERE es_demo=0 ORDER BY fecha DESC,id',
      'config':'SELECT umbral FROM p10_config WHERE id=1'},path)


def recognition(data,local_rows,period='',group=''):
    if any(data[k] is None for k in ('benefits','surveys','stories','config')):return None
    selected=[s for s in data['surveys'] if not s.get('es_demo') and (not period or s['periodo']==period) and (not group or s['grupo']==group)]
    threshold=data['config'][0]['umbral'] if data['config'] else 7
    local={x['ID']:x for x in local_rows or []}; grouped=defaultdict(list); linked=defaultdict(list)
    for s in selected:
        grouped[s['grupo']].append(s)
        if s.get('beneficio_id') and s.get('reconocimiento') is not None:linked[s['beneficio_id']].append(s['reconocimiento'])
    benefits=[]
    for b in data['benefits']:
        if b.get('es_demo'):continue
        vals=linked.get(b['id'],[]); avg=sum(vals)/len(vals) if vals else None
        l=local.get(b['id']); current='Expediente externo · sin cotejo local'
        if b['origen']=='SQLite Paso 9':
            current='Fuente local no disponible' if local_rows is None else 'Revisar sincronización / validación' 
            if l and l['Situación']=='Verificado' and l['Fecha validación']==b['fecha_validacion'] and l['Evidencia validación']==b['evidencia'] and l['Resultado']==b['resultado_real'] and all(l[k]==b[v] for k,v in [('Servicio','servicio'),('Cliente','cliente'),('Beneficio','beneficio')]):
                current='Coincide con verificación local vigente'
        benefits.append({'ID':b['id'],'Servicio':b['servicio'],'Cliente':b['cliente'],'Beneficio':b['beneficio'],
            'Origen':b['origen'],'Verificación':current,'Respuestas vinculadas':len(vals),'Reconocimiento /10':avg,
            'Percepción':'Sin respuesta' if avg is None else 'Alcanza umbral' if avg>=threshold else 'Por debajo del umbral'})
    lookup={b['ID']:b for b in benefits}
    stories=[]
    for s in data['stories']:
        if s.get('es_demo') or (group and s['grupo']!=group):continue
        b=lookup.get(s['beneficio_id']); stories.append({'Título':s['titulo'],'Fecha':s['fecha'],'Grupo registrado':s['grupo'],
            'Estado registrado':s['estado'],'Evidencia':bool(s['evidencia']),'Autorización':bool(s['autorizacion']),
            'Estado del vínculo':b['Verificación'] if b else 'Sin beneficio vigente vinculado'})
    return {'nps':step10.nps(selected),'threshold':threshold,'benefits':benefits,'stories':stories,
            'groups':[{'Grupo registrado':g,'Respuestas':len(ss),'NPS':step10.nps(ss)['puntaje'],
                       'Satisfacción /10':sum(x['satisfaccion'] for x in ss)/len(ss)} for g,ss in sorted(grouped.items())]}


def sponsor_html(local_rows, report, period='', group='', generated=None):
    """Informe agregado de consulta actual; no certifica ni congela un corte."""
    from html import escape
    from datetime import datetime, timezone
    def e(v):return escape(str(v if v is not None else 'No disponible'))
    def display_number(v):return '—' if v is None else f'{v:.1f}'
    generated=generated or datetime.now(timezone.utc).isoformat(timespec='seconds')
    n=report['nps'];bs=report['benefits']
    items=[('Compromisos Paso 09',len(local_rows) if local_rows is not None else None),
           ('Medidos Paso 09',sum(x['Mediciones']>0 for x in local_rows) if local_rows is not None else None),
           ('Verificados Paso 09',sum(x['Situación']=='Verificado' for x in local_rows) if local_rows is not None else None),
           ('Beneficios importados vigentes Paso 10',len(bs)),('Respuestas no demostrativas',n['total']),
           ('NPS',display_number(n['puntaje'])),('Importaciones locales que requieren revisión',sum(x['Verificación']=='Revisar sincronización / validación' for x in bs)),
           ('Beneficios importados sin respuesta en la selección',sum(x['Respuestas vinculadas']==0 for x in bs))]
    cells=''.join(f'<tr><th>{e(k)}</th><td>{e(v)}</td></tr>' for k,v in items)
    groups=''.join('<tr>'+''.join(f'<td>{e(v)}</td>' for v in [r['Grupo registrado'],r['Respuestas'],display_number(r['NPS']),display_number(r['Satisfacción /10'])])+'</tr>' for r in report['groups'])
    return f'''<!doctype html><html lang="es"><meta charset="utf-8"><title>CENS · Lectura ejecutiva del valor</title><style>body{{font:15px Arial,sans-serif;color:#183b4b;max-width:900px;margin:40px auto;padding:20px}}h1{{color:#103b4c}}table{{width:100%;border-collapse:collapse;margin:20px 0}}th,td{{text-align:left;border-bottom:1px solid #d9e4e8;padding:10px}}th{{background:#edf5f6}}small{{color:#536d77}}</style><h1>PMO FLYWHEEL CENS · Lectura ejecutiva</h1><p>Generado UTC: {e(generated)} · Alpha 05</p><p>Encuesta: {e(period or 'Todos los periodos')} · Grupo: {e(group or 'Todos los grupos')}</p><p>Los datos del Paso 09 y los beneficios importados del Paso 10 corresponden al estado vigente general de la base. Las respuestas se limitan al filtro. Se excluyen registros demostrativos. No es un corte histórico congelado ni una certificación del valor.</p><table>{cells}</table><h2>Percepción por grupo registrado</h2><table><tr><th>Grupo</th><th>Respuestas</th><th>NPS</th><th>Satisfacción /10</th></tr>{groups or '<tr><td colspan="4">Sin respuestas para la selección</td></tr>'}</table><p>Fuentes: SQLite, p9_beneficios, p9_mediciones, p10_beneficios, p10_encuestas. NPS de −100 a +100; sin respuestas no se calcula. La percepción no sustituye la validación documental ni demuestra causalidad. El informe no atribuye valor económico.</p><small>Consulta interna · revisar antes de divulgar.</small></html>'''
