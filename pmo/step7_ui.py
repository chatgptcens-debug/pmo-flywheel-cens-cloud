"""Paso 07 · Tablero único y trazable de monitoreo de servicios PMO CENS.

Consulta automáticamente Paso 06 al abrir una vista; nunca cambia sus tickets.
Los cortes congelados se guardan únicamente por acción explícita del usuario.
"""
from __future__ import annotations
import collections
import html
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from .staff_picker import staff_picker
from . import step7 as s
from .ui import kpi

NAV=list(s.MODULES)
CSS=Path(__file__).parent/'assets'/'step7_ux.css'
PAGES={
 NAV[0]:('MÓDULO 01','Tablero integral de desempeño','Indicadores de prestación de servicios desde la operación, con fuentes y denominadores.'),
 NAV[1]:('MÓDULO 02','Control de ANS y alertas','El mismo motor del Paso 06 calcula tiempos hábiles, calendario, alertas y desviaciones.'),
 NAV[2]:('MÓDULO 03','Informes y comunicación del desempeño','Cortes verificables y reproducibles que no cambian si un ticket se actualiza después.'),
 NAV[3]:('MÓDULO 04','Satisfacción y voz del cliente','Conformidad, CSAT, NPS y comentarios; sin convertir la escala histórica 1–10.'),
}


def apply_step7_theme():
    st.markdown('<style>'+CSS.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)


def e(value):return html.escape(str(value if value is not None else ''))
def jb(data):return json.dumps(data,ensure_ascii=False,indent=2,default=str).encode('utf-8')
def fmt(value,suffix='',decimals=1):
    if value is None:return '—'
    return f'{value:.{decimals}f}'.replace('.',',')+suffix

def kpis(values):
    for col,(label,value,details) in zip(st.columns(len(values)),values):
        with col:kpi(label,str(value),details,'chart-no-axes-column')

def heading(part,title,subtitle):
    st.markdown(f'<div class="pmo-eyebrow">PASO 07 · {e(part)}</div>'
                f'<div class="pmo-title">{e(title)}</div>'
                f'<div class="pmo-subtitle">{e(subtitle)}</div>',unsafe_allow_html=True)

def action(fn,message):
    try:
        r=fn();st.success(message);return r if r is not None else True
    except (s.ValidationError,ValueError,KeyError,json.JSONDecodeError) as exc:
        st.error(str(exc));return None


def imports_panel():
    with st.expander('Fuentes, importaciones de respaldo y recuperación',expanded=False):
        st.caption('La sincronización operativa es automática. JSON queda disponible para recuperar fuentes o consultar un expediente externo; el Paso 06 permanece intacto.')
        demo=st.checkbox('Mostrar registros de laboratorio (señalados como simulación)',key='p7_include_demo')
        a,b=st.columns(2)
        with a:
            if st.button('Verificar cambios del Paso 06',key='p7_manual_sync'):
                if action(lambda:s.sync_live(include_demo=demo),'Fuente operativa verificada'):st.rerun()
            uploaded=st.file_uploader('Importar expediente histórico JSON Paso 06',type=['json'],key='p7_source_json')
            if uploaded and st.button('Validar expediente histórico',key='p7_load_source'):
                if action(lambda:s.import_step6_json(json.loads(uploaded.getvalue()),include_demo=demo),'Expediente importado'):st.rerun()
        with b:
            if st.button('Consultar catálogo e indicadores del Paso 04',key='p7_catalog_sync'):
                if action(s.import_catalog_direct,'Referencias de indicadores actualizadas'):st.rerun()
            u=st.file_uploader('O importar catálogo JSON',type=['json'],key='p7_catalog_json')
            if u and st.button('Cargar catálogo',key='p7_import_p4'):
                if action(lambda:s.import_catalog_json(json.loads(u.getvalue())),'Catálogo importado'):st.rerun()
        with st.expander('Respaldo y restauración'):
            st.download_button('Descargar respaldo Paso 07',jb(s.backup()),file_name='PMO_CENS_PASO07_RESPALDO.json',mime='application/json')
            upload=st.file_uploader('Seleccionar respaldo anterior',type=['json'],key='p7_restore_json')
            approved=st.checkbox('Confirmo que reemplazaré los registros del Paso 07, nunca los del Paso 06',key='p7_confirm_restore')
            if upload and st.button('Restaurar respaldo',disabled=not approved):
                if action(lambda:s.restore(json.loads(upload.getvalue()),confirmed=True),'Paso 07 restaurado'):st.rerun()
        if s.imports():
            st.dataframe(pd.DataFrame(s.imports()[:12])[['origen','fecha','creados','actualizados','excluidos']],hide_index=True,use_container_width=True)


def source_status(sync_result):
    a,b=st.columns([2,1])
    with a:
        st.caption('**Origen operativo:** SQLite compartida · Paso 06. Los datos reales no se mezclan con simulaciones por defecto.')
    with b:
        n=sync_result.get('registros_origen',0)
        st.caption(f'**En origen:** {n} tickets · ' + ('Sin cambios nuevos' if sync_result.get('sin_cambios') else 'Actualizado'))


def filters():
    all_=s.ticket_list(include_demo=bool(st.session_state.get('p7_include_demo',False)))
    services=sorted({(x['servicio_id'],x['servicio_nombre']) for x in all_})
    areas=sorted({x['dependencia'] for x in all_ if x.get('dependencia')})
    owners=sorted({x['responsable'] for x in all_ if x.get('responsable')})
    with st.container(border=True):
        st.caption('Filtros comunes a todos los módulos operativos del Paso 07')
        a,b,c,d=st.columns([2.3,1.6,1.4,1.4])
        with a:query=st.text_input('Buscar ticket, cliente o servicio',placeholder='Código, cliente, servicio…',key='p7_filter_q')
        with b:
            service=st.selectbox('Servicio',['']+[x[0] for x in services],key='p7_filter_s',
                   format_func=lambda v:'Todos' if not v else next((n for k,n in services if k==v),v))
        with c:dep=st.selectbox('Dependencia',['',*areas],key='p7_filter_d',format_func=lambda v:v or 'Todas')
        with d:owner=st.selectbox('Responsable',['',*owners],key='p7_filter_o',format_func=lambda v:v or 'Todos')
        c1,c2,c3=st.columns([1.5,1,1])
        modes={'Creación':'creado_en','Primera respuesta':'primera_respuesta_en','Entrega':'terminado_en','Cierre':'cerrado_en'}
        with c1:period=st.selectbox('Criterio de periodo',list(modes),key='p7_filter_date_kind')
        with c2:from_=st.date_input('Desde',value=None,key='p7_filter_from', format='YYYY/MM/DD')
        with c3:to_=st.date_input('Hasta',value=None,key='p7_filter_to', format='YYYY/MM/DD')
    opts=dict(query=query,service=service,area=dep,owner=owner,
              date_from=str(from_) if from_ else '',date_to=str(to_) if to_ else '',
              date_field=modes[period],include_demo=bool(st.session_state.get('p7_include_demo',False)))
    st.session_state['p7_filter_snapshot']={**opts,'criterio_fecha':modes[period],
                                            'desde':opts['date_from'],'hasta':opts['date_to']}
    try:return s.ticket_list(**opts)
    except s.ValidationError as exc:st.error(str(exc));return []


def empty():
    st.info('No hay solicitudes para esta selección. Comprueba el periodo y los filtros. Si el Paso 06 no contiene tickets reales, no se generan datos de ejemplo.')


def progress_rows(data):
    if not data:return st.caption('Sin registros en esta selección.')
    peak=max([v for _,v in data]+[1])
    for label,value in data:
        a,b,c=st.columns([2.3,5.5,1])
        with a:st.caption(label)
        with b:st.progress(min(1,max(0,value)/peak))
        with c:st.caption(str(value))


def dashboard(items):
    if not items:return empty()
    if any(t.get('origen_demo') for t in items):st.warning('Incluye registros ficticios de laboratorio: no se consideran resultados institucionales.')
    from .alpha05_value_ui import render_performance
    render_performance(items)
    m=s.stats(items);f=s.client_feedback(items);q=s.quality_summary(items)
    kpis([('Servicios monitoreados',len({x['servicio_id'] for x in items}),f'{m["recibidas"]} solicitudes'),
          ('ANS de resolución',fmt(m['ans_resolucion'],'%',0),f'{m["cumplen_resolucion"]}/{m["base_resolucion"]} evaluables'),
          ('CSAT',fmt(f['csat'],'/5'),f'{f["base_csat"]} respuestas válidas'),
          ('Casos con riesgo ANS',len(m['vencidos'])+len(m['riesgo']),'Abiertos vencidos o en riesgo')])
    a,b=st.columns([1.4,1])
    with a:
        with st.container(border=True):
            st.subheader('Evolución de la demanda y entregas')
            months=sorted({str(t[k])[:7] for t in items for k in ('creado_en','terminado_en') if t.get(k)})
            frame=pd.DataFrame([{'Mes':x,'Recibidas':sum(str(t['creado_en']).startswith(x) for t in items),
                          'Entregadas':sum(str(t.get('terminado_en') or '').startswith(x) for t in items)} for x in months]).set_index('Mes')
            st.line_chart(frame)
            st.caption('Los conteos utilizan el evento correspondiente; no se atribuyen todas las entregas al mes de creación.')
    with b:
        with st.container(border=True):
            st.subheader('Estado y calidad del registro')
            progress_rows([('Recibidas',m['recibidas']),('Entregadas',m['atendidas']),
                           ('Finalizadas',m['finalizadas']),('Abiertas',m['abiertas'])])
            st.caption(f'ANS respuesta: {m["cumplen_respuesta"]}/{m["base_respuesta"]} evaluables')
            st.caption(f'Sin ANS de resolución: {q["sin_ans_resolucion"]} · Sin responsable: {q["sin_responsable"]}')
    a,b=st.columns([1.4,1])
    with a:
        with st.container(border=True):
            st.subheader('Desempeño por servicio')
            compare=s.by_service(items)
            st.dataframe(pd.DataFrame([{'Servicio':v['servicio'],'Solicitudes':v['recibidas'],
              'Finalizadas':v['finalizadas'],'ANS respuesta':f'{v["cumplen_respuesta"]}/{v["base_respuesta"]}',
              'ANS resolución':f'{v["cumplen_resolucion"]}/{v["base_resolucion"]}',
              'En riesgo':len(v['riesgo']),'Vencidas':len(v['vencidos'])} for v in compare]),hide_index=True,use_container_width=True)
    with b:
        with st.container(border=True):
            st.subheader('Plan de monitoreo')
            ids={t['servicio_id']:t['servicio_nombre'] for t in items}
            selected=st.selectbox('Servicio',list(ids),format_func=lambda key:ids[key],key='p7_monitor_service')
            old=next((x for x in s.monitoring() if x['servicio_id']==selected),{})
            with st.form('p7_monitor_form'):
                responsible=staff_picker('Responsable de revisión',value=old.get('responsable',''))
                kinds=['Diaria','Semanal','Mensual','Trimestral']
                cadence=st.selectbox('Periodicidad',kinds,index=kinds.index(old.get('frecuencia','Mensual')))
                source=st.text_input('Fuente de información',value=old.get('fuente','Paso 06 · SQLite'))
                if st.form_submit_button('Guardar configuración'):
                    action(lambda:s.save_monitor(selected,responsible,cadence,source),'Plan de monitoreo guardado')
    with st.expander('Indicadores de Paso 04 · definiciones y mediciones por periodo',expanded=False):
        measures=s.metric_measurements(service_ids={x['servicio_id'] for x in items})
        if measures:
            st.dataframe(pd.DataFrame([{'Indicador':r['nombre'],'Periodo':r['periodo'],
              'Resultado':r['resultado'],'Unidad':r['unidad'],'Semáforo':r['rag'],
              'Fuente':r['evidencia_url'],'Versión':r['revision']} for r in measures]),
              hide_index=True,use_container_width=True)
            st.caption('Se muestra la última revisión registrada por métrica y periodo, sin alterar la medición original.')
        else:
            st.caption('Sin mediciones reales asociadas a estos servicios y periodos.')
        refs=s.reference_metrics()
        if refs:
            st.caption('Catálogo de definiciones del Paso 04 (no representa una medición por sí mismo)')
            st.dataframe(pd.DataFrame([{'Indicador':r['nombre'],'Categoría':r['tipo'],
                  'Meta':r['meta'],'Fuente':r['fuente']} for r in refs]),
                  hide_index=True,use_container_width=True)
    st.download_button('Exportar indicadores CSV',s.metrics_csv(items),file_name='CENS_Paso07_Indicadores.csv',mime='text/csv')


def ans_page(items):
    if not items:return empty()
    m=s.stats(items);q=s.quality_summary(items)
    kpis([('ANS primera respuesta',fmt(m['ans_respuesta'],'%',0),f'{m["cumplen_respuesta"]}/{m["base_respuesta"]} evaluables'),
          ('ANS resolución',fmt(m['ans_resolucion'],'%',0),f'{m["cumplen_resolucion"]}/{m["base_resolucion"]} evaluables'),
          ('En riesgo',len(m['riesgo']),'Tickets abiertos ≥80%'),('Vencidos',len(m['vencidos']),'Tickets abiertos vencidos')])
    st.caption('El consumo se calcula con la unidad y el calendario congelados de cada ticket en el Paso 06. Los ANS sin configurar no cuentan como cumplidos.')
    alerts=[]
    for t in items:
        for kind in ('respuesta','resolucion'):
            x=s.sla(t,kind)
            if x['estado'] in ('Vencido','En riesgo','Incumplió','Calendario inválido'):
                alerts.append((t,kind,x))
    left,right=st.columns([1.65,1])
    with left:
        with st.container(border=True):
            st.subheader('Alertas por ticket y compromiso')
            if not alerts:st.success('No hay casos en riesgo, vencidos o con calendario inválido en esta selección.')
            for t,kind,x in alerts:
                with st.expander(f'{t["folio"]} · {kind} · {x["estado"]}'):
                    st.write(f'**Servicio:** {t["servicio_nombre"]} · **Responsable:** {t["responsable"] or "Sin asignar"}')
                    st.caption(f'Consumo: {fmt(x["consumido"]," h")} / Plazo: {fmt(x["plazo"]," h")} · Unidad: {x["unidad"]}')
                    if x.get('detalle'):st.warning(x['detalle'])
                    if st.button('Documentar hallazgo',key='p7_find_'+t['id']+kind):
                        st.session_state['p7_edit_finding']=(t['id'],kind)
            if st.session_state.get('p7_edit_finding'):
                ticketid,kind=st.session_state['p7_edit_finding']
                with st.form('p7_save_finding'):
                    text=st.text_area('Hallazgo o causa *')
                    measure=st.text_area('Acción correctiva / preventiva')
                    owner=staff_picker('Responsable de seguimiento')
                    status=st.selectbox('Estado',['Pendiente','En seguimiento','Resuelto'])
                    if st.form_submit_button('Guardar hallazgo'):
                        if action(lambda:s.save_finding(ticketid,kind,text,measure,owner,status),'Hallazgo registrado'):
                            st.session_state.pop('p7_edit_finding',None);st.rerun()
    with right:
        with st.container(border=True):
            st.subheader('Eventos de alerta desde Paso 06')
            events=s.recorded_alerts(items)
            st.metric('Eventos registrados',len(events))
            st.metric('Sin ANS de respuesta',q['sin_ans_respuesta'])
            st.metric('Sin ANS de resolución',q['sin_ans_resolucion'])
            if events:
                st.dataframe(pd.DataFrame([{'Ticket':x['ticket_id'][:9],'Tipo':x['tipo'],
                      'Umbral':str(x['umbral'])+'%','Estado':x['estado'],'Fecha':x['fecha']} for x in events]),
                      hide_index=True,use_container_width=True)
            st.caption('El Paso 07 consulta eventos existentes. No ejecuta ni duplica el envío de notificaciones.')
    st.subheader('Comparativo ANS por servicio')
    st.dataframe(pd.DataFrame([{'Servicio':x['servicio'],'Evaluables':x['base_resolucion'],
        'ANS respuesta %':x['ans_respuesta'],'ANS resolución %':x['ans_resolucion'],
        'Vencidos':len(x['vencidos']),'En riesgo':len(x['riesgo'])} for x in s.by_service(items)]),
        use_container_width=True,hide_index=True)
    st.download_button('Exportar ANS CSV',s.ans_csv(items),file_name='CENS_Paso07_ANS.csv',mime='text/csv')


def reports_page(items):
    if not items:return empty()
    m=s.stats(items);f=s.client_feedback(items);saved=s.report_config()
    kpis([('Solicitudes',m['recibidas'],'Base del corte'),
          ('ANS resolución',fmt(m['ans_resolucion'],'%',0),f'{m["base_resolucion"]} evaluables'),
          ('CSAT',fmt(f['csat'],'/5'),f'{f["base_csat"]} respuestas'),
          ('NPS',fmt(f['nps'],' puntos',0),f'{f["base_nps"]} respuestas')])
    a,b=st.columns([1.4,1])
    with a:
        with st.container(border=True):
            st.subheader('Contenido del informe')
            st.write(f'Se registraron **{m["recibidas"]}** solicitudes, **{m["atendidas"]}** entregas técnicas y **{m["finalizadas"]}** cierres administrativos.')
            st.write(f'ANS de respuesta: **{m["cumplen_respuesta"]}/{m["base_respuesta"]}**; ANS de resolución: **{m["cumplen_resolucion"]}/{m["base_resolucion"]}**.')
            st.dataframe(pd.DataFrame([{'Servicio':x['servicio'],'Solicitudes':x['recibidas'],
                  'Entregadas':x['atendidas'],'ANS resolución %':x['ans_resolucion']} for x in s.by_service(items)]),
                  hide_index=True,use_container_width=True)
            st.caption('El contenido usa la selección de periodo activa y mantiene denominadores. No estima beneficios estratégicos.')
    with b:
        with st.container(border=True):
            st.subheader('Crear corte reproducible')
            with st.form('p7_cut_form'):
                owner=staff_picker('Responsable de emisión *',value=saved['responsable'])
                notes=st.text_area('Hallazgos, decisiones y compromisos',value=saved['observaciones'],height=145)
                if st.form_submit_button('Guardar y congelar corte',type='primary'):
                    def save():
                        code=s.report_cut(items,owner,notes,st.session_state.get('p7_filter_snapshot',{}))
                        s.save_report(owner,notes)
                        return code
                    code=action(save,'Corte generado y guardado con huella de integridad')
                    if code:st.session_state['p7_cut_selected']=code;st.rerun()
            st.caption('Guardar un corte no modifica los tickets. Los datos posteriores no reescriben el informe archivado.')
    cuts=s.report_cuts()
    if cuts:
        st.subheader('Historial de cortes archivados')
        selected=st.selectbox('Seleccionar corte',cuts,index=next((i for i,c in enumerate(cuts) if c['id']==st.session_state.get('p7_cut_selected')) ,0),
           format_func=lambda x:f'{x["creado_en"][:16]} · {x["responsable"]} · {x["id"][:8]}',key='p7_report_select')
        report=s.report_cut_data(selected['id'])
        st.caption(f'Integridad SHA-256: {selected["huella_sha256"][:18]}… · Criterio de fecha: {selected["criterio_fecha"]}')
        a,b,c=st.columns(3)
        with a:st.download_button('Descargar PDF',s.report_pdf(report),file_name='CENS_Paso07_Corte.pdf',mime='application/pdf')
        with b:st.download_button('Descargar Excel',s.report_excel(report),file_name='CENS_Paso07_Corte.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        with c:st.download_button('Descargar JSON',jb(report),file_name='CENS_Paso07_Corte.json',mime='application/json')
    else:st.info('Aún no existen cortes guardados. Completa el responsable y utiliza Guardar y congelar corte.')
    st.download_button('Exportar hallazgos al Paso 08',jb(s.step8_export(items)),file_name='CENS_Paso07_Hallazgos_Paso08.json',mime='application/json')


def feedback_page(items):
    if not items:return empty()
    m=s.stats(items);f=s.client_feedback(items)
    kpis([('CSAT',fmt(f['csat'],'/5'),f'{f["base_csat"]} respuestas'),
          ('NPS',fmt(f['nps'],' puntos',0),f'{f["base_nps"]} respuestas'),
          ('Conformidades',f['conformes'],'Clientes que aceptaron'),
          ('Solicitudes de ajuste',f['ajustes'],'Clientes que pidieron correcciones')])
    st.caption('CSAT usa 1–5; NPS usa 0–10 para calcular promotores menos detractores y se expresa entre −100 y +100. No convertir las notas históricas 1–10 a ninguna de estas métricas.')
    a,b=st.columns([1,1.25])
    with a:
        with st.container(border=True):
            st.subheader('Satisfacción histórica 1–10')
            st.metric('Nota media histórica',fmt(m['calificacion'],'/10'),help=f'{m["evaluaciones"]} notas legadas')
            st.caption(f'{m["evaluaciones"]} notas históricas. No se consideran NPS ni CSAT.')
            st.metric('Cobertura histórica',fmt(m['cobertura_satisfaccion'],'%'))
    with b:
        with st.container(border=True):
            st.subheader('Conformidad y comentarios del cliente')
            refs={x['id']:x for x in items}
            if f['filas']:
                st.dataframe(pd.DataFrame([{'Ticket':refs[x['ticket_id']]['folio'],
                   'Decisión':x['decision'],'CSAT /5':x['csat'],'NPS 0–10':x['nps'],
                   'Comentarios':x['observaciones'],'Fecha':x['fecha']} for x in f['filas']]),
                   hide_index=True,use_container_width=True)
            else:st.info('Sin respuestas de conformidad registradas en los tickets seleccionados.')
    st.subheader('Retroalimentación y acciones de mejora')
    byid={x['id']:x for x in items}
    candidate=sorted(set(x['ticket_id'] for x in f['filas']) | set(x['id'] for x in items if x.get('calificacion') is not None))
    if candidate:
        selected=st.selectbox('Ticket a revisar',candidate,format_func=lambda key:byid[key]['folio'],key='p7_feedback_ticket')
        previous=next((x for x in s.findings() if x['ticket_id']==selected and x['tipo']=='cliente'),{})
        with st.form('p7_feedback_form'):
            detail=st.text_area('Hallazgo o comentario',value=previous.get('descripcion',''))
            resolution=st.text_area('Acción y comunicación al cliente',value=previous.get('accion',''))
            owner=st.text_input('Responsable',value=previous.get('responsable',''))
            options=['Pendiente','En seguimiento','Resuelto'];old=previous.get('estado','Pendiente')
            status=st.selectbox('Estado de gestión',options,index=options.index(old) if old in options else 0)
            if st.form_submit_button('Guardar seguimiento'):
                action(lambda:s.save_finding(selected,'cliente',detail,resolution,owner,status),'Retroalimentación documentada')
    else:st.info('Sin comentarios ni evaluaciones que requieran seguimiento.')
    st.download_button('Exportar satisfacción histórica CSV',s.feedback_csv(items),file_name='CENS_Paso07_Satisfaccion_historica.csv',mime='text/csv')


def pmi_page():
    heading('MÓDULO 05','Autoevaluación metodológica PMI','20 criterios en cuatro dimensiones: escala 1–5, instrucciones, interpretación e historial.')
    st.info('**Instrucciones de la guía PMI:** califica de 1 a 5: 1 = En absoluto/nunca; 2 = Rara vez/deficiente; 3 = A veces/promedio; 4 = A menudo/bien; 5 = Siempre/excelente.')
    evs=s.evaluations();draft=next((x for x in evs if x['estado']=='Borrador'),None)
    if not draft:
        with st.form('p7_pmi_new'):
            owner=st.text_input('Responsable de la evaluación *')
            if st.form_submit_button('Crear autoevaluación',type='primary'):
                if action(lambda:s.new_evaluation(owner),'Evaluación nueva creada con las preguntas de la guía PMI'):st.rerun()
    else:
        result=s.evaluation_summary(draft['id'])
        questions=s.GUIDE_QUESTIONS if draft.get('instrumento')=='PMI-2025-guia' else s.QUESTIONS
        if draft.get('instrumento')!='PMI-2025-guia':
            st.warning('Borrador histórico: conserva los enunciados de su versión original; no se sustituyen por las preguntas del nuevo instrumento.')
        kpis([('Respondidas',f'{result["respondidas"]}/20','4 dimensiones'),
              ('Puntaje',str(result['puntaje_final']) if result['puntaje_final'] is not None else '—','20 a 100 puntos'),
              ('Interpretación',result['clasificacion_final'] or 'Pendiente','Solo si está completa'),
              ('Archivadas',sum(e['estado']=='Archivada' for e in evs),'Sin modificación retrospectiva')])
        left,right=st.columns([1.6,1])
        with left:
            dim=st.radio('Dimensión de la guía',list(range(4)),key='p7_pmi_dim',
                format_func=lambda i:f'{i+1}. {questions[i]["name"]}')
            previous={x['numero']:x for x in s.answers(draft['id'])}
            with st.form('p7_pmi_form_'+str(dim)):
                values=[]
                for i,q in enumerate(questions[dim]['questions'],start=1):
                    num=dim*5+i;old=previous.get(num)
                    st.markdown(f'**{num}. {q}**')
                    score=st.selectbox('Calificación',[None,1,2,3,4,5],
                        index=(old['valor'] if old else 0),key=f'p7_q_{num}',
                        format_func=lambda n:'Sin responder' if n is None else str(n))
                    a,b=st.columns(2)
                    with a:note=st.text_input('Observación',value=old['observacion'] if old else '',key=f'p7_note_{num}')
                    with b:evidence=st.text_input('Evidencia',value=old['evidencia'] if old else '',key=f'p7_ev_{num}')
                    values.append((num,score,note,evidence))
                if st.form_submit_button('Guardar esta dimensión',type='primary'):
                    def save():
                        for num,score,note,evidence in values:
                            if score is not None:s.save_answer(draft['id'],num,score,note,evidence)
                    if action(save,'Respuestas guardadas'):st.rerun()
            if st.button('Archivar evaluación completa',type='primary'):
                if action(lambda:s.archive_evaluation(draft['id']),'Evaluación archivada'):st.rerun()
        with right:
            with st.container(border=True):
                st.subheader('Resumen por dimensión')
                for d in result['dimensiones']:
                    st.caption(f'{d["dimension"]}: {d["respondidas"]}/5 · {d["subtotal"] if d["respondidas"]==5 else "—"}/25')
                    st.progress(d['respondidas']/5)
                st.caption('Crítico: 20–38 · Pobre: 39–58 · Promedio: 59–75 · Bien: 76–88 · Excelente: 89–100')
                st.download_button('Exportar evaluación JSON',jb({'resultados':result,'respuestas':s.answers(draft['id'])}),file_name='CENS_Paso07_PMI.json',mime='application/json')
    with st.expander('Historial de autoevaluaciones'):
        archives=[x for x in evs if x['estado']=='Archivada']
        if archives:
            st.dataframe(pd.DataFrame(archives)[['version','responsable','puntaje','clasificacion','archivado_en','instrumento']],hide_index=True,use_container_width=True)
        else:st.caption('No hay evaluaciones archivadas.')


def page(section):
    if section not in NAV:st.error('Vista no disponible');return
    if section==NAV[4]:return pmi_page()
    part,title,subtitle=PAGES[section];heading(part,title,subtitle)
    try:status=s.sync_live(include_demo=bool(st.session_state.get('p7_include_demo',False)))
    except (ValueError,s.ValidationError,KeyError) as exc:
        st.error('No se pudo verificar el origen operativo del Paso 06: '+str(exc))
        return
    source_status(status)
    if section==NAV[0]:imports_panel()
    items=filters()
    if section==NAV[0]:return dashboard(items)
    if section==NAV[1]:return ans_page(items)
    if section==NAV[2]:return reports_page(items)
    if section==NAV[3]:return feedback_page(items)
