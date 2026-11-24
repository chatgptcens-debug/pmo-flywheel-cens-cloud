"""Interfaz integrada de Matriz de Correspondencia para el motor del Paso 2."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from . import matrix as m
from .clients import ValidationError


def _label(vid,available):
    v=next((x for x in available if x['id']==vid),None)
    if vid == m.V5_ID:
        return f"Matriz PMO Value Ring · V5 (referencia Excel coincidente) · {v['estado']}" if v else vid
    return f"{vid} · {v['estado']}" if v else vid


_SCALE = (
    (0, 'Sin relación identificada', 'No se consignó una contribución en esta matriz'),
    (1, 'Baja', 'Contribución baja al resultado'),
    (2, 'Media', 'Contribución media al resultado'),
    (3, 'Alta', 'Contribución alta al resultado'),
    (4, 'Muy alta', 'Contribución muy alta al resultado'),
)


def _value_ring_guide():
    """Descripción y leyenda sin modificar las 780 intensidades del motor."""
    st.markdown('''<div class="pmo-vr-intro">
      <div class="pmo-vr-kicker">PMO FLYWHEEL CENS · PASO 02</div>
      <div class="pmo-vr-intro-title">Matriz PMO Value Ring</div>
      <div class="pmo-vr-intro-copy">Representa la contribución de cada uno de los <b>26 servicios de la PMO</b>
      a cada uno de los <b>30 resultados esperados</b> por sus clientes. Cada cruce se expresa
      en una escala de 0 a 4. Sirve para convertir las prioridades de valor en una
      comparación cuantitativa de servicios, sujeta a validación y criterio experto.</div>
    </div>''', unsafe_allow_html=True)
    st.markdown('**Fuerza de contribución por relación (0–4)**')
    legend=''.join(
        f'<div class="pmo-vr-level pmo-vr-level-{n}" title="{explanation}">'
        f'<span class="pmo-vr-n">{n}</span><span class="pmo-vr-name">{label}</span></div>'
        for n,label,explanation in _SCALE
    )
    st.markdown('<div class="pmo-vr-legend">' + legend + '</div>',unsafe_allow_html=True)
    st.caption('El valor 0 identifica una relación no registrada en esta versión; no demuestra ausencia de valor. Los coeficientes representan una referencia de contribución y no sustituyen la validación de servicios.')
    with st.expander('Acerca de la matriz, su fuente y el control de cambios', expanded=False):
        st.markdown('''La matriz relaciona **30 resultados esperados** (filas) con **26 servicios PMO** (columnas).
        Para el cálculo del Paso 02, el motor combina las prioridades de los clientes,
        las ponderaciones expertas de sus roles y las intensidades de las relaciones resultado–servicio.
        Las ponderaciones son configurables para cada evaluación y no se infieren automáticamente del directorio.''')
        st.markdown('''**Fuente y cotejo:** el archivo `PMO_Value_Ring_Matrix.xlsx` aportado por el usuario contiene
        31 filas **incluida la cabecera**, por lo que registra **30 resultados**, no 31.
        Sus 780 coeficientes coinciden exactamente con la matriz V5 almacenada (290 relaciones positivas).
        El archivo original se conserva en la edición local; no se incluye en Cloud.
        La coincidencia numérica no constituye certificación de PMI/PMOGA ni verifica por sí sola el origen editorial.''')
        st.caption('Versiones X2 documental y escenario experimental CENS se preservan como referencias independientes. Los cambios deben registrarse mediante borrador, justificación, responsable y auditoría.')
        st.caption('Cloud: el Excel original se conserva fuera del paquete de demostración. La matriz de cálculo permanece intacta.')


def panel(diag):
    _value_ring_guide()
    st.caption('Control de versiones: X2 documental (0–1), escenario experimental CENS (0–4) y V5 (0–4). Matriz de origen del usuario cotejada contra la V5, con 780/780 coeficientes coincidentes; sin certificación PMI/PMOGA.')
    available=m.versions()
    keys=[x['id'] for x in available]
    choice=st.selectbox('Versión para inspeccionar',keys,index=keys.index(m.V5_ID),format_func=lambda x:_label(x,available),key='p2_matrix_inspect')
    current=m.version(choice)
    if choice==m.V5_ID:
        st.info('**Matriz PMO Value Ring · versión V5:** 780/780 coeficientes coincidentes con el Excel de referencia suministrado; 290 vínculos positivos. La V5 reproduce 30 ensayos FOCO y 8 históricos independientes, y registra 127 coincidencias con las 128 recomendaciones X2. O-30/S-17 requiere contraste documental. El archivo aportado no constituye certificación ni autorización institucional.')
    all_links=m.links(choice)
    enabled=sum(x['intensidad']>0 for x in all_links)
    st.caption(f"**{current['fuente']}** · {enabled} vínculos activos · 780 cruces · {current['estado']}. No se interpreta la ausencia de vínculo X2 como ausencia de valor del servicio.")
    tab1,tab2,tab3,tab4,tab5=st.tabs(['Mapa 30 × 26','Ficha y edición','Versiones y comparación','Importación y auditoría','Conformidad V5'])
    with tab1:
        a,b=st.columns(2)
        outcome=a.selectbox('Filtrar resultados',[0,*m.OUTCOMES],format_func=lambda i:'Todos' if i==0 else f'O-{i:02d} · {m.OUTCOMES[i]}',key='p2_mat_out_filter')
        service=b.selectbox('Filtrar servicios',[0,*m.SERVICES],format_func=lambda i:'Todos' if i==0 else f'S-{i:02d} · {m.SERVICES[i]}',key='p2_mat_svc_filter')
        status=a.selectbox('Estado documental',['Todos','X2_documentado','Nuevo_no_validado','No_documentado'],key='p2_mat_source_filter')
        review=a.selectbox('Estado de revisión',['Todos','DOCUMENTADO','PENDIENTE','VALIDADO','RECHAZADO','NO_DOCUMENTADO'],key='p2_mat_review_filter')
        only=b.checkbox('Mostrar solo relaciones activas',key='p2_mat_nonzero')
        focus=[r for r in all_links if (outcome==0 or r['resultado_id']==outcome)
               and (service==0 or r['servicio_id']==service)
               and (status=='Todos' or r['estado_documental']==status)
               and (review=='Todos' or r['estado_revision']==review)
               and (not only or r['intensidad']>0)]
        st.caption(f'{len(focus)} cruces encontrados')
        if not focus:st.info('No hay cruces para estos filtros.')
        else:
            detail=pd.DataFrame([{'Resultado':f"O-{r['resultado_id']:02d}", 'Servicio':f"S-{r['servicio_id']:02d}",
              'Intensidad':r['intensidad'],'X2':('Sí' if r['x2_documentado'] else 'No'),
              'HTML previo':('Sí' if r['presente_html'] else 'No'),'Estado documental':r['estado_documental'],
              'Revisión':r['estado_revision']} for r in focus])
            # Presentación condicional; conserva exactamente la tabla, filas y datos.
            from .design_system import matrix_intensity_style, matrix_status_style
            styled_detail=(detail.style
                .map(matrix_intensity_style, subset=['Intensidad'])
                .map(matrix_status_style, subset=['Estado documental','Revisión']))
            st.dataframe(styled_detail,hide_index=True,use_container_width=True,height=min(480,120+len(focus)*35))
            st.markdown('**Vista matricial de las 780 celdas**')
            wide=pd.DataFrame([{'Resultado':f'O-{o:02d}',**{f'S-{s:02d}':next(r['intensidad'] for r in all_links if r['resultado_id']==o and r['servicio_id']==s) for s in range(1,27)}} for o in range(1,31)])
            # Solo presentación de intensidad 0–4; no se modifica la matriz V5.
            styled_wide=wide.set_index('Resultado').style.map(matrix_intensity_style)
            st.dataframe(styled_wide,use_container_width=True,height=455)
        st.download_button('↓ Descargar los 780 cruces (CSV)',m.export_csv(choice),file_name=f'PMO_CENS_{choice}_780.csv',mime='text/csv',key='p2_mat_export_csv')
    with tab2:
        x,y=st.columns(2)
        o=x.selectbox('Resultado esperado',list(m.OUTCOMES),format_func=lambda i:f'O-{i:02d} · {m.OUTCOMES[i]}',key='p2_relation_outcome')
        s=y.selectbox('Servicio PMO',list(m.SERVICES),format_func=lambda i:f'S-{i:02d} · {m.SERVICES[i]}',key='p2_relation_service')
        r=next(r for r in all_links if r['resultado_id']==o and r['servicio_id']==s)
        st.markdown(f"**Correspondencia O-{o:02d} / S-{s:02d}** · Intensidad actual **{r['intensidad']}**")
        z,w=st.columns(2)
        z.caption(f"Apéndice X2: {'recomendación documentada' if r['x2_documentado'] else 'sin vínculo explícito'} · HTML anterior: {'sí' if r['presente_html'] else 'no'}")
        w.caption(f"Propuesta adicional (vista directa): {'sí' if r['propuesta_directa'] else 'no'} · (vista inversa): {'sí' if r['propuesta_inversa'] else 'no'}")
        st.caption(f"Estado documental: {r['estado_documental']} · Revisión: {r['estado_revision']}. El cero documental no prueba ausencia de contribución.")
        if current['estado']=='BORRADOR':
            with st.form('p2_matrix_edit'):
                intensity=st.number_input('Intensidad (0–4)',min_value=0,max_value=4,value=r['intensidad'],step=1)
                rev=st.selectbox('Revisión',['PENDIENTE','VALIDADO','RECHAZADO'],index=['PENDIENTE','VALIDADO','RECHAZADO'].index(r['estado_revision']) if r['estado_revision'] in ('PENDIENTE','VALIDADO','RECHAZADO') else 0)
                justification=st.text_area('Justificación técnica *',value=r['justificacion'])
                evidence=st.text_input('Evidencia o documento de respaldo',value=r['evidencia'])
                actor=st.text_input('Responsable del cambio *')
                if st.form_submit_button('Guardar cambio en borrador',type='primary'):
                    try:
                        m.edit(choice,o,s,int(intensity),actor,justification,evidence,rev)
                        st.success('Cambio guardado y auditado.');st.rerun()
                    except ValidationError as ex:st.error(str(ex))
        else:st.info('Esta versión no es editable. Puedes crear un borrador desde la pestaña Versiones y comparación.')
    with tab3:
        st.markdown('**Nueva versión editable**')
        with st.form('p2_clone_matrix'):
            code=st.text_input('Código de versión nueva *',placeholder='CENS-P2-2026-V2')
            desc=st.text_input('Objetivo y alcance de la revisión *')
            actor=st.text_input('Responsable *')
            if st.form_submit_button('Crear borrador a partir de la versión seleccionada'):
                try:m.clone(choice,code,actor,desc);st.success('Borrador completo creado; ya puede seleccionarlo y editarlo.');st.rerun()
                except ValidationError as ex:st.error(str(ex))
        st.markdown('**Comparación celda a celda**')
        other=st.selectbox('Comparar contra',keys,index=keys.index(m.EXPERIMENT_ID) if choice!=m.EXPERIMENT_ID else keys.index(m.DOC_ID),key='p2_mat_comp')
        if other!=choice:
            diffs=m.comparison(choice,other)
            st.metric('Intensidades diferentes',len(diffs))
            if diffs:st.dataframe(pd.DataFrame(diffs),hide_index=True,use_container_width=True,height=280)
            else:st.caption('Las 780 celdas coinciden.')
            st.markdown('**Simulación comparativa del ranking con la muestra actual**')
            from . import step2 as p2
            saved=p2.saved_weights(diag)
            complete=p2._participant_records(diag)
            groups={x['group'] for x in complete if len(x['priorities'])==5}
            if saved and set(saved)==groups and groups:
                if st.button('Comparar rankings sin guardar una corrida',key='p2_mat_simulate'):
                    try:
                        left=p2.compute(diag,saved,m.matrix(choice))
                        right=p2.compute(diag,saved,m.matrix(other))
                        l={r['id']:r for r in left['services']}
                        r={r['id']:r for r in right['services']}
                        positions_left={x['id']:i+1 for i,x in enumerate(left['services'])}
                        positions_right={x['id']:i+1 for i,x in enumerate(right['services'])}
                        comparison=[{'Servicio':f'S-{sid:02d} · {m.SERVICES[sid]}',
                            choice+' (%)':round(l[sid]['score'],3),other+' (%)':round(r[sid]['score'],3),
                            'Diferencia (pp)':round(r[sid]['score']-l[sid]['score'],3),
                            'Cambio de posición':positions_left[sid]-positions_right[sid]} for sid in m.SERVICES]
                        st.session_state[f'p2_mat_sim_{diag}']=(choice,other,comparison)
                    except ValidationError as ex:st.error(str(ex))
                sim=st.session_state.get(f'p2_mat_sim_{diag}')
                if sim and sim[:2]==(choice,other):
                    st.dataframe(pd.DataFrame(sim[2]),hide_index=True,use_container_width=True,height=345)
                    st.caption('Comparación de sensibilidad con ponderaciones guardadas y respuestas actuales. No modifica ni aprueba versiones, ni sustituye corridas históricas.')
            else:st.caption('Para comparar rankings, registre cinco expectativas por cliente y guarde los pesos de todos los grupos participantes.')
    with tab4:
        if current['estado']=='BORRADOR':
            st.markdown('**Importar intensidades al borrador**')
            sheet=st.selectbox('Hoja del Excel de revisión',['MATRIZ_PMI_0_1','MATRIZ_ESCENARIO'],key='p2_mat_sheet')
            uploaded=st.file_uploader('Archivo CSV o XLSX de matriz',type=['csv','xlsx'],key='p2_mat_file')
            if uploaded:
                try:
                    matrix=m.read_uploaded_matrix(uploaded.getvalue(),uploaded.name,sheet)
                    count=sum(len(x) for x in matrix.values())
                    st.caption(f'Matriz válida: {count} celdas explícitas · {sum(v>0 for x in matrix.values() for v in x.values())} vínculos activos.')
                    zero=st.checkbox('El archivo es disperso: aceptar que los pares ausentes se conviertan en cero',key='p2_mat_zero')
                    actor=st.text_input('Responsable de importación *',key='p2_mat_imp_actor')
                    reason=st.text_input('Motivo de carga *',key='p2_mat_imp_reason')
                    if st.button('Confirmar reemplazo del borrador',type='primary',disabled=(count!=780 and not zero)):
                        try:
                            changed=m.replace_from_import(choice,matrix,actor,reason,zero_missing=zero)
                            st.success(f'Borrador actualizado: {changed} celdas cambiaron.');st.rerun()
                        except ValidationError as ex:st.error(str(ex))
                except ValidationError as ex:st.error(str(ex))
        else:st.caption('Para importar, primero crea y selecciona un borrador.')
        st.markdown('**Control documental de versiones**')
        st.warning('La identidad del responsable es declarativa: este MVP local no cuenta con SSO, autorización institucional ni firma. Los estados NO sustituyen aprobación formal de CENS.')
        if current['estado'] in ('BORRADOR','EN_REVISION','APROBADA'):
            options={'BORRADOR':['EN_REVISION','ARCHIVADA'],'EN_REVISION':['BORRADOR','APROBADA'],'APROBADA':['ARCHIVADA']}
            with st.form('p2_mat_change_status'):
                new=st.selectbox('Registrar transición',options[current['estado']])
                actor=st.text_input('Responsable que documenta la decisión *')
                justification=st.text_input('Acta/referencia y fundamento de la decisión *')
                confirm=st.checkbox('Confirmo que la decisión tiene respaldo documental verificable')
                if st.form_submit_button('Registrar decisión',disabled=not confirm):
                    try:m.change_status(choice,new,actor,justification);st.success('Transición documentada; la versión aprobada queda inmutable.');st.rerun()
                    except ValidationError as ex:st.error(str(ex))
        changes=m.history(choice)
        if changes:st.dataframe(changes,hide_index=True,use_container_width=True,height=320)
        else:st.caption('Versión de referencia sin cambios de usuario.')

    with tab5:
        st.info('Cloud: los 38 archivos de escenarios históricos no se distribuyen. Puedes ensayar nuevas corridas con datos ficticios y el motor V5 original.')
