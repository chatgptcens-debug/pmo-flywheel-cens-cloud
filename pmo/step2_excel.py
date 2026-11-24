"""Importación segura de prioridades y matriz Excel / CSV para el Paso 2.
Usa el directorio de clientes existente; nunca inventa clientes ni modifica el Paso 1.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from typing import Any
from .clients import ValidationError
from .storage import connect,transaction
from .step2 import _validate_priorities,audit,compute,default_matrix,validate_matrix,OUTCOMES,SERVICES
from .clients import list_clients

PRIORITY_COLUMNS=['Prioridad 1','Prioridad 2','Prioridad 3','Prioridad 4','Prioridad 5']


def _key(v:Any)->str:
    s=''.join(c for c in unicodedata.normalize('NFD',str(v or '').strip().lower()) if unicodedata.category(c)!='Mn')
    return ''.join(c for c in s if c.isalnum())


def _normalize_row(raw:dict[str,Any]):
    obj={_key(k):v for k,v in raw.items()}
    def val(*aliases):
        for s in aliases:
            if _key(s) in obj:return obj[_key(s)]
        return None
    client=val('Codigo Cliente','Código Cliente','Cliente','Customer Name','Nombre del cliente','Nombre')
    group=val('Grupo','Grupo clientes','Customer Group','Segmento','Grupo / Segmento')
    results=[val(f'Prioridad {i}',f'Priority {i}', f'{name} Outcome Priority') for i,name in enumerate(['First','Second','Third','Fourth','Fifth'],1)]
    return client,group,results


def _load_records(source:bytes,name:str)->list[dict[str,Any]]:
    if len(source)>12_000_000:raise ValidationError('El archivo supera 12 MB; divida la carga en lotes.')
    if name.lower().endswith('.csv'):
        try: content=source.decode('utf-8-sig')
        except UnicodeDecodeError as ex:raise ValidationError('El CSV debe estar codificado en UTF-8.') from ex
        sample=content[:1000]
        delim=';' if sample.count(';')>sample.count(',') else ','
        records=list(csv.DictReader(io.StringIO(content),delimiter=delim))
    elif name.lower().endswith('.xlsx'):
        try:
            from openpyxl import load_workbook
            wb=load_workbook(io.BytesIO(source),read_only=True,data_only=True)
        except Exception as ex:raise ValidationError('No se pudo abrir el archivo Excel.') from ex
        sheet=next((wb[n] for n in ('Expectativas','Customer Data','Prioridades') if n in wb.sheetnames),None)
        if sheet is None: sheet=wb.active
        it=sheet.iter_rows(values_only=True)
        header=next(it,None)
        if not header:raise ValidationError('La hoja Excel no tiene encabezados.')
        records=[dict(zip([str(x or '') for x in header],r)) for r in it if any(v is not None and str(v).strip() for v in r)]
        wb.close()
    else:raise ValidationError('Adjunte un archivo XLSX o CSV.')
    if not records:raise ValidationError('No se encontraron filas de clientes.')
    if len(records)>5000:raise ValidationError('Máximo 5.000 clientes por carga.')
    return records


def validate_import(source:bytes,name:str,diag:str,path:Path|None=None):
    raw=_load_records(source,name)
    clients=list_clients(path=path)
    by_code={c['codigo'].casefold():c for c in clients}
    names={}
    for c in clients:names.setdefault(c['nombre'].casefold().strip(),[]).append(c)
    from .step2 import expectations
    existing={}
    for x in expectations(diag,path=path):existing.setdefault(x['cliente_id'],[]).append(x['resultado_id'])
    seen=set();out=[]
    for number,row in enumerate(raw,2):
        client,group,results=_normalize_row(row)
        view={'Fila':number,'Cliente':str(client or '').strip(),'Grupo':str(group or '').strip(),
              'Acción':'Error','Motivo':'','ID cliente':None,'Prioridades':None}
        try:
            ident=str(client or '').strip()
            if not ident:raise ValidationError('Falta código o nombre del cliente.')
            c=by_code.get(ident.casefold())
            if not c:
                matches=names.get(ident.casefold(),[])
                if len(matches)!=1:raise ValidationError('Cliente no encontrado o nombre ambiguo. Use código de Paso 1.')
                c=matches[0]
            if not c['activo']:raise ValidationError('El cliente está inactivo en el Paso 1.')
            group_real=(c['segmento'] or '').strip()
            if not group_real:raise ValidationError('Cliente sin segmento. Complete el perfil en Paso 1.')
            if group and str(group).strip().casefold()!=group_real.casefold():
                raise ValidationError(f'El grupo no coincide con Paso 1 ({group_real}).')
            if c['id'] in seen:raise ValidationError('El mismo cliente aparece más de una vez en el archivo.')
            seen.add(c['id'])
            priority=[]
            for value in results:
                if value is None or str(value).strip()=='':raise ValidationError('Se necesitan las cinco prioridades.')
                try:
                    n=float(value)
                    if not n.is_integer():raise ValueError()
                    priority.append(int(n))
                except (TypeError,ValueError) as ex:raise ValidationError('Las prioridades deben ser códigos enteros 1–30.') from ex
            _validate_priorities(priority,False)
            view.update({'ID cliente':c['id'],'Grupo':group_real,'Prioridades':priority,
                         'Acción':'Sin cambios' if existing.get(c['id'])==priority else ('Actualizar' if c['id'] in existing else 'Nuevo')})
        except ValidationError as ex:view['Motivo']=str(ex)
        out.append(view)
    return out


def import_priorities(source:bytes,name:str,diag:str,actor:str,confirm:bool=False,path:Path|None=None):
    actor=actor.strip()
    if not actor:raise ValidationError('Indique el responsable de la carga.')
    preview=validate_import(source,name,diag,path)
    if not confirm:return preview
    if any(x['Acción']=='Error' for x in preview):raise ValidationError('Existen errores; no se importó ningún registro.')
    if not any(x['Acción'] in ('Nuevo','Actualizar') for x in preview):return preview
    from .step2 import expectations
    # revalidar bajo transacción y detectar cambios concurrentes en prioridades
    previous={}
    for x in expectations(diag,path=path):previous.setdefault(x['cliente_id'],[]).append(x['resultado_id'])
    with transaction(path) as con:
        if not con.execute('SELECT id FROM p2_diagnosticos WHERE id=?',(diag,)).fetchone():raise ValidationError('Diagnóstico inexistente.')
        for r in preview:
            if r['Acción'] not in ('Nuevo','Actualizar'):continue
            current=[x['resultado_id'] for x in con.execute('SELECT resultado_id FROM p2_expectativas WHERE diagnostico_id=? AND cliente_id=? ORDER BY posicion',(diag,r['ID cliente']))]
            if current!=previous.get(r['ID cliente'],[]):raise ValidationError('Los registros cambiaron mientras se procesaba el Excel. Repita la validación.')
            con.execute('DELETE FROM p2_expectativas WHERE diagnostico_id=? AND cliente_id=?',(diag,r['ID cliente']))
            for p,outcome in enumerate(r['Prioridades'],1):
                con.execute('INSERT INTO p2_expectativas(diagnostico_id,cliente_id,posicion,resultado_id,actor) VALUES (?,?,?,?,?)',
                            (diag,r['ID cliente'],p,outcome,actor))
            audit(con,'p2_expectativas',r['ID cliente'],'importar_excel',actor,{'diagnostico':diag,'prioridades':r['Prioridades']})
        con.execute('INSERT INTO p2_cargas_excel(id,diagnostico_id,sha256,filas,actor) VALUES (?,?,?,?,?)',
                    (uuid.uuid4().hex,diag,hashlib.sha256(source).hexdigest(),len(preview),actor))
    return preview


def import_matrix(source:bytes,name:str):
    if len(source)>6_000_000:raise ValidationError('La matriz supera el límite de 6 MB.')
    if name.lower().endswith('.csv'):
        try: csv_text=source.decode('utf-8-sig')
        except UnicodeDecodeError as ex:raise ValidationError('CSV no está en UTF-8.') from ex
        sample=csv_text[:1000]; sep=';' if sample.count(';')>sample.count(',') else ','
        r=list(csv.DictReader(io.StringIO(csv_text),delimiter=sep))
    elif name.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        try:wb=load_workbook(io.BytesIO(source),read_only=True,data_only=True)
        except Exception as ex:raise ValidationError('Excel de matriz ilegible.') from ex
        ws=wb['Matriz'] if 'Matriz' in wb.sheetnames else wb.active
        it=ws.iter_rows(values_only=True);head=next(it,None)
        if not head:raise ValidationError('Matriz sin encabezados.')
        r=[dict(zip([str(x or '') for x in head],values)) for values in it if any(x is not None for x in values)]
        wb.close()
    else:raise ValidationError('La matriz debe ser XLSX o CSV.')
    if len(r)>780:raise ValidationError('La matriz no puede superar 780 pares resultado–servicio.')
    result={};seen=set()
    for num,row in enumerate(r,2):
        obj={_key(k):v for k,v in row.items()}
        keys=[obj.get('outcomeid',obj.get('resultadoid')),obj.get('serviceid',obj.get('servicioid')),obj.get('strength',obj.get('intensidad'))]
        try:
            a,b,c=[int(float(v)) for v in keys]
            if float(keys[2])!=c or float(keys[0])!=a or float(keys[1])!=b:raise ValueError()
        except (TypeError,ValueError) as ex:raise ValidationError(f'Fila {num}: códigos e intensidad deben ser enteros.') from ex
        if (a,b) in seen:raise ValidationError(f'Fila {num}: relación repetida.')
        seen.add((a,b));result.setdefault(a,{})[b]=c
    return validate_matrix(result)


def template_bytes(clients:list[dict]|None=None)->bytes:
    """Plantilla con clientes referenciados, pero sin asignarles prioridades ficticias."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill,Font,Alignment
    wb=Workbook();ws=wb.active;ws.title='Expectativas'
    ws.append(['Código cliente','Grupo clientes',*PRIORITY_COLUMNS])
    for c in (clients or []):ws.append([c['codigo'],c['segmento'] or '',None,None,None,None,None])
    ws2=wb.create_sheet('30 resultados');ws2.append(['Outcome ID','Resultado esperado (resumen CENS)'])
    for k,v in OUTCOMES.items():ws2.append([k,v])
    ws3=wb.create_sheet('26 servicios');ws3.append(['Service ID','Servicio (referencia)'])
    for k,v in SERVICES.items():ws3.append([k,v])
    ws4=wb.create_sheet('Matriz');ws4.append(['Outcome ID','Service ID','Strength'])
    for o,services in default_matrix().items():
        for s,value in services.items():ws4.append([o,s,value])
    ws5=wb.create_sheet('INSTRUCCIONES')
    for row in [
        ['PMO CENS · Paso 2 · Carga de expectativas'],
        ['No altere los nombres de columnas ni los códigos de cliente.'],
        ['Cinco prioridades DISTINTAS, identificadas con números del 1 al 30.'],
        ['El cliente y segmento deben existir previamente en Paso 1.'],
        ['Cargar y confirmar reemplazará las prioridades del mismo cliente en el diagnóstico seleccionado.'],
        ['La matriz es una correspondencia ilustrativa de origen HTML, no puntuación propietaria PMOGA.'],
        ['Para cargar la matriz, use únicamente la hoja Matriz y un archivo XLSX separado.']
    ]:ws5.append(row)
    for sheet in wb.worksheets:
        sheet.freeze_panes='A2';sheet.sheet_view.showGridLines=False
        for cell in sheet[1]:cell.fill=PatternFill('solid',fgColor='10374B');cell.font=Font(color='FFFFFF',bold=True);cell.alignment=Alignment(wrap_text=True)
        from openpyxl.utils import get_column_letter
        for col in range(1,sheet.max_column+1):sheet.column_dimensions[get_column_letter(col)].width=42 if col==2 else 23
        sheet.auto_filter.ref=f'A1:{get_column_letter(sheet.max_column)}{sheet.max_row}'
    buff=io.BytesIO();wb.save(buff);return buff.getvalue()
