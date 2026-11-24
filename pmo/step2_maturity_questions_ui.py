"""Vista ejecutiva V0.39.3: 53 preguntas de la encuesta de madurez institucional."""
from __future__ import annotations

from html import escape as e
from . import step2_maturity_questions as analysis
from .clients import ValidationError
import streamlit as st

STYLES = '''
<style>
.p2q-eyebrow{font-size:11px;font-weight:850;color:#ED6E38;letter-spacing:1.05px;margin:22px 0 6px}
.p2q-title{font-size:22px;letter-spacing:-.3px;font-weight:800;color:#142F46;margin-bottom:4px}
.p2q-subtitle{font-size:12px;color:#70849A;margin-bottom:20px;line-height:1.55}
.p2q-stats{border:1px solid #DFE7F1;background:white;border-radius:12px;padding:11px 15px;min-height:92px}
.p2q-stats b{display:block;font-weight:850;font-size:28px;color:#123753}
.p2q-stats span{font-size:12px;color:#697C91}
.p2q-card{background:white;border:1px solid #DFE7F1;border-radius:14px;padding:16px;margin-bottom:13px;box-shadow:0 2px 8px rgba(16,55,75,.025)}
.p2q-card-header{font-size:15px;font-weight:850;color:#19374C;margin-bottom:4px;display:flex;align-items:center;gap:9px}
.p2q-card-header .p2q-bubble{width:28px;height:28px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;background:#FFF0EA;color:#E45532}
.p2q-card-header.good .p2q-bubble{background:#E7F5E8;color:#257D3D}
.p2q-card-help{font-size:11px;color:#8190A2;margin-bottom:13px}
.p2q-item{display:grid;grid-template-columns:27px minmax(145px,1fr) minmax(45px,.5fr) 66px;align-items:center;gap:9px;border-bottom:1px solid #EDF0F5;padding:10px 0}
.p2q-item:last-child{border-bottom:none}
.p2q-item .id{font-size:11px;color:#9AA7B7}
.p2q-item .name{font-size:12px;font-weight:650;color:#253D53;line-height:1.3}
.p2q-item .score{font-size:12px;font-weight:800;text-align:right;color:#243849;font-variant-numeric:tabular-nums}
.p2q-track{height:8px;border-radius:12px;background:#E9EBF1;overflow:hidden}
.p2q-track i{height:100%;display:block;border-radius:12px}
.p2q-rank{background:white;border:1px solid #DFE7F1;border-radius:14px;overflow:hidden;margin-top:10px}
.p2q-rank-row{display:grid;grid-template-columns:36px minmax(220px,2.6fr) minmax(90px,1.2fr) 83px;align-items:center;gap:14px;border-bottom:1px solid #E9EDF3;padding:11px 14px;}
.p2q-rank-row:last-child{border-bottom:0}
.p2q-rank-row:nth-child(odd){background:#FBFCFE}
.p2q-rank-index{background:#FFF0EA;color:#D65C38;padding:5px;border-radius:9px;min-width:30px;text-align:center;font-size:12px;font-weight:750}
.p2q-rank-label{font-size:12px;font-weight:750;color:#1E3650}
.p2q-rank-desc{font-size:10px;color:#78889C;line-height:1.4;margin-top:3px}
.p2q-rank-score{text-align:right;font-size:13px;font-weight:850;color:#1F394E;font-variant-numeric:tabular-nums}
.p2q-rank-score small{display:block;font-size:9px;color:#8190A0;font-weight:500}
.p2q-delta{font-size:10px;font-weight:800;white-space:nowrap}
@media(max-width:820px){.p2q-rank-row{grid-template-columns:30px minmax(120px,1fr) 60px;gap:8px}.p2q-rank-row>.p2q-track{display:none}.p2q-item{grid-template-columns:20px minmax(80px,1fr) 45px 58px;gap:5px}}
</style>
'''


def _color(score:float,positive:bool=False):
    if positive:
        return '#36883C' if score >= 3.7 else '#67A84F'
    if score < 1: return '#E5484D'
    if score < 2: return '#EA6E3B'
    if score < 3: return '#E9A11B'
    return '#4A9B5B'


def _card(title,values,positive=False):
    icon='✓' if positive else '!' 
    classname=' good' if positive else ''
    header=f'<div class="p2q-card-header{classname}"><span class="p2q-bubble">{icon}</span>{e(title)}</div>'
    helptext='Mayor calificación del instrumento' if positive else 'Menor calificación del instrumento'
    rows=[]
    for index,r in enumerate(values,1):
        score=float(r['promedio']); title=e(r['titulo']); color=_color(score,positive)
        rows.append(f'<div class="p2q-item" title="{e(r["pregunta"],quote=True)}">'
                    f'<span class="id">{index:02d}</span><span class="name">{title}</span>'
                    f'<div class="p2q-track"><i style="background:{color};width:{score/5*100:.2f}%"></i></div>'
                    f'<span class="score">{score:.2f} / 5</span></div>')
    return f'<section class="p2q-card">{header}<div class="p2q-card-help">{helptext}</div>{"".join(rows)}</section>'


def _rank_row(rank:int,r:dict,other:dict|None):
    score=float(r['promedio']); color=_color(score); title=e(r['titulo']); question=e(r['pregunta'])
    detail=f'<div class="p2q-rank-desc">{e(r["dimension"])} · Pregunta {r["numero"]:02d} · {question}</div>'
    if other is not None:
        previous=float(other['promedio']); change=score-previous
        icon='+' if change>0 else ''
        delta_color='#348854' if change>0 else '#DB5243' if change<0 else '#758599'
        detail+=f'<div class="p2q-delta" style="color:{delta_color}">Variación: {icon}{change:.2f} puntos respecto a {other["ano"]}</div>'
    return (f'<div class="p2q-rank-row"><span class="p2q-rank-index">{rank:02d}</span>'
            f'<div><div class="p2q-rank-label">{title}</div>{detail}</div>'
            f'<div class="p2q-track"><i style="width:{score/5*100:.2f}%;background:{color}"></i></div>'
            f'<div class="p2q-rank-score">{score:.2f} / 5<small>{r["respuestas"]} respuestas</small></div></div>')


def render(preferred_year:int|None=None):
    data=analysis.history()
    if not data['fuentes']:
        st.info('Aún no hay resultados por pregunta. Importa el archivo completo de respuestas de un año.')
    st.markdown(STYLES,unsafe_allow_html=True)
    st.markdown('<div class="p2q-eyebrow">DIAGNÓSTICO DE MADUREZ · RESULTADOS POR PREGUNTA</div>'
                '<div class="p2q-title">Debilidades y fortalezas de la gestión de proyectos</div>'
                '<div class="p2q-subtitle">Clasificación de las 53 preguntas del instrumento según la calificación media de las respuestas. '
                'Vista independiente de las autoevaluaciones PMI y del motor V5.</div>',unsafe_allow_html=True)
    if data['fuentes']:
        sources={int(r['ano']):r for r in data['fuentes']}
        years=sorted(sources)
        preferred=preferred_year if preferred_year in years else years[-1]
        chosen=st.selectbox('Año del diagnóstico por preguntas',years,index=years.index(preferred),
                            key='p2_questions_year_v0393',format_func=lambda yr:str(yr))
        meta=sources[chosen]
        rows=[x for x in data['preguntas'] if int(x['ano'])==chosen]
        rows.sort(key=lambda r:(float(r['promedio']),int(r['numero'])))
        bottom=rows[:7]
        top=sorted(rows,key=lambda r:(-float(r['promedio']),int(r['numero'])))[:7]
        capture_start=str(meta.get('captura_inicio',''))
        capture_end=str(meta.get('captura_fin',''))
        if capture_start and int(capture_start[:4])!=chosen:
            st.warning(f'El archivo se identificó para el diagnóstico {chosen}, pero las respuestas '
                       f'fueron capturadas del {capture_start} al {capture_end}. '
                       'Se conserva el año de evaluación declarado; revisa esta asociación antes de utilizarla en informes oficiales.')
        elif capture_start:
            st.caption(f'Respuestas capturadas entre {capture_start} y {capture_end} · {e(str(meta["fuente"]))}.')
        a,b,c,d=st.columns(4,gap='small')
        metrics=[('Preguntas evaluadas',str(len(rows))),('Respuestas de participantes',str(meta['participantes'])),
                 ('Brecha de menor nota',f'{min(float(r["promedio"]) for r in rows):.2f} / 5'),
                 ('Fortaleza de mayor nota',f'{max(float(r["promedio"]) for r in rows):.2f} / 5')]
        for col,(label,value) in zip((a,b,c,d),metrics):
            with col:
                st.markdown(f'<div class="p2q-stats"><b>{e(value)}</b><span>{e(label)}</span></div>',unsafe_allow_html=True)
        st.markdown('')
        left,right=st.columns(2,gap='medium')
        with left:st.markdown(_card('Puntos más débiles',bottom,False),unsafe_allow_html=True)
        with right:
            st.markdown(_card('Fortalezas destacadas' if top[0]['promedio']>=3 else 'Prácticas mejor valoradas',top,True),unsafe_allow_html=True)
        if top[0]['promedio'] < 3:
            st.caption('Advertencia de interpretación: aun las prácticas mejor valoradas están por debajo de 3/5. Son fortalezas relativas de la muestra, no capacidades consolidadas.')
        st.caption('Los promedios por pregunta se calculan sobre las respuestas importadas. No reemplazan ni corrigen los índices anuales consolidados y sus muestras pueden diferir.')
        st.markdown('#### Ranking completo de las 53 preguntas')
        st.caption('Del menor al mayor promedio. Se conservan los enunciados originales en cada fila, '
                   'incluidas las referencias a «área» cuando así se formularon en la encuesta.')
        filter_col,sort_col,search_col=st.columns([1.4,1.4,2],gap='small')
        with filter_col:
            dimension=st.selectbox('Dimensión',['Todas las dimensiones']+[x[0] for x in analysis.DIMENSIONS],key='p2q_dimension_v0393')
        with sort_col:
            order=st.selectbox('Ordenar preguntas',['Menor a mayor calificación','Mayor a menor calificación','Orden del instrumento'],key='p2q_order_v0393')
        with search_col:
            query=st.text_input('Buscar en las preguntas',placeholder='OKR, contratación, seguimiento...',key='p2q_query_v0393')
        other_years=[y for y in years if y!=chosen]
        compare=st.checkbox('Mostrar variación respecto de otro año',value=False,disabled=not other_years,key='p2q_compare_v0393')
        reference_year=st.selectbox('Año de comparación',other_years,index=len(other_years)-1,key='p2q_other_year_v0393') if compare and other_years else None
        reference={int(r['numero']):r for r in data['preguntas'] if int(r['ano'])==reference_year} if reference_year else {}
        filtered=[r for r in rows if (dimension=='Todas las dimensiones' or r['dimension']==dimension)
                  and (not query or query.casefold() in (r['pregunta']+' '+r['titulo']).casefold())]
        if order=='Mayor a menor calificación':filtered.sort(key=lambda r:(-float(r['promedio']),r['numero']))
        elif order=='Orden del instrumento':filtered.sort(key=lambda r:r['numero'])
        st.caption(f'{len(filtered)} de {len(rows)} preguntas · Escala 0–5 · '
                   '0 incluye «Nunca / No se presenta / No sabe», tal como se codificó en el instrumento.')
        if filtered:
            st.markdown('<div class="p2q-rank">'+''.join(_rank_row(i,r,reference.get(r['numero'])) for i,r in enumerate(filtered,1))+'</div>',unsafe_allow_html=True)
        else:
            st.info('No hay preguntas que coincidan con los filtros.')
        st.download_button('↓ Exportar ranking completo a CSV',analysis.export_rank_csv(rows),
                           file_name=f'PMO_CENS_Madurez_Preguntas_{chosen}.csv',mime='text/csv',key='p2q_export_v0393')
        if reference_year is not None:
            st.caption(f'Comparación entre las mismas posiciones de pregunta (01–53) de {reference_year} y {chosen}. '
                       'Las variaciones son descriptivas: pueden corresponder a muestras distintas y algunas preguntas cambiaron ligeramente de redacción.')
    with st.expander('＋ Cargar respuestas de un nuevo año (53 preguntas)',expanded=False):
        st.caption('Importa el Excel/CSV/TXT/TSV original de Microsoft Forms. '
                   'Se guardan SOLO promedios, número de respuestas y frecuencias por pregunta; '
                   'no se conservan nombres, correos ni respuestas personales. '
                   'No se modifican los índices históricos consolidados.')
        next_year=max((int(x['ano']) for x in data['fuentes']),default=2026)+1
        target=st.number_input('Año de evaluación',min_value=2000,max_value=2100,value=min(next_year,2100),key='p2q_upload_year_v0393')
        source=st.text_input('Fuente de la evaluación',value='Encuesta CENS de madurez en gestión de proyectos',key='p2q_upload_source_v0393')
        responsible=st.text_input('Responsable de la importación *',key='p2q_upload_actor_v0393')
        file=st.file_uploader('Respuestas completas del año',type=['xlsx','csv','txt','tsv'],key='p2q_upload_file_v0393')
        if file is not None:
            try:
                payload=analysis.parse_survey(file.getvalue(),file.name,int(target),source,responsible or 'Pendiente de registrar')
                dates=payload['captura_inicio']+' a '+payload['captura_fin'] if payload['captura_inicio'] else 'No disponibles'
                st.success(f'Archivo legible: {payload["participantes"]} respuestas y 53 preguntas · Captura: {dates}.')
                if payload['captura_inicio'] and int(payload['captura_inicio'][:4])!=int(target):
                    st.warning('El año declarado para la evaluación es distinto al año de captura del archivo. '
                               'Comprueba que corresponde al año institucional que deseas registrar.')
                replace=st.checkbox('Autorizar reemplazo de los resultados por pregunta del mismo año (con respaldo)',key='p2q_upload_replace_v0393')
                confirm=st.checkbox('Confirmo el año, la fuente, las calificaciones y el responsable.',key='p2q_upload_confirm_v0393')
                if st.button('Guardar resultados por pregunta',type='primary',disabled=not confirm or not responsible.strip(),key='p2q_upload_save_v0393'):
                    payload['responsable']=responsible.strip()
                    result=analysis.import_survey(payload,overwrite=replace)
                    st.success('Importación completada con respaldo: '+result['respaldo'])
                    st.rerun()
            except (ValidationError,ValueError) as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error('No fue posible procesar la encuesta. '+str(exc))
