"""Vista unificada del Paso 01: Portal de valor y biblioteca V0.28.
Mantiene los menús del aplicativo, almacena cambios en SQLite y archivos locales.
"""
from __future__ import annotations

from datetime import date
from html import escape
import streamlit as st
from .staff_picker import staff_picker

from . import library_portal as lib
from .clients import ValidationError, list_clients

STYLE = __import__('pathlib').Path(__file__).resolve().parent / 'assets' / 'portal_value.css'


def _styles():
    st.markdown('<style>\n'+STYLE.read_text(encoding='utf-8')+'\n</style>',unsafe_allow_html=True)


def _navigate(page):
    # Callback anterior a la creación del st.radio de navegación lateral.
    st.session_state['pmo_active_page']=page
    st.session_state['pmo_excel_active']=False


def _kpi(label,value,foot,icon):
    from .panel_superior import render_kpi_card_panel
    themes={'▣':('book','orange'),'◇':('layers','blue'),
            '♙':('users','purple'),'⇩':('chart','teal')}
    icon_name,theme=themes.get(icon,('chart','orange'))
    st.markdown(render_kpi_card_panel(label=label,value=value,subtext=foot,
                                      icon_name=icon_name,theme=theme),unsafe_allow_html=True)


def _resource_card(r,with_manage=False,scope="biblioteca"):
    rid=r['id']
    with st.container(border=True):
        tag='SERVICIO PMO' if r['tipo']=='Servicio' else ('EXPERIENCIA' if r['tipo']=='Historia' else r['categoria'].upper())
        st.markdown(f'<div class="portal-item-tag">{escape(tag)}</div>',unsafe_allow_html=True)
        st.markdown(f'<div class="portal-item-title">{escape(r["titulo"])}</div>',unsafe_allow_html=True)
        st.caption((r['descripcion'] or 'Sin descripción registrada')[:180])
        st.markdown(f'<div class="portal-meta">{escape(r["estado"])} · Versión {escape(r['version'] or 'Sin versión')} · {escape(r["acceso"])}'
                    f' · {int(r["archivos_count"])} archivo(s)</div>',unsafe_allow_html=True)
        if r['publico']: st.caption('Dirigido a: '+r['publico'])
        with st.expander('Consultar ficha y archivos'):
            st.write('**Responsable:**',r['responsable'])
            st.write('**Autor:**',r['autor'] or 'Sin información registrada')
            st.write('**Publicado:**',r['publicado_en'] or 'Sin información registrada')
            if r['url']:
                st.markdown(f'[Abrir recurso web]({r["url"]})')
            if r['acceso']=='Restringido':
                st.warning('Este recurso está marcado como restringido. La descarga se deshabilita en esta vista; no existe autenticación por roles en el aplicativo local.')
            files=lib.list_files(rid)
            if not files and not r['url']: st.caption('Sin archivo o enlace registrado.')
            if files:
                st.markdown('**Archivos y versiones**')
                for f in files:
                    st.caption(f"{f['nombre_original']} · v{f['version']} · {f['estado']} · {f['creado_en'][:10]}")
                    if r['acceso']!='Restringido':
                        try:
                            data=lib.read_file(f['id'])
                            if f['mime'].startswith('image/') and f['estado']=='Vigente':
                                st.image(data,caption=f['nombre_original'],use_container_width=True)
                            st.download_button('Descargar '+f['nombre_original'],data=data,
                                file_name=f['nombre_original'],mime=f['mime'],key=f'pv_dl_{scope}_{rid}_{f["id"]}',
                                on_click=lib.register_interaction,
                                args=(rid,'Descarga iniciada','Operación desde biblioteca'))
                        except (ValidationError,OSError) as err:st.error(str(err))
            if r['estado']!='Archivado' and r['tipo']!='Servicio':
                if st.button('Registrar consulta de cliente',key=f'pv_consult_{scope}_{rid}',use_container_width=True):
                    _consult_dialog(rid)
        if with_manage:
            a,b=st.columns(2)
            if a.button('Editar',key=f'pv_edit_{scope}_{rid}',use_container_width=True):_resource_dialog(rid)
            if b.button('Archivar',key=f'pv_archive_{scope}_{rid}',use_container_width=True):_archive_dialog(rid)


@st.dialog('Recurso de la PMO',width='large')
def _resource_dialog(resource_id=None,kind='Material'):
    prior=lib.get_resource(resource_id) if resource_id else None
    if resource_id and not prior:
        st.error('El recurso no existe.');return
    st.caption('Los archivos se guardan en el directorio local del ciclo, fuera del ZIP de la aplicación.')
    # Los servicios nuevos se caracterizan en el Paso 04; se conserva solo la edición de recursos locales históricos.
    kinds=[k for k in lib.KINDS if k != 'Servicio']
    if prior:
        selected_kind=prior['tipo']
        st.caption('Tipo: '+selected_kind)
    else:
        selected_kind=st.selectbox('Tipo de recurso',kinds,index=kinds.index(kind),key='pv_kind_'+kind)
    with st.form('pv_resource_form'):
        a,b=st.columns([1.7,1])
        title=a.text_input('Título *',value=(prior or {}).get('titulo',''))
        category=b.selectbox('Categoría',list(lib.CATEGORIES),index=(list(lib.CATEGORIES).index(prior['categoria'])
                  if prior and prior['categoria'] in lib.CATEGORIES else len(lib.CATEGORIES)-1))
        custom_category=st.text_input('Categoría personalizada (si seleccionó Otros)',
                        value=(prior['categoria'] if prior and prior['categoria'] not in lib.CATEGORIES else ''))
        description=st.text_area('Descripción',value=(prior or {}).get('descripcion',''),height=78)
        url=st.text_input('Enlace web (opcional)',value=(prior or {}).get('url',''))
        c,d=st.columns(2)
        allowed=list(lib.SERVICE_STATUSES if selected_kind=='Servicio' else lib.RESOURCE_STATUSES)
        status=c.selectbox('Estado',allowed,index=(allowed.index(prior['estado']) if prior and prior['estado'] in allowed else 0))
        access=d.selectbox('Acceso',list(lib.ACCESS),index=list(lib.ACCESS).index((prior or {}).get('acceso','Interno')))
        e,f=st.columns(2)
        owner=staff_picker('Responsable *',value=(prior or {}).get('responsable',''))
        author=f.text_input('Autor / fuente',value=(prior or {}).get('autor',''))
        g,h=st.columns(2)
        version=g.text_input('Versión *',value=((prior or {}).get('version') or '1.0'))
        audience=h.text_input('Público objetivo',value=(prior or {}).get('publico',''))
        publication=st.date_input('Fecha de publicación / actualización',value=(
            date.fromisoformat(prior['publicado_en']) if prior and prior.get('publicado_en') else None), format='YYYY/MM/DD')
        file=st.file_uploader('Adjuntar o reemplazar archivo (opcional, máximo 20 MB)',
             type=sorted(lib.EXTENSIONS),key=f'pv_upload_{resource_id or "new"}')
        actor=st.text_input('Registrado / actualizado por *')
        submit=st.form_submit_button('Guardar recurso',type='primary',use_container_width=True)
    if submit:
        try:
            data=file.getvalue() if file else None
            if data is not None:lib._validate_file(file.name,data)
            rid=lib.save_resource(resource_id=resource_id,title=title,
               category=custom_category.strip() if category=='Otros' and custom_category.strip() else category,
               description=description,url=url,kind=selected_kind,status=status,owner=owner,
               actor=actor,author=author,version=version,audience=audience,
               access=access,publication_date=publication.isoformat() if publication else '')
            if data is not None:lib.save_file(rid,file.name,data,actor,version)
            st.session_state['pv_success']='Recurso guardado. Sus datos permanecen disponibles después de reiniciar.'
            st.rerun()
        except (ValidationError,OSError,ValueError) as err:st.error(str(err))


@st.dialog('Confirmar archivo del recurso')
def _archive_dialog(resource_id):
    r=lib.get_resource(resource_id)
    if not r:st.error('No se encontró el recurso.');return
    st.warning(f'¿Estás seguro de archivar «{r["titulo"]}»? Se conservarán sus archivos, versiones y registros anteriores.')
    actor=st.text_input('Responsable de la acción *')
    if st.button('Sí, archivar',type='primary',use_container_width=True):
        try:
            lib.archive_resource(resource_id,actor)
            st.session_state['pv_success']='Recurso archivado sin borrar evidencias.'
            st.rerun()
        except ValidationError as err:st.error(str(err))


@st.dialog('Registrar consulta de recurso')
def _consult_dialog(resource_id):
    people=[r for r in list_clients() if r.get('activo')]
    if not people:
        st.info('Primero registre clientes en el directorio.');return
    by_id={x['id']:x for x in people}
    selected=st.selectbox('Cliente que consultó el recurso *',list(by_id),
                          format_func=lambda cid:f"{by_id[cid]['codigo']} · {by_id[cid]['nombre']}")
    actor=st.text_input('Responsable del registro *')
    st.caption('Este registro es una interacción documentada; no demuestra aprendizaje ni beneficio.')
    if st.button('Registrar consulta',type='primary'):
        try:
            lib.register_interaction(resource_id,'Consulta registrada',actor,selected)
            st.session_state['pv_success']='Consulta asociada al cliente del directorio.'
            st.rerun()
        except ValidationError as err:st.error(str(err))


def _approved_services():
    """Consulta de solo lectura del catálogo aprobado del Paso 04.

    No crea fichas duplicadas ni habilita operación sin autorización del Paso 05.
    """
    from .portal_services import approved_services
    return approved_services()


def _approved_service_card(r):
    from .public_codes import public_code
    sid = r['id']
    code = public_code('servicio', sid)
    with st.container(border=True):
        st.markdown('<div class="portal-item-tag">APROBADO · PASO 04</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="portal-item-title">{escape(code)} · {escape(r["nombre"])}</div>', unsafe_allow_html=True)
        st.caption((r.get('descripcion') or 'Sin descripción registrada')[:220])
        if r.get('cliente'):
            st.caption('Destinatarios: '+r['cliente'])
        with st.expander('Consultar oferta de servicio'):
            st.write('**Estado de diseño:**',r['estado'])
            st.write('**Responsable:**',r.get('responsable') or 'Sin registrar')
            if r.get('propuesta_valor'):
                st.write('**Propuesta de valor:**',r['propuesta_valor'])
            st.caption('La aprobación del Paso 04 no constituye autorización para operar. La transición se valida en el Paso 05.')


def render_portal():
    _styles()
    from .value_info_panel import info_panel
    st.markdown('<div class="portal-eyebrow">PASO 01 · GENERACIÓN DE CONCIENCIA</div>',unsafe_allow_html=True)
    a,b=st.columns([4,1.1],vertical_alignment='center')
    with a:
        st.markdown('<div class="portal-title">Portal de valor y biblioteca</div>',unsafe_allow_html=True)
        st.markdown('<div class="portal-subtitle">Conocimiento, servicios y participación para fortalecer la cultura de proyectos en CENS.</div>',unsafe_allow_html=True)
    with b:
        if st.button('＋ Nuevo recurso',type='primary',use_container_width=True,key='pv_new_top'):_resource_dialog()
    if st.session_state.pop('pv_success',None):st.success('Operación registrada correctamente.')
    st.markdown('''<div class="portal-hero"><div class="portal-hero-chip">PMO FLYWHEEL CENS · CULTURA DE PROYECTOS</div>
      <h2>Conectamos conocimiento, personas y proyectos</h2>
      <p>Conoce la PMO, accede a recursos útiles y participa en la construcción de una gestión de proyectos orientada al valor.</p></div>''',unsafe_allow_html=True)
    s=lib.stats()
    approved=_approved_services()
    a,b,c,d=st.columns(4,gap='small')
    with a:_kpi('Recursos publicados',s['published'],'Materiales e historias publicados','▣')
    with b:_kpi('Servicios aprobados',len(approved),'Catálogo oficial del Paso 04','◇')
    with c:_kpi('Clientes con consulta',s['clients_consulted'],'Identificados por código único','♙')
    with d:_kpi('Descargas iniciadas',s['downloads_started'],'Acciones registradas, no beneficios','⇩')
    t1,t2,t3,t4,t5=st.tabs(['Inicio','Conoce la PMO','Servicios PMO','Biblioteca','Participa'])
    with t1:
        st.markdown('### Descubre el valor de la PMO')
        c1,c2,c3=st.columns(3)
        for col,title,desc,icon in [
           (c1,'Conocimiento compartido','Guías y experiencias para apoyar la gestión de proyectos.','◈'),
           (c2,'Acompañamiento','Orientación y herramientas según las necesidades de las áreas.','◎'),
           (c3,'Mejora continua','Aprendizajes que respaldan decisiones y fortalecen capacidades.','↗')]:
            with col:
                st.markdown(f'<div class="portal-pillar"><div class="portal-pillar-icon">{icon}</div><b>{title}</b><p>{desc}</p></div>',unsafe_allow_html=True)
        st.markdown('### Publicaciones recientes')
        recent=[r for r in lib.list_resources() if r['tipo']!='Servicio' and r['estado']=='Publicado'][:3]
        if not recent:st.info('Aún no existen publicaciones. Comienza registrando un recurso de la biblioteca.')
        else:
            cols=st.columns(min(3,len(recent)))
            for j,(col,r) in enumerate(zip(cols,recent)):
                with col:_resource_card(r,scope=f'inicio_{j}')
        st.caption('Los recursos publicados son productos. La consulta, participación y los beneficios se registran por separado.')
    with t2:
        st.markdown('### ¿Qué es la PMO CENS?')
        st.write('La Oficina de Gestión de Proyectos es una capacidad organizacional que busca ayudar a las áreas a gestionar proyectos con mejores prácticas, acompañamiento y conocimiento compartido.')
        left,right=st.columns([1.15,1], gap='large')
        with left:
            st.markdown('#### Recorrido de valor')
            st.write('El Flywheel articula diez pasos de creación, prestación, seguimiento, mejora y reconocimiento del valor. Las autoevaluaciones y autorizaciones se documentan por separado.')
            st.caption('El paso seleccionado en la navegación no indica porcentaje de implementación ni nivel de madurez.')
        with right:
            ref_image=__import__('pathlib').Path(__file__).resolve().parent / 'assets' / 'flywheel_pmi_reference.png'
            if ref_image.exists():
                st.image(str(ref_image),caption='Esquema de referencia PMO Value Ring™ aportado para consulta metodológica. La adaptación CENS no representa una certificación PMI.',use_container_width=True)
        st.markdown('### ¿Cómo puede generar valor?')
        st.markdown('''- **Cultura de proyectos:** facilitar un lenguaje y prácticas comunes.
- **Formación y desarrollo:** fortalecer competencias de equipos y líderes.
- **Metodologías y conocimiento:** facilitar instrumentos reutilizables y lecciones aprendidas.
- **Información y toma de decisiones:** mejorar el acceso a herramientas y aprendizajes.''')
        st.info('Los beneficios anteriores expresan el propósito de la PMO; su materialización debe validarse con evidencias en los pasos posteriores del Value Ring.')
        c1,c2=st.columns(2)
        with c1:
            if st.button('Consultar Eventos y campañas',on_click=_navigate,args=('Eventos y campañas',),use_container_width=True,key='pv_go_events_a'):pass
        with c2:
            if st.button('Consultar clientes internos',on_click=_navigate,args=('Clientes internos',),use_container_width=True,key='pv_go_clients_a'):pass
    with t3:
        info_panel('Catálogo único de servicios', 'Los servicios aprobados se consultan directamente desde el Paso 04; esta vista no vuelve a capturarlos ni autoriza su operación.')
        st.markdown('### Servicios de la PMO')
        st.markdown('**Servicios aprobados en el Paso 04**')
        st.caption('Catálogo de solo lectura, conectado con las fichas oficiales. Se actualiza automáticamente; no es necesario registrar otra ficha en el portal.')
        if approved:
            for start in range(0,len(approved),2):
                cols=st.columns(2)
                for col,svc in zip(cols,approved[start:start+2]):
                    with col:_approved_service_card(svc)
        else:
            st.info('Aún no hay servicios con estado Aprobado en el Paso 04. No se muestran servicios en diseño como aprobados.')
        historical=lib.list_resources(kind='Servicio')
        if historical:
            with st.expander(f'Fichas informativas heredadas del portal ({len(historical)}) · no son el catálogo oficial', expanded=False):
                st.caption('Se conservan sin modificar sus identificadores, archivos ni interacciones anteriores. Para publicar nuevos servicios utiliza el catálogo aprobado del Paso 04.')
                for i in range(0,len(historical),2):
                    cols=st.columns(2)
                    for j,(col,r) in enumerate(zip(cols,historical[i:i+2])):
                        with col:_resource_card(r,with_manage=True,scope=f'servicios_heredados_{i+j}')
    with t4:
        st.markdown('### Biblioteca de conocimiento')
        filters=st.columns([2.1,1.3,1.1])
        search=filters[0].text_input('Buscar',placeholder='Título, categoría, autor o descripción...',key='pv_search')
        cat=filters[1].selectbox('Categoría',['Todas']+list(lib.CATEGORIES),key='pv_category')
        status=filters[2].selectbox('Estado',['Todos','Publicado','Borrador','Archivado'],key='pv_status')
        show_archived=status=='Archivado'
        rows=[r for r in lib.list_resources(search=search,category='' if cat=='Todas' else cat,
                status='' if status=='Todos' else status,include_archived=show_archived)
              if r['tipo']!='Servicio']
        st.caption(f'{len(rows)} recursos encontrados · Archivos y versiones guardados localmente')
        if not rows:st.info('No hay recursos que coincidan con los filtros. Puedes crear el primero.')
        for i in range(0,len(rows),2):
            cols=st.columns(2)
            for j,(col,r) in enumerate(zip(cols,rows[i:i+2])):
                with col:
                    position=i+j
                    if r['estado']=='Archivado':
                        _resource_card(r,scope=f'biblioteca_archivada_{position}')
                        if st.button('Restaurar como borrador',key=f'pv_restore_{position}_{r["id"]}'):
                            _restore_dialog(r['id'])
                    else:_resource_card(r,with_manage=True,scope=f'biblioteca_{position}')
    with t5:
        st.markdown('### Participa en la construcción de la PMO')
        st.write('Tus consultas, experiencias y necesidades ayudan a comprender cómo la PMO puede aportar valor. Utiliza los componentes existentes del Paso 01 para registrar cada interacción una sola vez.')
        c1,c2=st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown('**Solicita orientación**')
                st.caption('Registra preguntas, inquietudes y solicitudes en Consultas e interacciones.')
                st.button('Ir a Consultas e interacciones',on_click=_navigate,args=('Consultas e interacciones',),
                          key='pv_go_tickets',use_container_width=True)
        with c2:
            with st.container(border=True):
                st.markdown('**Participa en actividades**')
                st.caption('Conoce las jornadas de sensibilización y registra asistencia en Eventos y campañas.')
                st.button('Ir a Eventos y campañas',on_click=_navigate,args=('Eventos y campañas',),
                          key='pv_go_events_b',use_container_width=True)
        st.warning('La biblioteca del ciclo es local y no dispone de autenticación por roles. No publique información confidencial ni comparta esta instalación en una red sin controles de acceso.')


@st.dialog('Restaurar recurso archivado')
def _restore_dialog(rid):
    actor=st.text_input('Responsable de la restauración *')
    if st.button('Restaurar como borrador',type='primary'):
        try:
            lib.restore_resource(rid,'Borrador',actor)
            st.rerun()
        except ValidationError as err:st.error(str(err))
