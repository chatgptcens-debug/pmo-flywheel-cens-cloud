"""V0.39.9 · Códigos públicos consecutivos, separados de IDs y claves históricas.
No reescribe códigos del motor ni snapshots. Cada correlativo es permanente.
"""
from __future__ import annotations
from contextlib import closing
from .storage import connect, transaction

PREFIX={'solucion':'SOL','servicio':'SRV','integrante':'PMO'}
TABLES={'solucion':('p3_soluciones','creado_en'), 'servicio':('p4_services','creado_en'),
        'integrante':('p4_team','rowid')}
SCHEMA='''
CREATE TABLE IF NOT EXISTS pmo_codigos_publicos (
 tipo TEXT NOT NULL, entidad_id TEXT NOT NULL, numero INTEGER NOT NULL,
 codigo TEXT NOT NULL, codigo_origen TEXT NOT NULL DEFAULT '',
 asignado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(tipo,entidad_id), UNIQUE(tipo,numero), UNIQUE(tipo,codigo)
);
CREATE TABLE IF NOT EXISTS pmo_codigos_secuencias(tipo TEXT PRIMARY KEY, ultimo INTEGER NOT NULL);
'''

def _exists(con,name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def _assign(con,tipo,entity_id,legacy=''):
    old=con.execute('SELECT codigo FROM pmo_codigos_publicos WHERE tipo=? AND entidad_id=?',(tipo,entity_id)).fetchone()
    if old:return old[0]
    last=con.execute('SELECT ultimo FROM pmo_codigos_secuencias WHERE tipo=?',(tipo,)).fetchone()
    num=(last[0] if last else 0)+1
    code=f'{PREFIX[tipo]}-{num:03d}'
    con.execute('INSERT INTO pmo_codigos_publicos(tipo,entidad_id,numero,codigo,codigo_origen) VALUES(?,?,?,?,?)',
                (tipo,entity_id,num,code,legacy or ''))
    con.execute('INSERT INTO pmo_codigos_secuencias(tipo,ultimo) VALUES(?,?) ON CONFLICT(tipo) DO UPDATE SET ultimo=excluded.ultimo',(tipo,num))
    return code

def initialize(path=None):
    with transaction(path) as con:
        con.executescript(SCHEMA)
        for kind,(table,order) in TABLES.items():
            if not _exists(con,table):continue
            # Los servicios del taller se ordenan por el número de su ficha; el resto conserva el orden de creación.
            ordering=("CASE WHEN codigo GLOB 'TVAL26-SRV-*' THEN 0 ELSE 1 END, codigo" if kind=='servicio' else order+',rowid' if order!='rowid' else 'rowid')
            code_field='codigo' if kind!='integrante' else "'' AS codigo"
            for row in con.execute(f'SELECT id,{code_field} FROM {table} ORDER BY {ordering}').fetchall():
                _assign(con,kind,row['id'],row['codigo'])
        # Servicios importados mediante expediente JSON pueden no existir todavía en Paso 04.
        if _exists(con,'p5_services'):
            for row in con.execute('SELECT id,codigo FROM p5_services ORDER BY importado_en,rowid').fetchall():
                _assign(con,'servicio',row['id'],row['codigo'])

def code(kind,entity_id,path=None):
    if not entity_id:return next_code(kind,path)
    with closing(connect(path)) as con:
        if _exists(con,'pmo_codigos_publicos'):
            item=con.execute('SELECT codigo FROM pmo_codigos_publicos WHERE tipo=? AND entidad_id=?',(kind,entity_id)).fetchone()
            if item:return item[0]
    initialize(path)
    with closing(connect(path)) as con:
        row=con.execute('SELECT codigo FROM pmo_codigos_publicos WHERE tipo=? AND entidad_id=?',(kind,entity_id)).fetchone()
        return row[0] if row else str(entity_id)

def next_code(kind,path=None):
    initialize(path)
    with closing(connect(path)) as con:
        row=con.execute('SELECT ultimo FROM pmo_codigos_secuencias WHERE tipo=?',(kind,)).fetchone()
        return f'{PREFIX[kind]}-{(row[0] if row else 0)+1:03d}'

def code_map(kind,path=None):
    initialize(path)
    with closing(connect(path)) as con:
        return {x['entidad_id']:x['codigo'] for x in con.execute('SELECT entidad_id,codigo FROM pmo_codigos_publicos WHERE tipo=?',(kind,))}
