"""Vista histórica anual de madurez CENS en escala 0–5, sin reemplazar línea base 1–5."""
from __future__ import annotations

import math
from pathlib import Path

import streamlit as st
from . import step2_maturity_annual as annual
from .clients import ValidationError
from .ui import e


def _radar_svg(scenario, values):
    dimensions=annual.DIMENSIONS[scenario]
    if any(x not in values for x in dimensions): return ''
    cx,cy,r=220,172,114
    n=len(dimensions)
    def positions(scale):
        return [(cx+r*scale*math.sin(2*math.pi*i/n), cy-r*scale*math.cos(2*math.pi*i/n)) for i in range(n)]
    def pts(coords):return ' '.join(f'{x:.1f},{y:.1f}' for x,y in coords)
    rings=''.join(f'<polygon points="{pts(positions(level/5))}" fill="none" stroke="#D8E5E8" stroke-width="1"/>' for level in (1,2,3,4,5))
    spokes=''.join(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#DFE9EE"/>' for x,y in positions(1))
    scorepos=[(cx+(x-cx)*float(values[name])/5,cy+(y-cy)*float(values[name])/5) for name,(x,y) in zip(dimensions,positions(1))]
    polygon=f'<polygon points="{pts(scorepos)}" fill="#F18A3F44" stroke="#E77C32" stroke-width="2.5"/>'
    dots=''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#E77C32"/>' for x,y in scorepos)
    label_map={'Estandarización':['Estandarización'], 'Gobierno':['Gobierno'], 'Medición':['Medición'],
               'Seguimiento y control':['Seguimiento','y control'], 'Enfoques y metodologías':['Enfoques y','metodologías']}
    labels=[]
    for name,(x,y) in zip(dimensions,positions(1.37)):
        lines=label_map[name];anchor='middle' if abs(x-cx)<20 else ('start' if x>cx else 'end')
        txt=''.join(f'<tspan x="{x:.1f}" dy="{0 if ix==0 else 13}">{e(s)}</tspan>' for ix,s in enumerate(lines))
        labels.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="11" text-anchor="{anchor}" fill="#40566B" font-weight="600">{txt}<tspan x="{x:.1f}" dy="14" font-weight="700" fill="#B76D2B">{values[name]:.2f}</tspan></text>')
    numbers=''.join(f'<text x="{cx+6}" y="{cy-r*level/5-3:.1f}" font-size="9" fill="#8699A5">{level}</text>' for level in (1,2,3,4,5))
    return (f'<svg viewBox="0 0 440 360" width="100%" role="img" aria-label="Radar de madurez {e(scenario)}" xmlns="http://www.w3.org/2000/svg">'
            +rings+spokes+polygon+dots+''.join(labels)+numbers+'</svg>')



def comparison_radar_svg(records: dict, years: list[int]) -> str:
    """Radar de las cinco dimensiones de madurez institucional (NO PMI)."""
    from html import escape
    dimensions=annual.DIMENSIONS[annual.CON]
    complete=[(year,records[(year,annual.CON)]['dimensiones']) for year in years
              if (year,annual.CON) in records and all(d in records[(year,annual.CON)]['dimensiones'] for d in dimensions)]
    if not complete:return ''
    colors=['#2563EB','#E57A27','#7C3AED','#159E93','#C8496E','#6F7F18','#40536C','#DEAD22']
    cx,cy,r=310,207,138
    import math
    def pos(i,v):
        angle=2*math.pi*i/5
        return cx+r*v/5*math.sin(angle),cy-r*v/5*math.cos(angle)
    def pts(points):return ' '.join(f'{x:.1f},{y:.1f}' for x,y in points)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Comparación anual de cinco dimensiones de madurez institucional" viewBox="0 0 760 460" width="100%">']
    for level in range(1,6):
        svg.append(f'<polygon points="{pts([pos(i,level) for i in range(5)])}" fill="none" stroke="#E0E7EF" stroke-width="1.2"/>')
        svg.append(f'<text x="{cx+7}" y="{cy-r*level/5-5:.1f}" fill="#7F91A3" font-size="11">{level}</text>')
    for i,dim in enumerate(dimensions):
        x,y=pos(i,5)
        svg.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#D1DCE5"/>')
        labx,laby=pos(i,6.35)
        anchor='middle' if abs(labx-cx)<20 else ('start' if labx>cx else 'end')
        lines={'Seguimiento y control':('Seguimiento','y control'),
               'Enfoques y metodologías':('Enfoques y','metodologías')}.get(dim,(dim,))
        svg.append(f'<text x="{labx:.1f}" y="{laby:.1f}" fill="#38546B" font-weight="600" text-anchor="{anchor}" font-size="12">')
        for j,line in enumerate(lines):svg.append(f'<tspan x="{labx:.1f}" dy="{14 if j else 0}">{escape(line)}</tspan>')
        svg.append('</text>')
    for idx,(year,values) in enumerate(complete):
        color=colors[(year-2023)%len(colors)]
        coordinates=[pos(i,float(values[dim])) for i,dim in enumerate(dimensions)]
        svg.append(f'<polygon points="{pts(coordinates)}" fill="{color}" fill-opacity="0.065" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>')
        for dim,(x,y) in zip(dimensions,coordinates):
            score=float(values[dim]); label=f'{score:.2f}'.replace('.',',')
            # A larger transparent target makes both mouse hover and keyboard focus usable.
            svg.append(f'<g class="radar-point" tabindex="0" role="img" '
                       f'data-year="{int(year)}" data-dimension="{escape(dim,quote=True)}" '
                       f'data-score="{score:.2f}" '
                       f'aria-label="{int(year)} · {escape(dim,quote=True)}: {label} de 5">'
                       f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="transparent" stroke="none" />'
                       f'<circle class="radar-marker" cx="{x:.1f}" cy="{y:.1f}" r="5.2" '
                       f'fill="{color}" stroke="white" stroke-width="1.5" pointer-events="none"/>'
                       f'<title>{int(year)} · {escape(dim)}: {label} / 5</title></g>')
        ly=80+idx*27
        svg.append(f'<line x1="590" y1="{ly}" x2="616" y2="{ly}" stroke="{color}" stroke-width="3"/>')
        svg.append(f'<circle cx="603" cy="{ly}" r="4" fill="{color}"/>')
        svg.append(f'<text x="625" y="{ly+5}" fill="#324B60" font-size="14" font-weight="700">{year}</text>')
    svg.append('</svg>')
    return ''.join(svg)


def comparison_radar_html(records: dict, years: list[int]) -> str:
    """Interactive, offline tooltip. Same annual dataset and SVG geometry as the static radar."""
    svg = comparison_radar_svg(records, years)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
html,body{{margin:0;padding:0;overflow:hidden;background:transparent;font-family:'Segoe UI',Arial,sans-serif;color:#253854}}
#radar-wrap{{width:100%;max-width:900px;position:relative;margin:0 auto;touch-action:manipulation}}
#radar-wrap svg{{display:block;width:100%;height:auto}}
.radar-point{{cursor:pointer;outline:none}}
.radar-point:hover .radar-marker,.radar-point:focus .radar-marker{{stroke:#0C2548;stroke-width:2.3}}
.radar-point:focus{{filter:drop-shadow(0 0 3px #6B8ABC)}}
#radar-tooltip{{display:none;position:absolute;pointer-events:none;z-index:8;min-width:160px;max-width:230px;padding:10px 12px;background:#172845;color:white;border-radius:10px;box-shadow:0 6px 24px #16243A33;font-size:12px;line-height:1.4}}
#radar-tooltip b{{display:block;font-size:13px;margin-bottom:4px}}#radar-tooltip .score{{font-size:19px;font-weight:800;color:#EAF4FF}}
#radar-readout{{position:absolute;right:3.5%;bottom:6%;width:25%;min-width:135px;padding:9px 12px;border:1px solid #D5E2F1;border-radius:11px;background:#F8FAFF;font-size:12px;color:#334764}}
#radar-readout b{{display:block;margin-bottom:4px;color:#183C72}}#radar-readout .score{{font-size:18px;font-weight:800;color:#1B559D}}
</style></head><body>
<div id="radar-wrap">{svg}<div id="radar-tooltip" role="tooltip"></div><div id="radar-readout" aria-live="polite"><b>Consulta de puntos</b>Pasa el cursor sobre un vértice o selecciónalo con el teclado.</div></div>
<script>
(function(){{
  const wrap=document.getElementById('radar-wrap'),tip=document.getElementById('radar-tooltip'),readout=document.getElementById('radar-readout');
  function data(node){{return {{ano:node.dataset.year,dimension:node.dataset.dimension,valor:Number(node.dataset.score).toFixed(2).replace('.',',')}};}}
  function show(node,evt){{const d=data(node);tip.replaceChildren();const title=document.createElement('b');title.textContent=d.ano+' · '+d.dimension;const val=document.createElement('span');val.className='score';val.textContent=d.valor+' / 5';tip.append(title,val);tip.style.display='block';
    readout.replaceChildren();const h=document.createElement('b');h.textContent=d.ano+' · '+d.dimension;const v=document.createElement('span');v.className='score';v.textContent=d.valor+' / 5';readout.append(h,v);
    const bounds=wrap.getBoundingClientRect();let x=bounds.width*.55,y=80;
    if(evt&&typeof evt.clientX==='number'){{x=evt.clientX-bounds.left+12;y=evt.clientY-bounds.top+10;}}
    else{{const target=node.getBoundingClientRect();x=target.left-bounds.left+18;y=target.top-bounds.top-10;}}
    tip.style.left=Math.max(5,Math.min(x,bounds.width-230))+'px';tip.style.top=Math.max(0,Math.min(y,bounds.height-65))+'px';}}
  const dots=Array.from(wrap.querySelectorAll('.radar-point'));
  dots.forEach(node=>{{node.addEventListener('mouseenter',evt=>show(node,evt));node.addEventListener('mousemove',evt=>show(node,evt));
    node.addEventListener('mouseleave',()=>{{tip.style.display='none';}});node.addEventListener('focus',()=>show(node));
    node.addEventListener('blur',()=>{{tip.style.display='none';}});node.addEventListener('click',evt=>show(node,evt));}});
}})();
</script></body></html>"""


def _small_kpi(label, value, subtitle=''):
    st.markdown(f'''<div style="border:1px solid #DEE6ED;background:#F9FBFD;border-radius:12px;
      padding:12px 15px;min-height:87px;margin-bottom:11px"><div style="font-size:26px;font-weight:750;color:#18384A">{e(value)}</div>
      <div style="font-size:12px;color:#53657A;font-weight:600">{e(label)}</div>
      <div style="font-size:10px;color:#8A9AA9">{e(subtitle)}</div></div>''',unsafe_allow_html=True)


def _panel_index(scenario, record, trend):
    accent='#C99C43' if scenario==annual.CON else '#628DC9'
    subtitle='Cinco dimensiones (incluye enfoques)' if scenario==annual.CON else 'Cuatro dimensiones (excluye enfoques)'
    value=f'{record["indice"]:.2f}' if record else '—'
    st.markdown(f'''<div style="border:1px solid #E0E7EF;border-radius:14px;background:#FAFBFD;
    text-align:center;padding:17px 14px;min-height:176px"><div style="color:#495C71;font-size:13px;font-weight:700">{e(scenario)}</div>
    <div style="font-size:13px;color:#758397">{e(subtitle)}</div>
    <div style="font-size:55px;line-height:1.2;font-weight:800;color:{accent}">{value}</div>
    <div style="color:#7E8C9B;font-size:11px">Índice percibido · escala 0–5</div></div>''',unsafe_allow_html=True)
    if trend:
        st.caption('  ·  '.join(f'{yr}: {value:.2f}' for yr,value in trend))


def render_history(diag, item):
    st.markdown('### Madurez percibida · Histórico anual')
    st.caption('Registro consolidado institucional de CENS · Escala 0–5 · Sin conexión con PMOGA, encuestas individuales ni priorización de servicios.')
    data=annual.history()
    periods={r['ano']:r for r in data['periodos']}
    scenarios={(r['ano'],r['escenario']):r for r in data['escenarios']}
    years=sorted(periods)
    if years:
        selected=st.selectbox('Año de evaluación',years,index=len(years)-1,format_func=lambda y:str(y),key='p2_maturity_year_v036')
        current=periods[selected]
        cols=st.columns([0.85,1.4,1.4,1.1],gap='medium')
        with cols[0]:
            for label,field in [('Participantes en sesiones','participantes'),('Encuestas diligenciadas','encuestas'),
                                ('Equipos de trabajo','equipos'),('Dependencias participantes','dependencias')]:
                value=current.get(field)
                _small_kpi(label,str(value) if value is not None else '—')
        for i,scenario in enumerate(annual.SCENARIOS,1):
            with cols[i]:
                trend=sorted([(yr,scenarios[(yr,scenario)]['indice']) for yr in years if (yr,scenario) in scenarios])
                _panel_index(scenario,scenarios.get((selected,scenario)),trend)
        with cols[3]:
            st.markdown('**Dimensiones del modelo**')
            dims=scenarios.get((selected,annual.CON),{}).get('dimensiones',{})
            if dims:
                for label in reversed(annual.DIMENSIONS[annual.CON]):
                    if label in dims:
                        st.markdown(f'<div style="font-size:11px;color:#52687C;margin:8px 0 3px">{e(label)} · <b>{dims[label]:.2f}</b></div>',unsafe_allow_html=True)
                        st.progress(min(1.0,float(dims[label])/5))
            else:st.caption('Sin desglose por dimensión para este año.')
        a,b,c=st.columns([1.15,1.15,1],gap='medium')
        for col,scenario in ((a,annual.CON),(b,annual.SIN)):
            with col:
                with st.container(border=True):
                    st.markdown('**'+scenario+'**')
                    record=scenarios.get((selected,scenario))
                    if record and record['dimensiones']:
                        st.markdown(_radar_svg(scenario,record['dimensiones']),unsafe_allow_html=True)
                    elif record:
                        st.info('Índice histórico disponible; falta el desglose de dimensiones para construir el radar.')
                    else:st.info('No hay resultados para este escenario y año.')
        with c:
            with st.container(border=True):
                st.markdown('**Principales hallazgos**')
                findings=[s.strip(' •-\t') for s in (current['hallazgos'] or '').splitlines() if s.strip(' •-\t')]
                if findings:
                    for desc in findings:
                        st.markdown(f'<div style="padding:6px 0;border-bottom:1px solid #EBEFF3;font-size:13px;color:#405368">✓ {e(desc)}</div>',unsafe_allow_html=True)
                else:st.caption('Este año no tiene hallazgos documentados.')
                st.caption(f"Fuente: {current['fuente']}. Responsable: {current['responsable']}.")
        st.markdown('#### Evolución comparativa de las cinco dimensiones · Radar por año')
        available_years=[yr for yr in years if (yr,annual.CON) in scenarios and
                         all(name in scenarios[(yr,annual.CON)]['dimensiones'] for name in annual.DIMENSIONS[annual.CON])]
        if available_years:
            selected_years=st.multiselect('Años a comparar',available_years,default=available_years[-4:],
                                           format_func=lambda yr:str(yr),key='p2_madurez_radar_comparativo_v0391')
            if selected_years:
                with st.container(border=True):
                    st.components.v1.html(comparison_radar_html(scenarios,sorted(selected_years)),height=480,scrolling=False)
                    st.caption('Pasa el cursor sobre cualquier punto (o selecciónalo con Tab) para consultar el año, dimensión y puntaje exacto. Escenario con enfoques y metodologías · Escala 0–5.')
            else:st.info('Seleccione por lo menos un año para comparar.')
        else:st.info('No hay años con el desglose completo de las cinco dimensiones; el radar no estima resultados faltantes.')
        st.markdown('#### Evolución de los índices')
        import pandas as pd
        trend_df=pd.DataFrame([{'Año':yr,annual.CON:scenarios.get((yr,annual.CON),{}).get('indice'),
                                annual.SIN:scenarios.get((yr,annual.SIN),{}).get('indice')} for yr in years]).set_index('Año')
        st.line_chart(trend_df,y_label='Índice (0–5)')
        st.markdown('#### Comparación por dimensión · Años disponibles')
        dimension_rows=[]
        for yr in years:
            vals=scenarios.get((yr,annual.CON),{}).get('dimensiones',{})
            if vals and len(vals)==5:
                dimension_rows.append({'Año':str(yr),**vals})
        if dimension_rows:
            st.bar_chart(pd.DataFrame(dimension_rows).set_index('Año'),y_label='Madurez percibida (0–5)')
        else:
            st.caption('Faltan los resultados consolidados por dimensión.')
        st.caption('Los índices históricos se muestran tal como fueron informados. No se estiman dimensiones ni años faltantes.')
        with st.expander('Ver datos registrados y trazabilidad'):
            st.dataframe([{'Año':r['ano'],'Escenario':r['escenario'],'Índice':r['indice'],'Dimensiones':len(r['dimensiones']),
                           'Fuente':r['fuente'],'Responsable':r['responsable'],'Actualizado':r['actualizado_en']} for r in data['escenarios']],
                         hide_index=True,use_container_width=True)
    else:
        st.info('Todavía no hay resultados históricos cargados. Importa el archivo de madurez anual para comenzar.')
    with st.expander('＋ Registrar o actualizar un año manualmente',expanded=False):
        st.caption('Resultados institucionales agregados. No se registran respuestas individuales; los índices son promedios simples de las dimensiones ingresadas.')
        with st.form('p2_maturity_manual_v037'):
            y=st.number_input('Año',min_value=2000,max_value=2100,value=2027,step=1)
            form_cols=st.columns(4)
            fields=('participantes','encuestas','equipos','dependencias')
            labels=('Participantes','Encuestas','Equipos','Dependencias')
            nums={}
            for col,k,label in zip(form_cols,fields,labels):
                with col: nums[k]=st.number_input(label,min_value=0,value=None,step=1,placeholder='Sin dato')
            st.markdown('**Puntuaciones por dimensión (0–5)**')
            values={}
            dim_cols=st.columns(5)
            for col,dim in zip(dim_cols,annual.DIMENSIONS[annual.CON]):
                with col: values[dim]=st.number_input(dim,min_value=0.0,max_value=5.0,step=0.01,value=None,format='%.2f',key='p2_maturity_manual_'+annual._norm(dim))
            findings=st.text_area('Hallazgos principales (uno por línea)')
            source=st.text_input('Fuente del resultado consolidado *')
            owner=st.text_input('Responsable del registro *')
            replace_manual=st.checkbox('Autorizo reemplazar el año registrado si existe (con respaldo)')
            saved=st.form_submit_button('Guardar resultado anual',type='primary')
        if saved:
            try:
                if not source.strip() or not owner.strip():
                    raise ValidationError('Fuente y responsable son obligatorios.')
                period={'ano':int(y),**{k:(int(v) if v is not None else None) for k,v in nums.items()},'hallazgos':findings.strip(),'fuente':source.strip(),'responsable':owner.strip()}
                if any(v is None for v in values.values()):
                    raise ValidationError('Complete las cinco dimensiones; no se asignan ceros por defecto.')
                scenarios=[]
                for scenario,dims in annual.DIMENSIONS.items():
                    ratings={dim:float(values[dim]) for dim in dims}
                    scenarios.append({'ano':int(y),'escenario':scenario,'indice':round(sum(ratings.values())/len(ratings),2),'fuente':source.strip(),'responsable':owner.strip(),'dimensiones':ratings})
                outcome=annual.import_history({'periodos':[period],'escenarios':scenarios},owner,overwrite=replace_manual)
                st.success('Año registrado con respaldo y trazabilidad.')
                st.rerun()
            except ValidationError as err: st.error(str(err))
    with st.expander('＋ Importar resultados consolidados anuales desde Excel',expanded=not bool(years)):

        st.caption('Carga simplificada: hoja **Resumen anual**, una fila por año. También acepta el formato anterior de tres hojas para compatibilidad. Nunca lee encuestas individuales.')
        root=Path(__file__).resolve().parents[1]
        for name,label in [('PLANTILLA_MADUREZ_CONSOLIDADA_V037.xlsx','Descargar plantilla consolidada'),
                           ('RESULTADOS_MADUREZ_CONSOLIDADOS_CENS_2023_2026_V037.xlsx','Descargar resultados consolidados CENS')]:
            filepath=root/'plantillas'/name
            if filepath.is_file():
                st.download_button(label,filepath.read_bytes(),file_name=name,
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key=f'p2_v036_download_{name}')
        uploaded=st.file_uploader('Archivo de madurez anual (Excel)',type=['xlsx'],key='p2_maturity_upload_v037')
        if uploaded is not None:
            try:
                parsed=annual.parse_summary_excel(uploaded.getvalue())
                st.success(f"Archivo válido: {len(parsed['periodos'])} años y {len(parsed['escenarios'])} escenarios.")
                st.dataframe([{'Año':x['ano'],'Escenario':x['escenario'],'Índice':x['indice'],
                              'Dimensiones':len(x['dimensiones'])} for x in parsed['escenarios']],
                             use_container_width=True,hide_index=True)
                with st.form('p2_maturity_confirm_v036'):
                    actor=st.text_input('Responsable de la importación *')
                    replace=st.checkbox('Reemplazar resultados existentes cuando el archivo tenga valores diferentes (con respaldo)')
                    authorized=st.checkbox('Confirmo los valores, su fuente y la escala de 0 a 5.')
                    submit=st.form_submit_button('Validar y guardar histórico anual',type='primary',disabled=not authorized)
                if submit:
                    result=annual.import_history(parsed,actor,overwrite=replace,backup=True)
                    st.success(f"Actualización completada ({result['cambios']} cambios). Respaldo: {result['respaldo'] or 'Sin cambios en la base'}")
                    st.rerun()
            except (ValidationError,ValueError) as ex:
                st.error(str(ex))
            except Exception as ex:
                st.error('No se pudo procesar el archivo. Verifica su formato y origen. Detalle: '+str(ex))

    # V0.39.3: ranking por pregunta independiente de las 5 dimensiones consolidadas.
    from .step2_maturity_questions_ui import render as render_questions
    render_questions(preferred_year=selected if years else None)
