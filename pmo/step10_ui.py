"""Interfaz del Paso 10, integrada en Streamlit (5 pantallas; no HTML paralelo)."""
from __future__ import annotations
from .date_widgets import iso_date_input
import html, json
from datetime import date
import pandas as pd
import streamlit as st
from .staff_picker import staff_picker
from .client_picker import choose_client
from . import step10 as s
from .ui import kpi

NAV=list(s.NAV)

def apply_step10_theme():
    st.markdown('''<style>
      .p10-info{background:#EFF8F9;border:1px solid #C9E4E9;border-radius:10px;padding:12px 15px;color:#426E7B;font-size:12px;margin:12px 0 18px}
      .p10-question{border:1px solid #DEE8EF;border-radius:10px;background:#fff;padding:14px 16px;margin:8px 0;min-height:76px}
      .p10-question strong{font-size:13px;color:#123B4F}.p10-question small{display:block;font-size:11px;color:#657F90;margin-top:5px}
      .p10-header{border-left:4px solid #0B9A9F;background:#EFF8F9;padding:10px 14px;border-radius:7px;margin:20px 0 8px}
      .p10-header b{color:#123B50}
    </style>''',unsafe_allow_html=True)

def esc(x):return html.escape(str(x if x is not None else ''))
def jb(data):return json.dumps(data,ensure_ascii=False,indent=2,default=str).encode('utf-8')
def number(x,decimals=1):return '—' if x is None else f'{x:,.{decimals}f}'.replace(',','X').replace('.',',').replace('X','.')
def run(fn,message='Registro guardado'):
    try:
        result=fn();st.success(message);return True,result
    except (s.ValidationError,ValueError,TypeError,KeyError,__import__('sqlite3').IntegrityError) as ex:
        st.error(str(ex));return False,None

def heading(n,title,description):
    st.markdown(f'<div class="pmo-eyebrow">PASO 10 · MÓDULO {n:02d} · RECONOCIMIENTO DEL VALOR</div><div class="pmo-title">{esc(title)}</div><div class="pmo-subtitle">{esc(description)}</div>',unsafe_allow_html=True)

def kpis(items):
    for idx,(c,(title,value,caption)) in enumerate(zip(st.columns(len(items)),items)):
        with c:kpi(title,str(value),caption,'chart-no-axes-column',('orange','blue','purple','teal')[idx%4])

def information():
    st.markdown('<div class="p10-info">El reconocimiento expresa la percepción de los clientes y <b>no prueba por sí solo que un beneficio fue entregado</b>. La evidencia de realización se valida en el Paso 9. El NPS, la satisfacción y la autoevaluación metodológica tienen escalas independientes.</div>',unsafe_allow_html=True)

def _options_benefits():
    return {x['id']:x for x in s.benefits()}

def _clear_filters():
    st.session_state['p10_filter_period']=''
    st.session_state['p10_filter_group']=''

def _filters():
    source=s.surveys();ps=sorted({x['periodo'] for x in source},reverse=True);gs=sorted({x['grupo'] for x in source})
    a,b,c=st.columns([1.2,1.6,1])
    with a:period=st.selectbox('Periodo',['']+ps,format_func=lambda x:x or 'Todos los periodos',key='p10_filter_period')
    with b:group=st.selectbox('Grupo de clientes',['']+gs,format_func=lambda x:x or 'Todos los grupos',key='p10_filter_group')
    with c:
        st.write('')
        st.button('Limpiar filtros',key='p10_clear_filters',on_click=_clear_filters)
    return period,group

@st.dialog('Encuesta institucional de reconocimiento',width='large')
def survey_dialog(key=None):
    old=s.survey(key) if key else None;old=old or {}
    bs=_options_benefits()
    st.caption('NPS: 0–10. Percepción institucional y reconocimiento particular: 1–10. Los datos de demostración se incorporan únicamente en el laboratorio.')
    with st.form('p10_form_survey'):
        a,b=st.columns(2)
        with a:
            period=st.text_input('Periodo de evaluación *',value=old.get('periodo','2026-4'))
            when=st.date_input('Fecha *',value=date.fromisoformat(old['fecha']) if old.get('fecha') else date.today(), format='YYYY/MM/DD')
            group=st.text_input('Grupo de interesados *',value=old.get('grupo',''))
            area=st.text_input('Dependencia',value=old.get('area',''))
        with b:
            name=choose_client(st,'Nombre de cliente (opcional) · Paso 01',old.get('nombre',''),key=f'p10_survey_client_{key or "new"}')[0]
            code=st.text_input('Código seudónimo de encuestado',value=old.get('codigo_encuestado',''))
            options=['']+list(bs)
            current=old.get('beneficio_id') or ''
            benefit=st.selectbox('Beneficio verificado relacionado (opcional)',options,
                index=options.index(current) if current in options else 0,
                format_func=lambda x: 'Encuesta institucional general, sin vínculo' if not x else f'{bs[x]["servicio"]} · {bs[x]["beneficio"][:70]}')
            nps_options=['Sin responder',*range(11)]
            nps_value=st.selectbox('¿Qué tan probable es que recomiende la PMO? (NPS) *',nps_options,
                index=nps_options.index(old['nps']) if old.get('nps') is not None and old['nps'] in nps_options else 0)
        st.markdown('**Percepción del valor institucional (1–10)**')
        vals={}
        scale_options=['Sin responder',*range(1,11)]
        for dimension,question in s.QUESTIONS_PERCEPTION.items():
            previous=old.get(dimension)
            vals[dimension]=st.selectbox(question,scale_options,index=scale_options.index(previous) if previous in range(1,11) else 0,
                key=f'p10_dimension_{dimension}_{key or "new"}')
        recognition=st.selectbox('Reconocimiento del beneficio específico (1–10)',scale_options,
            index=scale_options.index(old.get('reconocimiento')) if old.get('reconocimiento') in range(1,11) else 0) if benefit else None
        comment=st.text_area('Comentarios del cliente',value=old.get('comentario',''))
        demo=st.checkbox('Este registro es una simulación de laboratorio',value=bool(old.get('es_demo')))
        submitted=st.form_submit_button('Guardar encuesta',type='primary')
    if submitted:
        d={'periodo':period,'fecha':when.isoformat(),'grupo':group,'area':area,'nombre':name,'codigo_encuestado':code,
           'beneficio_id':benefit,'nps':nps_value,'reconocimiento':recognition,'comentario':comment,'es_demo':demo,
           **vals}
        good,_=run(lambda:s.save_survey(d,key),'Encuesta registrada en SQLite')
        if good:st.rerun()

def perception_page():
    heading(1,'Percepción del valor','Encuestas de reconocimiento por grupo; NPS de 0 a 10 y percepción institucional de 1 a 10.')
    c1,c2,c3=st.columns([1.3,1,1.2])
    with c1:
        if st.button('＋ Registrar encuesta',type='primary'):survey_dialog()
    with c2:st.download_button('↓ Plantilla CSV',s.template_csv(),file_name='CENS_P10_Plantilla_Encuestas.csv',mime='text/csv')
    with c3:
        with st.popover('↑ Importar CSV'):
            upload=st.file_uploader('Archivo CSV de la plantilla',type='csv',key='p10_upload_csv')
            st.caption('La carga valida cada respuesta y evita duplicados por código y periodo. Los datos ficticios deben cargarse únicamente en la base de laboratorio.')
            if upload and st.button('Validar e importar respuestas CSV',type='primary'):
                good,r=run(lambda:s.import_surveys_csv(upload.getvalue()),'Importación CSV registrada')
                if good:
                    st.info(f"{r['agregadas']} incorporadas · {r['rechazadas']} rechazadas");st.rerun()
    period,group=_filters();d=s.dashboard(period,group)
    kpis([('Encuestas registradas',d['encuestas'],'Respuestas del filtro'),
          ('NPS general',number(d['nps']['puntaje'],0),'Promotores menos detractores · −100 a +100'),
          ('Satisfacción institucional',number(d['promedios']['satisfaccion'])+'/10' if d['encuestas'] else '—','No equivale a satisfacción por ticket'),
          ('Confianza en la PMO',number(d['promedios']['confianza'])+'/10' if d['encuestas'] else '—','Promedio institucional')])
    a,b=st.columns([1.5,1])
    with a:
        with st.container(border=True):
            st.subheader('Encuesta de reconocimiento del valor')
            st.caption('Siete dimensiones de percepción independientes del NPS.')
            for i,(code,text) in enumerate(s.QUESTIONS_PERCEPTION.items()):
                st.markdown(f'<div class="p10-question"><strong>{esc(code.capitalize())}</strong><small>{esc(text)}</small></div>',unsafe_allow_html=True)
    with b:
        with st.container(border=True):
            st.subheader('Clasificación NPS')
            st.write('🔴 0–6 · Detractores')
            st.write('🟠 7–8 · Pasivos')
            st.write('🟢 9–10 · Promotores')
            st.info('NPS = (% promotores) − (% detractores). Rango −100 a +100. La satisfacción 1–10 no se sustituye ni se mezcla con NPS.')
            if d['encuestas']:
                x=d['nps'];st.write(f"Detractores: **{x['detractores']}** · Pasivos: **{x['pasivos']}** · Promotores: **{x['promotores']}**")
    with st.container(border=True):
        st.subheader('Respuestas registradas')
        selected=d['seleccion']
        if not selected:st.info('Todavía no hay encuestas para el filtro seleccionado. No se precargan respuestas ficticias.')
        else:
            table=[]
            for x in selected:
                table.append({'Fecha':x['fecha'],'Periodo':x['periodo'],'Grupo':x['grupo'],'Dependencia':x['area'],
                              'NPS':x['nps'],'Satisfacción':x['satisfaccion'],'Reconocimiento vinculado':x['reconocimiento'],
                              'Tipo':'Laboratorio' if x['es_demo'] else 'Registro'})
            st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
            st.download_button('↓ Exportar encuestas CSV',s.export_surveys_csv(period=period,group=group),file_name='CENS_P10_Encuestas.csv',mime='text/csv')
            selected_map={x['id']:x for x in selected};key=st.selectbox('Seleccionar respuesta para editar o eliminar',list(selected_map),format_func=lambda k:f'{selected_map[k]["fecha"]} · {selected_map[k]["grupo"]} · NPS {selected_map[k]["nps"]} · {k[:8]}')
            col1,col2=st.columns(2)
            with col1:
                if st.button('Editar respuesta'):survey_dialog(key)
            with col2:
                if st.checkbox('Confirmar eliminación',key='p10_confirm_remove_survey'):
                    if st.button('Eliminar respuesta',type='secondary'):
                        if run(lambda:s.delete_survey(key),'Respuesta eliminada')[0]:st.rerun()
    information()

def comparison_page():
    heading(2,'Valor entregado frente a reconocido','Comparación entre beneficios demostrados en el Paso 9 y la percepción específica de sus clientes.')
    a,b=st.columns([1,2])
    with a:
        if st.button('↑ Importar beneficios verificados del Paso 9',type='primary'):
            good,r=run(lambda:s.import_from_step9(),'Importación desde la base compartida terminada')
            if good:st.info(f"Agregados: {r['agregados']} · Actualizados: {r['actualizados']} · Omitidos: {r['omitidos']}");st.rerun()
    with b:
        with st.popover('Importar expediente JSON externo del Paso 9'):
            uploaded=st.file_uploader('Expediente JSON del Paso 9',type='json',key='p10_step9_json')
            if uploaded and st.button('Importar expediente'):
                good,r=run(lambda:s.import_step9_json(json.loads(uploaded.getvalue()),uploaded.name),'Expediente del Paso 9 importado')
                if good:st.info(r);st.rerun()
    period,group=_filters();d=s.dashboard(period,group);information()
    kpis([('Beneficios importados',d['beneficios'],'Verificados en Paso 9'),('Entregados y reconocidos',d['reconocidos'],f'Promedio ≥{d["umbral"]}/10'),
          ('Entregados, poco reconocidos',d['poco_reconocidos'],'Con percepción inferior al umbral'),
          ('Sin percepción vinculada',d['sin_vinculo'],'Pendientes de encuesta específica')])
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            st.subheader('Cómo interpretar la comparación')
            st.success('Entregado y reconocido: beneficio verificado con reconocimiento suficiente.')
            st.warning('Entregado, poco reconocido: beneficio verificado con percepción inferior al umbral.')
            st.info('Pendiente de percepción: beneficio verificado sin encuesta vinculada.')
            st.caption('Una encuesta general sin beneficio asociado no demuestra valor específico.')
    with b:
        with st.container(border=True):
            st.subheader('Regla analítica configurable CENS')
            cfg=s.config();st.caption('Este umbral no es una clasificación oficial del PMI.')
            threshold=st.selectbox('Umbral de reconocimiento 1–10',range(1,11),index=int(cfg['umbral'])-1,key='p10_threshold_choice')
            if st.button('Guardar umbral de reconocimiento'):
                if run(lambda:s.save_config(cfg['poblacion_objetivo'],threshold,cfg['responsable_informe'],cfg['lectura_ejecutiva']))[0]:st.rerun()
            st.write(f"{sum(x['beneficio_id'] is not None for x in d['seleccion'])} respuestas vinculadas · {len(d['seleccion'])-sum(x['beneficio_id'] is not None for x in d['seleccion'])} institucionales generales")
    with st.container(border=True):
        st.subheader('Matriz de beneficios y reconocimiento')
        if not d['beneficios']:st.info('Importa los beneficios formalmente verificados del Paso 9 para comenzar.')
        else:
            table=[]
            for x in s.benefits():
                val=d['reconocimiento_por_beneficio'].get(x['id'])
                status='Sin percepción vinculada' if val is None else 'Entregado y reconocido' if val>=d['umbral'] else 'Entregado, poco reconocido'
                table.append({'Servicio':x['servicio'],'Beneficio verificado':x['beneficio'],'Cliente':x['cliente'],
                    'Resultado observado':f"{number(x['resultado_real'],2)} {x['unidad']}",
                    'Reconocimiento':number(val)+'/10' if val is not None else '—','Lectura':status,
                    'Evidencia Paso 9':x['evidencia']})
            st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
    st.caption('La importación conserva el ID original del beneficio; nunca modifica ni recalcula el Paso 9.')

@st.dialog('Historia de valor documentada',width='large')
def story_dialog(key=None):
    old=next((x for x in s.stories() if x['id']==key),{}) if key else {}
    bs=_options_benefits();options=['']+list(bs);bid=old.get('beneficio_id') or ''
    with st.form('p10_story_form'):
        a,b=st.columns(2)
        with a:
            title=st.text_input('Título de historia *',value=old.get('titulo',''))
            when=st.date_input('Fecha',value=date.fromisoformat(old['fecha']) if old.get('fecha') else date.today(), format='YYYY/MM/DD')
            group=st.text_input('Grupo o destinatarios *',value=old.get('grupo',''))
            linked=st.selectbox('Beneficio verificado relacionado',options,index=options.index(bid) if bid in options else 0,format_func=lambda x:bs[x]['beneficio'] if x else 'Sin vinculación')
            owner=staff_picker('Responsable *',value=old.get('responsable',''))
        with b:
            situation=st.text_area('Situación inicial *',value=old.get('situacion',''))
            contribution=st.text_area('Contribución de la PMO *',value=old.get('contribucion',''))
            result=st.text_area('Resultado documentado *',value=old.get('resultado',''))
        test=st.text_area('Testimonio textual (opcional)',value=old.get('testimonio',''))
        ev=st.text_input('Evidencia de resultado',value=old.get('evidencia',''))
        consent=st.checkbox('Autorización expresa para divulgar el caso',value=bool(old.get('autorizacion')))
        status=st.selectbox('Estado',('Borrador','En revisión','Publicada'),index=('Borrador','En revisión','Publicada').index(old.get('estado','Borrador')))
        demo=st.checkbox('Caso demostrativo',value=bool(old.get('es_demo')))
        submit=st.form_submit_button('Guardar historia',type='primary')
    if submit:
        data={'titulo':title,'fecha':when.isoformat(),'grupo':group,'beneficio_id':linked,'situacion':situation,
             'contribucion':contribution,'resultado':result,'testimonio':test,'evidencia':ev,'autorizacion':consent,
             'estado':status,'responsable':owner,'es_demo':demo}
        if run(lambda:s.save_story(data,key),'Historia de valor guardada')[0]:st.rerun()

@st.dialog('Nueva actividad de reconocimiento',width='large')
def activity_dialog():
    with st.form('p10_activity_form'):
        title=st.text_input('Nombre de la actividad *')
        a,b=st.columns(2)
        with a:
            typ=st.selectbox('Tipo',('Taller','Campaña','Evento'));when=st.date_input('Fecha', format='YYYY/MM/DD')
            group=st.text_input('Grupo participante *')
        with b:
            owner=staff_picker('Responsable *');people=st.number_input('Asistentes reales',min_value=0,step=1,value=0)
            state=st.selectbox('Estado',('Programada','En ejecución','Completada'))
        results=st.text_area('Resultados observados y acciones');evidence=st.text_input('Evidencia o acta')
        demo=st.checkbox('Actividad demostrativa')
        ok=st.form_submit_button('Guardar actividad',type='primary')
    if ok:
        d=dict(titulo=title,tipo=typ,fecha=when.isoformat(),grupo=group,responsable=owner,asistentes=people,
               resultados=results,evidencia=evidence,estado=state,es_demo=demo)
        if run(lambda:s.save_activity(d),'Actividad guardada')[0]:st.rerun()

@st.dialog('Retroalimentación 360°',width='large')
def feedback_dialog():
    with st.form('p10_feedback_form'):
        a,b=st.columns(2)
        with a:
            when=st.date_input('Fecha', format='YYYY/MM/DD');group=choose_client(st,'Grupo o cliente · Paso 01 *',key='p10_feedback_client',optional=False)[0];channel=st.selectbox('Canal',('Taller','Entrevista','Encuesta','Reunión','Canal digital','Otro'))
        with b:
            owner=staff_picker('Responsable *');status=st.selectbox('Estado',('Abierta','En gestión','Cerrada'))
            deadline=iso_date_input('Fecha compromiso (opcional)')
        observation=st.text_area('Observación recibida *');action=st.text_area('Acción comprometida *');evidence=st.text_input('Evidencia de seguimiento')
        demo=st.checkbox('Retroalimentación de prueba');ok=st.form_submit_button('Guardar retroalimentación',type='primary')
    if ok:
        d=dict(fecha=when.isoformat(),grupo=group,canal=channel,responsable=owner,estado=status,fecha_compromiso=deadline,
               observacion=observation,accion=action,evidencia=evidence,es_demo=demo)
        if run(lambda:s.save_feedback(d),'Retroalimentación guardada')[0]:st.rerun()

def stories_page():
    heading(3,'Historias y actividades de reconocimiento','Testimonios verificables, talleres, campañas y retroalimentación 360°.')
    a,b,c=st.columns(3)
    with a:
        if st.button('＋ Historia de valor',type='primary'):story_dialog()
    with b:
        if st.button('＋ Taller o evento'):activity_dialog()
    with c:
        if st.button('＋ Retroalimentación'):feedback_dialog()
    historias=s.stories();actividades=s.activities();replies=s.feedback()
    kpis([('Historias documentadas',len(historias),'Borradores y publicaciones'),
          ('Actividades registradas',len(actividades),'Talleres, campañas y eventos'),
          ('Retroalimentaciones 360°',len(replies),'Acciones y compromisos')])
    with st.container(border=True):
        st.subheader('Historias de valor y testimonios')
        if not historias:st.info('No hay historias registradas.')
        for x in historias:
            with st.expander(f"{x['titulo']} · {x['estado']} · {x['grupo']}"):
                st.write(f"**Situación inicial:** {x['situacion']}")
                st.write(f"**Contribución PMO:** {x['contribucion']}")
                st.write(f"**Resultado:** {x['resultado']}")
                if x['testimonio']:st.markdown(f"> {esc(x['testimonio'])}")
                st.caption(f"Evidencia: {x['evidencia'] or 'No registrada'} · Autorización: {'Sí' if x['autorizacion'] else 'No'}")
                a,b=st.columns(2)
                with a:
                    if st.button('Editar historia',key='p10_edit_story_'+x['id']):story_dialog(x['id'])
                with b:
                    if st.checkbox('Confirmar eliminación de historia',key='p10_delcheck_story_'+x['id']):
                        if st.button('Eliminar historia',key='p10_delete_story_'+x['id']):
                            if run(lambda:s.delete_story(x['id']),'Historia eliminada')[0]:st.rerun()
        if historias:st.download_button('↓ Historias CSV',s.export_csv_records(historias),file_name='CENS_P10_Historias.csv',mime='text/csv')
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            st.subheader('Talleres, campañas y eventos')
            if actividades:
                st.dataframe(pd.DataFrame(actividades)[['fecha','titulo','tipo','grupo','asistentes','estado','evidencia']],hide_index=True,use_container_width=True)
                amap={x['id']:x for x in actividades};key=st.selectbox('Seleccionar actividad',list(amap),format_func=lambda k:amap[k]['titulo'])
                if st.checkbox('Confirmar eliminación de actividad'):
                    if st.button('Eliminar actividad'):
                        if run(lambda:s.delete_activity(key),'Actividad eliminada')[0]:st.rerun()
            else:st.info('Sin actividades registradas.')
    with b:
        with st.container(border=True):
            st.subheader('Retroalimentación 360°')
            if replies:
                st.dataframe(pd.DataFrame(replies)[['fecha','grupo','canal','observacion','accion','responsable','estado']],hide_index=True,use_container_width=True)
                fmap={x['id']:x for x in replies};key=st.selectbox('Seleccionar observación',list(fmap),format_func=lambda k:fmap[k]['grupo']+' · '+fmap[k]['fecha'])
                if st.checkbox('Confirmar eliminación de retroalimentación'):
                    if st.button('Eliminar retroalimentación'):
                        if run(lambda:s.delete_feedback(key),'Registro eliminado')[0]:st.rerun()
            else:st.info('Sin retroalimentaciones registradas.')
    st.caption('La publicación de una historia exige beneficio formalmente verificado, evidencia y autorización de divulgación.')

def _chart_bar(title,values,empty_message='Sin datos'):
    st.markdown('**'+title+'**')
    if not values:st.caption(empty_message);return
    st.bar_chart(pd.DataFrame({'Indicador':list(values),'Valor':list(values.values())}).set_index('Indicador'),use_container_width=True)

def executive_html(report):
    summary=report['nps'];x=report['indicadores'];cfg=report['configuracion']
    r=lambda v:'—' if v is None else number(v)
    rows=''.join(f'<tr><td>{esc(group)}</td><td>{d["encuestas"]}</td><td>{r(d["nps"])}</td><td>{r(d["confianza"])}</td></tr>' for group,d in x['grupos'].items())
    return ('<!DOCTYPE html><html lang="es-CO"><meta charset="utf-8"><title>PMO CENS · Informe de reconocimiento</title>'
       '<style>body{font:14px Segoe UI,sans-serif;color:#10374B;max-width:950px;margin:28px auto}h1{border-bottom:3px solid #0B9A9F;padding-bottom:12px}'
       'table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #DCE5EA;padding:9px;text-align:left}th{background:#F4F7FA}'
       '@media print{body{margin:1cm}}</style><h1>PMO FLYWHEEL CENS · Reconocimiento del valor</h1>'
       f'<p>Periodo: {esc(report["periodo"] or "Todos")} · Grupo: {esc(report["grupo"] or "Todos")}</p>'
       f'<p>Encuestas: {summary["total"]} · NPS: {r(summary["puntaje"])} · Promotores: {summary["promotores"]} · Detractores: {summary["detractores"]}</p>'
       f'<p>Confianza: {r(x["promedios"]["confianza"])} / 10 · Satisfacción: {r(x["promedios"]["satisfaccion"])} / 10</p>'
       f'<p>Beneficios verificados importados: {x["beneficios"]} · Reconocidos: {x["reconocidos"]} · Pendientes de percepción: {x["sin_vinculo"]}</p>'
       f'<h2>Comparación por segmentos</h2><table><tr><th>Grupo</th><th>Encuestas</th><th>NPS</th><th>Confianza</th></tr>{rows}</table>'
       f'<h2>Lectura ejecutiva</h2><p>{esc(cfg["lectura_ejecutiva"]).replace(chr(10),"<br>")}</p>'
       '<p>Una calificación positiva y el NPS no constituyen por sí solos prueba de ahorro o realización de beneficios. La evidencia se conserva en Paso 9.</p></html>')

def dashboard_page():
    heading(4,'Tablero ejecutivo de reconocimiento','Indicadores institucionales, segmentación de clientes, evolución y cierre de ciclo.')
    period,group=_filters();d=s.dashboard(period,group);cfg=s.config()
    from .alpha05_value_ui import render_recognition
    render_recognition(period,group)
    n=d['nps'];av=d['promedios'];cov=d['cobertura'];
    kpis([('NPS de la PMO',number(n['puntaje'],0),f"{n['total']} respuestas · −100 a +100"),
          ('Confianza promedio',number(av['confianza'])+'/10' if av['confianza'] is not None else '—','Credibilidad de la PMO'),
          ('PMO como socio estratégico',number(av['socio'])+'/10' if av['socio'] is not None else '—','Percepción de aliado'),
          ('Satisfacción general',number(av['satisfaccion'])+'/10' if av['satisfaccion'] is not None else '—','Encuesta institucional')])
    kpis([('Encuestas respondidas',n['total'],'Respuestas válidas'),
          ('Cobertura de encuesta',number(cov['porcentaje'])+'%' if cov['porcentaje'] is not None else '—',cov.get('razon','Población medida')),
          ('Reconocimiento vinculado',number(d['reconocimiento_promedio'])+'/10' if d['reconocimiento_promedio'] is not None else '—','Sobre encuestas asociadas a beneficios'),
          ('Beneficios reconocidos',d['reconocidos'],f"De {d['beneficios']} beneficios verificados importados")])
    a,b=st.columns([1.35,1])
    with a:
        with st.container(border=True):
            st.subheader('Distribución NPS')
            _chart_bar('Respuestas válidas',{'Detractores (0–6)':n['detractores'],'Pasivos (7–8)':n['pasivos'],'Promotores (9–10)':n['promotores']} if n['total'] else {})
            st.caption('NPS = porcentaje de promotores − porcentaje de detractores; la escala puede tomar valores negativos.')
    with b:
        with st.container(border=True):
            st.subheader('Percepción por dimensión')
            for k,v in av.items():
                if v is None:st.caption(f'{k.capitalize()}: —')
                else:st.progress(min(1,v/10),text=f'{k.capitalize()} · {number(v)}/10')
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            st.subheader('Evolución mensual')
            if d['mensual']:
                df=pd.DataFrame([{'Mes':m,**x} for m,x in d['mensual'].items()]).set_index('Mes')
                st.line_chart(df,use_container_width=True)
            else:st.info('No hay datos para construir tendencia.')
    with b:
        with st.container(border=True):
            st.subheader('Lectura ejecutiva')
            st.write(f"**NPS:** {number(n['puntaje'],0)} puntos, calculado con {n['total']} respuestas.")
            st.write(f"**Cobertura:** {number(cov['porcentaje'])+'%' if cov['porcentaje'] is not None else cov['razon']}.")
            st.write(f"**Valor entregado:** {d['beneficios']} beneficios verificados incorporados desde el Paso 9.")
            st.write(f"**Valor reconocido:** {d['reconocidos']} beneficios con reconocimiento explícito suficiente.")
            st.warning('El NPS, positivo o negativo, no demuestra impacto financiero. Ese valor se prueba y valida en el Paso 9.')
    with st.container(border=True):
        st.subheader('Comparación por segmentos de clientes')
        if d['grupos']:
            st.dataframe(pd.DataFrame([{'Grupo':g,**v} for g,v in d['grupos'].items()]),hide_index=True,use_container_width=True)
        else:st.info('No existen respuestas para los filtros seleccionados.')
    with st.expander('Configuración de cobertura e informe ejecutivo'):
        with st.form('p10_config_form'):
            a,b=st.columns(2)
            with a:
                population=st.number_input('Población objetivo general (0 = sin definir)',min_value=0,value=int(cfg['poblacion_objetivo'] or 0),step=1)
                owner=staff_picker('Responsable del informe',value=cfg['responsable_informe'])
            with b:threshold=st.number_input('Umbral de reconocimiento CENS',min_value=1,max_value=10,value=cfg['umbral'])
            reading=st.text_area('Lectura ejecutiva y decisiones',value=cfg['lectura_ejecutiva'])
            if st.form_submit_button('Guardar configuración'):
                if run(lambda:s.save_config(population or None,threshold,owner,reading),'Configuración guardada')[0]:st.rerun()
    a,b,c=st.columns(3)
    with a:
        st.download_button('↓ Informe ejecutivo HTML',executive_html(s.report(period,group)).encode('utf-8'),file_name='CENS_P10_Informe_Reconocimiento.html',mime='text/html')
        st.caption('Abre el informe en navegador e imprime como PDF.')
    with b:st.download_button('↓ Indicadores JSON',jb(s.report(period,group)),file_name='CENS_P10_Indicadores.json',mime='application/json')
    with c:st.download_button('↓ Encuestas CSV',s.export_surveys_csv(period=period,group=group),file_name='CENS_P10_Encuestas.csv',mime='text/csv')
    st.divider();st.subheader('Cierre formal del ciclo')
    st.caption('El cierre guarda una copia histórica del informe; no modifica los datos ni borra registros de los pasos anteriores.')
    with st.form('p10_cycle_form'):
        a,b=st.columns(2)
        with a:closing_period=st.text_input('Periodo de cierre *',value=period or '')
        with b:closing_owner=st.text_input('Responsable del cierre *',value=cfg['responsable_informe'])
        if st.form_submit_button('Guardar corte del ciclo',type='primary'):
            if run(lambda:s.close_cycle(closing_period,closing_owner),'Corte del ciclo archivado')[0]:st.rerun()
    cuts=s.cycle_history()
    if cuts:
        st.dataframe(pd.DataFrame(cuts),hide_index=True,use_container_width=True)
        opts={x['id']:x for x in cuts};k=st.selectbox('Descargar cierre histórico',list(opts),format_func=lambda k:opts[k]['periodo']+' · '+opts[k]['creado_en'])
        st.download_button('↓ Expediente histórico del ciclo',jb(s.cycle(k)),file_name='CENS_P10_Ciclo_Historico.json',mime='application/json')


def assessment_page():
    heading(5,'Autoevaluación metodológica PMI','30 preguntas en seis dimensiones; escala 1–5, evidencias e historial de evaluaciones.')
    assessments=s.evaluations();draft=next((x for x in assessments if x['estado']=='Borrador'),None)
    archived=[x for x in assessments if x['estado']=='Archivada']
    if not draft:
        st.info('Inicia una nueva evaluación para registrar respuestas sin sobrescribir los cortes archivados.')
        owner=st.text_input('Responsable de nueva evaluación',key='p10_new_evaluator')
        if st.button('＋ Crear autoevaluación metodológica',type='primary'):
            if run(lambda:s.create_evaluation(owner),'Autoevaluación iniciada')[0]:st.rerun()
        if archived:
            last=s.assessment(archived[0]['id']);kpis([('Preguntas respondidas',f"{last['respondidas']}/30",'Último corte'),('Puntuación',str(last['puntaje'])+'/150','Último corte'),('Clasificación',last['clasificacion'],'Instrumento metodológico'),('Historial',len(archived),'Cortes archivados')])
    else:
        d=s.assessment(draft['id'])
        kpis([('Preguntas respondidas',f"{d['respondidas']}/30",'Seis dimensiones'),('Puntuación',str(d['puntaje'])+'/150' if d['puntaje'] is not None else '—','Solo al responder todo'),('Clasificación',d['clasificacion'] or 'En progreso','Sin clasificación provisional'),('Historial',len(archived),'Cortes previos')])
        a,b=st.columns([1.5,1])
        with a:
            with st.container(border=True):
                st.subheader('Resultado por dimensión')
                for i,(title,_) in enumerate(s.DIMENSIONS):
                    score=d['dimensiones'][i];st.progress(score/25 if score is not None else 0,text=f'D{i+1} · {title}: {score if score is not None else "—"}/25')
        with b:
            with st.container(border=True):
                st.subheader('Clasificación PMI')
                for title,interval in [('Excelente','134–150'),('Bien','114–133'),('Promedio','89–113'),('Pobre','59–88'),('Crítico','30–58')]:
                    st.write(f'**{title}** · {interval}')
                st.caption('Instrumento de escala 1–5. No representa NPS ni satisfacción institucional.')
        section=st.selectbox('Dimensión a responder',range(6),format_func=lambda i:f'{i+1}. {s.DIMENSIONS[i][0]}',key='p10_pmi_dim')
        with st.form(f'p10_pmi_form_{section}'):
            responses=[]
            for n in range(section*5+1,section*5+6):
                old=d['respuestas'].get(n,{})
                st.markdown('**'+str(n)+'. '+s.QUESTIONS[n-1]+'**')
                answer=st.radio('Valoración',options=[0,1,2,3,4,5],index=int(old.get('valor') or 0),horizontal=True,
                  format_func=lambda v:'Sin responder' if v==0 else str(v),key=f'p10_pmi_rate_{draft["id"]}_{n}')
                a,b=st.columns(2)
                with a:obs=st.text_input('Observación (opcional)',value=old.get('observacion',''),key=f'p10_pmi_obs_{draft["id"]}_{n}')
                with b:ev=st.text_input('Evidencia / referencia',value=old.get('evidencia',''),key=f'p10_pmi_ev_{draft["id"]}_{n}')
                responses.append((n,answer or None,obs,ev))
            save=st.form_submit_button('Guardar cinco respuestas',type='primary')
        if save:
            for n,answer,obs,ev in responses:
                good,_=run(lambda n=n,answer=answer,obs=obs,ev=ev:s.save_answer(draft['id'],n,answer,obs,ev),'Respuesta guardada')
                if not good:break
            else:st.rerun()
        if d['respondidas']==30:
            st.success(f"Evaluación completa: {d['puntaje']}/150 · {d['clasificacion']}")
            if st.button('Archivar evaluación',type='primary'):
                if run(lambda:s.archive_evaluation(draft['id']),'Evaluación archivada')[0]:st.rerun()
    if archived:
        st.subheader('Historial de autoevaluaciones')
        st.dataframe(pd.DataFrame(archived)[['version','responsable','puntaje','clasificacion','archivado_en']],hide_index=True,use_container_width=True)
        which=st.selectbox('Seleccionar corte archivado',[x['id'] for x in archived],format_func=lambda k:'Versión '+str(next(x['version'] for x in archived if x['id']==k)))
        st.download_button('↓ Evaluación y evidencias JSON',jb(s.assessment(which)),file_name='CENS_P10_Autoevaluacion_PMI.json',mime='application/json')


def backup_panel():
    with st.expander('Respaldo, restauración y procedencia de los registros del Paso 10'):
        st.download_button('↓ Respaldo completo Paso 10 JSON',jb(s.backup()),file_name='PMO_CENS_PASO10_RESPALDO.json',mime='application/json')
        f=st.file_uploader('Restaurar solo las tablas del Paso 10',type='json',key='p10_restore_json')
        confirmation=st.checkbox('Confirmo que reemplazaré los datos del Paso 10. Los Pasos 1–9 no se alteran.',key='p10_restore_confirm')
        if f and st.button('Restaurar respaldo del Paso 10',disabled=not confirmation):
            try:
                good,_=run(lambda:s.restore(json.loads(f.getvalue()),confirmation),'Respaldo del Paso 10 restaurado')
                if good:st.rerun()
            except json.JSONDecodeError as e:st.error('JSON inválido: '+str(e))
        imported=s.rows('SELECT * FROM p10_importaciones ORDER BY fecha DESC LIMIT 12')
        if imported:
            st.subheader('Últimas importaciones')
            st.dataframe(pd.DataFrame(imported)[['fuente','agregados','actualizados','omitidos','fecha']],hide_index=True,use_container_width=True)

def page(name):
    if name==NAV[0]:perception_page()
    elif name==NAV[1]:comparison_page()
    elif name==NAV[2]:stories_page()
    elif name==NAV[3]:dashboard_page()
    elif name==NAV[4]:assessment_page()
    else:st.error('Módulo desconocido del Paso 10')
    backup_panel()
