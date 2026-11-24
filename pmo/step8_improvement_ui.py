"""V0.39.25 · Vista compacta de mejora, sin duplicar el perfil PMI ni las fuentes."""
from __future__ import annotations
import json
from datetime import date,timedelta
import pandas as pd
import streamlit as st
from .staff_picker import staff_picker
from . import step8 as core, step8_improvement as m, step8_documented as doc


def _call(fn,ok='Registro guardado'):
    try:
        value=fn();st.success(ok);return value if value is not None else True
    except (core.ValidationError,ValueError,KeyError,TypeError) as exc:
        st.error(str(exc));return None

def _date(value):
    try:return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError):return date.today()

def _stats(cols):
    fields=st.columns(len(cols))
    for col,(t,v,foot) in zip(fields,cols):
        with col:
            with st.container(border=True):
                st.metric(t,v)
                st.caption(foot)

def render_quality(r):
    z=m.quality(r['cycle']['id']);rsummary=r['summary']
    st.markdown('#### Calidad y cobertura de la evaluación')
    _stats([('Evaluados',f"{z['evaluados']}/26",'Cobertura total del catálogo'),
            ('Con validación',z['validados'],'Evaluación vigente con evidencia'),
            ('Sin soporte',z['sin_soporte'],'Calificaciones que requieren sustento'),
            ('Pendientes',z['pendientes'],'No son nivel cero')])
    st.progress(min(z['evaluados']/26,1),text=f"Cobertura {z['cobertura_pct']}% · {z['no_ofrecidos']} servicios no ofrecidos")
    if z['evaluados']<26 or z['pendientes']:
        st.warning('Índices provisionales: la cobertura es parcial. No se asigna nivel 0 a servicios sin evaluación o no ofrecidos.')
    if z['evaluados'] and z['validados']<z['evaluados']:
        st.info(f"{z['evaluados']-z['validados']} evaluaciones no tienen validación documental vigente. Registrar una nota no equivale a aprobar el nivel.")
    if z['discrepancias']:st.error(f"{z['discrepancias']} evaluaciones fueron modificadas después de su validación.")
    st.caption('La media macro muestra el promedio de las categorías disponibles; la media ponderada por servicios es otro indicador CENS. Ninguno sustituye el juicio documentado del evaluador.')
    with st.expander('Consultar sustento por servicio',expanded=False):
        lines=[]
        for x in r['ratings']:
            if x['estado']!='Evaluado':continue
            rv=doc.review(r['cycle']['id'],x['servicio_ref']);ev=doc.evidences(r['cycle']['id'],x['servicio_ref'])
            lines.append({'Servicio':x['name_es'],'Actual':x['actual'],'Deseada':x['deseado'],
                          'Brecha pp':x['gap'],'Estado documental':'Validada' if rv['vigente'] else rv['estado'],
                          'Evidencias':len(ev),'Evaluador':rv['evaluador']})
        st.dataframe(pd.DataFrame(lines),hide_index=True,use_container_width=True)

def render_brechas(r):
    st.markdown('#### Priorización de oportunidades')
    st.caption('La magnitud de la brecha es un criterio orientativo. El impacto, la viabilidad y la alineación estratégica se definen y justifican en cada iniciativa; no son pesos PMI automáticos.')
    data=[]
    for x in core.ranked(r['cycle']['id']):
        rv=doc.review(r['cycle']['id'],x['id'])
        data.append({'Ref':x['id'],'Servicio':x['name_es'],'Actual':x['actual'],
                     'Meta':x['deseado'],'Brecha (pp)':x['gap'],'Nivel de riesgo':core.gap_band(x['gap']),
                     'Sustento':'Validado' if rv['vigente'] else 'Por verificar'})
    st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True,height=290)

def _new_form(r):
    options={a['id']:a for a in r['ratings'] if a['estado']=='Evaluado'}
    if not options:
        st.info('Primero evalúa al menos un servicio. Las propuestas no alteran automáticamente la madurez.');return
    with st.expander('Nueva iniciativa vinculada a una brecha',expanded=not r['actions']):
        with st.form('p8_03925_new_action'):
            srv=st.selectbox('Servicio evaluado *',list(options),format_func=lambda k:f"{k:02d} · {options[k]['name_es']} · brecha {options[k]['gap']:.0f} pp")
            title=st.text_input('Acción concreta *',placeholder='Ej.: Estandarizar el proceso de actualización de proyectos')
            objective=st.text_input('Resultado verificable de la mejora *')
            root=st.text_area('Causa raíz de la brecha *',height=75)
            desc=st.text_area('Alcance de la iniciativa',height=75)
            a,b,c=st.columns(3)
            with a:owner=staff_picker('Responsable *',value=r['cycle']['responsable'])
            with b:due=st.date_input('Fecha meta',value=date.today()+timedelta(days=90), format='YYYY/MM/DD')
            with c:priority=st.selectbox('Prioridad',['Alta','Media','Baja','Crítica'])
            a,b,c=st.columns(3)
            with a:impact=st.selectbox('Impacto',['Alto','Medio','Bajo'])
            with b:target=st.selectbox('Nivel objetivo (opcional)',[None,1,2,3,4,5],format_func=lambda x:'— Referencia de ficha' if x is None else f'Nivel {x}')
            with c:actor=st.text_input('Quién registra *',value=r['cycle']['responsable'])
            criterion=st.text_input('Criterio de aceptación / evidencia de éxito *')
            indicator=st.text_input('Indicador asociado (nombre o código)',placeholder='Ej.: MET-SRV011-02')
            a,b=st.columns(2)
            with a:alignment=st.text_input('Alineación con necesidades o estrategia')
            with b:feasibility=st.text_input('Viabilidad y restricciones')
            res=st.text_input('Recursos requeridos')
            deps=st.text_input('Dependencias / prerrequisitos')
            risks=st.text_input('Riesgos relevantes')
            if st.form_submit_button('Registrar iniciativa en propuesta',type='primary'):
                action=_call(lambda:m.create_initiative(r['cycle']['id'],srv,title,owner,str(due),actor,
                    description=desc,impact=impact,indicator=indicator,
                    causa_raiz=root,objetivo=objective,prioridad=priority,alineacion=alignment,
                    viabilidad=feasibility,recursos=res,dependencias=deps,riesgos=risks,
                    criterio_aceptacion=criterion,nivel_objetivo=target),'Iniciativa creada sin aprobación automática')
                if action:st.rerun()

def _followup(action):
    a_id=action['id'];data=m.detail(a_id);detail=data['detalle']
    public=(detail or {}).get('codigo_publico') or 'LEGADO'
    title=f"{public} · {core.CAT[action['servicio_ref']]['name_es']} · {action['titulo']}"
    phase=(detail or {}).get('fase') or f"{action['estado']} · registro anterior"
    with st.expander(f'{title}  |  {phase}',expanded=False):
        if not detail:
            st.warning('Registro histórico del Paso 08: todavía no tiene ficha de iniciativa estructurada. Su estado y evidencia originales se conservan.')
            actor=st.text_input('Responsable de estructuración',value=action['responsable'],key='p8ext_actor_'+a_id)
            if st.button('Completar ficha de iniciativa',key='p8ext_'+a_id):
                if _call(lambda:m.extend_legacy(a_id,actor),'Ficha creada; el historial no fue reescrito'):st.rerun()
            return
        c1,c2,c3,c4=st.columns(4)
        with c1:st.metric('Fase',detail['fase'])
        with c2:st.metric('Prioridad',detail['prioridad'])
        with c3:st.metric('Soportes',len(m.supports(a_id)))
        with c4:st.metric('Hitos',len(m.milestones(a_id)))
        st.caption('La ejecución no aumenta automáticamente el nivel de madurez. La reevaluación se registra en un ciclo nuevo.')
        t1,t2,t3,t4=st.tabs(['01 · Diseño','02 · Hitos y fuentes','03 · Evidencia y verificación','04 · Decisiones y auditoría'])
        with t1:
            with st.form('p8det_'+a_id):
                root=st.text_area('Causa raíz',value=detail['causa_raiz'],height=80)
                goal=st.text_input('Objetivo verificable',value=detail['objetivo'])
                criterion=st.text_input('Criterio de aceptación',value=detail['criterio_aceptacion'])
                a,b,c=st.columns(3)
                with a:priority=st.selectbox('Prioridad',m.PRIORITIES,index=m.PRIORITIES.index(detail['prioridad']))
                with b:target=st.selectbox('Nivel meta',[None,1,2,3,4,5],index=[None,1,2,3,4,5].index(detail['nivel_objetivo']))
                with c:actor=staff_picker('Responsable del cambio',value=action['responsable'])
                alignment=st.text_input('Alineación',value=detail['alineacion'])
                feasibility=st.text_input('Viabilidad',value=detail['viabilidad'])
                resources=st.text_input('Recursos',value=detail['recursos'])
                deps=st.text_input('Dependencias',value=detail['dependencias'])
                risks=st.text_input('Riesgos',value=detail['riesgos'])
                disabled=detail['fase'] in ('Completada','Cancelada')
                if st.form_submit_button('Guardar ficha de mejora',disabled=disabled):
                    if _call(lambda:m.update_plan(a_id,actor,causa_raiz=root,objetivo=goal,
                        criterio_aceptacion=criterion,prioridad=priority,nivel_objetivo=target,
                        alineacion=alignment,viabilidad=feasibility,recursos=resources,
                        dependencias=deps,riesgos=risks),'Diseño actualizado'):st.rerun()
        with t2:
            ms=m.milestones(a_id)
            if ms:st.dataframe(pd.DataFrame([{'Hito':z['titulo'],'Fecha meta':z['fecha_meta'],
                 'Responsable':z['responsable'],'Estado':z['estado'],'Evidencia':z['evidencia']} for z in ms]),hide_index=True,use_container_width=True)
            if detail['fase'] not in ('Completada','Cancelada'):
                with st.form('p8_hito_'+a_id):
                    a,b=st.columns(2)
                    with a:milestone_title=st.text_input('Hito / entregable *')
                    with b:due=st.date_input('Fecha objetivo',value=date.today()+timedelta(days=30), format='YYYY/MM/DD')
                    owner=staff_picker('Responsable del hito',value=action['responsable'])
                    status=st.selectbox('Estado del hito',m.MILESTONE_STATES)
                    ev=st.text_input('Evidencia (obligatoria si está cumplido)')
                    if st.form_submit_button('Agregar hito'):
                        if _call(lambda:m.save_milestone(a_id,milestone_title,owner,str(due),action['responsable'],status,ev),'Hito registrado'):st.rerun()
            st.markdown('**Hallazgos del Paso 07 vinculados**')
            links=m.linked_findings(a_id)
            if links:st.dataframe(pd.DataFrame([{'Ticket':x['ticket_id'],'Tipo':x['tipo'],'Hallazgo':x['descripcion']} for x in links]),hide_index=True,use_container_width=True)
            sources=core.findings()
            options=[(x['ticket_id'],x['tipo'],x['fuente']) for x in sources]
            if options and detail['fase'] not in ('Completada','Cancelada'):
                sel=st.selectbox('Hallazgo existente del Paso 07',options,
                    format_func=lambda k:next((f"{x['ticket_id']} · {x['descripcion'][:90]}" for x in sources if (x['ticket_id'],x['tipo'],x['fuente'])==k),str(k)),key='p8f_sel_'+a_id)
                if st.button('Vincular hallazgo sin duplicarlo',key='p8f_attach_'+a_id):
                    if _call(lambda:m.attach_finding(a_id,*sel,action['responsable']),'Hallazgo vinculado'):st.rerun()
            elif not options:st.caption('Sin hallazgos disponibles: sincroniza Paso 07 en la sección inferior del plan.')
        with t3:
            supports=m.supports(a_id)
            if supports:st.dataframe(pd.DataFrame([{'Fecha':x['fecha'],'Tipo':x['tipo'],
                'Descripción':x['descripcion'],'Referencia':x['referencia']} for x in supports]),hide_index=True,use_container_width=True)
            with st.form('p8sup_'+a_id):
                kind=st.selectbox('Tipo de soporte',m.EVIDENCE_TYPES)
                description=st.text_input('Qué demuestra el soporte')
                reference=st.text_input('Código / ruta / URL documental')
                actor=st.text_input('Registrado por',value=action['responsable'])
                if st.form_submit_button('Registrar soporte'):
                    if _call(lambda:m.add_support(a_id,kind,description,reference,actor),'Soporte registrado'):st.rerun()
            if detail['fase']=='En verificación':
                if supports:
                    with st.form('p8verify_'+a_id):
                        result=st.selectbox('Resultado de verificación',['Conforme','Requiere ajustes','No conforme'])
                        ev=st.selectbox('Soporte vinculado',list(x['id'] for x in supports),format_func=lambda k:next(x['descripcion'] for x in supports if x['id']==k))
                        observed=st.text_input('Valor medido / resultado observado (si aplica)')
                        notes=st.text_area('Conclusión técnica de la verificación *')
                        inspector=st.text_input('Verificador',value=action['responsable'])
                        if st.form_submit_button('Guardar verificación'):
                            if _call(lambda:m.verify(a_id,result,notes,inspector,ev,observed),'Verificación registrada; no cambia la madurez'):st.rerun()
                else:st.warning('Registra un soporte antes de verificar los resultados.')
            ver=m.verifications(a_id)
            if ver:st.dataframe(pd.DataFrame([{'Fecha':x['fecha'],'Resultado':x['resultado'],'Valor observado':x['valor_observado'],'Verificador':x['verificador']} for x in ver]),hide_index=True,use_container_width=True)
        with t4:
            st.caption('Secuencia controlada: Propuesta → Aprobada → En ejecución → En verificación → Completada. Las decisiones son explícitas y dejan registro de auditoría.')
            moves={'Propuesta':['Aprobada','Cancelada'],'Aprobada':['En ejecución','Cancelada'],
                   'En ejecución':['En verificación','Cancelada'],
                   'En verificación':['En ejecución','Completada','Cancelada'],
                   'Completada':[],'Cancelada':[]}
            possible=moves[detail['fase']]
            if possible:
                with st.form('p8_stage_'+a_id):
                    future=st.selectbox('Siguiente decisión',possible)
                    who=st.text_input('Responsable de la decisión',value=action['responsable'])
                    ref=st.text_input('Acta / referencia de decisión (necesaria para aprobación o cancelación)')
                    if st.form_submit_button('Registrar decisión',type='primary'):
                        if _call(lambda:m.set_stage(a_id,future,who,ref),'Decisión trazada y guardada'):st.rerun()
            with st.expander('Historial y cadena de evidencia'):
                chain=m.evidence_chain(a_id)
                st.json({'madurez':chain['madurez'],'evaluacion_validada':chain['evaluacion_validada'],
                        'hitos':len(chain['hitos']),'hallazgos':len(chain['hallazgos']),
                        'soportes':len(chain['soportes']),'verificaciones':len(chain['verificaciones'])})
                from .storage import connect
                with connect() as con:
                    events=[dict(x) for x in con.execute('SELECT fecha,actor,evento,despues_json FROM p8_mejora_auditoria WHERE accion_id=? ORDER BY fecha,id',(a_id,))]
                if events:st.dataframe(pd.DataFrame(events),hide_index=True,use_container_width=True)

def render_plan(r):
    m.initialize()
    z=m.quality(r['cycle']['id'])
    current=m.initiatives(r['cycle']['id'])
    _stats([('Servicios evaluados',f"{z['evaluados']}/26",'Calificación por ciclo'),
            ('Brechas críticas',sum(x['gap'] is not None and x['gap']>=30 for x in r['ratings']),'≥30 pp; umbral CENS'),
            ('Iniciativas',len(current),'Incluye registros anteriores'),
            ('Completadas verificadas',sum(x['fase']=='Completada' for x in current),'Evidencia y verificación conforme')])
    _new_form(r)
    st.markdown('#### Portafolio de acciones e iniciativas')
    if current:
        stage=st.selectbox('Filtrar por fase',['Todas',*m.STAGES,'Históricas sin estructurar'],key='p8_phase_filter')
        toshow=[x for x in current if stage=='Todas' or x['fase']==stage or (stage=='Históricas sin estructurar' and x['fase'] is None)]
        if not toshow:st.info('No hay iniciativas para el filtro elegido.')
        for action in toshow:_followup(action)
    else:st.info('Aún no existen iniciativas. Registra la primera a partir de un servicio evaluado.')
    with st.expander('Hallazgos del Paso 07 y correspondencias con el Paso 04',expanded=False):
        if st.button('Sincronizar hallazgos de Paso 07',key='p8_03925_sync'):
            def sincronizar():
                from . import step7
                step7.sync_live()  # actualiza el espejo consultivo de Paso 06, no los tickets originales
                return core.import_step7_direct()
            if _call(sincronizar,'Hallazgos consultados sin modificar la fuente'):st.rerun()
        findings=core.findings()
        if findings:st.dataframe(pd.DataFrame([{'Ticket':x['ticket_id'],'Tipo':x['tipo'],'Hallazgo':x['descripcion'],'Origen':x['servicio_origen']} for x in findings]),hide_index=True,use_container_width=True)
        else:st.caption('No hay hallazgos; su ausencia no equivale a cumplimiento.')
        st.divider()
        st.markdown('**Correspondencia de servicios con control documental**')
        from . import step4
        choices={x['id']:x for x in step4.services()}
        refs={x['id']:x for x in r['ratings']}
        if choices:
            a,b=st.columns(2)
            with a:ref=st.selectbox('Servicio de referencia PMI',[x for x in refs],format_func=lambda k:refs[k]['name_es'],key='p8_link_r_25')
            with b:sid=st.selectbox('Servicio real CENS',list(choices),format_func=lambda k:f"{choices[k]['codigo']} · {choices[k]['nombre']}",key='p8_link_s_25')
            if st.button('Registrar correspondencia pendiente de validar',key='p8_25_link'):
                if _call(lambda:core.link_service(r['cycle']['id'],ref,sid),'Correspondencia creada; requiere verificación'):st.rerun()
        correlations=m.correspondence(r['cycle']['id'])
        if correlations:
            st.dataframe(pd.DataFrame([{'Ref':x['servicio_ref'],'Servicio CENS':x['servicio_cens'],
              'Verificación':x['verificacion'],'Justificación':x['justificacion']} for x in correlations]),hide_index=True,use_container_width=True)
            sel=st.selectbox('Correspondencia para revisar',list(range(len(correlations))),format_func=lambda i:f"{correlations[i]['servicio_ref']:02d} → {correlations[i]['servicio_cens']}")
            item=correlations[sel]
            with st.form('p8_25_verify_link'):
                state=st.selectbox('Estado',['Por verificar','Verificada','Rechazada'])
                why=st.text_input('Justificación del alcance y equivalencia *')
                actor=st.text_input('Verificador',value=r['cycle']['responsable'])
                if st.form_submit_button('Guardar verificación de correspondencia'):
                    if _call(lambda:m.verify_correspondence(r['cycle']['id'],item['servicio_ref'],item['servicio_cens'],state,why,actor),'Correspondencia revisada'):st.rerun()
    with st.expander('Exportar expediente de mejora verificable'):
        payload=m.export_improvements(r['cycle']['id'])
        st.download_button('Descargar informe de iniciativas y evidencias (JSON)',
           json.dumps(payload,ensure_ascii=False,indent=2,default=str).encode('utf-8'),
           file_name='CENS_Paso08_Mejoras_V03925.json',mime='application/json')
        st.caption('Los datos del Paso 08 y los archivos originales del Paso 07 permanecen intactos. Conserva un respaldo de SQLite para restaurar el expediente completo.')

def render_evolution():
    cs=core.cycles()
    if len(cs)<2:return
    opts={x['id']:x for x in cs}
    st.markdown('#### Evolución comparable por servicio')
    with st.container(border=True):
        a,b=st.columns(2)
        with a:past=st.selectbox('Ciclo base',list(opts),index=len(opts)-1,format_func=lambda k:opts[k]['nombre']+' · '+opts[k]['inicio'],key='p8hist_base')
        with b:later=st.selectbox('Ciclo de reevaluación',list(opts),index=0,format_func=lambda k:opts[k]['nombre']+' · '+opts[k]['inicio'],key='p8hist_after')
        if past==later:st.info('Selecciona dos ciclos distintos.');return
        comparison=m.compare_cycles(past,later)
        if opts[past]['es_demo'] or opts[later]['es_demo']:
            st.warning('Al menos uno de los ciclos comparados contiene datos de demostración. No lo reportes como resultado institucional.')
        _stats([('Comparables',comparison['comparables'],'Evaluados en ambos ciclos'),
                ('Mejoraron',comparison['mejoraron'],'Nivel mayor en reevaluación'),
                ('Sin cambio',comparison['sin_cambio'],'Mismo nivel'),
                ('Disminuyeron',comparison['retrocedieron'],'Nivel menor')])
        df=pd.DataFrame(comparison['filas'])
        st.dataframe(df.rename(columns={'servicio':'Servicio','antes':'Inicial','despues':'Final',
               'delta':'Cambio de nivel','comparable':'Comparable'}),hide_index=True,use_container_width=True)
        st.caption('La comparación excluye servicios sin evaluación en cualquiera de los ciclos; no atribuye causalidad a las iniciativas ni valida beneficios del Paso 09.')
