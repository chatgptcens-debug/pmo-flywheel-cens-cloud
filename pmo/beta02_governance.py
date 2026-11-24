"""Registro de seguimiento PMO, independiente de aprobaciones metodológicas.
Migración aditiva bajo demanda; historial de cambios en pmo_auditoria.
"""
from datetime import date
import json, sqlite3, uuid
from pathlib import Path
from .config import database_path
from .storage import transaction
from .alpha06_transversal import reader
from .clients import ValidationError

KINDS=('Comité','Compromiso','Riesgo')
STATES=('Abierto','En seguimiento','Cerrado','Cancelado')
SCHEMA='''CREATE TABLE IF NOT EXISTS pmo_beta02_governance (
 id TEXT PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT NOT NULL,
 descripcion TEXT NOT NULL, responsable TEXT NOT NULL, fecha_meta TEXT NOT NULL,
 evidencia TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL,
 creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''

def records(path=None):
    try:
        with reader(path) as c:
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pmo_beta02_governance'").fetchone()
            if not exists:return []
            return [dict(r) for r in c.execute('SELECT * FROM pmo_beta02_governance ORDER BY fecha_meta, id')]
    except sqlite3.Error:return None

def save(payload, actor, path=None, record_id=None):
    actor=str(actor or '').strip()
    fields=('tipo','titulo','descripcion','responsable','fecha_meta','evidencia','estado')
    values={k:str(payload.get(k) or '').strip() for k in fields}
    if not actor or len(actor)>180:raise ValidationError('Indique un actor de hasta 180 caracteres.')
    if values['tipo'] not in KINDS or values['estado'] not in STATES:raise ValidationError('Tipo o estado inválido.')
    if not all(values[k] for k in ('titulo','descripcion','responsable','fecha_meta')):raise ValidationError('Complete título, descripción, responsable y fecha meta.')
    for k,maximum in [('titulo',180),('descripcion',4000),('responsable',180),('evidencia',1000)]:
        if len(values[k])>maximum:raise ValidationError(f'{k}: máximo {maximum} caracteres.')
    try:
        if date.fromisoformat(values['fecha_meta']).isoformat()!=values['fecha_meta']:raise ValueError()
    except ValueError as exc:raise ValidationError('Fecha meta AAAA-MM-DD inválida.') from exc
    if values['estado'] in ('Cerrado','Cancelado') and not values['evidencia']:raise ValidationError('Registre evidencia o justificación para cerrar o cancelar.')
    if not Path(path or database_path()).is_file():raise ValidationError('La base conectada no existe.')
    with transaction(path) as c:
        c.execute(SCHEMA)
        if record_id is None:
            record_id=uuid.uuid4().hex;old=None
            c.execute('INSERT INTO pmo_beta02_governance(id,'+','.join(fields)+') VALUES ('+','.join('?' for _ in range(8))+')',(record_id,*values.values()))
        else:
            row=c.execute('SELECT * FROM pmo_beta02_governance WHERE id=?',(record_id,)).fetchone()
            if row is None:raise ValidationError('Registro no encontrado; actualice la consulta.')
            old=dict(row)
            if old['tipo']!=values['tipo']:raise ValidationError('El tipo original del registro no se puede modificar.')
            if all(old[k]==values[k] for k in fields):return record_id
            c.execute('UPDATE pmo_beta02_governance SET '+','.join(k+'=?' for k in fields)+',actualizado_en=CURRENT_TIMESTAMP WHERE id=?',(*values.values(),record_id))
        new=dict(c.execute('SELECT * FROM pmo_beta02_governance WHERE id=?',(record_id,)).fetchone())
        c.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor) VALUES (?,?,?,?,?,?)',('seguimiento_gobernanza',record_id,'crear' if old is None else 'actualizar',json.dumps(old,ensure_ascii=False) if old else None,json.dumps(new,ensure_ascii=False),actor))
    return record_id

def overdue(rows,today=None):
    today=(today or date.today()).isoformat()
    return [r for r in rows if r['estado'] in ('Abierto','En seguimiento') and r['fecha_meta']<today]

def render(st):
    st.markdown('### Registro de seguimiento de gobernanza')
    st.caption('Comités, compromisos y riesgos. Registro local de seguimiento; no autoriza servicios, no sustituye actas ni controles corporativos. El actor declarado no equivale a autenticación.')
    rows=records()
    if rows is None:st.warning('No se pudo consultar la base.');return
    for col,(label,num) in zip(st.columns(3), [('Registros',len(rows)),('Abiertos',sum(r['estado'] in ('Abierto','En seguimiento') for r in rows)),('Vencidos',len(overdue(rows)))]):col.metric(label,num)
    kind=st.selectbox('Filtrar tipo',['Todos',*KINDS],key='b02_gov_filter')
    visible=[r for r in rows if kind=='Todos' or r['tipo']==kind]
    if visible:st.dataframe(visible,hide_index=True,use_container_width=True)
    else:st.info('No hay registros de seguimiento para este filtro.')
    choices={r['id']:r for r in visible}
    pick=st.selectbox('Registro a gestionar',[None,*choices],format_func=lambda k:'Nuevo registro' if k is None else choices[k]['titulo']+' · '+k[:8],key='b02_gov_pick')
    old=choices.get(pick,{})
    with st.form('b02_gov_form_'+str(pick)):
        typ=st.selectbox('Tipo',KINDS,index=KINDS.index(old.get('tipo',KINDS[0])),disabled=bool(pick))
        title=st.text_input('Título',value=old.get('titulo',''),max_chars=180)
        description=st.text_area('Descripción / tratamiento',value=old.get('descripcion',''),max_chars=4000)
        owner=st.text_input('Responsable',value=old.get('responsable',''),max_chars=180)
        due=st.date_input('Fecha meta',value=date.fromisoformat(old['fecha_meta']) if old else None,format='YYYY/MM/DD')
        status=st.selectbox('Estado',STATES,index=STATES.index(old.get('estado','Abierto')))
        evidence=st.text_area('Referencia de evidencia o justificación',value=old.get('evidencia',''),max_chars=1000)
        actor=st.text_input('Actor que registra el cambio',max_chars=180)
        if st.form_submit_button('Guardar seguimiento',type='primary'):
            try:save(dict(tipo=typ,titulo=title,descripcion=description,responsable=owner,fecha_meta=due.isoformat() if due else '',estado=status,evidencia=evidence),actor,record_id=pick)
            except (ValidationError,sqlite3.Error) as exc:st.error(str(exc))
            else:st.session_state['b02_gov_saved']=True;st.rerun()
    if st.session_state.pop('b02_gov_saved',False):st.success('Seguimiento guardado con auditoría.')
