"""V0.39.21: capa de rutas CENS, consultas derivadas sin recapturar datos de otros módulos.

La ruta y los estados son una adaptación CENS. No son un nuevo sistema de aprobación PMI.
"""
from __future__ import annotations
import json
from .storage import transaction

ROUTE_TYPES=('Pilotada','Gradual','Simplificada')
ROUTE_STAGES=(('preparacion','Preparación y plan'),('formacion','Comunicación y formación'),
              ('piloto','Prueba piloto'),('soporte','Soporte y monitoreo inicial'),
              ('verificacion','Verificación de transición'),('autorizacion','Autorización a operación'))

def route(sid,path=None):
 from . import step5 as s
 return s._row('SELECT * FROM p5_routes WHERE service_id=?',(sid,),path)

def save_route(sid,data,path=None,actor='Equipo PMO'):
 """Guardar estrategia por servicio, sin alterar aprobaciones, plan o autorización."""
 from . import step5 as s
 sr=s.service(sid,path)
 if not sr:raise s.ValidationError('Primero importa el servicio aprobado desde Paso 04.')
 a=s.adoption(sid,path)
 already_authorized=bool(a and a['authorized_at'])
 old=route(sid,path)
 if already_authorized and old:
  raise s.ValidationError('La clasificación documental de la ruta está congelada después de su registro retrospectivo.')
 retrospective=int(already_authorized)
 reconstruction_note=s._text(data.get('reconstruction_note'))
 if already_authorized and (not data.get('retrospective_confirm') or not reconstruction_note):
  raise s.ValidationError('Para un servicio ya autorizado, confirma la reconstrucción retrospectiva y aporta su fuente documental.')
 kind=s._required(data.get('route_type'),'ruta de incorporación')
 if kind not in ROUTE_TYPES:raise s.ValidationError('Ruta de incorporación no reconocida.')
 fields=('rationale','rollout','owner','client_groups','support_notes')
 vals={k:s._text(data.get(k,'')) for k in fields}
 if not vals['rationale']:raise s.ValidationError('Justifica la elección de ruta para este servicio.')
 if old and old['route_type']==kind and all(old[k]==v for k,v in vals.items()):return sid
 with transaction(path) as c:
  c.execute('''INSERT INTO p5_routes(service_id,route_type,rationale,rollout,owner,client_groups,support_notes,retrospective,reconstruction_note,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(service_id) DO UPDATE SET
    route_type=excluded.route_type,rationale=excluded.rationale,rollout=excluded.rollout,
    owner=excluded.owner,client_groups=excluded.client_groups,support_notes=excluded.support_notes,retrospective=excluded.retrospective,
    reconstruction_note=excluded.reconstruction_note,updated_at=excluded.updated_at''',
    (sid,kind,vals['rationale'],vals['rollout'],vals['owner'],vals['client_groups'],vals['support_notes'],retrospective,reconstruction_note,s.now()))
  s._audit(c,'route',sid,'updated' if old else 'created',actor,
         {'previous':dict(old) if old else None,'route_type':kind,'rationale':vals['rationale'],'retrospective':bool(retrospective),'reconstruction_note':reconstruction_note})
 return sid

def route_summary(sid,path=None):
 """Lee exclusivamente registros persistentes; un avance no constituye aprobación.

 La cobertura declarada en Paso 05 no prueba personas únicas sin identificación individual.
 """
 from . import step5 as s
 sr=s.service(sid,path)
 if not sr:raise s.ValidationError('Servicio inexistente en Paso 05.')
 cfg=route(sid,path);p=s.plan(sid,path);a=s.adoption(sid,path)
 acts=[x for x in s.activities(path) if x['service_id']==sid]
 ps=[x for x in s.pilots(path) if x['service_id']==sid]
 inc=[x for x in s.issues(path) if x['service_id']==sid]
 checks=json.loads(a['checks_json']) if a else {}
 r=s.readiness(sid,path)
 stages=[]
 def add(key,status,detail,source,notes=''):
  stages.append({'key':key,'name':dict(ROUTE_STAGES)[key], 'status':status,
                 'detail':detail,'source':source,'notes':notes})
 if p and p['approved_at']:
  add('preparacion','Completa','Plan aprobado por '+p['approved_by'],'Plan de incorporación',
      'Los hitos pueden tener fechas futuras: el plan aprobado no equivale a hitos ejecutados.')
 elif p and (p['owner'] or p['strategy'] or p['milestones_json']!='[]'):
  add('preparacion','Registrada','Plan sin aprobación formal','Plan de incorporación')
 else:add('preparacion','Pendiente','Falta completar el plan','Plan de incorporación')
 done=[x for x in acts if x['status']=='Realizada']
 trained=[x for x in done if x['kind']=='Formación']
 communicated=[x for x in done if x['kind']=='Comunicación']
 documented=[x for x in done if x['evidence']]
 if trained and communicated and len(documented)==len(done): fstatus='Con evidencia'
 elif acts:fstatus='Registrada'
 else:fstatus='Pendiente'
 add('formacion',fstatus,
     f'{len(done)}/{len(acts)} actividades realizadas · {len(documented)} con evidencia · {len(trained)} formaciones · {len(communicated)} comunicaciones',
     'Comunicación y formación','Los asistentes declarados no acreditan personas únicas sin un identificador verificable.')
 finished=[x for x in ps if x['status'] in ('Validado','Completado')]
 proved=[x for x in finished if x['criteria'] and x['results'] and x['evidence']]
 pilot_na=checks.get('piloto')=='na' and bool(a and a['exemption_reason'])
 if pilot_na: pilotstatus='No aplica justificado'
 elif proved: pilotstatus='Con evidencia'
 elif ps: pilotstatus='Registrada'
 else: pilotstatus='Pendiente'
 add('piloto',pilotstatus,
     ('No aplica con justificación registrada' if pilot_na else f'{len(finished)}/{len(ps)} pilotos terminados · {len(proved)} con criterios, resultados y evidencia'),
     'Pilotos y soporte','Un piloto marcado Validado sin evidencia individual continúa como registrado.')
 support_keys=('equipo','documentos','soporte')
 support_n=sum(checks.get(k)=='cumple' for k in support_keys)
 issue_n=sum(x['status'] not in ('Resuelta','Descartada') for x in inc)
 supportstate='Declarada' if support_n==3 and a and a['evidence'] else 'Registrada' if support_n else 'Pendiente'
 add('soporte',supportstate,f'{support_n}/3 controles de soporte declarados cumplidos · {issue_n} incidencias abiertas',
     'Pilotos y soporte / Adopción y transición',
     'La evidencia general no demuestra por sí sola cada condición de soporte.')
 control_done=sum(checks.get(k)=='cumple' for k,_ in s.CHECKS)
 control_na=sum(checks.get(k)=='na' for k,_ in s.CHECKS)
 add('verificacion','Lista para autorizar' if r['eligible'] else 'Pendiente',
     f'{control_done}/7 controles en Cumple · {control_na} No aplica · '+('Sin bloqueos formales' if r['eligible'] else '; '.join(r['blockers'][:3])),
     'Adopción y transición',
     'La elegibilidad usa estados declarados y evidencia general; el autorizador debe verificar los soportes.')
 add('autorizacion','Autorizada' if r['authorized'] and r['eligible'] else 'Bloqueada' if r['authorized'] else 'Pendiente',
     f'Autorizada por {a["authorized_by"]} el {a["authorized_at"]}' if r['authorized'] else 'Falta decisión expresa de autorización',
     'Adopción y transición','La transferencia al catálogo del Paso 06 es una acción posterior y separada.')
 return {'service':sr,'route':cfg,'stages':stages,'readiness':r,
         'activities':len(acts),'pilots':len(ps),'issues_open':issue_n,
         'milestones':json.loads(p['milestones_json']) if p else [],
         'activity_evidence':len(documented),'pilot_evidence':len(proved),
         'stages_with_progress':sum(x['status']!='Pendiente' for x in stages),
         'training_declared':(a['trained_people'],a['target_people']) if a else (None,None),
         'adoption_declared':(a['active_clients'],a['enabled_clients']) if a else (None,None)}
