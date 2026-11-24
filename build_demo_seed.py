"""Build a new synthetic seed without reading any operational database."""
from pathlib import Path
from contextlib import closing
import sqlite3, importlib
from pmo import storage, clients, awareness, step2, step4

DEST=Path(__file__).parent/'cloud_seed'/'demo.sqlite3'
MODULES=('storage','v0391_clients','v0391_diagnostics','assessment','step1_closure','events_media','library_portal','interactions','step3','step4','step5','step6','step7','step8','step8_documented','step8_improvement','step8_profile','step9','step10','pmi_flywheel_assessment','public_codes','step2_maturity_questions')

def init(path):
    for name in MODULES:
        mod=importlib.import_module('pmo.'+name)
        func={'v0391_clients':'harmonize_roles','v0391_diagnostics':'harmonize_diagnostic_names'}.get(name,'initialize')
        getattr(mod,func)(path)

def build(path):
    if path.exists(): raise FileExistsError('No se sobrescribe una semilla existente.')
    path.parent.mkdir(parents=True,exist_ok=True)
    init(path)
    people=[]
    for i in range(6):
        dept=['Dependencia DEMO A','Dependencia DEMO B','Dependencia DEMO C'][i//2]
        role=['Dirección de ensayo','Equipo de ensayo'][i%2]
        cid=clients.create_client({'codigo':f'DEMO-{i+1:03d}','nombre':f'Cliente ficticio {i+1:02d}','dependencia':dept,'segmento':role,'rol_especifico':role,'influencia':'Alta' if i%2==0 else 'Media','interes':'Alto','activo':True},'Laboratorio ficticio',path)
        people.append((cid,dept))
    diag=step2.create_diagnostic('Diagnóstico 01 - 2027 - Laboratorio ficticio','2027','Laboratorio ficticio',scope='Ejercicio de demostración, no institucional',population=6,path=path)
    for i,(cid,dept) in enumerate(people):
        step2.save_priorities(diag,cid,[1+i,10+i,20+i,27,30],'Laboratorio ficticio',path=path)
        step2.create_need(diag,cid,dept,f'Caso ficticio {i+1}: dificultad de coordinación',f'Caso ficticio {i+1}: información de proyectos disponible',i+1,'Medio','Caso inventado','Laboratorio ficticio',path=path)
    for i in range(2):
        awareness.create_event(f'Taller ficticio {i+1}','Taller',f'2027-01-{10+i:02d}','Participantes ficticios','Virtual','Laboratorio ficticio','Programado',path)
        step4.save_service({'codigo':f'DEMO-SRV-{i+1:03d}','nombre':['Acompañamiento ficticio','Informes ficticios'][i],'estado':'Borrador','descripcion':'Servicio de ensayo sin autorización institucional','cliente':'Dependencia DEMO A','modelo':'Consultivo'},'Laboratorio ficticio',path=path)
    with closing(sqlite3.connect(path)) as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
    # Only the final synthetic database is included, never migration backups.
if __name__=='__main__': build(DEST)
