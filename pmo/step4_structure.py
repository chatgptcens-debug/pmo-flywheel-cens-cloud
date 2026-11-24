"""Datos estructurados no destructivos para fichas Paso 04 V0.39.16.

El texto heredado permanece intacto para trazabilidad; las filas de captura
permiten continuar un diseño sin aprobar ni simular hechos de operación.
"""
from __future__ import annotations
import re

COLUMNAS = {
    "entregables_items": ("Entregable", "Descripción", "Criterio de aceptación"),
    "proceso_actividades": ("Orden", "Actividad", "Responsable", "Resultado"),
    "riesgos_registro": ("Riesgo", "Categoría", "Tratamiento", "Responsable", "Estado"),
    "hitos_registro": ("Hito", "Fecha objetivo", "Responsable", "Dependencia", "Estado"),
    "raci_registro": ("Actividad", "Responsable (R)", "Aprobador (A)", "Consultado (C)", "Informado (I)"),
}
ESTADOS_HITOS=("Pendiente", "En ejecución", "Bloqueado", "Completado", "Cancelado")
ESTADOS_RIESGOS=("Identificado", "En tratamiento", "Mitigado", "Cerrado")

def empty_rows(field):
    return []

def propose_rows(details: dict, field: str) -> list[dict]:
    """Sugiere filas editables SIN inventar aceptación, responsable ni avance.
    La sugerencia solo se guarda si el usuario decide guardar la ficha.
    """
    explicit=details.get(field)
    if isinstance(explicit,list) and explicit: return [dict(row) for row in explicit if isinstance(row,dict)]
    if field=='hitos_registro':
        return [{"Hito":str(v),"Fecha objetivo":"", "Responsable":"", "Dependencia":"", "Estado":"Pendiente"}
                for v in details.get('hitos_lista',[]) if str(v).strip()]
    if field=='entregables_items':
        candidate=str(details.get('entregables') or '')
        rows=[]
        for line in candidate.splitlines():
            line=re.sub(r'^\s*[•*\-]\s*','',line).strip()
            if not line or re.fullmatch(r'Agregar(?: Agregar)*',line,re.I): continue
            rows.append({'Entregable':line,'Descripción':'','Criterio de aceptación':''})
        return rows[:60]
    if field=='raci_registro':
        matrix=details.get('raci_matriz_propuesta') or []
        result=[]
        for item in matrix:
            if not isinstance(item,dict):continue
            assignment={k:[] for k in ('R','A','C','I')}
            for role,code in item.items():
                if role.casefold()=='actividad':continue
                for letter in str(code or '').upper():
                    if letter in assignment: assignment[letter].append(role)
            result.append({'Actividad':str(item.get('Actividad') or item.get('actividad') or ''),
                'Responsable (R)':', '.join(assignment['R']),
                'Aprobador (A)':', '.join(assignment['A']),
                'Consultado (C)':', '.join(assignment['C']),
                'Informado (I)':', '.join(assignment['I'])})
        return result
    if field=='riesgos_registro':
        existing=details.get('riesgos_matriz_propuesta')
        if isinstance(existing,list) and existing:
            return [{'Riesgo':str(item.get('riesgo') or item.get('Riesgo') or ''),
                     'Categoría':str(item.get('categoria') or item.get('Categoría') or ''),
                     'Tratamiento':str(item.get('tratamiento') or item.get('Tratamiento') or ''),
                     'Responsable':'', 'Estado':'Identificado'} for item in existing if isinstance(item,dict)]
    return []

def clean_rows(field,rows):
    columns=COLUMNAS[field]
    clean=[]
    for row in rows:
        if not isinstance(row,dict): continue
        data={name:str(row.get(name,'') or '').strip() for name in columns}
        main=columns[0] if field!='proceso_actividades' else 'Actividad'
        if data[main]:clean.append(data)
    return clean

def effective_field(details,field):
    """Lee registros estructurados; si están vacíos, vuelve al texto histórico."""
    items=details.get(field)
    return items if isinstance(items,list) and items else None
