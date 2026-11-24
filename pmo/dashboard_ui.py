"""V0.30: presentación ejecutiva del Paso 01. Solo lee fuentes del Ciclo 01."""
from __future__ import annotations
from datetime import date, timedelta
import html

import streamlit as st

from .awareness_dashboard import snapshot, coverage_csv, executive_report, executive_html
from .storage import connect
from contextlib import closing


def _escape(x):
    return html.escape(str(x))


def _kpi(label, value, foot, icon='◉'):
    from .panel_superior import render_kpi_card_panel
    theme_map={
        'Clientes activos':'orange','Clientes alcanzados':'blue',
        'Familiaridad PMO':'purple','Interacciones':'teal',
        'Asistentes únicos':'orange','Consultas':'blue',
        'Portal de valor':'purple','Compromisos':'teal',
    }
    st.markdown(render_kpi_card_panel(label=label,value=value,subtext=foot,
                  icon_name=icon,theme=theme_map.get(label,'orange')),unsafe_allow_html=True)


def _options():
    with closing(connect()) as con:
        rows=con.execute('''SELECT d.nombre,c.equipo_trabajo FROM pmo_clientes c
             JOIN pmo_dependencias d ON d.id=c.dependencia_id
             WHERE c.activo=1 ORDER BY d.nombre,c.equipo_trabajo''').fetchall()
    return [(r['nombre'],r['equipo_trabajo'] or '') for r in rows]


def render_dashboard():
    st.markdown('''<style>
      .pmo30-title{font-size:27px;letter-spacing:-.8px;color:#10374B;font-weight:820;margin:0 0 4px}
      .pmo30-overline{font-size:11px;font-weight:800;color:#0A858A;letter-spacing:1.1px;margin:7px 0}
      .pmo30-sub{font-size:13px;color:#61778A;margin:0 0 18px;line-height:1.55}
      .pmo30-kpi{min-height:134px;border:1px solid #DBE7EC;background:#FFF;border-radius:15px;
         padding:17px 18px;margin-bottom:10px;box-shadow:0 6px 24px rgba(24,62,79,.055)}
      .pmo30-kpi-label{display:flex;align-items:center;justify-content:space-between;
         font-size:12px;font-weight:750;color:#516E81}
      .pmo30-ico{background:#E8F5F6;color:#0B7F87;font-size:17px;padding:5px 9px;border-radius:10px}
      .pmo30-kpi-value{font-size:30px;letter-spacing:-.5px;color:#10374B;font-weight:850;margin:12px 0 5px}
      .pmo30-kpi-foot{font-size:11.5px;color:#708496;line-height:1.4}
      .pmo30-section{font-weight:780;font-size:17px;color:#10374B;margin:16px 0 7px}
      .pmo30-note{border-left:3px solid #0C989B;border-radius:8px;background:#EBF6F7;
          font-size:12px;color:#416678;padding:12px 14px;margin-top:15px}
      </style>''',unsafe_allow_html=True)
    st.markdown('<div class="pmo30-overline">PASO 01 · GENERACIÓN DE CONCIENCIA</div>',unsafe_allow_html=True)
    st.markdown('<div class="pmo30-title">Tablero ejecutivo de concienciación</div>',unsafe_allow_html=True)
    st.markdown('<div class="pmo30-sub">Alcance, participación, conocimiento y evidencias del valor de la PMO. Datos reales del Ciclo 01.</div>',unsafe_allow_html=True)

    people=_options()
    dependencies=['Todas las dependencias']+sorted({dep for dep,_ in people},key=str.casefold)
    f1,f2,f3=st.columns([1.1,1.1,1.1],gap='small')
    with f1: dependency=st.selectbox('Dependencia',dependencies,key='pmo30_dep')
    selected_dep='' if dependency==dependencies[0] else dependency
    possible_teams=sorted({team for dep,team in people if team and (not selected_dep or dep==selected_dep)},key=str.casefold)
    with f2:
        team=st.selectbox('Equipo de trabajo',['Todos los equipos']+possible_teams,key='pmo30_team')
    with f3:
        period=st.selectbox('Periodo',['Todo el ciclo','Últimos 30 días','Últimos 90 días','Personalizado'],key='pmo30_period')
    today=date.today()
    start,end='',''
    if period=='Últimos 30 días': start=(today-timedelta(days=29)).isoformat(); end=today.isoformat()
    elif period=='Últimos 90 días': start=(today-timedelta(days=89)).isoformat(); end=today.isoformat()
    elif period=='Personalizado':
        p1,p2=st.columns(2)
        with p1: d0=st.date_input('Desde',value=today.replace(day=1),key='pmo30_start', format='YYYY/MM/DD')
        with p2: d1=st.date_input('Hasta',value=today,key='pmo30_end', format='YYYY/MM/DD')
        start,end=d0.isoformat(),d1.isoformat()
        if start>end:
            st.error('El inicio del periodo no puede ser posterior al final.')
            return
    data=snapshot(dependency=selected_dep,team='' if team=='Todos los equipos' else team,start=start,end=end)
    pct='Sin denominador' if data['coverage'] is None else f"{data['coverage']:.0f}%"
    fam='Sin medición' if data['familiarity'] is None else f"{data['familiarity']:.1f} / 5"

    cols=st.columns(4,gap='small')
    for col,values in zip(cols,(
       ('Clientes activos',str(data['active']),'Población objetivo del filtro','♙'),
       ('Clientes alcanzados',str(data['reached'])+(' · '+pct if data['active'] else ''),'Unión por ID, sin duplicados','◎'),
       ('Familiaridad PMO',fam,f"{data['survey_after_clients']} clientes con encuesta posterior",'◈'),
       ('Interacciones',str(data['interactions']),'Contactos documentados en el periodo','✉'),
    )):
        with col:_kpi(*values)

    secondary=st.columns(4,gap='small')
    for col,(name,val,foot,icon) in zip(secondary,(
        ('Asistentes únicos',data['attendance_unique'],f"{data['attendance_total']} asistencias confirmadas",'◉'),
        ('Consultas',data['consultations'],f"{data['tickets_pending']} pendientes de respuesta",'▤'),
        ('Portal de valor',data['resource_visits'],f"{data['resource_clients']} clientes con consulta atribuida",'▣'),
        ('Compromisos',data['commitments_pending'],f"{data['commitments_overdue']} vencidos",'◷'),
    )):
        with col:_kpi(name,str(val),foot,icon)

    pcoverage,pknowledge,pevidence=st.tabs(['Cobertura y actividad','Conocimiento y comprensión','Evidencias y mejora'])
    with pcoverage:
        left,right=st.columns([1.45,1],gap='medium')
        with left:
            st.markdown('<div class="pmo30-section">Cobertura por dependencia</div>',unsafe_allow_html=True)
            st.caption('Clientes distintos alcanzados y pendientes sobre el directorio activo. Solo fuentes con ID verificable.')
            rows=data['department_coverage']
            if rows:
                st.bar_chart(rows,x='Dependencia',y=['Alcanzados','Pendientes'],horizontal=True,stack=True,height=320)
                st.dataframe(rows,hide_index=True,use_container_width=True,height=min(355,65+len(rows)*35))
            else:st.info('No existen clientes activos para los filtros seleccionados.')
        with right:
            st.markdown('<div class="pmo30-section">Cobertura del público objetivo</div>',unsafe_allow_html=True)
            if data['coverage'] is not None:
                safe_pct=max(0,min(100,round(data['coverage'])))
                st.markdown(f'''<div style="height:168px;width:168px;border-radius:50%;background:conic-gradient(#0C989B {safe_pct}%,#E5EFF3 {safe_pct}%);margin:14px auto;display:grid;place-items:center">
                  <div style="height:125px;width:125px;border-radius:50%;background:#fff;display:grid;place-items:center;font-size:30px;color:#10374B;font-weight:850">{safe_pct}%</div></div>''',unsafe_allow_html=True)
                st.caption(f"{data['reached']} clientes alcanzados de {data['active']} activos")
            else:st.info('Sin población objetivo: no es posible calcular cobertura.')
            st.markdown('<div class="pmo30-section">Fuentes del alcance</div>',unsafe_allow_html=True)
            st.dataframe([
                {'Fuente':'Asistencias a eventos realizados','Registros':data['sources']['attendance']},
                {'Fuente':'Interacciones registradas','Registros':data['sources']['interactions']},
                {'Fuente':'Consultas formales','Registros':data['sources']['consultations']},
                {'Fuente':'Consultas del portal identificadas','Registros':data['sources']['portal']},
            ],hide_index=True,use_container_width=True)
        st.markdown('<div class="pmo30-section">Actividad mensual</div>',unsafe_allow_html=True)
        st.caption('Clientes únicos por mes; no sumar personas entre meses. Se muestran hasta 12 meses con actividad registrada.')
        if data['monthly']:
            st.line_chart(data['monthly'],x='Mes',y=['Asistencias','Interacciones','Consultas','Portal'],height=250)
            st.dataframe(data['monthly'],hide_index=True,use_container_width=True)
        else:st.info('Todavía no se han registrado actividades verificables en el periodo.')
        with st.expander('Cobertura por equipo de trabajo'):
            if data['team_coverage']:st.dataframe(data['team_coverage'],hide_index=True,use_container_width=True)
            else:st.info('No hay equipos con clientes activos en la selección.')

    with pknowledge:
        st.markdown('<div class="pmo30-section">Comprensión y aprendizaje: encuestas</div>',unsafe_allow_html=True)
        c1,c2,c3=st.columns(3)
        c1.metric('Encuestas posteriores',data['survey_after_count'])
        c2.metric('Clientes con encuesta posterior',data['survey_after_clients'])
        c3.metric('Pares comparables',data['paired_count'])
        if data['paired_count']:
            st.caption('Comparación de las mismas personas y contexto de evento. Cinco dimensiones, escala de 1 a 5.')
            st.bar_chart(data['knowledge'],x='Dimensión',y=['Antes','Después'],height=320)
            st.dataframe(data['knowledge'],hide_index=True,use_container_width=True)
        else:
            st.info('Sin pares comparables Antes/Después. No se calcula variación de conocimiento sin ambas mediciones por cliente y evento.')
        st.markdown('<div class="pmo30-note">Una asistencia, un contacto o una descarga no demuestran comprensión ni beneficios. Las encuestas solo representan a su muestra, no automáticamente a los 112 clientes.</div>',unsafe_allow_html=True)

    with pevidence:
        st.markdown('<div class="pmo30-section">Matriz de evidencias del Paso 01</div>',unsafe_allow_html=True)
        st.caption('Cinco actividades de la metodología. Los estados describen información registrada, no una certificación de cumplimiento.')
        st.dataframe(data['evidence'],hide_index=True,use_container_width=True,height=260)
        left,right=st.columns(2,gap='medium')
        with left:
            st.markdown('<div class="pmo30-section">Seguimiento</div>',unsafe_allow_html=True)
            st.metric('Compromisos pendientes',data['commitments_pending'])
            st.metric('Eventos realizados',data['events_realized'])
            if data['publications'] is not None:
                st.metric('Recursos publicados',data['publications'])
            st.metric('Compromisos vencidos',data['commitments_overdue'])
            st.metric('Antecedentes potenciales para Paso 02',data['needs_preliminary'])
        with right:
            st.markdown('<div class="pmo30-section">Autoevaluación metodológica</div>',unsafe_allow_html=True)
            assessment=data['assessment']
            if assessment:
                st.metric('Resultado',f"{assessment['puntaje']} / 125")
                st.write(f"**Clasificación:** {assessment['clasificacion'] or 'Sin clasificar'}")
                st.caption(f"Periodo de instrumento: {assessment['periodo']}. Cuestionario de la aplicación: adaptación CENS, no instrumento PMI oficial reproducido.")
            else:st.info('Sin autoevaluación finalizada para el periodo. Regístrala en el componente Autoevaluación PMI.')
        st.markdown('<div class="pmo30-note">La mejora continua exige evidencias del ajuste realizado y de su efecto. Cerrar un compromiso no equivale necesariamente a mejorar la concienciación.</div>',unsafe_allow_html=True)

    st.markdown('<div class="pmo30-section">Exportar resultados del Paso 01</div>',unsafe_allow_html=True)
    exp1,exp2=st.columns(2)
    with exp1:
        st.download_button('Descargar informe ejecutivo',data=executive_html(data),file_name='PMO_CENS_Informe_Concienciacion_Paso01.html',mime='text/html',use_container_width=True)
    with exp2:
        st.download_button('Descargar cobertura por dependencia (CSV)',data=coverage_csv(data),file_name='PMO_CENS_Cobertura_Paso01.csv',mime='text/csv',use_container_width=True)
    st.caption('Fuente: base SQLite del Ciclo 01. El informe indica el periodo, los filtros, los criterios de cálculo y las limitaciones de interpretación.')
