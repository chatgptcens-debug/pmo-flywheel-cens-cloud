"""Exportación auditable de resultados del Paso 2, sin dependencia de Streamlit."""
from __future__ import annotations
import io


def results_xlsx(report):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill
    wb=Workbook();ws=wb.active;ws.title='Resumen'
    r=report['resultados']
    for row in [['PMO FLYWHEEL CENS · PASO 2'],['Fecha',report['fecha']],['Método',report['modelo']],['Versión de matriz',report.get('matrix_version_id') or r.get('matrix_version_id') or 'Matriz histórica no versionada'],['Fuente',report['origen']],['Participantes',r['participants']],['Grupos',len(r['groups'])],['Top 5 (%)',r['top5']]]:ws.append(row)
    for name,head,records in [
        ('Resultados de valor',['ID','Resultado','Porcentaje'],[[x['id'],x['name'],x['score']] for x in r['outcomes']]),
        ('Ranking servicios',['ID','Servicio','Porcentaje','Acumulado'],[[x['id'],x['name'],x['score'],x['cumulative']] for x in r['services']]),
        ('Pesos',['Grupo','Participantes','Peso'],[[g,v['participants'],v['weight']] for g,v in r['groups'].items()]),
        ('Clientes',['ID','Código','Nombre','Grupo','P1','P2','P3','P4','P5'],[[x['id'],x['codigo'],x['name'],x['group'],*x['priorities']] for x in report['respuestas']]),
        ('Correspondencias',['Outcome ID','Service ID','Strength'],[[int(oid),int(sid),stren] for oid,m in report['matriz'].items() for sid,stren in m.items()]),
        ('Aportes por servicio',['Servicio ID','Resultado ID','Resultado esperado','Peso resultado %','Intensidad','Aporte al servicio %','Aporte al ranking pp'],
         [[int(sid),x['outcome_id'],x['outcome'],x['result_weight_pct'],x['intensity'],x['service_share_pct'],x['global_share_pct']]
         for sid,links in r.get('contributions',{}).items() for x in links]),
    ]:
        sheet=wb.create_sheet(name);sheet.append(head)
        for row in records:sheet.append(row)
        sheet.freeze_panes='A2'
        for col in sheet[1]:col.fill=PatternFill('solid',fgColor='10374B');col.font=Font(color='FFFFFF',bold=True)
        for col in range(1,sheet.max_column+1):
            from openpyxl.utils import get_column_letter
            sheet.column_dimensions[get_column_letter(col)].width=58 if col==2 else 20
        sheet.auto_filter.ref=sheet.dimensions
    buff=io.BytesIO();wb.save(buff);return buff.getvalue()

