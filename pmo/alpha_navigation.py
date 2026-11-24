"""Rutas V1.0.0; sin dependencias de UI ni persistencia."""
VERSION = 'V1.0.0 Cloud Edition'
HOME = 'Inicio'
STAGES = ('Exploración', 'Diseño', 'Despliegue', 'Mejora', 'Realización')
STEP_NAMES = ('Generación de conciencia', 'Evaluación de necesidades', 'Propuesta de valor',
              'Desarrollo de servicios', 'Incorporación de servicios', 'Operación de servicios',
              'Monitoreo de servicios', 'Mejora de servicios', 'Entrega de valor', 'Reconocimiento del valor')
STEPS = tuple(f'Paso {i:02d} · {name}' for i, name in enumerate(STEP_NAMES, 1))
ROUTES = {HOME: 0, **{step: i for i, step in enumerate(STEPS, 1)}}


def step_number(route):
    """No convierte rutas inválidas en Paso 10."""
    return ROUTES.get(route)


def stage_of(number):
    if not 1 <= number <= 10:
        raise ValueError('Paso fuera del recorrido')
    return STAGES[(number - 1) // 2]


def go_to(route):
    """Callback nativo: se ejecuta antes de crear los widgets en el rerun."""
    import streamlit as st
    if route not in ROUTES:
        raise ValueError('Ruta desconocida')
    st.session_state['pmo_active_step'] = None if route == HOME else route
