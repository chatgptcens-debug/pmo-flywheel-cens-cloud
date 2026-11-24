"""Centro interno de relacionamiento · PMO FLYWHEEL CENS V0.29.

No añade rutas ni menús: lo invoca el router original del Paso 01.
"""
from __future__ import annotations

from datetime import date
from html import escape
from io import StringIO
import csv

import pandas as pd
import streamlit as st

from . import interactions as ir
from .clients import ValidationError, list_clients, dependencies
from .catalog_manager import smart_choice


def _style():
    st.markdown('''<style>
    .rel-title{font-size:29px;color:#183650;font-weight:850;line-height:1.18;margin:6px 0}
    .rel-overline{color:#087d91;font-size:11px;font-weight:800;letter-spacing:1.1px}
    .rel-sub{color:#6b7f92;font-size:13px;margin-bottom:14px}
    .rel-kpi{background:linear-gradient(135deg,#fff,#f5f9ff);border:1px solid #dfebf3;
       box-shadow:0 4px 13px #20344b0a;border-radius:14px;padding:16px;min-height:113px}
    .rel-kpi .name{font-size:12px;font-weight:680;color:#536c81}
    .rel-kpi .value{font-size:28px;font-weight:830;color:#153354;letter-spacing:-.8px;margin:6px 0 0}
    .rel-kpi .meta{font-size:11px;color:#75899c}
    .rel-detail{border:1px solid #deebf4;border-radius:14px;background:#fbfdff;padding:16px}
    .rel-badge{display:inline-block;color:#075c78;background:#e6f4f8;border-radius:8px;
       padding:4px 8px;font-size:12px;font-weight:750}
    div[data-testid="stTabs"] button[role="tab"]{font-size:13px;font-weight:700}
    </style>''',unsafe_allow_html=True)


def _metric(label: str, value, detail: str):
    from .panel_superior import render_kpi_card_panel
    configuration={
        'Clientes contactados':('users','orange'),
        'Interacciones':('message','blue'),
        'Consultas pendientes':('file','purple'),
        'Compromisos pendientes':('clock','teal'),
    }
    icon,theme=configuration.get(label,('chart','orange'))
    st.markdown(render_kpi_card_panel(label=label,value=value,subtext=detail,
                                       icon_name=icon,theme=theme),unsafe_allow_html=True)


def _notify(error: Exception):
    st.error(str(error))


def _clients():
    return list_clients(status='Activos')


def _labels(people):
    return {p['id']:f"{p['codigo']} · {p['nombre']}" for p in people}


def _csv(rows, fields):
    output=StringIO()
    w=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore',delimiter=';')
    w.writeheader();w.writerows(rows)
    return ('\ufeff'+output.getvalue()).encode('utf-8')


def _day(value):
    try:return date.fromisoformat(str(value))
    except (ValueError,TypeError):return date.today()


@st.dialog('Registrar interacción con cliente',width='large')
def new_interaction():
    people=_clients()
    if not people:
        st.warning('Primero registre clientes activos en Clientes internos.');return
    labels=_labels(people)
    st.caption('Registre contactos que realmente ocurrieron. No constituye un diagnóstico validado.')
    with st.form('rel_new_interaction',clear_on_submit=False):
        client=st.selectbox('Cliente *',list(labels),format_func=lambda x:labels[x])
        a,b=st.columns(2)
        when=a.date_input('Fecha del contacto *',value=date.today(), format='YYYY/MM/DD')
        channel=b.selectbox('Canal *',ir.CHANNELS)
        c,d=st.columns(2)
        motive=c.selectbox('Motivo *',ir.MOTIVES)
        owner=smart_choice('Responsable PMO *','responsable',key='rel_new_owner',parent=d)
        description=st.text_area('Resumen de la interacción *',height=85)
        result=st.text_area('Resultado / acuerdos',height=65)
        preliminary=st.text_area('Necesidad preliminar (opcional)',height=65)
        transfer=st.checkbox('Marcar como antecedente potencial del Paso 02',value=False)
        with st.expander('Compromiso de seguimiento (opcional)'):
            commitment=st.text_area('Descripción del compromiso')
            cp_owner=smart_choice('Responsable del compromiso','responsable',key='rel_new_commit_owner')
            due=st.date_input('Fecha límite (opcional)',value=None, format='YYYY/MM/DD')
        actor=st.text_input('Registrado por *')
        sent=st.form_submit_button('Guardar interacción',type='primary',use_container_width=True)
    if sent:
        try:
            ir.create_interaction(client,when,channel,motive,description,owner,actor,result,
                                  preliminary,transfer,commitment,cp_owner,due)
            st.session_state['rel_flash']='Interacción guardada correctamente.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify(exc)


@st.dialog('Editar interacción',width='large')
def edit_interaction(row):
    with st.form('rel_edit_int'):
        a,b=st.columns(2)
        when=a.date_input('Fecha',value=_day(row['fecha']), format='YYYY/MM/DD')
        channel=b.selectbox('Canal',ir.CHANNELS,index=ir.CHANNELS.index(row['canal']))
        c,d=st.columns(2)
        motive=c.selectbox('Motivo',ir.MOTIVES,index=ir.MOTIVES.index(row['motivo']))
        owner=smart_choice('Responsable PMO','responsable',value=row['responsable'],key=f'rel_edit_owner_{row["id"]}',parent=d)
        description=st.text_area('Resumen',value=row['descripcion'])
        result=st.text_area('Resultado',value=row['resultado'])
        preliminary=st.text_area('Necesidad preliminar',value=row['necesidad_preliminar'])
        transfer=st.checkbox('Insumo potencial Paso 02',value=bool(row['insumo_paso2']))
        actor=st.text_input('Actualizado por *')
        sent=st.form_submit_button('Guardar cambios',type='primary')
    if sent:
        try:
            ir.edit_interaction(row['id'],when,channel,motive,description,owner,actor,result,preliminary,transfer)
            st.session_state['rel_flash']='Interacción actualizada.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify(exc)


@st.dialog('Nueva consulta',width='medium')
def new_consultation():
    people=_clients()
    if not people:
        st.warning('Primero registre clientes activos.');return
    labels=_labels(people)
    with st.form('rel_new_consult'):
        client=st.selectbox('Cliente *',list(labels),format_func=lambda x:labels[x])
        subject=st.text_input('Asunto *')
        category=st.selectbox('Categoría',['Información PMO','Servicios','Metodologías','Formación','Herramientas','Acompañamiento','Sugerencias','Otra'])
        priority=st.selectbox('Prioridad',ir.PRIORITIES,index=1)
        detail=st.text_area('Descripción *')
        owner=smart_choice('Responsable PMO','responsable',key='rel_consult_new_owner')
        actor=st.text_input('Registrado por *')
        submitted=st.form_submit_button('Guardar consulta',type='primary')
    if submitted:
        try:
            ir.create_consultation(client,subject,category,detail,owner,actor,priority)
            st.session_state['rel_flash']='Consulta registrada.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify(exc)


@st.dialog('Actualizar consulta')
def edit_consultation(row):
    with st.form('rel_update_consult'):
        status=st.selectbox('Estado',ir.TICKET_STATES,index=ir.TICKET_STATES.index(row['estado']))
        priority=st.selectbox('Prioridad',ir.PRIORITIES,index=ir.PRIORITIES.index(row['prioridad']))
        owner=smart_choice('Responsable PMO','responsable',value=row['responsable'],key=f'rel_consult_edit_owner_{row["id"]}')
        answer=st.text_area('Respuesta y seguimiento',value=row['respuesta'] or '')
        actor=st.text_input('Actualizado por *')
        sent=st.form_submit_button('Guardar seguimiento',type='primary')
    if sent:
        try:
            ir.update_consultation(row['id'],status,priority,owner,answer,actor)
            st.session_state['rel_flash']='Consulta actualizada.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify(exc)


@st.dialog('Agregar compromiso a interacción')
def new_commitment(interaction_id):
    with st.form('rel_new_task'):
        description=st.text_area('Compromiso *')
        owner=st.text_input('Responsable *')
        due=st.date_input('Fecha límite (opcional)',value=None, format='YYYY/MM/DD')
        actor=st.text_input('Registrado por *')
        sent=st.form_submit_button('Guardar compromiso',type='primary')
    if sent:
        try:
            ir.add_commitment(interaction_id,description,owner,actor,due)
            st.session_state['rel_flash']='Compromiso registrado.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify(exc)


@st.dialog('Seguimiento del compromiso')
def edit_commitment(row):
    st.write(row['descripcion'])
    with st.form('rel_task_followup'):
        state=st.selectbox('Estado',ir.COMMITMENT_STATES,index=ir.COMMITMENT_STATES.index(row['estado']))
        observation=st.text_area('Observaciones',value=row['observaciones'] or '')
        actor=st.text_input('Actualizado por *')
        sent=st.form_submit_button('Guardar seguimiento',type='primary')
    if sent:
        try:
            ir.update_commitment(row['id'],state,observation,actor)
            st.session_state['rel_flash']='Compromiso actualizado.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify(exc)


def _interaction_tab():
    left,right=st.columns([1.7,1],gap='medium')
    with left:
        st.subheader('Registro de interacciones')
        a,b=st.columns([1.5,1])
        query=a.text_input('Buscar cliente o asunto',placeholder='Nombre, código o asunto...',key='rel_int_search')
        dept=b.selectbox('Dependencia',['Todas',*dependencies()],key='rel_int_dep')
        channel=st.selectbox('Canal',['Todos',*ir.CHANNELS],key='rel_int_channel')
        rows=ir.list_interactions(dependency='' if dept=='Todas' else dept,
                                  channel='' if channel=='Todos' else channel,search=query)
        st.caption(f'{len(rows)} interacción(es) registradas')
        if rows:
            df=pd.DataFrame([{'Fecha':r['fecha'],'Cliente':r['cliente'],'Dependencia':r['dependencia'],
                              'Motivo':r['motivo'],'Canal':r['canal'],'Responsable':r['responsable'],
                              'Insumo P2':'Sí' if r['insumo_paso2'] else 'No'} for r in rows])
            selected=st.dataframe(df,hide_index=True,use_container_width=True,height=375,
                     on_select='rerun',selection_mode='single-row',key='rel_int_grid')
            picks=selected.selection.rows
            chosen=rows[picks[0]] if picks else rows[0]
            st.download_button('Exportar interacciones (CSV)',data=_csv(rows,
              ['fecha','codigo_cliente','cliente','dependencia','canal','motivo','descripcion',
               'responsable','resultado','necesidad_preliminar','insumo_paso2']),
              file_name='PMO_interacciones.csv',mime='text/csv',key='rel_export_int')
        else:
            chosen=None;st.info('Aún no hay interacciones con los filtros actuales.')
    with right:
        st.subheader('Ficha de relacionamiento')
        if not chosen:
            st.info('Seleccione o registre una interacción para consultar su detalle.');return
        with st.container(border=True):
            st.markdown('**'+escape(chosen['cliente'])+'**')
            st.caption(f"{chosen['codigo_cliente']} · {chosen['dependencia']}")
            st.caption(f"{chosen['fecha']} · {chosen['canal']} · {chosen['motivo']}")
            st.write(chosen['descripcion'])
            st.markdown('**Resultado:**')
            st.write(chosen['resultado'] or 'Sin información registrada')
            st.markdown('**Necesidad preliminar:**')
            st.write(chosen['necesidad_preliminar'] or 'Sin información registrada')
            if chosen['insumo_paso2']:
                st.info('Antecedente potencial para el Paso 02. No constituye necesidad validada.')
            a,b=st.columns(2)
            if a.button('Editar interacción',key='rel_int_edit',use_container_width=True):edit_interaction(chosen)
            if b.button('Añadir compromiso',key='rel_int_task',use_container_width=True):new_commitment(chosen['id'])
            timeline=ir.client_timeline(chosen['cliente_id'])
            with st.expander(f'Historial del cliente ({len(timeline)} registros)'):
                for entry in timeline[:25]:
                    title=(entry.get('motivo') or entry.get('asunto') or entry.get('descripcion') or '')
                    st.markdown(f"**{escape(entry['tipo'])} · {escape(str(entry['fecha'])[:10])}**")
                    st.caption(str(title)[:240])


def _consultation_tab():
    st.subheader('Bandeja de consultas y solicitudes')
    search,status,prio=st.columns([2,1,1])
    query=search.text_input('Buscar consultas',key='rel_tkt_search')
    state=status.selectbox('Estado',['Todos',*ir.TICKET_STATES],key='rel_tkt_state')
    priority=prio.selectbox('Prioridad',['Todas',*ir.PRIORITIES],key='rel_tkt_priority')
    rows=ir.list_consultations('' if state=='Todos' else state,
                               '' if priority=='Todas' else priority,query)
    left,right=st.columns([1.7,1],gap='medium')
    with left:
        st.caption(f'{len(rows)} consulta(s)')
        if rows:
            df=pd.DataFrame([{'Fecha':r['creado_en'][:10],'Cliente':r['cliente'],
                  'Asunto':r['asunto'],'Prioridad':r['prioridad'],'Estado':r['estado']} for r in rows])
            ev=st.dataframe(df,hide_index=True,use_container_width=True,height=335,
                 on_select='rerun',selection_mode='single-row',key='rel_cons_grid')
            sel=ev.selection.rows
            chosen=rows[sel[0]] if sel else rows[0]
            st.download_button('Exportar consultas (CSV)',data=_csv(rows,
              ['creado_en','codigo_cliente','cliente','asunto','categoria','descripcion',
               'responsable','prioridad','estado','respuesta']),
               file_name='PMO_consultas.csv',mime='text/csv',key='rel_export_tkt')
        else: chosen=None;st.info('No existen consultas para los filtros seleccionados.')
    with right:
        if chosen:
            with st.container(border=True):
                st.markdown('**'+escape(chosen['asunto'])+'**')
                st.caption(chosen['cliente']+' · '+chosen['dependencia'])
                st.write(f"Estado: **{chosen['estado']}** · Prioridad: **{chosen['prioridad']}**")
                st.write(chosen['descripcion'])
                st.markdown('**Respuesta**')
                st.write(chosen['respuesta'] or 'Sin información registrada')
                if st.button('Actualizar consulta',key='rel_tkt_update',use_container_width=True):
                    edit_consultation(chosen)
        else:st.info('Seleccione una consulta para consultar y responder.')


def _commitments_tab():
    st.subheader('Compromisos y seguimiento')
    state=st.selectbox('Filtrar compromisos',['Todos',*ir.COMMITMENT_STATES],key='rel_task_filter')
    rows=ir.list_commitments('' if state=='Todos' else state)
    if not rows:
        st.info('No hay compromisos registrados para el estado seleccionado.');return
    table=pd.DataFrame([{'Cliente':r['cliente'],'Compromiso':r['descripcion'],
          'Responsable':r['responsable'],'Vence':r['vence_en'] or 'Sin fecha',
          'Estado':r['estado']} for r in rows])
    ev=st.dataframe(table,hide_index=True,use_container_width=True,height=360,
                    on_select='rerun',selection_mode='single-row',key='rel_tasks_grid')
    sel=ev.selection.rows
    item=rows[sel[0]] if sel else rows[0]
    with st.container(border=True):
        st.markdown('**'+escape(item['cliente'])+'**')
        st.write(item['descripcion'])
        st.caption(f"Responsable: {item['responsable']} · Fecha límite: {item['vence_en'] or 'Sin fecha'}")
        if item['observaciones']:st.write('Observación: '+item['observaciones'])
        if st.button('Actualizar seguimiento',key='rel_task_update'):edit_commitment(item)


def _results_tab():
    metrics=ir.metrics()
    st.subheader('Resultados verificables del relacionamiento')
    st.caption('Un contacto corresponde a una interacción registrada o consulta formal. '
               'No se suman automáticamente asistentes a eventos ni descargas de materiales.')
    a,b=st.columns(2)
    a.metric('Clientes contactados',f"{metrics['contacted']} de {metrics['active']}")
    b.metric('Cobertura de contacto',f"{metrics['coverage']:.0f}%" if metrics['coverage'] is not None else 'No calculable')
    st.metric('Antecedentes potenciales Paso 02',metrics['preliminary'],help='No son necesidades validadas.')
    data=ir.department_summary()
    if data:
        df=pd.DataFrame(data).rename(columns={'dependencia':'Dependencia','objetivo':'Clientes objetivo',
                                                  'contactados':'Clientes contactados'})
        st.dataframe(df,hide_index=True,use_container_width=True)
    st.info('Productos: contactos y consultas registradas. Resultados: participación y respuestas documentadas. '
            'Beneficios y necesidades validadas requieren verificación posterior.')


def render_interactions():
    ir.initialize()
    _style()
    st.markdown('<div class="rel-overline">PASO 01 · GENERACIÓN DE CONCIENCIA</div>',unsafe_allow_html=True)
    left,right=st.columns([3.7,1.7],vertical_alignment='bottom')
    with left:
        st.markdown('<div class="rel-title">Consultas e interacciones</div>',unsafe_allow_html=True)
        st.markdown('<div class="rel-sub">Relacionamiento con clientes internos, solicitudes y seguimiento de compromisos.</div>',unsafe_allow_html=True)
    with right:
        a,b=st.columns(2)
        if a.button('＋ Interacción',type='primary',key='rel_open_inter',use_container_width=True):new_interaction()
        if b.button('＋ Consulta',key='rel_open_cons',use_container_width=True):new_consultation()
    msg=st.session_state.pop('rel_flash',None)
    if msg:st.success(msg)
    numbers=ir.metrics()
    specs=[('Clientes contactados',numbers['contacted'],f"De {numbers['active']} clientes activos"),
           ('Interacciones',numbers['interactions'],'Contactos documentados'),
           ('Consultas pendientes',numbers['tickets_pending'],'Requieren respuesta'),
           ('Compromisos pendientes',numbers['commitments_pending'],'Pendiente o en curso')]
    for col,(label,value,desc) in zip(st.columns(4),specs):
        with col:_metric(label,value,desc)
    st.write('')
    interactions,consultations,commitments,results=st.tabs([
        'Interacciones','Consultas y solicitudes','Compromisos','Resultados'])
    with interactions:_interaction_tab()
    with consultations:_consultation_tab()
    with commitments:_commitments_tab()
    with results:_results_tab()
