"""Inspect archived snapshots without recomputation or persistence."""
def matrix_rows(report, *, outcome=None, service=None, positive=False):
    result=report.get('resultados',{})
    matrix=report.get('matriz',{})
    rows=[]
    for o in result.get('outcomes',[]):
        oid=int(o['id'])
        if outcome is not None and oid!=outcome:continue
        line=matrix.get(str(oid),matrix.get(oid,{}))
        for s in result.get('services',[]):
            sid=int(s['id'])
            if service is not None and sid!=service:continue
            intensity=line.get(str(sid),line.get(sid))
            if positive and not (intensity is not None and intensity>0):continue
            rows.append({'Resultado':f'O-{oid:02d} · {o["name"]}','Servicio':f'S-{sid:02d} · {s["name"]}','Intensidad':intensity})
    return rows


def render(report, runs, diag):
    import streamlit as st
    from . import step2 as p2
    with st.expander('Explorar matriz congelada y comparar escenarios archivados'):
        st.caption('Consulta exclusivamente la matriz y las ponderaciones guardadas en la corrida seleccionada. Un cruce ausente no se convierte en cero.')
        result=report['resultados'];outcomes={int(o['id']):o['name'] for o in result['outcomes']};services={int(s['id']):s['name'] for s in result['services']}
        a,b=st.columns(2)
        outcome=a.selectbox('Resultado',[None,*outcomes],format_func=lambda v:outcomes[v] if v else 'Todos',key=f'a02_snap_o_{diag}')
        service=b.selectbox('Servicio',[None,*services],format_func=lambda v:services[v] if v else 'Todos',key=f'a02_snap_s_{diag}')
        positive=st.checkbox('Solo intensidades positivas',key=f'a02_snap_pos_{diag}')
        rows=matrix_rows(report,outcome=outcome,service=service,positive=positive)
        st.caption(f'{len(rows)} cruces en la selección.')
        if rows:st.dataframe(rows,hide_index=True,use_container_width=True)
        else:st.info('Sin relaciones para los filtros.')
        available={r['id']:r for r in runs if r['id']!=report['id']}
        other=st.selectbox('Otra corrida real para comparar pesos',[None,*available],format_func=lambda v:f"{available[v]['fecha']} · {available[v]['actor']} · {v[:8]}" if v else 'Sin comparación',key=f'a02_snap_compare_{diag}')
        if other:
            previous=p2.get_run(other);first=report.get('pesos',{});second=previous.get('pesos',{})
            if isinstance(first,dict) and isinstance(second,dict):
                st.dataframe([{'Rol':k,'Peso corrida actual':first.get(k),'Peso otra corrida':second.get(k)} for k in sorted(set(first)|set(second))],hide_index=True,use_container_width=True)
            st.caption(f"Participantes: {result.get('participants','—')} frente a {previous['resultados'].get('participants','—')}. Pueden cambiar muestra, matriz y roles; no atribuir diferencias exclusivamente al peso.")
        st.info('Esta vista no crea escenarios, corridas ni decisiones MVS. Para ejecutar un análisis experto, usa Ponderar y ejecutar.')
