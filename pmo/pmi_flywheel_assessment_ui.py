"""Autoevaluaciones de diez pasos con guía PMI 2025 e instrumentos históricos versionados."""
from __future__ import annotations
import html,json
import streamlit as st
from . import pmi_flywheel_assessment as ev
from .ui import kpi

def _text(v):return html.escape(str(v if v is not None else ''))
def _call(fn,ok):
 try:
  value=fn();st.success(ok);return value if value is not None else True
 except (ValueError,TypeError,KeyError) as e:st.error(str(e));return None

def page(step:int):
 step=int(step)
 count=ev.COUNTS[step]
 st.markdown(f'<div class="pmo-eyebrow">PASO {step:02d} · AUTOEVALUACIÓN METODOLÓGICA</div>'
             f'<div class="pmo-title">Autoevaluación PMI · Paso {step:02d}</div>'
             f'<div class="pmo-subtitle">{_text(ev.STEPS[step-1])} · {count} preguntas · {len(ev.questions(step))} secciones · escala 1–5 · instrumento versionado.</div>',
             unsafe_allow_html=True)
 st.caption('Cuestionario documental de la guía PMI 2025 en las evaluaciones nuevas; antecedentes CENS con su instrumento original. Esta evaluación no es certificación PMI.')
 all_=ev.list_evaluations(step)
 with st.expander('＋ Nueva autoevaluación',expanded=not all_):
  with st.form(f'pmi_new_{step}'):
   a,b=st.columns(2)
   with a:period=st.text_input('Período o ciclo *',value='Ciclo 01',key=f'pmi_period_new_{step}',help='Usa la misma denominación de ciclo para que las diez evaluaciones se consoliden en el perfil.')
   with b:owner=st.text_input('Responsable de la evaluación *',key=f'pmi_owner_new_{step}')
   demo=st.checkbox('Evaluación de ensayo con datos ficticios',value=False)
   if st.form_submit_button('Crear autoevaluación',type='primary'):
    key=_call(lambda:ev.create(step,period,owner,demo),'Autoevaluación creada')
    if key:st.session_state[f'pmi_selected_{step}']=key;st.rerun()
 legacy=ev.legacy_available(step)
 if legacy:
  with st.expander('Recuperar una evaluación registrada en la versión anterior',expanded=False):
   st.caption('Crea una copia en el nuevo formulario, sin alterar la evaluación ni el expediente original. Comprueba su período y respuestas; los enunciados compartidos son adaptaciones CENS.')
   with st.form(f'pmi_legacy_import_{step}'):
    options={x['id']:x for x in legacy}
    old=st.selectbox('Evaluación anterior',list(options),format_func=lambda key:f"{options[key]['source']} · {options[key]['state']} · {options[key]['owner']} · {str(options[key]['score'] or '—')}")
    period=st.text_input('Período de la copia *',value=options[old]['period'] or 'Ciclo 01')
    actor=st.text_input('Responsable de la incorporación *')
    approved=st.checkbox('Confirmo el período y deseo conservar una copia de la evaluación')
    if st.form_submit_button('Incorporar copia editable',disabled=not approved):
     created=_call(lambda:ev.import_legacy(step,old,period,actor),'Evaluación anterior incorporada sin alterar el original')
     if created:st.session_state[f'pmi_selected_{step}']=created;st.rerun()
 if not all_:
  st.info('Todavía no se han registrado autoevaluaciones de este paso.');return
 opts={e['id']:e for e in all_};key=f'pmi_selected_{step}'
 if st.session_state.get(key) not in opts:st.session_state[key]=all_[0]['id']
 selected=st.selectbox('Evaluación / corte',list(opts),key=key,format_func=lambda eid:(
    f"{opts[eid]['periodo']} · {ev.instrument_name(opts[eid]['instrumento'])} · {opts[eid]['evaluador']} · {opts[eid]['estado']} · V{opts[eid]['version']}"))
 info=ev.detail(selected);responses=info['respuestas']
 original=info['instrumento']==ev.INSTRUMENT
 guide=ev.guide_info(step)
 with st.container(border=True):
  st.markdown('#### Instrucciones y orientación de la autoevaluación')
  st.caption(f"Referencia: PMI, Oficinas de Dirección de Proyectos: Una Guía Práctica (2025), páginas PDF {guide['source_pages'][0]}–{guide['score_page']} · Instrumento: {ev.instrument_name(info['instrumento'])}")
  if original:
   st.markdown(f"**{guide['title']}**")
   st.write(guide['intro'])
   st.markdown('**Instrucciones de calificación**')
   st.write(guide['instructions'])
  else:
   st.warning('Esta evaluación fue creada con las preguntas adaptadas CENS de la versión anterior. Se conserva su redacción original, sus respuestas y su trazabilidad. Para evaluar los enunciados literales de la guía PMI 2025, crea una nueva autoevaluación.')
   st.caption('Los rangos publicados pueden consultarse como referencia, pero no equivalen a una clasificación oficial del cuestionario histórico adaptado.')
  for note in guide['source_discrepancies']:
   st.warning('Nota de fidelidad documental: '+note)
  with st.expander('Consultar los cinco rangos de puntuación y sus orientaciones',expanded=False):
   for band in guide['bands']:
    st.markdown(f"**{band['label']} · {band['min']}–{band['max']} puntos**")
    st.write(band['guidance'])
 interpretation=info['interpretacion']
 a,b,c,d,e=st.columns(5)
 with a:kpi('Respuestas diligenciadas',f"{info['respondidas']}/{count}",'Criterios respondidos','file','orange')
 with b:kpi('Puntuación',f"{info['puntaje']}/{info['maximo']}" if info['puntaje'] is not None else f"— / {info['maximo']}",'Suma total al finalizar','chart','blue')
 with c:kpi('Estado',info['estado'],'Reapertura auditada','check','purple')
 with d:kpi('Interpretación',interpretation['label'] if interpretation else 'Pendiente','Según rango de la guía' if original else 'Referencia, no equivalencia','layers','teal')
 with e:kpi('Secciones',str(info['dimensiones']),'Cinco preguntas por sección','layers','blue')
 st.progress(info['respondidas']/count,text=f"{info['respondidas']}/{count} criterios respondidos")
 st.caption(f"Instrumento: {info['instrumento']} · Período: {info['periodo']} · No se asigna cero a respuestas pendientes")
 if interpretation:
  with st.container(border=True):
   heading=f"Puntuación: {info['puntaje']}/{count*5} · {interpretation['label']}"
   st.markdown('**'+heading+'**')
   if not original:st.warning('Clasificación orientativa con base en los rangos publicados; las preguntas originales de esta evaluación son adaptaciones CENS.')
   if interpretation['discrepancy']:st.warning('El resultado está fuera de los rangos que figuran en la guía. La puntuación se conserva sin asignar una categoría no publicada.')
   st.write(interpretation['guidance'])
 if info['es_demo']:st.warning('Evaluación de ensayo: se excluye del radar institucional.')
 if info['estado']=='Finalizada':
  st.info('Evaluación finalizada. Puedes consultarla o reabrirla justificadamente para corregir valoraciones; se conserva el historial anterior.')
  with st.expander('Reabrir evaluación para editar',expanded=False):
   with st.form(f'pmi_reopen_{selected}'):
    actor=st.text_input('Responsable de la reapertura *',value=info['evaluador'])
    why=st.text_area('Motivo documentado del cambio *',placeholder='Qué valoración se requiere corregir y por qué')
    confirmed=st.checkbox('Confirmo que deseo reabrir esta evaluación')
    if st.form_submit_button('Reabrir evaluación',disabled=not confirmed):
     if _call(lambda:ev.reopen(selected,actor,why),'Evaluación reabierta; revisa las respuestas y vuelve a finalizar'):st.rerun()
 dims=ev.questions(step,info['instrumento'])
 if info['estado']=='Borrador':
  with st.expander('Editar datos de la evaluación',expanded=False):
   with st.form(f'pmi_header_{selected}'):
    period=st.text_input('Período o ciclo *',value=info['periodo'])
    evaluator=st.text_input('Evaluador *',value=info['evaluador'])
    editor=st.text_input('Responsable de la actualización *',value=info['evaluador'])
    if st.form_submit_button('Guardar datos de evaluación'):
     if _call(lambda:ev.update_metadata(selected,period,evaluator,editor),'Datos actualizados con trazabilidad'):st.rerun()
  dimkey=f'pmi_dim_{step}_{selected}'
  colleft,colright=st.columns([0.95,2.05])
  with colleft:
   dimension=st.radio('Dimensiones',list(range(len(dims))),format_func=lambda i:f"{i+1:02d} · {dims[i]['name']}",key=dimkey)
   if st.button('Finalizar evaluación',key=f'pmi_finish_{selected}',disabled=info['respondidas']<count,type='primary'):
    if _call(lambda:ev.complete(selected,info['evaluador']),'Evaluación finalizada. El perfil podrá consultarla automáticamente.'):st.rerun()
  with colright:
   item=dims[dimension];start=sum(len(x['questions']) for x in dims[:dimension])
   st.markdown(f'#### {dimension+1:02d}. {_text(item["name"])}')
   st.caption('Califica según la escala de la guía: 1 = En absoluto/nunca · 2 = Rara vez/deficiente · 3 = A veces/promedio · 4 = A menudo/bien · 5 = Siempre/excelente. Justifica y referencia evidencias cuando corresponda.')
   with st.form(f'pmi_answers_{selected}_{dimension}'):
    actor_save=st.text_input('Responsable del registro *',value=info['evaluador'],key=f'pmi_actor_save_{selected}_{dimension}')
    entries=[]
    for j,question in enumerate(item['questions'],1):
     num=start+j;answer=responses.get(num,{})
     st.markdown(f'**{num:02d}. {_text(question)}**')
     values=('Sin responder',1,2,3,4,5)
     present=answer.get('valor','Sin responder')
     rating=st.selectbox('Valoración',values,index=values.index(present) if present in values else 0,key=f'pmi_rate_{selected}_{num}')
     note=st.text_input('Justificación',value=answer.get('justificacion',''),key=f'pmi_note_{selected}_{num}')
     evidence=st.text_input('Enlace o código de evidencia',value=answer.get('evidencia',''),key=f'pmi_evidence_{selected}_{num}')
     entries.append((rating,note,evidence))
     if j<len(item['questions']):st.divider()
    if st.form_submit_button('Guardar dimensión',type='primary'):
     parsed=[(None if rating=='Sin responder' else int(rating),note,evidence) for rating,note,evidence in entries]
     if _call(lambda:ev.save_dimension(selected,dimension,parsed,actor_save),'Dimensión guardada'):st.rerun()
 else:
  for i,dim in enumerate(dims):
   with st.expander(f'{i+1:02d} · {dim["name"]} · {sum((sum(len(d["questions"]) for d in dims[:i])+j) in responses for j in range(1,len(dim["questions"])+1))}/{len(dim["questions"])}',expanded=False):
    offset=sum(len(x['questions']) for x in dims[:i])
    for j,q in enumerate(dim['questions'],1):
     answer=responses.get(offset+j)
     st.markdown(f'**{offset+j:02d}. {_text(q)}**')
     st.caption(f"Valoración: {answer['valor'] if answer else 'Pendiente'} · Justificación: {_text(answer['justificacion']) if answer else '—'} · Evidencia: {_text(answer['evidencia']) if answer else '—'}")
 with st.expander('Historial de cambios y exportación',expanded=False):
  items=ev.audit(selected)
  if items:st.dataframe([{'Fecha':r['fecha'],'Acción':r['accion'],'Responsable':r['actor'],'Detalle':r['detalle']} for r in items],use_container_width=True,hide_index=True)
  st.download_button('Exportar evaluación y trazabilidad (JSON)',json.dumps(ev.export(selected),ensure_ascii=False,indent=2,default=str),file_name=f'CENS_Autoevaluacion_Paso{step:02d}_{selected[:8]}.json',mime='application/json')
