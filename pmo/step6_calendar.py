"""Calendarios de ANS CENS (configurables y congelables por solicitud).

No se presume que la jornada de ejemplo sea la política oficial vigente de CENS.
Los feriados nacionales incluyen Ley 51/1983 y, desde 2026, Ley 2578/2026.
El usuario debe confirmar calendario y cierres corporativos antes de activarlo.
"""
from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import json

BOGOTA = ZoneInfo('America/Bogota')
DEFAULT_SLOTS = [['07:30','12:00'], ['13:30','17:00']]
DEFAULT_CONFIG = {'timezone':'America/Bogota','weekdays':[0,1,2,3,4],
                  'slots':DEFAULT_SLOTS,'closures':[],'national_holidays':True,
                  'confirmed':False,'source':''}

def easter(year:int)->date:
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25
    g=(b-f+1)//3;h=(19*a+b-d-g+15)%30;i=c//4;k=c%4
    l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451
    month=(h+l-7*m+114)//31; day=(h+l-7*m+114)%31+1
    return date(year,month,day)

def next_monday(d:date)->date:
    return d+timedelta(days=(7-d.weekday())%7)

def colombian_holidays(year:int)->set[date]:
    e=easter(year)
    fixed={date(year,m,d) for m,d in ((1,1),(5,1),(7,20),(8,7),(12,8),(12,25))}
    shifted={(1,6),(3,19),(6,29),(8,15),(10,12),(11,1),(11,11)}
    if year>=2026:shifted.add((7,9))
    return fixed|{next_monday(date(year,m,d)) for m,d in shifted}|{
       e-timedelta(days=3),e-timedelta(days=2),
       next_monday(e+timedelta(days=39)),next_monday(e+timedelta(days=60)),
       next_monday(e+timedelta(days=68))}

def check_calendar(config:dict,require_confirmed:bool=True)->dict:
    c=dict(config)
    if c.get('timezone')!='America/Bogota':raise ValueError('Se admite el huso horario America/Bogota.')
    if require_confirmed and not c.get('confirmed'):raise ValueError('Confirma el horario y calendario corporativo antes de activar ANS hábiles.')
    if c.get('confirmed') and not str(c.get('source') or '').strip():raise ValueError('Registra la fuente del calendario verificado.')
    weekdays=c.get('weekdays',[])
    if not weekdays or not all(isinstance(v,int) and 0<=v<7 for v in weekdays):raise ValueError('Días laborables inválidos.')
    slots=c.get('slots',[])
    if not slots:raise ValueError('Se requiere al menos una franja laborable.')
    last=None
    for start,end in slots:
        a=time.fromisoformat(start);b=time.fromisoformat(end)
        if b<=a or (last and a<last):raise ValueError('Franjas solapadas o inválidas.')
        last=b
    for d in c.get('closures',[]):date.fromisoformat(d)
    return c

def local_dt(value)->datetime:
    if isinstance(value,datetime):dt=value
    else:dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return dt.replace(tzinfo=timezone.utc).astimezone(BOGOTA) if dt.tzinfo is None else dt.astimezone(BOGOTA)

def sessions(day:date,c:dict):
    if day.weekday() not in c['weekdays'] or day.isoformat() in c.get('closures',[]):return []
    if c.get('national_holidays',True) and day in colombian_holidays(day.year):return []
    return [(datetime.combine(day,time.fromisoformat(a),BOGOTA),datetime.combine(day,time.fromisoformat(b),BOGOTA)) for a,b in c['slots']]

def business_hours(start,end,config:dict)->float:
    c=check_calendar(config,True)
    start=local_dt(start);end=local_dt(end)
    if end<=start:return 0.0
    total=0.0; day=start.date()
    if (end.date()-day).days>3660:raise ValueError('Intervalo demasiado extenso.')
    while day<=end.date():
        for a,b in sessions(day,c):total+=max(0.0,(min(b,end)-max(a,start)).total_seconds())/3600
        day+=timedelta(days=1)
    return round(total,8)

def due_at(start,hours:float,config:dict)->datetime:
    c=check_calendar(config,True)
    if hours<=0:raise ValueError('El plazo debe ser positivo.')
    pointer=local_dt(start);remaining=float(hours)
    for _ in range(3662):
        day=pointer.date()
        for a,b in sessions(day,c):
            current=max(pointer,a)
            if current>=b:continue
            available=(b-current).total_seconds()/3600
            if remaining<=available+1e-10:return (current+timedelta(hours=remaining)).astimezone(timezone.utc)
            remaining-=available;pointer=b
        pointer=datetime.combine(day+timedelta(days=1),time.min,BOGOTA)
    raise ValueError('No se pudo calcular vencimiento; revisa el calendario.')

def snapshot(c):return json.dumps(check_calendar(c,True),ensure_ascii=False,sort_keys=True)
