"""Portal de valor y biblioteca V0.28.

Extiende p1_recursos en forma aditiva, sin modificar el esquema original del Paso 01.
Los archivos se guardan fuera del código, junto a la base SQLite del ciclo.
No proporciona autenticación ni publicación externa: uso local autorizado únicamente.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import sqlite3
import uuid
import zipfile

from .clients import ValidationError
from .config import database_path
from .storage import connect, transaction

CATEGORIES = ('Fundamentos PMO', 'Metodologías', 'Herramientas y plantillas',
              'Formación', 'Experiencias CENS', 'Gestión del conocimiento', 'Otros')
KINDS = ('Material', 'Servicio', 'Historia')
RESOURCE_STATUSES = ('Borrador', 'Publicado', 'Archivado')
SERVICE_STATUSES = ('En diseño', 'Piloto', 'Disponible', 'Suspendido', 'Archivado')
ACCESS = ('Interno', 'Restringido')
EXTENSIONS = {'pdf','docx','xlsx','pptx','png','jpg','jpeg','webp','txt','md'}
MIMES = {
 'pdf':'application/pdf', 'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
 'xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
 'pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
 'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp',
 'txt':'text/plain','md':'text/markdown',
}
MAX_BYTES = 20*1024*1024


def _db(path=None): return Path(path) if path is not None else database_path()


def files_root(path=None): return _db(path).parent / 'biblioteca_pmo'


def _required(value, label):
    v=str(value or '').strip()
    if not v: raise ValidationError(f'Diligencie {label}.')
    return v


def _backup_before_migration(file:Path):
    backup=file.with_name(file.stem+'.antes_V0_28_portal.sqlite3')
    if file.exists() and file.stat().st_size and not backup.exists():
        with closing(connect(file)) as src, closing(sqlite3.connect(str(backup))) as dst:
            src.backup(dst)
    return backup


def initialize(path=None):
    """Migración idempotente con respaldo en el primer arranque actualizado."""
    file=_db(path)
    with closing(connect(file)) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p1_recursos'").fetchone():
            raise RuntimeError('Inicialice primero pmo.storage.initialize().')
        exists=bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p1_recurso_detalles'").fetchone())
    if not exists: _backup_before_migration(file)
    with transaction(file) as con:
        for stmt in '''
        CREATE TABLE IF NOT EXISTS p1_recurso_detalles (
          recurso_id TEXT PRIMARY KEY REFERENCES p1_recursos(id) ON DELETE CASCADE,
          autor TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '1.0',
          publico TEXT NOT NULL DEFAULT '', acceso TEXT NOT NULL DEFAULT 'Interno'
            CHECK(acceso IN ('Interno','Restringido')),
          publicado_en TEXT NOT NULL DEFAULT '',
          actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS p1_recurso_archivos (
          id TEXT PRIMARY KEY, recurso_id TEXT NOT NULL REFERENCES p1_recursos(id),
          nombre_original TEXT NOT NULL, almacenado TEXT NOT NULL UNIQUE,
          mime TEXT NOT NULL, peso INTEGER NOT NULL, hash_sha256 TEXT NOT NULL,
          version TEXT NOT NULL, estado TEXT NOT NULL CHECK(estado IN ('Vigente','Anterior')),
          creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, actor TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_p1_archivos_recurso ON p1_recurso_archivos(recurso_id,estado);
        CREATE TABLE IF NOT EXISTS p1_recurso_interacciones (
          id TEXT PRIMARY KEY, recurso_id TEXT NOT NULL REFERENCES p1_recursos(id),
          cliente_id TEXT REFERENCES pmo_clientes(id),
          accion TEXT NOT NULL CHECK(accion IN ('Consulta registrada','Descarga iniciada')),
          actor TEXT NOT NULL, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_p1_interacciones_recurso ON p1_recurso_interacciones(recurso_id);
        '''.split(';'):
            if stmt.strip(): con.execute(stmt)
        # Registra la actualización sin alterar el historial de migraciones de otros módulos.
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (28)')


def _fields(*, title, category, description, url, kind, status, owner, actor,
            author='', version='1.0', audience='', access='Interno', publication_date=''):
    title=_required(title,'el título');category=_required(category,'la categoría')
    owner=_required(owner,'el responsable');actor=_required(actor,'quién realiza el registro')
    if kind not in KINDS:raise ValidationError('Tipo de recurso inválido.')
    if status not in (SERVICE_STATUSES if kind=='Servicio' else RESOURCE_STATUSES):
        raise ValidationError('Estado incompatible con el tipo de recurso.')
    if access not in ACCESS:raise ValidationError('Nivel de acceso inválido.')
    url=str(url or '').strip()
    if url:
        from urllib.parse import urlparse
        p=urlparse(url)
        if p.scheme not in ('https','http') or not p.netloc or p.username or p.password:
            raise ValidationError('El enlace debe ser una URL HTTP(S) válida y sin credenciales.')
    if publication_date:
        try:date.fromisoformat(str(publication_date))
        except ValueError as err:raise ValidationError('Fecha de publicación inválida.') from err
    return dict(titulo=title,categoria=category,descripcion=str(description or '').strip(),
                url=url,tipo=kind,estado=status,responsable=owner,
                autor=str(author or '').strip(),version=_required(version,'la versión'),
                publico=str(audience or '').strip(),acceso=access,publicado_en=str(publication_date or ''))


def save_resource(*, resource_id=None, title, category, description='',url='',kind='Material',
                  status='Borrador',owner,actor,author='',version='1.0',audience='',
                  access='Interno',publication_date='',path=None):
    fields=_fields(title=title,category=category,description=description,url=url,
       kind=kind,status=status,owner=owner,actor=actor,author=author,version=version,
       audience=audience,access=access,publication_date=publication_date)
    rid=resource_id or uuid.uuid4().hex
    with transaction(path) as con:
        existing=con.execute('SELECT id FROM p1_recursos WHERE id=?',(rid,)).fetchone()
        if resource_id and not existing:raise ValidationError('El recurso seleccionado ya no existe.')
        if existing:
            con.execute('''UPDATE p1_recursos SET titulo=?,categoria=?,descripcion=?,url=?,tipo=?,estado=?,responsable=? WHERE id=?''',
                        tuple(fields[k] for k in ('titulo','categoria','descripcion','url','tipo','estado','responsable'))+(rid,))
        else:
            con.execute('''INSERT INTO p1_recursos(id,titulo,categoria,descripcion,url,tipo,estado,responsable)
                        VALUES (?,?,?,?,?,?,?,?)''',
                        (rid,)+tuple(fields[k] for k in ('titulo','categoria','descripcion','url','tipo','estado','responsable')))
        con.execute('''INSERT INTO p1_recurso_detalles
          (recurso_id,autor,version,publico,acceso,publicado_en) VALUES(?,?,?,?,?,?)
          ON CONFLICT(recurso_id) DO UPDATE SET
          autor=excluded.autor, version=excluded.version, publico=excluded.publico,
          acceso=excluded.acceso, publicado_en=excluded.publicado_en,
          actualizado_en=CURRENT_TIMESTAMP''',
          (rid,fields['autor'],fields['version'],fields['publico'],fields['acceso'],fields['publicado_en']))
        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor) VALUES (?,?,?,?)',
                    ('recurso',rid,'editar' if existing else 'crear',actor))
    return rid


def get_resource(resource_id,path=None):
    with closing(connect(path)) as con:
        row=con.execute('''SELECT r.*,COALESCE(d.autor,'') autor,COALESCE(d.version,'') version,
          COALESCE(d.publico,'') publico,COALESCE(d.acceso,'Interno') acceso,
          COALESCE(d.publicado_en,'') publicado_en,
          (SELECT COUNT(*) FROM p1_recurso_archivos f WHERE f.recurso_id=r.id) archivos_count
          FROM p1_recursos r LEFT JOIN p1_recurso_detalles d ON d.recurso_id=r.id WHERE r.id=?''',(resource_id,)).fetchone()
        return dict(row) if row else None


def list_resources(kind='',search='',category='',status='',include_archived=False,path=None):
    sql='''SELECT r.*,COALESCE(d.autor,'') autor,COALESCE(d.version,'') version,
       COALESCE(d.publico,'') publico,COALESCE(d.acceso,'Interno') acceso,
       COALESCE(d.publicado_en,'') publicado_en,
       (SELECT COUNT(*) FROM p1_recurso_archivos f WHERE f.recurso_id=r.id) archivos_count
       FROM p1_recursos r LEFT JOIN p1_recurso_detalles d ON d.recurso_id=r.id WHERE 1=1'''
    params=[]
    if not include_archived:sql+=" AND r.estado<>'Archivado'"
    if kind:sql+=' AND r.tipo=?';params.append(kind)
    if category:sql+=' AND r.categoria=?';params.append(category)
    if status:sql+=' AND r.estado=?';params.append(status)
    if search:
        sql+=' AND (r.titulo LIKE ? OR r.descripcion LIKE ? OR r.categoria LIKE ? OR r.responsable LIKE ?)'
        params.extend([f'%{search}%']*4)
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(sql+' ORDER BY r.creado_en DESC,r.titulo COLLATE NOCASE',params)]


def archive_resource(resource_id,actor,path=None):
    actor=_required(actor,'quién archiva')
    with transaction(path) as con:
        row=con.execute('SELECT estado FROM p1_recursos WHERE id=?',(resource_id,)).fetchone()
        if row is None:raise ValidationError('Recurso inexistente.')
        if row['estado']=='Archivado':return
        con.execute("UPDATE p1_recursos SET estado='Archivado' WHERE id=?",(resource_id,))
        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor,antes_json) VALUES(?,?,?,?,?)',
                    ('recurso',resource_id,'archivar',actor,row['estado']))


def restore_resource(resource_id,status,actor,path=None):
    actor=_required(actor,'quién restaura')
    with transaction(path) as con:
        row=con.execute('SELECT tipo,estado FROM p1_recursos WHERE id=?',(resource_id,)).fetchone()
        if not row or row['estado']!='Archivado':raise ValidationError('El recurso no está archivado.')
        if status not in (SERVICE_STATUSES if row['tipo']=='Servicio' else RESOURCE_STATUSES) or status=='Archivado':
            raise ValidationError('Estado de recuperación inválido.')
        con.execute('UPDATE p1_recursos SET estado=? WHERE id=?',(status,resource_id))
        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor) VALUES(?,?,?,?)',
                    ('recurso',resource_id,'restaurar',actor))


def _validate_file(name,data):
    if not isinstance(data,bytes):raise ValidationError('No se pudo leer el archivo.')
    if not data or len(data)>MAX_BYTES:raise ValidationError('El archivo está vacío o supera 20 MB.')
    filename=Path(str(name)).name
    if filename!=name or '/' in name or '\\' in name:raise ValidationError('Nombre de archivo inseguro.')
    ext=filename.rsplit('.',1)[-1].lower() if '.' in filename else ''
    if ext not in EXTENSIONS:raise ValidationError('Formato no permitido: PDF, Word, Excel, PowerPoint, imágenes o texto.')
    if ext=='pdf' and not data.startswith(b'%PDF-'):raise ValidationError('El contenido no corresponde a un PDF.')
    if ext in ('png','jpg','jpeg','webp'):
        try:
            from PIL import Image
            with Image.open(BytesIO(data)) as img:
                actual=img.format
                img.verify()
            expected={'jpg':'JPEG','jpeg':'JPEG','png':'PNG','webp':'WEBP'}[ext]
            if actual != expected:raise ValueError('Formato de imagen no coincide con la extensión.')
        except Exception as exc:raise ValidationError('Imagen inválida o dañada.') from exc
    if ext in ('xlsx','docx','pptx'):
        expected={'xlsx':'xl/workbook.xml','docx':'word/document.xml','pptx':'ppt/presentation.xml'}[ext]
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                entries=z.infolist()
                if len(entries)>5000 or sum(e.file_size for e in entries)>100*1024*1024:
                    raise ValueError('Contenido comprimido excesivo.')
                if expected not in z.namelist():raise ValueError('Estructura Office inválida.')
                if any(n.lower().endswith('vbaproject.bin') for n in z.namelist()):
                    raise ValueError('No se admiten archivos con macros.')
        except (zipfile.BadZipFile,ValueError) as exc:raise ValidationError('Documento Office inválido o inseguro.') from exc
    if ext in ('md','txt'):
        try:data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:raise ValidationError('El archivo de texto debe estar en UTF-8.') from exc
    return filename,ext,MIMES[ext]


def save_file(resource_id,name,data,actor,version='1.0',path=None):
    actor=_required(actor,'quién carga');version=_required(version,'la versión')
    filename,ext,mime=_validate_file(name,data)
    with closing(connect(path)) as con:
        if not con.execute('SELECT id FROM p1_recursos WHERE id=?',(resource_id,)).fetchone():
            raise ValidationError('Seleccione un recurso existente.')
    folder=files_root(path)
    folder.mkdir(parents=True,exist_ok=True)
    key=uuid.uuid4().hex
    stored=f'{key}.{ext}'
    destination=folder/stored
    # El nombre persistido nunca proviene de la entrada del usuario.
    try:
        with destination.open('xb') as fp:
            fp.write(data)
            fp.flush();os.fsync(fp.fileno())
        with transaction(path) as con:
            con.execute("UPDATE p1_recurso_archivos SET estado='Anterior' WHERE recurso_id=? AND estado='Vigente'",(resource_id,))
            con.execute('''INSERT INTO p1_recurso_archivos
              (id,recurso_id,nombre_original,almacenado,mime,peso,hash_sha256,version,estado,actor)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',
              (key,resource_id,filename,stored,mime,len(data),sha256(data).hexdigest(),version,'Vigente',actor))
            con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor) VALUES (?,?,?,?)',
                        ('recurso',resource_id,'cargar_archivo',actor))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return key


def list_files(resource_id,path=None):
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute('''SELECT * FROM p1_recurso_archivos WHERE recurso_id=?
          ORDER BY CASE estado WHEN 'Vigente' THEN 0 ELSE 1 END,creado_en DESC''',(resource_id,))]


def read_file(file_id,path=None):
    with closing(connect(path)) as con:
        row=con.execute('SELECT * FROM p1_recurso_archivos WHERE id=?',(file_id,)).fetchone()
    if row is None:raise ValidationError('Archivo no encontrado.')
    file=files_root(path)/row['almacenado']
    if file.name!=row['almacenado'] or file.parent!=files_root(path):
        raise ValidationError('Ruta de archivo insegura.')
    if not file.is_file():raise ValidationError('El archivo no existe en esta instalación. Revise sus respaldos.')
    data=file.read_bytes()
    if sha256(data).hexdigest()!=row['hash_sha256']:
        raise ValidationError('Falló la comprobación de integridad del documento.')
    return data


def register_interaction(resource_id,action,actor,client_id=None,path=None):
    actor=_required(actor,'quién registra')
    if action not in ('Consulta registrada','Descarga iniciada'):
        raise ValidationError('Acción de interacción inválida.')
    if action=='Consulta registrada' and not client_id:
        raise ValidationError('Seleccione el cliente que consultó el recurso.')
    with transaction(path) as con:
        if not con.execute('SELECT id FROM p1_recursos WHERE id=?',(resource_id,)).fetchone():
            raise ValidationError('Recurso inexistente.')
        if client_id and not con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client_id,)).fetchone():
            raise ValidationError('Cliente inexistente.')
        eid=uuid.uuid4().hex
        con.execute('INSERT INTO p1_recurso_interacciones(id,recurso_id,cliente_id,accion,actor) VALUES (?,?,?,?,?)',
                    (eid,resource_id,client_id,action,actor))
    return eid


def stats(path=None):
    with closing(connect(path)) as con:
        published=con.execute("SELECT COUNT(*) FROM p1_recursos WHERE tipo<>'Servicio' AND estado='Publicado'").fetchone()[0]
        services=con.execute("SELECT COUNT(*) FROM p1_recursos WHERE tipo='Servicio' AND estado IN ('Piloto','Disponible')").fetchone()[0]
        consulted=con.execute("SELECT COUNT(DISTINCT cliente_id) FROM p1_recurso_interacciones WHERE accion='Consulta registrada' AND cliente_id IS NOT NULL").fetchone()[0]
        downloads=con.execute("SELECT COUNT(*) FROM p1_recurso_interacciones WHERE accion='Descarga iniciada'").fetchone()[0]
        total=con.execute("SELECT COUNT(*) FROM p1_recursos WHERE estado<>'Archivado'").fetchone()[0]
    return {'published':published,'services':services,'clients_consulted':consulted,'downloads_started':downloads,'total':total}
