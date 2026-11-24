"""Offline, non-overwriting backups of the entire local data directory.
Close all writers first. Hash comparisons detect ordinary concurrent changes,
not a substitute for exclusive access or a corporate backup system.
"""
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone
import hashlib, json, os, shutil, sqlite3, tempfile

DB = 'pmo_flywheel.sqlite3'
MANIFEST = 'manifest.json'


def _link(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def _hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _inventory(root):
    if not root.is_dir() or _link(root):
        raise ValueError('Carpeta de datos no disponible o enlace no permitido.')
    files, dirs = {}, []
    for current, subdirs, names in os.walk(root, followlinks=False):
        for name in sorted(subdirs + names):
            p = Path(current)/name
            if _link(p):
                raise ValueError('No se respaldan enlaces o junctions: '+str(p))
            rel = p.relative_to(root).as_posix()
            if p.is_dir(): dirs.append(rel)
            elif p.is_file():
                if name.endswith(('-wal','-shm','-journal')):
                    raise ValueError('SQLite tiene archivos auxiliares. Cierra todas las instancias y revisa la base; no los borres manualmente.')
                files[rel] = {'bytes':p.stat().st_size,'sha256':_hash(p)}
            else: raise ValueError('Elemento no regular: '+rel)
    return {'files':files,'directories':sorted(dirs)}


def inspect_db(path):
    p=Path(path)
    if not p.is_file(): raise FileNotFoundError(str(p))
    with closing(sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        integrity=[r[0] for r in c.execute('PRAGMA integrity_check')]
        fk=sum(1 for _ in c.execute('PRAGMA foreign_key_check'))
        tables=c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    return {'integrity':integrity,'foreign_key_violations':fk,'tables':tables}


def _check(db):
    r=inspect_db(db)
    if r['integrity']!=['ok'] or r['foreign_key_violations']:
        raise ValueError('Integridad o claves foráneas no conformes; no se publica la copia.')
    return r


def _separate(source,dest):
    if _link(source) or _link(dest): raise ValueError('No se permiten enlaces.')
    a,b=source.resolve(),dest.resolve()
    if a==b or a in b.parents or b in a.parents:
        raise ValueError('Origen y destino deben ser carpetas independientes.')
    if dest.exists(): raise FileExistsError('Destino existente; no se sobrescribe: '+str(dest))


def _publish(staged,dest):
    # reserve destination atomically; copy to our empty directory, clean only on own failure.
    # No other operation may target this directory until completion.
    dest.mkdir(exist_ok=False)
    try:
        shutil.copytree(staged,dest,dirs_exist_ok=True)
        if _inventory(dest)!=_inventory(staged): raise ValueError('Verificación final de archivos fallida.')
    except BaseException:
        shutil.rmtree(dest)
        raise


def create_backup(source,destination):
    source,destination=Path(source),Path(destination)
    _separate(source,destination)
    before=_inventory(source)
    if DB not in before['files']: raise FileNotFoundError('Falta la base principal.')
    _check(source/DB)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent,prefix='beta_backup_') as temp:
        stage=Path(temp)/'backup';stage.mkdir()
        shutil.copytree(source,stage/'datos')
        after=_inventory(source);copied=_inventory(stage/'datos')
        if before!=after or before!=copied: raise ValueError('El origen cambió durante la copia. Cierra todas las aplicaciones y vuelve a intentar.')
        report=_check(stage/'datos'/DB)
        m={'format':1,'created_utc':datetime.now(timezone.utc).isoformat(),'source_name':source.name,'inventory':copied,'sqlite':report}
        (stage/MANIFEST).write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
        verify_backup(stage)
        _publish(stage,destination)
    return m


def verify_backup(backup):
    backup=Path(backup)
    if _link(backup) or not backup.is_dir() or _link(backup/MANIFEST): raise ValueError('Respaldo no válido.')
    m=json.loads((backup/MANIFEST).read_text(encoding='utf-8'))
    if m.get('format')!=1 or _inventory(backup/'datos')!=m.get('inventory'):
        raise ValueError('Manifiesto no coincide con los archivos del respaldo.')
    _check(backup/'datos'/DB)
    return m


def restore_backup(backup,destination):
    backup,destination=Path(backup),Path(destination)
    _separate(backup,destination)
    m=verify_backup(backup)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent,prefix='beta_restore_') as temp:
        stage=Path(temp)/'datos';shutil.copytree(backup/'datos',stage)
        if _inventory(stage)!=m['inventory']: raise ValueError('La copia restaurada no coincide con el manifiesto.')
        _check(stage/DB)
        _publish(stage,destination)
    return m
