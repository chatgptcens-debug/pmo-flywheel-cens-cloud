"""Motor PMO FLYWHEEL CENS Paso 2 / V5.

Código reutilizable y verificable. Reproduce el comportamiento numérico
observado en los ensayos PMOGA bajo el modelo aditivo declarado.
No es una biblioteca oficial ni certificada por PMOGA o PMI.

No exige numpy para la operación cotidiana; solamente para reconstruir
la matriz original a partir de 30 experimentos (reconstruir_matriz.py).
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RESULTADOS = 30
SERVICIOS = 26
PUNTOS = [5, 4, 3, 2, 1]


def cargar_matriz(ruta: str | Path) -> tuple[list[list[int]], dict]:
    """Lee JSON de la V5 (30x26) o CSV Outcome ID,Service ID,Strength."""
    ruta = Path(ruta)
    if ruta.suffix.lower() == '.json':
        obj = json.loads(ruta.read_text(encoding='utf-8-sig'))
        matriz = obj.get('matrix')
        metadatos = {k: v for k, v in obj.items() if k not in {'matrix', 'outcomes', 'services', 'pmiDocumented'}}
    elif ruta.suffix.lower() == '.csv':
        matriz = [[0 for _ in range(SERVICIOS)] for _ in range(RESULTADOS)]
        with ruta.open(encoding='utf-8-sig', newline='') as f:
            rdr = csv.DictReader(f)
            if not {'Outcome ID', 'Service ID', 'Strength'}.issubset(rdr.fieldnames or []):
                raise ValueError('CSV requiere Outcome ID, Service ID y Strength')
            vistos = set()
            for n, row in enumerate(rdr, start=2):
                i, j = int(row['Outcome ID']), int(row['Service ID'])
                v = int(row['Strength'])
                if not 1 <= i <= 30 or not 1 <= j <= 26:
                    raise ValueError(f'Fila {n}: IDs fuera de rango')
                if (i, j) in vistos:
                    raise ValueError(f'Fila {n}: cruce duplicado ({i},{j})')
                vistos.add((i, j))
                matriz[i - 1][j - 1] = v
        metadatos = {'fuente': str(ruta), 'version': 'CSV importada'}
    else:
        raise ValueError('La matriz debe ser un JSON o CSV')
    validar_matriz(matriz)
    return matriz, metadatos


def validar_matriz(matriz: list[list[int]]) -> None:
    if not isinstance(matriz, list) or len(matriz) != RESULTADOS:
        raise ValueError('La matriz debe tener 30 filas')
    for i, fila in enumerate(matriz, start=1):
        if not isinstance(fila, list) or len(fila) != SERVICIOS:
            raise ValueError(f'Resultado {i}: se requieren 26 intensidades')
        for j, v in enumerate(fila, start=1):
            if type(v) is not int or not (0 <= v <= 4):
                raise ValueError(f'Intensidad inválida O-{i:02} S-{j:02}: {v}')
    if sum(sum(fila) for fila in matriz) == 0:
        raise ValueError('La matriz no puede contener solo ceros')


def validar_pesos(pesos: dict[str, int], grupos: list[str] | None = None) -> None:
    if not pesos:
        raise ValueError('No se recibieron pesos')
    if grupos is not None and set(pesos) != set(grupos):
        raise ValueError('Los grupos con respuesta y los grupos ponderados deben coincidir exactamente')
    for grupo, peso in pesos.items():
        if type(peso) is not int or peso < 0 or peso > 100:
            raise ValueError(f'El peso de {grupo} debe ser entero 0..100')
    if sum(pesos.values()) != 100:
        raise ValueError(f'Los pesos deben sumar exactamente 100%, no {sum(pesos.values())}%')


def validar_registros(registros: list[dict], pesos: dict[str, int]) -> None:
    if not registros:
        raise ValueError('No hay clientes para evaluar')
    grupos = sorted({r.get('group', '') for r in registros})
    validar_pesos(pesos, grupos)
    for i, registro in enumerate(registros, start=1):
        prioridades = registro.get('priorities')
        if not registro.get('group'):
            raise ValueError(f'Cliente {i}: falta grupo')
        if not isinstance(prioridades, list) or len(prioridades) != 5:
            raise ValueError(f'Cliente {i}: debe indicar exactamente cinco resultados')
        if any(type(p) is not int or p < 1 or p > 30 for p in prioridades):
            raise ValueError(f'Cliente {i}: las prioridades deben ser enteros 1..30')
        if len(set(prioridades)) != 5:
            raise ValueError(f'Cliente {i}: hay resultados repetidos')


def relevancias_de_clientes(registros: list[dict], pesos: dict[str, int]) -> tuple[list[float], dict]:
    """Calcula R[o] = sum_g Wg * (puntos grupo o)/(15*Ng), Wg en 0..1.

    Las 30 relevancias se expresan como proporciones, y suman 1.0.
    Cada grupo tiene peso estratégico, NO proporcional a su tamaño.
    """
    validar_registros(registros, pesos)
    puntos = defaultdict(lambda: [0.0] * RESULTADOS)
    conteos = defaultdict(int)
    for cliente in registros:
        g = cliente['group']
        conteos[g] += 1
        for indice, resultado in enumerate(cliente['priorities']):
            puntos[g][resultado - 1] += PUNTOS[indice]
    relevancias = [0.0] * RESULTADOS
    detalles = {}
    for g, peso in pesos.items():
        n = conteos[g]
        fracciones = [v / (n * 15) for v in puntos[g]]
        detalles[g] = {'clientes': n, 'peso_entero': peso, 'distribucion_30': [100 * x for x in fracciones]}
        for o in range(RESULTADOS):
            relevancias[o] += (peso / 100.0) * fracciones[o]
    total = sum(relevancias)
    if total <= 0:
        raise ValueError('Relevancia total nula')
    relevancias = [x / total for x in relevancias]
    return relevancias, detalles


def relevancias_de_json_pmoga(caso: dict) -> list[float]:
    """Permite reproducir un reporte cuando ya conocemos sus 30 relevancias.

    Las claves ausentes se consideran 0, porque PMOGA omite en JSON los
    resultados que no fueron escogidos por los clientes.
    """
    valores = caso.get('outcomeRelevances', {})
    r = [float(valores.get(str(i), 0)) / 100.0 for i in range(1, RESULTADOS + 1)]
    total = sum(r)
    if abs(total - 1) > 1e-7:
        raise ValueError(f'Las relevancias PMOGA deben sumar 100%; suman {total * 100:.10f}%')
    return [x / total for x in r]


def calcular_servicios(relevancias: list[float], matriz: list[list[int]], metadata: dict | None = None) -> dict:
    """Fórmula: bruto[s] = Σ_o R[o]*M[o,s]; P[s]=100*bruto[s]/Σ_s bruto[s]."""
    validar_matriz(matriz)
    if len(relevancias) != RESULTADOS or any(float(x) < 0 for x in relevancias):
        raise ValueError('Se esperan 30 relevancias no negativas')
    total_r = sum(relevancias)
    if total_r <= 0:
        raise ValueError('Las relevancias no pueden sumar cero')
    r = [float(x) / total_r for x in relevancias]
    bruto = [sum(r[o] * matriz[o][s] for o in range(RESULTADOS)) for s in range(SERVICIOS)]
    denominador = sum(bruto)
    if denominador <= 0:
        raise ValueError('Ningún servicio está relacionado con los resultados priorizados')
    puntuaciones = [100 * x / denominador for x in bruto]
    ranking = sorted(range(1, SERVICIOS + 1), key=lambda sid: (-puntuaciones[sid - 1], sid))
    contribuciones = [
        {
            'service_id': s + 1,
            'numerador': bruto[s],
            'porcentaje': puntuaciones[s],
            'rank': ranking.index(s + 1) + 1,
            'resultados_aportantes': [
                {'outcome_id': o + 1, 'relevancia': r[o] * 100, 'intensidad': matriz[o][s],
                 'contribucion_bruta': r[o] * matriz[o][s]}
                for o in range(RESULTADOS) if r[o] * matriz[o][s] > 0
            ],
        }
        for s in range(SERVICIOS)
    ]
    return {
        'generado_en': datetime.now(timezone.utc).isoformat(),
        'metadatos_matriz': metadata or {},
        'relevancias_30_pct': [x * 100 for x in r],
        'numerador_total_servicios': denominador,
        'servicios_26_pct': puntuaciones,
        'ranking_ids': ranking,
        'top5_pct': sum(sorted(puntuaciones, reverse=True)[:5]),
        'contribuciones': contribuciones,
    }


def _leer_xlsx_primera_hoja(ruta: Path) -> list[dict]:
    """Lee XLSX básico sin instalar librerías adicionales.

    Para Excel de PMOGA (texto, números y celdas comunes). No evalúa
    macros, fórmulas ni enlaces externos.
    """
    import re
    from zipfile import ZipFile
    from xml.etree import ElementTree as ET
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(ruta) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('m:si', ns):
                shared.append(''.join(t.text or '' for t in si.iterfind('.//m:t', ns)))
        nombres = sorted((x for x in z.namelist() if re.fullmatch(r'xl/worksheets/sheet[0-9]+.xml', x)),
                         key=lambda x: int(re.search(r'sheet([0-9]+)', x).group(1)))
        if not nombres:
            raise ValueError('XLSX no contiene hojas legibles')
        root = ET.fromstring(z.read(nombres[0]))
        rows = root.findall('.//m:sheetData/m:row', ns)
        if not rows:
            raise ValueError('XLSX sin filas')
        def read_row(row):
            result = {}
            for c in row.findall('m:c', ns):
                ref = c.get('r', 'A1')
                letters = re.match(r'[A-Z]+', ref).group(0)
                index = 0
                for ch in letters:
                    index = index * 26 + ord(ch) - 64
                index -= 1
                v = c.find('m:v', ns)
                if c.get('t') == 'inlineStr':
                    val = ''.join(t.text or '' for t in c.iterfind('.//m:t', ns))
                elif v is None:
                    val = None
                elif c.get('t') == 's':
                    val = shared[int(v.text)]
                else:
                    val = v.text
                result[index] = val
            return result
        header = read_row(rows[0])
        if not header:
            raise ValueError('Primera fila sin encabezados')
        out = []
        for row in rows[1:]:
            vals = read_row(row)
            if any(x is not None and str(x).strip() for x in vals.values()):
                out.append({str(t): vals.get(i) for i, t in header.items() if t is not None})
        return out


def cargar_clientes(ruta: str | Path) -> list[dict]:
    """CSV/Excel con encabezados en inglés o español; un registro por fila.

    Excel utiliza openpyxl como dependencia opcional para ejecución futura.
    """
    ruta = Path(ruta)
    if ruta.suffix.lower() == '.csv':
        with ruta.open(encoding='utf-8-sig', newline='') as f:
            filas = list(csv.DictReader(f))
    elif ruta.suffix.lower() == '.json':
        filas = json.loads(ruta.read_text(encoding='utf-8-sig'))
        if isinstance(filas, dict):
            filas = filas.get('records') or filas.get('clientes')
    elif ruta.suffix.lower() == '.xlsx':
        filas = _leer_xlsx_primera_hoja(ruta)
    else:
        raise ValueError('Se admiten CSV, JSON y XLSX')
    if not isinstance(filas, list):
        raise ValueError('La entrada no contiene una lista de clientes')
    if filas and 'priorities' in filas[0] and 'group' in filas[0]:
        return filas

    def norm(s):
        import unicodedata
        s = unicodedata.normalize('NFKD', str(s).lower())
        return ''.join(c for c in s if not unicodedata.combining(c) and c.isalnum())
    mapa = {norm(x): x for x in (filas[0].keys() if filas else [])}
    def campo(opciones):
        for op in opciones:
            if norm(op) in mapa:
                return mapa[norm(op)]
        return None
    n = campo(['Customer Name', 'Nombre Cliente', 'Cliente', 'Nombre'])
    g = campo(['Customer Group', 'Grupo Cliente', 'Grupo'])
    entradas = [
        campo(['First Outcome Priority', '1st', 'Primera Prioridad', 'Prioridad 1', '1ra']),
        campo(['Second Outcome Priority', '2nd', 'Segunda Prioridad', 'Prioridad 2', '2da']),
        campo(['Third Outcome Priority', '3rd', 'Tercera Prioridad', 'Prioridad 3', '3ra']),
        campo(['Fourth Outcome Priority', '4th', 'Cuarta Prioridad', 'Prioridad 4', '4ta']),
        campo(['Fifth Outcome Priority', '5th', 'Quinta Prioridad', 'Prioridad 5', '5ta']),
    ]
    if not g or any(x is None for x in entradas):
        raise ValueError('Faltan columnas Customer Group o una de las cinco prioridades. Cabeceras: ' + str(list(mapa.values())))
    registros = []
    for i, fila in enumerate(filas, start=2):
        try:
            pri = []
            for columna in entradas:
                v = float(fila[columna])
                if not v.is_integer():
                    raise ValueError('Prioridad decimal no permitida')
                pri.append(int(v))
        except (TypeError, ValueError) as e:
            raise ValueError(f'Excel fila {i}: hay una prioridad no entera') from e
        registros.append({'name': str(fila.get(n) or f'Cliente {i}'), 'group': str(fila[g]).strip(), 'priorities': pri})
    return registros


def comparar_reporte(resultado: dict, caso_pmoga: dict) -> dict:
    """Comparación de porcentajes con el reporte PMOGA, NO compara solo posiciones."""
    pmoga = {}
    for servicio in caso_pmoga['results']:
        sid = int(str(servicio['serviceName']).split('.')[0])
        pmoga[sid] = float(servicio['priorityScore'])
    if set(pmoga) != set(range(1, SERVICIOS + 1)):
        raise ValueError('El reporte PMOGA no tiene exactamente los 26 servicios')
    diferencias = [resultado['servicios_26_pct'][s - 1] - pmoga[s] for s in range(1, SERVICIOS + 1)]
    return {
        'error_absoluto_medio_pp': sum(map(abs, diferencias)) / SERVICIOS,
        'error_maximo_pp': max(map(abs, diferencias)),
        'por_servicio': [{'id': i + 1, 'PMOGA': pmoga[i + 1], 'CENS': resultado['servicios_26_pct'][i],
                          'diferencia_pp': diferencias[i]} for i in range(SERVICIOS)]
    }


def hash_matriz(matriz: list[list[int]]) -> str:
    validar_matriz(matriz)
    return hashlib.sha256(json.dumps(matriz, separators=(',', ':')).encode()).hexdigest()


def guardar_json(resultado: dict, ruta: str | Path) -> None:
    Path(ruta).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
