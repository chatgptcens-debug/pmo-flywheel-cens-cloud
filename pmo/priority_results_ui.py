"""V0.39.29 · Tablero de resultados del Paso 02, inspirado en los cuatro
apartados funcionales de las pantallas PMOGA aportadas por el usuario.

NO calcula, repondera ni reescribe corridas: solo consume su snapshot.
La clasificación se lee del resultado original, no se infiere por umbrales fijos.
"""
from __future__ import annotations
from collections import Counter
from html import escape as html_escape
from io import BytesIO
import math

import streamlit as st

from . import step2 as p2
from .step2_reports import results_xlsx

CATEGORY_ORDER=('Núcleo', 'Importante', 'Periférico')
CATEGORY_COLORS={'Núcleo':'#302653','Importante':'#76689C','Periférico':'#A8AEC1'}


def group_summary(snapshot: dict) -> list[dict]:
    """Cifras basadas exclusivamente en la clasificación almacenada en la corrida."""
    services=snapshot['resultados']['services']
    result=[]
    for label in CATEGORY_ORDER:
        subset=[s for s in services if s.get('category')==label]
        result.append({'categoria':label, 'servicios':len(subset),
                       'relevancia':sum(float(s['score']) for s in subset)})
    return result


def service_stats(snapshot: dict) -> dict:
    scores=[float(x['score']) for x in snapshot['resultados']['services']]
    if not scores:return dict(total=0,maximo=0,minimo=0,media=0,mediana=0,rango=0,top5=0)
    ordered=sorted(scores)
    n=len(ordered)
    middle=(ordered[(n-1)//2]+ordered[n//2])/2
    return {'total':n, 'maximo':max(scores), 'minimo':min(scores),
            'media':sum(scores)/n, 'mediana':middle, 'rango':max(scores)-min(scores),
            'top5':sum(scores[:5])}


def group_outcome_score(group:dict, outcome_id:int) -> float:
    values=group.get('outcomes',{})
    raw=values.get(str(outcome_id),values.get(outcome_id,0))
    return max(0,float(raw or 0))*100


def group_service_ranking(snapshot:dict, role:str) -> list[dict]:
    """Recomendaciones descriptivas por rol, usando SOLO la matriz y el reparto
    de resultados congelados en la corrida, sin cambiar el ranking global V5.
    """
    data=snapshot['resultados']
    group=data.get('groups',{}).get(role)
    if not group:return []
    matrix=snapshot.get('matriz',{})
    output=[]
    for service in data.get('services',[]):
        sid=int(service['id'])
        score=0.0
        for outcome in data.get('outcomes',[]):
            oid=int(outcome['id'])
            line=matrix.get(str(oid),matrix.get(oid,{}))
            intensity=float(line.get(str(sid),line.get(sid,0)) or 0)
            score+=group_outcome_score(group,oid)*intensity
        output.append({'id':sid,'name':service['name'],'raw':score})
    total=sum(x['raw'] for x in output)
    for x in output:x['score']=100*x['raw']/total if total>0 else 0.0
    return sorted(output,key=lambda x:(-x['score'],x['id']))


def ranking_diff(snapshot:dict, old:dict|None) -> dict[int,int]:
    if not old:return {}
    previous={int(s['id']):i+1 for i,s in enumerate(old['resultados']['services'])}
    return {int(s['id']):previous[int(s['id'])]-(i+1) for i,s in enumerate(snapshot['resultados']['services'])
            if int(s['id']) in previous}


def _styles():
    st.markdown('''<style>
    .pr29-banner{border-radius:16px;background:#F5F5FC;border:1px solid #E2E2F1;padding:20px 24px;margin:8px 0 16px}
    .pr29-eyebrow{font-size:11px;letter-spacing:1px;font-weight:800;color:#9D491C}
    .pr29-title{font-size:27px;color:#192C49;font-weight:800;line-height:1.25;margin-top:6px}
    .pr29-lede{font-size:13px;color:#58647B;margin-top:6px}
    .pr29-tier{background:#fff;border:1px solid #E3E6EF;border-radius:13px;padding:17px 18px;height:100%;}
    .pr29-tier-name{font-size:12px;color:#66718B;font-weight:700}
    .pr29-tier-value{font-size:28px;color:#24243F;font-weight:800;margin-top:3px}
    .pr29-tier-foot{font-size:11px;color:#68748D;margin-top:3px}
    .pr29-stripe{height:5px;border-radius:5px;margin-top:12px}
    .pr29-row{display:grid;grid-template-columns: minmax(125px,2fr) minmax(110px,4fr) 70px;
      align-items:center;column-gap:14px;border-bottom:1px solid #EDF0F6;padding:9px 3px}
    .pr29-row:last-child{border-bottom:0}
    .pr29-label{font-size:12px;color:#2C3658;overflow-wrap:anywhere}
    .pr29-track{height:12px;background:#EFF1F7;border-radius:9px;overflow:hidden}
    .pr29-track > i{height:100%;display:block;border-radius:9px}
    .pr29-number{font-size:12px;font-weight:750;color:#333C5E;text-align:right}
    .pr29-summary{background:#FBFBFE;border:1px solid #E5E7F2;border-radius:13px;padding:15px 17px;margin:10px 0}
    .pr29-chip{padding:4px 9px;border-radius:24px;background:#F3EFFB;font-size:11px;color:#3D3173;font-weight:700}
    .pr29-note{padding:12px 14px;background:#EDF5FF;border-left:3px solid #3974C5;border-radius:9px;color:#24426C;font-size:12px}
    </style>''',unsafe_allow_html=True)


def _bar_rows(items:list[tuple[str,float]],*, color='#38305C', maximum:float|None=None) -> None:
    if not items:
        st.info('Aún no hay resultados disponibles para esta vista.');return
    den=maximum or max([max(float(v),0) for _,v in items]+[1])
    body=[]
    for name,val in items:
        val=float(val)
        width=max(0,min(100,100*val/den))
        body.append(f'<div class="pr29-row"><div class="pr29-label" title="{html_escape(str(name),quote=True)}">'
                    f'{html_escape(str(name))}</div><div class="pr29-track"><i style="background:{color};width:{width:.2f}%"></i></div>'
                    f'<div class="pr29-number">{val:.1f}%</div></div>')
    st.markdown('<div class="pr29-summary">'+''.join(body)+'</div>',unsafe_allow_html=True)


def _tier_cards(summary:list[dict]) -> None:
    cols=st.columns(3,gap='small')
    for col,entry in zip(cols,summary):
        hue=CATEGORY_COLORS[entry['categoria']]
        with col:
            st.markdown(f'<div class="pr29-tier"><div class="pr29-tier-name">{entry["categoria"]}</div>'
                        f'<div class="pr29-tier-value">{entry["relevancia"]:.1f}%</div>'
                        f'<div class="pr29-tier-foot">{entry["servicios"]} servicios · participación acumulada</div>'
                        f'<div class="pr29-stripe" style="background:{hue}"></div></div>',unsafe_allow_html=True)


def _tier_donut(summary:list[dict]) -> None:
    current=0.0
    stops=[]
    for item in summary:
        nxt=current+max(0,float(item['relevancia']))
        stops.append(f'{CATEGORY_COLORS[item["categoria"]]} {current:.2f}% {nxt:.2f}%')
        current=nxt
    gradient='conic-gradient('+', '.join(stops)+')'
    st.markdown('<div style="display:flex;gap:22px;align-items:center;justify-content:center;flex-wrap:wrap;padding:12px 4px">'
                f'<div role="img" aria-label="Distribución por categoría de prioridad" style="width:178px;height:178px;border-radius:50%;background:{gradient};position:relative;">'
                '<div style="position:absolute;inset:40px;background:white;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;color:#322752">100%</div></div>'
                '<div style="display:grid;gap:9px">'+''.join(f'<div style="font-size:12px;color:#33405D">'
                f'<span style="display:inline-block;width:10px;height:10px;background:{CATEGORY_COLORS[i["categoria"]]};margin-right:8px;border-radius:2px"></span>'
                f'{i["categoria"]}: <b>{i["relevancia"]:.1f}%</b> · {i["servicios"]} servicios</div>' for i in summary)+'</div></div>',unsafe_allow_html=True)


def _overview(report:dict,results:dict):
    tiers=group_summary(report)
    stats=service_stats(report)
    st.subheader('Resumen ejecutivo de la priorización')
    _tier_cards(tiers)
    st.caption('Núcleo: servicios que conducen hasta alrededor del 50% de la relevancia acumulada. '
               'Importantes: hasta alrededor del 80%. Periféricos: restantes. La banda se recupera del snapshot original.')
    col1,col2=st.columns([1.35,1],gap='large')
    with col1:
        st.markdown('**Servicios por categoría de prioridad**')
        for item in tiers:
            subset=[s for s in results['services'] if s.get('category')==item['categoria']]
            with st.expander(f'{item["categoria"]} · {len(subset)} servicios · {item["relevancia"]:.1f}%', expanded=item['categoria']=='Núcleo'):
                st.dataframe([{'Puesto': next(i for i,x in enumerate(results['services'],1) if x['id']==s['id']),
                               'Servicio':s['name'],'Prioridad %':round(s['score'],2)} for s in subset],
                             hide_index=True,use_container_width=True)
    with col2:
        st.markdown('**Distribución de la prioridad**')
        _tier_donut(tiers)
        st.markdown('**Estadísticas clave**')
        entries=[('Servicios',stats['total']),('Máximo',f"{stats['maximo']:.1f}%"),
                 ('Mínimo',f"{stats['minimo']:.1f}%"),('Promedio',f"{stats['media']:.1f}%"),
                 ('Mediana',f"{stats['mediana']:.1f}%"),('Concentración Top 5',f"{stats['top5']:.1f}%")]
        st.dataframe([{'Indicador':k,'Valor':v} for k,v in entries],hide_index=True,use_container_width=True)
        st.markdown('**Distribución por umbrales de puntuación**')
        high=sum(float(x['score'])>=5 for x in results['services'])
        medium=sum(2<=float(x['score'])<5 for x in results['services'])
        low=sum(float(x['score'])<2 for x in results['services'])
        st.caption(f'Alta (5% o más): **{high}** · Media (de 2% a menos de 5%): **{medium}** · Baja (menos de 2%): **{low}**. '
                   'Estos umbrales son informativos y distintos de las bandas por puntuación acumulada.')
    st.markdown('**Comparación de puntuaciones · primeros servicios**')
    count=st.selectbox('Servicios en la gráfica',[5,10,15,26],index=1,key='pr29_n_overview')
    _bar_rows([(str(i)+' · '+s['name'],s['score']) for i,s in enumerate(results['services'][:count],1)],
              color='#352B61')


def _outcomes(report:dict):
    results=report['resultados']
    st.subheader('Relevancia de resultados esperados')
    groups=results.get('groups',{})
    top=results['outcomes']
    active=sum(x['score']>0 for x in top)
    cols=st.columns(4)
    cols[0].metric('Roles con respuestas',len(groups))
    cols[1].metric('Clientes procesados',results['participants'])
    cols[2].metric('Resultados activos',f'{active}/{len(top)}')
    cols[3].metric('Mayor relevancia',f"{top[0]['score']:.1f}%" if top else '—')
    weights=', '.join(f'{name}: {g["weight"]:.0f}%' for name,g in groups.items())
    st.caption(f'Ponderaciones originales de esta corrida: {weights or "Sin información"}. No se sustituyen por pesos prefijados de PMOGA.')
    st.markdown('**Resultados priorizados por los clientes**')
    count=st.selectbox('Mostrar primeros resultados',[5,10,15,30],index=1,key='pr29_n_outcomes')
    _bar_rows([(f'O-{int(x["id"]):02d} · {x["name"]}',x['score']) for x in top[:count]],color='#346EC5')
    st.dataframe([{'Posición':i,'Resultado':f'O-{int(x["id"]):02d} · {x["name"]}',
                   'Relevancia (%)':round(x['score'],3)} for i,x in enumerate(top,1)],
                 hide_index=True,use_container_width=True)
    st.divider()
    st.subheader('Comparación por rol de los clientes')
    st.caption('El porcentaje individual de cada rol indica cómo ese grupo distribuye sus preferencias. No equivale al peso asignado al rol.')
    if not groups:return
    import pandas as pd
    compare=st.selectbox('Comparar los primeros resultados',[5,10,15],index=0,key='pr29_compare_top')
    data=[]
    for x in top[:compare]:
        row={'Resultado':f'O-{int(x["id"]):02d} · {x["name"][:48]}'}
        for name,g in groups.items():row[name]=group_outcome_score(g,int(x['id']))
        data.append(row)
    if data:
        chart=pd.DataFrame(data).set_index('Resultado')
        st.bar_chart(chart,horizontal=True,stack=False,use_container_width=True)
    for name,g in groups.items():
        ranked=sorted(((int(o['id']),o['name'],group_outcome_score(g,int(o['id']))) for o in top),
                      key=lambda a:(-a[2],a[0]))
        with st.expander(f'{name} · {g["participants"]} participantes · ponderación {g["weight"]:.0f}%'):
            st.markdown('**Resultados esperados más relevantes del rol**')
            _bar_rows([(f'O-{oid:02d} · {title}',v) for oid,title,v in ranked[:10]],color='#7555B1')
            st.markdown('**Servicios relacionados con estas prioridades**')
            recommendations=group_service_ranking(report,name)
            if recommendations:
                st.dataframe([{'Puesto':i, 'Servicio':f'S-{x["id"]:02d} · {x["name"]}',
                               'Relevancia dentro del rol (%)':round(x['score'],2)}
                              for i,x in enumerate(recommendations[:10],1)],hide_index=True,use_container_width=True)
                st.caption('Comparación descriptiva derivada de las relaciones de matriz congeladas para este rol; '
                           'no es un nuevo escenario ni sustituye el ranking global de la corrida.')


def analyze_insights(report:dict) -> dict:
    """Genera conclusiones descriptivas basadas solamente en el snapshot disponible."""
    result=report['resultados'];groups=result.get('groups',{});services=result.get('services',[])
    outcomes=result.get('outcomes',[])
    sets={}
    for name,g in groups.items():
        ordered=sorted([(int(x['id']),group_outcome_score(g,int(x['id']))) for x in outcomes],
                       key=lambda t:(-t[1],t[0]))
        sets[name]={oid for oid,score in ordered[:5] if score>0}
    best_pair=None
    for a in sets:
        for b in sets:
            if a>=b:continue
            overlap=len(sets[a]&sets[b])
            if best_pair is None or overlap<best_pair[2]:best_pair=(a,b,overlap)
    borders=[]
    for i in range(len(services)-1):
        a,b=services[i],services[i+1]
        if a.get('category')!=b.get('category'):
            borders.append({'antes':a,'despues':b,'distancia_pp':abs(a['score']-b['score'])})
    return {'top_service':services[0] if services else None,
            'top_outcomes':outcomes[:3], 'concentracion':sum(x['score'] for x in services if x.get('category')=='Núcleo'),
            'core_count':sum(x.get('category')=='Núcleo' for x in services),
            'pair_min_overlap':best_pair,'fronteras':borders}


def _insights(report:dict):
    info=analyze_insights(report)
    st.subheader('Hallazgos y preguntas para decidir')
    if info['top_service']:
        s=info['top_service'];st.success(f'Servicio con mayor relevancia: **{s["name"]}**, con **{s["score"]:.1f}%** en esta corrida.')
    st.info(f'Los **{info["core_count"]} servicios del Núcleo** representan **{info["concentracion"]:.1f}%** de la prioridad acumulada.')
    top=info['top_outcomes']
    if top:
        st.markdown('**Resultados esperados que más impulsan la priorización**')
        _bar_rows([(x['name'],x['score']) for x in top],color='#468FAD')
    pair=info['pair_min_overlap']
    if pair:
        st.markdown('**Diferencias entre roles**')
        st.write(f'Los roles «{pair[0]}» y «{pair[1]}» comparten {pair[2]} de sus cinco resultados principales. '
                 'Revisa si necesitan ofertas diferenciadas; la comparación no demuestra por sí sola un conflicto organizacional.')
    st.markdown('**Fronteras entre categorías**')
    if info['fronteras']:
        for boundary in info['fronteras']:
            a,b=boundary['antes'],boundary['despues'];d=boundary['distancia_pp']
            st.warning(f'**{a["category"]} → {b["category"]}**: «{a["name"]}» ({a["score"]:.2f}%) y '
                       f'«{b["name"]}» ({b["score"]:.2f}%) están separados por {d:.2f} pp. '
                       'Si la diferencia es pequeña, conviene analizar la sensibilidad antes de tomar una decisión.')
    st.markdown('**Precaución con servicios que ya se prestan**')
    st.markdown('<div class="pr29-note">Una prioridad baja no demuestra que un servicio sea innecesario. '
                'Puede existir una necesidad satisfecha, por lo que conviene contrastar la clasificación con '
                'su uso, riesgos y resultados del monitoreo (Pasos 06 y 07) antes de retirarlo.</div>',unsafe_allow_html=True)
    st.caption('Estos hallazgos son lecturas descriptivas de la corrida V5 guardada. No constituyen validación formal ni certificación PMOGA.')


def _details(report:dict,all_reports:list[dict]):
    result=report['resultados'];services=result['services']
    st.subheader('Clasificación de prioridad del servicio')
    st.caption('26 servicios ordenados por su contribución relativa según las necesidades registradas, los pesos confirmados y la matriz seleccionada.')
    a,b=st.columns([2.2,1])
    search=a.text_input('Buscar servicio',placeholder='Nombre o código del servicio',key='pr29_service_find')
    limit=b.selectbox('Filtrar ranking',['Todos','Top 5','Top 10','Top 15'],key='pr29_service_limit')
    maxshow={'Todos':len(services),'Top 5':5,'Top 10':10,'Top 15':15}[limit]
    rows=[(i,s) for i,s in enumerate(services[:maxshow],1) if search.strip().casefold() in (f'S-{int(s["id"]):02d} {s["name"]}').casefold()]
    others={r['id']:r for r in all_reports if r['id']!=report['id']}
    comparison=st.selectbox('Comparar posiciones con otra corrida (opcional)',
                            ['Sin comparación',*others],format_func=lambda key: key if key=='Sin comparación' else
                            next(f'{x["fecha"]} · {x["actor"]}' for x in all_reports if x['id']==key),key='pr29_compare_run')
    old=p2.get_run(comparison) if comparison!='Sin comparación' else None
    changes=ranking_diff(report,old)
    with st.container(border=True):
        for i,s in rows:
            sid=int(s['id']);diff=changes.get(sid)
            arrow=f' · {"▲" if diff>0 else "▼" if diff<0 else "="}{abs(diff)} posiciones' if diff is not None else ''
            st.markdown(f'**{i:02d}. S-{sid:02d} · {s["name"]}** · {s["category"]} · **{s["score"]:.2f}%**{arrow}')
            st.progress(min(1,max(0,s['score']/max(0.01,float(services[0]['score'])))))
        if not rows:st.info('No hay servicios que coincidan con los filtros.')
    st.markdown('**Ranking completo · detalle exportable**')
    st.dataframe([{'Posición':i,'Código':f'S-{int(x["id"]):02d}', 'Servicio':x['name'],
                   'Banda':x.get('category','—'), 'Relevancia (%)':round(x['score'],3),
                   'Acumulado (%)':round(x['cumulative'],3),
                   'Movimiento (puestos)':changes.get(int(x['id'])) if old else None}
                  for i,x in enumerate(services,1)], hide_index=True,use_container_width=True)
    ids={int(s['id']):s for s in services}
    selected=st.selectbox('Explicar la posición de un servicio',list(ids),
                          format_func=lambda sid:f'S-{sid:02d} · {ids[sid]["name"]}',key='pr29_drivers')
    contribution=result.get('contributions',{}).get(str(selected))
    if contribution:
        st.dataframe([{'Resultado esperado':x['outcome'], 'Peso resultado %':round(x['result_weight_pct'],3),
                       'Intensidad 0–4':x['intensity'], 'Contribución al ranking (pp)':round(x['global_share_pct'],4)}
                      for x in contribution],hide_index=True,use_container_width=True)
    elif 'contributions' not in result:
        st.caption('Esta corrida histórica no dispone del desglose de aportes; se conserva sin recomputar.')
    else:st.info('No hay contribuciones positivas para este servicio.')
    with st.expander('Cómo calcula V5 y cómo interpretar los porcentajes'):
        st.markdown('1. Cada cliente ordena cinco resultados esperados, puntuados **5, 4, 3, 2 y 1**.\n'
                    '2. Las preferencias se consolidan por **rol** y los roles reciben **ponderaciones por criterio experto**, cuya suma es 100%.\n'
                    '3. Se aplica la **Matriz PMO Value Ring de 30 resultados × 26 servicios**, con intensidades documentadas de 0 a 4.\n'
                    '4. La relevancia se **normaliza a porcentajes** y se clasifica en bandas de relevancia acumulada.\n'
                    '5. El ranking ayuda a decidir, pero **no aprueba servicios** ni se equipara a resultados financieros realizados.')
        st.caption(f'Fuente: {report.get("origen", "Corrida histórica")}. Matriz: {report.get("modelo", "Sin identificar")}.')


def results_pdf(report:dict)->bytes:
    """Informe ejecutivo del snapshot elegido; no altera las corridas ni consulta PMOGA."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
    content=BytesIO();doc=SimpleDocTemplate(content,pagesize=(21*cm,29.7*cm),
                 rightMargin=1.6*cm,leftMargin=1.6*cm,topMargin=1.8*cm,bottomMargin=1.8*cm)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PMO29Title',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=17,
                              textColor=colors.HexColor('#2F2854'),spaceAfter=8))
    styles.add(ParagraphStyle(name='PMO29Small',parent=styles['BodyText'],fontSize=8,leading=11))
    styles.add(ParagraphStyle(name='PMO29Cell',parent=styles['Normal'],fontSize=7.2,leading=9.5))
    P=lambda v:Paragraph(html_escape(str(v)),styles['PMO29Cell'])
    result=report['resultados'];tier=group_summary(report)
    flow=[Paragraph('PMO FLYWHEEL CENS · Priorización de servicios',styles['PMO29Title']),
          Paragraph('Informe de una corrida guardada · Documento analítico no equivalente a aprobación institucional',styles['PMO29Small']),Spacer(1,0.5*cm),
          Paragraph('Fecha: '+html_escape(str(report.get('fecha','—')))+' · Responsable: '+html_escape(str(report.get('actor','—'))),styles['PMO29Small']),
          Paragraph('Matriz: '+html_escape(str(report.get('modelo','—'))),styles['PMO29Small']),
          Spacer(1,0.5*cm), Paragraph('Resumen ejecutivo',styles['Heading2'])]
    leader=result['services'][0] if result['services'] else None
    if leader:flow.append(Paragraph(f'Servicio más relevante: {html_escape(leader["name"])} ({leader["score"]:.2f}%).',styles['PMO29Small']))
    flow.append(Paragraph(f'{result.get("participants",0)} participantes · {len(result.get("groups",{}))} roles · {len(result["services"])} servicios.',styles['PMO29Small']))
    t=Table([[P('Categoría'),P('Servicios'),P('Relevancia acumulada')] ]+
            [[P(x['categoria']),P(x['servicios']),P(f'{x["relevancia"]:.2f}%')] for x in tier],colWidths=[6.3*cm,4*cm,6.3*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7E4F2')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                           ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#D9DAE6')),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    flow.extend([Spacer(1,0.3*cm),t,Spacer(1,0.5*cm),Paragraph('Ranking de los 26 servicios',styles['Heading2'])])
    rows=[[P('#'),P('Servicio'),P('Prioridad'),P('Categoría')]]
    for i,s in enumerate(result['services'],1):rows.append([P(i),P(s['name']),P(f'{s["score"]:.2f}%'),P(s['category'])])
    table=Table(rows,colWidths=[1*cm,10.7*cm,2.5*cm,2.4*cm],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7E4F2')),('VALIGN',(0,0),(-1,-1),'TOP'),
                           ('LINEBELOW',(0,0),(-1,-1),0.25,colors.HexColor('#D9DAE6')),
                           ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    flow.extend([table,Spacer(1,0.5*cm),Paragraph('Resultados esperados · ranking',styles['Heading2'])])
    outcome_rows=[[P('#'),P('Resultado esperado'),P('Relevancia')]]+[
        [P(i),P(x['name']),P(f'{x["score"]:.2f}%')] for i,x in enumerate(result['outcomes'],1)]
    outcome_table=Table(outcome_rows,colWidths=[1*cm,13*cm,2.6*cm],repeatRows=1,hAlign='LEFT')
    outcome_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7E4F2')),
                                      ('LINEBELOW',(0,0),(-1,-1),0.25,colors.HexColor('#D9DAE6')),
                                      ('VALIGN',(0,0),(-1,-1),'TOP')]))
    flow.append(outcome_table)
    for role,details in result.get('groups',{}).items():
        flow.append(Spacer(1,0.5*cm))
        flow.append(Paragraph('Rol: '+html_escape(role),styles['Heading2']))
        flow.append(Paragraph(f'{details["participants"]} participantes · Ponderación experta: {details["weight"]:.0f}%',styles['PMO29Small']))
        group_outcomes=sorted([(int(o['id']),o['name'],group_outcome_score(details,int(o['id'])))
                              for o in result['outcomes']],key=lambda row:(-row[2],row[0]))[:10]
        rtable=Table([[P('Resultado esperado'),P('Relevancia en rol')]]+
                     [[P(n),P(f'{score:.2f}%')] for _,n,score in group_outcomes],
                     colWidths=[13*cm,3.6*cm],repeatRows=1,hAlign='LEFT')
        rtable.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7E4F2')),
                                   ('VALIGN',(0,0),(-1,-1),'TOP'),
                                   ('LINEBELOW',(0,0),(-1,-1),0.2,colors.HexColor('#D9DAE6'))]))
        flow.append(rtable)
        services_role=group_service_ranking(report,role)[:10]
        if services_role:
            flow.append(Spacer(1,0.25*cm))
            flow.append(Paragraph('Servicios asociados al rol',styles['Heading3']))
            stable=Table([[P('Servicio'),P('Relevancia en rol')]]+
                         [[P(x['name']),P(f'{x["score"]:.2f}%')] for x in services_role],
                         colWidths=[13*cm,3.6*cm],repeatRows=1,hAlign='LEFT')
            stable.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F0EEF7')),
                                       ('LINEBELOW',(0,0),(-1,-1),0.2,colors.HexColor('#D9DAE6')),
                                       ('VALIGN',(0,0),(-1,-1),'TOP')]))
            flow.append(stable)
    flow.append(Spacer(1,0.5*cm))
    flow.append(Paragraph('Nota: las ponderaciones y las relaciones son las de la corrida seleccionada. '
                          'La reconstrucción V5 de CENS no representa certificación de PMI/PMOGA.',styles['PMO29Small']))
    doc.build(flow)
    return content.getvalue()


def render(diag:str)->None:
    """Vista consultiva: no utiliza funciones de actualización de preferencias o matrices."""
    _styles()
    runs=p2.runs(diag)
    if not runs:
        st.info('Todavía no existe una corrida de priorización. Completa las preferencias y utiliza «Ponderar y ejecutar».')
        return
    names={x['id']:f"{x['fecha']} · {x['modelo']} · {x['actor']}" for x in runs}
    selected=st.selectbox('Análisis guardado',list(names),format_func=lambda sid:names[sid],key='pr29_selected_run_'+diag)
    report=p2.get_run(selected);r=report['resultados']
    st.markdown('<div class="pr29-banner"><div class="pr29-eyebrow">PASO 02 · PRIORIZACIÓN DE SERVICIOS</div>'
                '<div class="pr29-title">Resultados de la priorización PMO</div>'
                '<div class="pr29-lede">Cuatro vistas complementarias: resumen, voz del cliente, hallazgos y ranking de 26 servicios.</div></div>',unsafe_allow_html=True)
    k1,k2,k3,k4=st.columns(4)
    k1.metric('Clientes procesados',r.get('participants',0))
    k2.metric('Roles',len(r.get('groups',{})))
    k3.metric('Servicios analizados',len(r['services']))
    k4.metric('Concentración Top 5',f"{sum(x['score'] for x in r['services'][:5]):.1f}%")
    c1,c2=st.columns([1.8,1])
    with c1:
        st.caption(f"Corrida {report['fecha']} · Matriz {report.get('modelo','—')} · Snapshots de pesos y respuestas conservados.")
    with c2:
        st.download_button('Excel de resultados',results_xlsx(report),file_name=f'PMO_CENS_P2_{selected[:8]}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='pr29_xlsx_'+diag)
        st.download_button('Informe PDF',results_pdf(report),file_name=f'PMO_CENS_P2_{selected[:8]}.pdf',
            mime='application/pdf',key='pr29_pdf_'+diag)
    tabs=st.tabs(['Descripción general','Resultados esperados','Análisis y hallazgos','Datos detallados'])
    with tabs[0]:_overview(report,r)
    with tabs[1]:_outcomes(report)
    with tabs[2]:_insights(report)
    with tabs[3]:_details(report,runs)
    from .alpha02_priority import render as render_snapshot_explorer
    render_snapshot_explorer(report,runs,diag)
    st.caption('Fuente de todos los resultados: la corrida seleccionada de PMO FLYWHEEL CENS. '
               'Las pantallas PMOGA suministradas son una referencia de experiencia de usuario, no la fuente de estos cálculos.')
