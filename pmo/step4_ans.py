"""Definición y validación de ANS del Paso 04 (adaptación CENS).

No gestiona tickets ni mide tiempos operativos. Los acuerdos validados se
conservan como snapshots inmutables dentro del expediente JSON del servicio.
La evidencia adjunta (máx. 3 MiB) se mantiene en el mismo expediente para
que el respaldo JSON del Paso 04 siga siendo autocontenido.
"""
from __future__ import annotations
import base64
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import PurePath
import re

ESTADOS = ('Borrador', 'En revisión', 'Validado')
UNIDADES = ('Por definir', 'Horas hábiles', 'Días hábiles', 'Horas calendario', 'Días calendario', 'Semanas')
MEDIOS = ('Por definir', 'Acta firmada', 'Correo institucional', 'Registro de conformidad', 'Documento aprobado', 'Otro')
MAX_EVIDENCIA_BYTES = 3 * 1024 * 1024
# Únicamente los campos sustantivos forman parte del acuerdo. Los anexos se
# referencian por hash y no se duplican dentro de cada snapshot.
CAMPOS_ACUERDO = (
    'ans_respuesta_valor','ans_respuesta_unidad','ans_entrega_valor','ans_entrega_unidad',
    'ans_horario','ans_inicio_computo','ans_fin_computo','sla_calidad','sla_aceptacion',
    'ans_medio_aceptacion','ans_responsable_escalamiento','sla_escalamiento',
    'periodicidad_revision','ans_responsable_revision','sla_seguimiento',
    'ans_cliente_id','validacion_cliente','validacion_fecha','validacion_evidencia',
    'ans_nivel_servicio','ans_condiciones_nivel','ans_motivo_fecha',
)

class ANSError(ValueError):
    pass

def _text(value):
    return str(value or '').strip()

def _serializable(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def extract_snapshot(details:dict) -> dict:
    snapshot={field:_text(details.get(field)) for field in CAMPOS_ACUERDO}
    attachment=details.get('ans_archivo')
    if isinstance(attachment,dict):
        snapshot['evidencia_sha256']=_text(attachment.get('sha256'))
        snapshot['evidencia_nombre']=_text(attachment.get('nombre'))
    else:
        snapshot['evidencia_sha256']=''
        snapshot['evidencia_nombre']=''
    return snapshot

def digest(snapshot:dict)->str:
    return sha256(_serializable(snapshot).encode('utf-8')).hexdigest()

def hydrate_legacy(details:dict)->dict:
    """Copia no destructiva: los nueve campos antiguos se conservan literales.

    Los valores antiguos sin estructura nunca se interpretan como ANS
    cuantitativos ni como evidencias de una validación.
    """
    d=dict(details)
    d.setdefault('ans_estado','Borrador')
    d.setdefault('ans_versiones',[])
    if not isinstance(d['ans_versiones'],list):d['ans_versiones']=[]
    return d

def store_attachment(name:str,data:bytes,mime:str='application/octet-stream')->dict:
    name=PurePath(str(name).replace('\\','/')).name
    extension=name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if extension not in {'pdf','png','jpg','jpeg','docx','xlsx'}:
        raise ANSError('Solo se admiten PDF, PNG, JPG, DOCX y XLSX como evidencia.')
    if not name or not isinstance(data,bytes) or not data:
        raise ANSError('La evidencia adjunta está vacía.')
    if len(data)>MAX_EVIDENCIA_BYTES:
        raise ANSError('La evidencia supera el máximo de 3 MiB.')
    return {'nombre':name,'mime':str(mime),'sha256':sha256(data).hexdigest(),
            'bytes':len(data),'base64':base64.b64encode(data).decode('ascii')}

def attachment_bytes(entry:dict)->bytes:
    raw=base64.b64decode(entry['base64'],validate=True)
    if sha256(raw).hexdigest()!=entry['sha256']:
        raise ANSError('La evidencia adjunta no coincide con su huella SHA-256.')
    return raw

def _positive_decimal(value):
    s=_text(value).replace(',','.')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?',s):return False
    try:return 0<float(s)<=100000
    except (ValueError,OverflowError):return False

def validate_agreement(d:dict)->None:
    """Se aplica únicamente al acto explícito de registrar validación."""
    required=[]
    for field,label in (
        ('ans_horario','Horario y calendario aplicable'),
        ('ans_inicio_computo','Evento de inicio del cómputo'),
        ('ans_fin_computo','Evento de finalización del cómputo'),
        ('sla_calidad','Estándares verificables de calidad'),
        ('sla_aceptacion','Criterios de aceptación'),
        ('ans_responsable_escalamiento','Responsable de escalamiento'),
        ('sla_escalamiento','Procedimiento de escalamiento'),
        ('ans_responsable_revision','Responsable de revisión'),
        ('sla_seguimiento','Mecanismo de seguimiento'),
        ('validacion_cliente','Cliente que valida'),
    ):
        if not _text(d.get(field)):required.append(label)
    for field,label in (('ans_respuesta_valor','respuesta'),('ans_entrega_valor','entrega')):
        if not _positive_decimal(d.get(field)):
            required.append(f'Tiempo objetivo numérico de {label} mayor que cero')
    for field,label in (('ans_respuesta_unidad','respuesta'),('ans_entrega_unidad','entrega')):
        if _text(d.get(field)) not in UNIDADES[1:]:required.append(f'Unidad del tiempo de {label}')
    if _text(d.get('ans_medio_aceptacion')) in ('','Por definir'):
        required.append('Medio de aceptación')
    if _text(d.get('periodicidad_revision')) in ('','Por definir'):
        required.append('Periodicidad de revisión')
    if not (_text(d.get('validacion_evidencia')) or isinstance(d.get('ans_archivo'),dict)):
        required.append('Evidencia documental o enlace de validación')
    if _text(d.get('ans_nivel_servicio'))=='Diferenciado' and not _text(d.get('ans_condiciones_nivel')):
        required.append('Condiciones del nivel de servicio diferenciado')
    if required:
        raise ANSError('Antes de validar el ANS completa: '+ '; '.join(required)+'.')

def register_validation(details:dict,*,actor:str='Equipo PMO',override_date=None,motive:str='')->dict:
    """Congela un acuerdo validado solo por acción explícita del usuario."""
    d=hydrate_legacy(details)
    validate_agreement(d)
    if override_date is None:
        validation_date=date.today()
    elif isinstance(override_date,date):
        validation_date=override_date
    else:
        try:validation_date=date.fromisoformat(str(override_date))
        except ValueError as exc:raise ANSError('Fecha de validación inválida.') from exc
    if validation_date!=date.today() and not _text(motive):
        raise ANSError('La fecha distinta de hoy requiere justificación trazable.')
    attachment=d.get('ans_archivo')
    if isinstance(attachment,dict):
        attachment_bytes(attachment)  # Comprueba huella y contenido antes de validar.
        historical=d.get('ans_evidencias_historicas')
        if not isinstance(historical,list):historical=[]
        if not any(isinstance(x,dict) and x.get('sha256')==attachment.get('sha256') for x in historical):
            historical=[*historical,attachment]
        d['ans_evidencias_historicas']=historical
    d['validacion_fecha']=validation_date.isoformat()
    d['ans_motivo_fecha']=_text(motive) if validation_date!=date.today() else ''
    snapshot=extract_snapshot(d)
    previous=d.get('ans_versiones',[])
    # Revalidación idéntica no crea una versión duplicada.
    if previous and previous[-1].get('sha256')==digest(snapshot):
        d['ans_estado']='Validado'
        return d
    next_num=max([int(x.get('numero',0)) for x in previous if isinstance(x,dict)] or [0])+1
    version={'numero':next_num,'validado_en':datetime.now(timezone.utc).isoformat(),
             'actor':_text(actor) or 'Equipo PMO','fecha_acuerdo':d['validacion_fecha'],
             'sha256':digest(snapshot),'contenido':snapshot}
    d['ans_versiones']=[*previous,version]
    d['ans_estado']='Validado'
    return d

def enforce_snapshot_integrity(details:dict)->dict:
    """Cualquier edición posterior reabre revisión sin borrar el acuerdo firmado."""
    d=hydrate_legacy(details)
    if d.get('ans_estado')!='Validado':return d
    versions=d.get('ans_versiones',[])
    if not versions or digest(extract_snapshot(d))!=versions[-1].get('sha256'):
        d['ans_estado']='En revisión'
    return d

def legacy_time_string(number,unit,start,end)->str:
    return f"{_text(number)} {_text(unit)} · inicio: {_text(start)} · finalización: {_text(end)}"


def historical_attachment(details:dict,sha:str)->dict|None:
    for row in details.get('ans_evidencias_historicas',[]):
        if isinstance(row,dict) and row.get('sha256')==sha:
            attachment_bytes(row)
            return row
    return None
