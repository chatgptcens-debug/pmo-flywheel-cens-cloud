"""Paso 2: modelo de negocio integrado, persistente, con trazabilidad a Paso 1.
Modelo analítico CENS basado en el prototipo aportado, NO equivalente a PMOGA.
La identidad de quien registra es declarativa; no hay autenticación corporativa en MVP.
"""
from __future__ import annotations
import json
import math
import uuid
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from .storage import connect, transaction
from .clients import ValidationError
from .step2_catalog import OUTCOMES, SERVICES, MAPPING_DOC

MATURITY = ['Estandarización','Gobernanza','Seguimiento','Metodologías']
AUDIT_DIMENSIONS = [
 ('Evaluación orientada a resultados',[
   'El diagnóstico parte de resultados que desean conseguir los clientes.',
   'Existe información documentada sobre el contexto de los proyectos.',
   'Se identifican segmentos y sus expectativas diferenciadas.',
   'Los resultados deseados se vinculan a problemas reales.',
   'Se acuerda el alcance del diagnóstico con los interesados.']),
 ('Recopilación y análisis de información',[
   'Se aplican métodos apropiados para escuchar a los clientes.',
   'Las evidencias conservan fuente, fecha y relación con el cliente.',
   'Los registros permiten comparar necesidades entre segmentos.',
   'Se analizan entrevistas, encuestas y fuentes documentales.',
   'Se comprueba la calidad de las respuestas antes de analizar.']),
 ('Brechas y oportunidades',[
   'Se identifica la situación actual y la situación esperada.',
   'Se registran problemas y sus consecuencias para los clientes.',
   'Las oportunidades incluyen resultados verificables.',
   'Se distinguen hechos documentados de percepciones.',
   'Se relacionan brechas con objetivos de la organización.']),
 ('Priorización de necesidades',[
   'Las reglas de ponderación se documentan y se justifican.',
   'Las prioridades se sustentan en respuestas de clientes.',
   'La priorización considera diferencias entre grupos.',
   'Se revisan las recomendaciones antes de decidir servicios.',
   'Los clientes participan en validar prioridades y hallazgos.']),
 ('Valor y comunicación del diagnóstico',[
   'Se entregan resultados comprensibles para cada audiencia.',
   'Se comunican límites de la muestra y del método.',
   'Las necesidades validadas mantienen trazabilidad a sus fuentes.',
   'Se identifican decisiones y acciones posteriores.',
   'Los antecedentes quedan disponibles para formular propuestas.']),
]
INSTRUMENT = 'CENS-ADAPTADA-P2-2026.1'
RANGES = [(113,125,'Excelente'),(98,112,'Bien'),(77,97,'Promedio'),(51,76,'Pobre'),(25,50,'Crítico')]


def required(v: Any, name: str) -> str:
    value=str(v or '').strip()
    if not value: raise ValidationError(f'Indique {name}.')
    return value


def validate_date(v: date | str) -> str:
    try:return (v if isinstance(v,date) else date.fromisoformat(str(v))).isoformat()
    except (TypeError,ValueError) as ex:raise ValidationError('Fecha inválida; utilice AAAA-MM-DD.') from ex


def rows(sql: str, params: tuple=(), path:Path|None=None) -> list[dict]:
    with closing(connect(path)) as con:
        return [dict(r) for r in con.execute(sql,params)]


def audit(con,kind,eid,action,actor,detail=None):
    con.execute('INSERT INTO pmo_auditoria(entidad,entidad_id,accion,actor,despues_json) VALUES (?,?,?,?,?)',
                (kind,eid,action,actor,json.dumps(detail,ensure_ascii=False,default=str) if detail is not None else None))


def _id_ok(con,diag_id:str):
    row=con.execute('SELECT * FROM p2_diagnosticos WHERE id=?',(diag_id,)).fetchone()
    if not row:raise ValidationError('El diagnóstico seleccionado no existe.')
    return row


def create_diagnostic(name:str,cycle:str,owner:str,objective:str='',scope:str='',population:int|None=None,path:Path|None=None)->str:
    name,cycle,owner=required(name,'nombre del diagnóstico'),required(cycle,'ciclo'),required(owner,'responsable')
    if population is not None and (not isinstance(population,int) or population<0):raise ValidationError('Población objetivo inválida.')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        con.execute('INSERT INTO p2_diagnosticos(id,nombre,ciclo,objetivo,alcance,responsable,poblacion_objetivo) VALUES (?,?,?,?,?,?,?)',
                    (key,name,cycle,objective.strip(),scope.strip(),owner,population))
        audit(con,'p2_diagnostico',key,'crear',owner)
    return key


def list_diagnostics(path:Path|None=None):
    return rows('SELECT * FROM p2_diagnosticos ORDER BY creado_en DESC, rowid DESC',path=path)


def update_diagnostic(diag:str,name:str,owner:str,objective:str,scope:str,population:int|None,status:str,actor:str,path:Path|None=None):
    if status not in ('En diseño','Programado','En levantamiento','En análisis','Cerrado'):
        raise ValidationError('Estado de diagnóstico inválido.')
    if population is not None and (not isinstance(population,int) or population<0):raise ValidationError('Población inválida.')
    actor=required(actor,'responsable del cambio')
    with transaction(path) as con:
        before=dict(_id_ok(con,diag))
        con.execute('UPDATE p2_diagnosticos SET nombre=?,responsable=?,objetivo=?,alcance=?,poblacion_objetivo=?,estado=?,actualizado_en=CURRENT_TIMESTAMP WHERE id=?',
                    (required(name,'nombre'),required(owner,'responsable'),objective.strip(),scope.strip(),population,status,diag))
        audit(con,'p2_diagnostico',diag,'actualizar',actor,{'antes':before,'nuevo_estado':status})


def set_maturity(diag:str, dimension:str, actual:int,desired:int,source:str,actor:str,path:Path|None=None):
    if dimension not in MATURITY:raise ValidationError('Dimensión de madurez inválida.')
    if any(not isinstance(x,int) or not 1<=x<=5 for x in (actual,desired)):raise ValidationError('Calificaciones entre 1 y 5.')
    source=required(source,'fuente de percepción')
    actor=required(actor,'responsable')
    with transaction(path) as con:
        _id_ok(con,diag)
        con.execute('INSERT INTO p2_madurez(diagnostico_id,dimension,actual,deseado,fuente,responsable) VALUES (?,?,?,?,?,?) ON CONFLICT(diagnostico_id,dimension) DO UPDATE SET actual=excluded.actual,deseado=excluded.deseado,fuente=excluded.fuente,responsable=excluded.responsable,registrado_en=CURRENT_TIMESTAMP',
                    (diag,dimension,actual,desired,source,actor))
        audit(con,'p2_madurez',diag,'actualizar',actor,{'dimension':dimension,'actual':actual,'deseado':desired,'fuente':source})


def maturity(diag:str,path:Path|None=None):
    return rows('SELECT * FROM p2_madurez WHERE diagnostico_id=? ORDER BY dimension',(diag,),path)


def create_interview(diag:str,client:str,method:str,when:date|str,status:str,notes:str,source:str,actor:str,path:Path|None=None)->str:
    if method not in ('Entrevista','Encuesta','Grupo focal','Revisión documental'):raise ValidationError('Método inválido.')
    if status not in ('Programada','En curso','Completada','Cancelada'):raise ValidationError('Estado inválido.')
    actor=required(actor,'responsable')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        _id_ok(con,diag)
        if not con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client,)).fetchone():raise ValidationError('Cliente no registrado en Paso 1.')
        con.execute('INSERT INTO p2_levantamientos(id,diagnostico_id,cliente_id,metodo,fecha,estado,observaciones,fuente,actor) VALUES (?,?,?,?,?,?,?,?,?)',
                    (key,diag,client,method,validate_date(when),status,notes.strip(),source.strip(),actor))
        audit(con,'p2_levantamiento',key,'crear',actor)
    return key


def interviews(diag:str,path:Path|None=None):
    return rows('''SELECT l.*,c.nombre AS cliente,c.codigo AS codigo_cliente,c.segmento FROM p2_levantamientos l
        JOIN pmo_clientes c ON c.id=l.cliente_id WHERE diagnostico_id=? ORDER BY fecha DESC,creado_en DESC''',(diag,),path)


def _validate_priorities(priorities:list[int], allow_partial:bool=True):
    if len(priorities)>5 or (not allow_partial and len(priorities)!=5):raise ValidationError('Se requieren cinco resultados diferentes para la priorización.')
    if any(not isinstance(v,int) or isinstance(v,bool) or v not in OUTCOMES for v in priorities):raise ValidationError('Resultados permitidos: números enteros entre 1 y 30.')
    if len(set(priorities))!=len(priorities):raise ValidationError('Una persona no puede repetir resultados entre sus prioridades.')


def save_priorities(diag:str,client:str,priorities:list[int],actor:str,notes:dict[int,str]|None=None,path:Path|None=None):
    _validate_priorities(priorities)
    actor=required(actor,'responsable')
    notes=notes or {}
    with transaction(path) as con:
        _id_ok(con,diag)
        if not con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client,)).fetchone():raise ValidationError('Cliente no registrado en Paso 1.')
        previous=[dict(r) for r in con.execute('SELECT posicion,resultado_id FROM p2_expectativas WHERE diagnostico_id=? AND cliente_id=? ORDER BY posicion',(diag,client))]
        con.execute('DELETE FROM p2_expectativas WHERE diagnostico_id=? AND cliente_id=?',(diag,client))
        for pos,result in enumerate(priorities,1):
            con.execute('INSERT INTO p2_expectativas(diagnostico_id,cliente_id,posicion,resultado_id,notas,actor) VALUES (?,?,?,?,?,?)',
                        (diag,client,pos,result,str(notes.get(result,'')).strip(),actor))
        audit(con,'p2_expectativas',client,'guardar',actor,{'diagnostico':diag,'antes':previous,'despues':priorities})


def expectations(diag:str,client:str|None=None,path:Path|None=None):
    sql='''SELECT e.*, c.codigo,c.nombre,c.segmento,c.activo,d.nombre AS dependencia FROM p2_expectativas e
        JOIN pmo_clientes c ON c.id=e.cliente_id JOIN pmo_dependencias d ON d.id=c.dependencia_id WHERE e.diagnostico_id=?'''
    if client:sql+=' AND e.cliente_id=?'
    sql+=' ORDER BY c.nombre COLLATE NOCASE,e.posicion'
    return rows(sql,(diag,client) if client else (diag,),path)


def _participant_records(diag:str, path:Path|None=None):
    record={}
    for r in expectations(diag,path=path):
        if not r['activo']:continue
        if r['cliente_id'] not in record:
            record[r['cliente_id']]={'id':r['cliente_id'],'codigo':r['codigo'],'name':r['nombre'],'group':r['segmento'].strip() or 'Sin segmento','priorities':[]}
        record[r['cliente_id']]['priorities'].append(r['resultado_id'])
    return list(record.values())


def create_need(diag:str,client:str|None,dept:str,problem:str,gain:str,outcome:int|None,impact:str,source:str,actor:str,path:Path|None=None)->str:
    problem,gain,dept,actor=required(problem,'dificultad'),required(gain,'resultado deseado'),required(dept,'dependencia'),required(actor,'responsable')
    if outcome is not None and outcome not in OUTCOMES:raise ValidationError('Resultado esperado inexistente.')
    if impact not in ('Sin evaluar','Bajo','Medio','Alto'):raise ValidationError('Impacto inválido.')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        _id_ok(con,diag)
        if client and not con.execute('SELECT id FROM pmo_clientes WHERE id=?',(client,)).fetchone():raise ValidationError('Cliente inexistente.')
        con.execute('INSERT INTO p2_necesidades(id,diagnostico_id,cliente_id,dependencia,problema,ganancia,resultado_id,impacto,fuente,actor) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (key,diag,client,dept,problem,gain,outcome,impact,source.strip(),actor))
        audit(con,'p2_necesidad',key,'crear',actor)
    return key


def needs(diag:str,status:str='',path:Path|None=None):
    sql='''SELECT n.*,c.nombre AS cliente,c.codigo AS cliente_codigo,c.segmento AS segmento FROM p2_necesidades n
       LEFT JOIN pmo_clientes c ON c.id=n.cliente_id WHERE n.diagnostico_id=?'''
    args=[diag]
    if status:sql+=' AND n.estado=?';args.append(status)
    sql+=' ORDER BY n.creado_en DESC,n.rowid DESC'
    return rows(sql,tuple(args),path)


def update_need_status(need_id:str,status:str,actor:str,reason:str,path:Path|None=None):
    if status not in ('Registrada','En validación','Validada','Descartada'):raise ValidationError('Estado de necesidad inválido.')
    actor=required(actor,'responsable de validación')
    if status in ('Validada','Descartada') and not reason.strip():raise ValidationError('Debe explicar la decisión de validar o descartar.')
    with transaction(path) as con:
        before=con.execute('SELECT * FROM p2_necesidades WHERE id=?',(need_id,)).fetchone()
        if not before:raise ValidationError('Necesidad inexistente.')
        if status=='Validada' and not before['fuente'] and not con.execute('SELECT 1 FROM p2_evidencias WHERE necesidad_id=?',(need_id,)).fetchone():
            raise ValidationError('La validación requiere una fuente registrada o una evidencia vinculada.')
        con.execute('UPDATE p2_necesidades SET estado=?,validador=?,justificacion_validacion=?,validado_en=CASE WHEN ?=? THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?',
                    (status,actor,reason.strip(),status,'Validada',need_id))
        audit(con,'p2_necesidad',need_id,'cambiar_estado',actor,{'antes':before['estado'],'despues':status,'motivo':reason})


def create_evidence(diag:str,title:str,kind:str,when:date|str,actor:str,need_id:str|None=None,interview_id:str|None=None,url:str='',path:Path|None=None)->str:
    title,kind,actor=required(title,'descripción de evidencia'),required(kind,'tipo de evidencia'),required(actor,'responsable')
    if url:
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc:raise ValidationError('El enlace debe comenzar con https:// o http://.')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        _id_ok(con,diag)
        if need_id and not con.execute('SELECT id FROM p2_necesidades WHERE id=? AND diagnostico_id=?',(need_id,diag)).fetchone():raise ValidationError('La necesidad no pertenece a este diagnóstico.')
        if interview_id and not con.execute('SELECT id FROM p2_levantamientos WHERE id=? AND diagnostico_id=?',(interview_id,diag)).fetchone():raise ValidationError('El levantamiento no pertenece a este diagnóstico.')
        con.execute('INSERT INTO p2_evidencias(id,diagnostico_id,necesidad_id,levantamiento_id,titulo,tipo,url,responsable,fecha) VALUES (?,?,?,?,?,?,?,?,?)',
                    (key,diag,need_id,interview_id,title,kind,url.strip(),actor,validate_date(when)))
        audit(con,'p2_evidencia',key,'crear',actor)
    return key


def evidence(diag:str,path:Path|None=None):
    return rows('SELECT * FROM p2_evidencias WHERE diagnostico_id=? ORDER BY fecha DESC',(diag,),path)


def groups_with_participants(diag:str,path:Path|None=None):
    from collections import Counter
    return dict(sorted(Counter(x['group'] for x in _participant_records(diag,path)).items()))


def save_weights(diag:str,weights:dict[str,float],actor:str,path:Path|None=None):
    actor=required(actor,'responsable')
    complete={x['group'] for x in _participant_records(diag,path) if len(x['priorities'])==5}
    if set(weights)!=complete or not complete:
        raise ValidationError('Configure exactamente los grupos que tienen cinco prioridades completas.')
    try:w={str(k):float(v) for k,v in weights.items()}
    except (ValueError,TypeError) as ex:raise ValidationError('Peso de grupo inválido.') from ex
    if any(not math.isfinite(v) or v<0 or v>100 for v in w.values()) or abs(sum(w.values())-100)>0.001:
        raise ValidationError('Los pesos deben estar entre 0 y 100 y sumar 100%.')
    with transaction(path) as con:
        _id_ok(con,diag)
        con.execute('DELETE FROM p2_pesos WHERE diagnostico_id=?',(diag,))
        for group,weight in w.items():con.execute('INSERT INTO p2_pesos(diagnostico_id,grupo,peso) VALUES (?,?,?)',(diag,group,weight))
        audit(con,'p2_pesos',diag,'guardar',actor,w)


def saved_weights(diag:str,path:Path|None=None):
    return {r['grupo']:r['peso'] for r in rows('SELECT * FROM p2_pesos WHERE diagnostico_id=?',(diag,),path)}


def validate_matrix(mapping:dict[int,dict[int,float]]):
    if not isinstance(mapping,dict):raise ValidationError('Matriz de correspondencias inválida.')
    clean={}
    for outcome,services in mapping.items():
        try:oid=int(outcome)
        except (TypeError,ValueError) as ex:raise ValidationError('Código de resultado inválido.') from ex
        if oid not in OUTCOMES or not isinstance(services,dict):raise ValidationError('Resultado inválido en matriz.')
        clean[oid]={}
        for svc,strength in services.items():
            try:sid=int(svc); v=float(strength)
            except (TypeError,ValueError) as ex:raise ValidationError('Código o intensidad inválida.') from ex
            if sid not in SERVICES or not math.isfinite(v) or v not in (0,1,2,3,4):raise ValidationError('Códigos 1–30, servicios 1–26, intensidad entera 0–4.')
            clean[oid][sid]=int(v)
    if not any(value>0 for sub in clean.values() for value in sub.values()):raise ValidationError('La matriz no puede tener todas las intensidades en cero.')
    return clean


def default_matrix():return {oid:{sid:1 for sid in ids} for oid,ids in MAPPING_DOC.items()}


def compute(diag:str,weights:dict[str,float],matrix:dict|None=None,path:Path|None=None):
    """Ranking a partir de las 5 prioridades válidas por cliente y ponderación por grupo.

    Score resultado[g] = sum(6-pos)/(15*n_g); share = sum(peso_g * score_g).
    Servicios = sum(share_resultado * intensidad), normalizados a 100.
    """
    participants=_participant_records(diag,path)
    complete=[x for x in participants if len(x['priorities'])==5]
    skipped=[x for x in participants if len(x['priorities'])!=5]
    if not complete:raise ValidationError('No hay clientes con las cinco prioridades completas.')
    active_groups={x['group'] for x in complete}
    if set(weights)!=active_groups:raise ValidationError('Los pesos no corresponden a los grupos con respuestas completas.')
    w={k:float(v) for k,v in weights.items()}
    if any(not math.isfinite(v) or v<0 or v>100 for v in w.values()) or abs(sum(w.values())-100)>0.001:raise ValidationError('Los pesos deben sumar 100%.')
    mat=validate_matrix(matrix if matrix is not None else default_matrix())
    raw={oid:0.0 for oid in OUTCOMES}
    by_group={}
    for group in sorted(active_groups):
        individuals=[x for x in complete if x['group']==group]
        values={oid:0.0 for oid in OUTCOMES}
        for x in individuals:
            for pos,oid in enumerate(x['priorities'],1):values[oid]+=(6-pos)
        values={k:v/(15*len(individuals)) for k,v in values.items()}
        by_group[group]={'participants':len(individuals),'weight':w[group],'outcomes':values}
        for oid,val in values.items():raw[oid]+=val*w[group]/100
    total=sum(raw.values())
    if total<=0:raise ValidationError('No hay participantes con peso positivo.')
    outcome_rank=[{'id':oid,'name':OUTCOMES[oid],'score':100*raw[oid]/total} for oid in OUTCOMES]
    outcome_rank.sort(key=lambda x:(-x['score'],x['id']))
    sr={sid:0.0 for sid in SERVICES}
    for oid,val in raw.items():
        for sid,strength in mat.get(oid,{}).items():sr[sid]+=val*strength
    denominator=sum(sr.values())
    if denominator<=0:raise ValidationError('La matriz no genera relaciones para resultados con prioridad.')
    contribution={}
    for sid,raw_score in sr.items():
        lines=[]
        if raw_score>0:
            for oid,share in raw.items():
                strength=mat.get(oid,{}).get(sid,0)
                amount=share*strength
                if amount>0:
                    lines.append({'outcome_id':oid,'outcome':OUTCOMES[oid],
                        'result_weight_pct':100*share,'intensity':strength,
                        'raw_contribution':amount,'service_share_pct':100*amount/raw_score,
                        'global_share_pct':100*amount/denominator})
        contribution[str(sid)]=sorted(lines,key=lambda x:(-x['raw_contribution'],x['outcome_id']))
    accum=0
    service_rank=[]
    for sid,v in sorted(sr.items(),key=lambda x:(-x[1],x[0])):
        part=100*v/denominator;accum+=part
        category='Núcleo' if accum-part < 50-1e-8 else 'Importante' if accum-part < 80-1e-8 else 'Periférico'
        service_rank.append({'id':sid,'name':SERVICES[sid],'score':part,'cumulative':min(accum,100.0),'category':category})
    return {'participants':len(complete),'excluded_partial':len(skipped),'groups':by_group,
            'outcomes':outcome_rank,'services':service_rank,
            'top5':sum(x['score'] for x in service_rank[:5]), 'method':'CENS-P2-PESO-POSICION-1',
            'sample_total':len(participants), 'contributions':contribution, 'matrix_cells':sum(len(sub) for sub in mat.values()), 'nonzero_links':sum(v>0 for sub in mat.values() for v in sub.values())}


def run(diag:str,weights:dict[str,float],actor:str,custom_matrix:dict|None=None,path:Path|None=None,source:str='Registros del Paso 2',matrix_version_id:str|None=None)->str:
    actor=required(actor,'responsable del cálculo')
    from . import matrix as canonical
    vid=matrix_version_id
    if vid is not None and custom_matrix is not None:
        raise ValidationError('Seleccione una versión de matriz O una matriz temporal, no ambas.')
    if vid is not None:
        v=canonical.version(vid,path)
        if v['estado']=='ARCHIVADA':raise ValidationError('Matriz archivada; seleccione una vigente.')
        mat=canonical.matrix(vid,path)
        model=f"{vid} · {v['fuente']} · {v['estado']}"
    elif custom_matrix is not None:
        mat=validate_matrix(custom_matrix)
        model='Matriz temporal personalizada sin versión institucional'
    else:
        vid=canonical.DOC_ID
        mat=canonical.matrix(vid,path)
        model='X2 documental · 0–1 · referencia sin aprobación corporativa'
    # V5: respetar los supuestos verificados en las 38 corridas de referencia.
    # El resto de matrices conserva el funcionamiento de versiones anteriores.
    if vid == canonical.V5_ID:
        from . import v5_engine
        participants_all = _participant_records(diag,path)
        if any(len(person['priorities'])!=5 for person in participants_all):
            raise ValidationError('V5 exige exactamente cinco prioridades distintas para cada participante registrado; complete los borradores antes de procesar.')
        integers = {}
        for group,value in weights.items():
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not float(value).is_integer():
                raise ValidationError('V5 requiere ponderaciones enteras explícitas (0 a 100) por grupo.')
            integers[group]=int(value)
        reference_rows=[{'name':person['name'],'group':person['group'],'priorities':person['priorities']} for person in participants_all]
        try:
            r, _group_info=v5_engine.relevancias_de_clientes(reference_rows,integers)
            v5_result=v5_engine.calcular_servicios(r,[[mat[o][sid] for sid in range(1,27)] for o in range(1,31)],
                                                    metadata={'version':canonical.V5_ID})
        except (ValueError,TypeError,KeyError) as ex:
            raise ValidationError('Los datos no cumplen las reglas del motor V5: '+str(ex)) from ex
        weights=integers
    result=compute(diag,weights,mat,path)
    if vid == canonical.V5_ID:
        by_id={record['id']:record['score'] for record in result['services']}
        delta=max(abs(by_id[service_id]-v5_result['servicios_26_pct'][service_id-1]) for service_id in range(1,27))
        if delta>1e-9:
            raise ValidationError('Control de conformidad V5 fallido: el ranking no coincide con el motor de referencia.')
        digest=v5_engine.hash_matriz([[mat[o][sid] for sid in range(1,27)] for o in range(1,31)])
        if digest!=canonical.V5_HASH:
            raise ValidationError('La matriz V5 cambió respecto a su versión de referencia.')
        result['method']='CENS-V5-ADITIVO-30FOCO'
        result['v5_validation']={'matrix_sha256':digest,'cases_reference':38,'historical_independent':8,
            'focus_cases':30,'max_internal_delta_pp':delta,'weight_policy':'enteros explícitos, suma exacta 100',
            'provenance':'reconstrucción matemática; no certificada PMI/PMOGA'}
    result['matrix_version_id']=vid
    result['matrix_model']=model
    participants=[x for x in _participant_records(diag,path) if len(x['priorities'])==5]
    key=uuid.uuid4().hex
    with transaction(path) as con:
        _id_ok(con,diag)
        con.execute('INSERT INTO p2_corridas(id,diagnostico_id,origen,modelo,matriz_json,pesos_json,respuestas_json,resultados_json,actor,matrix_version_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (key,diag,source,model,json.dumps(mat,ensure_ascii=False,sort_keys=True),
             json.dumps(weights,ensure_ascii=False,sort_keys=True),json.dumps(participants,ensure_ascii=False),
             json.dumps(result,ensure_ascii=False),actor,vid))
        audit(con,'p2_corrida',key,'procesar',actor,{'diagnostico':diag,'participantes':len(participants),
            'origen':source,'version_matriz':vid})
    return key


def runs(diag:str,path:Path|None=None):
    return rows('SELECT id,diagnostico_id,origen,modelo,actor,fecha FROM p2_corridas WHERE diagnostico_id=? ORDER BY fecha DESC,rowid DESC',(diag,),path)


def get_run(key:str,path:Path|None=None):
    r=rows('SELECT * FROM p2_corridas WHERE id=?',(key,),path)
    if not r:raise ValidationError('Análisis no encontrado.')
    data=r[0]
    for field in ('matriz_json','pesos_json','respuestas_json','resultados_json'):data[field[:-5]]=json.loads(data[field])
    return data


def set_candidate(diag:str,service:int,status:str,reason:str,actor:str,path:Path|None=None):
    if service not in SERVICES:raise ValidationError('Servicio fuera del catálogo.')
    if status not in ('Preseleccionado','En validación','Validado','Descartado'):raise ValidationError('Estado candidato inválido.')
    actor=required(actor,'responsable')
    reason=required(reason,'justificación de la decisión')
    with transaction(path) as con:
        _id_ok(con,diag)
        if status=='Validado' and not con.execute("SELECT 1 FROM p2_necesidades WHERE diagnostico_id=? AND estado='Validada'",(diag,)).fetchone():
            raise ValidationError('Primero registre al menos una necesidad validada.')
        con.execute('INSERT INTO p2_servicios_candidatos(diagnostico_id,servicio_id,estado,justificacion,responsable) VALUES (?,?,?,?,?) ON CONFLICT(diagnostico_id,servicio_id) DO UPDATE SET estado=excluded.estado,justificacion=excluded.justificacion,responsable=excluded.responsable,actualizado_en=CURRENT_TIMESTAMP',
                    (diag,service,status,reason,actor))
        audit(con,'p2_candidato',f'{diag}:{service}','decidir',actor,{'estado':status,'justificacion':reason})


def candidates(diag:str,path:Path|None=None):
    return rows('SELECT * FROM p2_servicios_candidatos WHERE diagnostico_id=? ORDER BY servicio_id',(diag,),path)


def classification(score:int|None):
    return next((name for lo,hi,name in RANGES if score is not None and lo<=score<=hi),None)


def start_assessment(diag:str,evaluator:str,path:Path|None=None):
    evaluator=required(evaluator,'evaluador')
    key=uuid.uuid4().hex
    with transaction(path) as con:
        _id_ok(con,diag)
        con.execute('INSERT INTO p2_autoevaluaciones(id,diagnostico_id,evaluador,instrumento) VALUES (?,?,?,?)',
                    (key,diag,evaluator,INSTRUMENT))
        audit(con,'p2_autoevaluacion',key,'crear',evaluator)
    return key


def assessments(diag:str,path:Path|None=None):
    return rows('SELECT * FROM p2_autoevaluaciones WHERE diagnostico_id=? ORDER BY creado_en DESC,rowid DESC',(diag,),path)


def answers(aid:str,path:Path|None=None):
    return {r['numero']:r for r in rows('SELECT * FROM p2_respuestas_autoevaluacion WHERE evaluacion_id=?',(aid,),path)}


def save_answer(aid:str,number:int,rating:int|None,observation:str,evidence_url:str,actor:str,path:Path|None=None):
    if number<1 or number>25:raise ValidationError('Criterio fuera de rango.')
    if rating is not None and (not isinstance(rating,int) or rating not in range(1,6)):raise ValidationError('Valoración 1–5.')
    actor=required(actor,'responsable')
    with transaction(path) as con:
        r=con.execute('SELECT estado FROM p2_autoevaluaciones WHERE id=?',(aid,)).fetchone()
        if not r:raise ValidationError('Evaluación inexistente.')
        if r['estado']=='Finalizada':raise ValidationError('No se puede modificar una evaluación finalizada.')
        if rating is None:
            con.execute('DELETE FROM p2_respuestas_autoevaluacion WHERE evaluacion_id=? AND numero=?',(aid,number))
        else:
            con.execute('INSERT INTO p2_respuestas_autoevaluacion(evaluacion_id,numero,valor,observacion,evidencia) VALUES (?,?,?,?,?) ON CONFLICT(evaluacion_id,numero) DO UPDATE SET valor=excluded.valor,observacion=excluded.observacion,evidencia=excluded.evidencia',
                        (aid,number,rating,observation.strip(),evidence_url.strip()))
        audit(con,'p2_autoevaluacion',aid,'guardar_respuesta',actor,{'numero':number,'rating':rating})


def finish_assessment(aid:str,actor:str,path:Path|None=None):
    actor=required(actor,'responsable')
    with transaction(path) as con:
        r=con.execute('SELECT estado FROM p2_autoevaluaciones WHERE id=?',(aid,)).fetchone()
        if not r:raise ValidationError('Evaluación inexistente.')
        if r['estado']=='Finalizada':raise ValidationError('Ya está finalizada.')
        count,total=con.execute('SELECT COUNT(*), SUM(valor) FROM p2_respuestas_autoevaluacion WHERE evaluacion_id=?',(aid,)).fetchone()
        if count!=25:raise ValidationError(f'Faltan {25-count} criterios para finalizar.')
        level=classification(total)
        con.execute("UPDATE p2_autoevaluaciones SET estado='Finalizada',puntaje=?,clasificacion=?,finalizada_en=CURRENT_TIMESTAMP WHERE id=?",(total,level,aid))
        audit(con,'p2_autoevaluacion',aid,'finalizar',actor,{'puntaje':total,'clasificacion':level})
    return total,level


def summary(diag:str,path:Path|None=None):
    with closing(connect(path)) as con:
        clients=con.execute('SELECT COUNT(DISTINCT cliente_id) FROM p2_levantamientos WHERE diagnostico_id=?',(diag,)).fetchone()[0]
        participant=con.execute('SELECT COUNT(DISTINCT cliente_id) FROM p2_expectativas WHERE diagnostico_id=?',(diag,)).fetchone()[0]
        needs_valid=con.execute("SELECT COUNT(*) FROM p2_necesidades WHERE diagnostico_id=? AND estado='Validada'",(diag,)).fetchone()[0]
        needs_pending=con.execute("SELECT COUNT(*) FROM p2_necesidades WHERE diagnostico_id=? AND estado IN ('Registrada','En validación')",(diag,)).fetchone()[0]
        dept=con.execute('''SELECT COUNT(DISTINCT c.dependencia_id) FROM p2_levantamientos l JOIN pmo_clientes c ON c.id=l.cliente_id WHERE l.diagnostico_id=?''',(diag,)).fetchone()[0]
        evidence_count=con.execute('SELECT COUNT(*) FROM p2_evidencias WHERE diagnostico_id=?',(diag,)).fetchone()[0]
    return {'clientes_levantados':clients,'clientes_expectativas':participant,'areas':dept,'necesidades_validadas':needs_valid,'necesidades_pendientes':needs_pending,'evidencias':evidence_count}


def transfer_json(diag:str,path:Path|None=None):
    d=[x for x in list_diagnostics(path) if x['id']==diag]
    if not d:raise ValidationError('Diagnóstico no encontrado.')
    data={'version':'CENS-P2-TRANSFERENCIA-1','tipo':'Insumos para futuro Paso 3; no equivale a aprobación',
          'diagnostico':d[0], 'clientes_y_expectativas':expectations(diag,path=path),
          'necesidades':needs(diag,path=path), 'evidencias':evidence(diag,path=path),
          'servicios_candidatos':candidates(diag,path=path), 'corridas':runs(diag,path=path)}
    return json.dumps(data,ensure_ascii=False,indent=2,default=str).encode('utf-8')

# AHP: ayuda opcional y separada del motor; nunca sustituye pesos confirmados.
def ahp_weights(groups:list[str], comparisons:dict[tuple[str,str],float]):
    """Calcula pesos AHP por promedio geométrico y CR aproximada (método CENS).
    No representa un cálculo certificado de PMOGA; el usuario debe confirmar los pesos.
    """
    if not 2<=len(groups)<=8 or len(set(groups))!=len(groups):
        raise ValidationError('AHP admite de dos a ocho grupos distintos.')
    n=len(groups)
    matrix=[[1.0]*n for _ in range(n)]
    for i,a in enumerate(groups):
        for j in range(i+1,n):
            b=groups[j]
            try:value=float(comparisons[(a,b)])
            except (KeyError,ValueError,TypeError) as ex:raise ValidationError(f'Falta comparación entre {a} y {b}.') from ex
            if not math.isfinite(value) or value<1/9 or value>9:raise ValidationError('AHP exige relaciones entre 1/9 y 9.')
            matrix[i][j]=value
            matrix[j][i]=1/value
    geo=[math.prod(row)**(1/n) for row in matrix]
    total=sum(geo)
    v=[x/total for x in geo]
    lam=sum(sum(matrix[i][j]*v[j] for j in range(n))/v[i] for i in range(n))/n
    ci=max((lam-n)/(n-1),0.0)
    ri={2:0.0,3:0.58,4:0.90,5:1.12,6:1.24,7:1.32,8:1.41}[n]
    cr=(ci/ri if ri>0 else 0.0)
    # for numeric robustness, force exact 100 with last component
    weights={g:round(100*v[i],2) for i,g in enumerate(groups[:-1])}
    weights[groups[-1]]=round(100-sum(weights.values()),2)
    return weights,cr
