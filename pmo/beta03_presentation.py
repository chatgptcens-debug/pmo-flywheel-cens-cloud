"""Vista ejecutiva agregada, sin edición, sin nombres personales ni persistencia."""
from datetime import datetime, timezone
from html import escape
from .alpha_control_tower import read_metrics, METRICS
from .alpha05_value import benefit_data, benefit_rows, recognition_data, recognition
from .alpha06_transversal import quality
from .alpha_navigation import STEPS, go_to, VERSION
from .config import database_path


def report(path=None):
    m=read_metrics(path)
    local=benefit_rows(benefit_data(path))
    perception=recognition(recognition_data(path),local)
    q=quality(path)
    # Distinguish unavailable from zero, and not aggregate incompatible measures.
    cards=[(label,m[label],source,step) for label,_,_,source,step in METRICS]
    cards.extend([
        ('Beneficios con medición',None if local is None else sum(x['Mediciones']>0 for x in local),'Paso 09 · no demo',9),
        ('Beneficios verificados vigentes',None if local is None else sum(x['Situación']=='Verificado' for x in local),'Paso 09 · última medición cotejada',9),
        ('Respuestas de percepción',None if perception is None else perception['nps']['total'],'Paso 10 · todos los periodos, no demo',10),
        ('NPS',None if perception is None else perception['nps']['puntaje'],'Paso 10 · −100 a +100; no equivale a beneficio',10),
        ('Reglas con hallazgos',sum(bool(v) for v in q.values()) if any(v is not None for v in q.values()) else None,'Advertencias, no calificación de madurez',2),
        ('Reglas no evaluables',sum(v is None for v in q.values()),'Fuentes de revisión no disponibles',2),
    ])
    return {'generated':datetime.now(timezone.utc).isoformat(timespec='seconds'),'cards':cards}


def value_text(v):
    if v is None:return '—'
    if isinstance(v,float):return f'{v:.1f}'
    return str(v)


def to_html(data, isolated=True):
    cards=''.join(f'<article><small>{escape(label)}</small><strong>{escape(value_text(v))}</strong><p>{escape(source)}</p></article>' for label,v,source,_ in data['cards'])
    mode='Vista previa aislada · no constituye resultado oficial' if isolated else 'Consulta local · revisar antes de divulgar'
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PMO CENS · Lectura ejecutiva</title><style>body{{font:16px Arial,sans-serif;color:#18384c;margin:24px auto;padding:16px;max-width:1200px}}header{{background:#10374b;color:#fff;padding:22px;border-radius:12px}}h1{{margin:0 0 8px}}main{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:20px 0}}article{{border:1px solid #d9e3ec;border-top:4px solid #087d83;border-radius:10px;padding:14px;break-inside:avoid}}small,p{{line-height:1.45}}strong{{display:block;font-size:30px;margin:10px 0}}@media(max-width:720px){{main{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media print{{body{{margin:0;padding:0;font-size:12px}}header{{color:#18384c;background:white;border-bottom:2px solid #087d83}}main{{gap:8px}}article{{padding:8px}}}}</style></head><body><header><h1>PMO FLYWHEEL CENS · Lectura ejecutiva</h1><p>{escape(mode)} · {escape(VERSION)} · UTC {escape(data['generated'])}</p></header><main>{cards}</main><p>Acumulados de la base, sin filtro anual. Consultas consecutivas de solo lectura, no corte histórico congelado. Un guion indica fuente o cálculo no disponible. Las reglas son advertencias; la percepción no acredita materialización del valor. No se incluyen nombres de clientes ni detalles individuales.</p></body></html>'''


def render(st, isolated=True):
    st.markdown('<div class="b03-sponsor-intro"><h2>Lectura ejecutiva para el sponsor</h2><p>Visión agregada de clientes, operación, beneficios, percepción y calidad.</p></div>',unsafe_allow_html=True)
    if isolated:st.info('Vista previa aislada · no constituye información oficial de CENS.')
    data=report();st.caption(f"Base conectada: {database_path().parent.name} · Consulta UTC: {data['generated']} · Acumulado, sin filtro anual.")
    from .design_system import alpha_metric
    for start in range(0,len(data['cards']),3):
        for col,(label,value,source,step) in zip(st.columns(3),data['cards'][start:start+3]):
            with col:
                # Native metric supports NPS decimals without truncating.
                st.metric(label,value_text(value));st.caption(source)
    st.caption('Fuentes consultadas consecutivamente: no representa un corte histórico congelado. Un guion indica ausencia de cálculo o fuente. No se agregan unidades económicas ni se atribuye causalidad.')
    st.download_button('Descargar vista ejecutiva imprimible (HTML)',to_html(data,isolated).encode('utf-8'),file_name='CENS_V100_Lectura_Ejecutiva.html',mime='text/html',key='b03_presentation_download',on_click='ignore')
    with st.expander('Volver a fuentes de información'):
        for n in (1,2,6,9,10):
            st.button(STEPS[n-1],key=f'b03_source_{n}',on_click=go_to,args=(STEPS[n-1],),use_container_width=True)
