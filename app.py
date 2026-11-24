"""PMO FLYWHEEL CENS · Pasos 1 al 10 integrados · V1.0.0 · madurez y mejora continua y cortes trazables, equipo y planificación de lienzo de valor / Panel superior ejecutivo.
Datos ficticios por sesión, temporales. No apto para producción ni datos institucionales.
"""
import os
import streamlit as st

from pmo.cloud_runtime import prepare, reset
st.set_page_config(page_title='PMO FLYWHEEL CENS · V1.0.0 Cloud Edition', page_icon='📘', layout='wide', initial_sidebar_state='expanded')
prepare(st.session_state)
MODO_DEMO = MODO_TALLER_REAL = MODO_FICHAS_PASO04 = False
from pmo.alpha_navigation import HOME, step_number
from pmo.storage import initialize
from pmo.ui import apply_theme,sidebar,topbar,excel_import_page,PAGES
from pmo.step2_ui import page as step2_page
from pmo.step3_ui import page as step3_page, apply_step3_theme
from pmo.step4_ui import page as step4_page, apply_step4_theme
from pmo.step5_ui import page as step5_page, apply_step5_theme
from pmo.step6_ui import page as step6_page, apply_step6_theme
from pmo.step7_ui import page as step7_page, apply_step7_theme
from pmo.step8_ui import page as step8_page, apply_step8_theme
from pmo.step9_ui import page as step9_page, apply_step9_theme
from pmo.step10_ui import page as step10_page, apply_step10_theme
from pmo.pmi_flywheel_assessment import initialize as initialize_flywheel_assessment
from pmo.pmi_flywheel_assessment_ui import page as uniform_pmi_assessment_page


initialize()
# Migraciones V0.39.1: respaldos + auditoría; los snapshots de corridas no se tocan.
from pmo.v0391_clients import harmonize_roles
from pmo.v0391_diagnostics import harmonize_diagnostic_names
harmonize_roles()
harmonize_diagnostic_names()
from pmo.assessment import initialize as initialize_assessment
initialize_assessment()
from pmo.step1_closure import initialize as initialize_closure
initialize_closure()
from pmo.events_media import initialize as initialize_eventos
initialize_eventos()
from pmo.library_portal import initialize as initialize_portal
initialize_portal()
from pmo.interactions import initialize as initialize_interactions
initialize_interactions()
from pmo.step3 import initialize as initialize_step3
initialize_step3()
from pmo.step4 import initialize as initialize_step4
initialize_step4()
from pmo.step5 import initialize as initialize_step5
initialize_step5()
from pmo.step6 import initialize as initialize_step6
initialize_step6()
from pmo.step7 import initialize as initialize_step7
initialize_step7()
from pmo.step8 import initialize as initialize_step8
initialize_step8()
from pmo.step8_documented import initialize as initialize_step8_documented
initialize_step8_documented()
from pmo.step8_improvement import initialize as initialize_step8_improvement
initialize_step8_improvement()
from pmo.step8_profile import initialize as initialize_step8_profile
initialize_step8_profile()
from pmo.step9 import initialize as initialize_step9
initialize_step9()
from pmo.step10 import initialize as initialize_step10
initialize_step10()
initialize_flywheel_assessment()
# V0.39.18 · códigos públicos estables, sin reescribir claves de origen.
from pmo.public_codes import initialize as initialize_public_codes
initialize_public_codes()
from pmo.step2_maturity_questions import initialize as init_annual_question_results
init_annual_question_results()
apply_theme()
apply_step3_theme()
apply_step4_theme()
apply_step5_theme()
apply_step6_theme()
apply_step7_theme()
apply_step8_theme()
apply_step9_theme()
apply_step10_theme()
# V0.31: aplicar el estándar de formularios después de las capas particulares
from pmo.form_system import apply_form_standard
apply_form_standard()
# V0.39.4: acabado homogéneo de los controles de carga; solo CSS, sin sustituir el uploader nativo.
from pmo.upload_ui import apply_upload_ui
apply_upload_ui()
if MODO_FICHAS_PASO04:
    st.session_state.setdefault('pmo_active_step', 'Paso 04 · Desarrollo de servicios')
    st.session_state.setdefault('pmo_active_p4_page', 'Catálogo y fichas de servicios')
elif MODO_DEMO or MODO_TALLER_REAL:
    st.session_state.setdefault('pmo_active_step', 'Paso 03 · Propuesta de valor')
    st.session_state.setdefault('pmo_active_p3_page', 'Lienzo y conexiones de valor')
# Migrar un acceso heredado a su componente ANTES de instanciar los widgets de navegación.
if st.session_state.pop('pmo_excel_active', False):
    st.session_state['pmo_active_step'] = 'Paso 01 · Generación de conciencia'
    st.session_state['pmo_active_page'] = 'Eventos y campañas'
step,page=sidebar()
st.warning('CLOUD EDITION · LABORATORIO FICTICIO · No cargues datos personales, expedientes ni documentos institucionales. Los cambios son temporales y separados por sesión; se pierden al reiniciar o cerrar la sesión. No es un entorno operativo ni una decisión oficial de CENS.')
with st.sidebar:
    with st.expander('Laboratorio Cloud · datos temporales'):
        st.caption('Cada sesión empieza con una copia de la semilla ficticia. Descarga los informes antes de salir.')
        confirm_reset = st.checkbox('Confirmo borrar mis cambios de ensayo', key='cloud_reset_check')
        if st.button('Reiniciar laboratorio', key='cloud_reset_confirmed', disabled=not confirm_reset, help='Borra los cambios de esta sesión y vuelve a la semilla de ensayo.'):
            reset(st.session_state)
            st.rerun()
route_number = step_number(step)
p1,p2,p3,p4,p5,p6,p7,p8,p9 = (route_number == n for n in range(1,10))
topbar(('Inicio' if step == HOME else f'Paso {route_number:02d}' if route_number else 'Ruta desconocida')+' / '+page)
if MODO_DEMO:
    st.warning("🧪 **MODO DEMOSTRACIÓN — DATOS FICTICIOS.** Esta base está aislada del ciclo oficial. Las propuestas, puntuaciones, fechas y aprobaciones mostradas son simuladas; no constituyen compromisos ni decisiones de CENS.")
if MODO_FICHAS_PASO04:
    st.info('📋 **FICHAS PRELIMINARES DEL PASO 04 — NO APROBADAS.** El taller 2026 y las propuestas técnicas se utilizan como insumos iniciales. Las 26 fichas pueden editarse y guardarse; acuerdos de servicio, metas, responsables y aprobaciones quedan por validar. Esta instancia está separada del ciclo oficial.')
elif MODO_TALLER_REAL:
    st.info("📚 **TALLER REAL 2026 — Lienzos documentales.** Se cargaron 15 servicios priorizados y 11 restantes desde «Taller - Lienzo de Valor.pdf». Esta copia está separada del ciclo oficial. Las posibles acciones NO implican aprobación institucional.")
if os.environ.get('PMO_CENS_ALPHA_PREVIEW') == '1':
    st.info('V1.0.0 · ENTORNO DE ACEPTACIÓN · Los cambios se guardan en la copia aislada, no en el ciclo operativo.')
if route_number in range(1,11):
    from pmo.beta03_visual import render_context
    render_context(st,route_number,page)
    from pmo.alpha_guidance import render as render_guidance
    render_guidance(route_number)
    from pmo.beta01_workspace import render_favorite
    render_favorite(st,step)
if step == HOME:
    from pmo.alpha06_ui import render as render_home
    render_home(isolated=True)
elif ((p1 or p2 or p3 or p4 or p5 or p6 or p7 or p8 or p9 or step.startswith("Paso 10"))
    and (page == "Autoevaluación PMI" or "Evaluación metodológica PMI" in page or "Autoevaluación metodológica PMI" in page)):
    uniform_pmi_assessment_page(int(step[5:7]))
elif p1:PAGES[page]()
elif p2:step2_page(page)
elif p3:step3_page(page)
elif p4:step4_page(page)
elif p5:step5_page(page)
elif p6:step6_page(page)
elif p7:step7_page(page)
elif p8:step8_page(page)
elif p9:step9_page(page)
elif route_number == 10:step10_page(page)
else:st.error('Ruta no disponible. Selecciona Inicio o un paso del Flywheel.')
