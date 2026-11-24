"""Streamlit · Paso 3: tres módulos, 25 criterios PMI integrados y datos SQLite.

No altera Paso 2 ni la matriz V5. El lienzo usa un componente local sin CDN.
"""
from __future__ import annotations
from .date_widgets import iso_date_input
import csv
import html
import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from .staff_picker import staff_picker
from .client_picker import choose_client
from . import step3 as s
from .public_codes import code as public_code, next_code as next_public_code
from .step3_export import export_canvas, assessment_radar_svg, assessment_pdf, solutions_pdf
from .step2 import list_diagnostics
from .clients import list_clients
from .ui import kpi as shared_kpi

from .step3_quality import benefit_quality, canvas_quality, solution_quality, quality_summary, context_audit
NAV=['Oportunidades y beneficios','Lienzo y conexiones de valor','Soluciones, validación y hoja de ruta','Autoevaluación PMI']
OLD_NAV=list(s.MODULES)
ALIASES=dict(zip(OLD_NAV,NAV[:3]))
ROOT=Path(__file__).resolve().parent.parent

def apply_step3_theme():
    theme=Path(__file__).resolve().parent/'assets'/'step3_ux.css'
    st.markdown('<style>'+theme.read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
TEMPLATE=ROOT/'plantillas'/'PLANTILLA_PASO3_BENEFICIOS.xlsx'

def esc(v):return html.escape(str(v or ''))

def heading(section,title,description):
    st.markdown(f'<div class="pmo-eyebrow">PASO 03 · PROPUESTA DE VALOR</div><div class="pmo-title">{esc(title)}</div><div class="pmo-subtitle">{esc(description)}</div>',unsafe_allow_html=True)

def metrics(items):
    columns=st.columns(len(items))
    for idx,(c,(label,value,helptext,icon)) in enumerate(zip(columns,items)):
        with c:shared_kpi(label,value,helptext,icon, ('orange','blue','purple','teal')[idx%4])

def go(section):
    st.session_state['pmo_active_p3_page']=section
    st.rerun()

def notice_error(exc):st.error(str(exc))

def _json_button(label,data,name,key=None):
    st.download_button(label,json.dumps(data,ensure_ascii=False,indent=2,default=str).encode('utf-8'),file_name=name,mime='application/json',key=key)

# ----------------------------------- BENEFICIOS -----------------------------------
BEN_HEADERS=('Necesidad (condición actual insatisfecha)','Entregable (Output – Salida)',
             'Beneficio (Outcome – Resultado)','Métrica de beneficio','Valor generado','Tipo de valor')
XL_MAP={
 'necesidad':['necesidad (condición actual insatisfecha)','necesidad','problema','pain'],
 'entregable':['entregable (output – salida)','entregable (output - salida)','entregable','output'],
 'beneficio':['beneficio (outcome – resultado)','beneficio (outcome - resultado)','beneficio','outcome'],
 'metrica':['métrica de beneficio','metrica de beneficio','indicador','métrica'],
 'valor':['valor generado','valor','impacto esperado'],
 'tipo_valor':['tipo de valor','tipo_valor'],
 'linea_base':['línea base','linea base'], 'meta':['meta'],
 'medicion':['estado del beneficio','medición','medicion'],
 'estado':['estado de validación','estado'], 'evidencia':['evidencia','fuente de evidencia'],
 'cliente':['cliente'], 'dependencia':['dependencia'],
 'resultado_id':['resultado_id','resultado esperado id'],
 'servicios_json':['servicios_json','servicios pm i'],
 'responsable':['responsable']
}

def parse_excel(file)->list[dict]:
    if file.name.lower().endswith('.csv'):
        raw=file.getvalue().decode('utf-8-sig')
        import csv as _csv
        dialect=_csv.Sniffer().sniff(raw[:3000],delimiters=',;\t') if raw.strip() else _csv.excel
        data=pd.read_csv(io.StringIO(raw),sep=dialect.delimiter,dtype=str)
    else:data=pd.read_excel(io.BytesIO(file.getvalue()),dtype=str,sheet_name=0)
    data=data.fillna('')
    mapping={}
    def norm(v):
        import unicodedata
        t=unicodedata.normalize('NFKD',str(v).lower())
        return ''.join(c for c in t if not unicodedata.combining(c) and c.isalnum())
    for dest,aliases in XL_MAP.items():
        match=next((col for col in data.columns if norm(col) in {norm(a) for a in aliases}),None)
        if match is not None:mapping[dest]=match
    if 'necesidad' not in mapping:raise s.ValidationError('Excel debe contener la columna «Necesidad (condición actual insatisfecha)».')
    records=[]
    for rownum,(_,row) in enumerate(data.iterrows(),2):
        record={key:str(row[col]).strip() for key,col in mapping.items()}
        if not any(v for v in record.values()):continue
        if not record.get('necesidad'):raise s.ValidationError(f'Fila {rownum}: necesidad vacía.')
        records.append(record)
    if not records:raise s.ValidationError('El Excel no contiene filas de necesidades.')
    return records

def export_excel(rows):
    out=io.BytesIO();headers=list(BEN_HEADERS)+['Línea base','Meta','Estado del beneficio','Estado de validación','Cliente','Dependencia','Resultado esperado ID','Evidencia','ID origen','Versión Paso 2']
    body=[]
    for r in rows:
        body.append([r.get(k,'') for k in ('necesidad','entregable','beneficio','metrica','valor','tipo_valor',
                                         'linea_base','meta','medicion','estado','cliente','dependencia','resultado_id',
                                         'evidencia','necesidad_origen','version_origen')])
    with pd.ExcelWriter(out,engine='openpyxl') as writer:
        pd.DataFrame(body,columns=headers).to_excel(writer,index=False,sheet_name='Beneficios')
        ws=writer.sheets['Beneficios'];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        from openpyxl.styles import PatternFill,Font,Alignment
        for cell in ws[1]:cell.fill=PatternFill('solid',fgColor='302B56');cell.font=Font(color='FFFFFF',bold=True)
        for col in ws.columns:
            letter=col[0].column_letter
            ws.column_dimensions[letter].width=35 if col[0].column<=4 else 22
    return out.getvalue()

def export_csv(rows):
    buf=io.StringIO();keys=['id','necesidad','entregable','beneficio','metrica','linea_base','meta','valor','tipo_valor','medicion','estado','dependencia','cliente','necesidad_origen']
    writer=csv.DictWriter(buf,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    return ('\ufeff'+buf.getvalue()).encode('utf-8')

@st.dialog('Ficha de necesidad, entrega y beneficio',width='large')
def benefit_dialog(key=None):
    original=s.benefit(key) if key else {}
    original=original or {}
    linked=bool(original.get('diagnostico_origen') and original.get('necesidad_origen'))
    if linked:
        st.info('Necesidad vinculada del Paso 02. Su descripción, cliente, dependencia y resultado esperado se consultan aquí sin reescribir el diagnóstico original.')
        st.caption(f"Diagnóstico: {original.get('diagnostico_origen')} · Necesidad: {original.get('necesidad_origen')} · Versión: {original.get('version_origen') or '—'}")
    with st.form('p3_form_beneficio'):
        a,b=st.columns(2)
        with a:need=st.text_area('Necesidad de origen *',value=original.get('necesidad',''),height=90,disabled=linked)
        with b:output=st.text_area('Entregable (Output – Salida)',value=original.get('entregable',''),height=90)
        benefit=st.text_area('Beneficio (Outcome – Resultado)',value=original.get('beneficio',''),height=80)
        a,b=st.columns(2)
        with a:
            metric=st.text_input('Métrica de beneficio',value=original.get('metrica',''))
            baseline=st.text_input('Línea base',value=original.get('linea_base',''))
        with b:
            target=st.text_input('Meta',value=original.get('meta',''))
            value=st.text_input('Valor generado (solo si está sustentado)',value=original.get('valor',''))
        a,b,c=st.columns(3)
        with a:vt=st.selectbox('Tipo de valor',s.VALUE_TYPES,index=s.VALUE_TYPES.index(original.get('tipo_valor','Por definir')))
        with b:measurement=st.selectbox('Beneficio',s.BENEFIT_STATES,index=s.BENEFIT_STATES.index(original.get('medicion','Esperado')))
        with c:status=st.selectbox('Estado de validación',s.STATES,index=s.STATES.index(original.get('estado','Borrador')))
        a,b=st.columns(2)
        with a:
            client=st.text_input('Cliente destinatario',value=original.get('cliente',''),disabled=True) if linked else choose_client(st,'Cliente destinatario · Paso 01',original.get('cliente',''),key=f'p3_benefit_client_{key or "new"}')[0]
            dept=st.text_input('Dependencia',value=original.get('dependencia',''),disabled=linked)
        with b:
            outcome=st.number_input('Resultado esperado del Paso 2 (0 = sin asociar)',min_value=0,max_value=30,value=int(original.get('resultado_id') or 0),step=1,disabled=linked)
            evidence=st.text_input('Fuente o evidencia',value=original.get('evidencia',''))
        owner=staff_picker('Responsable *',value=original.get('responsable','') or 'Equipo PMO')
        saved=st.form_submit_button('Guardar beneficio',type='primary')
    if saved:
        try:
            data=dict(original,necesidad=need,entregable=output,beneficio=benefit,metrica=metric,
                      linea_base=baseline,meta=target,valor=value,tipo_valor=vt,medicion=measurement,
                      estado=status,cliente=client,dependencia=dept,resultado_id=outcome or None,
                      evidencia=evidence,responsable=owner)
            s.save_benefit(data,owner,key)
            st.rerun()
        except (ValueError,Exception) as exc:notice_error(exc)

def _needs_table(rows):
    return pd.DataFrame([{
        'Necesidad':r['necesidad'],'Entregable':r['entregable'] or 'Pendiente',
        'Beneficio esperado':r['beneficio'] or 'Pendiente','Métrica':r['metrica'] or 'Pendiente',
        'Valor':r['valor'] or '—','Tipo':r['tipo_valor'],
        'Medición':r['medicion'],'Estado':r['estado'],
        'Fuente':r['necesidad_origen'] or 'Registro propio',
    } for r in rows])

def benefits_page():
    heading('01','Oportunidades y beneficios','Necesidades vinculadas del Paso 02 y formulación del entregable, beneficio e indicador candidato, sin doble captura.')
    all_rows=s.benefits()
    overview=quality_summary()
    st.caption(f"Recorrido de valor: {overview['origen_p2']} necesidades vinculadas al Paso 02 · {overview['lienzos_con_conexiones']}/{overview['lienzos']} lienzos con conexiones · {overview['soluciones_listas']} soluciones aptas según requisitos históricos de transferencia.")
    with st.expander('Verificar base activa y orígenes antes de importar',expanded=False):
        from .config import database_path
        active=context_audit()
        st.caption('Base de datos en uso: '+str(database_path()))
        st.caption('Esta auditoría es de solo lectura. No se mezclan datos del taller con el Ciclo 01 automáticamente.')
        st.json({'Necesidades por diagnóstico':active['necesidades_por_origen'],
                 'Lienzos por origen':active['lienzos_por_origen'],
                 'Soluciones sin necesidad ni lienzo':len(active['soluciones_sin_necesidad_ni_lienzo']),
                 'Soluciones con referencias de diagnósticos diferentes':len(active['soluciones_con_origenes_conflictivos'])},expanded=False)
        if active['soluciones_con_origenes_conflictivos']:
            st.warning('Existen soluciones que vinculan una necesidad y un lienzo de orígenes diferentes. Revísalas antes de validar una nueva transferencia.')
            st.dataframe(pd.DataFrame(active['soluciones_con_origenes_conflictivos']),hide_index=True,use_container_width=True)

    a,b,c=st.columns([3,1,1])
    with a:st.caption('Las metas y los beneficios esperados no representan resultados ya materializados.')
    with b:
        if st.button('Importar Paso 2',use_container_width=True):st.session_state['p3_import_p2']=not st.session_state.get('p3_import_p2',False)
    with c:
        if st.button('＋ Nuevo registro',type='primary',use_container_width=True):benefit_dialog()
    if st.session_state.get('p3_import_p2'):
        with st.container(border=True):
            st.subheader('Importar desde el Paso 2')
            mode=st.radio('Origen',['Base de datos compartida','Expediente JSON exportado'],horizontal=True,key='p3_import_mode')
            if mode.startswith('Base'):
                diagnostics=list_diagnostics()
                if not diagnostics:st.info('No hay diagnósticos en el Paso 2. Registra uno allí primero.')
                else:
                    opts={f"{d['nombre']} · {d['ciclo']} · {d['id'][:8]}":d['id'] for d in diagnostics}
                    choice=st.selectbox('Diagnóstico de origen',list(opts))
                    selected=opts[choice]
                    from . import step2
                    need_rows=step2.needs(selected)
                    chosen=st.multiselect('Selecciona las necesidades que deseas transferir',
                        options=[n['id'] for n in need_rows],default=[n['id'] for n in need_rows],
                        format_func=lambda x:next((n['problema'][:90] for n in need_rows if n['id']==x),x))
                    owner=st.text_input('Responsable',value='Equipo PMO',key='p3_direct_owner')
                    if st.button('Vincular necesidades seleccionadas',type='primary'):
                        try:
                            result=s.import_step2_direct(selected,owner,chosen)
                            st.success(f"{result['nuevos']} necesidades vinculadas; {result['omitidos']} ya existentes. Matriz de referencia: {result['version_matriz'] or 'No registrada'}.")
                            st.rerun()
                        except Exception as ex:notice_error(ex)
            else:
                up=st.file_uploader('Expediente JSON del Paso 2',type=['json'],key='p3_p2_json')
                if up:
                    try:
                        payload=json.loads(up.getvalue().decode('utf-8-sig'))
                        preview=s.preview_step2_json(payload)
                        st.write(preview)
                        _,needd=s._extract_p2(payload)
                        chosen=st.multiselect('Necesidades a importar',[n.get('id') or n.get('codigo') for n in needd],
                                              default=[n.get('id') or n.get('codigo') for n in needd],
                                              format_func=lambda x:next((str(n.get('problema') or n.get('pain') or n.get('necesidad') or '')[:70] for n in needd if (n.get('id') or n.get('codigo'))==x),str(x)))
                        owner=st.text_input('Responsable de importación',value='Equipo PMO',key='p3_json_owner')
                        if st.button('Confirmar importación de JSON',type='primary'):
                            result=s.import_step2_json(payload,up.name,owner,chosen)
                            st.success(f"{result['nuevos']} necesidades importadas; {result['omitidos']} duplicadas omitidas.")
                            st.rerun()
                    except Exception as ex:notice_error(ex)
    metrics([
       ('Necesidades registradas',len(all_rows),'Registros de la matriz','▦'),
       ('Beneficios formulados',sum(bool(r['beneficio']) and bool(r['entregable']) for r in all_rows),'Con beneficio y entregable propuesto','◎'),
       ('Métricas documentadas',sum(bool(r['metrica']) for r in all_rows),'Con indicador de beneficio','⌁'),
       ('Con soporte',sum(bool(r['evidencia']) for r in all_rows),'Referencia; no implica validación','▤'),
       ('Registros validados',sum(r['estado'] in ('Validada','Aprobada') for r in all_rows),'Revisión registrada','✓'),
    ])
    with st.container(border=True):
        st.markdown('#### Matriz de necesidad → entregable → beneficio')
        bar=st.columns([3,1,1])
        with bar[0]:search=st.text_input('Buscar',placeholder='Necesidad, beneficio, cliente o dependencia',label_visibility='collapsed')
        with bar[1]:vt=st.selectbox('Tipo',('Todos',)+s.VALUE_TYPES,label_visibility='collapsed')
        with bar[2]:status=st.selectbox('Validación',('Todos',)+s.STATES,label_visibility='collapsed')
        filtered=[r for r in all_rows if (vt=='Todos' or r['tipo_valor']==vt) and (status=='Todos' or r['estado']==status)
                  and search.lower() in ' '.join(str(r.get(k) or '') for k in ('necesidad','beneficio','cliente','dependencia')).lower()]
        if filtered:
            st.dataframe(_needs_table(filtered),hide_index=True,use_container_width=True,height=min(480,50+len(filtered)*40))
            selection=st.selectbox('Registro a revisar o editar',[r['id'] for r in filtered],
                format_func=lambda x:next((r['necesidad'][:90] for r in filtered if r['id']==x),x))
            a,b=st.columns([1,3])
            with a:
                if st.button('Editar ficha',use_container_width=True):benefit_dialog(selection)
            with b:
                with st.popover('Eliminar registro'):
                    st.warning('Eliminación irreversible; los registros asociados a soluciones o lienzos estarán protegidos.')
                    if st.button('Confirmar eliminación',key='p3_del_benefit'):
                        try:s.delete_benefit(selection,'Equipo PMO');st.rerun()
                        except Exception as ex:notice_error(ex)
        else:st.info('No hay registros que coincidan. Puedes importar necesidades del Paso 2 o crear una ficha.')
        a,b,c,d=st.columns(4)
        with a:
            if TEMPLATE.exists():st.download_button('Plantilla Excel',TEMPLATE.read_bytes(),'PMO_CENS_Paso3_Plantilla_Beneficios.xlsx')
        with b:st.download_button('Exportar Excel',export_excel(all_rows),'PMO_CENS_P3_Beneficios.xlsx')
        with c:st.download_button('Exportar CSV',export_csv(all_rows),'PMO_CENS_P3_Beneficios.csv','text/csv')
        with d:_json_button('Exportar JSON',{'schema':'PMO-CENS-P3-BENEFICIOS-v1','registros':all_rows,'fuentes':s.sources()},'PMO_CENS_P3_Beneficios.json')
    with st.expander('Importar Excel o CSV de beneficios (opcional)',expanded=False):
        up=st.file_uploader('Seleccionar plantilla diligenciada',type=['xlsx','csv'],key='p3_excel_ben')
        if up:
            try:
                preview=parse_excel(up)
                st.caption(f'{len(preview)} registros detectados')
                st.dataframe(pd.DataFrame(preview[:15]),hide_index=True,use_container_width=True)
                owner=st.text_input('Responsable de carga',value='Equipo PMO',key='p3_excel_owner')
                if st.button('Importar registros de Excel',type='primary'):
                    n=s.import_benefit_rows(preview,owner)
                    st.success(f'Se importaron {n} registros.');st.rerun()
            except Exception as ex:notice_error(ex)
    source_list=s.sources()
    with st.expander('Trazabilidad del Paso 2 y control metodológico'):
        if source_list:st.dataframe(pd.DataFrame(source_list),hide_index=True,use_container_width=True)
        else:st.caption('Todavía no se ha importado un diagnóstico del Paso 2.')
        st.info('La matriz V5 no se recalcula en el Paso 3. Los estados originales de necesidades se conservan separados de la aprobación de nuevas soluciones.')
    if st.button('Continuar → Lienzo y conexiones de valor',key='p3_continue_to_canvas'):
        go(NAV[1])
    st.caption('Autoevaluación PMI del Paso 03: utiliza el acceso independiente del menú lateral. Las evaluaciones históricas permanecen conservadas.')

# -------------------------------- LIENZO ------------------------------------
@st.dialog('Tarjeta del lienzo',width='large')
def card_dialog(lienzo,key=None,zone=None):
    old=next((c for c in s.cards(lienzo) if c['id']==key),{}) if key else {}
    with st.form('p3_card_form'):
        title=st.text_input('Título de la tarjeta *',value=old.get('titulo',''))
        z=st.selectbox('Sección del lienzo',list(s.ZONES),index=list(s.ZONES).index(old.get('zona',zone or 'dolores')),format_func=s.ZONES.get)
        detail=st.text_area('Descripción y justificación',value=old.get('detalle',''))
        records=s.benefits();opts={'Sin relación directa':None}
        opts.update({f"{r['necesidad'][:75]} · {r['id'][:7]}":r['id'] for r in records})
        ix=next((i for i,(n,v) in enumerate(opts.items()) if v==old.get('beneficio_id')),0)
        chosen=st.selectbox('Vincular con necesidad/beneficio (opcional)',list(opts),index=ix)
        ref=st.text_input('Referencia de origen',value=old.get('referencia',''))
        submit=st.form_submit_button('Guardar tarjeta',type='primary')
    if submit:
        try:s.save_card(lienzo,z,title,detail,opts[chosen],actor='Equipo PMO',key=key,reference=ref);st.rerun()
        except Exception as ex:notice_error(ex)

@st.dialog('Vincular tarjetas',width='large')
def link_dialog(lienzo):
    cs=s.cards(lienzo)
    if len(cs)<2:st.warning('Crea al menos dos tarjetas antes de vincularlas.');return
    options={f"{s.ZONES[c['zona']]}: {c['titulo']} · {c['id'][:6]}":c['id'] for c in cs}
    a,b=st.columns(2)
    with a:origin=st.selectbox('Tarjeta origen',list(options))
    with b:dest=st.selectbox('Tarjeta destino',list(options),index=min(1,len(options)-1))
    note=st.text_area('Justificación del vínculo')
    if st.button('Guardar conexión',type='primary'):
        try:s.create_link(lienzo,options[origin],options[dest],note,'Equipo PMO');st.rerun()
        except Exception as ex:notice_error(ex)

@st.dialog('Nuevo lienzo de propuesta de valor')
def canvas_dialog(clone=None):
    with st.form('p3_new_canvas'):
        segment=choose_client(st,'Cliente del Paso 01 / segmento *',(s.canvas(clone) or {}).get('segmento','') if clone else '',key=f'p3_canvas_segment_{clone or "new"}')[0]
        name=st.text_input('Nombre del lienzo')
        owner=staff_picker('Responsable *',value='Equipo PMO')
        origin=st.text_input('Diagnóstico de origen (si aplica)',value=(s.canvas(clone) or {}).get('diagnostico_origen','') if clone else '')
        saved=st.form_submit_button('Crear versión del lienzo',type='primary')
    if saved:
        try:
            key=s.create_canvas(segment,owner,name,origin,clone)
            st.session_state['p3_current_canvas']=key
            st.rerun()
        except Exception as ex:notice_error(ex)

def _canvas_component(key,card_data,link_data):
    from streamlit.components.v1 import declare_component
    root=Path(__file__).resolve().parent/'components'/'canvas'
    cmp=declare_component('pmo_cens_canvas_step3',path=str(root))
    info=s.canvas(key) or {}
    event=cmp(cards=card_data,links=link_data,title=str(info.get('nombre') or ''),
              segment=str(info.get('segmento') or ''),key=f'p3_cmp_{key}',default=None)
    if event and isinstance(event,dict) and event.get('nonce')!=st.session_state.get('p3_cmp_last'):
        st.session_state['p3_cmp_last']=event['nonce']
        try:
            if event.get('type')=='move':s.move_card(event['card_id'],event['zone'],'Equipo PMO')
            elif event.get('type')=='link':s.create_link(key,event['origin'],event['destination'],'Conexión interactiva','Equipo PMO')
            else:return
            st.rerun()
        except Exception as ex:notice_error(ex)

def canvas_page():
    heading('02','Lienzo y conexiones de valor','Relaciona los dolores del cliente con aliviadores, capacidades y beneficios; las conexiones requieren confirmación.')
    st.caption('Cloud: la carga del taller institucional no está habilitada. Crea lienzos ficticios.')
    all_canvases=s.canvases()
    a,b=st.columns([4,1])
    with a:
        if all_canvases:
            canv_map={f"{x['segmento']} · Versión {x['version']} · {x['nombre']}":x['id'] for x in all_canvases}
            initial=next((i for i,x in enumerate(canv_map.values()) if x==st.session_state.get('p3_current_canvas')),0)
            selected=st.selectbox('Cliente o grupo y versión del lienzo',list(canv_map),index=initial)
            key=canv_map[selected]
            st.session_state['p3_current_canvas']=key
        else:
            key=None;st.info('Crea tu primer lienzo para un cliente o grupo de interesados.')
    with b:
        if st.button('＋ Nuevo lienzo',type='primary',use_container_width=True):canvas_dialog()
    if not key:
        return
    a,b,c=st.columns([1,1,4])
    with a:
        if st.button('Nueva versión',use_container_width=True):canvas_dialog(key)
    with b:
        if st.button('＋ Tarjeta',use_container_width=True):card_dialog(key)
    cs=s.cards(key);ls=s.links(key)
    quality=canvas_quality(key)
    cov=quality['cobertura_pct']
    st.caption(f"Cobertura de dolores: {quality['atendidos']}/{quality['dolores']} ({str(cov)+'%' if cov is not None else 'sin dolores registrados'}) · Conexiones: {quality['conexiones']}. Las relaciones no se crean automáticamente.")
    with st.expander('Conectar dolores con aliviadores o productos · asistente guiado',expanded=bool(quality['pendientes']) and len(cs)>1):
        pending=quality['pendientes']
        if not pending:
            st.success('No hay dolores pendientes de conexión explícita con aliviadores o productos.')
        else:
            candidates=[c for c in cs if c['zona'] in ('aliviadores','servicios')]
            if not candidates:st.info('Primero registra una tarjeta de aliviador o producto/servicio.')
            else:
                p=st.selectbox('Dolor sin relación',[x['id'] for x in pending],format_func=lambda x:next(t['titulo'] for t in pending if t['id']==x),key=f'p3_guided_pain_{key}')
                t=st.selectbox('Aliviador o producto que lo atiende',[x['id'] for x in candidates],format_func=lambda x:next(f"{s.ZONES[t['zona']]} · {t['titulo']}" for t in candidates if t['id']==x),key=f'p3_guided_solution_{key}')
                reason=st.text_input('Cómo contribuye a resolver el dolor',placeholder='Describir el mecanismo de valor, no solo seleccionar tarjetas',key=f'p3_guided_reason_{key}')
                if st.button('Guardar relación de valor',disabled=not bool(reason.strip()),type='primary',key=f'p3_guided_save_{key}'):
                    try:s.create_link(key,p,t,reason,'Equipo PMO');st.rerun()
                    except Exception as ex:notice_error(ex)
    try:_canvas_component(key,cs,ls)
    except Exception as ex:
        st.warning('Vista interactiva no disponible. Las tarjetas pueden crearse y moverse con el formulario inferior.')
        for label,zone in s.ZONES.items():st.markdown(f'**{zone}:** '+', '.join(c['titulo'] for c in cs if c['zona']==label))
    from .alpha03_studio import render_canvas
    render_canvas(key,cs,ls)
    a,b,c=st.columns([1,1,2])
    with a:
        if st.button('Conectar tarjetas',use_container_width=True):link_dialog(key)
    with b:
        st.download_button('Exportar PNG',export_canvas(key,'PNG'),f'PMO_CENS_Lienzo_{key[:8]}.png',mime='image/png',use_container_width=True)
    with c:
        aa,bb=st.columns(2)
        with aa:st.download_button('Exportar PDF',export_canvas(key,'PDF'),f'PMO_CENS_Lienzo_{key[:8]}.pdf',mime='application/pdf',use_container_width=True)
        with bb:st.download_button('Exportar JSON',s.canvas_export_json(key).encode('utf-8'),f'PMO_CENS_Lienzo_{key[:8]}.json',mime='application/json',use_container_width=True)
    coverage=s.canvas_coverage(key)
    metrics([('Tarjetas',len(cs),'Seis áreas del lienzo','▦'),('Conexiones',len(ls),'Relaciones persistidas','⌁'),
             ('Dolores sin atender',coverage['sin_atender'],'Sin vínculo registrado','◎'),
             ('Servicios sin necesidad',coverage['soluciones_sin_necesidad'],'Pendiente de correspondencia','▣')])
    with st.expander('Gestionar tarjetas y conexiones'):
        if cs:
            idmap={f"{c['zona']} · {c['titulo']} · {c['id'][:7]}":c['id'] for c in cs}
            selected=st.selectbox('Tarjeta',list(idmap))
            card_id=idmap[selected]
            a,b,c=st.columns(3)
            with a:
                if st.button('Editar / mover',use_container_width=True):card_dialog(key,card_id)
            with b:
                with st.popover('Eliminar tarjeta'):
                    if st.button('Confirmar eliminación',key='p3_delete_card'):
                        try:s.remove_card(card_id,'Equipo PMO');st.rerun()
                        except Exception as ex:notice_error(ex)
            with c:
                if st.button('Añadir vínculo',use_container_width=True):link_dialog(key)
        if ls:
            st.dataframe(pd.DataFrame([{'Origen':next((c['titulo'] for c in cs if c['id']==l['origen_id']),'?'),
                'Destino':next((c['titulo'] for c in cs if c['id']==l['destino_id']),'?'),
                'Justificación':l['justificacion']} for l in ls]),hide_index=True,use_container_width=True)
            choices={f"{l['origen_id'][:6]} ↔ {l['destino_id'][:6]}":l['id'] for l in ls}
            which=st.selectbox('Conexión registrada',list(choices))
            with st.popover('Eliminar vínculo'):
                if st.button('Confirmar',key='p3_delete_link'):
                    try:s.remove_link(choices[which],'Equipo PMO');st.rerun()
                    except Exception as ex:notice_error(ex)
    with st.expander('Importar datos existentes del Módulo 1 para crear tarjetas'):
        existing=s.benefits();source_ids={c['beneficio_id'] for c in cs if c['beneficio_id']}
        remaining=[r for r in existing if r['id'] not in source_ids]
        if remaining:
            selected=st.multiselect('Beneficios / necesidades', [r['id'] for r in remaining],
                format_func=lambda rid:next((r['necesidad'][:85] for r in remaining if r['id']==rid),rid))
            if st.button('Crear tarjetas de dolores y ganancias',type='primary'):
                try:
                    for rid in selected:
                        r=next(q for q in remaining if q['id']==rid)
                        s.save_card(key,'dolores',r['necesidad'],r['dependencia'],rid,'Equipo PMO')
                        if r['beneficio']:s.save_card(key,'ganancias',r['beneficio'],r['metrica'],rid,'Equipo PMO')
                    st.rerun()
                except Exception as ex:notice_error(ex)
        else:st.caption('No hay registros pendientes. Crea o importa necesidades en la matriz de beneficios.')
    with st.expander('Borrador de declaración de valor'):
        with st.form('p3_value_statement'):
            client=choose_client(st,'Cliente destinatario · Paso 01',s.canvas(key)['segmento'],key=f'p3_statement_{key}')[0]
            need=st.text_input('Necesidad identificada')
            sol=st.text_input('Solución propuesta')
            cap=st.text_input('Capacidad aportada por la PMO')
            benefit=st.text_input('Beneficio esperado')
            submit=st.form_submit_button('Crear declaración editable',type='primary')
        if submit:
            try:s.save_statement(key,client,need,sol,cap,benefit,'Equipo PMO');st.rerun()
            except Exception as ex:notice_error(ex)
        for statement in s.statements(key):st.info(statement['declaracion']+' · Borrador sujeto a revisión')
    if st.button('Continuar → Soluciones y validación',key='p3_continue_to_solutions'):go(NAV[2])

# ---------------------------- SOLUCIONES ------------------------------
@st.dialog('Ficha simplificada de solución',width='large')
def solution_dialog(key=None):
    old=s.solution(key) if key else {}
    old=old or {}
    needs=s.benefits();options={'Sin vincular':None}
    options.update({f"{r['necesidad'][:80]} · {r['id'][:6]}":r['id'] for r in needs})
    selected_idx=next((i for i,v in enumerate(options.values()) if v==old.get('necesidad_id')),0)
    with st.form('p3_solution_form'):
        a,b=st.columns([1,2])
        with a:
            st.text_input('Código consecutivo',value=public_code('solucion',key) if key else next_public_code('solucion'),disabled=True)
            code=old.get('codigo') or next_public_code('solucion')
        with b:name=st.text_input('Nombre de la solución *',value=old.get('nombre',''))
        client=choose_client(st,'Cliente o grupo destinatario · Paso 01',old.get('cliente',''),key=f'p3_solution_client_{key or "new"}')[0]
        need=st.selectbox('Necesidad principal vinculada',list(options),index=selected_idx)
        try:prior_needs=json.loads(old.get('necesidades_json') or '[]')
        except (TypeError,ValueError):prior_needs=[]
        additional_needs=st.multiselect('Otras necesidades relacionadas (opcional)',
             [name for name in options if options[name] is not None],
             default=[name for name,value in options.items() if value in prior_needs])
        a,b=st.columns(2)
        with a:
            decision=st.selectbox('Decisión de diseño *',s.DECISIONS,index=s.DECISIONS.index(old.get('decision','Adoptar')))
            status=st.selectbox('Estado',s.STATES,index=s.STATES.index(old.get('estado','Borrador')))
        with b:
            horizon=st.selectbox('Horizonte',s.HORIZONS,index=s.HORIZONS.index(old.get('horizonte','Desarrollo posterior')))
            period=st.text_input('Periodo configurable',value=old.get('periodo',''))
        detail=st.text_area('Descripción del concepto',value=old.get('descripcion',''))
        selected_need=next((r for r in needs if r['id']==options[need]),None) if options[need] else None
        if selected_need:
            st.caption('Beneficio declarado en la matriz de origen (solo lectura): '+(selected_need.get('beneficio') or 'Aún no formulado'))
        benefit=st.text_area('Contribución específica de esta solución al beneficio',
                             value=old.get('beneficio','') or (selected_need or {}).get('beneficio',''),
                             help='Define el valor atribuible a esta solución. No sustituye el beneficio original de la matriz.')
        metric=st.text_input('Indicador de beneficio',value=old.get('metrica',''))
        raw_service=old.get('servicios_json') or '[]'
        try:initial_service=', '.join(str(n) for n in json.loads(raw_service))
        except Exception:initial_service=str(raw_service)
        service=st.text_input('Servicios PMI de origen (IDs 1–26 separados por coma)',value=initial_service)
        st.caption('Viabilidad orientativa adaptada CENS, distinta de la autoevaluación PMI. Una puntuación alta es más favorable.')
        columns=st.columns(4)
        scores={}
        for i,(field,title) in enumerate([('impacto','Impacto esperado'),('capacidad','Capacidad disponible'),('recursos','Suficiencia de recursos'),('facilidad','Facilidad de implementación')]):
            with columns[i]:
                vals=['Sin evaluar',1,2,3,4,5];idx=vals.index(old.get(field)) if old.get(field) in vals else 0
                sc=st.selectbox(title,vals,index=idx);scores[field]=None if sc=='Sin evaluar' else sc
        st.markdown('**Validación del cliente y control del compromiso**')
        a,b=st.columns(2)
        with a:
            val_name=choose_client(st,'Cliente o representante validador · Paso 01',old.get('validador',''),key=f'p3_solution_validator_{key or "new"}')[0]
            val_date=iso_date_input('Fecha de validación',old.get('fecha_validacion',''))
        with b:
            val_ev=st.text_input('Evidencia de validación / aprobación',value=old.get('evidencia_validacion',''))
            owner=staff_picker('Responsable',value=old.get('responsable','') or 'Equipo PMO')
        obs=st.text_area('Observaciones de validación',value=old.get('observaciones_validacion',''))
        risk=st.text_input('Riesgos del valor comprometido',value=old.get('riesgo',''))
        submitted=st.form_submit_button('Guardar solución',type='primary')
    if submitted:
        try:
            service_ids=[]
            for entry in service.split(','):
                if entry.strip():
                    x=int(entry.strip())
                    if not 1<=x<=26:raise s.ValidationError('Servicios PMI deben estar entre 1 y 26.')
                    service_ids.append(x)
            payload=dict(old,codigo=code,nombre=name,cliente=client,decision=decision,estado=status,
                         necesidad_id=options[need],descripcion=detail,beneficio=benefit,metrica=metric,
                         servicios_json=service_ids,necesidades_json=[options[name] for name in additional_needs],
                         horizonte=horizon,periodo=period,riesgo=risk,
                         validador=val_name,fecha_validacion=val_date,evidencia_validacion=val_ev,
                         observaciones_validacion=obs,responsable=owner,**scores)
            s.save_solution(payload,owner,key)
            st.rerun()
        except Exception as ex:notice_error(ex)

def solutions_page():
    heading('03','Soluciones, validación y hoja de ruta','Un solo gestor de propuestas: clasificación de diseño, viabilidad, acuerdo de valor y transferencia documentada al Paso 04.')
    st.caption('Cloud: la carga de propuestas institucionales no está habilitada.')
    a,b,c=st.columns([3,1,1])
    with a:st.caption('Los 26 servicios PMI son referencia; pueden adoptarse, adaptarse, utilizarse como habilitadores o dar lugar a soluciones nuevas.')
    with b:
        if st.button('Candidatos Paso 2',use_container_width=True):st.session_state['p3_candidate_panel']=not st.session_state.get('p3_candidate_panel',False)
    with c:
        if st.button('＋ Nueva solución',type='primary',use_container_width=True):solution_dialog()
    if st.session_state.get('p3_candidate_panel'):
        with st.container(border=True):
            available=s.sources()
            if not available:st.info('Primero importa un expediente del Paso 2 en la Matriz de beneficios.')
            else:
                st.caption('Los candidatos importados son conceptos preliminares, no soluciones aprobadas.')
                sid=st.selectbox('Expediente importado',[x['id'] for x in available],
                    format_func=lambda x:next((t['fuente'] for t in available if t['id']==x),x))
                from .storage import connect
                from contextlib import closing
                with closing(connect()) as con:
                    snap=json.loads(con.execute('SELECT snapshot_json FROM p3_sources WHERE id=?',(sid,)).fetchone()[0])
                candidates=s.service_candidates_from_source(sid)
                st.caption(f'{len(candidates)} candidatos registrados. No se recalcula el modelo V5.')
                if candidates:
                    st.dataframe(pd.DataFrame(candidates),hide_index=True,use_container_width=True)
                    selection=st.multiselect('Selecciona servicios para convertir en borradores de solución',
                        [r['id'] for r in candidates],format_func=lambda x:next((r['nombre'] for r in candidates if r['id']==x),str(x)))
                    decision=st.selectbox('Decisión inicial de diseño (podrás modificarla después)',s.DECISIONS)
                    owner=staff_picker('Responsable',value='Equipo PMO',key='p3_candidate_owner')
                    if st.button('Crear borradores seleccionados',type='primary'):
                        try:
                            result=s.import_service_candidates(sid,selection,decision,owner)
                            st.success(f"{result['nuevos']} borradores creados; {result['omitidos']} ya existentes.")
                            st.rerun()
                        except Exception as ex:notice_error(ex)
                else:st.info('Este expediente no contiene candidatos o ranking reconocibles para importar.')
    sol=s.solutions()
    ready=[r for r in sol if r['estado']=='Aprobada' and not s.approval_errors(r)]
    metrics([('Soluciones formuladas',len(sol),'Conceptos registrados','▦'),
             ('En validación',sum(x['estado']=='En validación' for x in sol),'Pendientes de confirmación','⌁'),
             ('Aprobadas',sum(x['estado']=='Aprobada' for x in sol),'Con validación documentada','✓'),
             ('Listas para Paso 4',len(ready),'Expedientes íntegros','◎')])
    st.markdown('#### Gestor único de soluciones')
    st.caption('Lista, tablero y hoja de ruta consultan los mismos registros. La decisión de diseño no equivale al estado de aprobación.')
    with st.container(border=True):
        search_col,decision_col,status_col=st.columns([3,2,2])
        with search_col:search=st.text_input('Buscar solución',placeholder='Nombre, código, beneficio o cliente',key='p3_search_solutions')
        with decision_col:design_filter=st.selectbox('Decisión de diseño',('Todas',)+s.DECISIONS,key='p3_filter_decision')
        with status_col:state_filter=st.selectbox('Estado de revisión',('Todos',)+s.STATES,key='p3_filter_status')
        filtered=[r for r in sol if (design_filter=='Todas' or r['decision']==design_filter) and (state_filter=='Todos' or r['estado']==state_filter)
                  and search.lower() in ' '.join(str(r.get(k) or '') for k in ('codigo','nombre','beneficio','cliente','descripcion')).lower()]
        tab_list,tab_board,tab_route=st.tabs(['Lista y gestión','Tablero por decisión','Hoja de ruta y transferencia'])
        with tab_list:
            if filtered:
                rows=[]
                for r in filtered:
                    q=solution_quality(r)
                    rows.append({'Código':public_code('solucion',r['id']),'Solución':r['nombre'],
                        'Cliente':r['cliente'] or 'Sin identificar','Decisión':r['decision'],'Estado':r['estado'],
                        'Viabilidad CENS':q['viabilidad_cens'],'Bloqueantes para transferir':len(q['bloqueantes']),
                        'Recomendaciones':len(q['recomendaciones'])})
                st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,height=min(450,60+len(rows)*36))
                selected=st.selectbox('Solución que deseas gestionar',[r['id'] for r in filtered],key='p3_select_solution',
                    format_func=lambda rid:next((f"{public_code('solucion',r['id'])} · {r['nombre']}" for r in filtered if r['id']==rid),rid))
                selected_row=next(r for r in filtered if r['id']==selected)
                q=solution_quality(selected_row)
                qa,edit_col,delete_col=st.columns([3,1,1])
                with qa:
                    if q['habilitada_para_transferencia']:st.success('Requisitos de transferencia actuales: completos. Revisa el expediente antes de exportar.')
                    else:st.info('Pendientes mínimos: '+(', '.join(q['bloqueantes']) if q['bloqueantes'] else 'estado de aprobación'))
                    if q['recomendaciones']:
                        with st.expander(f"{len(q['recomendaciones'])} mejoras documentales recomendadas"):
                            for item in q['recomendaciones']:st.write('• '+item)
                with edit_col:
                    if st.button('Abrir ficha',type='primary',use_container_width=True,key='p3_open_one'):solution_dialog(selected)
                with delete_col:
                    with st.popover('Eliminar'):
                        st.warning('No se puede recuperar después de eliminar.')
                        if st.button('Confirmar eliminación',key='p3_remove_unique'):
                            try:s.remove_solution(selected,'Equipo PMO');st.rerun()
                            except Exception as ex:notice_error(ex)
                record=s.agreement_record(selected)
                if record:
                    st.caption(f"Acuerdo documentado: versión {record['version']} · {record['fecha_registro']} · "+
                               ('Vigente frente a la ficha actual' if record['vigente'] else 'Desactualizado; requiere nueva conformidad'))
                if selected_row['estado']=='Aprobada' and not q['bloqueantes']:
                    with st.expander('Registrar acuerdo de valor con el cliente · evidencia versionada'):
                        st.caption('Solo registra la validación obtenida y respaldada por la documentación indicada en la ficha. No se emite una aprobación automática.')
                        sign=st.checkbox('Confirmo que existe validación documental del cliente para los compromisos actuales',key=f'p3_agreement_sign_{selected}')
                        if st.button('Registrar versión del acuerdo',disabled=not sign,key=f'p3_agreement_register_{selected}'):
                            try:
                                v=s.register_value_agreement(selected,'Equipo PMO',confirmed=True)
                                st.success(f'Acuerdo documental registrado · versión {v}')
                                st.rerun()
                            except Exception as ex:notice_error(ex)
            else:st.info('No existen soluciones para los filtros seleccionados.')
        with tab_board:
            boards=st.columns(2)
            for i,decision in enumerate(s.DECISIONS):
                with boards[i%2]:
                    records=[r for r in filtered if r['decision']==decision]
                    with st.container(border=True):
                        st.markdown(f"**{decision}** · {len(records)}")
                        if not records:st.caption('Sin soluciones para estos filtros')
                        for r in records:
                            st.markdown(f"**{esc(r['nombre'])}**")
                            st.caption(f"{public_code('solucion',r['id'])} · {r['estado']} · {r['cliente'] or 'Cliente pendiente'}")
                            st.divider()
            st.caption('Para editar, selecciona la solución en «Lista y gestión». No se repiten los botones por tarjeta.')
        with tab_route:
            st.caption('Horizonte orientativo de propuesta de valor. La ejecución, RACI y ANS se definen en los Pasos 04 y 05.')
            for h in s.HORIZONS:
                relevant=[r for r in filtered if r['horizonte']==h]
                with st.expander(f"{h} · {len(relevant)} propuestas",expanded=h==s.HORIZONS[0]):
                    if relevant:
                        st.dataframe(pd.DataFrame([{'Solución':r['nombre'],'Periodo tentativo':r['periodo'] or 'Por definir',
                          'Estado':r['estado'],'Viabilidad CENS':s.feasibility(r)} for r in relevant]),hide_index=True,use_container_width=True)
                    else:st.caption('Sin soluciones registradas para este horizonte')
            st.divider()
            st.markdown('**Expediente y transferencia al Paso 04**')
            envelope=s.step4_transfer()
            if not ready:st.warning('Sin propuestas aprobadas con necesidad, cliente, beneficio y validación documental completas.')
            else:st.success(f'{len(ready)} propuestas cumplen los requisitos de transferencia establecidos.')
            st.download_button('Transferir aprobadas al Paso 04 · JSON',
                json.dumps(envelope,ensure_ascii=False,indent=2,default=str).encode('utf-8'),
                'PMO_CENS_Paso3_Transferencia_Paso4.json',mime='application/json',disabled=not bool(ready),type='primary')
            # Expediente separado y extensible; el JSON de interfaz hacia Paso 04 sigue intacto.
            report={'schema':'PMO-CENS-P3-EXPEDIENTE-v03918',
                    'transferencia_paso04':envelope,
                    'necesidades_y_beneficios':s.benefits(),
                    'lienzos':[{'lienzo':c,'cobertura':canvas_quality(c['id'])} for c in s.canvases()],
                    'soluciones_control':[{'id':r['id'],**solution_quality(r)} for r in sol],
                    'fuentes':s.sources(),
                    'nota':'Los registros no representan aprobación o beneficios medidos salvo evidencia y estado respectivos.'}
            # Evitar incorporar filas de dolor completas dentro de la propiedad de cobertura del expediente.
            for l in report['lienzos']:l['cobertura']['pendientes']=[{'id':x['id'],'titulo':x['titulo']} for x in l['cobertura']['pendientes']]
            st.download_button('Expediente integral de valor · JSON',json.dumps(report,ensure_ascii=False,indent=2,default=str).encode('utf-8'),
                               'PMO_CENS_Paso3_Expediente_V03918.json',mime='application/json')
            st.download_button('Consolidado Excel',export_excel_solutions(sol),'PMO_CENS_Paso3_Soluciones.xlsx')
            st.download_button('Reporte PDF',solutions_pdf(),'PMO_CENS_Paso3_Propuestas_Valor.pdf',mime='application/pdf')
    st.caption('Autoevaluación PMI: acceso independiente en el menú del Paso 03. Los instrumentos antiguos se conservan solo como histórico.')

def export_excel_solutions(rows):
    output=io.BytesIO()
    fields=('codigo','nombre','cliente','decision','descripcion','beneficio','metrica','estado','horizonte','periodo','validador','fecha_validacion','evidencia_validacion')
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        pd.DataFrame([{x:r.get(x,'') for x in fields} for r in rows]).to_excel(writer,sheet_name='Soluciones',index=False)
        ws=writer.sheets['Soluciones'];ws.freeze_panes='A2'
        from openpyxl.styles import Font,PatternFill
        for c in ws[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='302B56')
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=27
    return output.getvalue()

# -------------------------------- AUTOEVALUACIÓN TRANSVERSAL ----------------------------
def assessment_panel(module:int):
    question_start,question_end=((0,5),(5,15),(15,25))[module]
    evs=s.evaluations()
    with st.expander(f'Evaluación metodológica PMI · {s.MODULES[module]} · {question_end-question_start} preguntas',expanded=False):
        st.caption('Instrumento de 25 criterios parafraseados. No equivale a una transcripción literal ni a certificación PMI.')
        a,b=st.columns([3,1])
        with a:
            if evs:
                opts={f"Evaluación {x['version']} · {x['estado']} · {x['responsable']}":x['id'] for x in evs}
                chosen=st.selectbox('Versión de autoevaluación',list(opts),key=f'p3_eval_choice_{module}')
                eid=opts[chosen]
            else:eid=None;st.info('Crea una evaluación para comenzar los 25 criterios.')
        with b:
            with st.popover('Nueva evaluación'):
                owner=st.text_input('Responsable',value='Equipo PMO',key=f'p3_eval_owner_{module}')
                if st.button('Crear versión',type='primary',key=f'p3_eval_new_{module}'):
                    try:
                        s.create_evaluation(owner)
                        st.rerun()
                    except Exception as ex:notice_error(ex)
        if not eid:return
        summary=s.assessment_summary(eid)
        metrics([('Respuestas',f"{summary['respondidas']}/25",'Instrumento completo','▦'),
                 ('Puntaje',str(summary['puntaje']) if summary['puntaje'] is not None else '—',
                  'Clasificación solo con 25 respuestas','◎'),
                 ('Avance',f"{summary['avance_pct']}%",'Cinco dimensiones','⌁'),
                 ('Evidencias',summary['con_evidencia'],'Preguntas sustentadas','▤')])
        st.progress(summary['respondidas']/25)
        if summary['clasificacion']:st.success(f"Clasificación global: {summary['clasificacion']} · {summary['puntaje']}/125")
        elif summary['respondidas']:st.info(f"Puntaje parcial: {summary['puntaje_parcial']} · Evaluación sin clasificar hasta completar 25/25.")
        for dim_index,(name,questions) in enumerate(s.DIMENSIONS):
            if dim_index not in ((0,),(1,2),(3,4))[module]:continue
            data=summary['dimensiones'][dim_index]
            st.markdown(f"**Dimensión {dim_index+1}: {name}** · {data['respondidas']}/5 · Subtotal: {data['subtotal']} puntos")
            ans={r['numero']:r for r in s.assessment_answers(eid)}
            with st.form(f'p3_dimension_form_{eid}_{dim_index}'):
                row_data=[]
                for j,question in enumerate(questions):
                    index=dim_index*5+j+1
                    old=ans.get(index,{})
                    st.markdown(f'**{index:02d}.** {question}')
                    col=st.columns([1,2,2])
                    with col[0]:
                        choices=['Sin responder',1,2,3,4,5]
                        index_value=choices.index(old['valor']) if old.get('valor') in choices else 0
                        score=st.selectbox('Valor 1–5',choices,index=index_value,key=f'p3_question_{eid}_{index}')
                    with col[1]:comment=st.text_input('Observación',value=old.get('observacion',''),key=f'p3_comment_{eid}_{index}')
                    with col[2]:proof=st.text_input('Evidencia / URL',value=old.get('evidencia',''),key=f'p3_proof_{eid}_{index}')
                    row_data.append((index,score,comment,proof))
                submit=st.form_submit_button('Guardar respuestas de la dimensión',disabled=summary['estado']=='Finalizada',type='primary')
            if submit:
                try:
                    for i,rate,note,ev in row_data:
                        s.save_assessment_answer(eid,i,None if rate=='Sin responder' else rate,note,ev,'Equipo PMO')
                    st.rerun()
                except Exception as ex:notice_error(ex)
        st.divider()
        st.markdown('#### Consolidado de las cinco dimensiones')
        df=pd.DataFrame([{'Dimensión':x['nombre'],'Promedio 1–5':x['promedio'] if x['promedio'] is not None else 0,
                          'Respondidas':x['respondidas'],'Subtotal':x['subtotal']} for x in summary['dimensiones']])
        st.dataframe(df,hide_index=True,use_container_width=True)
        previous=None
        previous_options=[x for x in evs if x['id']!=eid]
        if previous_options:
            prev_choice=st.selectbox('Comparar radar con otra evaluación (opcional)',
                                     ['Sin comparar']+[f"v{x['version']} · {x['estado']}" for x in previous_options],
                                     key=f'p3_compare_{module}')
            if prev_choice!='Sin comparar':
                previous=s.assessment_summary(previous_options[[f"v{x['version']} · {x['estado']}" for x in previous_options].index(prev_choice)]['id'])
        st.image(assessment_radar_svg(summary,previous),use_container_width=True)
        st.bar_chart(df.set_index('Dimensión')['Promedio 1–5'],color='#67618F')
        past=[{'Versión':r['version'],'Estado':r['estado'],'Puntaje':r['puntaje'],'Clasificación':r['clasificacion'] or 'Sin concluir'} for r in evs]
        st.markdown('**Historial**')
        st.dataframe(pd.DataFrame(past),hide_index=True,use_container_width=True)
        _json_button('Exportar evaluación e historial',s.assessment_export(eid),'PMO_CENS_P3_Autoevaluacion.json',key=f'p3_export_ass_{module}')
        st.download_button('Informe de autoevaluación PDF',assessment_pdf(eid),
                           f'PMO_CENS_Paso3_Evaluacion_v{summary["version"]}.pdf',mime='application/pdf',
                           key=f'p3_export_ass_pdf_{module}')
        if summary['estado']!='Finalizada':
            improvements=st.text_area('Acciones de mejora propuestas',key=f'p3_eval_improvements_{eid}_{module}')
            if st.button('Finalizar evaluación',disabled=summary['respondidas']!=25,key=f'p3_eval_finish_{module}'):
                try:s.finish_evaluation(eid,'Equipo PMO',improvements);st.rerun()
                except Exception as ex:notice_error(ex)

def page(section):
    section=ALIASES.get(section,section)
    if section==NAV[0]:benefits_page()
    elif section==NAV[1]:canvas_page()
    elif section==NAV[2]:solutions_page()
    else:st.error('Sección del Paso 3 no reconocida. Usa el acceso independiente a Autoevaluación PMI.')
