"""Consultative administration: no authentication or privileged business action."""
import csv, sqlite3
from pathlib import Path
from .config import database_path
from .beta01_backup import inspect_db

AUDIT=Path(__file__).resolve().parents[1]/'AUDITORIA_PLAN_MAESTRO_V100.csv'


def read_audit():
    with AUDIT.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def render(st):
    st.subheader('Administración y calidad de la versión')
    st.warning('Cloud Edition de demostración. No hay autenticación corporativa ni autorización por roles. Mantén el aplicativo privado y usa únicamente datos ficticios.')
    st.caption('Base conectada: '+str(database_path()))
    if st.button('Comprobar integridad SQLite (solo lectura)',icon=':material/verified:',key='beta_check'):
        try:
            r=inspect_db(database_path())
            if r['integrity']==['ok'] and r['foreign_key_violations']==0:st.success('Integridad y claves foráneas conformes en esta consulta.')
            else:st.error('Hallazgos de integridad; no realizar restauraciones ni eliminar archivos manualmente.')
            st.json(r)
        except (OSError,sqlite3.Error) as e:st.error(str(e))
    st.markdown('**Persistencia del laboratorio**')
    st.info('Datos temporales por sesión. Descarga los informes de ensayo desde sus módulos. No se permite restaurar bases operativas en Cloud.')
    st.markdown('**Seguimiento del Plan Maestro (revisión técnica preliminar)**')
    rows=read_audit();statuses=list(dict.fromkeys(r['Estado'] for r in rows));state=st.selectbox('Estado de cobertura',['Todos']+statuses,key='beta_audit_filter')
    st.dataframe([r for r in rows if state=='Todos' or r['Estado']==state],hide_index=True,use_container_width=True)
    st.download_button('Descargar auditoría de 72 componentes',AUDIT.read_bytes(),file_name=AUDIT.name,mime='text/csv',key='beta_audit_download')
    st.caption('Cobertura de código, no certificación PMI ni aceptación de usuario. Los componentes implementados siguen sujetos a validación visual y operativa.')
