"""Motor de alertas V0.39.23 · ejecución puntual para Programador de tareas.

No es un servicio residente ni crea cronogramas en Windows. Requiere ejecutar el
BAT con frecuencia definida por el administrador. Credenciales SMTP solo por
variables de entorno, nunca en SQLite, tickets ni logs.
"""
from __future__ import annotations
import argparse
import json
from .storage import initialize as init_base
from . import step6


def main(argv=None):
    parser=argparse.ArgumentParser(description='Escaneo de alertas ANS e intento de envío SMTP si se configuró.')
    parser.add_argument('--no-email',action='store_true',help='Generar eventos internos sin intentar correos.')
    args=parser.parse_args(argv)
    init_base();step6.initialize()
    summary=step6.scan_sla_alerts()
    if not args.no_email:summary['smtp']=step6.dispatch_sla_emails()
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
