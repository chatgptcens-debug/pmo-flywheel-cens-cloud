"""Gestión de clientes V0.24: persistencia, campos propios e importación Excel.

Mantiene las tablas de V0.21 y la misma SQLite para los diez pasos. Todas las
operaciones de carga se validan en una transacción y se confirman sólo si no hay errores.
"""
from __future__ import annotations

import json
import posixpath
import re
import sqlite3
import unicodedata
import uuid
import zipfile
from contextlib import closing
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from .clients import FIELDS, ValidationError, normalize, _department
from .excel_import import (
    N, _audit, _column_index, _insert, _safe_member, _text, _value, _bool, _date, _score,
    MAX_FILE, MAX_SHEET_ROWS, MAX_TOTAL_ROWS,
)
from .storage import connect, transaction
from .config import database_path

EXTRA_LABELS = {
    'equipo_trabajo': 'Equipo de trabajo',
    'rol_especifico': 'Rol',
    'estado_gestion': 'Estado de gestión',
}
DISPLAY_COLUMNS = {
    'nombre': 'Cliente', 'codigo': 'Código', 'dependencia': 'Dependencia',
    'cargo': 'Cargo actual', 'equipo_trabajo': 'Equipo de trabajo',
    'rol_especifico': 'Rol', 'estado_gestion': 'Estado de gestión',
    'influencia': 'Influencia', 'interes': 'Interés', 'relacionamiento': 'Relacionamiento',
    'correo': 'Correo', 'segmento': 'Rol (legado)',
    'conocimiento': 'Conocimiento PMO', 'participa_proyectos': 'Participa en proyectos',
    'canal': 'Canal preferido', 'retos': 'Retos',
    'necesidades_preliminares': 'Necesidades preliminares',
    'beneficios_esperados': 'Beneficios esperados', 'barreras': 'Barreras',
    'responsable': 'Responsable PMO', 'primer_contacto': 'Primer contacto',
    'observaciones': 'Observaciones', 'embajador': 'Embajador PMO', 'activo': 'Estado',
}
DEFAULT_VISIBLE = ['nombre','codigo','dependencia','cargo','rol_especifico','influencia','activo']


def custom_columns(path: Path | None = None) -> list[dict]:
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(
            'SELECT * FROM p1_client_custom_columns ORDER BY posicion, nombre COLLATE NOCASE')]


def add_custom_column(name: str, typ: str, actor: str, path: Path | None = None) -> str:
    name = name.strip()
    if not actor.strip():
        raise ValidationError('Indique responsable de la modificación.')
    if not 2 <= len(name) <= 55 or any(c in name for c in '<>\r\n'):
        raise ValidationError('Indique un nombre válido de 2 a 55 caracteres.')
    if name.casefold() in {n.casefold() for n in DISPLAY_COLUMNS.values()} or name.casefold() in {k.casefold() for k in FIELDS}:
        raise ValidationError('Este campo ya existe entre los campos estándar.')
    if typ not in ('Texto','Número','Fecha'):
        raise ValidationError('Tipo de campo no permitido.')
    key = uuid.uuid4().hex
    try:
        with transaction(path) as con:
            pos=con.execute('SELECT COALESCE(MAX(posicion),0)+1 FROM p1_client_custom_columns').fetchone()[0]
            if pos > 30:
                raise ValidationError('Máximo 30 columnas personalizadas.')
            con.execute('INSERT INTO p1_client_custom_columns(id,nombre,tipo,posicion) VALUES(?,?,?,?)', (key,name,typ,pos))
            _audit(con,'columna_cliente',key,'crear',actor,json.dumps({'nombre':name,'tipo':typ},ensure_ascii=False))
    except sqlite3.IntegrityError as exc:
        raise ValidationError('Ya existe una columna con ese nombre.') from exc
    return key


def remove_custom_column(key: str, actor: str, path: Path | None = None) -> None:
    if not actor.strip():
        raise ValidationError('Indique responsable de la modificación.')
    with transaction(path) as con:
        r=con.execute('SELECT nombre FROM p1_client_custom_columns WHERE id=?',(key,)).fetchone()
        if not r:
            raise ValidationError('La columna seleccionada ya no existe.')
        # Eliminación intencionada de campo personalizado y sus valores, con auditoría.
        con.execute('DELETE FROM p1_client_custom_values WHERE columna_id=?',(key,))
        con.execute('DELETE FROM p1_client_custom_columns WHERE id=?',(key,))
        _audit(con,'columna_cliente',key,'eliminar',actor,r['nombre'])


def custom_values_for_clients(ids: list[str], path: Path | None = None) -> dict[str, dict[str,str]]:
    if not ids:
        return {}
    with closing(connect(path)) as con:
        result={}
        for i in range(0,len(ids),300):
            batch=ids[i:i+300]
            sql='SELECT cliente_id,columna_id,valor FROM p1_client_custom_values WHERE cliente_id IN ('+','.join('?' for _ in batch)+')'
            for r in con.execute(sql,batch):
                result.setdefault(r['cliente_id'],{})[r['columna_id']]=r['valor']
        return result


def save_custom_values(client_id: str, data: dict[str,str], actor: str, path: Path | None = None) -> None:
    if not actor.strip():
        raise ValidationError('Indique responsable de la modificación.')
    valid={c['id']:c for c in custom_columns(path)}
    with transaction(path) as con:
        if not con.execute('SELECT 1 FROM pmo_clientes WHERE id=?',(client_id,)).fetchone():
            raise ValidationError('Cliente no encontrado.')
        for key,val in data.items():
            if key not in valid:
                raise ValidationError('Columna personalizada no válida.')
            v=str(val or '').strip()
            if len(v)>1000:
                raise ValidationError('Máximo 1.000 caracteres por dato personalizado.')
            if v and valid[key]['tipo']=='Número':
                try: float(v.replace(',','.'))
                except ValueError as exc: raise ValidationError(f'{valid[key]["nombre"]}: número no válido.') from exc
            if v and valid[key]['tipo']=='Fecha':
                from datetime import date
                try: date.fromisoformat(v)
                except ValueError as exc: raise ValidationError(f'{valid[key]["nombre"]}: fecha AAAA-MM-DD requerida.') from exc
            con.execute('INSERT INTO p1_client_custom_values(cliente_id,columna_id,valor) VALUES(?,?,?) '
                        'ON CONFLICT(cliente_id,columna_id) DO UPDATE SET valor=excluded.valor',(client_id,key,v))
        _audit(con,'cliente',client_id,'campos_personalizados',actor,json.dumps(data,ensure_ascii=False))


def remove_clients(ids: list[str], actor: str, path: Path | None = None, *, permanently=False) -> int:
    """Archiva por defecto para proteger vínculos de todos los pasos.

    Eliminación definitiva sólo si SQLite permite las referencias; se desaconseja
    fuera de una base de pruebas y requiere decisión explícita en la UI.
    """
    ids=list(dict.fromkeys(ids))
    if not ids or not actor.strip():
        raise ValidationError('Seleccione clientes e indique responsable de la operación.')
    with transaction(path) as con:
        for client_id in ids:
            old=con.execute('SELECT codigo,nombre,activo FROM pmo_clientes WHERE id=?',(client_id,)).fetchone()
            if not old:
                raise ValidationError('Un cliente seleccionado ya no existe. Actualice la tabla.')
            if permanently:
                # Verificación de referencias en TODAS las tablas del sistema, no sólo en el Paso 1.
                for fk_table in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                    table=fk_table['name']
                    if table in ('pmo_auditoria','p1_client_custom_values'):
                        continue
                    for fk in con.execute(f'PRAGMA foreign_key_list("{table}")'):
                        if fk['table']=='pmo_clientes' and fk['to']=='id':
                            referenced=con.execute(f'SELECT 1 FROM "{table}" WHERE "{fk["from"]}"=? LIMIT 1',(client_id,)).fetchone()
                            if referenced:
                                raise ValidationError(f'El cliente {old["codigo"]} tiene registros vinculados en {table}. Use «Archivar» para conservarlos.')
                con.execute('DELETE FROM p1_client_custom_values WHERE cliente_id=?',(client_id,))
                con.execute('DELETE FROM pmo_clientes WHERE id=?',(client_id,))
                _audit(con,'cliente',client_id,'eliminar_definitivo',actor,json.dumps(dict(old),ensure_ascii=False))
            else:
                con.execute('UPDATE pmo_clientes SET activo=0, actualizado_en=CURRENT_TIMESTAMP WHERE id=?',(client_id,))
                _audit(con,'cliente',client_id,'archivar',actor,json.dumps(dict(old),ensure_ascii=False))
    return len(ids)


def normalized_label(text: str) -> str:
    form=unicodedata.normalize('NFKD',str(text or ''))
    return re.sub(r'[^a-z0-9]+','_', ''.join(c for c in form if not unicodedata.combining(c)).casefold()).strip('_')


FIELD_ALIASES = {
    'codigo': ('id','codigo interno','código','código corporativo'),
    'nombre': ('cliente','nombre completo','nombre'),
    'cargo': ('cargo actual','cargo'),
    'dependencia': ('area','área','dependencia'),
    'equipo_trabajo': ('equipo de trabajo',),
    'rol_especifico': ('rol específico','rol especifico','rol','grupo / segmento','grupo','segmento','grupo de clientes','grupo de priorización','grupo de priorizacion'),
    'estado_gestion': ('estado original','estado gestión','estado de gestión'),
    'activo': ('cliente activo','activo'),
    'segmento': ('grupo', 'grupo de clientes', 'grupo de priorizacion', 'grupo de priorización', 'grupo / segmento', 'segmento'),
}


def suggested_mapping(headers: list[str], extras: list[dict] | None = None) -> dict[str,str]:
    # Rol es un único campo de entrada. Segmento solo se conserva como
    # espejo interno para compatibilidad con V5; nunca se propone dos veces.
    lookup={normalized_label(h):h for h in headers}
    keys=[k for k in FIELDS if k!='segmento']+['extra:'+c['id'] for c in (extras or [])]
    res={k:'' for k in FIELDS}
    used=set()
    for key in keys:
        aliases=[key, DISPLAY_COLUMNS.get(key,key), *FIELD_ALIASES.get(key,())]
        if key.startswith('extra:'):
            aliases=[c['nombre'] for c in extras if c['id']==key.split(':',1)[1]]
        selected=next((lookup[normalized_label(a)] for a in aliases
                       if normalized_label(a) in lookup and lookup[normalized_label(a)] not in used),'')
        res[key]=selected
        if selected:used.add(selected)
    return res


def read_client_sheets(data: bytes) -> dict[str, list[tuple[int,dict]]]:
    """Lectura segura XLSX compatible con 'Clientes' y 'Mapa Clientes Potenciales'."""
    if not data or len(data)>MAX_FILE or not zipfile.is_zipfile(BytesIO(data)):
        raise ValidationError('Adjunte un Excel .xlsx válido de máximo 8 MB.')
    result={}
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            if len(z.infolist())>600 or sum(i.file_size for i in z.infolist())>55_000_000:
                raise ValidationError('Archivo demasiado grande para importar.')
            if any(i.filename.endswith('vbaProject.bin') for i in z.infolist()):
                raise ValidationError('No se admiten archivos con macros.')
            book=ET.fromstring(_safe_member(z,'xl/workbook.xml'))
            rels=ET.fromstring(_safe_member(z,'xl/_rels/workbook.xml.rels'))
            relmap={r.get('Id'):r.get('Target') for r in rels}
            shared=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                root=ET.fromstring(_safe_member(z,'xl/sharedStrings.xml'))
                shared=[''.join(t.text or '' for t in si.findall('.//x:t',N)) for si in root.findall('x:si',N)]
            for sheet in book.findall('x:sheets/x:sheet',N):
                name=sheet.get('name','')
                if len(result)>=12: break
                target=relmap.get(sheet.get(f'{{{N["r"]}}}id'),'')
                if not target: continue
                member_path=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
                if not member_path.startswith('xl/'): raise ValidationError('Ruta de hoja Excel inválida.')
                root=ET.fromstring(_safe_member(z,member_path))
                rows=[]
                for line in root.findall('.//x:sheetData/x:row',N):
                    number=int(line.get('r',str(len(rows)+1)))
                    values={_column_index(cell.get('r','')):_value(cell,shared)
                            for cell in line.findall('x:c',N) if _column_index(cell.get('r','')) < 100}
                    if any(_text(v) for v in values.values()):
                        rows.append((number,values))
                    if len(rows)>MAX_SHEET_ROWS+1: raise ValidationError('La hoja supera 2.000 registros.')
                if not rows: continue
                headers={i:_text(v).strip() for i,v in rows[0][1].items() if _text(v)}
                if not headers or len(set(normalized_label(v) for v in headers.values()))!=len(headers):
                    raise ValidationError(f'Encabezados inválidos o duplicados en {name}.')
                contents=[]
                for number, values in rows[1:]:
                    # Preservar las columnas del encabezado aun cuando sus celdas estén vacías:
                    # el usuario debe poder mapear los 22 campos originales del archivo.
                    entry={heading:_text(values.get(idx,'')) for idx,heading in headers.items()}
                    if any(entry.values()):contents.append((number,entry))
                if contents: result[name]=contents
        if not result: raise ValidationError('El archivo no contiene registros legibles.')
        if sum(map(len,result.values()))>MAX_TOTAL_ROWS:
            raise ValidationError('Demasiados registros para importar.')
        return result
    except (zipfile.BadZipFile,ET.ParseError,KeyError,IndexError) as exc:
        raise ValidationError('No fue posible interpretar el archivo Excel.') from exc


def source_data_fields(row: dict) -> dict:
    """Recupera los campos estructurales documentados en observaciones de la plantilla previa."""
    r=dict(row)
    notes=str(r.get('observaciones') or '')
    patterns={
        'equipo_trabajo':r'Equipo de trabajo \(fuente\):\s*(.*?)(?=\s*\|\s*|$)',
        'rol_especifico':r'Rol específico \(fuente\):\s*(.*?)(?=\s*\|\s*|$)',
        'estado_gestion':r'Estado original de la matriz:\s*(.*?)(?=\s*\|\s*|$)',
    }
    for field,pat in patterns.items():
        if not _text(r.get(field)):
            match=re.search(pat,notes,flags=re.I)
            if match:r[field]=match.group(1).strip()
    return r


def _mapped_value(field: str, value: str):
    """Convierte las columnas suministradas, sin inferir información ausente."""
    if field in ('activo', 'embajador'):
        return _bool(value, field, default=(field=='activo'))
    if field=='conocimiento':
        return _score(value, field) if _text(value) else None
    if field=='primer_contacto':
        return _date(value) if _text(value) else None
    return _text(value)


def _check_extra(value: str, column: dict) -> str:
    extra=_text(value)
    if len(extra)>1000:
        raise ValidationError(f'{column["nombre"]}: máximo 1.000 caracteres.')
    if extra and column['tipo']=='Número':
        try: float(extra.replace(',','.'))
        except ValueError as exc: raise ValidationError(f'{column["nombre"]}: número inválido.') from exc
    if extra and column['tipo']=='Fecha':
        from datetime import date
        try: date.fromisoformat(extra)
        except ValueError as exc: raise ValidationError(f'{column["nombre"]}: fecha AAAA-MM-DD requerida.') from exc
    return extra


def mapped_client_import(
    source_rows: list[tuple[int, dict]], mapping: dict[str, str], actor: str,
    path: Path | None = None, *, confirm: bool = False,
    mode: str = 'add', overwrite_blanks: bool = False,
) -> list[dict]:
    """Carga atómica, con vista previa idéntica a confirmación.

    mode='add': comportamiento histórico, omite repetidos.
    mode='upsert': actualiza por código sin sustituir ID ni vínculos; añade nuevos.
    Las celdas vacías se ignoran salvo que overwrite_blanks se solicite. Los
    indicadores booleanos vacíos siempre se ignoran porque no equivalen a 'No'.
    """
    if not actor or not actor.strip():
        raise ValidationError('Indique el responsable de la carga.')
    if mode not in ('add','upsert'):
        raise ValidationError('Modo de importación inválido.')
    if not mapping.get('codigo') or not mapping.get('nombre') or not mapping.get('dependencia'):
        raise ValidationError('Mapee Código, Nombre y Dependencia.')
    choices=[x for x in mapping.values() if x]
    if len(set(choices)) != len(choices):
        raise ValidationError('La misma columna Excel no puede asignarse a dos campos.')
    if not source_rows: raise ValidationError('No hay filas para importar.')
    metadata={c['id']:c for c in custom_columns(path)}
    for key in mapping:
        if key.startswith('extra:') and key[6:] not in metadata:
            raise ValidationError('Campo personalizado no reconocido en la base de datos.')
    con=connect(path)
    result=[]
    seen=set()
    try:
        con.execute('BEGIN IMMEDIATE')
        for rownum,raw in source_rows:
            con.execute('SAVEPOINT fila_cliente')
            try:
                data={field:raw[col] for field,col in mapping.items()
                      if col and col in raw and not field.startswith('extra:')}
                # Una columna histórica Grupo/Segmento no desplaza el Rol específico
                # documentado en las observaciones de la matriz original.
                legacy_role_headers={'grupo','segmento','grupo_segmento','grupo_de_clientes','grupo_de_priorizacion'}
                if normalized_label(mapping.get('rol_especifico','')) in legacy_role_headers:
                    data['segmento']=data.pop('rol_especifico','')
                data=source_data_fields(data)
                from .v0391_clients import canonical_role
                imported_role=canonical_role(data.get('rol_especifico') or data.get('segmento'))
                if imported_role:
                    data['rol_especifico']=imported_role
                    data['segmento']=imported_role
                elif overwrite_blanks and (mapping.get('rol_especifico') or mapping.get('segmento')):
                    data['rol_especifico']=data['segmento']=''
                code=_text(data.get('codigo')).upper()
                if not code:
                    raise ValidationError('Código vacío en la fila de origen.')
                if code.casefold() in seen:
                    raise ValidationError(f'Código {code} repetido dentro del mismo Excel.')
                seen.add(code.casefold())
                old=con.execute("SELECT c.*,d.nombre AS dependencia FROM pmo_clientes c JOIN pmo_dependencias d ON d.id=c.dependencia_id WHERE c.codigo=? COLLATE NOCASE",(code,)).fetchone()
                if old is not None and mode=='upsert':
                    old=dict(old)
                    base={key:old.get(key) for key in FIELDS}
                    for field,value in data.items():
                        if field not in FIELDS or field=='codigo':continue
                        if not _text(value):
                            if not overwrite_blanks or field in ('activo','embajador') or field in ('nombre','dependencia'):
                                continue
                        # La matriz inicial etiqueta 'Sin contacto' por defecto;
                        # no retroceder un seguimiento real por volver a cargarla.
                        if field=='relacionamiento' and _text(value)=='Sin contacto' and old.get('relacionamiento') not in ('','Sin contacto'):
                            continue
                        base[field]=_mapped_value(field,value)
                    # En CENS, sede equivale a dependencia: actualizar si la sede previa
                    # era un alias y no llegó una sede explícita diferente en el Excel.
                    if not _text(data.get('sede')) and old.get('sede','') in ('',old['dependencia']):
                        base['sede']=base['dependencia']
                    normalized=normalize(base)
                    newdep=normalized.pop('dependencia')
                    changes={f:(old.get(f),v) for f,v in normalized.items() if old.get(f)!=v}
                    changed_dep=newdep.casefold()!=old['dependencia'].casefold()
                    core_changed=bool(changes or changed_dep)
                    if core_changed:
                        depid=_department(con,newdep)
                        cols=list(normalized)
                        con.execute('UPDATE pmo_clientes SET '+','.join(f'{f}=?' for f in cols)+
                                    ',dependencia_id=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?',
                                    [*[normalized[f] for f in cols],depid,old['id']])
                    client_id=old['id']
                    action='Actualizado' if core_changed else 'Sin cambios'
                    desc=f'Código {code}; {len(changes)+(1 if changed_dep else 0)} campos actualizados'
                else:
                    action,desc=_insert(con,'Clientes',data,actor)
                    record=con.execute('SELECT id FROM pmo_clientes WHERE codigo=? COLLATE NOCASE',(code,)).fetchone()
                    client_id=record['id'] if record else None
                    old=None
                    core_changed=action=='Nuevo'
                custom_changed=False
                if action!='Duplicado' and client_id:
                    for field,source in mapping.items():
                        if not field.startswith('extra:') or not source:continue
                        extra=raw.get(source,'')
                        if not _text(extra) and not overwrite_blanks:continue
                        key=field[6:]
                        val=_check_extra(extra,metadata[key])
                        current=con.execute('SELECT valor FROM p1_client_custom_values WHERE cliente_id=? AND columna_id=?',
                                            (client_id,key)).fetchone()
                        if current is None and not val:continue
                        if current is None or current['valor']!=val:
                            con.execute('INSERT INTO p1_client_custom_values(cliente_id,columna_id,valor) VALUES(?,?,?) '
                                        'ON CONFLICT(cliente_id,columna_id) DO UPDATE SET valor=excluded.valor',
                                        (client_id,key,val))
                            custom_changed=True
                    if old is not None and (core_changed or custom_changed):
                        # Una sola anotación de cambio por cliente, sin cambiar su UUID.
                        after=con.execute('SELECT * FROM pmo_clientes WHERE id=?',(client_id,)).fetchone()
                        con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor) VALUES(?,?,?,?,?,?)',
                                    ('cliente',client_id,'actualizar_excel',json.dumps(old,ensure_ascii=False),
                                     json.dumps(dict(after),ensure_ascii=False),actor.strip()))
                        action='Actualizado'
                        desc=f'Código {code}; datos actualizados sin cambiar identificador'
                con.execute('RELEASE SAVEPOINT fila_cliente')
            except (ValidationError,sqlite3.IntegrityError,ValueError,OverflowError) as exc:
                con.execute('ROLLBACK TO SAVEPOINT fila_cliente')
                con.execute('RELEASE SAVEPOINT fila_cliente')
                action,desc='Error',str(exc)
            result.append({'Fila':rownum,'Código':_text(raw.get(mapping['codigo'],'')),
                           'Acción':action,'Detalle':desc})
        if confirm and not any(r['Acción']=='Error' for r in result):
            con.commit()
        else:
            con.rollback()
        return result
    except Exception:
        con.rollback();raise
    finally:
        con.close()


def delete_clients_quick(ids: list[str], actor: str = 'Operación desde la interfaz',
                         path: Path | None = None) -> dict[str,int]:
    """Un clic de confirmación: elimina clientes sin vínculos y archiva los vinculados.

    Todo ocurre en una sola transacción, con auditoría por cliente. Los registros
    de actividad nunca se pierden por una eliminación en lote.
    """
    ids=list(dict.fromkeys(ids))
    if not ids: raise ValidationError('Seleccione uno o más clientes.')
    totals={'eliminados':0,'archivados':0}
    with transaction(path) as con:
        tables=[r['name'] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        referencing=[]
        for table in tables:
            if table in ('pmo_auditoria','p1_client_custom_values'):continue
            for fk in con.execute(f'PRAGMA foreign_key_list("{table}")'):
                if fk['table']=='pmo_clientes' and fk['to']=='id':
                    referencing.append((table,fk['from']))
            # El Paso 09 tiene una referencia textual cliente_id sin FK formal.
            # No borrar su cliente aunque SQLite no lo restrinja.
            columns={r['name'] for r in con.execute(f'PRAGMA table_info("{table}")')}
            if 'cliente_id' in columns and (table,'cliente_id') not in referencing:
                referencing.append((table,'cliente_id'))
        for client_id in ids:
            old=con.execute('SELECT id,codigo,nombre,activo FROM pmo_clientes WHERE id=?',(client_id,)).fetchone()
            if old is None:raise ValidationError('Cliente seleccionado no encontrado. Actualice la tabla.')
            linked=any(con.execute(f'SELECT 1 FROM "{table}" WHERE "{fk_col}"=? LIMIT 1',
                                   (client_id,)).fetchone() for table,fk_col in referencing)
            if linked:
                con.execute('UPDATE pmo_clientes SET activo=0,actualizado_en=CURRENT_TIMESTAMP WHERE id=?',(client_id,))
                operation='archivar'
                totals['archivados']+=1
            else:
                con.execute('DELETE FROM p1_client_custom_values WHERE cliente_id=?',(client_id,))
                con.execute('DELETE FROM pmo_clientes WHERE id=?',(client_id,))
                operation='eliminar_definitivo'
                totals['eliminados']+=1
            _audit(con,'cliente',client_id,operation,actor,json.dumps(dict(old),ensure_ascii=False))
    return totals

def backup_clients_database(path: Path | None = None) -> Path:
    """Respaldo SQLite consistente, antes de una carga o eliminación confirmada.

    La copia es local, fuera de la carpeta del código, y no modifica la base.
    """
    from datetime import datetime
    source=Path(path) if path is not None else database_path()
    if not source.is_file():
        raise ValidationError('No se encontró la base para crear el respaldo previo.')
    backup_dir=source.parent/'respaldos_clientes'
    backup_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    target=backup_dir/f'clientes_antes_de_cambio_{stamp}_{uuid.uuid4().hex[:6]}.sqlite3'
    try:
        with sqlite3.connect(str(source)) as origin, sqlite3.connect(str(target)) as output:
            origin.backup(output)
            if output.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValidationError('La copia de seguridad no superó la verificación.')
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise

def export_clients_csv(rows: list[dict], visible: list[str], cols: list[dict] | None = None,
                       custom_data: dict | None = None) -> bytes:
    """Exporta las columnas visibles sin permitir que Excel ejecute fórmulas como celdas."""
    import csv
    import io
    names={**DISPLAY_COLUMNS, **{'extra:'+c['id']:c['nombre'] for c in (cols or [])}}
    visible=[k for k in visible if k in names]
    out=io.StringIO()
    w=csv.writer(out)
    w.writerow([names[k] for k in visible])
    custom_data=custom_data or {}
    for person in rows:
        values=[]
        for key in visible:
            if key=='activo':v='Activo' if person.get('activo') else 'Inactivo'
            elif key=='embajador':v='Sí' if person.get('embajador') else 'No'
            elif key.startswith('extra:'):v=custom_data.get(person['id'],{}).get(key[6:],'')
            else:v=person.get(key,'')
            v='' if v is None else str(v)
            if v.lstrip().startswith(('=','+','-','@')):v="'"+v
            values.append(v)
        w.writerow(values)
    return ('\ufeff'+out.getvalue()).encode('utf-8')
