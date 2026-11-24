"""Paso 01 · Eventos y campañas: extensión ADITIVA V0.25.

Mantiene las tablas y API p1_eventos/p1_campanas/p1_asistencias de V0.21–V0.24.
Los adjuntos se guardan en el directorio local de datos, nunca dentro del ZIP.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import sqlite3
import uuid
import zipfile

from . import awareness as aw
from .clients import ValidationError
from .config import database_path
from .storage import connect, transaction

IMAGE_TYPES = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}
DOC_TYPES = {'pdf': 'application/pdf',
             'xls': 'application/vnd.ms-excel',
             'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
             'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_DOC_BYTES = 20 * 1024 * 1024
STATUS_EVENT = ('Borrador', 'Programado', 'Realizado', 'Cancelado')
STATUS_CAMPAIGN = ('Borrador', 'Programada', 'En ejecución', 'Finalizada', 'Cancelada')


def _target(path=None) -> Path:
    return Path(path) if path is not None else database_path()


def media_root(path=None) -> Path:
    return _target(path).parent / 'evidencias_eventos'


def _backup_before_migration(path: Path):
    """SQLite backup consistente, guardado junto a la base, sólo antes de migrar."""
    if not path.is_file() or path.stat().st_size == 0:
        return None
    backup = path.with_name(path.stem + '.antes_V0_25.sqlite3')
    if not backup.exists():
        with closing(connect(path)) as src, closing(sqlite3.connect(str(backup))) as dest:
            src.backup(dest)
    return backup


def initialize(path=None):
    """Migración idempotente, con copia de seguridad previa de bases antiguas."""
    file = _target(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(file)) as con:
        exists = bool(con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='p1_eventos'").fetchone())
        if not exists:
            raise RuntimeError('Primero ejecute pmo.storage.initialize().')
        ev_cols = {r['name'] for r in con.execute('PRAGMA table_info(p1_eventos)')}
        ca_cols = {r['name'] for r in con.execute('PRAGMA table_info(p1_campanas)')}
        has_media = bool(con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='p1_adjuntos'").fetchone())
        changes = bool({'descripcion','objetivo'} - ev_cols or {'descripcion','objetivo'} - ca_cols or not has_media)
    if changes:
        _backup_before_migration(file)
    with transaction(file) as con:
        for table, fields in [('p1_eventos', ['descripcion', 'objetivo']),
                              ('p1_campanas', ['descripcion', 'objetivo'])]:
            cols = {r['name'] for r in con.execute(f'PRAGMA table_info({table})')}
            for col in fields:
                if col not in cols:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        con.execute('''CREATE TABLE IF NOT EXISTS p1_resultados_evento (
          evento_id TEXT PRIMARY KEY REFERENCES p1_eventos(id),
          meta_participantes INTEGER CHECK(meta_participantes IS NULL OR meta_participantes>0),
          productos TEXT NOT NULL DEFAULT '', observaciones TEXT NOT NULL DEFAULT '',
          actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        con.execute('''CREATE TABLE IF NOT EXISTS p1_satisfaccion_evento (
          evento_id TEXT NOT NULL REFERENCES p1_eventos(id),
          cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
          puntuacion INTEGER NOT NULL CHECK(puntuacion BETWEEN 1 AND 5),
          registrado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(evento_id,cliente_id))''')
        con.execute('''CREATE TABLE IF NOT EXISTS p1_adjuntos (
          id TEXT PRIMARY KEY,
          entidad TEXT NOT NULL CHECK(entidad IN ('evento','campana')),
          entidad_id TEXT NOT NULL,
          clase TEXT NOT NULL CHECK(clase IN ('imagen','documento')),
          nombre TEXT NOT NULL, titulo TEXT NOT NULL DEFAULT '',
          descripcion TEXT NOT NULL DEFAULT '', categoria TEXT NOT NULL DEFAULT '',
          mime TEXT NOT NULL, tamano INTEGER NOT NULL,
          sha256 TEXT NOT NULL, ruta TEXT NOT NULL UNIQUE,
          creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          eliminado INTEGER NOT NULL DEFAULT 0 CHECK(eliminado IN (0,1)))''')
        con.execute('''CREATE INDEX IF NOT EXISTS idx_p1_adjuntos_entidad
                       ON p1_adjuntos(entidad,entidad_id,eliminado)''')
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (25)')


def _check_entity(con, kind: str, key: str):
    table = {'evento': 'p1_eventos', 'campana': 'p1_campanas'}.get(kind)
    if not table or not con.execute(f'SELECT 1 FROM {table} WHERE id=?', (key,)).fetchone():
        raise ValidationError('La actividad o campaña seleccionada no existe.')


def update_event(event_id, *, title, day, kind, audience, modality, owner, status, description='', objective='', actor, path=None):
    if status not in STATUS_EVENT:
        raise ValidationError('Estado de actividad inválido.')
    title = aw._require(title, 'el nombre de la actividad')
    owner = aw._require(owner, 'el responsable')
    actor = aw._require(actor, 'quién modifica')
    with transaction(path) as con:
        prev = con.execute('SELECT * FROM p1_eventos WHERE id=?', (event_id,)).fetchone()
        if prev is None:
            raise ValidationError('Actividad inexistente.')
        if prev['estado'] == 'Cancelado' and status != 'Cancelado':
            raise ValidationError('No se puede reabrir una actividad cancelada.')
        con.execute('''UPDATE p1_eventos SET titulo=?,fecha=?,tipo=?,publico=?,modalidad=?,
                       responsable=?,estado=?,descripcion=?,objetivo=? WHERE id=?''',
                    (title, aw._iso_date(day),kind,audience,modality,owner,status,description,objective,event_id))
        aw._audit(con,'evento',event_id,'editar',actor,f"Estado: {prev['estado']} -> {status}")


def update_campaign(campaign_id, *, title, day, audience, channel, owner, status, description='', objective='', actor, path=None):
    if status not in STATUS_CAMPAIGN:
        raise ValidationError('Estado de campaña inválido.')
    title = aw._require(title, 'el nombre de la campaña')
    owner = aw._require(owner, 'el responsable')
    actor = aw._require(actor, 'quién modifica')
    with transaction(path) as con:
        prev=con.execute('SELECT * FROM p1_campanas WHERE id=?',(campaign_id,)).fetchone()
        if not prev:
            raise ValidationError('Campaña inexistente.')
        con.execute('''UPDATE p1_campanas SET titulo=?,fecha_inicio=?,audiencia=?,canal=?,
                       responsable=?,estado=?,descripcion=?,objetivo=? WHERE id=?''',
                    (title,aw._iso_date(day),audience,channel,owner,status,description,objective,campaign_id))
        aw._audit(con,'campana',campaign_id,'editar',actor,f"Estado: {prev['estado']} -> {status}")



def delete_campaign(campaign_id: str, actor: str, path=None) -> Path:
    """Elimina una campaña sin adjuntos activos, con respaldo y auditoría.

    No permite eliminar evidencias implícitamente. Las evidencias deben
    retirarse desde la galería antes de confirmar el borrado de la campaña.
    """
    actor = aw._require(actor, 'responsable de eliminación')
    db = _target(path)
    if not db.is_file():
        raise ValidationError('La base de datos no existe.')
    with closing(connect(db)) as con:
        row = con.execute('SELECT * FROM p1_campanas WHERE id=?', (campaign_id,)).fetchone()
        if row is None:
            raise ValidationError('Campaña inexistente o ya eliminada.')
        attachments = con.execute("SELECT COUNT(*) FROM p1_adjuntos WHERE entidad='campana' AND entidad_id=? AND eliminado=0", (campaign_id,)).fetchone()[0]
        if attachments:
            raise ValidationError(f'La campaña tiene {attachments} evidencia(s). '
                                  'Elimínalas desde la galería antes de eliminar la campaña.')
    backup_dir = db.parent / 'respaldos_campanas'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (db.stem + '_ANTES_ELIMINAR_CAMPANA_' +
                           datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
    with closing(connect(db)) as source, closing(sqlite3.connect(str(backup))) as destination:
        source.backup(destination)
    with transaction(db) as con:
        current = con.execute('SELECT * FROM p1_campanas WHERE id=?', (campaign_id,)).fetchone()
        if current is None:
            raise ValidationError('Campaña inexistente o ya eliminada.')
        attached = con.execute("SELECT COUNT(*) FROM p1_adjuntos WHERE entidad='campana' AND entidad_id=? AND eliminado=0", (campaign_id,)).fetchone()[0]
        if attached:
            raise ValidationError('Se añadieron evidencias a esta campaña. '
                                  'Elimínalas primero; no se ha borrado la campaña.')
        # Las evidencias ya retiradas conservan su acción histórica en auditoría.
        con.execute("DELETE FROM p1_adjuntos WHERE entidad='campana' AND entidad_id=? AND eliminado=1", (campaign_id,))
        con.execute('DELETE FROM p1_campanas WHERE id=?', (campaign_id,))
        aw._audit(con, 'campana', campaign_id, 'eliminar', actor,
                  f"Campaña: {current['titulo']}; respaldo: {backup.name}")
    return backup


def create_activity(*, kind, title, day, audience, mode, owner, status, description='', objective='', actor, path=None):
    """Alta atómica compatible con tablas originales, sin registros parciales."""
    title=aw._require(title,'el nombre de la actividad')
    owner=aw._require(owner,'el responsable')
    actor=aw._require(actor,'quién registra la actividad')
    dt=aw._iso_date(day)
    key=uuid.uuid4().hex
    if kind=='Evento' and status in STATUS_EVENT:
        with transaction(path) as con:
            con.execute('''INSERT INTO p1_eventos
              (id,titulo,tipo,fecha,publico,modalidad,responsable,estado,descripcion,objetivo)
              VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (key,title,'Evento',dt,audience,mode,owner,status,description,objective))
            aw._audit(con,'evento',key,'crear',actor)
        return 'evento',key
    if kind=='Campaña' and status in STATUS_CAMPAIGN:
        with transaction(path) as con:
            con.execute('''INSERT INTO p1_campanas
              (id,titulo,audiencia,canal,fecha_inicio,estado,responsable,descripcion,objetivo)
              VALUES (?,?,?,?,?,?,?,?,?)''',
              (key,title,audience,mode,dt,status,owner,description,objective))
            aw._audit(con,'campana',key,'crear',actor)
        return 'campana',key
    raise ValidationError('Tipo o estado de actividad no permitido.')


def fetch_event(event_id, path=None):
    with closing(connect(path)) as con:
        r=con.execute('SELECT * FROM p1_eventos WHERE id=?',(event_id,)).fetchone()
        return dict(r) if r else None


def fetch_campaign(campaign_id, path=None):
    with closing(connect(path)) as con:
        r=con.execute('SELECT * FROM p1_campanas WHERE id=?',(campaign_id,)).fetchone()
        return dict(r) if r else None


def save_results(event_id, meta, products, observations, actor, path=None):
    actor = aw._require(actor, 'quién registra los resultados')
    if meta is not None and (not isinstance(meta,int) or meta <= 0):
        raise ValidationError('La meta de participantes debe ser mayor que cero.')
    with transaction(path) as con:
        _check_entity(con,'evento',event_id)
        con.execute('''INSERT INTO p1_resultados_evento (evento_id,meta_participantes,productos,observaciones)
                       VALUES (?,?,?,?) ON CONFLICT(evento_id) DO UPDATE SET
                       meta_participantes=excluded.meta_participantes,productos=excluded.productos,
                       observaciones=excluded.observaciones,actualizado_en=CURRENT_TIMESTAMP''',
                    (event_id,meta,products.strip(),observations.strip()))
        aw._audit(con,'resultados_evento',event_id,'actualizar',actor)


def get_results(event_id,path=None):
    with closing(connect(path)) as con:
        row=con.execute('SELECT * FROM p1_resultados_evento WHERE evento_id=?',(event_id,)).fetchone()
        return dict(row) if row else {}


def record_satisfaction(event_id, client_id, score, actor, path=None):
    actor=aw._require(actor,'quién registra la calificación')
    if not isinstance(score,int) or score not in range(1,6):
        raise ValidationError('La satisfacción debe estar entre 1 y 5.')
    with transaction(path) as con:
        _check_entity(con,'evento',event_id)
        attendance=con.execute('SELECT asistio FROM p1_asistencias WHERE evento_id=? AND cliente_id=?',(event_id,client_id)).fetchone()
        if attendance is None or attendance['asistio'] != 1:
            raise ValidationError('La persona debe tener una asistencia confirmada.')
        con.execute('''INSERT INTO p1_satisfaccion_evento(evento_id,cliente_id,puntuacion) VALUES(?,?,?)
                       ON CONFLICT(evento_id,cliente_id) DO UPDATE SET puntuacion=excluded.puntuacion,
                       registrado_en=CURRENT_TIMESTAMP''',(event_id,client_id,score))
        aw._audit(con,'satisfaccion_evento',event_id,'registrar',actor,client_id)


def summary(path=None):
    with closing(connect(path)) as con:
        rows=con.execute('''SELECT
          (SELECT COUNT(*) FROM p1_eventos WHERE estado='Realizado') AS realizados,
          (SELECT COUNT(DISTINCT a.cliente_id) FROM p1_asistencias a JOIN p1_eventos e ON e.id=a.evento_id WHERE a.asistio=1 AND e.estado<>'Cancelado') AS unicos,
          (SELECT COUNT(*) FROM p1_asistencias a JOIN p1_eventos e ON e.id=a.evento_id WHERE a.asistio=1 AND e.estado<>'Cancelado') AS asistencias,
          (SELECT COUNT(*) FROM p1_campanas) AS campanas''').fetchone()
        return dict(rows)


def event_stats(event_id,path=None):
    with closing(connect(path)) as con:
        attendee=con.execute('SELECT COUNT(*) FROM p1_asistencias WHERE evento_id=? AND asistio=1',(event_id,)).fetchone()[0]
        rating=con.execute('SELECT AVG(puntuacion) AS promedio,COUNT(*) AS total FROM p1_satisfaccion_evento WHERE evento_id=?',(event_id,)).fetchone()
        n=con.execute('SELECT COUNT(*) FROM p1_adjuntos WHERE entidad=? AND entidad_id=? AND eliminado=0',('evento',event_id)).fetchone()[0]
        return dict(asistentes=attendee,satisfaccion=rating['promedio'],respuestas=rating['total'],evidencias=n)


def list_attachments(kind='',entity_id='',file_class='',category='',path=None):
    sql='SELECT * FROM p1_adjuntos WHERE eliminado=0'; args=[]
    for field,val in [('entidad',kind),('entidad_id',entity_id),('clase',file_class),('categoria',category)]:
        if val:
            sql+=f' AND {field}=?'; args.append(val)
    with closing(connect(path)) as con:
        return [dict(row) for row in con.execute(sql+' ORDER BY creado_en DESC, id DESC',args).fetchall()]


def _validate_content(data: bytes, filename: str, file_class: str):
    if not isinstance(data,bytes) or not data:
        raise ValidationError('Archivo vacío o no válido.')
    suffix=Path(filename).suffix.lower().lstrip('.')
    types=IMAGE_TYPES if file_class=='imagen' else DOC_TYPES if file_class=='documento' else {}
    if suffix not in types:
        raise ValidationError('Formato no permitido para esta evidencia.')
    if len(data) > (MAX_IMAGE_BYTES if file_class=='imagen' else MAX_DOC_BYTES):
        raise ValidationError('El archivo supera el tamaño máximo permitido.')
    if file_class=='imagen':
        try:
            from PIL import Image, UnidentifiedImageError
            with Image.open(BytesIO(data)) as im:
                if im.format.lower() not in (('jpeg' if suffix=='jpg' else suffix), ('jpeg' if suffix=='jpeg' else suffix)):
                    raise ValueError('Extensión y contenido no coinciden')
                im.verify()
        except Exception as exc:
            # Pillow valida también la estructura completa del archivo.
            raise ValidationError('La imagen no es válida o no coincide con su extensión.') from exc
    elif suffix=='pdf':
        if not data.startswith(b'%PDF-'):
            raise ValidationError('No es un archivo PDF válido.')
    elif suffix=='xls':
        if not data.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
            raise ValidationError('No es un archivo Excel .xls válido.')
    else:
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if (len(z.infolist())>500 or sum(i.file_size for i in z.infolist())>100*1024*1024
                    or z.testzip() is not None or '[Content_Types].xml' not in z.namelist()):
                    raise ValueError('Paquete Office inválido')
        except (zipfile.BadZipFile, ValueError) as exc:
            raise ValidationError('Documento Office no válido.') from exc
    return suffix,types[suffix]


def save_attachment(kind,entity_id,file_class,filename,content,*,title='',description='',category='',actor,path=None):
    actor=aw._require(actor,'quién carga la evidencia')
    suffix,mime=_validate_content(content,filename,file_class)
    if len(title) > 180 or len(description) > 2000 or len(category) > 100:
        raise ValidationError('Los metadatos de la evidencia superan el tamaño permitido.')
    file_id=uuid.uuid4().hex
    relative=f'{file_class}/{file_id}.{suffix}'
    destination=media_root(path)/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp=destination.with_name(destination.name+'.tmp')
    with closing(connect(path)) as con:
        _check_entity(con,kind,entity_id)
    try:
        # Primero fichero exclusivo y luego metadatos. Si falla la BD, se limpia.
        with open(temp,'xb') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(temp,destination)
        with transaction(path) as con:
            _check_entity(con,kind,entity_id)
            con.execute('''INSERT INTO p1_adjuntos(id,entidad,entidad_id,clase,nombre,titulo,descripcion,
                         categoria,mime,tamano,sha256,ruta) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (file_id,kind,entity_id,file_class,Path(filename).name,title or Path(filename).stem,
                         description,category,mime,len(content),sha256(content).hexdigest(),relative))
            aw._audit(con,'adjunto',file_id,'cargar',actor,f'{kind}:{entity_id}')
        return file_id
    except Exception:
        temp.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def file_path(attachment,path=None):
    """Ruta local segura: el nombre real siempre lo genera la aplicación."""
    if attachment.get('eliminado'):
        return None
    relative=Path(attachment['ruta'])
    if relative.is_absolute() or '..' in relative.parts:
        return None
    root=media_root(path).resolve()
    dest=(root/relative).resolve()
    if not dest.is_relative_to(root) or not dest.is_file():
        return None
    return dest


def delete_attachment(file_id,actor,path=None):
    actor=aw._require(actor,'quién elimina')
    with transaction(path) as con:
        row=con.execute('SELECT * FROM p1_adjuntos WHERE id=? AND eliminado=0',(file_id,)).fetchone()
        if not row:
            raise ValidationError('Evidencia inexistente o eliminada.')
        con.execute('UPDATE p1_adjuntos SET eliminado=1 WHERE id=?',(file_id,))
        aw._audit(con,'adjunto',file_id,'eliminar',actor,f'{row["entidad"]}:{row["entidad_id"]}')
    # El fichero ya no aparece para nadie; borrar el binario sólo después del commit.
    file=file_path(dict(row),path)
    if file:
        file.unlink(missing_ok=True)


def replace_attendance(event_id, client_ids, actor, path=None):
    """Registro atómico de asistentes seleccionados; el resto de datos no se toca."""
    actor=aw._require(actor,'quién registra las asistencias')
    chosen=set(client_ids)
    with transaction(path) as con:
        event=con.execute('SELECT estado FROM p1_eventos WHERE id=?',(event_id,)).fetchone()
        if not event or event['estado']=='Cancelado':
            raise ValidationError('El evento no existe o está cancelado.')
        if chosen:
            placeholders=','.join('?' for _ in chosen)
            available={r[0] for r in con.execute('SELECT id FROM pmo_clientes WHERE id IN ('+placeholders+')',tuple(chosen))}
            if chosen != available:
                raise ValidationError('Uno o más asistentes no existen.')
        previous={r[0] for r in con.execute('SELECT cliente_id FROM p1_asistencias WHERE evento_id=? AND asistio=1',(event_id,))}
        for cid in previous-chosen:
            con.execute('UPDATE p1_asistencias SET asistio=0 WHERE evento_id=? AND cliente_id=?',(event_id,cid))
        for cid in chosen-previous:
            con.execute('''INSERT INTO p1_asistencias(evento_id,cliente_id,asistio) VALUES (?,?,1)
                           ON CONFLICT(evento_id,cliente_id) DO UPDATE SET asistio=1''',(event_id,cid))
        aw._audit(con,'asistencia',event_id,'actualizar_lote',actor,f'Presentes: {len(chosen)}')
    return len(chosen)
