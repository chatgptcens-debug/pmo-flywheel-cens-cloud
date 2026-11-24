"""Native navigation: no dependence on radio DOM. Session routes remain stable."""
from .alpha_navigation import HOME, STEPS, STEP_NAMES, STAGES, go_to

COLORS = ('#FF7825', '#6092FF', '#22C5B5', '#21C2E3', '#A98AFF')
ICONS = ('campaign','fact_check','handshake','design_services','rocket_launch',
         'settings','monitoring','autorenew','target','workspace_premium')
COMPONENT_ICONS = {'clientes':'groups','portal':'menu_book','biblioteca':'menu_book',
                   'eventos':'event','consultas':'forum','autoevaluación':'fact_check',
                   'plan':'assignment','resumen':'dashboard','necesidades':'assignment',
                   'priorización':'analytics','validación':'verified','informes':'summarize',
                   'madurez':'monitoring','lienzo':'dashboard_customize','catálogo':'inventory_2',
                   'operación':'settings','indicadores':'monitoring','beneficios':'target',
                   'reconocimiento':'workspace_premium','mejora':'autorenew'}

def component_icon(name):
    return next((v for k,v in COMPONENT_ICONS.items() if k in name.casefold()),'folder_open')

def choose_component(key, value):
    import streamlit as st
    st.session_state[key] = value

def render_steps():
    import streamlit as st
    active = st.session_state.get('pmo_active_step')
    if active not in STEPS:
        active = None
    with st.container(key='alpha02_steps'):
        for i, stage in enumerate(STAGES):
            color = COLORS[i]
            st.markdown(f'<div class="alpha02-stage-title" style="color:{color}">{stage.upper()}</div>', unsafe_allow_html=True)
            with st.container(key=f'alpha02_stage_{i}'):
                for j in range(i*2,i*2+2):
                    st.button(f'{j+1:02d} · {STEP_NAMES[j]}', icon=f':material/{ICONS[j]}:',
                              key=f'alpha02_nav_{j+1:02d}', type='primary' if active==STEPS[j] else 'secondary',
                              on_click=go_to,args=(STEPS[j],),use_container_width=True)
    return active

def render_components(key, names, step):
    import streamlit as st
    current = st.session_state.get(key)
    if current not in names:
        current=names[0]
        st.session_state[key]=current
    stage=(step-1)//2
    with st.container(key=f'alpha02_components_{stage}'):
        for i,name in enumerate(names):
            st.button(name, icon=f':material/{component_icon(name)}:',
                      key=f'alpha02_component_{step}_{i}',type='primary' if name==current else 'secondary',
                      on_click=choose_component,args=(key,name),use_container_width=True)
    return current
