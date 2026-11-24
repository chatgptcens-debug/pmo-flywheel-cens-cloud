"""Navigation shortcuts are session-only and never persist business records."""
from .alpha_navigation import HOME, STEPS, go_to


def remember(state, step):
    if step not in STEPS: return
    state['beta_recent']=[step]+[s for s in state.get('beta_recent',[]) if s in STEPS and s!=step][:5]


def toggle(state, step):
    if step not in STEPS: raise ValueError('Paso inválido')
    old=[s for s in state.get('beta_favorites',[]) if s in STEPS]
    state['beta_favorites']=[s for s in old if s!=step] if step in old else old+[step]


def mark(step):
    import streamlit as st
    toggle(st.session_state,step)


def render_favorite(st,step):
    remember(st.session_state,step)
    if step in STEPS:
        favorite=step in st.session_state.get('beta_favorites',[])
        st.button('Quitar de favoritos' if favorite else 'Agregar paso a favoritos',icon=':material/star:' if favorite else ':material/star_border:',key='beta_favorite_step',on_click=mark,args=(step,))


def render_shortcuts(st):
    with st.expander('Favoritos y pasos recientes · sesión'):
        for label,key in [('Favoritos','beta_favorites'),('Recientes','beta_recent')]:
            st.markdown('**'+label+'**')
            steps=[s for s in st.session_state.get(key,[]) if s in STEPS]
            if not steps: st.caption('Aún no hay accesos en esta sesión.')
            for i,s in enumerate(steps):
                st.button(s,key=f'{key}_{i}',on_click=go_to,args=(s,),use_container_width=True)
        st.caption('No guarda favoritos entre sesiones ni selecciona un registro específico. Se conservan las claves de navegación originales.')
