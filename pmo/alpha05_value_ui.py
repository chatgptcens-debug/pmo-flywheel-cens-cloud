"""Vistas de lectura de Alpha05. Formularios y aprobaciones permanecen en sus módulos."""
import pandas as pd
import streamlit as st
from . import alpha05_value as a
from . import step8, pmi_flywheel_assessment
from .alpha04_operations import read_data


def table(rows, key=None):
    if rows is None: st.warning('Fuente no disponible en esta base.');return
    if not rows: st.info('Sin registros para esta selección.');return
    frame=pd.DataFrame(rows)
    st.dataframe(frame,hide_index=True,use_container_width=True)
    if key:
        # Evitar fórmulas activas al abrir CSV en una hoja de cálculo.
        def safe(v):return "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else v
        csv=frame.apply(lambda col:col.map(safe)).to_csv(index=False).encode('utf-8-sig')
        st.download_button('Descargar consulta CSV',csv,file_name=key+'.csv',mime='text/csv',key=key)


def metrics(values):
    for col,(name,value) in zip(st.columns(len(values)),values):
        col.metric(name,'—' if value is None else value)


def render_performance(items):
    with st.expander('Centro de desempeño · tendencias y bases de cálculo',expanded=False):
        st.caption('Solo registros no demostrativos de la cohorte de tickets seleccionada. Las fechas del filtro principal seleccionan tickets; cada tendencia utiliza el mes del evento correspondiente, que puede ser distinto. No es una reconstrucción de cortes históricos.')
        fb=read_data({'feedback':'SELECT * FROM p6_respuestas_cliente WHERE vigente=1'})['feedback']
        if fb is None:st.warning('Fuente de respuestas de clientes no disponible; CSAT no calculado.')
        rows=a.performance(items,fb or [])
        if not rows:return st.info('Sin eventos registrados en la selección.')
        frame=pd.DataFrame(rows).set_index('Mes')
        st.bar_chart(frame[['Recibidas','Entregadas']])
        if any(r['Base respuesta'] or r['Base resolución'] for r in rows):
            st.line_chart(frame[['ANS respuesta %','ANS resolución %']].astype(float))
        else:st.caption('Sin eventos ANS evaluables.')
        if fb is not None and any(r['Base CSAT'] for r in rows):st.line_chart(frame[['CSAT /5']])
        st.caption('ANS completados y evaluables según el motor vigente del Paso 07; solicitudes abiertas se analizan en el control ANS. CSAT corresponde a la última respuesta vigente por ticket, en su fecha registrada. Un mes sin base no es 0%.')
        table(rows,'alpha05_tendencias_p7')


def render_maturity(report):
    with st.expander('Mapa de calor · madurez actual, objetivo y brechas',expanded=True):
        rows=a.maturity_rows(report)
        if not rows:return st.info('Sin servicios en el ciclo.')
        frame=pd.DataFrame(rows)
        def color(v):
            if pd.isna(v):return 'background-color:#E5E7EB;color:#475569'
            return 'background-color:'+['#F9DDD4','#F8E7BD','#E5EDC7','#BEE4D9','#75C9B2'][max(0,min(4,int(v)-1))]+';color:#173B40'
        st.dataframe(frame.style.applymap(color,subset=['Actual','Meta']).format({'Actual':'{:.0f}','Meta':'{:.0f}','Brecha pp':'{:.0f}'},na_rep='—'),hide_index=True,use_container_width=True)
        st.caption('Escala 1–5 de madurez del servicio; gris = no evaluado / no ofrecido. Brecha en puntos porcentuales según Paso 08. No se combina con madurez institucional o metodológica.')


def render_integral():
    with st.expander('Centro integral de madurez · tres instrumentos independientes',expanded=False):
        st.caption('Consulta comparativa de instrumentos, no índice compuesto. Cada selección conserva su propio periodo y escala.')
        tabs=st.tabs(['Institucional · 0–5','Metodológica · 1–5','Servicios · 1–5'])
        with tabs[0]:
            data=read_data({'s':'SELECT * FROM p2_madurez_anual_escenarios ORDER BY ano DESC,escenario','d':'SELECT * FROM p2_madurez_anual_dimensiones ORDER BY ano DESC,escenario,dimension'})
            if data['s'] is None or data['d'] is None:st.warning('Fuente institucional no disponible.')
            else:
                table([{k:r[k] for k in ('ano','escenario','indice','fuente')} for r in data['s']])
                table([{k:r[k] for k in ('ano','escenario','dimension','puntaje')} for r in data['d']])
        with tabs[1]:
            data=read_data({'p':"SELECT DISTINCT periodo FROM pmi_step_evaluations WHERE es_demo=0 AND estado='Finalizada' ORDER BY periodo DESC"})['p']
            if data is None:st.warning('Fuente de autoevaluaciones no disponible.')
            elif not data:st.info('No hay evaluaciones finalizadas no demostrativas.')
            else:
                p=st.selectbox('Periodo metodológico',[r['periodo'] for r in data],key='a05_maturity_pmi')
                r=pmi_flywheel_assessment.consolidated(p)
                metrics([('Pasos completos',f"{r['completos']}/10"),('Índice metodológico',round(r['indice'],2) if r['indice'] is not None else None)])
                if r['mixed_instruments']:st.warning('Este periodo incluye instrumentos distintos; revisar comparabilidad.')
                table(r['pasos'])
        with tabs[2]:
            cycles=[c for c in step8.cycles() if not c['es_demo']]
            if not cycles:st.info('No hay ciclos no demostrativos de madurez de servicios.')
            else:
                opts={c['id']:c for c in cycles}
                def label(k):
                    c=opts[k];return f"{c['nombre']} · {c['inicio']}–{c['fin']} · {c['estado']} · {k[:8]}"
                current=st.selectbox('Ciclo de servicios',list(opts),format_func=label,key='a05_maturity_service')
                r=step8.report(current);z=r['summary'];metrics([('Evaluados',z['assessed']),('Actual %',round(z['current'],1) if z['current'] is not None else None),('Meta %',round(z['desired'],1) if z['desired'] is not None else None)])
                table(a.maturity_rows(r))
                other=st.selectbox('Ciclo anterior para contraste',[None]+[k for k in opts if k!=current],format_func=lambda k:label(k) if k else 'Sin comparación',key='a05_maturity_other')
                if other:
                    if opts[other]['fin']>opts[current]['inicio']:st.warning('Los periodos se solapan o no están en orden temporal. Lee el contraste como diferencia entre registros, no como efecto causal.')
                    table(a.maturity_comparison(step8.report(other),r),'alpha05_comparacion_madurez')
                    st.caption('El cambio entre dos evaluaciones registradas no demuestra por sí mismo la efectividad de una iniciativa.')


def render_backlog(report):
    with st.expander('Backlog consultivo · compromisos y última verificación',expanded=False):
        if report['cycle']['es_demo']:return st.info('Ciclo demostrativo: excluido de esta consulta institucional.')
        d=a.improvement_data()
        if d['actions'] is None:return st.warning('Fuente de iniciativas no disponible.')
        rows=a.backlog([x for x in d['actions'] if x['ciclo_id']==report['cycle']['id']],d['checks'],d['origins'])
        metrics([('Iniciativas',len(rows)),('Vencidas',sum(x['Vencida'] is True for x in rows)),('Última verificación conforme con soporte',sum(x['Última verificación']=='Conforme' and x['Soporte de última verificación'] for x in rows) if d['checks'] is not None else None)])
        states=sorted({x['Fase'] for x in rows}); phase=st.selectbox('Filtrar fase',['Todas']+states,key='a05_backlog_phase')
        table([x for x in rows if phase=='Todas' or x['Fase']==phase],'alpha05_backlog_mejora')
        st.caption('La última verificación documentada no equivale a aprobación, aumento de madurez ni beneficio validado. Las iniciativas históricas sin detalle conservan su estado original.')


def render_benefits():
    with st.expander('Centro de beneficios · trazabilidad y preparación del reporte',expanded=False):
        d=a.benefit_data();rows=a.benefit_rows(d)
        if rows is None:return st.warning('Fuente de beneficios o mediciones no disponible.')
        metrics([('Compromisos',len(rows)),('Medidos',sum(x['Mediciones']>0 for x in rows)),('Verificados',sum(x['Situación']=='Verificado' for x in rows))])
        deps=sorted({x['Dependencia'] for x in rows if x['Dependencia']}); opts=['Todos','Sin medición','Medido sin verificación vigente','Verificado']
        c1,c2=st.columns(2)
        with c1:dep=st.selectbox('Dependencia',['Todas']+deps,key='a05_benefit_dep')
        with c2:state=st.selectbox('Situación verificable',opts,key='a05_benefit_state')
        selected=[x for x in rows if (dep=='Todas' or x['Dependencia']==dep) and (state=='Todos' or x['Situación']==state)]
        st.caption('Estado vigente al consultar, no fotografía histórica. Se exige validación asociada a la última medición registrada. No agrega resultados de unidades distintas.')
        table(selected,'alpha05_centro_beneficios')
        st.markdown('**Alineación estratégica · insumos documentados**')
        if d['indicators'] is None:st.warning('Fuente de definiciones de indicadores no disponible.')
        else:table([{k:x[k] for k in ('ID','Servicio','Beneficio','Objetivo del indicador','Estado indicador','Impacto','Origen P3')} for x in selected])
        st.caption('El objetivo del indicador es un insumo, no un objetivo aprobado del Plan Empresa. No se asignan relaciones estratégicas sin catálogo y validación institucional.')


def render_recognition(period,group):
    with st.expander('Observatorio de percepción · reconocimiento y vigencia',expanded=False):
        local=a.benefit_rows(a.benefit_data())
        r=a.recognition(a.recognition_data(),local,period,group)
        if r is None:return st.warning('Fuente de reconocimiento no disponible.')
        n=r['nps'];metrics([('Respuestas no demo',n['total']),('NPS',round(n['puntaje'],1) if n['puntaje'] is not None else None),('Umbral configurado /10',r['threshold'])])
        st.caption('La encuesta se filtra por periodo y grupo; la lista de beneficios importados vigentes es general. Reconocimiento se expresa como percepción promedio de respuestas vinculadas por ID, no confirmación del beneficio por sí misma.')
        table(r['groups'],'alpha05_percepcion_segmentos')
        table(r['benefits'],'alpha05_reconocimiento_beneficios')
        st.markdown('**Historias de valor · control documental**')
        st.caption('Historias filtradas por grupo, no por periodo de encuesta. Estado y autorización se consultan sin publicarlas ni modificarlas.')
        table(r['stories'],'alpha05_historias_valor')
        st.download_button('Informe agregado para sponsor (HTML)',a.sponsor_html(local,r,period,group).encode('utf-8'),file_name='CENS_Alpha05_Lectura_Ejecutiva.html',mime='text/html',key='a05_sponsor_html')
        st.caption('Origen externo no implica cotejo con validación local. Si el registro del Paso 09 cambió, revisa la transferencia mediante el formulario vigente. Los registros demostrativos se excluyen de esta consulta.')
