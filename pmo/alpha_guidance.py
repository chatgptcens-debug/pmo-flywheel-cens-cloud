"""Orientación didáctica reutilizable. Contenido original, no reproduce la guía."""
GUIDANCE = {
  2: {'chapter': 15, 'purpose': 'Comprender los problemas y expectativas del cliente antes de diseñar o seleccionar servicios.',
      'sections': (
       ('Comprender', 'Distingue una necesidad (problema o ganancia) de una solución o servicio. La prioridad indica relevancia; no constituye aprobación.'),
       ('Preparar', 'Consulta el directorio, el contexto del diagnóstico y las evidencias de entrevistas. Comprueba que Dependencia y Rol estén correctamente registrados.'),
       ('Ejecutar', 'Registra expectativas y necesidades, relaciona los resultados esperados y usa el motor V5 con ponderaciones expertas justificadas que sumen 100%.'),
       ('Verificar', 'Revisa participantes, evidencias, corrida y contribuciones. Valida por separado la decisión MVS; seleccionar un servicio en el ranking no lo aprueba.'),
       ('Conectar', 'Utiliza los resultados validados como insumo para las propuestas de valor del Paso 03. Conserva el diagnóstico y su trazabilidad histórica.'))},
  3: {'chapter': 16, 'purpose': 'Transformar las necesidades identificadas en propuestas de valor comprensibles y verificables.',
      'sections': (
       ('Comprender', 'Separa problema, solución propuesta y beneficio esperado. Una conexión del lienzo explica una hipótesis de valor, no su materialización.'),
       ('Preparar', 'Consulta necesidades transferidas y versiones del lienzo; identifica el cliente destinatario y la evidencia de origen.'),
       ('Ejecutar', 'Relaciona dolores con aliviadores y ganancias con generadores. Formula una propuesta y documenta cómo se verificará su beneficio.'),
       ('Verificar', 'Revisa correspondencias, viabilidad, evidencia y validación del cliente. Usa los controles existentes para registrar acuerdos.'),
       ('Conectar', 'Transfiere únicamente las propuestas elegibles mediante el mecanismo vigente del Paso 04.'))},
  4: {'chapter': 17, 'purpose': 'Convertir la propuesta de valor en servicios diseñados, comprensibles y preparados para su incorporación.',
      'sections': (
       ('Comprender', 'Distingue el enfoque de prestación, el modelo de servicio y su estado de aprobación. Diseñar no autoriza operar.'),
       ('Preparar', 'Revisa propuesta de origen, cliente, alcance, capacidad del equipo y competencias requeridas.'),
       ('Ejecutar', 'Documenta activación, proceso, roles RACI, entregables, indicadores y acuerdos de nivel de servicio en la ficha oficial.'),
       ('Verificar', 'Contrasta requisitos y niveles evaluados, revisa las versiones ANS y utiliza los criterios de preparación existentes.'),
       ('Conectar', 'Transfiere al Paso 05 mediante los controles vigentes. La incorporación y autorización permanecen separadas.'))} ,
  5: {'chapter':18,'purpose':'Preparar a los clientes y al equipo para adoptar los servicios diseñados.', 'sections': (
      ('Comprender','La incorporación facilita la adopción; aprobar un plan no autoriza por sí solo la operación.'),
      ('Preparar','Verifica el servicio aprobado en Paso 04 y define la ruta, destinatarios, recursos y fechas.'),
      ('Ejecutar','Registra comunicación, formación, pilotos, hitos e incidencias en los formularios vigentes.'),
      ('Verificar','Contrasta los datos declarados con evidencias y aplica los criterios de transición. No confundas cobertura con usuarios únicos.'),
      ('Conectar','Transfiere únicamente servicios ya autorizados y elegibles al catálogo del Paso 06.'))},
  6: {'chapter':19,'purpose':'Prestar servicios de manera consistente y gestionar la demanda, los recursos y los compromisos.', 'sections': (
      ('Comprender','La entrega y el cierre son decisiones diferentes. Los ANS de cada ticket permanecen congelados.'),
      ('Preparar','Consulta el catálogo operativo, responsables, calendarios y límites WIP vigentes.'),
      ('Ejecutar','Asigna solicitudes y registra tareas, entregables y comunicaciones en la ficha original.'),
      ('Verificar','Consulta compromisos de respuesta y resolución por separado. Estima capacidad en horas de trabajo, no en horas de ANS.'),
      ('Conectar','Transfiere registros mediante el mecanismo existente del Paso 07; conserva evidencia y conformidad.'))}
}

GUIDANCE.update({
  1: {'chapter':14,'purpose':'Dar a conocer las capacidades y el valor potencial de la PMO y establecer relaciones con sus clientes.', 'sections': (
      ('Comprender','La sensibilización busca comprensión y confianza, no solo contabilizar eventos.'),
      ('Preparar','Revisa el directorio, los roles, las dependencias y los canales de comunicación.'),
      ('Ejecutar','Registra eventos, campañas y consultas mediante los formularios existentes.'),
      ('Verificar','Contrasta participación y evidencias con la cobertura y el conocimiento registrado.'),
      ('Conectar','Usa los contactos y la retroalimentación como insumos para evaluar necesidades en Paso 02.'))},
  7: {'chapter':20,'purpose':'Medir la prestación del servicio con información verificable y detectar oportunidades de mejora.', 'sections': (
      ('Comprender','Diferencia demanda, entregas, cierre, cumplimiento ANS y satisfacción. Son medidas distintas.'),
      ('Preparar','Consulta solicitudes de Paso 06, indicadores definidos y calendarios congelados.'),
      ('Ejecutar','Filtra los registros, analiza tendencias por evento y prepara informes de desempeño.'),
      ('Verificar','Revisa denominadores, fuentes, registros demostrativos y fechas. Sin base no hay porcentaje de cumplimiento.'),
      ('Conectar','Transfiere hallazgos documentados a Paso 08 por el mecanismo vigente.'))},
  8: {'chapter':21,'purpose':'Mejorar los servicios a partir de brechas, desempeño y retroalimentación documentada.', 'sections': (
      ('Comprender','Mantén independientes madurez institucional, metodológica y específica de los servicios.'),
      ('Preparar','Selecciona un ciclo real, sus evaluaciones y los hallazgos pertinentes.'),
      ('Ejecutar','Prioriza brechas y registra iniciativas, responsables, plazos y criterios de aceptación.'),
      ('Verificar','Revisa la última verificación y sus soportes. Un cambio entre ciclos no demuestra causalidad.'),
      ('Conectar','Usa las mejoras verificadas como insumos para revisar la entrega de valor, sin recalificar automáticamente.'))},
  9: {'chapter':22,'purpose':'Medir, verificar y comunicar los beneficios comprometidos con los clientes.', 'sections': (
      ('Comprender','Una actividad, un entregable o una nota de satisfacción no equivale a un beneficio materializado.'),
      ('Preparar','Identifica compromiso, indicador, unidad, línea base, meta, fuente y responsable.'),
      ('Ejecutar','Registra mediciones comparables y documenta los supuestos de atribución económica cuando apliquen.'),
      ('Verificar','Usa el mecanismo formal de validación y su evidencia. No sumes unidades diferentes ni conceptos económicos duplicados.'),
      ('Conectar','Transfiere únicamente beneficios elegibles a Paso 10 mediante la importación existente.'))},
  10: {'chapter':23,'purpose':'Comprender cómo los clientes reconocen el valor y retroalimentar el siguiente ciclo.', 'sections': (
      ('Comprender','Percepción, NPS, satisfacción y beneficio verificado son conceptos independientes.'),
      ('Preparar','Consulta los beneficios transferidos y define el periodo y grupo de la encuesta.'),
      ('Ejecutar','Registra respuestas, historias y retroalimentación con sus evidencias.'),
      ('Verificar','Contrasta la vigencia de beneficios locales, el vínculo por ID, la autorización de divulgación y los denominadores.'),
      ('Conectar','Registra nuevas expectativas y compromisos; utiliza el cierre del ciclo para orientar la siguiente exploración.'))}
})


def render(step):
    import streamlit as st
    guide = GUIDANCE.get(step)
    if not guide:
        return
    with st.expander(f'Orientación metodológica · Paso {step:02d}', expanded=False):
        st.markdown('**' + guide['purpose'] + '**')
        tabs = st.tabs([label for label, _ in guide['sections']])
        for tab, (_, detail) in zip(tabs, guide['sections']):
            with tab:
                st.write(detail)
        st.caption(f'Referencia: PMI (2025), Oficinas de Dirección de Proyectos: Una Guía Práctica, cap. {guide["chapter"]}. Adaptación CENS; no modifica datos ni decisiones.')
