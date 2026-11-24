"""Interfaz ejecutiva de Clientes internos (Paso 01) — V0.24.

Sin rutas nuevas: se llama desde pmo.ui.clients_page(). Usa pmo_clientes,
la misma configuración y los mismos identificadores que los pasos 2–10.
"""
from __future__ import annotations

import html
import io
from datetime import date

import streamlit as st
from .clients import ValidationError, get_client, list_clients, dependencies, audit_history
from .v0391_clients import client_role,stakeholder_matrix,QUADRANTS,export_full_directory_xlsx
from .client_forms import client_form, _csv_bytes
from . import awareness as aw
from .interactions import metrics as contact_metrics
from .panel_superior import render_kpi_card_panel, render_clients_heading, render_contact_note, render_directory_header
from .client_directory import (
    DEFAULT_VISIBLE, DISPLAY_COLUMNS, custom_columns, custom_values_for_clients,
    add_custom_column, remove_custom_column, save_custom_values,
    remove_clients, delete_clients_quick, backup_clients_database, read_client_sheets, suggested_mapping, mapped_client_import,
    export_clients_csv,

)


def esc(v):
    return html.escape(str(v if v is not None else ''))


def apply_clients_style():
    st.markdown('''<style>
    /* Sólo estilos del módulo de clientes. El CSS de los otros 9 pasos no se toca. */
    .pmo-card-title{font-size:18px;font-weight:780;color:#192746;margin:1px 0 4px}
    .pmo-card-subtitle{font-size:11px;color:#77869C;margin-bottom:12px}
    .pmo-detail-header{background:linear-gradient(115deg,#F7F9FF,#EDF3FF);border:1px solid #E1E7F9;
      padding:15px;border-radius:13px;margin:6px 0 12px}
    .pmo-detail-name{font-size:15px;font-weight:780;color:#152747;margin:3px 0}
    .pmo-detail-secondary{font-size:11px;color:#687990;line-height:1.5}
    .pmo-detail-badge{display:inline-block;background:#EDEAFB;color:#51468E;border-radius:99px;
      padding:4px 10px;font-size:10px;font-weight:650;margin-top:8px}
    .pmo-field-pair{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;
      font-size:11px;padding:8px 0;border-bottom:1px solid #EEF1F6}
    .pmo-field-pair span{color:#7D899A;max-width:45%}
    .pmo-field-pair b{text-align:right;color:#243651;overflow-wrap:anywhere;max-width:55%;font-weight:650}
    .pmo-sectionhint{font-size:11px;color:#6C7E94}
    [data-testid="stDataFrame"]{border:1px solid #E6EBF4;border-radius:11px;overflow:hidden}
    </style>''',unsafe_allow_html=True)


def metric_card(label,value,sub,icon_name,theme):
    # Presentación solamente: los valores se calculan en render_client_directory.
    st.markdown(render_kpi_card_panel(label=label,value=value,subtext=sub,
                                      icon_name=icon_name,theme=theme),unsafe_allow_html=True)


def detail(label,value):
    st.markdown(f'<div class="pmo-field-pair"><span>{esc(label)}</span><b>{esc(value if value not in (None,"") else "Sin registrar")}</b></div>',unsafe_allow_html=True)


@st.dialog('Registrar cliente',width='large')
def new_dialog():
    client_form()


@st.dialog('Editar ficha del cliente',width='large')
def edit_dialog(row):
    client_form(row)


@st.dialog('Editar columnas personalizadas del cliente',width='large')
def edit_extra_dialog(row):
    fields=custom_columns()
    if not fields:
        st.info('Todavía no existen columnas personalizadas. Cree una desde «Gestionar columnas».')
        return
    values=custom_values_for_clients([row['id']]).get(row['id'],{})
    with st.form('edit_extra_fields'):
        st.caption('Estos datos quedan vinculados al código del cliente en la base SQLite.')
        edited={}
        for f in fields:
            if f['tipo']=='Fecha':
                edited[f['id']]=st.text_input(f['nombre']+' · AAAA-MM-DD',value=values.get(f['id'],'') or '')
            else:
                edited[f['id']]=st.text_input(f['nombre'],value=values.get(f['id'],'') or '')
        actor=st.text_input('Modificado por *',key='extra_actor')
        send=st.form_submit_button('Guardar valores',type='primary')
    if send:
        try:
            save_custom_values(row['id'],edited,actor)
            st.session_state['pmo_clients_notice']='Campos personalizados guardados.'
            st.rerun()
        except ValidationError as exc:st.error(str(exc))


@st.dialog('Gestionar columnas',width='large')
def columns_dialog():
    defs=custom_columns()
    st.caption('Muestre u oculte campos de la tabla o agregue columnas propias al directorio, sin modificar los otros pasos.')
    known={**{k:v for k,v in DISPLAY_COLUMNS.items() if k!='segmento'}, **{'extra:'+r['id']:r['nombre'] for r in defs}}
    current=[x for x in st.session_state.get('pmo_clients_visible_cols',DEFAULT_VISIBLE) if x in known]
    selected=st.multiselect('Columnas visibles',options=list(known),default=current,
                            format_func=lambda key:known[key],key='pmo_clients_columns_selector')
    if st.button('Aplicar columnas',type='primary',key='apply_column_settings'):
        if not selected or 'nombre' not in selected:
            st.error('Mantenga visible al menos la columna Cliente.')
        else:
            st.session_state['pmo_clients_visible_cols']=selected
            st.rerun()
    st.divider()
    with st.form('new_custom_field'):
        st.markdown('**Añadir columna al directorio**')
        a,b=st.columns([2,1])
        name=a.text_input('Nombre del nuevo campo')
        kind=b.selectbox('Tipo',['Texto','Número','Fecha'])
        actor=st.text_input('Responsable *',key='column_creator')
        submit=st.form_submit_button('Agregar columna')
    if submit:
        try:
            col_id=add_custom_column(name,kind,actor)
            st.session_state['pmo_clients_visible_cols']=[*current,'extra:'+col_id]
            st.session_state['pmo_clients_notice']='Columna creada y disponible en el directorio.'
            st.rerun()
        except ValidationError as exc:st.error(str(exc))
    if defs:
        with st.expander('Eliminar una columna personalizada'):
            st.warning('Eliminar una columna personalizada borra sus valores. No afecta los campos estándar ni los diez pasos.')
            target=st.selectbox('Columna',options=[r['id'] for r in defs],format_func=lambda val:next(r['nombre'] for r in defs if r['id']==val))
            actor2=st.text_input('Responsable de la eliminación',key='column_deleter')
            confirmed=st.checkbox('Confirmo que deseo eliminar la columna y sus valores',key='column_remove_confirm')
            if st.button('Eliminar columna',disabled=not confirmed):
                try:
                    remove_custom_column(target,actor2)
                    st.session_state['pmo_clients_visible_cols']=[x for x in current if x!='extra:'+target]
                    st.session_state['pmo_clients_notice']='Columna personalizada eliminada.'
                    st.rerun()
                except ValidationError as exc:st.error(str(exc))


@st.dialog('Confirmar eliminación de clientes',width='small')
def remove_dialog(ids):
    ids=list(dict.fromkeys(ids))
    st.markdown(f'**¿Estás seguro de quitar {len(ids)} cliente(s) del directorio?**')
    st.caption('Se eliminarán los registros sin vínculos. Si tienen actividades o evaluaciones, se ocultarán del directorio activo y se conservará su historial.')
    cancel, confirm = st.columns(2)
    if cancel.button('Cancelar',use_container_width=True,key='pmo_cancel_delete'):
        st.rerun()
    if confirm.button('Sí, eliminar',type='primary',use_container_width=True,key='pmo_confirm_delete'):
        try:
            backup_clients_database()
            outcome=delete_clients_quick(ids,actor='Operador PMO (interfaz, sin autenticación)')
            st.session_state.pop('current_client_id',None)
            st.session_state['pmo_clients_notice']=(
                f'{outcome["eliminados"]} cliente(s) eliminado(s); '
                f'{outcome["archivados"]} archivado(s) por tener registros vinculados. '
                'Se conservaron los datos de los demás pasos.')
            st.rerun()
        except ValidationError as exc: st.error(str(exc))


@st.dialog('Importar clientes desde Excel',width='large')
def import_dialog():
    st.caption('Carga la misma base de Clientes PMO 1.xlsx tantas veces como necesites. Identifica cada cliente por su código: actualiza los existentes y añade los nuevos, sin duplicar registros.')
    uploaded=st.file_uploader('Adjunta el archivo .xlsx (máximo 8 MB)',type=['xlsx'],key='pmo_clients_excel_uploader')
    if not uploaded:return
    try:
        sheets=read_client_sheets(uploaded.getvalue())
    except ValidationError as exc:
        st.error(str(exc));return
    suggested='Clientes' if 'Clientes' in sheets else ('Mapa Clientes Potenciales' if 'Mapa Clientes Potenciales' in sheets else next(iter(sheets)))
    names=list(sheets)
    selected=st.selectbox('Hoja para importar',names,index=names.index(suggested),key='pmo_clients_excel_sheet')
    raw=sheets[selected]
    headers=list(dict.fromkeys(k for _,r in raw for k in r))
    st.success(f'Archivo leído correctamente · {len(raw)} registro(s) · {len(headers)} columnas')
    st.markdown('**Correspondencia de columnas**')
    extras=custom_columns()
    defaults=suggested_mapping(headers,extras)
    pick=['codigo','nombre','dependencia','cargo','equipo_trabajo','rol_especifico','estado_gestion','influencia','interes',
          'activo','embajador', 'observaciones','correo', 'relacionamiento']
    allfields=list(dict.fromkeys([*pick,*(k for k in DISPLAY_COLUMNS if k!='segmento'), *['extra:'+r['id'] for r in extras]]))
    mapping={}
    choices=['— No importar —',*headers]
    group_basic=allfields[:len(pick)]
    for labelgroup, group in [('Campos principales',group_basic),('Campos adicionales',allfields[len(pick):])]:
        with st.expander(labelgroup,expanded=labelgroup=='Campos principales'):
            for i in range(0,len(group),2):
                cols=st.columns(2)
                for col,key in zip(cols,group[i:i+2]):
                    description=DISPLAY_COLUMNS.get(key,next((d['nombre'] for d in extras if 'extra:'+d['id']==key),key))
                    choice=defaults.get(key,'')
                    mapping[key]=col.selectbox(description,choices,index=choices.index(choice) if choice in choices else 0,
                                               key=f'pmo_map_{selected}_{key}')
    mapping={k:('' if v==choices[0] else v) for k,v in mapping.items()}
    st.caption('El campo Rol es único y sirve para la clasificación y la ponderación por criterio experto. Los valores históricos se conservan en auditoría.')
    st.caption('Dependencia y Equipo de trabajo son campos organizacionales distintos.')
    operation=st.radio('Qué hacer con códigos que ya existen',
                       ['Actualizar existentes y agregar nuevos','Agregar solamente clientes nuevos'],
                       index=0,key='pmo_clients_import_mode',horizontal=False)
    import_mode='upsert' if operation.startswith('Actualizar') else 'add'
    overwrite_blanks=False
    if import_mode=='upsert':
        overwrite_blanks=st.checkbox('Sobrescribir también campos vacíos (borrar valores existentes)',
                                     value=False,key='pmo_clients_import_clear_blanks',
                                     help='Desactivado: las celdas vacías nunca borran datos que ya existen. Los campos Sí/No se actualizan solo con un valor explícito.')
        if overwrite_blanks:
            st.warning('Atención: las celdas vacías del archivo podrán borrar información de los campos mapeados. El código, nombre y dependencia no se borrarán. Comprueba el resumen antes de confirmar.')
    actor=st.text_input('Responsable de la importación *',key='pmo_clients_import_actor')
    if not actor:
        st.info('Indica un responsable para activar la vista previa y la importación. No se han guardado datos todavía.');return
    try:
        preview=mapped_client_import(raw,mapping,actor,confirm=False,mode=import_mode,overwrite_blanks=overwrite_blanks)
    except ValidationError as exc:
        st.error(str(exc));return
    totals={k:sum(r['Acción']==k for r in preview)
            for k in ('Nuevo','Actualizado','Sin cambios','Duplicado','Error')}
    a,b,c=st.columns(3)
    a.metric('Nuevos',totals['Nuevo'])
    b.metric('Actualizados',totals['Actualizado'])
    c.metric('Sin cambios',totals['Sin cambios']+totals['Duplicado'])
    st.caption(f'Vista previa · {len(preview)} filas · Errores: {totals["Error"]}. No se ha guardado ningún cambio.')
    st.dataframe(preview,hide_index=True,use_container_width=True,height=min(320,35+len(preview)*31))
    if totals['Error']:
        st.error('Hay errores de validación. No se aplicará ninguna fila hasta corregirlos.')
        return
    to_apply=totals['Nuevo']+totals['Actualizado']
    if not to_apply:
        st.info('El archivo ya está sincronizado: no hay clientes nuevos ni cambios para guardar.');return
    if st.button(f'Confirmar: {totals["Nuevo"]} nuevos y {totals["Actualizado"]} actualizaciones',
                 type='primary',use_container_width=True,key='pmo_import_save'):
        try:
            backup_clients_database()
            applied=mapped_client_import(raw,mapping,actor,confirm=True,
                                          mode=import_mode,overwrite_blanks=overwrite_blanks)
            if any(x['Acción']=='Error' for x in applied):
                st.error('La confirmación encontró errores: se revirtió la carga completa.');return
            st.session_state['pmo_clients_notice']=(
                f'{sum(x["Acción"]=="Nuevo" for x in applied)} nuevos; '
                f'{sum(x["Acción"]=="Actualizado" for x in applied)} actualizados; '
                f'{sum(x["Acción"] in ("Sin cambios","Duplicado") for x in applied)} sin cambios. '
                'Se conservaron los identificadores y relaciones existentes y se creó respaldo previo.')
            st.rerun()
        except ValidationError as exc: st.error(str(exc))


def render_client_directory():
    apply_clients_style()
    if notice:=st.session_state.pop('pmo_clients_notice',None):st.success(notice)
    if st.session_state.pop('pmo_clients_open_import',False):import_dialog()

    heading,actions=st.columns([1.2,2.1],vertical_alignment='bottom',gap='medium')
    with heading:
        st.markdown(render_clients_heading(),unsafe_allow_html=True)
    with actions:
        a,b,c,d=st.columns([1.05,1.1,1.4,1.08],gap='small')
        if a.button('Nuevo cliente',icon=':material/person_add:',type='primary',use_container_width=True,key='pmo_c_new'):
            new_dialog()
        if b.button('Importar Excel',icon=':material/upload_file:',use_container_width=True,key='pmo_c_import'):
            import_dialog()
        if c.button('Gestionar columnas',icon=':material/view_column:',use_container_width=True,key='pmo_c_cols'):
            columns_dialog()
        # el borrado se habilita debajo, tras la selección múltiple del grid.
        pressed_delete=d.button('Quitar clientes',icon=':material/delete_outline:',use_container_width=True,key='pmo_c_del')

    people=list_clients()
    active=[r for r in people if r['activo']]
    # Un solo indicador verificable: cliente único con interacción o consulta registrada.
    # El estado manual de relacionamiento NO acredita contacto.
    contacted=contact_metrics()['contacted']
    for col,args in zip(st.columns(4,gap='medium'),[
        ('Clientes identificados',len(active),'Activos en el directorio','users','orange'),
        ('Dependencias registradas',len({r['dependencia'].casefold() for r in active}),'Con clientes activos','layers','blue'),
        ('Embajadores',sum(bool(r['embajador']) for r in active),'Marcados en el directorio','award','purple'),
        ('Clientes contactados',f'{contacted/len(active):.0%}' if active else 'Sin datos','Interacción o consulta documentada','clock','teal'),
    ]):
        with col:metric_card(*args)

    st.markdown(render_contact_note(),unsafe_allow_html=True)
    st.caption('Rol: clasificación única del directorio que alimenta las ponderaciones expertas del Paso 02. Los pesos y resultados históricos no se modifican.')

    left,right=st.columns([2.15,1],gap='medium')
    selection_ids=[]
    selected_id=None
    with left:
        with st.container(border=True):
            st.markdown(render_directory_header(len(people)),unsafe_allow_html=True)
            f1,f2,f3=st.columns([1.4,1,0.9],gap='small')
            query=f1.text_input('Buscar',placeholder='Buscar por nombre, código o cargo...',label_visibility='collapsed',key='pmo_c_search')
            deps=dependencies()
            dep=f2.selectbox('Dependencia',['Todas',*deps],label_visibility='collapsed',key='pmo_c_department')
            status=f3.selectbox('Estado',['Activos','Todos','Inactivos'],label_visibility='collapsed',key='pmo_c_status')
            rows=list_clients(query, '' if dep=='Todas' else dep, status)
            st.caption(f'{len(rows)} cliente(s) según los filtros · Selecciona filas para editar o quitar.')
            select_all=st.checkbox('Seleccionar todos los clientes filtrados para eliminación',
                                   value=False,key='pmo_c_select_all',disabled=not bool(rows))
            extras=custom_columns()
            labels={**DISPLAY_COLUMNS, **{'extra:'+x['id']:x['nombre'] for x in extras}}
            labels['rol_especifico']='Rol'
            labels.pop('segmento',None)
            raw_visible=st.session_state.get('pmo_clients_visible_cols',DEFAULT_VISIBLE)
            visible=[key for key in raw_visible if key in labels]
            visible=['rol_especifico' if key=='segmento' else key for key in visible]
            visible=list(dict.fromkeys(visible))
            if not visible:visible=DEFAULT_VISIBLE
            vmap=custom_values_for_clients([r['id'] for r in rows])
            data=[]
            for r in rows:
                entry={}
                for key in visible:
                    if key=='activo':value='Activo' if r['activo'] else 'Inactivo'
                    elif key=='embajador':value='Sí' if r['embajador'] else 'No'
                    elif key=='rol_especifico':value=client_role(r)
                    elif key.startswith('extra:'):value=vmap.get(r['id'],{}).get(key[6:],'')
                    else:value=r.get(key,'')
                    entry[labels[key]]=value
                data.append(entry)
            if rows:
                # Una selección anterior no debe aplicarse a otra lista filtrada.
                import hashlib
                grid_ids=hashlib.sha256('|'.join(r['id'] for r in rows).encode()).hexdigest()[:16]
                result=st.dataframe(data,hide_index=True,use_container_width=True,height=min(550,max(220,56+len(rows)*34)),
                                    on_select='rerun',selection_mode='multi-row',key='pmo_c_grid_'+grid_ids+'_'+str(st.session_state.get('b02_grid_generation',0)))
                indices=result.selection.rows if result and result.selection else []
                selection_ids=([r['id'] for r in rows] if select_all else
                               [rows[idx]['id'] for idx in indices if 0 <= idx < len(rows)])
                selected_id=selection_ids[0] if selection_ids else (st.session_state.get('current_client_id') if st.session_state.get('current_client_id') in {r['id'] for r in rows} else rows[0]['id'])
                st.session_state['current_client_id']=selected_id
            else:
                st.info('No se encontraron clientes con estos filtros.')
                st.session_state.pop('current_client_id',None)
            low1,low2=st.columns([1,1],gap='small')
            with low1:
                st.download_button('Exportar directorio completo',data=export_full_directory_xlsx(rows),
                    file_name='PMO_CENS_Directorio_Clientes_V0391.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',icon=':material/download:',
                    use_container_width=True,key='pmo_c_export')
            with low2:
                if st.button(f'Quitar seleccionados ({len(selection_ids)})',icon=':material/delete:',
                             disabled=not selection_ids,use_container_width=True,key='pmo_c_remove_selected'):
                    remove_dialog(selection_ids)
            if selection_ids:
                st.caption(f'{len(selection_ids)} seleccionados. El borrado no depende del orden de las filas.')
        with st.container(border=True):
            st.markdown('**Matriz de stakeholders · Influencia e interés**')
            st.caption('Distribución dinámica de los clientes filtrados. Los niveles Medios o Sin evaluar quedan pendientes, sin asignación arbitraria.')
            parts=stakeholder_matrix(rows)
            colors={'Latentes':'#F28C3B','Promotores':'#B85050','Apáticos':'#858C96','Defensores':'#8D9161'}
            cells=st.columns(2,gap='small')
            for idx,(name,action,power,interest) in enumerate(QUADRANTS):
                with cells[idx%2]:
                    count=len(parts[name])
                    st.markdown(f'<div style="background:{colors[name]};color:white;border-radius:10px;padding:12px 14px;min-height:105px;text-align:center"><div style="font-size:11px;font-weight:800">{name.upper()}</div><div style="font-size:31px;font-weight:850">{count}</div><div style="font-size:12px;font-weight:700">{action.upper()}</div></div>',unsafe_allow_html=True)
                    with st.expander(f'Ver {name.lower()} ({count})'):
                        st.dataframe([{'Código':c['codigo'],'Cliente':c['nombre'],'Dependencia':c['dependencia'],'Rol':client_role(c)} for c in parts[name]],hide_index=True,use_container_width=True)
            missing=parts['Pendientes de clasificación']
            st.caption(f"Clasificados: {len(rows)-len(missing)} · Pendientes (Media/Medio/Sin evaluar): {len(missing)} · Total filtrado: {len(rows)}")
            if missing:
                with st.expander(f'Consultar pendientes de clasificación ({len(missing)})'):
                    st.dataframe([{'Código':c['codigo'],'Cliente':c['nombre'],'Influencia':c['influencia'],'Interés':c['interes']} for c in missing],hide_index=True,use_container_width=True)


    if pressed_delete:
        if selection_ids:remove_dialog(selection_ids)
        else:st.warning('Primero selecciona uno o más clientes en el directorio.')

    with right:
        with st.container(border=True):
            st.markdown('<div class="pmo-card-title">Ficha del cliente</div><div class="pmo-card-subtitle">Vista unificada de relacionamiento.</div>',unsafe_allow_html=True)
            client=get_client(selected_id) if selected_id else None
            if not client:
                st.info('Selecciona un cliente para ver su ficha.')
            else:
                initials=''.join(s[:1] for s in client['nombre'].split()[:2]).upper()
                st.markdown(f'<div class="pmo-detail-header"><div style="font-size:20px;font-weight:850;color:#4056A3">{esc(initials)}</div><div class="pmo-detail-name">{esc(client["nombre"])}</div><div class="pmo-detail-secondary">{esc(client["cargo"])} · {esc(client["dependencia"])}</div><div class="pmo-detail-badge">{esc("Embajador" if client["embajador"] else client["relacionamiento"] or "Sin contacto")}</div></div>',unsafe_allow_html=True)
                detail('Código corporativo',client['codigo'])
                detail('Equipo de trabajo',client.get('equipo_trabajo'))
                detail('Rol',client_role(client))
                detail('Estado de gestión',client.get('estado_gestion'))
                detail('Influencia',client['influencia'])
                detail('Interés',client['interes'])
                detail('Conocimiento PMO',client['conocimiento'] if client['conocimiento'] is not None else 'Sin evaluar')
                detail('Canal preferido',client['canal'])
                detail('Correo',client['correo'])
                detail('Cliente activo','Sí' if client['activo'] else 'No')
                with st.expander('Necesidades preliminares'):
                    st.write(client['necesidades_preliminares'] or 'Sin información registrada.')
                vals=custom_values_for_clients([client['id']]).get(client['id'],{})
                custom=custom_columns()
                if custom:
                    with st.expander('Campos personalizados'):
                        for f in custom: detail(f['nombre'],vals.get(f['id']))
                        if st.button('Editar campos personalizados',use_container_width=True):edit_extra_dialog(client)
                history=aw.client_history(client['id'])
                st.caption(f"Historial: {history['events']} eventos · {history['tickets']} consultas · {history['surveys']} encuestas")
                if st.button('Editar ficha',icon=':material/edit:',use_container_width=True,key='pmo_c_edit'):
                    edit_dialog(client)
                with st.expander('Historial de cambios'):
                    st.dataframe(audit_history(client['id']),hide_index=True,use_container_width=True)
                def goto_step2():
                    st.session_state['pmo_step2_client']=client['id']
                    st.session_state['pmo_active_step']='Paso 02 · Evaluación de necesidades'
                    st.session_state['pmo_active_p2_page']='Clientes y levantamiento'
                st.button('Evaluar necesidades →',key='pmo_c_goto_step2',on_click=goto_step2,use_container_width=True)
                st.caption('El vínculo utiliza el mismo ID: no duplica clientes entre pasos.')
    if selected_id and st.checkbox('Abrir ficha 360° del cliente seleccionado',key='alpha02_open_client360'):
        from .alpha02_clients import render_client
        selected_client=get_client(selected_id)
        if selected_client:render_client(selected_client)
