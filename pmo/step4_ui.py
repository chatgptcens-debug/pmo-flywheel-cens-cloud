"""Interfaz Paso 4: cuatro vistas sobre la misma base SQLite del Flywheel.
No modifica el Paso 3 ni sus cálculos. Componentes Streamlit nativos y CSS local.
"""
from __future__ import annotations
from .date_widgets import iso_date_input
import csv
import html
import io
import json
from datetime import date
from pathlib import Path
import os
import pandas as pd
import streamlit as st
from .staff_picker import staff_picker
from . import step4 as s
from . import step4_metrics as metrics_model
from . import step4_ans as ans
from . import clients as pmo_clients
from . import step4_catalogos_ficha as catalogs
from . import step4_structure as structure
from . import v0391_clients as client_roles
from .public_codes import code as public_code, next_code as next_public_code
from .ui import kpi as shared_kpi
from .step4_presentation import brief, service_summary, metric_state, metric_groups

NAV=list(s.MODULES)
ROOT=Path(__file__).resolve().parent.parent
TEMPLATE=ROOT/'plantillas'/'PLANTILLA_PASO4_CATALOGO.xlsx'
CSS=Path(__file__).resolve().parent/'assets'/'step4_ux.css'

def apply_step4_theme():
    st.markdown('<style>'+CSS.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)

def escape(v):return html.escape(str(v or ''))
def heading(number,title,caption):
    st.markdown(f'<div class="pmo-eyebrow">PASO 04 · MÓDULO {number:02d}</div><div class="pmo-title">{escape(title)}</div><div class="pmo-subtitle">{escape(caption)}</div>',unsafe_allow_html=True)

def indicators(entries):
    for idx,(c,(title,value,desc,ic)) in enumerate(zip(st.columns(len(entries)),entries)):
        with c:shared_kpi(title,value,desc,ic,('orange','blue','purple','teal')[idx%4])

def err(exc):st.error(str(exc))
def info(text):st.info(text)
def json_bytes(x):return json.dumps(x,ensure_ascii=False,indent=2,default=str).encode('utf-8')
def dl_json(label,payload,filename,key):
    st.download_button(label,json_bytes(payload),file_name=filename,mime='application/json',key=key)

def _xlsx(sheets):
    buffer=io.BytesIO()
    with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
        for name,records in sheets.items():
            table=pd.DataFrame(records)
            if table.empty:table=pd.DataFrame([{'Información':'No hay registros'}])
            table.to_excel(writer,sheet_name=name[:31],index=False)
            sheet=writer.sheets[name[:31]]
            sheet.freeze_panes='A2'
            for col in sheet.columns:
                max_len=min(44,max((len(str(x.value or '')) for x in col),default=12)+3)
                sheet.column_dimensions[col[0].column_letter].width=max(13,max_len)
    return buffer.getvalue()

def _parsed_catalog(file):
    if file.name.lower().endswith('.csv'):
        df=pd.read_csv(file,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    elif file.name.lower().endswith('.xlsx'):
        df=pd.read_excel(file,dtype=str,keep_default_na=False)
    else:raise s.ValidationError('Solo se admiten CSV y XLSX.')
    if len(df)>1000:raise s.ValidationError('Máximo 1000 servicios por carga.')
    aliases={'Nombre del servicio':'nombre','Código':'codigo','Codigo':'codigo','Descripción':'descripcion',
             'Propuesta de valor':'propuesta_valor','Cliente':'cliente','Responsable':'responsable',
             'Modelo':'modelo','Estado':'estado','Necesidad':'necesidad','Beneficio':'beneficio'}
    data=[{aliases.get(k,k):v for k,v in row.items()} for row in df.to_dict('records')]
    return data

@st.dialog('Ficha del servicio',width='large')
def service_dialog(key=None):
    """Ficha editable con catálogos guiados y campos narrativos intactos.

    Una lista de captura no constituye aprobación, ANS ni validación.
    """
    old=s.service(key) if key else None
    v=ans.hydrate_legacy(s.details(old))
    base=lambda field,default='':old.get(field,default) if old else default

    def choice(label, field, options, caption=None):
        values=list(options)
        saved=str(v.get(field) or '').strip()
        # Valorar un dato histórico existente sobre cualquier catálogo nuevo.
        if saved and saved not in values:values.append(saved)
        select=saved if saved else values[0]
        answer=st.selectbox(label,values,index=values.index(select),help=caption)
        v[field]=answer if answer!='Por definir' else ''

    def multiple(label, field, options, prior=None, caption=None):
        values=list(options)
        saved=v.get(field) or prior or []
        if not isinstance(saved,list):saved=[]
        values.extend(x for x in saved if x not in values)
        v[field]=st.multiselect(label,values,default=saved,help=caption)

    def structured_table(field,label,caption='',fallback=True):
        st.markdown('**'+label+'**')
        if caption:st.caption(caption)
        rows=structure.propose_rows(v,field) if fallback else (v.get(field) or [])
        columns=structure.COLUMNAS[field]
        df=pd.DataFrame(rows,columns=columns)
        if not rows:
            st.caption('Sin registros estructurados: agrega una fila si aplica.')
        if field=='hitos_registro':
            available=list(dict.fromkeys([*structure.ESTADOS_HITOS,*[r.get('Estado','') for r in rows if isinstance(r,dict)]]))
            config={'Estado':st.column_config.SelectboxColumn('Estado',options=available)}
        elif field=='riesgos_registro':
            treatments=list(dict.fromkeys(['',*catalogs.TRATAMIENTOS_RIESGO,*[r.get('Tratamiento','') for r in rows if isinstance(r,dict)]]))
            statuses=list(dict.fromkeys(['',*structure.ESTADOS_RIESGOS,*[r.get('Estado','') for r in rows if isinstance(r,dict)]]))
            config={
                'Tratamiento':st.column_config.SelectboxColumn('Tratamiento',options=treatments),
                'Estado':st.column_config.SelectboxColumn('Estado',options=statuses)}
        else:config={}
        edited=st.data_editor(df,num_rows='dynamic',hide_index=True,use_container_width=True,
                              column_config=config,key='p4_struct_'+field+'_'+str(key or 'nuevo'))
        v[field]=structure.clean_rows(field,edited.fillna('').to_dict('records'))

    with st.form('p4_service_dialog_form'):
        st.caption('Ficha editable · El Paso 04 desarrolla la oferta, el proceso, los ANS y la transición. '
                   'Los catálogos son una adaptación operativa CENS y no reemplazan las validaciones.')
        a,b=st.columns(2)
        with a:
            st.text_input('Código público · consecutivo',value=public_code('servicio',key) if key else next_public_code('servicio'),disabled=True)
            code=base('codigo',next_public_code('servicio'))
        with b:
            state_options=list(s.STATUSES)
            prior_state=base('estado','Borrador')
            state=st.selectbox('Estado',state_options,index=state_options.index(prior_state) if prior_state in state_options else 0)
        name=st.text_input('Nombre del servicio *',value=base('nombre'))
        with st.expander('Descripción y propuesta de valor · detalle editable',expanded=not bool(old)):
            desc=st.text_area('Descripción del servicio',value=base('descripcion'),height=85)
            value=st.text_area('Propuesta de valor / beneficio',value=base('propuesta_valor'),height=100)
        if old:
            st.caption('Descripción breve: '+brief(desc,135)+' · Valor: '+brief(value,150))
        c,d=st.columns(2)
        with c:
            roles_options=list(client_roles.role_catalog())
            multiple('Roles destinatarios · catálogo de clientes','destinatarios_roles',roles_options,
                     caption='Roles institucionales del directorio; no modifica clientes ni ponderaciones históricas.')
            with st.expander('Destinatarios · descripción histórica',expanded=not bool(roles_options)):
                client=st.text_area('Público objetivo / destinatarios',value=base('cliente'),height=78)
            if not client and v.get('destinatarios_roles'):
                client=', '.join(v['destinatarios_roles'])
        with d:
            owner=st.text_input('Propietario / responsable',value=base('responsable'))
            integrantes=s.members()
            if integrantes:
                roster={'Sin asignar desde equipo PMO':None}
                for person in integrantes:roster[f"{person['nombre']} · {person['rol']}"]=person['nombre']
                owner_pick=st.selectbox('Seleccionar integrante PMO (opcional)',list(roster),
                    help='Si seleccionas un integrante, su nombre se aplicará al guardar. No cambia las asignaciones de capacidad.')
            else:
                owner_pick=None
        model_options=list(s.DELIVERY_MODELS)
        saved_model=base('modelo','Consultivo')
        if saved_model not in model_options:model_options.append(saved_model)
        model=st.selectbox('Modelo de prestación',model_options,
              index=model_options.index(saved_model),
              help='Modelo operativo existente de CENS; independiente de la naturaleza y el dominio.')

        tabs=st.tabs(['01 · Ficha general','02 · Activación y proceso','03 · ANS y validación','04 · Implementación'])
        with tabs[0]:
            st.caption('Vista compacta: información clave visible y anexos editables desplegables. Las descripciones históricas no se eliminan.')
            with st.expander('Clasificación metodológica y destinatarios',expanded=True):
                g1,g2=st.columns(2)
                with g1:
                    original=v.get('naturaleza') or catalogs.infer_naturaleza(v.get('caracteristicas',''))
                    v['naturaleza']=original
                    values=list(catalogs.NATURALEZAS)
                    if original not in values:values.append(original)
                    choice('Naturaleza del servicio','naturaleza',values,
                           'Clasificación estratégica, táctica u operativa de CENS.')
                    choice('Mecanismo principal de retroalimentación','mecanismo_retroalimentacion',catalogs.RETROALIMENTACION)
                with g2:
                    multiple('Dominios de gestión','dominios',catalogs.DOMINIOS,
                             prior=catalogs.infer_dominios(v.get('caracteristicas','')))
                    choice('Integración tecnológica prevista','tipo_integracion',catalogs.INTEGRACIONES)
                if v.get('tipo_integracion') not in ('Por definir','Sin integración tecnológica',''):
                    v['tecnologia']=st.text_area('Integración tecnológica · especificación',value=v.get('tecnologia',''),height=80)
            with st.expander('Alcance, exclusiones y entregables',expanded=True):
                a,b=st.columns(2)
                with a:v['alcance']=st.text_area('Alcance del servicio',value=v.get('alcance',''),height=94)
                with b:v['exclusiones']=st.text_area('Exclusiones y límites de autoridad',value=v.get('exclusiones',''),height=94)
                structured_table('entregables_items','Entregables y criterios de aceptación',
                  'Cada entregable se agrega por fila. Se sugieren ítems a partir del texto histórico sin atribuirles aceptación.')
                st.caption('Los criterios definidos aquí pueden utilizarse como referencia del acuerdo ANS. Su aprobación se registra por separado.')
            with st.expander('Ficha documental histórica y campos complementarios',expanded=False):
                st.caption('Información previa no eliminada. Úsala para validar la migración a las tablas y corregir textos originales.')
                for field,label in [('caracteristicas','Características y componentes históricos'),
                    ('entregables','Entregables · texto original'),('recursos','Recursos estimados · texto histórico'),
                    ('indicadores','Indicadores esperados · texto histórico'),
                    ('retroalimentacion','Retroalimentación · detalle'),('formacion','Formación y adopción · texto histórico')]:
                    v[field]=st.text_area(label,value=v.get(field,''),height=85)
                if v.get('tipo_integracion') in ('Por definir','Sin integración tecnológica',''):
                    v['tecnologia']=st.text_area('Integración tecnológica · nota histórica',value=v.get('tecnologia',''),height=65)
            if key:
                linked_metrics=s.metric_list(key)
                req=s.requirements(key)
                assigned=[a for a in s.allocations() if a.get('servicio_id')==key and a.get('porcentaje',0)>0]
                st.caption(f'Datos relacionados · {len(linked_metrics)} indicadores en catálogo · {len(req)} competencias requeridas · {len(assigned)} asignaciones activas. Se editan en sus módulos de origen.')

        with tabs[1]:
            with st.expander('Solicitud y activación',expanded=True):
                v['activaciones']=st.multiselect('Modos de activación',list(s.ACTIVATIONS),default=v.get('activaciones',[]))
                g1,g2=st.columns(2)
                with g1:choice('Canal principal de solicitud','canal_solicitud',catalogs.CANALES)
                with g2:multiple('Prioridades previstas','prioridades_solicitud',catalogs.PRIORIDADES_SOLICITUD,
                      caption='Clasificación de diseño; no corresponde a tickets activos.')
                v['activacion_detalle']=st.text_area('Condiciones de activación',value=v.get('activacion_detalle',''),height=75)
                v['solicitud']=st.text_area('Instrucciones para solicitar el servicio',value=v.get('solicitud',''),height=75)
            with st.expander('Proceso y responsabilidades RACI',expanded=True):
                structured_table('proceso_actividades','Actividades del proceso',
                       'Orden, actividad, responsable y producto. Las filas no prueban aprobación del proceso.')
                structured_table('raci_registro','Matriz RACI por actividad',
                       'Captura los roles R, A, C e I. El diligenciamiento no prueba concertación ni aprobación.')
                if v.get('raci_matriz_propuesta'):
                    st.caption('Matriz del taller conservada para trazabilidad; su contenido se propone inicialmente en la nueva tabla.')
                    if st.checkbox('Mostrar matriz RACI original',value=False,key='p4_raci_src_'+str(key or 'nuevo')):
                        raci_df=st.data_editor(pd.DataFrame(v['raci_matriz_propuesta']),num_rows='dynamic',
                            hide_index=True,key='p4_raci_propuesta_editor_'+str(key or 'nuevo'),use_container_width=True)
                        v['raci_matriz_propuesta']=raci_df.fillna('').to_dict('records')
                if st.checkbox('Mostrar y editar proceso / RACI históricos',value=False,key='p4_legacy_process_'+str(key or 'nuevo')):
                    for field,label in [('proceso','Proceso de punta a punta · histórico'),('raci','RACI · histórico'),('plazos','Plazos estimados · histórico (sin ANS)')]:
                        v[field]=st.text_area(label,value=v.get(field,''),height=90)
                choice('Enfoque de prestación','enfoque_prestacion',catalogs.ENFOQUES)
            with st.expander('Variantes y riesgos',expanded=False):
                g1,g2=st.columns(2)
                with g1:multiple('Criterios de adaptación del proceso','variantes_tipo',catalogs.ADAPTACIONES)
                with g2:multiple('Categorías de riesgos','categorias_riesgo',catalogs.RIESGOS)
                structured_table('riesgos_registro','Registro de riesgos y tratamiento',
                       'Cada riesgo se conserva con tratamiento, responsable y estado independiente.')
                for field,label in [('variantes','Variaciones · texto histórico'),('riesgos','Riesgos · texto histórico')]:
                    v[field]=st.text_area(label,value=v.get(field,''),height=78)
        with tabs[2]:
            st.markdown('##### ANS y validación del servicio')
            st.caption('Compromisos de prestación y acuerdo con el cliente. Define el ANS aquí; '
                       'su medición corresponde a Operación y Monitoreo (Pasos 06 y 07).')
            st.caption(f"Servicio: {public_code('servicio',key) if key else 'Nuevo'} · "
                       f"Estado del servicio: {state} · Estado del ANS: {v.get('ans_estado') or 'Borrador'}")
            prior_ans_status=v.get('ans_estado') or 'Borrador'
            if prior_ans_status=='Validado':
                st.success(f"ANS validado · Versión {len(v.get('ans_versiones') or [])}. "
                           'Editar un compromiso reabrirá automáticamente su revisión sin borrar la versión validada.')
                reopen_ans=st.checkbox('Reabrir explícitamente el ANS para revisión',value=False)
                v['ans_estado']='En revisión' if reopen_ans else 'Validado'
            else:
                v['ans_estado']=st.selectbox('Estado de definición del ANS',('Borrador','En revisión'),
                    index=1 if prior_ans_status=='En revisión' else 0,
                    help='La validación solo se registra con el botón específico y la evidencia correspondiente.')

            if v.get('ans_escenarios_propuestos'):
                with st.expander('Escenarios de atención propuestos · sin ANS validado'):
                    st.warning('Valores extraídos de la ficha técnica SRV-011. No se copian automáticamente al ANS oficial ni habilitan su validación.')
                    draft_sla=st.data_editor(pd.DataFrame(v['ans_escenarios_propuestos']),num_rows='dynamic',
                                             hide_index=True,use_container_width=True,key='p4_ans_scenarios_editor_'+str(key or 'nuevo'))
                    v['ans_escenarios_propuestos']=draft_sla.fillna('').to_dict('records')
            with st.expander('🕒 1. Compromisos de atención',expanded=True):
                st.caption('Tiempos objetivo, horario aplicable y eventos que inician o finalizan el cómputo.')
                r1,r2=st.columns(2)
                with r1:
                    response_number=st.number_input('Tiempo objetivo de respuesta',min_value=0.01,
                        max_value=100000.0,value=(float(v['ans_respuesta_valor']) if str(v.get('ans_respuesta_valor') or '').replace('.','',1).isdigit() else None),
                        step=0.5,format='%.2f',placeholder='Por definir',
                        help='Número mayor que cero; no registra mediciones reales.')
                    v['ans_respuesta_valor']=str(response_number) if response_number is not None else ''
                    choice('Unidad de respuesta','ans_respuesta_unidad',ans.UNIDADES)
                with r2:
                    delivery_number=st.number_input('Tiempo objetivo de entrega',min_value=0.01,
                        max_value=100000.0,value=(float(v['ans_entrega_valor']) if str(v.get('ans_entrega_valor') or '').replace('.','',1).isdigit() else None),
                        step=0.5,format='%.2f',placeholder='Por definir')
                    v['ans_entrega_valor']=str(delivery_number) if delivery_number is not None else ''
                    choice('Unidad de entrega','ans_entrega_unidad',ans.UNIDADES)
                if (v.get('sla_respuesta') and not v.get('ans_respuesta_valor')) or (v.get('sla_entrega') and not v.get('ans_entrega_valor')):
                    with st.expander('Consultar compromisos históricos sin estructura',expanded=False):
                        st.caption('Estos valores originales se conservan. Para validar un ANS nuevo deben estructurarse.')
                        st.write('Respuesta:', v.get('sla_respuesta') or 'Sin registro')
                        st.write('Entrega:', v.get('sla_entrega') or 'Sin registro')
                        st.write('Unidad histórica:',v.get('unidad_tiempo_ans') or 'Sin registro')
                        if v.get('ans_sla_respuesta_original'):
                            st.write('Respuesta original antes de estructuración:',v['ans_sla_respuesta_original'])
                        if v.get('ans_sla_entrega_original'):
                            st.write('Entrega original antes de estructuración:',v['ans_sla_entrega_original'])
                v['ans_horario']=st.text_area('Horario de atención y calendario aplicable',
                    value=v.get('ans_horario') or '',height=70,
                    placeholder='Ej. lunes a viernes, 8:00 a. m. a 5:00 p. m.; festivos excluidos')
                c1,c2=st.columns(2)
                with c1:
                    v['ans_inicio_computo']=st.text_area('Evento de inicio del cómputo',
                        value=v.get('ans_inicio_computo') or '',height=72,
                        placeholder='Ej. solicitud completa y admitida por la PMO')
                with c2:
                    v['ans_fin_computo']=st.text_area('Evento de cumplimiento',
                        value=v.get('ans_fin_computo') or '',height=72,
                        placeholder='Ej. respuesta emitida / entregable disponible')
                v['ans_nivel_servicio']=st.selectbox('Modalidad de nivel de servicio',
                    ['Único para el servicio','Diferenciado','Por definir'],
                    index=(['Único para el servicio','Diferenciado','Por definir'].index(v.get('ans_nivel_servicio'))
                           if v.get('ans_nivel_servicio') in ['Único para el servicio','Diferenciado','Por definir'] else 2),
                    help='Solo aplica diferenciación cuando la naturaleza del servicio la justifique.')
                if v['ans_nivel_servicio']=='Diferenciado':
                    v['ans_condiciones_nivel']=st.text_area('Condiciones por prioridad / tipo de cliente',
                        value=v.get('ans_condiciones_nivel') or '',height=70)

            with st.expander('✅ 2. Calidad y aceptación',expanded=False):
                st.caption('Estándares verificables y conformidad sobre cada entregable.')
                v['sla_calidad']=st.text_area('Estándares de calidad',value=v['sla_calidad'],
                    height=85,placeholder='Especifica los controles y criterios que pueden verificarse')
                v['sla_aceptacion']=st.text_area('Criterios de aceptación del entregable',
                    value=v['sla_aceptacion'],height=85,placeholder='Condiciones objetivas para considerar aceptado el resultado')
                choice('Medio de aceptación','ans_medio_aceptacion',ans.MEDIOS)

            with st.expander('🔄 3. Escalamiento y seguimiento',expanded=False):
                st.caption('Responsabilidades y procedimiento de tratamiento de excepciones; sin seguimiento operativo automático.')
                c1,c2=st.columns(2)
                with c1:
                    v['ans_responsable_escalamiento']=st.text_input('Responsable del escalamiento',
                        value=v.get('ans_responsable_escalamiento') or '',placeholder='Rol o dependencia responsable')
                    choice('Nivel previsto de escalamiento','nivel_escalamiento',catalogs.ESCALAMIENTOS)
                with c2:
                    choice('Frecuencia de revisión','periodicidad_revision',catalogs.PERIODICIDADES)
                    v['ans_responsable_revision']=st.text_input('Responsable de la revisión',
                        value=v.get('ans_responsable_revision') or '',placeholder='Rol o dependencia responsable')
                v['sla_escalamiento']=st.text_area('Condiciones y procedimiento de escalamiento',
                    value=v['sla_escalamiento'],height=82)
                v['sla_seguimiento']=st.text_area('Seguimiento y revisión del ANS',
                    value=v['sla_seguimiento'],height=80,
                    help='Describir cómo se revisará el acuerdo, sin registrar todavía tickets o resultados reales.')

            with st.expander('📋 4. Validación del acuerdo',expanded=True):
                st.caption('Conformidad del cliente y evidencia trazable. No es una aprobación automática del servicio.')
                available=pmo_clients.list_clients(status='Activos')
                options={'Sin seleccionar':('','')}
                for c in available:
                    options[f"{c['nombre']} · {c['codigo']}"]=(c['id'],c['nombre'])
                saved_id=v.get('ans_cliente_id') or ''
                saved_name=v.get('validacion_cliente') or ''
                current=next((label for label,(ident,_) in options.items() if saved_id and ident==saved_id),None)
                if not current and saved_name:
                    current=next((label for label,(_,nm) in options.items() if nm.casefold()==saved_name.casefold()),None)
                if not current and saved_name:
                    current=f'Registro histórico: {saved_name}'
                    options[current]=(saved_id,saved_name)
                current=current or 'Sin seleccionar'
                selected=st.selectbox('Cliente que valida · Directorio Paso 01',list(options),
                    index=list(options).index(current),help='Selecciona un cliente existente; no crea identidades duplicadas.')
                v['ans_cliente_id'],v['validacion_cliente']=options[selected]
                if not available:st.caption('Aún no hay clientes activos en el directorio. Puede guardarse el borrador.')
                st.caption('Fecha registrada: '+(v.get('validacion_fecha') or 'Pendiente')+'. '
                           'Por defecto se registrará la fecha actual al validar el ANS.')
                ans_override=st.checkbox('Registrar fecha distinta de hoy (requiere justificación)',value=False)
                ans_date=st.date_input('Fecha real de conformidad',value=date.today(),format='YYYY/MM/DD') if ans_override else None
                ans_motive=st.text_input('Justificación de la fecha excepcional',value='',
                    disabled=not ans_override,help='Se conserva con la versión validada.')
                v['validacion_evidencia']=st.text_input('Enlace o referencia de validación',
                    value=v.get('validacion_evidencia') or '',placeholder='Acta, radicado, enlace documental o correo')
                current_attachment=v.get('ans_archivo')
                if isinstance(current_attachment,dict):
                    st.caption('Adjunto conservado: '+str(current_attachment.get('nombre','archivo'))+
                               ' · SHA-256: '+str(current_attachment.get('sha256',''))[:12]+'…')
                ans_uploaded=st.file_uploader('Adjuntar evidencia (PDF, imagen, Word o Excel; máx. 3 MiB)',
                    type=['pdf','png','jpg','jpeg','docx','xlsx'],key='p4_ans_evidencia_upload_'+str(key or 'nuevo'),
                    help='El archivo se conserva en la base del ciclo y en el respaldo JSON del Paso 04.')
                st.caption('Al registrar la validación se conserva una versión del acuerdo. '
                           'Las modificaciones posteriores quedan en revisión hasta una nueva conformidad.')
            if v.get('ans_versiones'):
                with st.expander(f"Historial de versiones validadas ({len(v['ans_versiones'])})"):
                    for past in reversed(v['ans_versiones']):
                        st.caption(f"v{past.get('numero')} · Fecha del acuerdo: {past.get('fecha_acuerdo')} · "
                                   f"Registro: {past.get('validado_en')} · SHA-256 {past.get('sha256','')[:12]}…")
        with tabs[3]:
            st.caption('Plan de preparación: las etapas y registros no aprueban por sí solos el servicio ni la operación.')
            with st.expander('Ruta, despliegue y presupuesto',expanded=True):
                g1,g2=st.columns(2)
                with g1:
                    choice('Fase de la ruta · estado real','fase_ruta_implementacion',catalogs.FASES_RUTA)
                    choice('Estrategia de despliegue','estrategia_despliegue',
                           tuple(dict.fromkeys((*catalogs.ESTRATEGIAS_DESPLIEGUE,*catalogs.ESTRATEGIAS))))
                with g2:
                    choice('Estado del presupuesto y recursos','estado_presupuesto',catalogs.ESTADOS_PRESUPUESTO)
                    choice('Estado de concertación institucional','estado_aprobacion_institucional',catalogs.ESTADOS_APROBACION,
                           'No modifica el estado oficial ni autoriza el Paso 05.')
                if v.get('fase_ruta_propuesta'):st.caption('Fase propuesta en documento técnico: '+str(v['fase_ruta_propuesta']))
                if v.get('propuesta_presupuesto'):st.caption('Hipótesis presupuestal: '+str(v['propuesta_presupuesto']))
                v['evidencia_aprobacion_institucional']=st.text_input('Evidencia de aprobación institucional',
                    value=v.get('evidencia_aprobacion_institucional',''),placeholder='Acta o radicado, cuando exista')
                if v.get('estado_presupuesto')=='Presupuesto CapEx/OpEx Aprobado':
                    v['evidencia_presupuesto_aprobado']=st.text_input('Evidencia de presupuesto aprobado',
                       value=v.get('evidencia_presupuesto_aprobado',''))
            with st.expander('Hitos de implementación · plan editable',expanded=True):
                milestone_options=list(catalogs.HITOS_TIPO)
                stored_milestones=v.get('hitos_lista') or []
                if not isinstance(stored_milestones,list):stored_milestones=[]
                milestone_options.extend(x for x in stored_milestones if x not in milestone_options)
                v['hitos_lista']=st.multiselect('Hitos de implementación · selección múltiple',milestone_options,default=stored_milestones,
                      key='p4_milestones_'+str(key or 'nuevo'))
                pending_milestones=st.text_area('Crear hitos adicionales (uno por línea)',value='',height=70)
                structured_table('hitos_registro','Planificación de hitos',
                     'Fechas, responsables, dependencias y avance. Los hitos nuevos comienzan pendientes.')
                v['hitos']=st.text_area('Hitos y dependencias específicas · texto histórico',value=v.get('hitos',''),height=76)
            with st.expander('Preparación de la transición',expanded=False):
                g1,g2=st.columns(2)
                with g1:
                    choice('Estado de preparación del piloto','estado_piloto',catalogs.ESTADOS_PILOTO)
                with g2:
                    multiple('Complejidades aplicables','complejidades_aplicables',catalogs.COMPLEJIDADES)
                v['plan']=st.text_area('Plan de implementación · resumen',value=v.get('plan',''),height=85)
                v['transicion']=st.text_area('Condiciones de transición a operación',value=v.get('transicion',''),height=85)
                if st.checkbox('Mostrar anexos técnicos e históricos',value=False,key='p4_legacy_impl_'+str(key or 'nuevo')):
                    for field,label in [('presupuesto','Presupuesto y recursos · texto histórico'),
                                        ('piloto','Diseño de piloto · histórico')]:
                        v[field]=st.text_area(label,value=v.get(field,''),height=75)
                    multiple('Tratamientos de riesgo previstos · histórico','riesgos_tratamientos',catalogs.TRATAMIENTOS_RIESGO)
                    choice('Nivel de madurez del servicio · evaluación histórica','nivel_madurez_servicio',catalogs.MADUREZES_SERVICIO,
                           'No supone una medición formal; el valor actual solo se conserva si el usuario lo registró.')
                    if v.get('meta_madurez_propuesta'):st.caption('Meta de madurez propuesta: '+str(v['meta_madurez_propuesta']))
                    if v.get('riesgos_matriz_propuesta'):
                        df=st.data_editor(pd.DataFrame(v['riesgos_matriz_propuesta']),num_rows='dynamic',
                            hide_index=True,use_container_width=True,key='p4_riesgos_editor_'+str(key or 'nuevo'))
                        v['riesgos_matriz_propuesta']=df.fillna('').to_dict('records')
                    if v.get('kpis_propuestos'):
                        st.caption('Indicadores propuestos: sin trasladar metas al catálogo.')
                        df=st.data_editor(pd.DataFrame(v['kpis_propuestos']),num_rows='dynamic',
                            hide_index=True,use_container_width=True,key='p4_kpis_propuestos_editor_'+str(key or 'nuevo'))
                        v['kpis_propuestos']=df.fillna('').to_dict('records')
            with st.expander('Preparación para Paso 05 · requisitos auditables',expanded=True):
                item_preview={**(old or {}),'id':key or '', 'nombre':name,'descripcion':desc,
                     'propuesta_valor':value,'cliente':client,'responsable':owner,'modelo':model,'estado':state}
                check=s.readiness_report(item_preview,details_override=v)
                count=sum(x['cumplido'] for x in check)
                st.progress(count/len(check),text=f'{count}/{len(check)} condiciones cumplidas · evaluación provisional')
                for entry in check:
                    st.caption(('✅' if entry['cumplido'] else '○')+f" {entry['nombre']} · {entry['modulo']}")
                st.caption('No se exige piloto exitoso para ingresar al Paso 05: su ejecución ocurre durante la incorporación. Los estados deben acreditarse documentalmente.')
                v['evidencia_raci_aprobado']=st.text_input('Evidencia de aprobación RACI · opcional para seguimiento',
                    value=v.get('evidencia_raci_aprobado',''))
                v['evidencia_piloto_exitoso']=st.text_input('Evidencia de evaluación del piloto · para transición a operación',
                    value=v.get('evidencia_piloto_exitoso',''))

        clean_markers=st.checkbox('Eliminar solo líneas vacías «Agregar» del taller al guardar',value=False,
                                help='Acción opcional; conserva todos los demás textos originales.')
        if old and old['source_step3_code']:
            if old['source_step3_version'].startswith('V0.39.8 · FICHAS PRELIMINARES'):
                st.caption('Origen: diseño preliminar del taller; no constituye aprobación institucional.')
                st.caption(f"Fuente trazable · {old['source_step3_code']} · {old['source_step3_version']}")
                try:
                    trace=json.loads(old.get('source_step3_json') or '{}')
                    if trace.get('hipotesis_necesidad'):
                        st.info('El taller no desarrolla la necesidad de este servicio: su caracterización y solución son hipótesis de diseño pendientes de validación.')
                    elif trace.get('propuesta_tecnica'):
                        st.caption('Necesidad del taller y solución complementaria propuesta en V0.39.7.')
                    else:
                        st.caption('Caracterización inicial derivada de Taller - Lienzo de Valor.pdf, página 1.')
                except (ValueError,TypeError):pass
            elif old['source_step3_id']:
                st.caption(f"Origen inmutable: Paso 3 · {old['source_step3_code']} · {old['source_step3_version']}")
        if state=='Aprobado' and not (v.get('validacion_cliente') and v.get('validacion_evidencia') and v.get('validacion_fecha')):
            st.info('Estado Aprobado registrado, pero aún debe completarse la evidencia de conformidad para pasar al Paso 05. Consulta el checklist de Implementación.')
        save_draft=st.form_submit_button('Guardar ficha',type='primary')
        register_ans=st.form_submit_button('Registrar validación del ANS',
            help='Genera una versión congelada del acuerdo solo si reúne los compromisos y evidencias esenciales.')
        if save_draft or register_ans:
            try:
                extras=[line.strip().lstrip('•- ').strip() for line in pending_milestones.splitlines() if line.strip()]
                existing={str(x).casefold() for x in v.get('hitos_lista') or []}
                for text in extras:
                    if text and text.casefold() not in existing:
                        v['hitos_lista'].append(text)
                        existing.add(text.casefold())
                if state=='Aprobado' and base('estado','Borrador')!='Aprobado' and (
                    v.get('ans_estado')!='Validado' or not v.get('ans_versiones') or
                    not v.get('evidencia_aprobacion_institucional')):
                    raise s.ValidationError('Antes de cambiar una ficha a Aprobado se requiere un ANS validado y evidencia institucional.')
                if v.get('estado_aprobacion_institucional') in catalogs.ESTADOS_APROBACION[-2:] and not v.get('evidencia_aprobacion_institucional'):
                    raise s.ValidationError('El aval o aprobación institucional requiere evidencia documental.')
                if v.get('estado_aprobacion_institucional')==catalogs.ESTADOS_APROBACION[-1] and state!='Aprobado':
                    raise s.ValidationError('La aprobación institucional definitiva requiere que la ficha de servicio esté en estado Aprobado.')
                if (v.get('estado_presupuesto')=='Presupuesto CapEx/OpEx Aprobado'
                    and not v.get('evidencia_presupuesto_aprobado')):
                    raise s.ValidationError('Para registrar presupuesto aprobado se requiere evidencia de aprobación financiera.')
                # Los hitos añadidos como etiquetas también se registran como filas pendientes.
                v['hitos_registro']=structure.clean_rows('hitos_registro',v.get('hitos_registro') or [])
                existing_hitos={row['Hito'].casefold() for row in v['hitos_registro']}
                for label in v.get('hitos_lista') or []:
                    if str(label).casefold() not in existing_hitos:
                        v['hitos_registro'].append({'Hito':str(label),'Fecha objetivo':'','Responsable':'',
                                                  'Dependencia':'','Estado':'Pendiente'})
                        existing_hitos.add(str(label).casefold())
                if clean_markers:
                    for field in ('caracteristicas','entregables'):
                        v[field]=catalogs.clean_empty_import_markers(v.get(field,''))
                if owner_pick and integrantes and owner_pick!='Sin asignar desde equipo PMO':
                    owner=roster[owner_pick]
                if ans_uploaded is not None:
                    evidence=ans.store_attachment(ans_uploaded.name,ans_uploaded.getvalue(),
                                                  ans_uploaded.type or 'application/octet-stream')
                    v['ans_archivo']=evidence
                    if not v.get('validacion_evidencia'):
                        v['validacion_evidencia']='Adjunto: '+evidence['nombre']+' · SHA-256: '+evidence['sha256']
                if v.get('ans_respuesta_valor') and v.get('ans_respuesta_unidad') in ans.UNIDADES[1:] and v.get('ans_inicio_computo') and v.get('ans_fin_computo'):
                    if old and not v.get('ans_sla_respuesta_original') and s.details(old).get('sla_respuesta'):
                        v['ans_sla_respuesta_original']=s.details(old)['sla_respuesta']
                    v['sla_respuesta']=ans.legacy_time_string(v['ans_respuesta_valor'],
                         v.get('ans_respuesta_unidad'),v.get('ans_inicio_computo'),v.get('ans_fin_computo'))
                if v.get('ans_entrega_valor') and v.get('ans_entrega_unidad') in ans.UNIDADES[1:] and v.get('ans_inicio_computo') and v.get('ans_fin_computo'):
                    if old and not v.get('ans_sla_entrega_original') and s.details(old).get('sla_entrega'):
                        v['ans_sla_entrega_original']=s.details(old)['sla_entrega']
                    v['sla_entrega']=ans.legacy_time_string(v['ans_entrega_valor'],
                         v.get('ans_entrega_unidad'),v.get('ans_inicio_computo'),v.get('ans_fin_computo'))
                if register_ans:
                    v=ans.register_validation(v,actor='Equipo PMO',
                        override_date=ans_date if ans_override else None,motive=ans_motive)
                s.save_service({'codigo':code,'nombre':name,'estado':state,'descripcion':desc,
                 'propuesta_valor':value,'cliente':client,'responsable':owner,'modelo':model,
                 'necesidad':base('necesidad'),'beneficio':base('beneficio'),'detalles':v},key=key)
                st.rerun()
            except Exception as ex:err(ex)
    if old:
        existing_ans=ans.hydrate_legacy(s.details(old))
        if isinstance(existing_ans.get('ans_archivo'),dict):
            try:
                st.download_button('Descargar evidencia del ANS',
                    data=ans.attachment_bytes(existing_ans['ans_archivo']),
                    file_name=existing_ans['ans_archivo']['nombre'],
                    mime=existing_ans['ans_archivo'].get('mime') or 'application/octet-stream',
                    key='p4_ans_download_evidence')
            except (ans.ANSError,KeyError,ValueError):
                st.error('La evidencia guardada no pudo verificarse. Conserva el respaldo anterior.')
        if existing_ans.get('ans_versiones'):
            st.markdown('##### Consulta de versiones validadas')
            historical_versions=list(reversed(existing_ans['ans_versiones']))
            selected_version=st.selectbox('Versión del ANS',range(len(historical_versions)),
                format_func=lambda ix: f"v{historical_versions[ix].get('numero')} · {historical_versions[ix].get('fecha_acuerdo','')}",
                key='p4_ans_snapshot_select')
            selected_snapshot=historical_versions[selected_version]
            historical_evidence=ans.historical_attachment(existing_ans,selected_snapshot.get('contenido',{}).get('evidencia_sha256',''))
            if historical_evidence is not None:
                st.download_button('Descargar evidencia de esta versión',data=ans.attachment_bytes(historical_evidence),
                    file_name=historical_evidence['nombre'],mime=historical_evidence.get('mime'),
                    key='p4_ans_download_selected_evidence')
            st.download_button('Exportar historial validado del ANS (JSON)',
                data=json_bytes({'servicio':old.get('codigo'),
                                 'versiones':existing_ans['ans_versiones']}),
                file_name='ANS_'+str(public_code('servicio',key))+'.json',
                mime='application/json',key='p4_ans_download_versions')
    if old:
        if st.button('Eliminar servicio',type='secondary',key='p4_del_service'):
            try:s.remove_service(key,'Equipo PMO');st.rerun()
            except Exception as ex:err(ex)

@st.dialog('Importar catálogo Excel / CSV',width='large')
def catalog_import_dialog():
    file=st.file_uploader('Selecciona un Excel o CSV',type=['xlsx','csv'],key='p4_catalog_file')
    if file:
        try:
            data=_parsed_catalog(file)
            st.caption(f'{len(data)} registros detectados. La carga agregará servicios, sin reemplazar fichas existentes.')
            st.dataframe(pd.DataFrame(data).head(20),use_container_width=True,hide_index=True)
            if st.button('Confirmar importación',type='primary'):
                result=s.import_catalog(data,'Equipo PMO')
                st.success(f"Cargados: {result['nuevos']} · Existentes: {result['existentes']}")
                st.rerun()
        except Exception as ex:err(ex)


@st.dialog('Restaurar respaldo del Paso 4',width='large')
def restore_dialog():
    st.warning('Esta operación sustituye únicamente los registros del Paso 4. Los Pasos 1, 2 y 3 no se modifican. Descarga antes un respaldo.')
    upload=st.file_uploader('Respaldo JSON del Paso 4',type='json',key='p4_restore_file')
    confirm=st.checkbox('Confirmo que deseo sustituir los datos actuales del Paso 4.',key='p4_restore_confirm')
    if upload and confirm and st.button('Restaurar Paso 4',type='primary'):
        try:
            result=s.restore_step4(json.load(upload),confirm=True)
            st.success(f"Restaurados {result['restaurados']} registros en {result['tablas']} tablas.")
            st.rerun()
        except Exception as ex:err(ex)

@st.dialog('Importar expediente del Paso 3',width='large')
def step3_dialog():
    st.markdown('**Origen del expediente**')
    mode=st.radio('Origen',['Base SQLite compartida','Archivo JSON de Paso 3'],horizontal=True)
    if mode=='Base SQLite compartida':
        from .step3 import step4_transfer
        payload=step4_transfer()
        st.caption(f"{len(payload['proposals'])} propuestas aprobadas disponibles · {len(payload['blocked'])} bloqueadas en origen")
        if payload['blocked']:st.dataframe(pd.DataFrame(payload['blocked']),hide_index=True)
        if st.button('Importar propuestas aprobadas',disabled=not payload['proposals'],type='primary'):
            try:res=s.import_step3(payload);st.success(f"Nuevas: {res['nuevos']} · Existentes: {res['existentes']}");st.rerun()
            except Exception as ex:err(ex)
    else:
        file=st.file_uploader('JSON exportado del Paso 3',type='json',key='p4_step3_upload')
        if file:
            try:
                payload=json.load(file)
                st.caption(f"Propuestas: {len(payload.get('proposals',[]))}")
                if st.button('Importar JSON',type='primary'):
                    res=s.import_step3(payload);st.success(f"Nuevas: {res['nuevos']} · Existentes: {res['existentes']}");st.rerun()
            except Exception as ex:err(ex)

def _catalog_tile(label, value, icon_name, tone):
    icons={'users':'♙','package':'▱','user-round':'♧','zap':'ϟ',
           'clipboard-list':'☷','chart-no-axes-column-increasing':'▥'}
    return (f'<div class="p4v-tile"><span class="p4v-tile-icon p4v-tile-icon-{tone}">{icons.get(icon_name,"•")}</span>'
            f'<div class="p4v-tile-content"><strong>{escape(label)}</strong><span>{escape(value)}</span></div></div>')


def _service_catalog_card(item, metrics):
    public=public_code('servicio',item['id'])
    state=item['estado']
    fields=service_summary(item,s.details(item),metrics)
    missing=s.service_readiness(item)
    tone={'Aprobado':'approved','Validado':'validated','En diseño':'design',
          'En validación':'validation','Suspendido':'suspended'}.get(state,'draft')
    tiles=''.join(_catalog_tile(*field) for field in fields)
    pending=f'{len(missing)} requisito'+('s' if len(missing)!=1 else '')+' pendiente'+('s' if len(missing)!=1 else '')
    # Resumen únicamente visual: no altera IDs, estado, datos, validación ni auditoría.
    st.markdown(f'''<div class="p4v-service-card">
      <div class="p4v-service-header"><span class="p4v-service-code">◈ {escape(public)}</span>
      <span class="p4v-service-status p4v-status-{tone}">{escape(state)}</span></div>
      <h3>{escape(item['nombre'])}</h3>
      <p class="p4v-service-description">{escape(brief(item.get('descripcion'),220,'Descripción pendiente'))}</p>
      <div class="p4v-service-tiles">{tiles}</div>
      <div class="p4v-service-pending">☷ &nbsp;{escape(pending)}</div>
      </div>''',unsafe_allow_html=True)
    left,right=st.columns([1,1],gap='small')
    with left:
        if st.button('↗ Abrir ficha',key=f'p4_open_{item["id"]}',type='primary',use_container_width=True):
            service_dialog(item['id'])
    with right:
        with st.popover('Preparación para Paso 5',use_container_width=True):
            st.markdown('**Requisitos para incorporar el servicio**')
            if missing:
                for text in missing:st.caption('• '+text)
                st.info('La preparación no implica aprobación ni autorización para operar.')
            else:st.success('Ficha técnicamente preparada para transferencia.')


def catalog_page():
    heading(1,'Catálogo y fichas de servicios',
        'Desarrolla los conceptos aprobados en el Paso 3: fichas, activación, modelo de prestación, procesos, ANS y transición.')
    from .value_info_panel import info_panel
    info_panel('Ficha oficial y reutilización del catálogo', 'Los servicios aprobados en este paso se consultan en el Portal de valor del Paso 01. La aprobación del diseño no autoriza por sí sola la operación.')
    a,b,c,d,e=st.columns([1.12,1.08,1.55,1.1,1.15],gap='small')
    with a:
        if st.button('Importar Paso 3',key='p4_import_p3',use_container_width=True):step3_dialog()
    with b:
        if st.button('＋ Nuevo servicio',type='primary',key='p4_new_service',use_container_width=True):service_dialog()
    with c:
        st.button('Carga institucional no disponible',key='p4_load_workshop',use_container_width=True,disabled=True)
    with d:
        st.download_button('Respaldo Paso 4',json_bytes(s.backup_step4()),
            file_name='PMO_CENS_Paso4_Respaldo.json',mime='application/json',
            key='p4_backup_json',use_container_width=True)
    with e:
        if st.button('Restaurar Paso 4',key='p4_open_restore',use_container_width=True):restore_dialog()
    st.caption('Cloud: no se incluyen fichas ni propuestas técnicas institucionales.')
    all_services=s.services()
    metrics=s.metric_list()
    from .alpha03_studio import render_service, render_modalities
    if st.checkbox("Abrir estudio de servicios y ficha 360°", key="a03_show_studio"):
        render_service(all_services)
        render_modalities(all_services)
    ready=sum(not s.service_readiness(x) for x in all_services)
    indicators([('Servicios registrados',len(all_services),'Catálogo PMO','layers'),
                ('En diseño',sum(x['estado']=='En diseño' for x in all_services),'Pendientes de completar','file'),
                ('Aprobados',sum(x['estado']=='Aprobado' for x in all_services),'Estado aprobado','check'),
                ('Listos para Paso 5',ready,'Criterios técnicos completos','target')])
    q,status=st.columns([3,1])
    with q:query=st.text_input('Buscar servicio',placeholder='Servicio, cliente o código (ej. SRV-001)',key='p4_query')
    with status:filter_state=st.selectbox('Estado',['Todos',*s.STATUSES],key='p4_state_filter')
    with st.expander('Importación, plantilla y exportaciones',expanded=False):
        a,b,c,d=st.columns(4)
        with a:
            if st.button('Importar catálogo',use_container_width=True):catalog_import_dialog()
        with b:
            if TEMPLATE.exists():st.download_button('Plantilla Excel',TEMPLATE.read_bytes(),
                file_name='PLANTILLA_PASO4_CATALOGO.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        with c:
            st.download_button('Exportar Excel',_xlsx({'Catálogo':[dict(x,**{
              'codigo_publico':public_code('servicio',x['id']),
              'detalles':json.dumps(s.details(x),ensure_ascii=False)}) for x in all_services]}),
              file_name='PMO_CENS_Paso4_Catalogo.xlsx',
              mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        with d:dl_json('Exportar JSON',s.export_catalog_json(),'PMO_CENS_Paso4_Catalogo.json','p4_export_json_catalog')
    matched=[x for x in all_services if (filter_state=='Todos' or x['estado']==filter_state)
             and query.casefold() in (public_code('servicio',x['id'])+' '+x['codigo']+' '+x['nombre']+' '+x['cliente']).casefold()]
    if not matched:
        st.info('No se encontraron servicios. Puedes importar propuestas del Paso 3 o crear un nuevo servicio.')
        return
    st.caption(f'{len(matched)} servicios en la vista · Resumen de fichas guardadas. «Abrir ficha» permite consultar y editar la información completa.')
    for i in range(0,len(matched),3):
        columns=st.columns(3,gap='medium')
        for col,item in zip(columns,matched[i:i+3]):
            with col:
                with st.container(border=True):_service_catalog_card(item,metrics)

@st.dialog('Métrica del servicio',width='large')
def metric_dialog(key=None):
    current=s.metric(key) if key else None
    services=s.services()
    if not services:st.warning('Primero crea un servicio.');return
    keys=[x['id'] for x in services]
    def get(k,default=''):return current.get(k,default) if current else default
    with st.form('p4_metric_form'):
        sid=st.selectbox('Servicio *',keys,format_func=lambda k:next(x['nombre'] for x in services if x['id']==k),index=keys.index(get('servicio_id',keys[0])) if get('servicio_id',keys[0]) in keys else 0)
        name=st.text_input('Nombre del indicador *',value=get('nombre'))
        kind=st.selectbox('Tipo de indicador',list(s.METRIC_TYPES),index=list(s.METRIC_TYPES).index(get('tipo','Eficiencia')))
        formula=st.text_area('Fórmula',value=get('formula'),height=65)
        c,d=st.columns(2)
        with c:unit=st.text_input('Unidad',value=get('unidad'));baseline=st.text_input('Línea base',value=get('linea_base'))
        with d:target=st.text_input('Meta',value=get('meta'));real=st.text_input('Resultado real (vacío hasta medir)',value=get('real'))
        sense=st.selectbox('Sentido favorable',['mayor','menor'],index=['mayor','menor'].index(get('sentido','mayor')))
        c,d=st.columns(2)
        with c:
            frequencies=['Por evento','Diaria','Semanal','Mensual','Trimestral','Semestral','Anual']
            existing_freq=get('frecuencia','Mensual') or 'Mensual'
            if existing_freq not in frequencies: frequencies=[existing_freq]+frequencies
            freq=st.selectbox('Frecuencia',frequencies,index=frequencies.index(existing_freq))
            owner=staff_picker('Responsable',value=get('responsable'))
        with d:source=st.text_input('Fuente',value=get('fuente'));date_real=iso_date_input('Fecha medición real',get('fecha_medicion'))
        evidence=st.text_input('Evidencia de medición',value=get('evidencia'))
        if st.form_submit_button('Guardar indicador',type='primary'):
            try:
                s.save_metric({'servicio_id':sid,'nombre':name,'tipo':kind,'formula':formula,'unidad':unit,'linea_base':baseline,
                 'meta':target,'real':real,'sentido':sense,'frecuencia':freq,'responsable':owner,'fuente':source,
                 'fecha_medicion':date_real,'evidencia':evidence},key=key);st.rerun()
            except Exception as ex:err(ex)
    if current and st.button('Eliminar indicador',key='p4_remove_metric'):
        try:s.remove_metric(key,'Equipo PMO');st.rerun()
        except Exception as ex:err(ex)

@st.dialog('Detalle del indicador',width='large')
def metric_detail_dialog(key):
    item=s.metric(key)
    if not item:
        st.warning('El indicador ya no existe.')
        return
    svc=s.service(item['servicio_id'])
    st.markdown(f'### {escape(item["nombre"])}')
    st.caption(f'Servicio: {svc["nombre"] if svc else "Sin referencia"} · {item["tipo"]}')
    status,_=metric_state(item)
    st.write(f'**Estado de definición:** {status}')
    for label,key_name in [('Fórmula','formula'),('Unidad','unidad'),('Frecuencia','frecuencia'),
                           ('Línea base','linea_base'),('Meta','meta'),('Resultado real','real'),
                           ('Sentido favorable','sentido'),('Responsable','responsable'),
                           ('Fuente','fuente'),('Fecha de medición','fecha_medicion'),('Evidencia','evidencia')]:
        st.markdown(f'**{label}:** {escape(item.get(key_name) or "Por definir")}')
    st.caption('La definición del indicador no equivale al cumplimiento de la meta.')


def _metric_row(row, item_spec=None, card_view=False):
    """Resumen de solo lectura; un único botón de edición para todo el servicio."""
    status,tone=metric_state(row)
    if item_spec:
        status=item_spec['estado'] if item_spec['estado']!='Aprobada' else ('Con medición' if metrics_model.measurement_list(row['id']) else 'Definida · sin medición')
        tone='ready' if item_spec['estado']=='Aprobada' else 'pending'
    kind=item_spec['categoria'] if item_spec else row.get('tipo','')
    classes={'Eficiencia':'efficiency','Salida':'output','Resultado':'outcome','Percepción':'outcome'}
    sym={'Eficiencia':'◷','Salida':'☷','Resultado':'◎','Percepción':'♡'}
    color=classes.get(kind,'other')
    data=(f'<div class="p4v-metric-title"><span class="p4v-metric-icon p4v-metric-{color}">{sym.get(kind,"◈")}</span>'
          f'<div><strong>{escape(row["nombre"])}</strong><span class="p4v-metric-kind p4v-metric-{color}">{escape(kind)}</span></div></div>')
    meta=(f'<div class="p4v-metric-meta"><span><b>Unidad:</b> {escape(row.get("unidad") or "—")}</span>'
          f'<span><b>Frecuencia:</b> {escape(row.get("frecuencia") or "—")}</span></div>')
    vals=(f'<div class="p4v-metric-target"><span><b>Línea base:</b> {escape(row.get("linea_base") or "—")}</span>'
          f'<span><b>Meta:</b> {escape(row.get("meta") or "—")}</span></div>')
    badge=f'<span class="p4v-metric-state p4v-metric-state-{tone}">{escape(status)}</span>'
    with st.container(border=True):
        if card_view:
            st.markdown(data+meta+vals+f'<div class="p4v-state-wrapper">{badge}</div>',unsafe_allow_html=True)
        else:
            a,b,c=st.columns([2.8,1.7,1.5],vertical_alignment='center')
            with a:st.markdown(data,unsafe_allow_html=True)
            with b:st.markdown(meta,unsafe_allow_html=True)
            with c:st.markdown(vals+f'<div class="p4v-state-wrapper">{badge}</div>',unsafe_allow_html=True)


def metrics_page():
    from . import step4_metric_ui
    heading(2,'Catálogo de indicadores por servicio',
            'Definición metodológica de indicadores separada de sus resultados por periodo.')
    rows=s.metric_list();all_services=s.services()
    specifications=metrics_model.specs()
    approved=sum(x['estado']=='Aprobada' for x in specifications.values())
    registered=sum(bool(metrics_model.measurement_list(x['id'])) for x in rows)
    st.caption(f'{len(rows)} indicadores registrados · {len(specifications)} fichas estructuradas · {approved} definiciones aprobadas · {registered} indicadores con cortes medidos.')
    st.caption('Cloud: no se incluyen definiciones SRV-011 institucionales.')
    a,b,c=st.columns([3,2,1.5],vertical_alignment='bottom')
    ids={x['id']:x['nombre'] for x in all_services}
    with a:
        selected=st.selectbox('Filtrar por servicio',['Todos',*list(ids)],
                format_func=lambda x:'Todos los servicios' if x=='Todos' else ids[x],key='p4_metric_filter')
    with b:order=st.selectbox('Ordenar por',['Servicio y nombre','Tipo y nombre','Estado de definición'],key='p4_metric_order')
    with c:view=st.segmented_control('Vista',['Lista','Tarjetas'],default='Lista',key='p4_metric_view')
    st.download_button('↓ Exportar indicadores Excel',_xlsx({'Indicadores':[dict(x, categoria_efectiva=(specifications.get(x['id']) or {}).get('categoria',x['tipo']), codigo_metrica=(specifications.get(x['id']) or {}).get('codigo','')) for x in rows if selected=='Todos' or x['servicio_id']==selected],
                            'Definiciones':list(specifications.values()),'Mediciones':metrics_model.measurement_list(latest_only=False)}),
        file_name='PMO_CENS_Paso4_Indicadores.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        key='p4_export_metric_xlsx')
    if selected=='Todos' or any(x['id']==selected for x in all_services):
        entries=list(metric_groups(all_services,rows,selected,order))
        occupied={svc['id'] for svc,_ in entries}
        entries.extend((svc,[]) for svc in all_services if svc['id'] not in occupied and (selected=='Todos' or svc['id']==selected))
    else:entries=[]
    if not entries:
        st.info('No hay servicios para mostrar.');return
    st.markdown('<div class="p4v-metrics-banner">Un solo botón <b>Gestionar fichas</b> por servicio. '
                'Las definiciones y resultados reales se registran en formularios separados.</div>',unsafe_allow_html=True)
    for index,(svc,items) in enumerate(entries):
        label=f'{public_code("servicio",svc["id"])} · {svc["nombre"]} · {len(items)} indicador{"es" if len(items)!=1 else ""}'
        with st.expander(label,expanded=index<2):
            caption_col,action_col=st.columns([5,1.5],vertical_alignment='center')
            with caption_col:
                st.caption(f'{len(items)} fichas existentes · {sum((specifications.get(x["id"]) or {}).get("estado")=="Aprobada" for x in items)} aprobadas')
            with action_col:
                if st.button('Gestionar fichas',key='p4_manage_metrics_'+svc['id'],type='primary',use_container_width=True):
                    step4_metric_ui.manager_dialog(svc['id'])
            if not items:st.info('Este servicio todavía no tiene indicadores. Usa «Gestionar fichas» para definirlos.')
            elif view=='Tarjetas':
                for start in range(0,len(items),2):
                    for col,item in zip(st.columns(2),items[start:start+2]):
                        with col:_metric_row(item,specifications.get(item['id']),card_view=True)
            else:
                for item in items:_metric_row(item,specifications.get(item['id']))

@st.dialog('Integrante del equipo PMO',width='large')
def member_dialog(key=None):
    old=s.member(key) if key else None
    profile=s.member_profile(key) if key else {}
    current=json.loads(old['habilidades_json']) if old else {}
    with st.form('p4_member_form'):
        st.text_input('Código PMO · consecutivo',value=public_code('integrante',key) if key else next_public_code('integrante'),disabled=True)
        name=st.text_input('Integrante *',value=old['nombre'] if old else '')
        role=st.text_input('Rol *',value=old['rol'] if old else '')
        cap=st.number_input('Capacidad de dedicación para PMO (%)',0,100,int(old['capacidad']) if old else 100,
                            help='Disponibilidad declarada para servicios PMO. No representa dedicación contratada ni asignación efectiva.')
        t1,t2,t3=st.tabs(['Datos organizacionales','Competencias y evidencias','Experiencia y disponibilidad'])
        new_profile={}
        with t1:
            a,b=st.columns(2)
            with a:
                new_profile['dependencia']=st.text_input('Dependencia',value=profile.get('dependencia',''))
                new_profile['equipo']=st.text_input('Equipo de trabajo',value=profile.get('equipo',''))
            with b:
                new_profile['correo']=st.text_input('Correo institucional',value=profile.get('correo',''))
                new_profile['dedicacion_referente']=st.text_input('Periodo o referencia de dedicación',value=profile.get('dedicacion_referente',''),placeholder='Ej. disponibilidad mensual por acordar')
        with t2:
            st.caption('Escala CENS 0–5. 0 = no evaluada; 1–5 = valoración documentable. Las puntuaciones ya registradas se conservan.')
            skills={}
            for i in range(0,len(s.SKILLS),2):
                for col,skill in zip(st.columns(2),s.SKILLS[i:i+2]):
                    with col:
                        score=st.selectbox(skill,list(range(6)),index=int(current.get(skill,0)),key=f'p4_skill_{i}_{skill}')
                        if score:skills[skill]=score
            new_profile['evidencia_competencias']=st.text_area('Evidencias o método de evaluación',value=profile.get('evidencia_competencias',''))
        with t3:
            new_profile['formacion']=st.text_area('Formación académica y complementaria',value=profile.get('formacion',''))
            new_profile['experiencia']=st.text_area('Experiencia relevante en proyectos y PMO',value=profile.get('experiencia',''))
            new_profile['certificaciones']=st.text_area('Certificaciones y formación acreditada',value=profile.get('certificaciones',''))
            new_profile['especialidades']=st.text_area('Áreas de especialidad / servicios que puede apoyar',value=profile.get('especialidades',''))
            new_profile['disponibilidad']=st.text_area('Restricciones, disponibilidad y condiciones de asignación',value=profile.get('disponibilidad',''))
            new_profile['observaciones']=st.text_area('Observaciones y oportunidades de desarrollo',value=profile.get('observaciones',''))
        if st.form_submit_button('Guardar ficha del integrante',type='primary'):
            try:
                s.save_member({'nombre':name,'rol':role,'capacidad':cap,'habilidades':skills,'perfil':new_profile},key)
                st.rerun()
            except Exception as ex:err(ex)

@st.dialog('Propuesta de competencias para servicios',width='large')
def requirement_suggestions_dialog():
    proposed=s.preview_requirements()
    st.info('Plantilla orientativa basada en el tipo de servicio PMO: los niveles sugeridos NO son requisitos aprobados ni calificaciones reales. Solo se incorporan competencias aún no configuradas.')
    if not proposed:return st.success('No hay requisitos sugeridos pendientes de agregar.')
    st.caption(f'{len(proposed)} competencias sugeridas para revisar con los responsables de los servicios.')
    st.dataframe(pd.DataFrame(proposed).drop(columns=['servicio_id','origen']),hide_index=True,use_container_width=True)
    confirm=st.checkbox('Acepto crear estos requisitos como propuesta editable, pendiente de validación experta.')
    if st.button('Agregar requisitos propuestos',disabled=not confirm,type='primary'):
        try:
            total=s.add_suggested_requirements()
            st.success(f'{total} registros creados; las competencias existentes quedaron intactas.');st.rerun()
        except Exception as ex:err(ex)

@st.dialog('Competencia requerida')
def requirement_dialog():
    services=s.services()
    if not services:st.warning('Registra un servicio primero.');return
    with st.form('p4_req_form'):
        sid=st.selectbox('Servicio', [x['id'] for x in services],format_func=lambda k:next(x['nombre'] for x in services if x['id']==k))
        skill=st.selectbox('Competencia',s.SKILLS)
        score=st.select_slider('Nivel requerido',options=[1,2,3,4,5],value=3)
        if st.form_submit_button('Guardar requisito',type='primary'):
            try:s.save_requirement(sid,skill,score);st.rerun()
            except Exception as ex:err(ex)

@st.dialog('Asignación de recursos')
def allocation_dialog():
    people=s.members();svcs=s.services()
    if not people or not svcs:st.warning('Se requiere al menos un integrante y un servicio.');return
    with st.form('p4_alloc_form'):
        person=st.selectbox('Integrante',[x['id'] for x in people],format_func=lambda k:next(x['nombre'] for x in people if x['id']==k))
        sid=st.selectbox('Servicio',[x['id'] for x in svcs],format_func=lambda k:next(x['nombre'] for x in svcs if x['id']==k))
        pct=st.number_input('Dedicación (%)',0,100,10)
        if st.form_submit_button('Guardar asignación',type='primary'):
            try:s.save_allocation(person,sid,pct);st.rerun()
            except Exception as ex:err(ex)

@st.dialog('Acción para cerrar brechas')
def training_dialog():
    people=s.members()
    if not people:st.warning('Registra un integrante primero.');return
    with st.form('p4_training_form'):
        person=st.selectbox('Integrante',[x['id'] for x in people],format_func=lambda k:next(x['nombre'] for x in people if x['id']==k))
        skill=st.selectbox('Competencia',s.SKILLS)
        action=st.text_area('Acción de desarrollo *')
        c,d=st.columns(2)
        with c:when=iso_date_input('Fecha meta');owner=staff_picker('Responsable')
        with d:status=st.selectbox('Estado',['Pendiente','En curso','Completada']);evidence=st.text_input('Evidencia')
        if st.form_submit_button('Guardar acción',type='primary'):
            try:s.add_training(person,skill,action,when,status,owner,evidence);st.rerun()
            except Exception as ex:err(ex)

def resources_page():
    a,b=st.columns([4,2])
    with a:heading(3,'Recursos y competencias','Contrasta competencias requeridas con capacidades disponibles; gestiona asignaciones y brechas de desarrollo.')
    with b:
        c,d=st.columns(2)
        with c:
            if st.button('Integrante',key='p4_new_member'):member_dialog()
        with d:
            if st.button('Competencia requerida',key='p4_new_skill',type='primary'):requirement_dialog()
    if st.button('Proponer competencias por servicio · por validar',key='p4_suggest_requirements'):
        requirement_suggestions_dialog()
    team=s.members();req=s.requirements();alloc=s.allocations();svcs=s.services()
    gaps=sum(x['brecha'] is not None and x['brecha']>0 for svc in svcs for x in s.competency_gaps(svc['id']))
    overloaded=sum(x['restante']<0 for x in s.capacity_summary())
    indicators([('Integrantes',len(team),'Recursos de la PMO','users'),('Competencias configuradas',len(req),'Por servicio','layers'),
                ('Brechas detectadas',gaps,'Entre requeridas y disponibles','alert'),('Sobrecargas',overloaded,'Asignación superior a capacidad','clock')])
    a,b,c,d=st.tabs(['Mapa de competencias','Equipo PMO','Asignación de recursos','Plan de desarrollo'])
    with a:
        if not svcs:st.info('Registra un servicio para ver la matriz de competencias.')
        else:
            selected=st.selectbox('Servicio para analizar',[x['id'] for x in svcs],format_func=lambda k:next(x['nombre'] for x in svcs if x['id']==k))
            matrix=s.competency_gaps(selected)
            left,right=st.columns([3,2])
            with left:
                st.subheader('Matriz requerida vs. disponible')
                if matrix:st.dataframe(pd.DataFrame(matrix),hide_index=True,use_container_width=True)
                if matrix and any(x['sin_asignacion'] for x in matrix):st.caption('Sin integrante asignado: no se calcula brecha real de capacidad.')
                if not matrix:st.info('Sin requisitos registrados.')
                if st.checkbox('Ver mapa de calor de competencias evaluadas',key='a03_competency_heatmap'):
                    from .alpha03_studio import render_competencies, service_views
                    views=service_views(selected)
                    render_competencies(st,views['Competencias'],views['Asignaciones'])
                if st.button('Agregar requisito'):requirement_dialog()
                if matrix:
                    with st.expander('Retirar requisito de competencia'):
                        skill=st.selectbox('Competencia requerida a retirar',[x['competencia'] for x in matrix],key='p4_req_del_select')
                        if st.button('Retirar requisito',key='p4_req_delete'):
                            try:s.remove_requirement(selected,skill);st.rerun()
                            except Exception as ex:err(ex)
            with right:
                st.subheader('Capacidad asignada')
                for m in team:
                    pct=sum(a['porcentaje'] for a in alloc if a['servicio_id']==selected and a['integrante_id']==m['id'])
                    if pct:st.markdown(f"**{escape(m['nombre'])}** · {pct}%");st.progress(pct/100)
                if st.button('Asignar recurso',key='p4_req_assign'):allocation_dialog()
    with b:
        st.subheader('Perfiles y competencias disponibles')
        for x in s.capacity_summary():
            left,right=st.columns([5,1])
            with left:
                skills=json.loads(x['habilidades_json'])
                st.markdown(f"**{public_code('integrante',x['id'])} · {escape(x['nombre'])}** · {escape(x['rol'])} · Capacidad {x['capacidad']}% · Asignado {x['asignado']}% · {len(skills)}/10 competencias")
                profile=s.member_profile(x['id'])
                st.caption('Dependencia: '+(profile.get('dependencia') or 'Por registrar')+' · Equipo: '+(profile.get('equipo') or 'Por registrar'))
                st.progress(min(1,x['asignado']/max(1,x['capacidad'])))
            with right:
                if st.button('Editar',key=f'p4_member_edit_{x["id"]}'):member_dialog(x['id'])
        if team:
            with st.expander('Ficha de recursos y competencias del integrante',expanded=len(team)==1):
                selection=st.selectbox('Integrante PMO',[x['id'] for x in team],
                     format_func=lambda k:public_code('integrante',k)+' · '+next(x['nombre'] for x in team if x['id']==k),key='p4_member_detail_pick')
                detail=s.member_file(selection)
                profile=detail['perfil'];skills=json.loads(detail['habilidades_json'])
                st.markdown('**'+public_code('integrante',selection)+' · '+escape(detail['nombre'])+'** · '+escape(detail['rol']))
                fields=[('Dependencia',profile.get('dependencia')),('Equipo',profile.get('equipo')),
                    ('Correo',profile.get('correo')),('Formación',profile.get('formacion')),
                    ('Experiencia',profile.get('experiencia')),('Certificaciones',profile.get('certificaciones')),
                    ('Especialidades',profile.get('especialidades')),('Evidencias',profile.get('evidencia_competencias'))]
                for name,value in fields:
                    st.caption('**'+name+':** '+(escape(value) if value else 'Por completar'))
                st.markdown('**Competencias evaluadas · 0 indica sin evaluación**')
                frame=pd.DataFrame([{'Competencia':sk,'Nivel':int(skills.get(sk,0))} for sk in s.SKILLS])
                st.dataframe(frame,hide_index=True,use_container_width=True)
                if detail['asignaciones']:st.caption(f"Asignaciones registradas: {len(detail['asignaciones'])}")
                if detail['formacion_pendiente']:st.caption(f"Acciones de desarrollo: {len(detail['formacion_pendiente'])}")
                st.download_button('Descargar ficha del integrante (JSON)',json_bytes(detail),
                    file_name=f'PMO_CENS_{public_code("integrante",selection)}.json',mime='application/json',key='p4_member_file_export')
        if not team:st.info('No hay integrantes registrados.')
    with c:
        st.subheader('Plan de dedicación por servicio')
        people={x['id']:x['nombre'] for x in team};service_names={x['id']:x['nombre'] for x in svcs}
        if alloc:st.dataframe(pd.DataFrame([{'Integrante':people.get(x['integrante_id']),'Servicio':service_names.get(x['servicio_id']),
                   'Dedicación %':x['porcentaje']} for x in alloc]),hide_index=True,use_container_width=True)
        else:st.info('Aún no existen asignaciones.')
        if st.button('Nueva asignación',key='p4_alloc_new'):allocation_dialog()
        if alloc:
            with st.expander('Retirar asignación'):
                candidates={f"{people.get(x['integrante_id'],'—')} · {service_names.get(x['servicio_id'],'—')} · {x['porcentaje']}%":x for x in alloc}
                picked=st.selectbox('Asignación que se retirará',list(candidates),key='p4_alloc_del_select')
                if st.button('Retirar asignación',key='p4_alloc_del'):
                    try:
                        x=candidates[picked];s.remove_allocation(x['integrante_id'],x['servicio_id']);st.rerun()
                    except Exception as ex:err(ex)
    with d:
        st.subheader('Acciones para cerrar brechas')
        tr=s.training_list()
        if tr:st.dataframe(pd.DataFrame(tr),hide_index=True,use_container_width=True)
        else:st.info('Aún no existen acciones de desarrollo.')
        if st.button('Acción de formación',key='p4_train_new'):training_dialog()
    st.info('La escala de competencia 1–5 es una adaptación operativa de CENS. No sustituye una evaluación formal del desempeño del personal.')
    st.download_button('Exportar recursos Excel',_xlsx({'Equipo':[{**x,**s.member_profile(x['id']),'Código PMO':public_code('integrante',x['id'])} for x in team],
       'Competencias':req,'Asignaciones':alloc,'Formación':s.training_list()}),
       file_name='PMO_CENS_Paso4_Recursos.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@st.dialog('Nuevo corte de autoevaluación')
def evaluation_dialog():
    with st.form('p4_eval_create'):
        owner=st.text_input('Responsable de la evaluación *')
        if st.form_submit_button('Crear evaluación',type='primary'):
            try:
                key=s.create_evaluation(owner)
                st.session_state['p4_eval_active']=key
                st.rerun()
            except Exception as ex:err(ex)

def eval_page():
    a,b=st.columns([4,2])
    with a:heading(4,'Evaluación metodológica PMI','Autoevaluación del desarrollo de servicios: 35 criterios funcionalmente parafraseados en siete dimensiones.')
    with b:
        if st.button('Nueva evaluación',type='primary'):evaluation_dialog()
    evs=s.evaluation_list()
    if not evs:
        indicators([('Preguntas respondidas','0/35','Sin evaluación','file'),('Puntaje total','—','Máximo matemático 175','chart'),
                    ('Dimensiones completas','0/7','Pendiente de evaluar','layers'),('Clasificación','Pendiente','Solo con 35 respuestas','target')])
        st.info('Crea un corte de autoevaluación para comenzar.');return
    ids=[x['id'] for x in evs]
    if st.session_state.get('p4_eval_active') not in ids:st.session_state['p4_eval_active']=ids[0]
    eid=st.selectbox('Versión de evaluación',ids,key='p4_eval_active',format_func=lambda k:next(f"Corte v{x['version']} · {x['responsable']} · {x['estado']}" for x in evs if x['id']==k))
    summ=s.evaluation_summary(eid)
    indicators([('Preguntas respondidas',f"{summ['respondidas']}/35",'Avance de la evaluación','file'),
                ('Puntaje total',summ['puntaje'] if summ['puntaje'] is not None else '—','Máximo matemático 175','chart'),
                ('Dimensiones completas',f"{sum(x['respondidas']==5 for x in summ['dimensiones'])}/7",'Cada dimensión contiene cinco preguntas','layers'),
                ('Clasificación',summ['clasificacion'] or 'Pendiente','Solo con 35 respuestas','target')])
    st.info('Nota metodológica: 35 ítems × 5 = 175 puntos. La guía consultada imprime el rango Excelente 154–160; CENS aplica provisionalmente 154–175 para evitar valores sin categoría. No es corrección oficial del PMI.')
    a,b=st.columns([3,2])
    with a:
        st.subheader('Perfil por dimensión')
        data=pd.DataFrame([{'Dimensión':f'D{i+1} · {x["nombre"]}', 'Promedio':x['promedio'] or 0} for i,x in enumerate(summ['dimensiones'])]).set_index('Dimensión')
        st.bar_chart(data,color='#67618F')
    with b:
        st.subheader('Criterios de interpretación')
        for name,lo,hi in [('Excelente',154,175),('Bien',131,153),('Promedio',102,130),('Pobre',68,101),('Crítico',35,67)]:
            st.caption(f'{name}: {lo}–{hi} puntos')
        st.caption('Los valores 0 de gráficos representan dimensiones sin respuesta y no calificaciones definitivas.')
    recorded={x['numero']:x for x in s.answers(eid)}
    st.subheader('Instrumento y evidencias')
    labels=[f'D{i+1} · {dim}' for i,(dim,_) in enumerate(s.DIMENSIONS)]
    selected=st.selectbox('Dimensión',range(7),format_func=lambda i:labels[i],key='p4_eval_dim')
    dim_name,questions=s.DIMENSIONS[selected]
    st.caption(f'{summ["dimensiones"][selected]["respondidas"]}/5 respuestas · {summ["dimensiones"][selected]["subtotal"]} puntos parciales')
    editable=summ['estado']!='Finalizada'
    with st.form(f'p4_eval_dim_form_{eid}_{selected}'):
        values=[]
        for i,q in enumerate(questions):
            num=selected*5+i+1;cur=recorded.get(num)
            st.markdown(f'**{num:02d}. {escape(q)}**')
            c1,c2,c3=st.columns([1,2,2])
            with c1:score=st.selectbox('Puntuación', ['Sin responder',1,2,3,4,5],index=(cur['valor'] if cur else 0),key=f'p4_score_{eid}_{num}',disabled=not editable)
            with c2:obs=st.text_input('Observación',value=cur['observacion'] if cur else '',key=f'p4_obs_{eid}_{num}',disabled=not editable)
            with c3:evid=st.text_input('Evidencia / referencia',value=cur['evidencia'] if cur else '',key=f'p4_evid_{eid}_{num}',disabled=not editable)
            values.append((num,None if score=='Sin responder' else score,obs,evid))
        if st.form_submit_button('Guardar respuestas de esta dimensión',type='primary',disabled=not editable):
            try:
                for num,rating,obs,evid in values:s.save_answer(eid,num,rating,obs,evid,summ['responsable'])
                st.rerun()
            except Exception as ex:err(ex)
    c,d=st.columns(2)
    with c:
        dl_json('Exportar evaluación JSON',s.assessment_export(eid),'PMO_CENS_Paso4_Evaluacion_PMI.json','p4_dl_assessment')
        st.download_button('Exportar evaluación Excel',_xlsx({'Evaluación':[summ],'Respuestas':s.answers(eid),'Dimensiones':summ['dimensiones']}),
                           file_name='PMO_CENS_Paso4_Evaluacion.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with d:
        if st.button('Finalizar evaluación',type='primary',disabled=not editable or summ['respondidas']!=35):
            try:s.finish_evaluation(eid,summ['responsable']);st.rerun()
            except Exception as ex:err(ex)
    st.subheader('Historial de cortes')
    st.dataframe(pd.DataFrame([{'Versión':x['version'],'Responsable':x['responsable'],'Estado':x['estado'],
                    'Puntaje':x['puntaje'],'Clasificación':x['clasificacion'],'Fecha':x['creado_en']} for x in evs]),hide_index=True,use_container_width=True)

def page(section):
    from .config import database_path
    if database_path().parent.name.lower()=='demostracion':
        st.warning('Modo demostración: los servicios, equipos, indicadores y evaluaciones de esta base son **ficticios**. No representan decisiones ni acuerdos institucionales de CENS.')
    if section==NAV[0]:catalog_page()
    elif section==NAV[1]:metrics_page()
    elif section==NAV[2]:resources_page()
    elif section==NAV[3]:eval_page()
    else:st.error('Sección del Paso 4 no reconocida.')
    st.divider()
    transfer=s.step5_transfer()
    with st.expander(f"Preparación para el Paso 5 · {len(transfer['services'])} listos / {len(transfer['blocked'])} pendientes"):
        if transfer['blocked']:
            st.dataframe(pd.DataFrame([{'Servicio':x['codigo'],'Pendiente':', '.join(x['faltan'])} for x in transfer['blocked']]),use_container_width=True,hide_index=True)
        else:st.caption('No hay servicios pendientes de preparación.')
        dl_json('Descargar expediente para el Paso 5',transfer,'PMO_CENS_Paso4_Transferencia_Paso5.json','p4_dl_step5')
