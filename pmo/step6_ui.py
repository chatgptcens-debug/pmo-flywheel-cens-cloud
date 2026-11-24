"""Interfaz del Paso 6: las cuatro vistas del HTML original sobre SQLite compartida.
La operación no sustituye los requisitos de incorporación del Paso 5.
"""
from __future__ import annotations
import html
import json
from collections import Counter
from pathlib import Path
import streamlit as st
from .staff_picker import staff_picker
import pandas as pd
import streamlit.components.v1 as components
from . import step6 as s
from .ui import kpi
from .catalog_manager import smart_choice
from .client_picker import choose_client

NAV=list(s.MODULES)
CSS=Path(__file__).parent/'assets'/'step6_ux.css'
KANBAN=components.declare_component('pmo_cens_kanban6',path=str(Path(__file__).parent/'components'/'kanban6'))

def apply_step6_theme():
    st.markdown('<style>'+CSS.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)

def e(text):return html.escape(str(text if text is not None else ''))
def json_bytes(data):return json.dumps(data,indent=2,ensure_ascii=False,default=str).encode('utf-8')
def heading(label,title,desc):
    st.markdown(f'<div class="pmo-eyebrow">PASO 06 · {e(label)}</div><div class="pmo-title">{e(title)}</div><div class="pmo-subtitle">{e(desc)}</div>',unsafe_allow_html=True)
def metrics(cards):
    cols=st.columns(len(cards),gap='medium')
    for idx,(col,(name,value,detail,ic)) in enumerate(zip(cols,cards)):
        with col:kpi(name,str(value),detail,ic,('orange','blue','purple','teal')[idx%4])
def fmt_pct(v):return f'{v:.0f}%' if v is not None else '—'
def fmt_hours(v):return f'{v:.1f} h'.replace('.',',') if v is not None else '—'
def actor():return st.session_state.get('p6_actor','Equipo PMO')
def service_label(k):
    sr=s.service(k)
    return f'{sr["codigo"]} · {sr["nombre"]}' if sr else 'No disponible'
def alert_error(ex):st.error(str(ex))
def try_do(callback,success):
    try:
        out=callback();st.success(success);return True if out is None else out
    except (s.ValidationError,ValueError) as err:
        st.error(str(err));return None

@st.dialog('Registrar nueva solicitud',width='large')
def new_ticket_dialog():
    services=s.catalog()
    if not services:
        st.warning('Primero autoriza expresamente el servicio en Paso 05 → Adopción y transición; luego transfiérelo al catálogo del Paso 06 → Catálogo y ANS. Una ficha aprobada en Paso 04 no constituye autorización operativa.')
        return
    client_name,client_id,person=choose_client(st,'Cliente del Paso 01 (seleccionar nombre)',key='p6_new_client',optional=True)
    with st.form('p6_new_ticket_form'):
        st.caption('El ticket conserva una copia de los ANS numéricos vigentes al registrarse.')
        title=st.text_input('Asunto de la solicitud *')
        a,b=st.columns(2)
        with a:
            client=st.text_input('Nombre del cliente *',value=client_name,disabled=bool(person),key='p6_new_customer_value') if person else client_name
            department=smart_choice('Dependencia','dependencia',value=person.get('dependencia','') if person else '',key='p6_ticket_department')
            origin=st.selectbox('Origen de activación',s.ORIGINS)
        with b:
            service_id=st.selectbox('Servicio del catálogo', [x['id'] for x in services],format_func=service_label)
            email=st.text_input('Correo de contacto',value=person.get('correo','') or '' if person else '')
            priority=st.selectbox('Prioridad',s.PRIORITIES,index=1)
        a,b=st.columns(2)
        with a:project_type=st.selectbox('Tipo de proyecto vinculado (opcional)',s.PROJECT_TYPES)
        with b:complexity=st.selectbox('Complejidad del requerimiento',s.COMPLEXITIES)
        description=st.text_area('Descripción de la necesidad *')
        expected=st.text_area('Resultado esperado del cliente',height=72)
        channel=st.selectbox('Canal de atención',['Portal PMO','Correo','Teléfono','Presencial','Otro'])
        sr=s.service(service_id)
        mode=sr['ans_tipo'] if 'ans_tipo' in sr else 'Calendario'
        st.caption(f'Unidad del ANS confirmada en catálogo: **horas {"hábiles" if mode=="Hábil" else "calendario"}**. Los tiempos de esta solicitud conservarán una copia de los acuerdos y del calendario aplicable.')
        if mode=='Hábil':
            cfg=s.get_calendar(service_id)
            if not cfg.get('confirmed'):st.warning('Calendario corporativo pendiente de confirmar en Catálogo y ANS. No se podrá registrar un ticket con ANS hábiles sin confirmación.')
        op=sr['operativo_asignado'] if 'operativo_asignado' in sr else ''
        st.caption('Responsable operativo preasignado: '+(op or 'Sin definir; se requiere triaje manual'))
        l,r=st.columns(2)
        with l:r_h=st.text_input('ANS primera respuesta (horas '+('hábiles' if mode=='Hábil' else 'calendario')+')',value=str(sr['sla_respuesta_h'] or ''),key=f'p6_ans_r_{service_id}')
        with r:t_h=st.text_input('ANS resolución (horas '+('hábiles' if mode=='Hábil' else 'calendario')+')',value=str(sr['sla_resolucion_h'] or ''),key=f'p6_ans_s_{service_id}')
        ok=st.form_submit_button('Guardar nueva solicitud',type='primary')
    if ok:
        result=try_do(lambda:s.create_ticket({'titulo':title,'cliente':client,'dependencia':department,
               'correo':email,'cliente_id':client_id,'servicio_id':service_id,'origen':origin,'prioridad':priority,
               'descripcion':description,'resultado_esperado':expected,'canal':channel,
               'ans_respuesta_h':r_h,'ans_resolucion_h':t_h,'ans_tipo':mode,
               'tipo_proyecto':project_type,'complejidad':complexity},actor()),'Solicitud registrada')
        if result:st.session_state['p6_ticket_open']=result;st.rerun()

@st.dialog('Catálogo operativo y ANS',width='large')
def catalog_dialog():
    st.caption('Ruta preferente: importar servicios autorizados del Paso 5. La importación directa del Paso 4 se conserva para continuidad técnica y debe verificarse por separado.')
    all_=s.catalog()
    if all_:
        st.dataframe([{'Código':v['codigo'],'Servicio':v['nombre'],'ANS respuesta (h)':v['sla_respuesta_h'],'Unidad ANS':v.get('ans_tipo','Calendario'),
            'ANS resolución (h)':v['sla_resolucion_h'],'Origen':v['origen']} for v in all_],hide_index=True,use_container_width=True)
    if st.button('Importar servicios autorizados del Paso 5',type='primary'):
        result=try_do(s.import_step5_direct,'Transferencia autorizada consultada en SQLite')
        if result:st.info(str(result));st.rerun()
    left,right=st.columns(2)
    with left:
        if st.button('Importar servicios técnicamente preparados del Paso 4',use_container_width=True):
            result=try_do(s.import_step4_direct,'Catálogo consultado en la misma SQLite')
            if result:st.info(str(result));st.rerun()
    with right:
        file=st.file_uploader('O importar expediente JSON del Paso 4',type='json',key='p6_catalog_json')
        if file and st.button('Validar e importar JSON'):
            try:
                result=s.import_catalog(json.load(file));st.success(str(result));st.rerun()
            except (json.JSONDecodeError,s.ValidationError,ValueError) as ex:st.error(str(ex))
    st.divider()
    ids=['__new__']+[x['id'] for x in all_]
    selected=st.selectbox('Actualizar ANS / registrar un servicio',ids,
          format_func=lambda v:'＋ Entrada manual de catálogo' if v=='__new__' else service_label(v))
    old=s.service(selected) if selected!='__new__' else None
    candidates=s.operational_candidates(selected) if old else []
    if old and old.get('p4_id'):
        if candidates:st.caption('Roles R documentados y con evidencia de aprobación de la RACI del Paso 04. Selecciona y confirma el rol que atenderá solicitudes.')
        else:st.caption('No existe un rol R validado del Paso 04 para preasignación. Designa el responsable operativo expresamente.')
    with st.form('p6_catalog_form'):
        code=st.text_input('Código',value=old['codigo'] if old else '')
        name=st.text_input('Nombre del servicio *',value=old['nombre'] if old else '')
        description=st.text_area('Descripción',value=old['descripcion'] if old else '',height=74)
        responsible=st.text_input('Propietario del servicio',value=old['responsable'] if old else '')
        raci_choice=st.selectbox('Consultar rol RACI aprobado Paso 04 (no asigna persona)', ['Sin seleccionar',*candidates]) if candidates else 'Sin seleccionar'
        operative,operative_member_id=staff_picker('Integrante PMO responsable operativo para asignación automática',value=old.get('operativo_asignado','') if old else '',current_id=old.get('operativo_integrante_id') if old else None,return_id=True,help='Selecciona una persona del Equipo PMO del Paso 04. El rol RACI y el propietario institucional no asignan personas automáticamente.')
        mode=st.selectbox('Unidad de ANS', ['Calendario','Hábil'],index=['Calendario','Hábil'].index(old.get('ans_tipo','Calendario')) if old else 0)
        c1,c2=st.columns(2)
        with c1:response=st.text_input('ANS respuesta en horas (según unidad seleccionada)',value=str(old['sla_respuesta_h'] or '') if old else '')
        with c2:resolution=st.text_input('ANS resolución en horas (según unidad seleccionada)',value=str(old['sla_resolucion_h'] or '') if old else '')
        submit=st.form_submit_button('Guardar catálogo',type='primary')
    if submit:
        if raci_choice!='Sin seleccionar':st.caption('RACI seleccionada como referencia de rol; la persona operativa se designa exclusivamente desde Equipo PMO.')
        result=try_do(lambda:s.save_service({'codigo':code,'nombre':name,'descripcion':description,
                 'responsable':responsible,'sla_respuesta_h':response,'sla_resolucion_h':resolution,'ans_tipo':mode,'operativo_asignado':operative,'operativo_integrante_id':operative_member_id},
                 key=selected if old else None),'Servicio del catálogo guardado')
        if result:st.rerun()
    st.caption('Modificar el ANS del catálogo no cambia los ANS congelados en solicitudes anteriores.')
    if old:
        with st.expander('Calendario de horas hábiles · configuración y confirmación'):
            from .step6_calendar import DEFAULT_CONFIG
            cfg=s.get_calendar(selected)
            st.warning('La jornada inicial es una PLANTILLA, no acredita el horario laboral oficial de CENS. Revísala con el responsable del ANS y registra cierres corporativos.')
            with st.form('p6_calendar_configuration'):
                day_names=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
                days=st.multiselect('Días laborables',day_names,default=[day_names[d] for d in cfg['weekdays']])
                col1,col2=st.columns(2)
                with col1:slot1=st.text_input('Franja 1 (HH:MM-HH:MM)',value='-'.join(cfg['slots'][0]) if cfg['slots'] else '07:30-12:00')
                with col2:slot2=st.text_input('Franja 2 (HH:MM-HH:MM, opcional)',value='-'.join(cfg['slots'][1]) if len(cfg['slots'])>1 else '')
                closures=st.text_area('Días adicionales no hábiles de CENS (AAAA-MM-DD; uno por línea)',value='\n'.join(cfg.get('closures',[])),height=65)
                include_festivals=st.checkbox('Excluir festivos nacionales de Colombia',value=bool(cfg.get('national_holidays',True)))
                source=st.text_input('Fuente o documento de confirmación del calendario',value=cfg.get('source',''))
                verified=st.checkbox('Confirmo que horarios, días no hábiles y excepciones fueron verificados para este servicio',value=bool(cfg.get('confirmed')))
                savecal=st.form_submit_button('Guardar calendario del servicio',type='primary')
            if savecal:
                try:
                    newcfg={'timezone':'America/Bogota','weekdays':[day_names.index(d) for d in days],
                            'slots':[v.strip().split('-') for v in (slot1,slot2) if v.strip()],
                            'closures':[d.strip() for d in closures.splitlines() if d.strip()],
                            'national_holidays':include_festivals,'source':source,'confirmed':verified}
                    s.set_calendar(selected,newcfg);st.success('Calendario guardado para nuevas solicitudes; no modifica tickets previos.');st.rerun()
                except (ValueError,s.ValidationError) as ex:st.error(str(ex))

    if old:
        with st.expander('Escalamiento preventivo ANS · contacto por servicio'):
            esc=s.escalation_config(selected)
            st.caption('Las alertas se registran en la aplicación al 80% y 100%. Los correos requieren SMTP y un proceso programado en Windows.')
            with st.form(f'p6_escalation_{selected}'):
                contact=st.text_input('Responsable de escalamiento',value=esc['responsable'])
                mailbox=st.text_input('Correo de escalamiento',value=esc['correo'])
                enabled=st.checkbox('Habilitar envío al ejecutar el motor de notificaciones',value=bool(esc['habilitado']))
                if st.form_submit_button('Guardar contacto de escalamiento'):
                    if try_do(lambda:s.set_escalation_config(selected,mailbox,contact,enabled),'Escalamiento configurado'):st.rerun()

@st.dialog('Detalle de la solicitud',width='large')
def ticket_dialog(key):
    t=s.ticket(key)
    if not t:return st.error('Solicitud no encontrada')
    st.markdown(f'**{e(t["folio"])} · {e(t["titulo"])}**')
    st.caption(f'Estado: {t["estado"]} · Servicio: {service_label(t["servicio_id"])}')
    a,b,c=st.columns(3)
    with a:st.metric('ANS respuesta',s.sla_state(t,'respuesta')['estado'])
    with b:st.metric('ANS resolución',s.sla_state(t,'resolucion')['estado'])
    with c:st.metric('Calificación cliente',t['calificacion'] if t['calificacion'] is not None else '—')
    tabs=st.tabs(['Ficha','Atención y tareas','Conformidad y satisfacción','Conocimiento','Evidencias y comentarios','Historial'])
    with tabs[0]:
        with st.form('p6_update_ticket'):
            title=st.text_input('Asunto',value=t['titulo'])
            desc=st.text_area('Descripción',value=t['descripcion'],height=75)
            a,b=st.columns(2)
            with a:
                customer,chosen_id,person=choose_client(st,'Cliente · Directorio Paso 01',current=t['cliente'],key=f'p6_ticket_client_edit_{t["id"]}',optional=False)
                owner,owner_member_id=staff_picker('Responsable asignado',value=t['responsable'].strip(),current_id=t.get('responsable_integrante_id'),return_id=True)
            with b:
                priority=st.selectbox('Prioridad',s.PRIORITIES,index=s.PRIORITIES.index(t['prioridad']))
                area=smart_choice('Dependencia','dependencia',value=t['dependencia'],key=f'p6_ticket_area_{t["id"]}')
            expected=st.text_input('Resultado esperado',value=t['resultado_esperado'])
            x,y=st.columns(2)
            with x:project_type=st.selectbox('Tipo de proyecto',s.PROJECT_TYPES,index=s.PROJECT_TYPES.index(t.get('tipo_proyecto','No aplica')))
            with y:complexity=st.selectbox('Complejidad',s.COMPLEXITIES,index=s.COMPLEXITIES.index(t.get('complejidad','Sin clasificar')))
            saved=st.form_submit_button('Guardar ficha',type='primary')
        if saved:
            if try_do(lambda:s.update_ticket(key,{'titulo':title,'descripcion':desc,'cliente':customer,'cliente_id':chosen_id,
                         'responsable':owner,'responsable_integrante_id':owner_member_id,'prioridad':priority,'dependencia':area,'resultado_esperado':expected,
                         'tipo_proyecto':project_type,'complejidad':complexity},actor()),'Ficha actualizada') is not None:
                st.rerun()
        with st.expander('Reasignación con validación de capacidad WIP'):
            with st.form(f'p6_assign_wip_{key}'):
                target_operator,target_member_id=staff_picker('Nuevo responsable operativo',value=t['responsable'],current_id=t.get('responsable_integrante_id'),return_id=True)
                reason_wip=st.text_input('Justificación de excepción si supera WIP')
                if st.form_submit_button('Reasignar con control WIP'):
                    if try_do(lambda:s.wip_override_ticket(key,target_operator,reason_wip,actor(),member_id=target_member_id),'Asignación registrada'):st.rerun()
        st.caption(f'ANS congelado: respuesta {t["ans_respuesta_h"] or "Sin ANS"} h; resolución {t["ans_resolucion_h"] or "Sin ANS"} h · Unidad: {t.get("ans_tipo","Calendario")}')
        st.caption(f'Servicio versión: {t["version_servicio"] or "No especificada"}')
    with tabs[1]:
        if not t['primera_respuesta_en'] and t['estado']!=s.STAGES[0]:
            if st.button('Registrar primera respuesta',key='p6_first_reply'):
                if try_do(lambda:s.first_response(key,actor()),'Primera respuesta registrada'):st.rerun()
        st.caption('La primera respuesta se registra mediante acción explícita, no al asignar el servicio.')
        delivery=st.text_area('Entregable / terminación técnica',value=t['entregable'],key=f'p6_delivery_{key}',height=80)
        if st.button('Guardar entregable',key='p6_save_delivery'):
            if try_do(lambda:s.update_ticket(key,{'entregable':delivery},actor()),'Entregable guardado'):st.rerun()
        for task in s.tasks(key):
            checked=st.checkbox(task['descripcion'],value=bool(task['completada']),key=f'p6_task_{task["id"]}')
            if checked!=bool(task['completada']):
                if try_do(lambda:s.set_task(key,task['id'],checked,actor()),'Actividad actualizada'):st.rerun()
        newtask=st.text_input('Nueva actividad',key=f'p6_new_task_{key}')
        if st.button('Agregar actividad',key='p6_add_task'):
            if try_do(lambda:s.add_task(key,newtask,actor()),'Actividad registrada'):st.rerun()
    with tabs[2]:
        if t.get('protocolo_cierre')=='Conformidad':
            st.info('Para nuevas solicitudes, el cierre requiere conformidad mediante código de un solo uso o excepción autorizada con evidencia. La ausencia de respuesta no implica aceptación.')
            existing=s.client_feedback(key)
            if existing:
                st.dataframe(existing,hide_index=True,use_container_width=True)
            with st.expander('1 · Solicitar conformidad al cliente',expanded=not bool(existing)):
                st.caption('Código verificable por posesión; no equivale a autenticación corporativa SSO. Entrégalo al cliente por un canal institucional seguro.')
                with st.form(f'p6_invite_{key}'):
                    days=st.number_input('Vigencia del código (días)',min_value=1,max_value=30,value=7)
                    ref=st.text_input('Referencia de envío o comunicación')
                    issue=st.form_submit_button('Generar código de conformidad',type='primary')
                if issue:
                    secret=s.invite_conformity(key,actor(),int(days),ref)
                    st.session_state['p6_active_invitation']=(key,secret)
                if st.session_state.get('p6_active_invitation',('',))[0]==key:
                    st.code(st.session_state['p6_active_invitation'][1],language=None)
                    st.warning('Copia el código ahora y compártelo por un canal seguro. Solo se guarda su huella criptográfica.')
                for invite in s.conformity_invitations(key):
                    st.caption(f'{invite["emitida_en"]} · {invite["estado"]} · vence {invite["vence_en"]}')
            with st.expander('2 · Registrar la respuesta utilizando el código recibido',expanded=not bool(existing)):
                with st.form(f'p6_client_reply_{key}'):
                    code=st.text_input('Código de verificación',type='password')
                    decision=st.selectbox('Decisión sobre entregable',['Conforme','Solicita ajustes'])
                    csat=st.selectbox('Satisfacción CSAT (1–5 estrellas)',[None,1,2,3,4,5],format_func=lambda v:'Sin respuesta' if v is None else '★'*v)
                    nps=st.selectbox('Recomendación NPS (0–10, opcional)',[None,*range(11)],format_func=lambda v:'Sin respuesta' if v is None else str(v))
                    comment=st.text_area('Observaciones del cliente')
                    confirmed=st.form_submit_button('Registrar decisión verificada')
                if confirmed:
                    if try_do(lambda:s.submit_conformity(key,code,decision,csat,nps,comment),'Respuesta de conformidad registrada'):st.rerun()
            with st.expander('3 · Excepción de cierre administrativo (sin conformidad)'):
                st.warning('No se autoriza cierre automático por 48 horas sin respuesta. Una excepción requiere autorización, motivo y documento de respaldo.')
                with st.form(f'p6_close_exception_{key}'):
                    ex=st.checkbox('Solicitar cierre administrativo sin conformidad',value=bool(t['excepcion_evaluacion']))
                    why=st.text_area('Justificación',value=t['motivo_excepcion'])
                    approver=st.text_input('Persona que autoriza el cierre excepcional',value=t.get('excepcion_autorizador',''))
                    evidence=st.text_input('Referencia documental de autorización',value=t.get('excepcion_evidencia',''))
                    done=st.form_submit_button('Guardar excepción documentada')
                if done:
                    if try_do(lambda:s.update_ticket(key,{'excepcion_evaluacion':ex,'motivo_excepcion':why,'excepcion_autorizador':approver,'excepcion_evidencia':evidence},actor()),'Excepción registrada'):st.rerun()
        else:
            st.caption('Ticket histórico: conserva la captura original de calificación 1–10 y sus reglas de cierre.')
            with st.form('p6_feedback_form'):
                score=st.selectbox('Calificación del cliente (1–10)',[None,*range(1,11)],
                  index=0 if t['calificacion'] is None else t['calificacion'],format_func=lambda x:'Sin calificación' if x is None else str(x))
                acceptance=st.selectbox('¿Se cumplió el resultado esperado?',['','Sí','No','Parcialmente'],
                   index=['','Sí','No','Parcialmente'].index(t['aceptacion'] or ''))
                comment=st.text_area('Comentario del cliente',value=t['calificacion_comentario'],height=70)
                exception=st.checkbox('Cierre excepcional sin evaluación de cliente',value=bool(t['excepcion_evaluacion']))
                reason=st.text_area('Motivo de excepción',value=t['motivo_excepcion'],height=65)
                done=st.form_submit_button('Guardar evaluación histórica',type='primary')
            if done:
                if try_do(lambda:s.update_ticket(key,{'calificacion':score,'aceptacion':acceptance,
                      'calificacion_comentario':comment,'excepcion_evaluacion':exception,'motivo_excepcion':reason},actor()),
                      'Evaluación guardada'):st.rerun()
    with tabs[3]:
        st.caption('Soluciones frecuentes vinculadas al servicio. Solo los artículos publicados se muestran para preparar respuestas.')
        published=s.knowledge_articles(t['servicio_id'])
        if published:
            query=st.text_input('Buscar procedimientos',key=f'p6_knowledge_find_{key}')
            filt=[a for a in published if not query or query.lower() in (a['titulo']+' '+a['cuerpo']).lower()]
            for entry in filt:
                with st.expander(f'{entry["titulo"]} · v{entry["version"]}'):
                    st.write(entry['cuerpo'])
                    if entry['referencia']:st.caption('Referencia: '+entry['referencia'])
                    if st.button('Preparar respuesta con este procedimiento',key=f'p6_kb_use_{entry["id"]}'):
                        st.session_state[f'p6_kb_draft_{key}']=f'{entry["titulo"]} (v{entry["version"]})\n{entry["cuerpo"]}\nReferencia: {entry["referencia"]}'
        else:st.info('Todavía no hay artículos publicados para este servicio.')
        with st.form(f'p6_kb_response_{key}'):
            response=st.text_area('Borrador de respuesta o procedimiento aplicado',key=f'p6_kb_draft_{key}',height=140)
            if st.form_submit_button('Registrar respuesta como comentario del ticket'):
                if try_do(lambda:s.add_comment(key,response,actor(),'Equipo PMO'),'Comentario documentado'):st.rerun()
        with st.expander('Administrar catálogo de conocimiento (revisión y publicación manual)'):
            all_articles=s.knowledge_articles(t['servicio_id'],include_drafts=True)
            choices=['__new__']+[a['id'] for a in all_articles]
            selected=st.selectbox('Artículo',choices,format_func=lambda x:'＋ Nuevo artículo' if x=='__new__' else next(z['titulo'] for z in all_articles if z['id']==x))
            old=next((z for z in all_articles if z['id']==selected),{})
            with st.form(f'p6_kb_form_{key}'):
                article_title=st.text_input('Título',value=old.get('titulo',''))
                article_body=st.text_area('Procedimiento / plantilla',value=old.get('cuerpo',''),height=120)
                article_ref=st.text_input('Referencia documental',value=old.get('referencia',''))
                a,b=st.columns(2)
                with a:article_version=st.text_input('Versión',value=old.get('version','1.0'))
                with b:article_status=st.selectbox('Estado',['Borrador','Publicado'],index=0 if old.get('estado','Borrador')=='Borrador' else 1)
                owner=st.text_input('Responsable de actualización',value=old.get('responsable',actor()))
                save=st.form_submit_button('Guardar artículo')
            if save:
                if try_do(lambda:s.save_knowledge(t['servicio_id'],article_title,article_body,article_ref,article_version,article_status,owner,selected if old else None),'Artículo guardado'):st.rerun()
    with tabs[4]:
        with st.form('p6_comment_form'):
            comment=st.text_area('Comentario de seguimiento')
            typ=st.selectbox('Origen de la observación',['Equipo PMO','Cliente PMO'])
            send=st.form_submit_button('Agregar comentario')
        if send:
            if try_do(lambda:s.add_comment(key,comment,actor(),typ),'Comentario guardado'):st.rerun()
        st.caption('«Cliente PMO» es un origen declarado manualmente: no equivale a autenticación del cliente.')
        with st.form('p6_evidence_form'):
            ev_name=st.text_input('Nombre de evidencia');ev_ref=st.text_input('Enlace o referencia documental')
            ev_send=st.form_submit_button('Vincular evidencia')
        if ev_send:
            if try_do(lambda:s.add_evidence(key,ev_name,ev_ref,actor()),'Evidencia vinculada'):st.rerun()
        uploaded=st.file_uploader('Adjuntar soporte local (máximo 300 KB)',
                  type=['pdf','png','jpg','jpeg','txt','docx','xlsx','csv'],key=f'p6_attachment_{key}')
        if uploaded and st.button('Guardar archivo adjunto',key=f'p6_attachment_save_{key}'):
            if try_do(lambda:s.upload_attachment(key,uploaded.name,uploaded.getvalue(),uploaded.type,actor()),
                      'Archivo guardado'):st.rerun()
        for file in s.attachments(key):
            name,raw=s.attachment_content(file['id'])
            st.download_button(f'↓ {name} · {file["tamano"]} B',raw,file_name=name,
                 mime='application/octet-stream',key=f'p6_attach_dl_{file["id"]}')
        for item in s.evidences(key):st.caption(f'📎 {item["titulo"]} · {item["referencia"]}')
        for item in s.comments(key):st.caption(f'{item["fecha"]} · {item["autor"]}: {item["comentario"]}')
    with tabs[5]:
        st.dataframe(s.history(key),hide_index=True,use_container_width=True)
    st.divider()
    current_idx=s.STAGES.index(t['estado']);left,right=st.columns([1,1])
    with left:
        if current_idx:
            reason=st.text_input('Motivo obligatorio de devolución',key=f'p6_reason_{key}')
            if st.button('← Retroceder una etapa',use_container_width=True):
                try:
                    s.transition(key,s.STAGES[current_idx-1],actor(),reason);st.rerun()
                except s.ValidationError as ex:st.error(str(ex))
    with right:
        wip_reason=st.text_input('Motivo WIP si se supera el límite',key=f'p6_wip_reason_{key}') if current_idx==1 else ''
        if current_idx<4 and st.button('Avanzar a '+s.STAGES[current_idx+1]+' →',type='primary',use_container_width=True):
            try:
                s.transition(key,s.STAGES[current_idx+1],actor(),wip_reason);st.rerun()
            except s.ValidationError as ex:st.error(str(ex))

def controls():
    t=s.tickets();cats=s.catalog()
    labels={x['id']:x['nombre'] for x in cats}
    a,b,c,d,e=st.columns([1.6,1.15,1,1,.8],vertical_alignment='bottom')
    with a:query=st.text_input('Buscar',placeholder='Código, solicitud, cliente...',key='p6_filter_q',label_visibility='collapsed')
    with b:service=st.selectbox('Servicio',['Todos',*labels],format_func=lambda k:'Todos los servicios' if k=='Todos' else labels[k],label_visibility='collapsed',key='p6_filter_serv')
    with c:priority=st.selectbox('Prioridad',['Todas',*s.PRIORITIES],label_visibility='collapsed',key='p6_filter_prio')
    owners=sorted({x['responsable'] for x in t if x['responsable'].strip()})
    with d:owner=st.selectbox('Responsable',['Todos',*owners],label_visibility='collapsed',key='p6_filter_owner')
    with e:
        def clear_filters():
            for name in ('p6_filter_q','p6_filter_serv','p6_filter_prio','p6_filter_owner','p6_filter_stage','p6_filter_ans','p6_filter_project','p6_filter_complexity','p6_triage_mode'):
                st.session_state.pop(name,None)
        st.button('Limpiar filtros',use_container_width=True,on_click=clear_filters)
    a,b,c,d,e=st.columns([1,1,1,1,.8],vertical_alignment='bottom')
    with a:stage=st.selectbox('Etapa',['Todas las etapas',*s.STAGES],key='p6_filter_stage')
    with b:risk=st.selectbox('Estado ANS',['Todos','Sin ANS','Verde','Ámbar','Rojo','Vencido','Cumplido'],key='p6_filter_ans')
    with c:project=st.selectbox('Tipo de proyecto',['Todos',*s.PROJECT_TYPES],key='p6_filter_project')
    with d:complexity=st.selectbox('Complejidad',['Todas',*s.COMPLEXITIES],key='p6_filter_complexity')
    with e:triage=st.checkbox('Triaje diario',key='p6_triage_mode',help='Ordena por riesgo ANS, prioridad y complejidad; no altera registros.')
    query=(query or '').casefold()
    def severity(x):
        stt=s.sla_state(x,'resolucion')
        return 'Vencido' if stt.get('semaforo')=='Vencido' else stt.get('semaforo','Sin ANS')
    out=[x for x in t if (not query or query in ' '.join(str(x[k]) for k in ('folio','titulo','cliente','dependencia','descripcion')).casefold())
         and (service=='Todos' or x['servicio_id']==service)
         and (priority=='Todas' or x['prioridad']==priority)
         and (owner=='Todos' or x['responsable']==owner)
         and (stage=='Todas las etapas' or x['estado']==stage)
         and (risk=='Todos' or severity(x)==risk)
         and (project=='Todos' or x.get('tipo_proyecto','No aplica')==project)
         and (complexity=='Todas' or x.get('complejidad','Sin clasificar')==complexity)]
    if triage:
        ranks={'Vencido':0,'Rojo':1,'Ámbar':2,'Verde':3,'Sin ANS':4,'Cumplido':5}
        priorities={'Urgente':0,'Alta':1,'Normal':2,'Baja':3}
        out.sort(key=lambda x:(x['estado']=='Finalizado',ranks.get(severity(x),6),priorities.get(x['prioridad'],4),
                               {'Alta':0,'Media':1,'Baja':2}.get(x.get('complejidad'),3),x['creado_en']))
    st.caption(f'{len(out)} solicitud(es) en la selección')
    return out

@st.dialog('Conformidad de entregable · cliente',width='large')
def client_feedback_dialog():
    st.info('Formulario de confirmación por código de un solo uso. No equivale a ingreso con identidad corporativa SSO. No compartas el código en comentarios o capturas.')
    with st.form('p6_client_feedback_self'):
        ticket_code=st.text_input('Código público del ticket *',placeholder='TCK-2026-SRV011-0001')
        secret=st.text_input('Código de confirmación recibido *',type='password')
        decision=st.radio('¿Cómo recibió el entregable?',['Conforme','Solicita ajustes'],horizontal=True)
        csat=st.selectbox('Satisfacción CSAT (opcional)',['No responder',1,2,3,4,5])
        nps=st.selectbox('Probabilidad de recomendar el servicio (NPS 0–10, opcional)',[None,*range(11)],format_func=lambda v:'No responder' if v is None else str(v))
        feedback=st.text_area('Observaciones o ajustes requeridos')
        submitted=st.form_submit_button('Enviar respuesta con código',type='primary')
    if submitted:
        target=s.row('SELECT id FROM p6_tickets WHERE folio=?',(ticket_code.strip(),))
        if not target:st.error('No se pudo validar el ticket o el código.')
        else:
            try:
                s.submit_conformity(target['id'],secret,decision,None if csat=='No responder' else csat,nps,feedback)
                st.success('Respuesta registrada. Conserva la referencia del ticket.')
            except s.ValidationError:
                st.error('No se pudo validar el ticket o el código, o el acuerdo ya no admite respuesta.')

def new_button():
    left,right=st.columns(2)
    with left:
        if st.button('＋ Nueva solicitud',type='primary',key=f'p6_new_{st.session_state.get("pmo_active_p6_page","")}'):
            new_ticket_dialog()
    with right:
        if st.button('Confirmar entrega',key=f'p6_client_link_{st.session_state.get("pmo_active_p6_page","")}'):
            client_feedback_dialog()

def board():
    cols=st.columns([4,1],vertical_alignment='top')
    with cols[0]:heading('OPERACIÓN · CONTROL DE CASOS','Tablero de operación de servicios','Solicitudes, asignación, ejecución, evaluación y cierre trazable.')
    with cols[1]:new_button()
    from .alpha04_operations import render_operations
    render_operations(ticket_dialog)
    report=s.scan_sla_alerts()
    if report['nuevas']:st.warning(f'{report["nuevas"]} alerta(s) ANS nuevas registradas. Revisar la bandeja de escalamiento.')
    with st.expander('Capacidad WIP y alertas de escalamiento'):
        rules=s.wip_summary()
        if rules:st.dataframe(rules,hide_index=True,use_container_width=True)
        else:st.caption('No hay límites definidos. Los valores por operador se configuran manualmente.')
        with st.form('p6_wip_rule'):
            x,y,z=st.columns([1.5,1,1])
            with x:operator=staff_picker('Integrante PMO · límite WIP')
            with y:limit=st.number_input('Límite de casos',min_value=1,max_value=100,value=3)
            with z:mode=st.selectbox('Acción al exceder',['Advertir','Bloquear'])
            if st.form_submit_button('Guardar límite WIP'):
                if try_do(lambda:s.set_work_limit(operator,int(limit),mode=mode),'Límite configurado'):st.rerun()
        alert_rows=[a for a in s.sla_alerts() if a['estado']=='Pendiente']
        if alert_rows:
            st.caption(f'{len(alert_rows)} alertas en aplicación pendientes de revisión')
            for a in alert_rows[:12]:
                st.warning(f'{a["tipo"]}: {a["umbral"]}% · {a["detalle"]} · Responsable: {a["responsable"] or "por configurar"}')
                if st.button('Marcar revisada',key='p6_alert_'+a['id']):
                    s.mark_alert_seen(a['id'],actor());st.rerun()
    items=controls();stats=s.statistics(items)
    metrics([('Solicitudes recibidas',stats['recibidas'],'Registros de la selección','▤'),
             ('Solicitudes atendidas',stats['atendidas'],'Con entregable técnico','✓'),
             ('Cumplimiento ANS',fmt_pct(stats['cumplimiento_resolucion']),f'{stats["base_resolucion"]} casos evaluables','◷'),
             ('Calificación del cliente',f'{stats["calificacion"]:.1f}/10' if stats['calificacion'] is not None else '—',f'{stats["evaluaciones_recibidas"]} evaluaciones','☆')])
    wip_rules={(r['operador'],r['etapa']):r for r in s.wip_summary()}
    payload=[{'id':item['id'],'folio':item['folio'],'titulo':item['titulo'],
          'cliente':item['cliente'],'prioridad':item['prioridad'],'estado':item['estado'],
          'responsable':item['responsable'],'demo':bool(item['demo']),
          'respuesta':s.sla_state(item,'respuesta')['estado'],
          'servicio':service_label(item['servicio_id']).split(' · ',1)[-1],
          'ans':s.sla_state(item,'resolucion')['estado'],
          'srap':s.sla_state(item,'respuesta').get('porcentaje'),
          'sres':s.sla_state(item,'resolucion').get('porcentaje'),
          'semaforo':s.sla_state(item,'resolucion').get('semaforo','Sin ANS'),
          'wip':wip_rules.get((item['responsable'],'En proceso'))} for item in items]
    event=KANBAN(items=payload,key='pmo_step6_interactive_board',default=None)
    if event and event.get('nonce')!=st.session_state.get('p6_last_kanban_event'):
        st.session_state['p6_last_kanban_event']=event['nonce']
        if event.get('action')=='open':
            if event.get('id') in {x['id'] for x in items}:ticket_dialog(event['id'])
        elif event.get('action')=='move':
            if event.get('id') in {x['id'] for x in items}:
                try:
                    s.transition(event['id'],event.get('to'),actor(),event.get('reason',''))
                    st.rerun()
                except s.ValidationError as ex:st.error(str(ex))
    st.caption('Los cambios por arrastre son solicitudes validadas por SQLite: asignación, entregable, tareas y cierre siguen siendo obligatorios.')

def ticket_list():
    c1,c2=st.columns([4,1],vertical_alignment='top')
    with c1:heading('OPERACIÓN · CONTROL DE CASOS','Gestión de solicitudes','Lista operativa con trazabilidad, estados, responsables, tiempos y evaluación del cliente.')
    with c2:new_button()
    items=controls();lookup={x['id']:x for x in items}
    data=[]
    for t in items:
        data.append({'Ticket':t['folio'],'Solicitud':t['titulo'],'Cliente':t['cliente'],'Responsable':t['responsable'],
           'Prioridad':t['prioridad'],'Complejidad':t.get('complejidad','Sin clasificar'),
           'Proyecto':t.get('tipo_proyecto','No aplica'),
           'Estado':t['estado'],'ANS resolución':s.sla_state(t,'resolucion')['estado'],
           'Calificación':f'{t["calificacion"]}/10' if t['calificacion'] else '—','Creación':t['creado_en']})
    if data:
        selection=st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True,on_select='rerun',selection_mode='single-row',key='p6_table',height=420)
        chosen=selection.selection.rows
        if chosen and chosen[0]<len(items):ticket_dialog(items[chosen[0]]['id'])
        selected=st.selectbox('Consultar ficha por ticket',[x['id'] for x in items],format_func=lambda x:lookup[x]['folio']+' · '+lookup[x]['titulo'])
        if st.button('Abrir ticket seleccionado'):ticket_dialog(selected)
    else:st.info('No hay solicitudes con estos filtros.')
    st.download_button('↓ Exportar CSV',s.export_tickets_csv(),'PMO_CENS_Paso6_Tickets.csv','text/csv')

def dashboard():
    c1,c2=st.columns([4,1],vertical_alignment='top')
    with c1:heading('ANALÍTICA OPERATIVA','Estado de solicitudes e indicadores','Vista de demanda, servicios atendidos, tiempos y satisfacción. Solo registros guardados.')
    with c2:st.download_button('↓ Exportar al Paso 7',json_bytes(s.export_step7()),'PMO_CENS_Paso6_Expediente_Paso7.json',mime='application/json',use_container_width=True)
    s.scan_sla_alerts()
    items=controls();stats=s.statistics(items)
    all_cards=[('Solicitudes recibidas',stats['recibidas'],'Todas las etapas','▤'),
      ('Solicitudes atendidas',stats['atendidas'],'Entregable concluido','✓'),
      ('Servicios distintos atendidos',stats['servicios_atendidos'],'Tipos con atención','◈'),
      ('Solicitudes finalizadas',stats['finalizadas'],'Cierre registrado','▣'),
      ('Solicitudes activas',stats['activas'],'Sin cierre final','◷'),
      ('Cumplimiento ANS resolución',fmt_pct(stats['cumplimiento_resolucion']),f'{stats["base_resolucion"]} evaluables','◎'),
      ('Cumplimiento ANS respuesta',fmt_pct(stats['cumplimiento_respuesta']),f'{stats["base_respuesta"]} evaluables','◉'),
      ('Calificación promedio',f'{stats["calificacion"]:.1f}/10' if stats['calificacion'] is not None else '—',f'{stats["evaluaciones_recibidas"]} clientes','☆'),
      ('Atención promedio',fmt_hours(stats['tiempo_medio']),'Registro → entregable','⏱'),
      ('Tickets en riesgo / vencidos',stats['riesgos'],'Abiertos con ANS','!'),
      ('Evaluaciones recibidas',stats['evaluaciones_recibidas'],'Captura directa del cliente no autenticada','✓'),
      ('Sin ANS resolución',stats['sin_ans'],'Excluidos del indicador de cumplimiento','—')]
    for i in range(0,12,4):metrics(all_cards[i:i+4])
    left,right=st.columns([1.6,1],gap='medium')
    with left:
        with st.container(border=True):
            st.subheader('Distribución por etapa')
            st.bar_chart(pd.DataFrame({'Solicitudes':[sum(x['estado']==stage for x in items) for stage in s.STAGES]},index=s.STAGES),horizontal=True)
    with right:
        with st.container(border=True):
            st.subheader('Demanda por servicio')
            c=Counter(service_label(x['servicio_id']).split(' · ',1)[-1] for x in items)
            if c:st.bar_chart(pd.DataFrame({'Solicitudes':list(c.values())},index=list(c)),horizontal=True)
            else:st.info('Sin registros')
    satis=s.satisfaction_summary(items)
    st.caption(f'CSAT verificado: {satis["csat"] if satis["csat"] is not None else "—"}/5 ({satis["base_csat"]} respuestas); NPS verificado: {satis["nps"] if satis["nps"] is not None else "—"} ({satis["base_nps"]} respuestas). No se mezcla con la calificación histórica 1–10.')
    st.caption('Los ANS se calculan según la unidad congelada por solicitud: horas calendario u horas hábiles verificadas. Los casos sin ANS no ingresan en el denominador de cumplimiento. Los alertas requieren motor programado para operar fuera de la sesión Streamlit.')

def pmi():
    heading('AUTOEVALUACIÓN','Evaluación metodológica del Paso 6','35 preguntas en siete dimensiones, con evidencia y versiones históricas. Escala de 1 a 5.')
    history=s.evaluation_list()
    if not history:
        owner=st.text_input('Responsable de la autoevaluación',key='p6_eval_owner_new')
        if st.button('Crear evaluación PMI',type='primary'):
            result=try_do(lambda:s.new_evaluation(owner),'Evaluación iniciada')
            if result:st.session_state['p6_eval_id']=result;st.rerun()
    else:
        candidates=[x['id'] for x in history]
        selected=st.selectbox('Evaluación / versión',candidates,
                 index=candidates.index(st.session_state['p6_eval_id']) if st.session_state.get('p6_eval_id') in candidates else 0,
                 format_func=lambda k:next(f'Versión {x["version"]} · {x["estado"]} · {x["responsable"]}' for x in history if x['id']==k))
        st.session_state['p6_eval_id']=selected
        summary=s.evaluation_summary(selected)
        metrics([('Preguntas respondidas',f'{summary["respondidas"]}/35','Avance del cuestionario','✓'),
            ('Puntaje global',str(summary['puntaje_final']) if summary['puntaje_final'] is not None else '—','Máximo 175','◈'),
            ('Dimensiones completas',sum(x['respondidas']==5 for x in summary['dimensiones']),'De siete dimensiones','▤'),
            ('Clasificación',summary['clasificacion_final'] or 'Pendiente','Solo con 35 respuestas','◎')])
        st.info('La autoevaluación PMI es independiente de las calificaciones 1–10 de los clientes. Los ítems son paráfrasis funcionales.')
        chosen_dim=st.radio('Dimensiones',list(range(7)),format_func=lambda i:f'{i+1}. {s.QUESTIONS[i]["name"]}',horizontal=True)
        existing={x['numero']:x for x in s.answers(selected)}
        with st.form(f'p6_pmi_dim_{selected}_{chosen_dim}'):
            choices=[]
            for offset,question in enumerate(s.QUESTIONS[chosen_dim]['questions']):
                num=chosen_dim*5+offset+1;old=existing.get(num)
                st.markdown(f'**{num}. {question}**')
                val=st.selectbox('Valor', [None,1,2,3,4,5],
                       index=0 if old is None else old['valor'],key=f'p6_pmi_val_{selected}_{num}',
                       format_func=lambda v:'Sin responder' if v is None else f'{v} / 5')
                a,b=st.columns(2)
                with a:obs=st.text_input('Observación',value=old['observacion'] if old else '',key=f'p6_pmi_obs_{selected}_{num}')
                with b:ev=st.text_input('Evidencia / referencia',value=old['evidencia'] if old else '',key=f'p6_pmi_ev_{selected}_{num}')
                choices.append((num,val,obs,ev))
            submit=st.form_submit_button('Guardar respuestas de esta dimensión',type='primary',disabled=summary['estado']=='Finalizada')
        if submit:
            try:
                for number,val,obs,ev in choices:
                    if val is not None:s.save_answer(selected,number,val,obs,ev)
                st.success('Respuestas guardadas');st.rerun()
            except s.ValidationError as ex:st.error(str(ex))
        st.subheader('Resumen por dimensión')
        st.dataframe(summary['dimensiones'],hide_index=True,use_container_width=True)
        left,right=st.columns(2)
        with left:
            st.download_button('↓ Exportar respuestas PMI',json_bytes({'schema':'PMO-FLYWHEEL-CENS-Paso6-evaluation-v1',
                     'resumen':summary,'respuestas':s.answers(selected),'historial':history}),
                     'PMO_CENS_Paso6_Evaluacion_PMI.json',mime='application/json')
        with right:
            if st.button('Finalizar y archivar evaluación',type='primary',disabled=summary['estado']=='Finalizada'):
                if try_do(lambda:s.finish_evaluation(selected),'Evaluación archivada'):st.rerun()
        if summary['estado']=='Finalizada':
            new_owner=st.text_input('Responsable de un nuevo corte',value=summary['responsable'])
            if st.button('Crear nuevo corte independiente'):
                newkey=try_do(lambda:s.new_evaluation(new_owner),'Nuevo corte creado')
                if newkey:st.session_state['p6_eval_id']=newkey;st.rerun()
        with st.expander('Historial completo de evaluaciones'):
            st.dataframe(history,hide_index=True,use_container_width=True)
    st.caption('Clasificación operativa: Crítico 35–67; Pobre 68–101; Promedio 102–130; Bien 131–153; Excelente 154–175.')

def page(name):
    a,b,c=st.columns([1.7,1,1],vertical_alignment='center')
    with a:st.caption('Paso 6 · Operación sobre SQLite compartida · Paso 5 disponible como fase de incorporación')
    with b:
        value=st.text_input('Operador responsable',value=actor(),key='p6_operator_input')
        st.session_state['p6_actor']=value.strip() or 'Equipo PMO'
    with c:
        if st.button('Catálogo y ANS',use_container_width=True,key='p6_open_cat'):catalog_dialog()
    with st.expander('Respaldo y restauración del Paso 6'):
        st.download_button('↓ Descargar respaldo JSON',json_bytes(s.export_backup()),'PMO_CENS_Paso6_Respaldo.json','application/json')
        backup=st.file_uploader('Selecciona respaldo compatible',type='json',key='p6_restore_file')
        confirmed=st.checkbox('Confirmo que deseo sustituir únicamente los registros del Paso 6',key='p6_restore_confirm')
        if backup and st.button('Restaurar Paso 6',disabled=not confirmed):
            try:
                result=s.restore_backup(json.load(backup),confirm=True)
                st.success(f'Restauración completada: {result}');st.rerun()
            except (s.ValidationError,ValueError,json.JSONDecodeError) as ex:st.error(str(ex))
    if any(x['demo'] for x in s.tickets()) or any(x['demo'] for x in s.catalog()):
        st.warning('MODO DEMOSTRACIÓN: algunas solicitudes y servicios son ficticios; no corresponden a registros operativos de CENS.')
        with st.expander('Eliminar exclusivamente los datos demostrativos del Paso 6'):
            confirmed=st.checkbox('Confirmo que deseo borrar solo los ejemplos de Paso 6',key='p6_demo_remove_check')
            if st.button('Eliminar ejemplos',disabled=not confirmed,key='p6_remove_demo'):
                st.success(str(s.remove_demo()));st.rerun()
    if name==NAV[0]:board()
    elif name==NAV[1]:ticket_list()
    elif name==NAV[2]:dashboard()
    elif name==NAV[3]:pmi()
    else:st.warning('Sección no disponible')
