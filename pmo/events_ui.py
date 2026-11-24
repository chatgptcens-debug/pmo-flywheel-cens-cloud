"""Interfaz ejecutiva del Paso 01 · Eventos y campañas. Exclusiva para V0.25.

No crea un router, sidebar ni logos adicionales: utiliza la V0.21/V0.24 como base.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from io import BytesIO
from html import escape

import pandas as pd
import streamlit as st
from .staff_picker import staff_picker

from . import awareness as aw
from . import events_media as em
from .clients import ValidationError, list_clients
from .catalog_manager import smart_choice


def _css():
    st.markdown('''<style>
    .events-title{font-size:30px;font-weight:850;color:#172947;letter-spacing:-.8px;margin:.25rem 0 .12rem}
    .events-eyebrow{font-size:11px;font-weight:800;color:#0755AA;letter-spacing:1.2px;text-transform:uppercase}
    .events-description{font-size:13px;color:#60738a;margin:0 0 15px}
    .events-kpi{padding:19px 18px;border-radius:14px;background:linear-gradient(145deg,#fff,#F1F7FE);
      border:1px solid #D8E6F4;box-shadow:0 4px 15px rgba(17,45,75,.06);min-height:122px}
    .events-kpi-top{font-size:12px;font-weight:650;color:#546880}
    .events-kpi-val{font-size:29px;color:#172C52;font-weight:850;margin:5px 0 0}
    .events-kpi-desc{font-size:11px;color:#718398}
    .events-subhead{font-size:17px;font-weight:800;color:#172947;margin:.1rem 0 .3rem}
    .events-tag{display:inline-block;border-radius:8px;padding:4px 9px;background:#EAF4FC;color:#1258A1;font-size:12px;font-weight:750}
    .events-card-label{font-size:12px;color:#70849A;font-weight:650;margin:.35rem 0 0}
    .events-card-value{font-size:13px;color:#233B57;font-weight:700;margin:0 0 .55rem}
    .events-empty{padding:32px 20px;background:#F7FAFD;border:1px dashed #D2DFEA;border-radius:12px;color:#617B94;text-align:center}
    div[data-testid="stTabs"] button[role="tab"]{font-size:12.5px;font-weight:700;border-radius:8px 8px 0 0;padding:11px 17px}
    div[data-testid="stTabs"] button[aria-selected="true"]{color:#0755AA!important}
    @media(max-width:1050px){.events-kpi{padding:12px;min-height:110px}.events-kpi-val{font-size:23px}}
    </style>''', unsafe_allow_html=True)


def _metric(label, value, subtitle):
    from .panel_superior import render_kpi_card_panel
    configuration={
        'Actividades realizadas':('calendar','orange'),
        'Asistentes únicos':('users','blue'),
        'Asistencias acumuladas':('chart','purple'),
        'Campañas registradas':('layers','teal'),
    }
    icon,theme=configuration.get(label,('chart','orange'))
    st.markdown(render_kpi_card_panel(label=label,value=value,subtext=subtitle,
                                       icon_name=icon,theme=theme),unsafe_allow_html=True)


def _as_date(value, default=None):
    try: return date.fromisoformat(str(value))
    except (ValueError, TypeError): return default or date.today()


def _notify_error(exc):
    st.error(str(exc))


def _safe_date(value):
    return str(value or 'Sin información registrada')


@st.dialog('Nueva actividad · PMO',width='large')
def _new_activity(default_kind='Evento'):
    st.caption('Complete los datos generales. Después podrá incorporar asistentes y evidencias.')
    kind=st.radio('Tipo de actividad *',['Evento','Campaña'],horizontal=True,
                  index=0 if default_kind=='Evento' else 1)
    with st.form('evt_create_form'):
        name=st.text_input('Nombre *')
        desc=st.text_area('Descripción',height=75)
        obj=st.text_area('Objetivo de sensibilización',height=75)
        a,b=st.columns(2)
        day=a.date_input('Fecha *',value=date.today(), format='YYYY/MM/DD')
        mode=b.selectbox('Modalidad / canal', ['Presencial','Virtual','Mixta','Correo','Teams','Portal','Otro'])
        audience=smart_choice('Público objetivo','publico_objetivo',key='evt_new_audience')
        c,d=st.columns(2)
        owner=staff_picker('Responsable *',key='evt_new_owner')
        states=em.STATUS_EVENT if kind=='Evento' else em.STATUS_CAMPAIGN
        status=d.selectbox('Estado *',states)
        actor=st.text_input('Registrado por *')
        submitted=st.form_submit_button('Guardar actividad',type='primary',use_container_width=True)
    if submitted:
        try:
            ent,eid=em.create_activity(kind=kind,title=name,day=day,audience=audience,mode=mode,
                    owner=owner,status=status,description=desc,objective=obj,actor=actor)
            st.session_state['evt_selected_id' if ent=='evento' else 'evt_campaign_open']=eid
            st.session_state['evt_flash']='Actividad creada. Abra su ficha para registrar evidencias o resultados.'
            st.rerun()
        except (ValidationError,ValueError) as exc:_notify_error(exc)


@st.dialog('Editar actividad',width='large')
def _edit_activity(ent,entity_id):
    row=em.fetch_event(entity_id) if ent=='evento' else em.fetch_campaign(entity_id)
    if not row:
        st.warning('La actividad no existe.');return
    is_evt=ent=='evento'
    with st.form(f'evt_edit_{ent}'):
        title=st.text_input('Nombre *',value=row['titulo'])
        description=st.text_area('Descripción',value=row.get('descripcion',''))
        obj=st.text_area('Objetivo de sensibilización',value=row.get('objetivo',''))
        day=st.date_input('Fecha',value=_as_date(row['fecha'] if is_evt else row['fecha_inicio']), format='YYYY/MM/DD')
        options=['Presencial','Virtual','Mixta','Correo','Teams','Portal','Otro']
        existing=row.get('modalidad','') if is_evt else row.get('canal','')
        if existing not in options: options=[existing]+options
        mode=st.selectbox('Modalidad / canal',options,index=options.index(existing))
        audience=smart_choice('Público objetivo','publico_objetivo',value=row['publico'] if is_evt else row['audiencia'],key=f'evt_edit_audience_{entity_id}')
        owner=staff_picker('Responsable *',value=row['responsable'],key=f'evt_edit_owner_{entity_id}')
        statuses=em.STATUS_EVENT if is_evt else em.STATUS_CAMPAIGN
        status=st.selectbox('Estado',statuses,index=statuses.index(row['estado']))
        who=st.text_input('Modificado por *')
        save=st.form_submit_button('Guardar cambios',type='primary',use_container_width=True)
    if save:
        try:
            if is_evt:
                em.update_event(entity_id,title=title,day=day,kind=row['tipo'],audience=audience,
                    modality=mode,owner=owner,status=status,description=description,objective=obj,actor=who)
            else:
                em.update_campaign(entity_id,title=title,day=day,audience=audience,
                    channel=mode,owner=owner,status=status,description=description,objective=obj,actor=who)
            st.session_state['evt_flash']='Cambios guardados.';st.rerun()
        except (ValidationError,ValueError) as exc:_notify_error(exc)


@st.dialog('Registrar asistentes',width='large')
def _attendance_form(event_id):
    event=em.fetch_event(event_id)
    if not event:return
    if event['estado']=='Cancelado':
        st.warning('No se registra asistencia de eventos cancelados.');return
    people=list_clients(status='Activos')
    if not people:
        st.info('Primero registre clientes activos en el directorio.');return
    currently={r['cliente_id'] for r in aw.attendance_for_event(event_id) if r['asistio']}
    names={p['id']:f"{p['codigo']} · {p['nombre']}" for p in people}
    with st.form('evt_attendance_form'):
        ids=st.multiselect('Personas con asistencia confirmada',options=list(names),
            default=[id for id in currently if id in names],format_func=lambda id:names[id])
        st.caption('Al guardar se actualiza el listado de presentes. Los clientes no se eliminan del directorio.')
        who=st.text_input('Registrado por *')
        ok=st.form_submit_button('Guardar asistentes',type='primary')
    if ok:
        try:
            em.replace_attendance(event_id,ids,who)
            st.session_state['evt_flash']=f'Asistencias verificadas: {len(ids)}.';st.rerun()
        except ValidationError as exc:_notify_error(exc)


@st.dialog('Resultados de la actividad')
def _results_form(event_id):
    data=em.get_results(event_id)
    with st.form('evt_results_form'):
        meta=st.number_input('Meta de asistentes (opcional; 0 = sin meta)',min_value=0,step=1,value=data.get('meta_participantes') or 0)
        products=st.text_area('Productos generados',value=data.get('productos') or '')
        notes=st.text_area('Observaciones',value=data.get('observaciones') or '')
        who=st.text_input('Registrado por *')
        save=st.form_submit_button('Guardar resultados',type='primary')
    if save:
        try:
            em.save_results(event_id,int(meta) or None,products,notes,who)
            st.session_state['evt_flash']='Resultados guardados.';st.rerun()
        except ValidationError as exc:_notify_error(exc)


@st.dialog('Registrar satisfacción')
def _satisfaction_form(event_id):
    attendees=[r for r in aw.attendance_for_event(event_id) if r['asistio']==1]
    if not attendees:
        st.info('Registre primero asistentes confirmados.');return
    label={r['cliente_id']:r['nombre'] for r in attendees}
    with st.form('evt_satisfaction_form'):
        client=st.selectbox('Asistente',list(label),format_func=lambda k:label[k])
        score=st.select_slider('Calificación de satisfacción',options=[1,2,3,4,5],value=4)
        who=st.text_input('Registrado por *')
        submitted=st.form_submit_button('Guardar calificación',type='primary')
    if submitted:
        try:
            em.record_satisfaction(event_id,client,int(score),who)
            st.session_state['evt_flash']='Satisfacción registrada con trazabilidad.';st.rerun()
        except ValidationError as exc:_notify_error(exc)


@st.dialog('Agregar evidencias',width='large')
def _upload_files(ent,entity_id):
    row=em.fetch_event(entity_id) if ent=='evento' else em.fetch_campaign(entity_id)
    if not row:
        st.warning('No existe la actividad.');return
    st.caption(f"Archivos asociados a: {row['titulo']}")
    kind=st.radio('Clase de evidencia',['imagen','documento'],horizontal=True,
                  format_func=lambda x:'Fotografías' if x=='imagen' else 'Documentos')
    with st.form('evt_upload_form'):
        exts=list(em.IMAGE_TYPES) if kind=='imagen' else list(em.DOC_TYPES)
        uploads=st.file_uploader('Seleccione uno o varios archivos',type=exts,accept_multiple_files=True)
        title=st.text_input('Título común (opcional)')
        desc=st.text_area('Descripción o contexto',height=65)
        categories=['Registro fotográfico','Material de divulgación','Lista de asistencia','Presentación','Acta','Informe','Otro']
        category=st.selectbox('Categoría',categories)
        who=st.text_input('Cargado por *')
        st.caption('Máximo 10 MB por foto o 20 MB por documento. Archivos locales privados; no se publican enlaces.')
        sent=st.form_submit_button('Guardar evidencias',type='primary')
    if sent:
        if not uploads: st.error('Seleccione al menos un archivo.');return
        saved=[]
        try:
            # Todos los formatos y límites se validan antes de guardar el primer archivo.
            for upload in uploads:em._validate_content(upload.getvalue(),upload.name,kind)
            if not who.strip(): raise ValidationError('Indique quién carga las evidencias.')
            for upload in uploads:
                new_id=em.save_attachment(ent,entity_id,kind,upload.name,upload.getvalue(),
                    title=title or upload.name,description=desc,category=category,actor=who)
                saved.append(new_id)
            st.session_state['evt_flash']=f'{len(uploads)} archivo(s) almacenado(s) correctamente.';st.rerun()
        except (ValidationError,ValueError,OSError) as exc:
            for saved_id in saved:
                em.delete_attachment(saved_id,who)
            _notify_error(exc)


@st.dialog('Ver fotografía',width='large')
def _image_detail(attachment):
    path=em.file_path(attachment)
    if not path:st.warning('El archivo no está disponible.');return
    st.image(str(path),caption=attachment['titulo'],use_container_width=True)
    st.write(attachment['descripcion'] or 'Sin descripción')
    st.caption(f"Subido: {attachment['creado_en']} · {attachment['categoria'] or 'Sin categoría'}")


@st.dialog('Confirmar eliminación de evidencia')
def _remove_attachment(attachment):
    st.warning('Esta operación elimina el archivo del almacenamiento local y no se puede deshacer desde la aplicación.')
    st.write(attachment['nombre'])
    who=st.text_input('Responsable de eliminación *')
    confirm=st.checkbox('Confirmo que deseo eliminar esta evidencia')
    if st.button('Eliminar definitivamente',disabled=not confirm,type='primary'):
        try:
            em.delete_attachment(attachment['id'],who)
            st.session_state['evt_flash']='Evidencia eliminada y acción auditada.';st.rerun()
        except (ValidationError,OSError) as exc:_notify_error(exc)


def _gallery(ent,entity_id,*,show_uploader=True,scope='main'):
    files=em.list_attachments(ent,entity_id)
    photos=[a for a in files if a['clase']=='imagen']
    docs=[a for a in files if a['clase']=='documento']
    c1,c2=st.columns([3,1],vertical_alignment='center')
    with c1:st.markdown(f'**Galería de evidencias ({len(photos)})**')
    with c2:
        if show_uploader and st.button('＋ Evidencias',key=f'ev_add_{scope}_{ent}_{entity_id}',use_container_width=True):
            _upload_files(ent,entity_id)
    if not photos:st.caption('Sin fotografías registradas para esta actividad.')
    else:
        for start in range(0,len(photos),3):
            for col,att in zip(st.columns(3),photos[start:start+3]):
                with col:
                    file=em.file_path(att)
                    if file:
                        st.image(str(file),use_container_width=True)
                    else:st.warning('Archivo no localizado')
                    st.caption(att['titulo'] or att['nombre'])
                    a,b=st.columns(2)
                    with a:
                        if st.button('Ampliar',key='zoom_'+scope+'_'+att['id'],use_container_width=True):_image_detail(att)
                    with b:
                        if st.button('Quitar',key='del_'+scope+'_'+att['id'],use_container_width=True):_remove_attachment(att)
    with st.expander(f'Documentos asociados ({len(docs)})'):
        if not docs:st.caption('Sin documentos asociados.')
        for att in docs:
            st.markdown(f"**{att['titulo'] or att['nombre']}** · {att['categoria']}")
            st.caption(att['descripcion'] or 'Sin descripción')
            file=em.file_path(att)
            a,b=st.columns([3,1])
            with a:
                if file:st.download_button('Descargar · '+att['nombre'],data=file.read_bytes(),
                         file_name=att['nombre'],mime=att['mime'],key='download_'+scope+'_'+att['id'])
                else:st.warning('Documento no localizado')
            with b:
                if st.button('Eliminar',key='remove_'+scope+'_'+att['id']):_remove_attachment(att)


def _event_card(row,scope='agenda'):
    if not row:return
    with st.container(border=True):
        st.markdown('<div class="events-subhead">Ficha de la actividad</div>',unsafe_allow_html=True)
        status=row['estado']
        st.markdown(f"<span class='events-tag'>{escape(status)}</span>",unsafe_allow_html=True)
        st.markdown(f"### {escape(row['titulo'])}")
        st.caption(f"{row['fecha']} · {row['modalidad'] or 'Sin modalidad registrada'}")
        for label,key in [('Responsable','responsable'),('Público objetivo','publico'),('Descripción','descripcion'),('Objetivo de sensibilización','objetivo')]:
            st.markdown(f"<div class='events-card-label'>{escape(label)}</div><div class='events-card-value'>{escape(row.get(key) or 'Sin información registrada')}</div>",unsafe_allow_html=True)
        stats=em.event_stats(row['id']);result=em.get_results(row['id'])
        st.divider()
        st.markdown('**Resultados verificables**')
        a,b=st.columns(2)
        a.metric('Asistencias',stats['asistentes'])
        b.metric('Satisfacción',f"{stats['satisfaccion']:.1f}/5" if stats['respuestas'] else 'Sin información')
        if stats['respuestas']:st.caption(f"{stats['respuestas']} calificaciones registradas")
        meta=result.get('meta_participantes')
        if meta:
            st.metric('Cumplimiento de convocatoria',f'{stats["asistentes"]/meta*100:.0f}%')
            st.caption(f'{stats["asistentes"]} asistentes de meta {meta}. No mide beneficios de la PMO.')
        else:st.caption('Cumplimiento: sin meta de participantes registrada.')
        st.markdown('**Productos generados**')
        st.write(result.get('productos') or 'Sin información registrada')
        st.markdown('**Observaciones**')
        st.write(result.get('observaciones') or 'Sin información registrada')
        a,b=st.columns(2)
        with a:
            if st.button('Editar actividad',key='edit_'+scope+'_'+row['id'],use_container_width=True):_edit_activity('evento',row['id'])
            if st.button('Asistencia',key='att_'+scope+'_'+row['id'],use_container_width=True):_attendance_form(row['id'])
        with b:
            if st.button('Resultados',key='result_'+scope+'_'+row['id'],use_container_width=True):_results_form(row['id'])
            if st.button('Satisfacción',key='score_'+scope+'_'+row['id'],use_container_width=True):_satisfaction_form(row['id'])
        st.divider()
        _gallery('evento',row['id'],scope=scope)



@st.dialog('Confirmar eliminación de campaña')
def _delete_campaign_dialog(campaign_id):
    row=em.fetch_campaign(campaign_id)
    if not row:
        st.warning('La campaña ya no existe.');return
    st.warning('Esta operación elimina definitivamente la campaña y no puede deshacerse desde la APP. '
               'Se guardará un respaldo local de la base de datos y el registro de auditoría.')
    st.markdown(f"**Campaña:** {escape(row['titulo'])}")
    attached=em.list_attachments('campana',campaign_id)
    if attached:
        st.error(f'Hay {len(attached)} evidencia(s) asociada(s). '
                 'Ciérralo y elimínalas primero desde la galería de la campaña.')
        return
    who=st.text_input('Responsable de eliminación *',key='delete_campaign_actor_'+campaign_id)
    confirmed=st.checkbox('Confirmo la eliminación definitiva de esta campaña',
                          key='delete_campaign_confirm_'+campaign_id)
    if st.button('Eliminar campaña definitivamente', type='primary',
                 disabled=not confirmed or not who.strip(), key='delete_campaign_commit_'+campaign_id):
        try:
            backup=em.delete_campaign(campaign_id,who)
            st.session_state.pop('evt_campaign_open',None)
            st.session_state['evt_flash']='Campaña eliminada y auditada. Respaldo: '+str(backup)
            st.rerun()
        except (ValidationError,OSError) as exc:_notify_error(exc)


def _campaign_card(row):
    if not row:return
    with st.container(border=True):
        imgs=[x for x in em.list_attachments('campana',row['id']) if x['clase']=='imagen']
        if imgs:
            f=em.file_path(imgs[0]);
            if f:st.image(str(f),use_container_width=True)
        st.markdown(f"### {escape(row['titulo'])}")
        st.caption(f"{row['fecha_inicio']} · {row['estado']} · {row['canal'] or 'Canal sin registrar'}")
        st.write(row.get('descripcion') or 'Sin descripción registrada')
        st.markdown('**Objetivo de sensibilización**')
        st.write(row.get('objetivo') or 'Sin información registrada')
        st.caption('Público objetivo: '+(row['audiencia'] or 'Sin información registrada'))
        st.caption('Responsable: '+row['responsable'])
        st.caption(f"Evidencias registradas: {len(em.list_attachments('campana',row['id']))}")
        edit_col,delete_col=st.columns([3,1])
        with edit_col:
            if st.button('Editar campaña',key='edit_campaign_'+row['id'],use_container_width=True):
                _edit_activity('campana',row['id'])
        with delete_col:
            if st.button('Eliminar',key='delete_campaign_'+row['id'],use_container_width=True):
                _delete_campaign_dialog(row['id'])
        st.divider();_gallery('campana',row['id'])


def _agenda_tab(events):
    st.markdown('<div class="events-subhead">Agenda de sensibilización</div>',unsafe_allow_html=True)
    f1,f2,f3,f4=st.columns([2,1,1,1])
    q=f1.text_input('Buscar actividad',placeholder='Buscar por nombre...',key='ev_search')
    status=f2.selectbox('Estado',['Todos',*em.STATUS_EVENT],key='ev_filter_status')
    modes=sorted({row['modalidad'] for row in events if row.get('modalidad')})
    mode=f3.selectbox('Modalidad',['Todas',*modes],key='ev_filter_mode')
    start=f4.date_input('Desde',value=None,key='ev_filter_start', format='YYYY/MM/DD')
    end=st.date_input('Hasta',value=None,key='ev_filter_end', format='YYYY/MM/DD')
    if start and end and start>end:st.warning('La fecha inicial es posterior a la final.')
    filtered=[r for r in events if (not q or q.casefold() in r['titulo'].casefold())
             and (status=='Todos' or r['estado']==status) and (mode=='Todas' or r['modalidad']==mode)
             and (not start or r['fecha']>=start.isoformat()) and (not end or r['fecha']<=end.isoformat())]
    st.caption(f'{len(filtered)} actividad(es) en el filtro')
    left,right=st.columns([1.7,1],gap='medium')
    with left:
        with st.container(border=True):
            if not filtered:st.info('No existen actividades para los filtros seleccionados.')
            else:
                grid=pd.DataFrame([{'Fecha':r['fecha'],'Actividad':r['titulo'],
                     'Modalidad':r['modalidad'],
                     'Estado':{'Realizado':'🟢','Programado':'🔵','Borrador':'⚪','Cancelado':'🔴'}.get(r['estado'],'')+' '+r['estado'],
                     'Asistentes':r['asistentes'],
                     'Evidencias':len(em.list_attachments('evento',r['id']))} for r in filtered])
                event=st.dataframe(grid,hide_index=True,use_container_width=True,height=min(480,100+len(grid)*38),
                                    on_select='rerun',selection_mode='single-row',key='evt_agenda_dataframe')
                indices=event.selection.rows
                if indices and 0<=indices[0]<len(filtered):
                    click_id=filtered[indices[0]]['id']
                    # No sobrescribir la elección manual del selector cuando
                    # la tabla mantiene una selección antigua en reruns posteriores.
                    if st.session_state.get('evt_last_table_selection') != click_id:
                        st.session_state['evt_last_table_selection']=click_id
                        st.session_state['evt_selected_id']=click_id
                        st.session_state['evt_agenda_lookup']=click_id
                choices={r['id']:f"{r['fecha']} · {r['titulo']}" for r in filtered}
                selected=st.session_state.get('evt_selected_id')
                if selected not in choices:selected=filtered[0]['id']
                if st.session_state.get('evt_agenda_lookup') not in choices:
                    st.session_state['evt_agenda_lookup']=selected
                st.selectbox('Consultar ficha',list(choices),index=list(choices).index(selected),
                             format_func=lambda id:choices[id],key='evt_agenda_lookup',on_change=_sync_agenda_selection)
                st.session_state['evt_selected_id']=st.session_state.get('evt_agenda_lookup',selected)
    with right:
        selected=next((r for r in filtered if r['id']==st.session_state.get('evt_selected_id')),None)
        if selected:_event_card(selected)
        else:st.info('Seleccione una actividad para visualizar su ficha.')


def _sync_agenda_selection():
    st.session_state['evt_selected_id']=st.session_state['evt_agenda_lookup']


def _campaign_tab(campaigns):
    a,b=st.columns([4,1],vertical_alignment='bottom')
    a.markdown('<div class="events-subhead">Campañas de sensibilización</div>',unsafe_allow_html=True)
    if b.button('＋ Crear campaña',use_container_width=True):_new_activity('Campaña')
    if not campaigns:st.info('Todavía no se han registrado campañas.');return
    st.caption(f'{len(campaigns)} campañas registradas · Seleccione una tarjeta para consultar sus evidencias.')
    for offset in range(0,len(campaigns),3):
        cols=st.columns(3)
        for col,record in zip(cols,campaigns[offset:offset+3]):
            with col:
                with st.container(border=True):
                    imgs=em.list_attachments('campana',record['id'],file_class='imagen')
                    if imgs:
                        img=em.file_path(imgs[0])
                        if img:st.image(str(img),use_container_width=True)
                        else:st.caption('Fotografía no localizada')
                    else:
                        st.markdown('<div class="events-empty">📣<br/>Sin portada fotográfica</div>',unsafe_allow_html=True)
                    st.markdown('**'+escape(record['titulo'])+'**')
                    st.caption(f"{record['fecha_inicio']} · {record['estado']} · {record['canal'] or 'Canal pendiente'}")
                    st.caption(f"{len(em.list_attachments('campana',record['id']))} evidencia(s)")
                    if st.button('Ver campaña',key='evt_camp_card_'+record['id'],use_container_width=True):
                        st.session_state['evt_campaign_open']=record['id']
    selected=st.session_state.get('evt_campaign_open')
    if selected not in {record['id'] for record in campaigns}:
        selected=campaigns[0]['id']
    st.divider()
    _campaign_card(next(r for r in campaigns if r['id']==selected))


def _calendar_tab(events):
    st.markdown('<div class="events-subhead">Calendario de actividades</div>',unsafe_allow_html=True)
    if 'evt_cal_month' not in st.session_state:st.session_state['evt_cal_month']=date.today().replace(day=1)
    month=st.session_state['evt_cal_month']
    a,b,c=st.columns([1,4,1])
    if a.button('◀ Mes anterior',use_container_width=True,key='evt_cal_prev'):
        st.session_state['evt_cal_month']=(month-timedelta(days=1)).replace(day=1)
        st.rerun()
    month_names=['','Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    b.markdown(f"### {month_names[month.month]} {month.year}")
    if c.button('Mes siguiente ▶',use_container_width=True,key='evt_cal_next'):
        st.session_state['evt_cal_month']=date(month.year+ (month.month//12),month.month%12+1,1)
        st.rerun()
    month=st.session_state['evt_cal_month']
    st.caption('🟢 Realizado   🔵 Programado   ⚪ Borrador   🔴 Cancelado')
    day_events={}
    for ev in events:
        if ev['fecha'].startswith(f'{month.year:04d}-{month.month:02d}'):
            day_events.setdefault(int(ev['fecha'][-2:]),[]).append(ev)
    for col,day_name in zip(st.columns(7),['L','M','M','J','V','S','D']):
        col.markdown(f'**{day_name}**')
    for week_index,week in enumerate(calendar.monthcalendar(month.year,month.month)):
        for col,day in zip(st.columns(7),week):
            with col:
                if not day:st.write(' ');continue
                hits=day_events.get(day,[])
                mark=('🟢' if any(e['estado']=='Realizado' for e in hits) else
                      '🔵' if any(e['estado']=='Programado' for e in hits) else
                      '⚪' if any(e['estado']=='Borrador' for e in hits) else '🔴') if hits else ''
                if st.button(f'{day:02d} {mark}',key=f'evt_day_{month.year}_{month.month}_{day}',use_container_width=True):
                    st.session_state['evt_selected_day']=day
    chosen=st.session_state.get('evt_selected_day',0)
    matches=day_events.get(chosen,[])
    st.divider()
    if matches:
        labels={r['id']:f"{r['titulo']} · {r['estado']}" for r in matches}
        chosen_id=st.selectbox(f'Actividades del día {chosen}',list(labels),format_func=lambda key:labels[key])
        st.session_state['evt_selected_id']=chosen_id
        _event_card(next(r for r in matches if r['id']==chosen_id),scope='calendar')
    else:st.info('Seleccione un día que tenga actividades para consultar sus detalles.')


def _bank_tab(events,campaigns):
    st.markdown('<div class="events-subhead">Banco de evidencias</div>',unsafe_allow_html=True)
    options={'Todas':'', 'Eventos':'evento','Campañas':'campana'}
    a,b,c=st.columns(3)
    source=a.selectbox('Origen',list(options),key='evt_bank_entity')
    category=b.selectbox('Categoría',['Todas','Registro fotográfico','Material de divulgación','Lista de asistencia','Presentación','Acta','Informe','Otro'],key='evt_bank_category')
    typ=c.selectbox('Tipo',['Todos','Fotografía','Documento'],key='evt_bank_type')
    rows=em.list_attachments(options[source],file_class={'Fotografía':'imagen','Documento':'documento','Todos':''}[typ],
                         category='' if category=='Todas' else category)
    all_labels={**{row['id']:row['titulo'] for row in events},**{row['id']:row['titulo'] for row in campaigns}}
    q=st.text_input('Buscar evidencia o actividad',placeholder='Nombre del archivo, título o actividad...',key='evt_bank_search')
    dt=st.date_input('Cargadas desde',value=None,key='evt_bank_since', format='YYYY/MM/DD')
    rows=[r for r in rows if (not q or q.casefold() in (r['titulo']+' '+r['nombre']+' '+all_labels.get(r['entidad_id'],'')).casefold())
          and (not dt or r['creado_en'][:10]>=dt.isoformat())]
    st.caption(f'{len(rows)} evidencias registradas')
    if not rows:st.info('No hay archivos para los filtros actuales. Abra la ficha del evento o campaña para cargar evidencias.');return
    for start in range(0,len(rows),3):
        for col,att in zip(st.columns(3),rows[start:start+3]):
            with col:
                with st.container(border=True):
                    st.caption(all_labels.get(att['entidad_id'],'Actividad no disponible'))
                    file=em.file_path(att)
                    if att['clase']=='imagen' and file:st.image(str(file),use_container_width=True)
                    elif att['clase']=='documento':st.markdown('📄 **Documento asociado**')
                    else:st.warning('Archivo no localizado')
                    st.markdown('**'+escape(att['titulo'])+'**')
                    st.caption(f"{att['categoria']} · {att['creado_en'][:10]}")
                    if file and att['clase']=='documento':
                        st.download_button('Descargar',file.read_bytes(),file_name=att['nombre'],mime=att['mime'],key='bank_dl_'+att['id'])
                    if file and att['clase']=='imagen' and st.button('Ampliar',key='bank_zoom_'+att['id']):_image_detail(att)


def _reports_tab(events,campaigns,stats):
    st.markdown('<div class="events-subhead">Reportes de sensibilización</div>',unsafe_allow_html=True)
    st.caption('Indicadores de ejecución y alcance, no de beneficios logrados de la PMO.')
    if not events:st.info('Sin registros suficientes para construir reportes.');return
    rows=[]
    for row in events:
        ev_stats=em.event_stats(row['id']);result=em.get_results(row['id'])
        rows.append({'Fecha':row['fecha'],'Actividad':row['titulo'],'Estado':row['estado'],
                     'Modalidad':row['modalidad'],'Asistentes':ev_stats['asistentes'],
                     'Evidencias':ev_stats['evidencias'],
                     'Satisfacción':round(ev_stats['satisfaccion'],2) if ev_stats['respuestas'] else None,
                     'Meta asistentes':result.get('meta_participantes')})
    df=pd.DataFrame(rows)
    a,b,c=st.columns(3)
    a.metric('Eventos realizados',stats['realizados'])
    b.metric('Asistencias verificadas',stats['asistencias'])
    c.metric('Actividades con evidencia',sum(bool(r['Evidencias']) for r in rows))
    monthly=df.copy()
    monthly['Mes']=monthly['Fecha'].astype(str).str.slice(0,7)
    chart=monthly.groupby('Mes').apply(lambda g:(g['Estado']=='Realizado').sum(),include_groups=False).rename('Realizadas')
    if not chart.empty:st.bar_chart(chart)
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.download_button('⬇ Exportar reporte CSV',df.to_csv(index=False).encode('utf-8-sig'),
                       file_name='reporte_eventos_pmo.csv',mime='text/csv',key='evt_report_export')
    st.caption(f"Campañas registradas: {len(campaigns)} · Solo se cuenta la existencia, no la recepción o impacto de la campaña.")


def render_events():
    _css()
    a,b=st.columns([4.8,1.2],vertical_alignment='bottom')
    with a:
        st.markdown('<div class="events-eyebrow">PASO 01 · GENERACIÓN DE CONCIENCIA</div>',unsafe_allow_html=True)
        st.markdown('<div class="events-title">Eventos y campañas</div>',unsafe_allow_html=True)
        st.markdown('<div class="events-description">Planifique actividades, registre asistentes y gestione las evidencias de las campañas de la PMO.</div>',unsafe_allow_html=True)
    with b:
        if st.button('＋ Nueva actividad',type='primary',use_container_width=True,key='evt_new_activity'):_new_activity()
    if st.session_state.get('evt_flash'):
        st.success(st.session_state.pop('evt_flash'))
    ev=aw.events();campaigns=aw.campaigns();stats=em.summary()
    for col,data in zip(st.columns(4),[
       ('Actividades realizadas',stats['realizados'],'Eventos con estado Realizado'),
       ('Asistentes únicos',stats['unicos'],'Clientes distintos con asistencia'),
       ('Asistencias acumuladas',stats['asistencias'],'Registros de presencia válidos'),
       ('Campañas registradas',stats['campanas'],'Todos los estados de campaña')]):
        with col:_metric(*data)
    st.write('')
    tabs=st.tabs(['▦ Agenda de actividades','📣 Campañas','▦ Calendario','▧ Banco de evidencias','▥ Reportes'])
    with tabs[0]:_agenda_tab(ev)
    with tabs[1]:_campaign_tab(campaigns)
    with tabs[2]:_calendar_tab(ev)
    with tabs[3]:_bank_tab(ev,campaigns)
    with tabs[4]:_reports_tab(ev,campaigns,stats)
    from .value_info_panel import info_panel
    info_panel('Trazabilidad de actividades', 'La asistencia, la evidencia y la retroalimentación se registran en sus fichas; los contadores no equivalen automáticamente a beneficios logrados.')
    with st.expander('Importar eventos, campañas, asistencias y encuestas desde Excel', expanded=False):
        st.caption('La plantilla compartida admite también clientes y biblioteca. Los datos se asignan a sus módulos correspondientes; la vista previa exige confirmación antes de guardar.')
        from .ui import excel_import_page
        excel_import_page()

