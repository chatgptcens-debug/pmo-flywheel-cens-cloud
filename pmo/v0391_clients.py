"""V0.39.1 · Rol único, exportación integral y matriz de stakeholders.

Compatibilidad: `segmento` es el campo legado consumido por V5 y
`rol_especifico` el campo de la ficha. No se modifican corridas/pesos históricos.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path

from .storage import connect, transaction
from .clients import ValidationError

# Homologaciones nominales, no mezcla automática de funciones distintas.
ROLE_ALIASES = {
    'líder del proyecto': 'Líder Proyecto',
    'líder proyecto': 'Líder Proyecto',
    'miembro equipo de proyecto': 'Miembro Proyecto',
    'miembro de equipo de proyecto': 'Miembro Proyecto',
    'miembro proyecto': 'Miembro Proyecto',
    'área de apoyo': 'Dependencia de Apoyo',
}


def canonical_role(value: str | None) -> str:
    text = ' '.join(str(value or '').split())
    return ROLE_ALIASES.get(text.casefold(), text)


def client_role(client: dict) -> str:
    return canonical_role(client.get('rol_especifico') or client.get('segmento'))


def role_catalog(path: Path | None = None) -> dict[str, int]:
    with closing(connect(path)) as con:
        roles = [client_role(dict(row)) for row in con.execute(
            'SELECT segmento,rol_especifico FROM pmo_clientes WHERE activo=1')]
    return dict(sorted(Counter(x for x in roles if x).items(), key=lambda v: v[0].casefold()))


def harmonize_roles(path: Path | None = None) -> dict:
    """Migración ÚNICA y auditable; respaldo antes de modificar clientes.

    Si los dos campos históricos discrepan, se toma Rol específico como más
    preciso. La auditoría conserva ambos valores previos para revisión. La
    copia de respaldo queda en el directorio local de datos de la aplicación.
    """
    from .client_directory import backup_clients_database
    with closing(connect(path)) as con:
        if con.execute('SELECT 1 FROM schema_migrations WHERE version=391').fetchone():
            return {'changed': 0, 'already_done': True}
        original = [dict(r) for r in con.execute('SELECT id,codigo,segmento,rol_especifico FROM pmo_clientes')]
    changes = [(r, client_role(r)) for r in original if
               (canonical_role(r.get('segmento')) != client_role(r) or
                canonical_role(r.get('rol_especifico')) != client_role(r) or
                str(r.get('segmento') or '') != client_role(r) or
                str(r.get('rol_especifico') or '') != client_role(r))]
    # Respaldar también cuando no hay clientes; guarda la marca de migración.
    backup_clients_database(path)
    with transaction(path) as con:
        if con.execute('SELECT 1 FROM schema_migrations WHERE version=391').fetchone():
            return {'changed': 0, 'already_done': True}
        for row, role in changes:
            con.execute('UPDATE pmo_clientes SET segmento=?,rol_especifico=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?',
                        (role,role,row['id']))
            con.execute('''INSERT INTO pmo_auditoria(entidad,entidad_id,accion,antes_json,despues_json,actor)
                           VALUES (?,?,?,?,?,?)''',
                        ('cliente',row['id'],'homologacion_rol_v0391',
                         json.dumps({'segmento':row['segmento'],'rol_especifico':row['rol_especifico']},ensure_ascii=False),
                         json.dumps({'rol':role,'regla':'Rol específico tiene prioridad; si falta, Grupo/Segmento'},ensure_ascii=False),
                         'Migración controlada PMO V0.39.1'))
        con.execute('INSERT INTO schema_migrations(version) VALUES (391)')
    return {'changed':len(changes),'already_done':False}


QUADRANTS = (
    ('Latentes', 'Informar', 'Alta', 'Bajo'),
    ('Promotores', 'Involucrar', 'Alta', 'Alto'),
    ('Apáticos', 'Monitorizar', 'Baja', 'Bajo'),
    ('Defensores', 'Reportar', 'Baja', 'Alto'),
)


def stakeholder_matrix(clients: list[dict]) -> dict:
    """Matriz sin asumir que 'Media' equivale a poder/interés alto o bajo."""
    groups = {name: [] for name,_,_,_ in QUADRANTS}
    groups['Pendientes de clasificación'] = []
    lookup = {(power,interest):name for name,_,power,interest in QUADRANTS}
    for c in clients:
        group = lookup.get((c.get('influencia'),c.get('interes')),'Pendientes de clasificación')
        groups[group].append(c)
    return groups


def export_full_directory_xlsx(clients: list[dict], path: Path | None = None) -> bytes:
    """Todas las fichas (independientemente de columnas visibles) y relaciones por ID."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter
    from .client_directory import custom_columns, custom_values_for_clients
    from .awareness import client_history
    from .clients import audit_history

    cols=custom_columns(path)
    customs=custom_values_for_clients([c['id'] for c in clients],path)
    fields=[('codigo','Código corporativo'),('nombre','Cliente'),('dependencia','Dependencia'),
            ('equipo_trabajo','Equipo de trabajo'),('cargo','Cargo actual'),
            ('rol','Rol'),('estado_gestion','Estado de gestión'),
            ('influencia','Influencia'),('interes','Interés'),('conocimiento','Conocimiento PMO'),
            ('canal','Canal preferido'),('correo','Correo'),('activo','Cliente activo'),
            ('necesidades_preliminares','Necesidades preliminares'),
            ('relacionamiento','Relacionamiento'),('participa_proyectos','Participa en proyectos'),
            ('retos','Retos'),('beneficios_esperados','Beneficios esperados'),
            ('barreras','Barreras'),('responsable','Responsable PMO'),('primer_contacto','Primer contacto'),
            ('embajador','Embajador PMO'),('observaciones','Observaciones'),
            ('creado_en','Creado en'),('actualizado_en','Actualizado en'),
            ('eventos','Eventos asistidos'),('consultas','Consultas'),('encuestas','Encuestas'),
            ('cambios','Cambios registrados')]
    fields.extend(('extra:'+v['id'],v['nombre']) for v in cols)
    wb=Workbook()
    sheet=wb.active;sheet.title='Directorio completo'
    sheet.append([v for _,v in fields])
    audits=wb.create_sheet('Historial de cambios')
    audits.append(['Código corporativo','Cliente','Acción','Responsable','Fecha'])
    needs=wb.create_sheet('Necesidades preliminares')
    needs.append(['Código corporativo','Cliente','Necesidades preliminares'])
    events=wb.create_sheet('Eventos')
    events.append(['Código corporativo','Cliente','Evento','Tipo','Fecha','Asistió'])
    tickets=wb.create_sheet('Consultas')
    tickets.append(['Código corporativo','Cliente','Asunto','Categoría','Descripción','Estado','Creado en','Respondido en'])
    surveys=wb.create_sheet('Encuestas')
    surveys.append(['Código corporativo','Cliente','Fase','Familiaridad','Propósito','Servicios','Utilidad','Interés','Responsable','Creado en'])
    with closing(connect(path)) as con:
        attendance={}
        for r in con.execute('''SELECT a.cliente_id,e.titulo,e.tipo,e.fecha,a.asistio FROM p1_asistencias a
                                JOIN p1_eventos e ON e.id=a.evento_id'''):
            attendance.setdefault(r['cliente_id'],[]).append(dict(r))
        enquiries={}
        for r in con.execute('SELECT * FROM p1_consultas'):
            enquiries.setdefault(r['cliente_id'],[]).append(dict(r))
        responses={}
        for r in con.execute('SELECT * FROM p1_encuestas'):
            responses.setdefault(r['cliente_id'],[]).append(dict(r))
    for c in clients:
        history=client_history(c['id'],path)
        changes=audit_history(c['id'],path)
        item={**c,'rol':client_role(c),'eventos':history['events'],
              'consultas':history['tickets'],'encuestas':history['surveys'],
              'cambios':len(changes)}
        item['activo']='Sí' if c.get('activo') else 'No'
        item['embajador']='Sí' if c.get('embajador') else 'No'
        def excel_safe(value):
            if value is None:return ''
            if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
                return "'"+value
            return value
        sheet.append([excel_safe(customs.get(c['id'],{}).get(field[6:],'')) if field.startswith('extra:')
                      else excel_safe(item.get(field,'')) for field,_ in fields])
        if c.get('necesidades_preliminares'):
            needs.append([excel_safe(c['codigo']),excel_safe(c['nombre']),excel_safe(c['necesidades_preliminares'])])
        for a in changes:
            audits.append([excel_safe(c['codigo']),excel_safe(c['nombre']),a['accion'],excel_safe(a['actor']),a['fecha']])
        for event in attendance.get(c['id'],[]):
            events.append([excel_safe(c['codigo']),excel_safe(c['nombre']),excel_safe(event['titulo']),
                           excel_safe(event['tipo']),event['fecha'],'Sí' if event['asistio'] else 'No'])
        for query in enquiries.get(c['id'],[]):
            tickets.append([excel_safe(c['codigo']),excel_safe(c['nombre']),excel_safe(query['asunto']),
                            excel_safe(query['categoria']),excel_safe(query['descripcion']),excel_safe(query['estado']),
                            query['creado_en'],query['respondido_en']])
        for survey in responses.get(c['id'],[]):
            surveys.append([excel_safe(c['codigo']),excel_safe(c['nombre']),excel_safe(survey['fase']),
                            survey['familiaridad'],survey['proposito'],survey['servicios'],survey['utilidad'],
                            survey['interes'],excel_safe(survey['responsable']),survey['creado_en']])
    for ws in wb:
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.fill=PatternFill('solid',fgColor='10374B');cell.font=Font(color='FFFFFF',bold=True)
            cell.alignment=Alignment(wrap_text=True)
        for n,column in enumerate(ws.columns,1):
            widths=[len(str(x.value or '')) for x in list(column)[:100]]
            ws.column_dimensions[get_column_letter(n)].width=min(55,max(16,max(widths,default=16)+2))
    output=BytesIO();wb.save(output);return output.getvalue()
