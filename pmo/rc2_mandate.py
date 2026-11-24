"""Mandato local versionado, evidencia documental; no confiere autoridad institucional."""
from datetime import date
from pathlib import Path
import json, sqlite3
from .config import database_path
from .storage import transaction
from .alpha06_transversal import reader
from .clients import ValidationError

FIELDS={'proposito':4000,'alcance':6000,'autoridad':4000,'responsabilidades':6000,'sponsor':180,'referencia':1000,'fecha_documento':10,'justificacion':2000}
STATES=('Borrador','Aprobación documentada','Retiro documentado')
SCHEMA='''CREATE TABLE IF NOT EXISTS pmo_rc2_mandate (
 version INTEGER PRIMARY KEY, estado TEXT NOT NULL CHECK(estado IN ('Borrador','Aprobación documentada','Retiro documentado')),
 contenido_json TEXT NOT NULL, actor TEXT NOT NULL, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)'''

def history(path=None):
    with reader(path) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pmo_rc2_mandate'").fetchone():return []
        return [dict(r) for r in con.execute('SELECT * FROM pmo_rc2_mandate ORDER BY version DESC')]

def current(rows):
    """Último acto documental registrado; los borradores no desplazan el mandato."""
    for r in sorted(rows,key=lambda r:r['version'],reverse=True):
        if r['estado']=='Retiro documentado':return None
        if r['estado']=='Aprobación documentada':return r
    return None

def save(payload, state, actor, expected_version, path=None, confirmed=False):
    actor=str(actor or '').strip()
    if not actor or len(actor)>180 or state not in STATES:raise ValidationError('Actor o estado inválido.')
    values={k:str(payload.get(k) or '').strip() for k in FIELDS}
    for k,v in values.items():
        if len(v)>FIELDS[k]:raise ValidationError(f'{k}: máximo {FIELDS[k]} caracteres.')
    if not values['justificacion']:raise ValidationError('Indique la justificación de esta versión.')
    if state!='Retiro documentado' and not all(values[k] for k in ('proposito','alcance','autoridad')):raise ValidationError('Complete propósito, alcance y autoridad.')
    if state!='Borrador':
        if not confirmed or not all(values[k] for k in ('sponsor','referencia','fecha_documento')):raise ValidationError('Confirme el acto externo e indique autoridad, referencia y fecha documental.')
        try:
            day=date.fromisoformat(values['fecha_documento'])
            if day.isoformat()!=values['fecha_documento'] or day>date.today():raise ValueError()
        except ValueError as exc:raise ValidationError('Fecha documental inválida o futura.') from exc
        if state=='Aprobación documentada' and not values['responsabilidades']:raise ValidationError('Documente las responsabilidades.')
    target=Path(path or database_path())
    if not target.is_file():raise ValidationError('La base conectada no existe.')
    with transaction(target) as con:
        con.execute(SCHEMA)
        rows=[dict(r) for r in con.execute('SELECT * FROM pmo_rc2_mandate ORDER BY version DESC')]
        latest=rows[0]['version'] if rows else 0
        if expected_version!=latest:raise ValidationError('El historial cambió; vuelva a consultar antes de guardar.')
        active=current(rows)
        if state=='Retiro documentado' and active is None:raise ValidationError('No existe un mandato documentado vigente para retirar.')
        if state!='Borrador':
            last_act=next((r for r in rows if r['estado']!='Borrador'),None)
            if last_act and values['fecha_documento']<json.loads(last_act['contenido_json'])['fecha_documento']:raise ValidationError('La fecha es anterior al último acto documentado.')
        if state=='Retiro documentado':
            for k in ('proposito','alcance','autoridad','responsabilidades'):values[k]=json.loads(active['contenido_json'])[k]
        version=latest+1
        body=json.dumps(values,ensure_ascii=False,sort_keys=True)
        con.execute('INSERT INTO pmo_rc2_mandate(version,estado,contenido_json,actor) VALUES (?,?,?,?)',(version,state,body,actor))
        new=dict(con.execute('SELECT * FROM pmo_rc2_mandate WHERE version=?',(version,)).fetchone())
        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor) VALUES (?,?,?,?,?,?)',('mandato_pmo',str(version),'registrar_version',json.dumps(rows[0],ensure_ascii=False) if rows else None,json.dumps(new,ensure_ascii=False),actor))
    return version

def render(st):
    st.markdown('### Mandato PMO · historial documental')
    st.caption('Registro local de versiones. La aprobación o retiro deben existir fuera del aplicativo; el actor declarado no equivale a autenticación. No habilita permisos ni modifica decisiones MVS.')
    try:rows=history()
    except sqlite3.Error as exc:st.error(f'No se pudo consultar el mandato: {exc}');return
    active=current(rows)
    if active:st.success(f"Última aprobación documentada no retirada: versión {active['version']}")
    else:st.info('No hay mandato documentado vigente en este registro local.')
    if rows:
        by_id={r['version']:r for r in rows}
        selected=st.selectbox('Consultar versión histórica',list(by_id),format_func=lambda n:f"V{n:03d} · {by_id[n]['estado']}",key='rc2_mandate_history')
        with st.expander('Detalle de la versión seleccionada'):
            st.write(json.loads(by_id[selected]['contenido_json']));st.caption('Actor: '+by_id[selected]['actor']+' · '+by_id[selected]['creado_en'])
        st.download_button('Exportar historial JSON',json.dumps(rows,ensure_ascii=False,indent=2).encode('utf-8'),file_name='mandato_pmo_historial.json',mime='application/json',key='rc2_mandate_export',on_click='ignore')
    latest=rows[0]['version'] if rows else 0
    base=json.loads(rows[0]['contenido_json']) if rows else {}
    with st.expander('Registrar nueva versión (sin editar las anteriores)'):
        with st.form('rc2_mandate_form_'+str(latest)):
            state=st.selectbox('Tipo de registro',STATES)
            payload={}
            labels={'proposito':'Propósito','alcance':'Alcance','autoridad':'Autoridad y límites','responsabilidades':'Responsabilidades','sponsor':'Sponsor / autoridad documental','referencia':'Referencia del acto externo','fecha_documento':'Fecha documental (AAAA-MM-DD)','justificacion':'Justificación del cambio'}
            for k in FIELDS:
                fn=st.text_area if k in ('proposito','alcance','autoridad','responsabilidades','justificacion') else st.text_input
                payload[k]=fn(labels[k],value=base.get(k,'') if k not in ('justificacion','referencia','fecha_documento') else '',max_chars=FIELDS[k])
            actor=st.text_input('Actor que registra',max_chars=180)
            confirmed=st.checkbox('Confirmo que el acto de aprobación o retiro existe fuera del aplicativo (solo aplica a actos documentados).')
            if st.form_submit_button('Registrar versión',type='primary'):
                try:save(payload,state,actor,latest,confirmed=confirmed)
                except (ValidationError,sqlite3.Error) as exc:st.error(str(exc))
                else:st.session_state['rc2_mandate_saved']=True;st.rerun()
    if st.session_state.pop('rc2_mandate_saved',False):st.success('Versión registrada con historial y auditoría.')
