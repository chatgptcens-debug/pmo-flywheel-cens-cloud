"""Paso 03 V0.39.18 · estado de calidad consultivo, sin recalcular V5.

El resultado de quality no implica aprobación ni cambia la elegibilidad histórica
al Paso 04; se preserva el gate documentado en step3.approval_errors.
"""
from __future__ import annotations
import json
from . import step3 as s


def benefit_quality(row):
    """Tres controles diferentes: descripción, salida propuesta y beneficio esperado."""
    linked=bool(row.get('diagnostico_origen') and row.get('necesidad_origen'))
    return {
        'origen_vinculado':linked,
        'necesidad_documentada':bool(str(row.get('necesidad') or '').strip()),
        'entregable_propuesto':bool(str(row.get('entregable') or '').strip()),
        'beneficio_formulado':bool(str(row.get('beneficio') or '').strip()),
        'metrica_candidata':bool(str(row.get('metrica') or '').strip()),
        'soporte_referenciado':bool(str(row.get('evidencia') or '').strip()),
        'validado_en_p3':row.get('estado') in ('Validada','Aprobada'),
        'validado_en_p2':row.get('estado_necesidad_origen') in ('Validada','Aprobada'),
    }


def canvas_quality(canvas_id,path=None):
    cs=s.cards(canvas_id,path);ls=s.links(canvas_id,path)
    by_id={x['id']:x for x in cs}
    pain=[x for x in cs if x['zona']=='dolores']
    addressed={}
    for x in pain:
        targets=[]
        for link in ls:
            if x['id'] not in (link['origen_id'],link['destino_id']):continue
            other=link['destino_id'] if link['origen_id']==x['id'] else link['origen_id']
            if by_id.get(other,{}).get('zona') in ('aliviadores','servicios'):
                targets.append(other)
        addressed[x['id']]=targets
    return {'dolores':len(pain),'atendidos':sum(bool(x) for x in addressed.values()),
            'pendientes':[x for x in pain if not addressed[x['id']]],
            'conexiones':len(ls),'tarjetas':len(cs),
            'cobertura_pct':round(100*sum(bool(x) for x in addressed.values())/len(pain)) if pain else None}


def solution_quality(row,path=None):
    """Separa mínimos contractuales ya vigentes de criterios de calidad orientativos.

    NO modifica aprobaciones históricas y nunca convierte una ficha en validada.
    """
    hard=s.approval_errors(row)
    advice=[]
    if s.feasibility(row) is None:
        advice.append('Completar los cuatro criterios de viabilidad CENS')
    lid=row.get('lienzo_id')
    if not lid:
        advice.append('Asociar lienzo o justificar el valor sin lienzo')
    else:
        coverage=canvas_quality(lid,path)
        if not coverage['conexiones']:
            advice.append('Documentar al menos una conexión del lienzo')
    if not str(row.get('horizonte') or '').strip() or not str(row.get('periodo') or '').strip():
        advice.append('Precisar horizonte y periodo tentativo')
    if not str(row.get('riesgo') or '').strip():
        advice.append('Identificar riesgos de no lograr el valor esperado')
    agreement=s.agreement_record(row.get('id'),path) if row.get('id') else None
    if row.get('estado')=='Aprobada' and (agreement is None or not agreement['vigente']):
        advice.append('Registrar o actualizar el acuerdo de valor versionado (validación histórica no verificada)')
    return {'acuerdo_versionado_vigente':bool(agreement and agreement['vigente']),
            'codigo':row.get('codigo'),'estado':row.get('estado'),
            'bloqueantes':hard,'recomendaciones':advice,
            'habilitada_para_transferencia':row.get('estado')=='Aprobada' and not hard,
            'viabilidad_cens':s.feasibility(row)}


def quality_summary(path=None):
    br=s.benefits(path);canv=s.canvases(path);sol=s.solutions(path)
    q=[benefit_quality(r) for r in br]
    return {'necesidades':len(br),'origen_p2':sum(x['origen_vinculado'] for x in q),
            'beneficios_formulados':sum(x['beneficio_formulado'] for x in q),
            'entregables_propuestos':sum(x['entregable_propuesto'] for x in q),
            'beneficios_validados':sum(x['validado_en_p3'] for x in q),
            'lienzos':len(canv),'lienzos_con_conexiones':sum(canvas_quality(c['id'],path)['conexiones']>0 for c in canv),
            'soluciones':len(sol),'soluciones_listas':sum(solution_quality(x,path)['habilitada_para_transferencia'] for x in sol)}


def context_audit(path=None):
    """Consulta de orígenes existentes; no fusiona ciclos ni reescribe claves."""
    benefits=s.benefits(path);canvases=s.canvases(path);solutions=s.solutions(path)
    bmap={b['id']:b for b in benefits};cmap={c['id']:c for c in canvases}
    origins={}
    for r in benefits:
        origin=str(r.get('diagnostico_origen') or '').strip() or 'Sin diagnóstico identificado'
        origins[origin]=origins.get(origin,0)+1
    conflicts=[];unlinked=[]
    for r in solutions:
        need=bmap.get(r.get('necesidad_id'))
        lienzo=cmap.get(r.get('lienzo_id'))
        n=str((need or {}).get('diagnostico_origen') or '').strip()
        c=str((lienzo or {}).get('diagnostico_origen') or '').strip()
        if n and c and n!=c:
            conflicts.append({'solucion_id':r['id'],'codigo':r['codigo'],'origen_necesidad':n,'origen_lienzo':c})
        if not need and not lienzo:
            unlinked.append({'solucion_id':r['id'],'codigo':r['codigo']})
    return {'necesidades_por_origen':dict(sorted(origins.items())),
            'lienzos_por_origen':{o:sum(str(c.get('diagnostico_origen') or '').strip()==o for c in canvases)
              for o in sorted({str(c.get('diagnostico_origen') or '').strip() for c in canvases})},
            'soluciones_sin_necesidad_ni_lienzo':unlinked,
            'soluciones_con_origenes_conflictivos':conflicts,
            'total_necesidades':len(benefits),'total_lienzos':len(canvases),'total_soluciones':len(solutions)}
