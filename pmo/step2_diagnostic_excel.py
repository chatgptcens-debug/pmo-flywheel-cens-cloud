"""Carga integral opcional del Paso 2 (V0.6), con previsualización y transacción.

Formato propio CENS, NO un instrumento oficial PMI ni una aprobación.
Nunca crea/modifica clientes del Paso 1 ni valida necesidades automáticamente.
"""
from __future__ import annotations
import hashlib
import io
import json
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any
from .clients import ValidationError, list_clients
from .storage import connect, transaction
from . import step2 as p2

SHEETS = {
 'Diagnostico': ['Codigo diagnostico','Nombre diagnostico','Ciclo','Responsable','Objetivo','Alcance','Poblacion objetivo','Estado'],
 'Madurez': ['Dimension','Nivel actual','Nivel deseado','Fuente','Responsable'],
 'Levantamientos': ['Codigo levantamiento','Codigo cliente','Metodo','Fecha','Estado','Observaciones','Fuente'],
 'Expectativas': ['Codigo cliente','Grupo clientes','Prioridad 1','Prioridad 2','Prioridad 3','Prioridad 4','Prioridad 5','Notas'],
 'Necesidades': ['Codigo necesidad','Codigo cliente','Dependencia','Problema','Ganancia','Resultado ID','Impacto','Fuente','Estado'],
 'Evidencias': ['Codigo evidencia','Codigo necesidad','Codigo levantamiento','Titulo','Tipo','Fecha','Enlace','Responsable'],
 'Pesos': ['Grupo','Peso %'],
}
DATA_SHEETS = [x for x in SHEETS if x != 'Diagnostico']
STATUS_DIAG = {'En diseño','Programado','En levantamiento','En análisis'}
STATUS_INTERVIEW = {'Programada','En curso','Completada','Cancelada'}
STATUS_NEED = {'Registrada','En validación'}
METH = {'Entrevista','Encuesta','Grupo focal','Revisión documental'}
IMPACTS = {'Sin evaluar','Bajo','Medio','Alto'}
MAX_BYTES = 10_000_000
MAX_ROWS = 5000


def s(v:Any)->str:
    return '' if v is None else str(v).strip()


def date_str(v:Any)->str:
    if isinstance(v,(date,datetime)):
        return v.date().isoformat() if isinstance(v,datetime) else v.isoformat()
    try:return date.fromisoformat(s(v)).isoformat()
    except (TypeError,ValueError) as ex:raise ValidationError('Fecha inválida. Use AAAA-MM-DD.') from ex


def integer(v:Any,name:str,lo:int,hi:int)->int:
    try:
        n=float(v)
        if not n.is_integer() or not lo<=n<=hi:raise ValueError()
        return int(n)
    except (ValueError,TypeError,OverflowError) as ex:
        raise ValidationError(f'{name}: ingrese un entero entre {lo} y {hi}.') from ex


def number(v:Any,name:str)->float:
    try:
        n=float(v)
        if not 0<=n<=100 or n!=n:raise ValueError()
        return n
    except (ValueError,TypeError,OverflowError) as ex:
        raise ValidationError(f'{name}: indique un porcentaje entre 0 y 100.') from ex


def required(v:Any,field:str)->str:
    x=s(v)
    if not x:raise ValidationError(f'Falta {field}.')
    if len(x)>1600:raise ValidationError(f'{field}: texto demasiado largo.')
    return x


def parse_xlsx(source:bytes,name:str)->dict[str,list[dict]]:
    if not name.lower().endswith('.xlsx'):raise ValidationError('Seleccione un archivo .xlsx válido.')
    if not source or len(source)>MAX_BYTES:raise ValidationError('Archivo vacío o superior a 10 MB.')
    try:
        from openpyxl import load_workbook
        book=load_workbook(io.BytesIO(source),read_only=True,data_only=True)
    except Exception as ex:raise ValidationError('No se puede leer el archivo XLSX.') from ex
    try:
        raw={}
        for tab,cols in SHEETS.items():
            if tab not in book.sheetnames:
                raw[tab]=[];continue
            ws=book[tab]
            if ws.max_row is not None and ws.max_row>MAX_ROWS+1:raise ValidationError(f'{tab}: máximo {MAX_ROWS} registros.')
            it=ws.iter_rows(values_only=True)
            header=next(it,())
            got=[s(x) for x in header] if header else []
            if got[:len(cols)]!=cols:
                raise ValidationError(f'{tab}: encabezados incorrectos. Utilice la plantilla sin cambiar las columnas.')
            rows=[]
            for rownum,values in enumerate(it,2):
                if rownum>MAX_ROWS+1:raise ValidationError(f'{tab}: máximo {MAX_ROWS} registros.')
                values=values[:len(cols)]
                if not any(x is not None and s(x) for x in values):continue
                rows.append({'_fila':rownum,**dict(zip(cols,values))})
            raw[tab]=rows
        if not any(raw.values()):raise ValidationError('No hay datos para importar.')
        return raw
    finally:book.close()


def _external_map(con,diag:str,kind:str)->dict[str,str]:
    return {r['codigo_externo'].casefold():r['registro_id'] for r in con.execute(
        'SELECT codigo_externo,registro_id FROM p2_excel_registros WHERE diagnostico_id=? AND seccion=?',(diag,kind))}


def preview(source:bytes,name:str,diagnostic_id:str|None=None,path:Path|None=None)->dict:
    """Prevalida 7 hojas y dependencias. No escribe nada en SQLite."""
    raw=parse_xlsx(source,name)
    errors=[]; norm={x:[] for x in SHEETS};seen={x:set() for x in SHEETS}
    clients=list_clients(path=path)
    by_code={c['codigo'].casefold():c for c in clients}
    with connect(path) as con:
        target=dict(con.execute('SELECT * FROM p2_diagnosticos WHERE id=?',(diagnostic_id,)).fetchone()) if diagnostic_id and con.execute('SELECT 1 FROM p2_diagnosticos WHERE id=?',(diagnostic_id,)).fetchone() else None
        existing_keys={kind:_external_map(con,diagnostic_id,kind) for kind in ('Levantamientos','Necesidades','Evidencias')} if target else {k:{} for k in ('Levantamientos','Necesidades','Evidencias')}
        existing_expects={r['cliente_id']:[] for r in con.execute('SELECT DISTINCT cliente_id FROM p2_expectativas WHERE diagnostico_id=?',(diagnostic_id,))} if target else {}
        if target:
            for r in con.execute('SELECT cliente_id,resultado_id FROM p2_expectativas WHERE diagnostico_id=? ORDER BY posicion',(diagnostic_id,)):
                existing_expects[r['cliente_id']].append(r['resultado_id'])
            existing_maturity={r['dimension']:(r['actual'],r['deseado'],r['fuente'],r['responsable']) for r in con.execute('SELECT * FROM p2_madurez WHERE diagnostico_id=?',(diagnostic_id,))}
            existing_weights={r['grupo']:r['peso'] for r in con.execute('SELECT * FROM p2_pesos WHERE diagnostico_id=?',(diagnostic_id,))}
        else:existing_maturity={};existing_weights={}
    if diagnostic_id and not target:raise ValidationError('El diagnóstico existente no fue encontrado.')
    if target and target['estado']=='Cerrado':raise ValidationError('El diagnóstico está cerrado; no admite carga masiva.')

    def fail(tab,r,ex):errors.append(f'{tab}, fila {r.get("_fila", "?")}: {ex}')
    def uniq(tab,value):
        key=value.casefold()
        if key in seen[tab]:raise ValidationError(f'Código o clave repetida: {value}.')
        seen[tab].add(key)

    for r in raw['Diagnostico']:
        try:
            if len(raw['Diagnostico'])!=1:raise ValidationError('Debe existir una única fila de diagnóstico.')
            code=required(r['Codigo diagnostico'],'código de diagnóstico');uniq('Diagnostico',code)
            entry={'codigo':code,'nombre':required(r['Nombre diagnostico'],'nombre de diagnóstico'),
                   'ciclo':required(r['Ciclo'],'ciclo'), 'responsable':required(r['Responsable'],'responsable'),
                   'objetivo':s(r['Objetivo']),'alcance':s(r['Alcance']),
                   'poblacion':None if s(r['Poblacion objetivo'])=='' else integer(r['Poblacion objetivo'],'población',0,10000000),
                   'estado':s(r['Estado']) or 'En diseño'}
            if entry['estado'] not in STATUS_DIAG:raise ValidationError('Estado del diagnóstico inválido o cerrado.')
            norm['Diagnostico'].append(entry)
        except ValidationError as ex:fail('Diagnostico',r,ex)
    if not target and not raw['Diagnostico']:
        errors.append('Diagnostico: incluya una fila para crear el diagnóstico inicial.')
    if not target and norm['Diagnostico']:
        with connect(path) as con:
            linked=con.execute('SELECT diagnostico_id FROM p2_excel_diagnosticos WHERE codigo_externo=?',
                               (norm['Diagnostico'][0]['codigo'],)).fetchone()
            if linked:
                errors.append('Diagnostico: el código ya fue importado. Elija Completar un diagnóstico existente para no duplicarlo.')

    for r in raw['Madurez']:
        try:
            dim=required(r['Dimension'],'dimensión');uniq('Madurez',dim)
            if dim not in p2.MATURITY:raise ValidationError(f'Dimensión no reconocida: {dim}.')
            entry={'dimension':dim,'actual':integer(r['Nivel actual'],'nivel actual',1,5),
                   'deseado':integer(r['Nivel deseado'],'nivel deseado',1,5),
                   'fuente':required(r['Fuente'],'fuente'),'responsable':required(r['Responsable'],'responsable')}
            entry['accion']='Sin cambios' if existing_maturity.get(dim)==(entry['actual'],entry['deseado'],entry['fuente'],entry['responsable']) else ('Actualizar' if dim in existing_maturity else 'Nuevo')
            norm['Madurez'].append(entry)
        except ValidationError as ex:fail('Madurez',r,ex)

    for r in raw['Levantamientos']:
        try:
            code=required(r['Codigo levantamiento'],'código de levantamiento');uniq('Levantamientos',code)
            c=by_code.get(required(r['Codigo cliente'],'código de cliente').casefold())
            if not c or not c['activo']:raise ValidationError('Cliente inexistente o inactivo en Paso 1.')
            method=required(r['Metodo'],'método');status=required(r['Estado'],'estado')
            if method not in METH or status not in STATUS_INTERVIEW:raise ValidationError('Método o estado no permitido.')
            entry={'codigo':code,'cliente_id':c['id'],'cliente':c['codigo'],'metodo':method,'fecha':date_str(r['Fecha']),
                   'estado':status,'observaciones':s(r['Observaciones']),'fuente':s(r['Fuente'])}
            previous_id=existing_keys['Levantamientos'].get(code.casefold())
            if previous_id:
                with connect(path) as con:
                    old=con.execute('SELECT * FROM p2_levantamientos WHERE id=?',(previous_id,)).fetchone()
                if not old:raise ValidationError('Referencia Excel sin levantamiento correspondiente en la base.')
                entry['accion']='Sin cambios' if all(old[k]==entry[v] for k,v in [('cliente_id','cliente_id'),('metodo','metodo'),('fecha','fecha'),('estado','estado'),('observaciones','observaciones'),('fuente','fuente')]) else 'Actualizar'
            else:entry['accion']='Nuevo'
            norm['Levantamientos'].append(entry)
        except ValidationError as ex:fail('Levantamientos',r,ex)

    for r in raw['Expectativas']:
        try:
            code=required(r['Codigo cliente'],'código de cliente');uniq('Expectativas',code)
            c=by_code.get(code.casefold())
            if not c or not c['activo']:raise ValidationError('Cliente inexistente o inactivo en Paso 1.')
            group=required(r['Grupo clientes'],'grupo de clientes')
            if group.casefold()!=s(c['segmento']).casefold():raise ValidationError(f'El grupo no coincide con Paso 1: {c["segmento"] or "sin segmento"}.')
            positions=[integer(r[f'Prioridad {i}'],f'prioridad {i}',1,30) for i in range(1,6)]
            p2._validate_priorities(positions,False)
            entry={'cliente_id':c['id'],'cliente':c['codigo'],'grupo':c['segmento'],'prioridades':positions,'notas':s(r['Notas'])}
            entry['accion']='Sin cambios' if existing_expects.get(c['id'])==positions else ('Actualizar' if c['id'] in existing_expects else 'Nuevo')
            norm['Expectativas'].append(entry)
        except ValidationError as ex:fail('Expectativas',r,ex)

    for r in raw['Necesidades']:
        try:
            code=required(r['Codigo necesidad'],'código de necesidad');uniq('Necesidades',code)
            c=by_code.get(required(r['Codigo cliente'],'código de cliente').casefold())
            if not c or not c['activo']:raise ValidationError('Cliente inexistente o inactivo en Paso 1.')
            if s(r['Dependencia']) and s(r['Dependencia']).casefold()!=c['dependencia'].casefold():raise ValidationError('Dependencia distinta de la registrada en Paso 1.')
            problem=required(r['Problema'],'problema');gain=required(r['Ganancia'],'ganancia')
            outcome=None if not s(r['Resultado ID']) else integer(r['Resultado ID'],'resultado ID',1,30)
            impact=s(r['Impacto']) or 'Sin evaluar';status=s(r['Estado']) or 'Registrada'
            if impact not in IMPACTS:raise ValidationError('Impacto no permitido.')
            if status not in STATUS_NEED:raise ValidationError('No se valida ni descarta una necesidad desde Excel; registre la decisión manualmente.')
            entry={'codigo':code,'cliente_id':c['id'],'cliente':c['codigo'],'dependencia':c['dependencia'],
                   'problema':problem,'ganancia':gain,'resultado_id':outcome,'impacto':impact,
                   'fuente':s(r['Fuente']),'estado':status}
            previous_id=existing_keys['Necesidades'].get(code.casefold())
            if previous_id:
                with connect(path) as con:
                    old=con.execute('SELECT * FROM p2_necesidades WHERE id=?',(previous_id,)).fetchone()
                if not old:raise ValidationError('Referencia Excel sin necesidad correspondiente en la base.')
                unchanged=all(old[k]==entry[k] for k in ('cliente_id','dependencia','problema','ganancia','resultado_id','impacto','fuente','estado'))
                if not unchanged and old['estado'] in ('Validada','Descartada'):
                    raise ValidationError('La necesidad ya fue validada/descartada: no puede modificarse por Excel.')
                entry['accion']='Sin cambios' if unchanged else 'Actualizar'
            else:entry['accion']='Nuevo'
            norm['Necesidades'].append(entry)
        except ValidationError as ex:fail('Necesidades',r,ex)

    new_levs={x['codigo'].casefold() for x in norm['Levantamientos']}
    new_needs={x['codigo'].casefold() for x in norm['Necesidades']}
    for r in raw['Evidencias']:
        try:
            code=required(r['Codigo evidencia'],'código de evidencia');uniq('Evidencias',code)
            ncode=s(r['Codigo necesidad']);lcode=s(r['Codigo levantamiento'])
            if ncode and ncode.casefold() not in new_needs and ncode.casefold() not in existing_keys['Necesidades']:
                raise ValidationError(f'La necesidad {ncode} no existe en el diagnóstico o archivo.')
            if lcode and lcode.casefold() not in new_levs and lcode.casefold() not in existing_keys['Levantamientos']:
                raise ValidationError(f'El levantamiento {lcode} no existe en el diagnóstico o archivo.')
            url=s(r['Enlace'])
            if url:
                pr=urlparse(url)
                if pr.scheme not in ('https','http') or not pr.netloc:raise ValidationError('El enlace debe usar https:// o http://.')
            entry={'codigo':code,'necesidad_codigo':ncode,'levantamiento_codigo':lcode,
                   'titulo':required(r['Titulo'],'título de evidencia'),'tipo':required(r['Tipo'],'tipo'),
                   'fecha':date_str(r['Fecha']),'url':url,'responsable':required(r['Responsable'],'responsable')}
            previous_id=existing_keys['Evidencias'].get(code.casefold())
            if previous_id:
                with connect(path) as con:
                    old=con.execute('SELECT * FROM p2_evidencias WHERE id=?',(previous_id,)).fetchone()
                    old_n=con.execute("SELECT codigo_externo FROM p2_excel_registros WHERE diagnostico_id=? AND seccion='Necesidades' AND registro_id=?",(diagnostic_id,old['necesidad_id'])).fetchone() if old else None
                    old_l=con.execute("SELECT codigo_externo FROM p2_excel_registros WHERE diagnostico_id=? AND seccion='Levantamientos' AND registro_id=?",(diagnostic_id,old['levantamiento_id'])).fetchone() if old else None
                if not old:raise ValidationError('Referencia Excel sin evidencia correspondiente en la base.')
                same=(all(old[k]==entry[k] for k in ('titulo','tipo','fecha','url','responsable')) and
                      s(old_n['codigo_externo'] if old_n else '').casefold()==ncode.casefold() and
                      s(old_l['codigo_externo'] if old_l else '').casefold()==lcode.casefold())
                entry['accion']='Sin cambios' if same else 'Actualizar'
            else:entry['accion']='Nuevo'
            norm['Evidencias'].append(entry)
        except ValidationError as ex:fail('Evidencias',r,ex)

    for r in raw['Pesos']:
        try:
            group=required(r['Grupo'],'grupo');uniq('Pesos',group)
            entry={'grupo':group,'peso':number(r['Peso %'],'peso %')}
            entry['accion']='Sin cambios' if existing_weights.get(group)==entry['peso'] else ('Actualizar' if group in existing_weights else 'Nuevo')
            norm['Pesos'].append(entry)
        except ValidationError as ex:fail('Pesos',r,ex)
    if norm['Pesos']:
        if abs(sum(x['peso'] for x in norm['Pesos'])-100)>1e-6:
            errors.append('Pesos: la suma debe ser exactamente 100 %.')
        existing_groups={s(c['segmento']) for c in clients if c['activo']}
        groups_in_new={x['grupo'] for x in norm['Expectativas']}
        valid_existing=set()
        if target:
            with connect(path) as con:
                valid_existing={x['segmento'] for x in con.execute('''SELECT c.segmento FROM p2_expectativas e JOIN pmo_clientes c ON c.id=e.cliente_id
                  WHERE e.diagnostico_id=? GROUP BY e.cliente_id HAVING COUNT(*)=5''',(diagnostic_id,))}
        for x in norm['Pesos']:
            if x['grupo'] not in existing_groups:errors.append(f'Pesos: grupo {x["grupo"]} no existe entre los clientes activos.')
            if x['peso']>0 and x['grupo'] not in groups_in_new|valid_existing:
                errors.append(f'Pesos: grupo {x["grupo"]} no tiene cinco prioridades completas.')
    if not target and not norm['Diagnostico']:
        errors.append('Para crear el diagnóstico, complete la hoja Diagnostico.')
    counts={sheet:len(norm[sheet]) for sheet in SHEETS}
    actions=Counter(x.get('accion','Nuevo') for section in norm.values() for x in section)
    return {'diagnostic_id':diagnostic_id,'diagnostic':norm['Diagnostico'][0] if norm['Diagnostico'] else None,
            'sections':norm,'counts':counts,'actions':dict(actions),'errors':errors,'sha256':hashlib.sha256(source).hexdigest(),
            'filename':name,'total':sum(counts.values())}


def import_workbook(source:bytes,name:str,actor:str,diagnostic_id:str|None=None,path:Path|None=None)->dict:
    actor=required(actor,'responsable de la importación')
    check=preview(source,name,diagnostic_id,path)
    if check['errors']:raise ValidationError('Corrija antes de importar: '+ ' | '.join(check['errors'][:8]))
    data=check['sections']
    with transaction(path) as con:
        if diagnostic_id:
            record=con.execute('SELECT estado FROM p2_diagnosticos WHERE id=?',(diagnostic_id,)).fetchone()
            if not record or record['estado']=='Cerrado':raise ValidationError('Diagnóstico no disponible o cerrado.')
            diag=diagnostic_id
        else:
            d=data['Diagnostico'][0];diag=uuid.uuid4().hex
            con.execute('''INSERT INTO p2_diagnosticos(id,nombre,ciclo,objetivo,alcance,responsable,poblacion_objetivo,estado)
                           VALUES (?,?,?,?,?,?,?,?)''',(diag,d['nombre'],d['ciclo'],d['objetivo'],d['alcance'],d['responsable'],d['poblacion'],d['estado']))
            con.execute('INSERT INTO p2_excel_diagnosticos(codigo_externo,diagnostico_id) VALUES (?,?)',(d['codigo'],diag))
            p2.audit(con,'p2_diagnostico',diag,'crear_desde_excel',actor,{'codigo_externo':d['codigo'],'nombre':d['nombre']})
        mapping={k:_external_map(con,diag,k) for k in ('Levantamientos','Necesidades','Evidencias')}
        applied=Counter()
        for r in data['Madurez']:
            if r['accion']=='Sin cambios':continue
            con.execute('''INSERT INTO p2_madurez(diagnostico_id,dimension,actual,deseado,fuente,responsable) VALUES (?,?,?,?,?,?)
              ON CONFLICT(diagnostico_id,dimension) DO UPDATE SET actual=excluded.actual,deseado=excluded.deseado,fuente=excluded.fuente,responsable=excluded.responsable,registrado_en=CURRENT_TIMESTAMP''',
              (diag,r['dimension'],r['actual'],r['deseado'],r['fuente'],r['responsable']))
            p2.audit(con,'p2_madurez',diag,'importar_excel',actor,r);applied['Madurez']+=1
        for r in data['Levantamientos']:
            if r['accion']=='Sin cambios':continue
            identifier=mapping['Levantamientos'].get(r['codigo'].casefold(),uuid.uuid4().hex)
            exists=identifier in mapping['Levantamientos'].values()
            if exists:
                con.execute('''UPDATE p2_levantamientos SET cliente_id=?,metodo=?,fecha=?,estado=?,observaciones=?,fuente=?,actor=? WHERE id=? AND diagnostico_id=?''',
                    (r['cliente_id'],r['metodo'],r['fecha'],r['estado'],r['observaciones'],r['fuente'],actor,identifier,diag))
            else:
                con.execute('''INSERT INTO p2_levantamientos(id,diagnostico_id,cliente_id,metodo,fecha,estado,observaciones,fuente,actor) VALUES (?,?,?,?,?,?,?,?,?)''',
                    (identifier,diag,r['cliente_id'],r['metodo'],r['fecha'],r['estado'],r['observaciones'],r['fuente'],actor))
                con.execute('INSERT INTO p2_excel_registros(diagnostico_id,seccion,codigo_externo,registro_id) VALUES (?,?,?,?)',
                    (diag,'Levantamientos',r['codigo'],identifier))
            mapping['Levantamientos'][r['codigo'].casefold()]=identifier
            p2.audit(con,'p2_levantamiento',identifier,'importar_excel',actor,{'codigo':r['codigo']});applied['Levantamientos']+=1
        for r in data['Expectativas']:
            if r['accion']=='Sin cambios':continue
            con.execute('DELETE FROM p2_expectativas WHERE diagnostico_id=? AND cliente_id=?',(diag,r['cliente_id']))
            for pos,oid in enumerate(r['prioridades'],1):
                con.execute('INSERT INTO p2_expectativas(diagnostico_id,cliente_id,posicion,resultado_id,notas,actor) VALUES (?,?,?,?,?,?)',
                    (diag,r['cliente_id'],pos,oid,r['notas'] if pos==1 else '',actor))
            p2.audit(con,'p2_expectativas',r['cliente_id'],'importar_excel_integral',actor,{'diagnostico':diag,'prioridades':r['prioridades']});applied['Expectativas']+=1
        for r in data['Necesidades']:
            if r['accion']=='Sin cambios':continue
            identifier=mapping['Necesidades'].get(r['codigo'].casefold(),uuid.uuid4().hex)
            exists=identifier in mapping['Necesidades'].values()
            if exists:
                old=con.execute('SELECT estado FROM p2_necesidades WHERE id=? AND diagnostico_id=?',(identifier,diag)).fetchone()
                if not old or old['estado'] in ('Validada','Descartada'):raise ValidationError(f'La necesidad {r["codigo"]} está validada/descartada: edítela manualmente.')
                con.execute('''UPDATE p2_necesidades SET cliente_id=?,dependencia=?,problema=?,ganancia=?,resultado_id=?,impacto=?,fuente=?,estado=?,actor=? WHERE id=? AND diagnostico_id=?''',
                    (r['cliente_id'],r['dependencia'],r['problema'],r['ganancia'],r['resultado_id'],r['impacto'],r['fuente'],r['estado'],actor,identifier,diag))
            else:
                con.execute('''INSERT INTO p2_necesidades(id,diagnostico_id,cliente_id,dependencia,problema,ganancia,resultado_id,impacto,fuente,estado,actor)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (identifier,diag,r['cliente_id'],r['dependencia'],r['problema'],r['ganancia'],r['resultado_id'],r['impacto'],r['fuente'],r['estado'],actor))
                con.execute('INSERT INTO p2_excel_registros(diagnostico_id,seccion,codigo_externo,registro_id) VALUES (?,?,?,?)',
                    (diag,'Necesidades',r['codigo'],identifier))
            mapping['Necesidades'][r['codigo'].casefold()]=identifier
            p2.audit(con,'p2_necesidad',identifier,'importar_excel',actor,{'codigo':r['codigo']});applied['Necesidades']+=1
        for r in data['Evidencias']:
            if r['accion']=='Sin cambios':continue
            identifier=mapping['Evidencias'].get(r['codigo'].casefold(),uuid.uuid4().hex)
            exists=identifier in mapping['Evidencias'].values()
            n_id=mapping['Necesidades'].get(r['necesidad_codigo'].casefold()) if r['necesidad_codigo'] else None
            l_id=mapping['Levantamientos'].get(r['levantamiento_codigo'].casefold()) if r['levantamiento_codigo'] else None
            if exists:
                con.execute('''UPDATE p2_evidencias SET necesidad_id=?,levantamiento_id=?,titulo=?,tipo=?,url=?,responsable=?,fecha=? WHERE id=? AND diagnostico_id=?''',
                    (n_id,l_id,r['titulo'],r['tipo'],r['url'],r['responsable'],r['fecha'],identifier,diag))
            else:
                con.execute('''INSERT INTO p2_evidencias(id,diagnostico_id,necesidad_id,levantamiento_id,titulo,tipo,url,responsable,fecha) VALUES (?,?,?,?,?,?,?,?,?)''',
                    (identifier,diag,n_id,l_id,r['titulo'],r['tipo'],r['url'],r['responsable'],r['fecha']))
                con.execute('INSERT INTO p2_excel_registros(diagnostico_id,seccion,codigo_externo,registro_id) VALUES (?,?,?,?)',
                    (diag,'Evidencias',r['codigo'],identifier))
            mapping['Evidencias'][r['codigo'].casefold()]=identifier
            p2.audit(con,'p2_evidencia',identifier,'importar_excel',actor,{'codigo':r['codigo']});applied['Evidencias']+=1
        for r in data['Pesos']:
            if r['accion']=='Sin cambios':continue
            con.execute('''INSERT INTO p2_pesos(diagnostico_id,grupo,peso) VALUES (?,?,?)
              ON CONFLICT(diagnostico_id,grupo) DO UPDATE SET peso=excluded.peso,actualizado_en=CURRENT_TIMESTAMP''',
              (diag,r['grupo'],r['peso']))
            p2.audit(con,'p2_pesos',diag,'importar_excel',actor,r);applied['Pesos']+=1
        if applied or not diagnostic_id:
            con.execute('INSERT INTO p2_importaciones_integrales(id,diagnostico_id,archivo,sha256,filas,detalle_json,actor) VALUES (?,?,?,?,?,?,?)',
                (uuid.uuid4().hex,diag,name,check['sha256'],check['total'],json.dumps(dict(applied),ensure_ascii=False),actor))
        p2.audit(con,'p2_importacion',diag,'importacion_integral',actor,{'archivo':name,'aplicados':dict(applied),'checksum':check['sha256']})
    return {'diagnostic_id':diag,'applied':dict(applied),'rows':check['total'],'filename':name}


def template_bytes()->bytes:
    template=Path(__file__).resolve().parents[1]/'plantillas'/'PLANTILLA_PASO2_DIAGNOSTICO_V0.6.xlsx'
    return template.read_bytes()
