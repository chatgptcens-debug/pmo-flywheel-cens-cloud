"""Exportador visual PNG/PDF del lienzo del Paso 3 (solo Pillow, sin servicios externos)."""
from __future__ import annotations
import io
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from . import step3 as p

COLORS={'servicios':'#EAF4FB','generadores':'#F1E7FF','aliviadores':'#FFF0E5',
        'ganancias':'#F1E7FF','tareas':'#EAF4FB','dolores':'#FFF0E5'}

def _font(size,bold=False):
    paths=(
       'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
       '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    )
    for path in paths:
        try:return ImageFont.truetype(path,size)
        except OSError:pass
    return ImageFont.load_default()

def _lines(s,font,width,draw,max_lines=4):
    words=str(s).split();out=[];cur=''
    for word in words:
        attempt=(cur+' '+word).strip()
        if draw.textbbox((0,0),attempt,font=font)[2]>width and cur:
            out.append(cur);cur=word
        else:cur=attempt
    if cur:out.append(cur)
    if len(out)>max_lines:return out[:max_lines-1]+[out[max_lines-1][:42]+'…']
    return out

def canvas_image(lienzo:str,path=None):
    """Exporta el mismo modelo de dos piezas de la vista interactiva (mapa cuadrado + perfil circular)."""
    record=p.canvas(lienzo,path)
    if not record:raise p.ValidationError('Lienzo no encontrado.')
    cards=p.cards(lienzo,path);links=p.links(lienzo,path)
    img=Image.new('RGB',(1720,1080),'#F6F8FC');d=ImageDraw.Draw(img)
    f_title=_font(31,True);f_head=_font(21,True);f_label=_font(18,True);f_body=_font(15)
    d.rounded_rectangle((42,26,1678,112),18,fill='#FFFFFF',outline='#DAE4EF',width=2)
    d.text((67,38),'PMO FLYWHEEL CENS · PASO 03',font=f_label,fill='#C94C38')
    d.text((67,67),'Lienzo y conexiones de valor',font=f_title,fill='#172744')
    d.rounded_rectangle((55,134,832,183),14,fill='#FFFFFF',outline='#CAD8E8',width=2)
    d.text((75,150),'Propuesta de valor:',font=f_label,fill='#263957')
    d.text((285,153),str(record['nombre'])[:60],font=f_body,fill='#475F7D')
    d.rounded_rectangle((888,134,1665,183),14,fill='#FFFFFF',outline='#CAD8E8',width=2)
    d.text((907,150),'Cliente / segmento:',font=f_label,fill='#263957')
    d.text((1148,153),str(record['segmento'])[:52],font=f_body,fill='#475F7D')
    left=(79,271,808,1000);right=(913,271,1642,1000)
    lx,ly,rx,ry=left;sx,sy,ex,ey=right
    d.rounded_rectangle((230,207,661,256),13,fill='#EEF2FB',outline='#C6D4E8',width=2)
    d.text((315,220),'Mapa de valor PMO',font=f_head,fill='#182C50')
    d.rounded_rectangle((1113,207,1453,256),13,fill='#EEF2FB',outline='#C6D4E8',width=2)
    d.text((1192,220),'Perfil del cliente',font=f_head,fill='#182C50')
    d.rectangle(left,fill='#FFFFFF',outline='#23314D',width=4)
    cx,cy=lx+364,ly+365
    d.line([(lx,ly),(cx,cy)],fill='#26314A',width=3)
    d.line([(lx,ry),(cx,cy)],fill='#26314A',width=3)
    d.line([(cx,cy),(rx,cy)],fill='#26314A',width=3)
    d.ellipse(right,fill='#FFFFFF',outline='#26314A',width=4)
    ccx,ccy=sx+364,sy+364
    d.line([(sx,ccy),(ccx,ccy)],fill='#26314A',width=3)
    d.line([(ccx,ccy),(sx+580,sy+148)],fill='#26314A',width=3)
    d.line([(ccx,ccy),(sx+580,sy+580)],fill='#26314A',width=3)
    d.rounded_rectangle((cx-40,cy-42,cx+40,cy+40),9,fill='#FFFFFF',outline='#26314A',width=3)
    d.line([(cx,cy-18),(cx,cy+28)],fill='#26314A',width=3)
    d.rectangle((cx-25,cy-12,cx+25,cy+24),outline='#26314A',width=3)
    d.ellipse((ccx-34,ccy-34,ccx+34,ccy+34),fill='#FFFFFF',outline='#26314A',width=3)
    d.ellipse((ccx-12,ccy-19,ccx+12,ccy+4),outline='#26314A',width=2)
    d.arc((ccx-24,ccy-4,ccx+24,ccy+29),0,180,fill='#26314A',width=2)
    d.line([(830,635),(866,635)],fill='#354C6B',width=3)
    d.line([(858,625),(869,635),(858,645)],fill='#354C6B',width=3)
    boxes={
      'servicios':(lx+22,ly+242,lx+292,ly+652),
      'generadores':(lx+391,ly+95,lx+701,ly+335),
      'aliviadores':(lx+391,ly+425,lx+701,ly+675),
      'ganancias':(sx+105,sy+105,sx+375,sy+326),
      'dolores':(sx+105,sy+432,sx+375,sy+643),
      'tareas':(sx+472,sy+242,sx+648,sy+527),
    }
    by_zone={k:[] for k in p.ZONES}
    for card in cards:by_zone[card['zona']].append(card)
    for zone,box in boxes.items():
        x1,y1,x2,y2=box
        d.text((x1,y1),p.ZONES[zone],font=f_label,fill='#223353')
        y=y1+34
        for card in by_zone[zone]:
            text=_lines(card['titulo'],f_body,x2-x1-34,d,3)
            h=max(43,len(text)*22+12)
            if y+h>y2-13:break
            d.rounded_rectangle((x1,y,x2,y+h),12,fill=COLORS[zone],outline='#D8E2EF',width=1)
            for i,line in enumerate(text):d.text((x1+10,y+9+i*22),line,font=f_body,fill='#172744')
            y+=h+9
        n=len(by_zone[zone])
        # Las tarjetas adicionales se consultan en la vista interactiva y JSON.
        if n>4:d.text((x1,y2-13),f'{n} tarjetas en esta zona · consultar lienzo interactivo',font=_font(10),fill='#65718C')
    d.rounded_rectangle((65,1021,1655,1060),10,fill='#EEF3FB')
    d.text((89,1031),f'{len(cards)} tarjetas  ·  {len(links)} relaciones persistidas  ·  Borrador de diseño, no validación institucional',font=f_body,fill='#4D6180')
    return img

def export_canvas(lienzo:str,kind:str='PNG',path=None)->bytes:
    img=canvas_image(lienzo,path)
    output=io.BytesIO()
    kind=kind.upper()
    if kind=='PNG':img.save(output,format='PNG')
    elif kind=='PDF':img.convert('RGB').save(output,format='PDF',resolution=144.0)
    else:raise ValueError('Formato no soportado')
    return output.getvalue()

def assessment_radar_svg(current:dict,previous:dict|None=None)->bytes:
    """Radar puro SVG de cinco ejes. Valores parciales no se representan como 0 definitivo."""
    import math,html
    cx=320;cy=236;r=135
    labels=['Síntesis','Problemas → soluciones','Definición de valor','Evolución','Medición y mejora']
    def point(index,value):
        ang=-math.pi/2+index*math.pi*2/5
        return (cx+math.cos(ang)*r*value/5,cy+math.sin(ang)*r*value/5)
    def poly(values):return ' '.join(f'{x:.1f},{y:.1f}' for x,y in (point(i,v) for i,v in enumerate(values)))
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="690" height="490" viewBox="0 0 690 490">',
         '<rect width="690" height="490" rx="18" fill="#FFFFFF"/>',
         '<text x="24" y="36" fill="#302B56" font-size="19" font-family="Arial" font-weight="bold">Evaluación metodológica PMI · 5 dimensiones</text>']
    for level in range(1,6):
        svg.append(f'<polygon points="{poly([level]*5)}" fill="none" stroke="#DEE5ED" stroke-width="1"/>')
    for i,label in enumerate(labels):
        x,y=point(i,5);svg.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#DEE5ED"/>')
        x,y=point(i,6.15);anchor='middle' if abs(x-cx)<9 else 'start' if x>cx else 'end'
        svg.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="#65718C" font-family="Arial" font-size="13" text-anchor="{anchor}">{html.escape(label)}</text>')
    values=[d['promedio'] or 0 for d in current['dimensiones']]
    if previous:
        vals=[d['promedio'] or 0 for d in previous['dimensiones']]
        svg.append(f'<polygon points="{poly(vals)}" fill="none" stroke="#CE7C42" stroke-width="3" stroke-dasharray="6 4"/>')
    svg.append(f'<polygon points="{poly(values)}" fill="#67618F33" stroke="#443D6C" stroke-width="3"/>')
    svg.append('<rect x="40" y="446" width="11" height="11" rx="2" fill="#443D6C"/>')
    svg.append('<text x="60" y="457" font-family="Arial" font-size="12" fill="#232747">Evaluación seleccionada</text>')
    if previous:
        svg.append('<rect x="266" y="446" width="11" height="11" rx="2" fill="#CE7C42"/>')
        svg.append('<text x="286" y="457" font-family="Arial" font-size="12" fill="#232747">Evaluación comparada</text>')
    if current['respondidas']<25:svg.append('<text x="470" y="457" font-family="Arial" font-size="11" fill="#B56B2F">Datos parciales</text>')
    svg.append('</svg>')
    return ''.join(svg).encode('utf-8')

def assessment_pdf(key:str,path=None)->bytes:
    """Informe PDF multipágina generado sin dependencia de servicio en línea."""
    overview=p.assessment_summary(key,path)
    answers={x['numero']:x for x in p.assessment_answers(key,path)}
    all_pages=[]
    def page():
        image=Image.new('RGB',(1240,1754),'#FFFFFF');draw=ImageDraw.Draw(image)
        draw.rectangle((0,0,1240,26),fill='#302B56')
        return image,draw
    img,d=page();y=65
    title=_font(30,True);heading=_font(21,True);body=_font(17)
    d.text((65,y),'PMO FLYWHEEL CENS · PASO 3',font=title,fill='#302B56');y+=62
    d.text((65,y),'Evaluación metodológica PMI · Propuesta de valor',font=heading,fill='#232747');y+=45
    d.text((65,y),f"Versión {overview['version']} · {overview['estado']} · {overview['responsable']}",font=body,fill='#65718C');y+=36
    d.text((65,y),f"Respuestas {overview['respondidas']}/25 · Puntaje {overview['puntaje'] if overview['puntaje'] is not None else 'Sin concluir'} · {overview['clasificacion'] or 'No clasificado'}",font=body,fill='#232747');y+=55
    d.text((65,y),'Dimensiones y observaciones',font=heading,fill='#302B56');y+=45
    for i,(dim,questions) in enumerate(p.DIMENSIONS):
        if y>1450:
            all_pages.append(img);img,d=page();y=65
        d.text((65,y),f'{i+1}. {dim}',font=heading,fill='#302B56');y+=32
        dim_score=overview['dimensiones'][i]
        d.text((77,y),f"{dim_score['respondidas']}/5 preguntas · {dim_score['subtotal']}/25 puntos",font=body,fill='#65718C');y+=34
        for j,question in enumerate(questions):
            num=i*5+j+1;ans=answers.get(num)
            text=f"{num:02d} · {ans['valor'] if ans else '—'}/5 · {question}"
            for line in _lines(text,body,1080,d,4):
                if y>1630:all_pages.append(img);img,d=page();y=65
                d.text((78,y),line,font=body,fill='#232747');y+=25
            if ans and (ans['observacion'] or ans['evidencia']):
                extra='Observación: '+str(ans['observacion'] or '—')+' | Evidencia: '+str(ans['evidencia'] or '—')
                for line in _lines(extra,_font(14),1090,d,3):
                    if y>1640:all_pages.append(img);img,d=page();y=65
                    d.text((87,y),line,font=_font(14),fill='#65718C');y+=21
            y+=13
        y+=20
    all_pages.append(img)
    output=io.BytesIO();all_pages[0].save(output,format='PDF',save_all=True,append_images=all_pages[1:],resolution=150)
    return output.getvalue()

def solutions_pdf(path=None)->bytes:
    """Reporte de selección de soluciones, con estados reales (no metas simuladas)."""
    solutions=p.solutions(path)
    img=Image.new('RGB',(1240,1754),'#FFFFFF');d=ImageDraw.Draw(img)
    d.rectangle((0,0,1240,24),fill='#302B56')
    d.text((56,67),'PMO FLYWHEEL CENS · PASO 3',font=_font(30,True),fill='#302B56')
    d.text((56,125),'Reporte de soluciones y propuesta de valor',font=_font(23,True),fill='#232747')
    d.text((56,173),f'Soluciones registradas: {len(solutions)} · Aprobadas: {sum(x["estado"]=="Aprobada" for x in solutions)}',
           font=_font(18),fill='#65718C')
    y=250;pages=[]
    for item in solutions:
        if y>1550:pages.append(img);img=Image.new('RGB',(1240,1754),'#FFFFFF');d=ImageDraw.Draw(img);y=65
        d.rounded_rectangle((50,y,1190,y+140),12,fill='#F4F6FA',outline='#E1E5EC')
        d.text((70,y+10),f"{item['codigo']} · {item['nombre'][:55]}",font=_font(19,True),fill='#302B56')
        d.text((70,y+47),f"{item['decision']} · {item['estado']} · {item['horizonte']}",font=_font(16),fill='#232747')
        benefit=item['beneficio'] or 'Beneficio aún no formulado'
        d.text((70,y+77),_lines(benefit,_font(16),1070,d,1)[0],font=_font(16),fill='#65718C')
        d.text((70,y+108),f"Validación: {item['validador'] or 'Pendiente'} · Viabilidad CENS: {p.feasibility(item) if p.feasibility(item) is not None else 'No evaluada'}",font=_font(15),fill='#65718C')
        y+=154
    pages.append(img);output=io.BytesIO()
    pages[0].save(output,format='PDF',save_all=True,append_images=pages[1:],resolution=150)
    return output.getvalue()
