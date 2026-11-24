"""Vista transversal de madurez metodológica PMI · Paso 8, adaptación de CENS."""
from __future__ import annotations
import html,json,math
from datetime import date
import pandas as pd
import streamlit as st
from . import step8_profile as model


def _esc(x):return html.escape(str(x if x is not None else ''))
def _num(x):return '—' if x is None else f'{x:.2f}'.replace('.',',')
def _json(obj):return json.dumps(obj,indent=2,ensure_ascii=False,default=str).encode('utf8')

def _action(func,success):
    try:
        v=func();st.success(success);return v
    except (ValueError,TypeError,KeyError) as e:
        st.error(str(e));return None

def radar_svg(steps):
    """Radar de diez ejes: 1–5 en CADA eje, valores y conexiones sin ceros ficticios.

    Los pasos sin evaluación carecen de punto. Las conexiones que saltan pasos
    pendientes son discontinuas y no suponen puntuación para esos pasos.
    """
    import textwrap
    cx,cy,r=560,349,222
    width,height=1120,735
    def ang(i):return -math.pi/2+2*math.pi*i/10
    def xy(i,value):
        theta=ang(i)
        return cx+math.cos(theta)*r*float(value)/5,cy+math.sin(theta)*r*float(value)/5
    def coords(points):return ' '.join(f'{x:.1f},{y:.1f}' for x,y in points)
    grid=''.join(f'<polygon points="{coords([xy(i,level) for i in range(10)])}" fill="{("#faf8ff" if level==5 else "none")}" stroke="#DBE2F4" stroke-width="1.5" />' for level in range(5,0,-1))
    axes=''.join(f'<line x1="{cx}" y1="{cy}" x2="{xy(i,5)[0]:.1f}" y2="{xy(i,5)[1]:.1f}" stroke="#BCCAE5" stroke-width="1.4" />' for i in range(10))
    ticks=[]
    for i in range(10):
        theta=ang(i)
        # Text is shifted orthogonal to the axis so each axis has 1,2,3,4,5.
        dx=-math.sin(theta)*11
        dy=math.cos(theta)*11
        for level in range(1,6):
            x,y=xy(i,level)
            ticks.append(f'<text x="{x+dx:.1f}" y="{y+dy+3:.1f}" text-anchor="middle" fill="#72819e" font-size="10.5" font-weight="600" font-family="Segoe UI,Arial">{level}</text>')
    names=[]
    for i,item in enumerate(steps):
        theta=ang(i); lx=cx+math.cos(theta)*(r+72);ly=cy+math.sin(theta)*(r+71)
        anchor='start' if math.cos(theta)>.28 else 'end' if math.cos(theta)<-.28 else 'middle'
        title=str(item.get('short') or item.get('name') or '')
        parts=textwrap.wrap(title,width=23,break_long_words=False,break_on_hyphens=False) or [title]
        if len(parts)>2:parts=[parts[0],' '.join(parts[1:])]
        lines=[f'{i+1:02d} · {parts[0]}']+parts[1:]
        yy=ly-8*(len(lines)-1)
        names.append(f'<text text-anchor="{anchor}" font-size="14" font-weight="600" fill="#233459" font-family="Segoe UI,Arial">'+''.join(f'<tspan x="{lx:.1f}" y="{yy+17*k:.1f}">{_esc(line)}</tspan>' for k,line in enumerate(lines))+'</text>')
    given=[]
    for i,entry in enumerate(steps):
        if entry.get('level') is None:continue
        try:
            score=float(entry['level'])
        except (TypeError,ValueError):continue
        if not math.isfinite(score) or score<1 or score>5:continue
        given.append((i,score))
    complete=len(given)==10
    shape=''
    if complete:
        shape=f'<polygon points="{coords([xy(i,value) for i,value in given])}" fill="#6C35D42C" stroke="#6334CF" stroke-width="3" stroke-linejoin="round" />'
    elif len(given)>=2:
        for (i,v1),(j,v2) in zip(given,given[1:]):
            a,b=xy(i,v1);c,d=xy(j,v2)
            dash='' if j==i+1 else ' stroke-dasharray="7 6"'
            shape+=f'<line x1="{a:.1f}" y1="{b:.1f}" x2="{c:.1f}" y2="{d:.1f}" stroke="#6633CC" stroke-width="3" stroke-linecap="round"{dash}/>'
        # The polygon is deliberately not closed while evaluations are missing.
    dots=[]
    for i,score in given:
        px,py=xy(i,score);theta=ang(i)
        # Label beside, not on top of, the actual observation.
        tx=px+math.cos(theta)*20;ty=py+math.sin(theta)*20+4
        label=f'{score:.2f}'.replace('.',',')
        dots.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6.5" fill="#6334CF" stroke="white" stroke-width="2.6"><title>Paso {i+1}: {_esc(steps[i].get("short",""))}: {label} / 5</title></circle>')
        dots.append(f'<rect x="{tx-20:.1f}" y="{ty-15:.1f}" width="40" height="21" rx="7" fill="white" stroke="#E5DDF8" stroke-width="1"/>')
        dots.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="14" font-weight="700" fill="#5120B4" text-anchor="middle" font-family="Segoe UI,Arial">{label}</text>')
    footer=('Los diez pasos evaluados · polígono completo' if complete else
            'Los pasos pendientes no tienen puntuación ni vértice · Línea discontinua = conexión entre evaluaciones disponibles')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Radar de diez pasos; cada eje presenta los niveles 1 a 5, puntos con valores y conexiones entre las evaluaciones disponibles. Los pendientes no se puntúan."><rect width="{width}" height="{height}" fill="#fff" />{grid}{axes}{''.join(ticks)}{shape}{''.join(dots)}{''.join(names)}<text x="{cx}" y="706" text-anchor="middle" fill="#65728E" font-size="14" font-family="Segoe UI,Arial">{footer}</text></svg>"""


def _kpis(data):
    stats=[('Pasos evaluados',f"{data['completed']}/10",'Total: 280 preguntas'),
           ('Índice de madurez',_num(data['index'])+' / 5' if data['index'] is not None else '—','Completo' if data['is_final'] else 'Provisional, solo pasos evaluados'),
           ('Cobertura metodológica',str(data['coverage'])+'%','Proporción de pasos evaluados'),
           ('Peso cubierto',str(data['covered_weight'])+'%','De 100% de ponderación')]
    cols=st.columns(4)
    for col,(name,val,foot) in zip(cols,stats):
        with col:
            st.markdown(f'<div class="p8prof-kpi"><div class="label">{_esc(name)}</div><div class="value">{_esc(val)}</div><div class="foot">{_esc(foot)}</div></div>',unsafe_allow_html=True)

def _create_import():
    with st.expander('Crear un perfil o importar un expediente JSON',expanded=not model.profiles()):
        a,b=st.tabs(['Nuevo perfil','Importar expediente'])
        with a:
            with st.form('p8prof_create'):
                name=st.text_input('Nombre del perfil',value='Perfil de madurez de la PMO CENS')
                owner=st.text_input('Responsable de la evaluación',value='Equipo PMO')
                scale=st.selectbox('Método de escala',('zero5','direct'),format_func=lambda k:'CENS: normalizada de 0 a 5' if k=='zero5' else 'Promedio directo PMI: de 1 a 5')
                demo=st.checkbox('Es un ejercicio / contiene datos ficticios',value=False)
                if st.form_submit_button('Crear perfil',type='primary'):
                    pid=_action(lambda:model.create_profile(name,owner,scale,demo),'Perfil creado')
                    if pid:st.session_state['p8prof_active']=pid;st.rerun()
        with b:
            st.caption('Compatible con el formato pmo-cens-pmo-profile-v1 del HTML que compartiste. Importar crea un perfil nuevo y conserva los anteriores.')
            file=st.file_uploader('Expediente JSON del perfil de diez pasos',type='json',key='p8prof_upload')
            name=st.text_input('Nombre del expediente importado',value='Perfil histórico importado')
            owner=st.text_input('Responsable de la importación',value='Equipo PMO')
            demo=st.checkbox('Identificar importación como demostración',value=True)
            if file and st.button('Validar e importar JSON',key='p8prof_import'):
                try:obj=json.loads(file.getvalue())
                except (ValueError,UnicodeError) as ex:st.error('Archivo JSON inválido: '+str(ex));return
                pid=_action(lambda:model.import_json(obj,name,owner,demo),'Expediente importado con trazabilidad')
                if pid:st.session_state['p8prof_active']=pid;st.rerun()
    template={'schema':'pmo-cens-pmo-profile-v1','scale':'zero5','steps':[
        {'step':n,'questionCount':count,'totalScore':None,'answers':[None]*count,
         'weightPercent':10,'source':'','notes':'','evidence':'','desired':None}
         for n,_,_,count in model.STEPS]}
    st.download_button('Descargar plantilla JSON de los diez pasos',_json(template),file_name='CENS_Paso8_Plantilla_Perfil_10_Pasos.json',mime='application/json')
    a,b=st.columns(2)
    with a:
        sample=__import__('pathlib').Path(__file__).parent.parent/'referencias'/'CENS_Paso8_Perfil_10_Pasos_EJEMPLO_FICTICIO.json'
        if sample.exists():st.download_button('Descargar ejemplo ficticio de 10 pasos',sample.read_bytes(),file_name=sample.name,mime='application/json',use_container_width=True)
    with b:
        if st.button('Cargar ejemplo ficticio en un perfil nuevo',use_container_width=True):
            if sample.exists():
                obj=json.loads(sample.read_text(encoding='utf8'))
                pid=_action(lambda:model.import_json(obj,'Laboratorio · Perfil PMI 10 pasos','EVALUADOR FICTICIO',True),'Perfil de laboratorio cargado')
                if pid:st.session_state['p8prof_active']=pid;st.rerun()


def _select():
    available=model.profiles()
    if not available:return None
    mp={x['id']:x for x in available}
    if st.session_state.get('p8prof_active') not in mp:st.session_state['p8prof_active']=available[0]['id']
    pid=st.selectbox('Perfil de madurez',list(mp),format_func=lambda k:f"{mp[k]['nombre']} · {mp[k]['responsable']}"+(' [DEMO]' if mp[k]['es_demo'] else ''),key='p8prof_active')
    return model.report(pid)

def _profile_radar(d):
    st.subheader('Perfil de madurez de los diez pasos')
    st.caption('Las calificaciones ausentes no son cero y no participan en la media. El radar usa un eje 0–5 de referencia.')
    a,b=st.columns([1.12,1])
    with a:
        st.components.v1.html(radar_svg(d['steps']),height=600,scrolling=False)
    with b:
        for s in d['steps']:
            value=s['level'];frac=max(0,100*(value or 0)/5)
            st.markdown(f'''<div class="p8prof-bar"><div class="name">{s['paso']}. {_esc(s['short'])}</div><div class="track"><i style="width:{frac:.1f}%"></i></div><b>{_num(value)}</b></div>''',unsafe_allow_html=True)
    label=('Escala CENS adaptada: (promedio de respuestas − 1) × 1,25. El 1 PMI se ubica en 0 y el 5 PMI en 5.' if d['scale']=='zero5' else 'Promedio directo de respuestas PMI: 1 a 5; el radar conserva el eje visual 0–5.')
    st.info(label+' Este indicador consolidado es una síntesis analítica de CENS y no una fórmula oficial de puntuación global del PMI.')
    st.subheader('Estado de las diez autoevaluaciones')
    st.dataframe(pd.DataFrame([{'Paso':f"{x['paso']:02d} · {x['name']}",'Preguntas':x['count'],
         'Resultado':str(x['puntaje'])+'/'+str(x['max']) if x['puntaje'] is not None else '—',
         'Calificación / 5':round(x['level'],2) if x['level'] is not None else None,
         'Peso (%)':x['peso'],'Origen':x['fuente'] or '—',
         'Estado':'Evaluado' if x['puntaje'] is not None else 'Pendiente'} for x in d['steps']]),hide_index=True,use_container_width=True,height=404)
    if not d['is_final']:st.warning(f"Índice provisional: {10-d['completed']} pasos pendientes. No se declara un perfil global definitivo hasta completar los diez instrumentos.")

def _capture(d):
    pid=d['profile']['id']
    with st.expander('Configurar ponderación y escala',expanded=False):
        with st.form('p8prof_weights'):
            scale=st.selectbox('Método',model.SCALES,index=model.SCALES.index(d['scale']),format_func=lambda x:'Normalizada CENS 0–5' if x=='zero5' else 'Directa PMI 1–5')
            cols=st.columns(5)
            inputs=[]
            for i,x in enumerate(d['steps']):
                with cols[i%5]:inputs.append(st.number_input(f"Paso {x['paso']} (%)",min_value=0,max_value=100,step=1,value=int(x['peso']),key=f'p8prof_w_{pid}_{i}'))
            st.caption('Los diez pesos deben sumar exactamente 100%. Predeterminado: 10% por paso.')
            if st.form_submit_button('Aplicar configuración',type='primary'):
                if _action(lambda:model.save_weights(pid,inputs,scale),'Ponderación y escala guardadas') is not None:st.rerun()
    st.subheader('Consolidar autoevaluaciones PMI finalizadas')
    source_rows=model.available_completed_assessments()
    if source_rows:
        selected=st.selectbox('Evaluación finalizada disponible en nuestra SQLite',range(len(source_rows)),
             format_func=lambda i:f"Paso {source_rows[i]['step']} · {source_rows[i]['score']}/{source_rows[i]['count']*5} · {source_rows[i]['date']} · {source_rows[i]['owner']}",key='p8prof_source')
        item=source_rows[selected]
        current=d['steps'][item['step']-1]
        st.caption('Solo se leen evaluaciones finalizadas. El documento original y su puntuación permanecen intactos.')
        overwrite=st.checkbox('Permitir sustituir la copia de la puntuación de este paso',value=False,key='p8prof_overwrite')
        if st.button('Vincular evaluación finalizada',type='primary',key='p8prof_copy'):
            if _action(lambda:model.sync_completed_assessment(pid,item['step'],item['id'],overwrite),'Puntuación validada de origen vinculada') is not None:st.rerun()
    else:st.caption('No hay instrumentos PMI finalizados en los Pasos 1–7 de la SQLite. Puedes ingresar una evaluación documentada o importar el JSON.')
    st.divider()
    target=st.selectbox('Selecciona el instrumento PMI',range(1,11),format_func=lambda n:f"{n:02d} · {model.STEPS[n-1][1]} · {model.COUNTS[n]} preguntas",key='p8prof_step_select')
    old=d['steps'][target-1]
    mode=st.radio('Modalidad de registro',('Total consolidado','Respuestas individuales'),horizontal=True,key='p8prof_mode')
    st.caption('Los puntajes se registran únicamente desde valoraciones documentadas. No se generan por la existencia de actividades o registros.')
    with st.form('p8prof_answers_'+str(target)+'_'+mode):
        source=st.text_input('Origen de la autoevaluación',value=old['fuente'],help='Acta, instrumento, versión, carpeta o evaluación completada')
        note=st.text_area('Observaciones',value=old['observacion'],height=75)
        evidence=st.text_input('Evidencia o referencia',value=old['evidencia'])
        meta=st.number_input('Meta opcional de madurez (escala 0–5)',min_value=0.0,max_value=5.0,step=0.25,value=float(old['meta'] if old['meta'] is not None else 0),help='0 significa sin meta cuando se desmarca la casilla siguiente')
        enable_meta=st.checkbox('Registrar meta del paso',value=old['meta'] is not None)
        if mode=='Total consolidado':
            has_score=st.checkbox('El instrumento está completamente respondido',value=old['puntaje'] is not None)
            total=st.number_input('Puntaje total verificado',min_value=old['count'],max_value=old['max'],value=int(old['puntaje'] or old['count']),step=1,disabled=not has_score)
            st.caption(f"Escala permitida: {old['count']}–{old['max']} puntos. Para registrar totales se exige identificar el instrumento de origen.")
            payload={'score':total if has_score else None,'answers':None}
        else:
            known=old['answers'] if len(old['answers'])==old['count'] else [None]*old['count']
            ed=pd.DataFrame({'Ítem PMI':[f'Ítem {i+1:02d}' for i in range(old['count'])],
                              'Calificación':known})
            result=st.data_editor(ed,hide_index=True,use_container_width=True,num_rows='fixed',key='p8prof_editor_'+str(target),
               column_config={'Ítem PMI':st.column_config.TextColumn('Ítem PMI',disabled=True),
                              'Calificación':st.column_config.NumberColumn('Calificación (1–5)',min_value=1,max_value=5,step=1)},
               disabled=['Ítem PMI'],height=min(550,max(215,44*old['count'])))
            values=[None if pd.isna(v) else v for v in result['Calificación'].tolist()]
            st.caption(f"Respondidas: {sum(v is not None for v in values)}/{old['count']}. Un instrumento incompleto no produce puntuación definitiva.")
            payload={'score':None,'answers':values}
        if st.form_submit_button('Guardar evaluación del paso',type='primary'):
            if _action(lambda:model.save_step(pid,target,**payload,source=source,note=note,evidence=evidence,target=meta if enable_meta else None),'Evaluación guardada') is not None:st.rerun()

def _history(d):
    pid=d['profile']['id'];hist=model.histories(pid)
    st.subheader('Cortes históricos del perfil')
    if hist:
        ar=[]
        for item in hist:
            snap=json.loads(item['snapshot_json']);ar.append({'Versión':item['version'],'Fecha':item['registrado_en'],
             'Responsable':item['responsable'],'Pasos':snap['completed'],
             'Índice / 5':round(snap['index'],2) if snap['index'] is not None else None,
             'Estado':'Completo' if snap['is_final'] else 'Parcial'})
        st.dataframe(pd.DataFrame(ar),hide_index=True,use_container_width=True)
        ix=st.selectbox('Consultar un corte sin sobrescribir el perfil actual',range(len(hist)),format_func=lambda i:f"V{hist[i]['version']} · {hist[i]['registrado_en']}")
        snap=json.loads(hist[ix]['snapshot_json'])
        st.caption('Comparación con el corte histórico seleccionado')
        st.dataframe(pd.DataFrame([{'Paso':x['name'],'Corte histórico':round(x['level'],2) if x['level'] is not None else None,
            'Perfil actual':round(d['steps'][i]['level'],2) if d['steps'][i]['level'] is not None else None}
            for i,x in enumerate(snap['steps'])]),hide_index=True,use_container_width=True)
    else:st.info('Aún no hay cortes archivados. Cada corte conserva las puntuaciones y ponderaciones vigentes en ese momento.')
    with st.form('p8prof_archive'):
        actor=st.text_input('Responsable del corte',value=d['profile']['responsable'])
        if st.form_submit_button('Guardar corte histórico',type='primary'):
            if _action(lambda:model.snapshot(pid,actor),'Corte histórico guardado sin sobrescribir versiones') is not None:st.rerun()
    st.subheader('Respaldo y restauración específicos del perfil')
    st.download_button('Descargar respaldo JSON de perfiles e historial',_json(model.backup()),file_name='CENS_Paso8_Respaldo_Perfiles.json',mime='application/json')
    with st.expander('Restaurar perfiles desde respaldo JSON'):
        file=st.file_uploader('Archivo de respaldo del perfil',type='json',key='p8prof_restore_file')
        confirmed=st.checkbox('Confirmo que deseo reemplazar solo los perfiles de madurez, no el resto del Paso 8',key='p8prof_restore_confirm')
        if file and st.button('Restaurar perfiles',disabled=not confirmed):
            try:obj=json.loads(file.getvalue())
            except ValueError as ex:st.error(str(ex));return
            if _action(lambda:model.restore(obj,confirmed=confirmed),'Perfiles restaurados correctamente') is not None:
                st.session_state.pop('p8prof_active',None);st.rerun()

def _legacy_page():
    st.markdown('<div class="pmo-eyebrow">PASO 08 · MODELO TRANSVERSAL CENS</div><div class="pmo-title">Perfil de madurez de la PMO</div><div class="pmo-subtitle">Radar de los diez pasos del PMO Value Ring™, construido con sus 280 criterios de autoevaluación. Es complementario al diagnóstico de los 26 servicios.</div>',unsafe_allow_html=True)
    _create_import()
    d=_select()
    if not d:
        st.info('Crea o importa un perfil para comenzar. El índice no se calcula sin autoevaluaciones diligenciadas.');return
    if d['profile']['es_demo']:st.warning('Este perfil contiene datos demostrativos y no representa una valoración institucional de CENS.')
    _kpis(d)
    left,right=st.columns([1,1])
    with left:st.caption('Perfil actual: '+d['profile']['nombre']+' · '+('Normalizada CENS 0–5' if d['scale']=='zero5' else 'Media directa PMI 1–5'))
    with right:
        st.download_button('Exportar perfil completo JSON',_json(model.export_json(d['profile']['id'])),file_name='CENS_Paso8_Perfil_10_Pasos.json',mime='application/json',use_container_width=True)
    a,b,c=st.tabs(['Radar y perfil','Captura de evaluaciones','Historial y metodología'])
    with a:_profile_radar(d)
    with b:_capture(d)
    with c:_history(d)


def _consolidated_pmi_page():
    from . import pmi_flywheel_assessment as unified
    from .ui import kpi
    st.markdown('<div class="pmo-eyebrow">PASO 08 · PERFIL TRANSVERSAL DE AUTOEVALUACIONES</div>'
                '<div class="pmo-title">Perfil de madurez de la PMO</div>'
                '<div class="pmo-subtitle">Radar integrado de las autoevaluaciones metodológicas de los diez pasos del PMO Value Ring™. Cálculo descriptivo CENS basado exclusivamente en evaluaciones guardadas.</div>',unsafe_allow_html=True)
    st.info('El perfil de prácticas de los diez pasos no es la evaluación de madurez de los 26 servicios ni la madurez institucional anual. No constituye una certificación PMI.')
    periods=unified.periods()
    if not periods:
        st.warning('No existen autoevaluaciones del ciclo registradas en el instrumento compartido. Abre «Autoevaluación PMI» en cualquier paso, crea una evaluación y empieza a registrar criterios.')
        st.caption('Las autoevaluaciones históricas creadas en módulos anteriores se conservan sin cambios y pueden consultarse desde los registros legados. No se asumen ni se mezclan automáticamente con un ciclo sin identificación.')
        return
    preferred=st.session_state.get('pmi_profile_period')
    if preferred not in periods:st.session_state['pmi_profile_period']=periods[0]
    period=st.selectbox('Ciclo de autoevaluación',periods,key='pmi_profile_period')
    r=unified.consolidated(period)
    cols=st.columns(4)
    for col,(name,value,description,icon,colour) in zip(cols,[
        ('Pasos finalizados',f"{r['completos']}/10",'Autoevaluaciones completas','file','orange'),
        ('Criterios cubiertos',f"{r['respondidas']}/{r['total']}",'Solo pasos finalizados','file','blue'),
        ('Índice descriptivo',f"{r['indice']:.2f}/5" if r['indice'] is not None else '—','Provisional si faltan pasos','chart','purple'),
        ('Estado','Completo' if r['final'] else 'En construcción','Sin suposiciones ni puntajes de ejemplo','layers','teal')]):
        with col:kpi(name,value,description,icon,colour)
    st.markdown('### Perfil de madurez de los diez pasos')
    st.caption('Cada eje muestra los niveles 1 a 5. Los puntajes aparecen junto a sus puntos; las conexiones discontinuas unen pasos evaluados sin asignar valores a los pendientes.')
    steps=[{'short':unified.STEPS[i],'level':r['pasos'][i]['promedio']} for i in range(10)]
    with st.container(border=True):
        st.markdown('#### Radar de los diez pasos · vista ampliada')
        # Ancho completo; la miniatura a media pantalla recortaba o reducía las etiquetas.
        st.components.v1.html('<div style="max-width:1120px;margin:0 auto;">'+radar_svg(steps)+'</div>',height=740,scrolling=False)
        if not r['final']:
            st.warning(f"Perfil provisional: {10-r['completos']} pasos aún sin evaluación finalizada. Los pasos faltantes no representan nivel cero.")
        else:
            st.success('Los diez pasos tienen instrumentos completos. El índice es una síntesis descriptiva CENS, no una nota oficial PMI.')
    with st.container(border=True):
        st.markdown('#### Desempeño por paso')
        left,right=st.columns(2)
        for i,x in enumerate(r['pasos']):
            score=x['promedio']
            with (left if i<5 else right):
                st.markdown(f'<div class="p8prof-bar"><div class="name">{x["paso"]:02d} · {_esc(x["nombre"])}</div><div class="track"><i style="width:{(score or 0)/5*100:.1f}%"></i></div><b>{_num(score)}</b></div>',unsafe_allow_html=True)
    if r.get('mixed_instruments'):
        st.warning('Este ciclo contiene autoevaluaciones de dos instrumentos: CENS adaptada e instrumento documental de la guía PMI 2025. Los resultados no son directamente comparables pregunta por pregunta; revisa el origen de cada paso.')
    data=[{'Paso':f"{x['paso']:02d} · {x['nombre']}",'Criterios':x['cantidad'],
           'Puntaje':f"{x['puntaje']}/{x['cantidad']*5}" if x['puntaje'] is not None else '—',
           'Media / 5':round(x['promedio'],2) if x['promedio'] is not None else None,
           'Interpretación':x['interpretacion']['label'] if x['interpretacion'] else 'Sin evaluar',
           'Instrumento':unified.instrument_name(x['instrumento']) if x['instrumento'] else '—',
           'Responsable':x['evaluator'],'Finalizada':x['fecha'] or 'Pendiente'} for x in r['pasos']]
    st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True)
    st.caption('Método: promedio simple de las diez medias de paso. Si faltan pasos, media provisional únicamente de los finalizados. Escala de preguntas 1–5, eje radar 0–5. Las respuestas incompletas no contribuyen al índice.')
    st.download_button('Exportar resumen metodológico JSON',_json(r),file_name=f'PMO_CENS_Perfil_Evaluaciones_{period.replace(" ","_")}.json',mime='application/json')


# Punto único de entrada. Streamlit ejecuta el contenido de AMBAS pestañas
# en cada rerun; no debemos volver a invocar page() ni _legacy_page() desde sí misma.
def page():
    primary,archive=st.tabs(['Radar automático de las diez autoevaluaciones','Perfil manual e historial anterior'])
    with primary:_consolidated_pmi_page()
    with archive:
        st.caption('El modelo histórico de perfiles manuales se conserva íntegro para consulta, importación y comparación. No se mezcla automáticamente con las nuevas autoevaluaciones.')
        _legacy_page()
