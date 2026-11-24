"""Paso 1 visual V0.2. Navegación inspirada en el HTML suministrado.

No interpreta cifras ilustrativas del prototipo como datos corporativos.
"""
from __future__ import annotations
import calendar
import html
from datetime import date
from pathlib import Path
from collections import Counter
import streamlit as st
from .staff_picker import staff_picker
from .clients import list_clients, get_client, audit_history, counts, dependencies
from .client_forms import client_form, _csv_bytes
from . import awareness as aw
from . import assessment as ass
from .clients import ValidationError
from .excel_import import import_xlsx

NAV = [
 ('Clientes internos','👥'), ('Portal y biblioteca','📚'),
 ('Eventos y campañas','📅'), ('Consultas e interacciones','💬'),
 ('Tablero de concienciación','📊'), ('Autoevaluación PMI','✅'),
 ('Plan de mejora y cierre','🗂️')
]


def e(value):
    return html.escape(str(value or ''))


def apply_theme():
    st.markdown('''<style>
    :root{--navy:#10374B;--teal:#0C989B;--orange:#EC9148;--bg:#F4F7FA;--ink:#203648;--muted:#718497;--line:#E1E8EF}
    .stApp{background:var(--bg)!important;color:var(--ink)}
    [data-testid="stSidebar"]{background:var(--navy)!important;min-width:240px!important;max-width:240px!important}
    [data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding:1.1rem .7rem .65rem}
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span{color:#DAE7EC}
    [data-testid="stSidebar"] [role="radiogroup"]>label{border-radius:10px;padding:9px 8px!important;margin:2px 0;min-height:42px}
    [data-testid="stSidebar"] [role="radiogroup"]>label:has(input:checked){background:#ffffff1d!important;border-left:3px solid #63D4CB}
    [data-testid="stSidebar"] [role="radiogroup"]>label:hover{background:#ffffff12}
    [data-testid="stSidebar"] [data-testid="stRadio"]>label{display:none}
    [data-testid="stSidebar"] .stMarkdown{margin-bottom:0}
    [data-testid="stSidebar"] hr{border-color:#ffffff22}
    .block-container{max-width:1630px!important;padding-top:1.3rem!important;padding-left:2rem!important;padding-right:2rem!important;padding-bottom:3rem!important}
    .pmo-brand{padding:12px 9px 18px;border-bottom:1px solid #ffffff1a;margin-bottom:19px}
    .pmo-brand strong{font-weight:850;font-size:15px;letter-spacing:.7px;color:#fff}
    .pmo-brand small{font-size:10px;letter-spacing:1.3px;color:#91B4C6;display:block;margin-top:6px}
    .pmo-side-label{font-size:10px;color:#90B1C1;letter-spacing:1.3px;font-weight:800;margin:17px 9px 9px;text-transform:uppercase}
    .pmo-side-step{margin:0 3px 15px;background:#ffffff13;border-radius:10px;padding:12px 10px;color:#fff;font-size:12px;font-weight:750}
    .pmo-side-num{display:inline-block;background:#EC9148;color:#fff;padding:5px 8px;border-radius:8px;margin-right:6px;font-weight:850}
    .pmo-sidebar-bottom{border:1px solid #ffffff1a;border-radius:12px;background:#ffffff0c;padding:14px;margin-top:26px;font-size:11px;color:#BDD6E0}
    .pmo-sidebar-bottom strong{color:#fff;display:block;margin:8px 0}
    .pmo-progress{height:6px;border-radius:5px;background:#ffffff23;overflow:hidden}.pmo-progress span{display:block;height:100%;width:10%;background:#65D2CB}
    .pmo-topbar{background:white;border:1px solid #E1E8EF;border-radius:10px;padding:13px 19px;display:flex;justify-content:space-between;align-items:center;color:#8B9BAC;font-size:12px;margin-bottom:25px}
    .pmo-topbar b{color:#203648}.pmo-topmark{background:#E7F7F6;border-radius:100%;font-weight:800;color:#117C80;padding:7px 8px}
    .pmo-eyebrow{font-size:10.5px;text-transform:uppercase;letter-spacing:1.3px;font-weight:850;color:#0C989B;margin-bottom:8px}
    .pmo-eyebrow:before{content:'';background:#EC9148;width:7px;height:7px;display:inline-block;border-radius:50%;margin-right:8px}
    .pmo-title{font-size:26px;font-weight:800;color:#203648;letter-spacing:-.7px;line-height:1.2;margin:0 0 7px}
    .pmo-subtitle{font-size:12.5px;color:#718497;margin:0 0 21px;line-height:1.7}
    .pmo-kpi{border:1px solid #E1E8EF;border-radius:14px;background:#fff;padding:18px 17px 16px;box-shadow:0 8px 24px rgba(20,50,71,.045);min-height:120px;margin-bottom:4px}
    .pmo-kpi-head{display:flex;justify-content:space-between;gap:9px;align-items:center;font-size:11px;font-weight:700;color:#718497}
    .pmo-kpi-icon{width:30px;height:30px;border-radius:9px;background:#E8F7F8;color:#178F94;text-align:center;line-height:30px;font-size:15px}
    .pmo-kpi-icon.orange{background:#FFF2E5;color:#D47E38}.pmo-kpi-icon.blue{background:#EAF0FA;color:#567CAC}.pmo-kpi-icon.purple{background:#F4ECFC;color:#8C67AD}
    .pmo-kpi-value{font-size:26px;color:#203648;font-weight:820;margin:11px 0 3px;line-height:1.24;letter-spacing:-.6px}
    .pmo-kpi-foot{font-size:11px;color:#8798A6}
    .pmo-card-header{font-size:14px;font-weight:780;color:#203648;margin:1px 0 5px}
    .pmo-card-caption{font-size:11px;color:#718497;margin-bottom:8px}
    .pmo-client-hero{background:linear-gradient(135deg,#F1F9FA,#F7FAFC);border:1px solid #E4F0F2;border-radius:12px;padding:17px;margin:4px 0 14px}
    .pmo-initial{border-radius:13px;background:#D1EFF0;color:#197E85;width:45px;height:45px;line-height:45px;text-align:center;font-weight:900;margin-bottom:12px}
    .pmo-person-title{font-size:17px;font-weight:800;margin-bottom:4px}.pmo-minor{font-size:11.4px;color:#718497}
    .pmo-pair{border-bottom:1px solid #F0F3F6;padding:9px 0;display:flex;justify-content:space-between;gap:6px;font-size:12px}
    .pmo-pair span{color:#7F91A1}.pmo-pair b{color:#243746;text-align:right}
    .pmo-soft{background:#F7FAFC;padding:13px;border:1px solid #ECF1F5;border-radius:11px;color:#536F80;font-size:12px;margin:8px 0 14px}
    .pmo-hero{border-radius:16px;background:linear-gradient(110deg,#123F54,#1C6870);padding:29px 31px;margin-bottom:15px;color:white;min-height:184px}
    .pmo-hero small{color:#ACE4DC;letter-spacing:1.4px;font-size:10px;font-weight:800}
    .pmo-hero h2{font-size:23px;font-weight:800;line-height:1.26;margin:12px 0 9px;max-width:600px;color:white}
    .pmo-hero p{font-size:12px;color:#CEE8E9;max-width:640px}
    .pmo-resource{border:1px solid #E1E8EF;border-radius:13px;background:#fff;padding:17px;min-height:155px}
    .pmo-resource strong{font-size:12.5px;color:#203648}.pmo-resource p{color:#718497;font-size:12px;line-height:1.65;margin-top:9px}
    .pmo-pill{background:#E3F6F3;color:#087F73;border-radius:100px;font-size:10px;font-weight:800;padding:5px 9px;display:inline-block;margin-top:8px}
    .pmo-hint{border:1px solid #E1E8EF;border-left:3px solid #0C989B;background:white;border-radius:10px;padding:13px 15px;color:#64748B;font-size:12px;margin-top:12px}
    [data-testid="stVerticalBlockBorderWrapper"]>div{border-color:#E1E8EF!important;border-radius:14px!important;background:white!important;box-shadow:0 8px 24px rgba(20,50,71,.035)}
    [data-testid="stDataFrame"]{border-radius:10px;overflow:hidden}
    div.stButton>button[kind="primary"],div.stFormSubmitButton>button[kind="primary"]{background:#10374B;color:white;border-color:#10374B;border-radius:9px}
    div.stButton>button,div.stDownloadButton>button,div.stFormSubmitButton>button{border-radius:9px!important;min-height:35px}
    h3{font-size:1rem!important}
    @media(max-width:950px){.block-container{padding-left:1rem!important;padding-right:1rem!important}}
    </style>''',unsafe_allow_html=True)
    # V0.9: capa visual centralizada; no altera widgets, estados ni lógica.
    from .design_system import apply_corporate_theme
    apply_corporate_theme()
    from .form_system import apply_form_standard
    apply_form_standard()


def sidebar():
    from .panel_layout import apply_panel_theme
    apply_panel_theme()
    from .design_system import apply_alpha_theme
    from .alpha_navigation import HOME, STEPS, go_to
    apply_alpha_theme()
    from .alpha02_sidebar import render_steps, render_components
    st.markdown("<style>" + (Path(__file__).parent / "assets/css/alpha02.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
    from .beta03_visual import apply as apply_beta03_visual
    apply_beta03_visual(st)
    from .step2_ui import NAV as P2_NAV
    from .step3_ui import NAV as P3_NAV
    from .step4_ui import NAV as P4_NAV
    from .step5_ui import NAV as P5_NAV
    from .step6_ui import NAV as P6_NAV
    from .step7_ui import NAV as P7_NAV
    from .step8_ui import NAV as P8_NAV
    from .step9_ui import NAV as P9_NAV
    from .step10_ui import NAV as P10_NAV
    with st.sidebar:
        from .panel_layout import render_sidebar_branding, render_section_heading, render_component_heading, render_sidebar_footers
        # pmo-brand-pro remains the branding class, rendered by panel_layout.
        render_sidebar_branding()
        st.button('Inicio · Control Tower', icon=':material/dashboard:', key='alpha_home_nav', on_click=go_to, args=(HOME,),
                  type='primary' if st.session_state.get('pmo_active_step') is None else 'secondary', use_container_width=True)
        render_section_heading('RECORRIDO FLYWHEEL · 10 PASOS', 'layers')
        step=render_steps()
        if step is None:
            st.caption('Selecciona cualquiera de los diez pasos para comenzar.')
            return HOME, 'Control Tower'
        # V0.38: contexto cromático de presentación, no cambia el radio ni su estado.
        from .icon_manager import STAGE_BY_STEP
        stage_name = STAGE_BY_STEP[int(step[5:7])-1]
        st.markdown(f'<span class="pmo-stage-context" data-stage="{stage_name}" aria-hidden="true"></span>', unsafe_allow_html=True)
        if step.startswith('Paso 01'):
            render_component_heading()
            names=[i[0] for i in NAV]
            page=render_components('pmo_active_page',names,int(step[5:7]))
            # V0.39.28: las importaciones viven dentro de cada componente,
            # nunca como páginas adicionales o accesos externos en el sidebar.
        elif step.startswith('Paso 02'):
            render_component_heading()
            names=[i[0] for i in P2_NAV]
            # V0.39.17: recupera la navegación histórica sin borrar datos de sesión.
            from .step2_consolidated_ui import ALIASES as P2_LEGACY_ALIASES
            prior = st.session_state.get('pmo_active_p2_page')
            if prior in P2_LEGACY_ALIASES:
                st.session_state['pmo_active_p2_page'] = P2_LEGACY_ALIASES[prior]
            if st.session_state.get('pmo_active_p2_page') not in names:
                st.session_state['pmo_active_p2_page']='Resumen ejecutivo'
            page=render_components('pmo_active_p2_page',names,int(step[5:7]))
        elif step.startswith('Paso 03'):
            render_component_heading()
            names=list(P3_NAV)
            # V0.39.18: conservar el acceso desde las tres denominaciones anteriores.
            from .step3_ui import ALIASES as P3_LEGACY_ALIASES
            prior=st.session_state.get('pmo_active_p3_page')
            if prior in P3_LEGACY_ALIASES:
                st.session_state['pmo_active_p3_page']=P3_LEGACY_ALIASES[prior]
            if st.session_state.get('pmo_active_p3_page') not in names:
                st.session_state['pmo_active_p3_page']=names[0]
            page=render_components('pmo_active_p3_page',names,int(step[5:7]))
        elif step.startswith('Paso 04'):
            render_component_heading()
            names=list(P4_NAV)
            if st.session_state.get('pmo_active_p4_page') not in names:
                st.session_state['pmo_active_p4_page']=names[0]
            page=render_components('pmo_active_p4_page',names,int(step[5:7]))
        elif step.startswith('Paso 05'):
            render_component_heading()
            names=list(P5_NAV)
            if st.session_state.get('pmo_active_p5_page') not in names:
                st.session_state['pmo_active_p5_page']=names[0]
            page=render_components('pmo_active_p5_page',names,int(step[5:7]))
        elif step.startswith('Paso 06'):
            render_component_heading()
            names=list(P6_NAV)
            if st.session_state.get('pmo_active_p6_page') not in names:
                st.session_state['pmo_active_p6_page']=names[0]
            page=render_components('pmo_active_p6_page',names,int(step[5:7]))
        elif step.startswith('Paso 07'):
            render_component_heading()
            names=list(P7_NAV)
            if st.session_state.get('pmo_active_p7_page') not in names:
                st.session_state['pmo_active_p7_page']=names[0]
            page=render_components('pmo_active_p7_page',names,int(step[5:7]))
        elif step.startswith('Paso 08'):
            render_component_heading()
            names=list(P8_NAV)
            if st.session_state.get('pmo_active_p8_page') not in names:
                st.session_state['pmo_active_p8_page']=names[0]
            page=render_components('pmo_active_p8_page',names,int(step[5:7]))
        elif step.startswith('Paso 09'):
            render_component_heading()
            names=list(P9_NAV)
            if st.session_state.get('pmo_active_p9_page') not in names:
                st.session_state['pmo_active_p9_page']=names[0]
            page=render_components('pmo_active_p9_page',names,int(step[5:7]))
        elif step.startswith('Paso 10'):
            render_component_heading()
            names=list(P10_NAV)
            if st.session_state.get('pmo_active_p10_page') not in names:
                st.session_state['pmo_active_p10_page']=names[0]
            page=render_components('pmo_active_p10_page',names,int(step[5:7]))
        else:
            return 'Ruta desconocida', ''
        n_paso=int(step[5:7]);progress=n_paso*10
        render_sidebar_footers(n_paso, 10)
        with st.expander('Ayuda metodológica'):
            if step.startswith('Paso 01'):
                st.caption('Cinco actividades PMI: identificar clientes, establecer contacto, educar sobre el valor, medir eficacia y mejorar.')
            elif step.startswith('Paso 02'):
                st.caption('El Paso 2 recoge la voz del cliente, identifica necesidades y prioriza resultados. El algoritmo es una adaptación CENS y no PMOGA certificado.')
            elif step.startswith('Paso 03'):
                st.caption('El Paso 3 traduce necesidades del Paso 2 en beneficios, lienzos y soluciones validadas. Sus 25 preguntas PMI están distribuidas en las tres pantallas.')
            elif step.startswith('Paso 04'):
                st.caption('El Paso 4 documenta los servicios, sus indicadores, recursos, ANS y evaluación de 35 criterios. La transferencia al Paso 5 exige preparación técnica completa.')
            elif step.startswith('Paso 05'):
                st.caption('El Paso 5 prepara la incorporación de servicios diseñados en el Paso 4; valida planes, pilotos, formación, adopción y la transferencia a operación.')
            elif step.startswith('Paso 06'):
                st.caption('El Paso 6 registra solicitudes y aplica los ANS en horas hábiles o calendario, según el calendario confirmado y congelado de cada ticket.')
            elif step.startswith('Paso 07'):
                st.caption('El Paso 7 monitorea tickets del Paso 6, genera indicadores y documenta hallazgos independientes. No altera el registro de operación.')
            elif step.startswith('Paso 08'):
                st.caption('El Paso 8 evalúa la madurez de 26 servicios de referencia del modelo PMO-GA, registra brechas y acciones de mejora. La madurez se valora con evidencias; no se deriva de tickets.')
            elif step.startswith('Paso 09'):
                st.caption('El Paso 9 compara los beneficios comprometidos en el Paso 3 con resultados medidos y validados. Los tickets y ANS aportan contexto, pero no demuestran por sí solos el valor entregado.')
            else:
                st.caption('El Paso 10 contrasta el valor verificado en el Paso 9 con el reconocimiento de los clientes, mide NPS de forma independiente, documenta historias, evalúa 30 criterios PMI y archiva el cierre del ciclo.')
    return step,page


def topbar(page):
    st.markdown(f'<div class="pmo-topbar"><span>PMO CENS　›　Flywheel　›　<b>{e(page)}</b></span><span class="pmo-topmark">PMO</span></div>',unsafe_allow_html=True)


def head(category,title,subtitle):
    st.markdown(f'<div class="pmo-eyebrow">PASO 01 · {e(category)}</div><div class="pmo-title">{e(title)}</div><div class="pmo-subtitle">{e(subtitle)}</div>',unsafe_allow_html=True)


def kpi(name,value,foot,icon='◈',accent=''):
    """KPI compartido con el diseño corporativo de Clientes internos."""
    from .panel_superior import render_kpi_card_panel
    theme=accent if accent in ('orange','blue','purple','teal') else 'orange'
    st.markdown(render_kpi_card_panel(label=name,value=value,subtext=foot,
                                      icon_name=icon,theme=theme),unsafe_allow_html=True)


def pair(label,value):
    st.markdown(f'<div class="pmo-pair"><span>{e(label)}</span><b>{e(value or "Sin registrar")}</b></div>',unsafe_allow_html=True)


def client_selector(rows,label='Cliente'):
    if not rows:return None
    lookup={r['id']:f"{r['codigo']} · {r['nombre']}" for r in rows}
    return st.selectbox(label,list(lookup),format_func=lambda v: lookup[v])


def client_dialog():
    @st.dialog('Registrar cliente',width='large')
    def inner():
        client_form()
    inner()


def client_edit_dialog(row):
    @st.dialog('Editar cliente',width='large')
    def inner():
        client_form(row)
    inner()


def clients_page():
    hcol,bcol=st.columns([4,1],vertical_alignment='bottom')
    with hcol:head('GESTIÓN DE CLIENTES','Clientes internos','Directorio único de interesados de la PMO, compartible con los siguientes pasos del Flywheel.')
    with bcol:
        if st.button('＋ Nuevo cliente',type='primary',use_container_width=True):client_dialog()
    persons=list_clients()
    c=counts()
    active=[r for r in persons if r['activo']]
    contacted=sum(r['relacionamiento']!='Sin contacto' for r in active)
    a,b,c3,d=st.columns(4,gap='medium')
    with a:kpi('Clientes identificados',str(c['registrados']),'Directorio registrado','♙')
    with b:kpi('Dependencias registradas',str(c['dependencias']),'Dependencias con clientes activos','⌁','blue')
    with c3:kpi('Embajadores',str(sum(r['embajador'] for r in active)),'Marcados en el directorio','☆','orange')
    with d:kpi('Clientes contactados',f'{contacted/len(active):.0%}' if active else 'Sin datos','De los clientes activos','◴','purple')
    left,right=st.columns([1.67,1],gap='medium')
    with left:
        with st.container(border=True):
            st.markdown('<div class="pmo-card-header">Directorio de clientes</div><div class="pmo-card-caption">Perfiles, segmentos y nivel de relacionamiento</div>',unsafe_allow_html=True)
            c1,c2=st.columns([1.35,1])
            with c1:q=st.text_input('Buscar cliente',placeholder='Nombre, código o cargo...',label_visibility='collapsed',key='search_clients')
            with c2:dep=st.selectbox('Dependencia',['Todas',*dependencies()],label_visibility='collapsed',key='department_filter')
            rows=list_clients(q,'' if dep=='Todas' else dep)
            st.caption(f'{len(rows)} registro(s)')
            if rows:
                options=[{'Cliente':r['nombre'],'Código':r['codigo'],'Dependencia':r['dependencia'],'Rol':r['cargo'],'Influencia':r['influencia'],'Estado':('Activo' if r['activo'] else 'Inactivo')} for r in rows]
                state=st.dataframe(options,hide_index=True,use_container_width=True,height=min(450,65+len(rows)*39),
                                   on_select='rerun',selection_mode='single-row',key='client_directory_grid')
                selected=state.selection.rows
                selected_idx=selected[0] if selected and selected[0]<len(rows) else 0
                st.session_state['current_client_id']=rows[selected_idx]['id']
                st.download_button('↓ Exportar directorio filtrado',_csv_bytes(rows),'clientes_pmo_cens.csv',mime='text/csv')
            else:
                st.info('No existen clientes con los filtros seleccionados.')
                st.session_state.pop('current_client_id',None)
    with right:
        with st.container(border=True):
            st.markdown('<div class="pmo-card-header">Ficha del cliente</div><div class="pmo-card-caption">Vista unificada de relacionamiento</div>',unsafe_allow_html=True)
            client=get_client(st.session_state['current_client_id']) if st.session_state.get('current_client_id') else None
            if not client:st.info('Selecciona un cliente en el directorio para consultar su ficha.')
            else:
                initials=''.join(x[:1] for x in client['nombre'].split()[:2]).upper()
                st.markdown(f'<div class="pmo-client-hero"><div class="pmo-initial">{e(initials)}</div><div class="pmo-person-title">{e(client["nombre"])}</div><div class="pmo-minor">{e(client["cargo"])} · {e(client["dependencia"])}</div><span class="pmo-pill">{e("Embajador" if client["embajador"] else client["relacionamiento"])}</span></div>',unsafe_allow_html=True)
                pair('Código corporativo',client['codigo']);pair('Rol',client['segmento']);pair('Influencia',client['influencia'])
                pair('Conocimiento PMO',client['conocimiento'] if client['conocimiento'] is not None else 'Sin evaluar');pair('Canal preferido',client['canal'])
                pair('Correo',client['correo']);pair('Estado','Activo' if client['activo'] else 'Inactivo')
                st.markdown('**Necesidad preliminar**')
                st.markdown(f'<div class="pmo-soft">{e(client["necesidades_preliminares"] or "Sin antecedentes registrados")}</div>',unsafe_allow_html=True)
                history=aw.client_history(client['id'])
                st.caption(f"Historial: {history['events']} eventos · {history['tickets']} consultas · {history['surveys']} encuestas")
                if st.button('Editar ficha',key='edit_client',use_container_width=True):client_edit_dialog(client)
                with st.expander('Historial de cambios'):
                    st.dataframe(audit_history(client['id']),hide_index=True,use_container_width=True)
                def _go_step2():
                    st.session_state['pmo_step2_client']=client['id']
                    st.session_state['pmo_active_step']='Paso 02 · Evaluación de necesidades'
                    st.session_state['pmo_active_p2_page']='Clientes y expectativas'
                    st.session_state['p2v03917_clients_view']='Directorio y levantamientos'
                st.button('Iniciar evaluación de necesidades →',key='goto_p2',on_click=_go_step2,use_container_width=True)
                st.caption('Este vínculo conserva el identificador del cliente; no crea un segundo directorio.')


def library_page():
    a,b=st.columns([4,1],vertical_alignment='bottom')
    with a:head('CONOCIMIENTO Y VALOR','Portal y biblioteca de recursos','Un espacio para divulgar contenidos y explicar cómo la PMO puede apoyar a sus clientes.')
    with b:
        if st.button('＋ Nuevo recurso',type='primary',use_container_width=True):st.session_state['show_resource_form']=not st.session_state.get('show_resource_form',False)
    st.markdown('<section class="pmo-hero"><small>BIBLIOTECA DE VALOR · PMO CENS</small><h2>Impulsamos proyectos con conocimiento y colaboración</h2><p>Recursos, herramientas y servicios para transformar desafíos organizacionales en resultados.</p></section>',unsafe_allow_html=True)
    if st.session_state.get('show_resource_form'):
        with st.form('new_resource'):
            st.subheader('Registrar recurso o ficha de servicio')
            t,c=st.columns(2)
            title=t.text_input('Título *');kind=c.selectbox('Tipo',['Material','Servicio','Historia'])
            category=t.text_input('Categoría *');status=c.selectbox('Estado',['Borrador','Publicado','En diseño','Piloto','Disponible','Suspendido'])
            description=st.text_area('Descripción');url=st.text_input('URL del recurso (https://)')
            actor=st.text_input('Responsable del registro *')
            sent=st.form_submit_button('Guardar recurso',type='primary')
        if sent:
            try:
                aw.create_resource(title,category,description,url,kind,status,actor)
                st.success('Recurso guardado.');st.session_state['show_resource_form']=False;st.rerun()
            except ValidationError as err:st.error(str(err))
    st.markdown('### Catálogo de servicios PMO CENS')
    services=aw.resources(kind='Servicio')
    if not services:
        st.info('El catálogo está vacío. Puedes incorporar servicios cuando CENS haya definido su descripción y estado.')
        with st.expander('Ver servicios de referencia para configurar'):
            st.markdown('Cultura de proyectos · Formación y desarrollo · Tutoría y coaching · Metodologías y conocimiento · Análisis de datos e informes · Gestión de incidentes · Gestión de sistemas y herramientas')
    else:
        for idx in range(0,len(services),3):
            cols=st.columns(3)
            for col,r in zip(cols,services[idx:idx+3]):
                with col:
                    st.markdown(f'<div class="pmo-resource"><strong>{e(r["titulo"])}</strong><p>{e(r["descripcion"])}</p><span class="pmo-pill">{e(r["estado"])}</span></div>',unsafe_allow_html=True)
                    if r['url']:st.link_button('Ver ficha',r['url'])
    st.markdown('### Biblioteca de aprendizaje')
    query=st.text_input('Buscar material',placeholder='Título, categoría o descripción...')
    materials=aw.resources(search=query)
    materials=[r for r in materials if r['tipo']!='Servicio']
    if not materials:st.info('Aún no hay materiales o historias publicados en el repositorio local.')
    else:
        for i in range(0,len(materials),3):
            cs=st.columns(3)
            for col,r in zip(cs,materials[i:i+3]):
                with col:
                    st.markdown(f'<div class="pmo-resource"><strong>{e(r["titulo"])}</strong><p>{e(r["descripcion"])}</p><span class="pmo-pill">{e(r["categoria"])} · {e(r["estado"])}</span></div>',unsafe_allow_html=True)
                    if r['url']:st.link_button('Abrir recurso',r['url'])
    st.caption('El repositorio admite vínculos registrados por la PMO. No publica ni autentica accesos de SharePoint.')


def _create_event_form():
    with st.form('create_event'):
        title=st.text_input('Nombre de la actividad *')
        c1,c2=st.columns(2)
        kind=c1.selectbox('Tipo',['Jornada de sensibilización','Taller','Webinar','Reunión','Presentación de servicios','Otra'])
        start=c2.date_input('Fecha',value=date.today(), format='YYYY/MM/DD')
        audience=c1.text_input('Público objetivo');mode=c2.selectbox('Modalidad',['Presencial','Virtual','Mixta'])
        status=c1.selectbox('Estado',['Borrador','Programado','Realizado','Cancelado'])
        owner=staff_picker('Responsable *')
        sent=st.form_submit_button('Guardar actividad',type='primary')
    if sent:
        try:
            aw.create_event(title,kind,start,audience,mode,owner,status)
            st.success('Actividad guardada.');st.rerun()
        except ValidationError as err:st.error(str(err))


def events_page():
    """V0.25: conserva el enrutador original y delega solo Eventos y campañas."""
    from .events_ui import render_events
    render_events()


def tickets_page():
    """V0.29: delegar vista; conservar navegación y otras funciones del Paso 01."""
    from .interactions_ui import render_interactions
    render_interactions()


def _survey_form():
    people=list_clients(status='Activos')
    if not people:
        st.info('No hay clientes activos para encuestar.');return
    events=aw.events()
    with st.form('new_survey'):
        label={p['id']:f"{p['codigo']} · {p['nombre']}" for p in people}
        client=st.selectbox('Cliente',list(label),format_func=lambda x:label[x])
        evlabels={'':'Sin evento asociado',**{v['id']:v['titulo'] for v in events}}
        eid=st.selectbox('Actividad relacionada',list(evlabels),format_func=lambda x:evlabels[x])
        phase=st.selectbox('Momento de encuesta',['Antes','Después'])
        questions=['Familiaridad con la PMO','Comprensión de su propósito','Conocimiento de los servicios','Utilidad percibida','Interés en actividades futuras']
        answers=[]
        for idx,q in enumerate(questions):answers.append(st.selectbox(q,['Sin responder',1,2,3,4,5],key=f'survey_{idx}'))
        actor=st.text_input('Registrado por *')
        sent=st.form_submit_button('Guardar encuesta',type='primary')
    if sent:
        try:aw.record_survey(client,eid or None,phase,answers,actor);st.success('Encuesta registrada.');st.rerun()
        except ValidationError as err:st.error(str(err))


def dashboard_page():
    a,b=st.columns([4,1],vertical_alignment='bottom')
    with a:head('MEDICIÓN','Tablero de concienciación','Distinga el alcance verificable de la participación y el conocimiento efectivo.')
    with b:
        if st.button('＋ Registrar encuesta',type='primary',use_container_width=True):st.session_state['show_survey']=not st.session_state.get('show_survey',False)
    if st.session_state.get('show_survey'):
        with st.container(border=True):_survey_form()
    summary=aw.summary()
    for col,(name,value,sub,ico,accent) in zip(st.columns(4),[
        ('Cobertura de clientes',f'{summary["coverage"]:.0f}%' if summary['coverage'] is not None else 'Sin datos',f'{summary["reached"]} de {summary["active"]} activos','◎',''),
        ('Participación única',str(summary['reached']),'Personas con asistencia','♙','blue'),
        ('Familiaridad PMO',f'{summary["familiarity"]:.1f}/5' if summary['familiarity'] is not None else 'Sin datos',f'Muestra: {summary["sample"]} respuestas posteriores','◇','orange'),
        ('Consultas atendidas',f'{summary["ticket_rate"]:.0f}%' if summary['ticket_rate'] is not None else 'Sin datos',f'{summary["answered"]} de {summary["tickets"]} casos','☏','purple')]):
        with col:kpi(name,value,sub,ico,accent)
    dep=aw.department_coverage()
    surveys=aw.surveys()
    left,right=st.columns([1.6,1],gap='medium')
    with left:
        with st.container(border=True):
            st.markdown('<div class="pmo-card-header">Cobertura por dependencia</div><div class="pmo-card-caption">Personas únicas con asistencia registrada / clientes activos</div>',unsafe_allow_html=True)
            if not dep:st.info('Sin clientes activos registrados.')
            else:
                st.bar_chart([{'Dependencia':x['dependencia'],'Cobertura (%)':100*x['alcanzados']/x['objetivo']} for x in dep],x='Dependencia',y='Cobertura (%)',horizontal=True)
                st.dataframe([{'Dependencia':x['dependencia'],'Público':x['objetivo'],'Alcanzados':x['alcanzados'],'Cobertura (%)':round(100*x['alcanzados']/x['objetivo'])} for x in dep],hide_index=True,use_container_width=True)
    with right:
        with st.container(border=True):
            st.markdown('<div class="pmo-card-header">Cobertura del público objetivo</div>',unsafe_allow_html=True)
            if summary['coverage'] is None:st.info('No hay denominador: registra clientes activos.')
            else:
                pct=round(summary['coverage'])
                st.markdown(f'<div style="height:155px;width:155px;border-radius:50%;background:conic-gradient(#0C989B {pct}%,#E5EFF3 {pct}%);margin:10px auto;display:grid;place-items:center"><div style="width:113px;height:113px;background:#fff;border-radius:50%;display:grid;place-items:center;font-size:27px;font-weight:800;color:#10374B">{pct}%</div></div>',unsafe_allow_html=True)
                st.caption(f"{summary['reached']} personas alcanzadas de {summary['active']} clientes activos")
        with st.container(border=True):
            st.markdown('<div class="pmo-card-header">Conocimiento antes y después</div>',unsafe_allow_html=True)
            before=[x['familiaridad'] for x in surveys if x['fase']=='Antes']
            after=[x['familiaridad'] for x in surveys if x['fase']=='Después']
            if not before or not after:st.info('Se requieren mediciones antes y después. No se calculan variaciones sin pares comparables.')
            else:
                st.caption(f'Antes: {len(before)} respuestas; después: {len(after)} respuestas')
                pairs={}
                for x in surveys:
                    key=(x['cliente_id'],x['evento_id'])
                    pairs.setdefault(key,{})[x['fase']]=x['familiaridad']
                paired=[(p['Antes'],p['Después']) for p in pairs.values() if 'Antes' in p and 'Después' in p]
                if paired:
                    avg0=sum(a for a,b in paired)/len(paired);avg1=sum(b for a,b in paired)/len(paired)
                    st.bar_chart([{'Momento':'Antes','Familiaridad':avg0},{'Momento':'Después','Familiaridad':avg1}],x='Momento',y='Familiaridad',horizontal=True)
                    st.caption(f'Muestra comparable: {len(paired)} clientes/evento. Variación: {avg1-avg0:+.1f} puntos.')
                else:st.info('Hay encuestas, pero aún no existen pares cliente/evento comparables.')
    st.markdown('<div class="pmo-hint">Comunicarse con una persona no demuestra que comprendió el valor de la PMO. Este tablero separa cobertura, participación, familiaridad y atención.</div>',unsafe_allow_html=True)


def assessment_page():
    """Autoevaluación V0.31: 25 criterios adaptados, evidencia separada y guardado atómico."""
    from .form_system import section_header, form_note
    import json
    a,b=st.columns([4,1],vertical_alignment='bottom')
    with a:head('AUTOEVALUACIÓN','Autoevaluación metodológica del Paso 01',
        'Cinco dimensiones, 25 criterios adaptados, evidencia por respuesta e historial de evaluaciones.')
    with b:
        if st.button('＋ Nueva evaluación',type='primary',use_container_width=True,key='v31_ass_new'):
            st.session_state['new_assessment']=not st.session_state.get('new_assessment',False)
    if st.session_state.get('new_assessment'):
        section_header('01','Nueva autoevaluación','Los registros comienzan en borrador y sin valoraciones precargadas.')
        with st.form('create_assessment'):
            a,b=st.columns(2)
            per=a.text_input('Periodo de evaluación *',value=str(date.today().year))
            author=b.text_input('Evaluador *')
            sent=st.form_submit_button('Guardar borrador',type='primary')
        if sent:
            try:
                key=ass.create(per,author)
                st.session_state['assessment_id']=key
                st.session_state['v31_ass_selected']=key
                st.session_state['new_assessment']=False
                st.success('Autoevaluación en borrador creada.')
                st.rerun()
            except ValidationError as err:st.error(str(err))
    versions=ass.list_assessments()
    if not versions:
        for col,(n,v,foot,ico,acc) in zip(st.columns(4),[
            ('Resultado total','No evaluado','Máximo 125 puntos','✓',''),
            ('Clasificación','No evaluado','Sin evaluación finalizada','◎','blue'),
            ('Dimensiones','5','Cinco criterios por dimensión','▤','orange'),
            ('Preguntas valoradas','0/25','Sin puntuaciones ficticias','◴','purple')]):
            with col:kpi(n,v,foot,ico,acc)
        st.info('Crea una evaluación para comenzar. El instrumento es una adaptación institucional CENS, no la transcripción literal del PMI.')
        return
    lookup={r['id']:f"{r['periodo']} · {r['evaluador']} · {r['estado']} · {r['creado_en']}" for r in versions}
    desired=st.session_state.get('assessment_id')
    selected=st.selectbox('Evaluación / corte',list(lookup),format_func=lambda x:lookup[x],
             index=list(lookup).index(desired) if desired in lookup else 0,key='v31_ass_selected')
    current=next(r for r in versions if r['id']==selected)
    ans=ass.responses(selected)
    finished=current['estado']=='Finalizada'
    ready=len(ans)==25
    score=current['puntaje'] if finished else (sum(x['valor'] for x in ans.values()) if ready else None)
    for col,(n,v,foot,ico,acc) in zip(st.columns(4),[
        ('Puntaje total',(str(score)+'/125') if score is not None else 'Pendiente','Solo 25 preguntas completas','✓',''),
        ('Clasificación',ass.classification(score) or 'Pendiente','Resultado adaptado CENS','◎','blue'),
        ('Dimensiones','5','Instrumento por dimensiones','▤','orange'),
        ('Valoraciones',f'{len(ans)}/25','Respuestas guardadas','◴','purple')]):
        with col:kpi(n,v,foot,ico,acc)
    form_note('Autoevaluación metodológica: no reemplaza las encuestas de conocimiento de los clientes. '
              'Utilice evidencia comprobable; los criterios son paráfrasis funcionales para CENS.')
    left,right=st.columns([1,2],gap='medium')
    with left:
        section_header('01','Dimensiones','Seleccione un grupo para registrar sus cinco valoraciones.')
        qdim=st.radio('Dimensión',list(range(5)),format_func=lambda i:
            f'{i+1:02d} · {ass.DIMENSIONS[i][0]} · {sum(ans.get(i*5+j,{}).get("valor",0) for j in range(1,6))}/25',
            key='v31_ass_dimension')
        st.progress(len(ans)/25,text=f'{len(ans)} de 25 criterios guardados')
        if not finished:
            if st.button('Finalizar autoevaluación',use_container_width=True,disabled=not ready,key='v31_ass_finish'):
                try:
                    score,cat=ass.finalize(selected,current['evaluador'])
                    st.success(f'Finalizada · {score}/125 · {cat}')
                    st.rerun()
                except ValidationError as err:st.error(str(err))
        else:st.success('Evaluación finalizada y protegida contra modificaciones.')
    with right:
        section_header('01',f'Dimensión {qdim+1} · {ass.DIMENSIONS[qdim][0]}',
                       'Valore 1 (ineficaz) a 5 (excelente); las referencias documentales son opcionales.')
        with st.form(f'v31_ass_dim_{selected}_{qdim}'):
            values=[]
            for j,text in enumerate(ass.DIMENSIONS[qdim][1],1):
                n=qdim*5+j
                previous=ans.get(n,{})
                st.markdown(f'**{n:02d}. {text}**')
                c1,c2=st.columns([.9,1.1])
                rating=c1.selectbox('Valoración', ['Sin responder',1,2,3,4,5],
                     index=previous['valor'] if 'valor' in previous else 0,
                     key=f'v31_ass_val_{selected}_{n}',disabled=finished)
                evidence=c2.text_input('Referencia de evidencia',value=previous.get('evidencia',''),
                     placeholder='Acta, recurso, evento o expediente',key=f'v31_ass_evd_{selected}_{n}',disabled=finished)
                note=st.text_input('Observaciones',value=previous.get('observacion',''),
                     key=f'v31_ass_obs_{selected}_{n}',disabled=finished)
                values.append((n,None if rating=='Sin responder' else rating,note,evidence))
                if j<5:st.divider()
            submitted=st.form_submit_button('Guardar las cinco preguntas',type='primary',disabled=finished)
        if submitted:
            try:
                ass.save_dimension(selected,qdim,values,current['evaluador'])
                st.success('Dimensión guardada con transacción única.')
                st.rerun()
            except ValidationError as err:st.error(str(err))
    section_header('01','Resultados por dimensión','Las dimensiones incompletas aparecen sin puntuación.')
    scores=ass.dimension_summary(selected)
    st.dataframe(scores,use_container_width=True,hide_index=True)
    if any(x['Puntaje'] is not None for x in scores):
        st.bar_chart([{'Dimensión':x['Dimensión'],'Puntaje':x['Puntaje'] or 0} for x in scores
                 if x['Puntaje'] is not None],x='Dimensión',y='Puntaje',horizontal=True)
    st.download_button('↓ Exportar autoevaluación y evidencias (JSON)',
        data=json.dumps(ass.assessment_export(selected),ensure_ascii=False,indent=2).encode('utf-8'),
        file_name=f'PMO_CENS_P01_Autoevaluacion_{selected[:8]}.json',mime='application/json',
        key='v31_ass_export')
    history=[{'Periodo':v['periodo'],'Finalizada el':v['finalizada_en'],
              'Evaluador':v['evaluador'],'Puntaje':v['puntaje'],
              'Clasificación':v['clasificacion']} for v in versions if v['estado']=='Finalizada']
    st.markdown('**Historial y comparación de cortes**')
    if history:
        st.dataframe(history,hide_index=True,use_container_width=True)
        if len(history)>=2:
            st.bar_chart(sorted(history,key=lambda r:(r['Periodo'],r['Finalizada el'] or '')),
                x='Periodo',y='Puntaje')
            st.caption('Compare únicamente cortes con el mismo instrumento y una población evaluada consistente.')
    else:st.info('Aún no existen cortes finalizados para comparar.')


def excel_import_page():
    head('CARGA DE INFORMACIÓN', 'Importar datos desde Excel',
         'Seleccione una plantilla, revise sus registros y confirme una única carga segura.')
    template = Path(__file__).resolve().parent.parent / 'plantillas' / 'PLANTILLA_CARGA_PASO1_PMO_CENS_V0.3.xlsx'
    with st.container(border=True):
        a, b = st.columns([1.7, 1], vertical_alignment='center')
        with a:
            st.markdown('**Carga única del Paso 1**')
            st.caption('Clientes, eventos, campañas, biblioteca, consultas, asistencias y encuestas. '
                       'Solo se importan las hojas diligenciadas.')
        with b:
            if template.exists():
                st.download_button('↓ Descargar plantilla Excel', template.read_bytes(),
                                   'PLANTILLA_CARGA_PASO1_PMO_CENS_V0.3.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   use_container_width=True)
            else:
                st.error('La plantilla Excel no está incluida en esta instalación.')
        st.info('Los clientes existentes no se modifican. La asistencia sí puede actualizarse con auditoría. '
                'Si hay errores, no se guarda ningún registro.')
        actor = st.text_input('Responsable que realiza la carga *', key='pmo_excel_actor')
        attachment = st.file_uploader('Seleccionar archivo .xlsx', type=['xlsx'],
                                      accept_multiple_files=False, key='pmo_excel_upload')
    if attachment is None:
        st.caption('La plantilla incluye instrucciones y ejemplos en hojas que el importador no carga.')
        return
    if not actor.strip():
        st.warning('Indique el responsable para obtener la vista previa.')
        return
    raw = attachment.getvalue()
    try:
        preview = import_xlsx(raw, actor, confirm=False)
    except ValidationError as err:
        st.error(str(err))
        return
    from collections import Counter
    totals = Counter(r['Acción'] for r in preview)
    for col, (label, key) in zip(st.columns(4),
            [('Nuevos', 'Nuevo'), ('Duplicados', 'Duplicado'),
             ('Asistencias actualizadas', 'Actualizado'), ('Errores', 'Error')]):
        with col:
            kpi(label, str(totals[key]), f'{len(preview)} filas revisadas',
                '✓' if key != 'Error' else '!', 'orange' if key == 'Error' else '')
    st.markdown('### Vista previa y diagnóstico')
    st.dataframe(preview, hide_index=True, use_container_width=True,
                 height=min(480, 80 + len(preview)*36))
    st.caption('Los registros nuevos se crean; los duplicados se omiten. '
               'El sistema no acepta cifras de indicadores ni valoraciones metodológicas desde Excel.')
    if totals['Error']:
        st.error('Corrija las filas marcadas como Error y vuelva a cargar el libro. Ningún dato ha sido guardado.')
    elif totals['Nuevo'] + totals['Actualizado'] == 0:
        st.info('No hay nuevos registros para importar.')
    else:
        if st.button(f'Confirmar e importar {totals["Nuevo"]} nuevos + {totals["Actualizado"]} actualizaciones',
                     type='primary', key='pmo_excel_confirm'):
            try:
                result = import_xlsx(raw, actor, confirm=True)
                if any(x['Acción'] == 'Error' for x in result):
                    st.error('La información cambió durante la operación. No se importó nada. Revise nuevamente.')
                    st.dataframe(result, hide_index=True, use_container_width=True)
                else:
                    st.success('Importación completada. Los datos están disponibles en sus respectivas secciones.')
                    st.session_state['pmo_excel_active'] = False
                    st.rerun()
            except (ValidationError, ValueError) as err:
                st.error(f'La carga no pudo completarse: {err}')


from .client_directory_ui import render_client_directory
from .library_ui import render_portal
from .dashboard_ui import render_dashboard as render_awareness_dashboard

PAGES={
 'Clientes internos':render_client_directory,
 'Portal y biblioteca':render_portal,
 'Eventos y campañas':events_page,
 'Consultas e interacciones':tickets_page,
 'Tablero de concienciación':render_awareness_dashboard,
 'Autoevaluación PMI':assessment_page,
 'Plan de mejora y cierre':lambda:__import__('pmo.step1_closure_ui',fromlist=['render_closure']).render_closure(),
}
