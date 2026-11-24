"""Catálogos de apoyo a la caracterización de servicios PMO (CENS, Paso 04).

La guía PMO indica qué debe documentarse, no establece estos códigos internos.
Las opciones y auxiliares de captura son una adaptación operativa editable de CENS.
"""
from __future__ import annotations
import re

NATURALEZAS = ('Por definir', 'Estratégico', 'Táctico', 'Operativo')
DOMINIOS = ('Portafolio', 'Programa', 'Proyecto', 'Empresa')
ENFOQUES = ('Por definir', 'Prestación integral PMO', 'Prestación compartida PMO/cliente',
            'Acompañamiento y facilitación', 'Autoservicio guiado')
INTEGRACIONES = ('Por definir', 'Sin integración tecnológica', 'Herramienta existente',
                 'Integración de sistemas existentes', 'Nuevo desarrollo por evaluar')
RETROALIMENTACION = ('Por definir', 'Encuesta al cierre', 'Encuesta periódica',
                     'Revisión con cliente', 'Lecciones aprendidas', 'Mecanismo mixto')
CANALES = ('Por definir', 'Formulario/Portal PMO', 'Correo institucional',
           'Mesa de servicio', 'Solicitud en comité o reunión', 'Activación automática por regla',
           'Actuación proactiva de la PMO', 'Otro')
ADAPTACIONES = ('Por tipología del proyecto', 'Por complejidad o criticidad',
                'Por madurez del cliente', 'Por tamaño o duración', 'Por sector o dependencia')
RIESGOS = ('Capacidad y disponibilidad', 'Calidad y tiempos de atención', 'Información y tecnología',
           'Gobernanza y coordinación', 'Adopción y cambio', 'Cumplimiento y regulación', 'Otros')
UNIDADES_ANS = ('Por definir', 'Horas hábiles', 'Días hábiles', 'Días calendario', 'Semanas')
PERIODICIDADES = ('Por definir', 'Por evento', 'Semanal', 'Quincenal', 'Mensual',
                  'Bimestral', 'Trimestral', 'Semestral', 'Anual')
ESCALAMIENTOS = ('Por definir', 'Responsable del servicio', 'Coordinador PMO',
                 'Cliente o dependencia solicitante', 'Comité o patrocinador', 'Gerencia')
ESTRATEGIAS = ('Por definir', 'Piloto controlado', 'Despliegue gradual',
               'Implementación por fases', 'Implementación completa')
ESTADOS_PILOTO = ('Por definir', 'Diseño pendiente', 'Planificado', 'En ejecución',
                  'Evaluación pendiente', 'Evaluado')

# Catálogos corporativos propuestos. Opciones de configuración, no evidencia de aprobación.
FASES_RUTA = ('Por definir', '1. Co-diseño con Clientes',
    '2. Concertación de ANS y RACI', '3. Piloto de Campo / Prueba',
    '4. Evaluación y Ajustes', '5. Incorporación Definitiva a Operación')
ESTRATEGIAS_DESPLIEGUE = ('Por definir', 'Piloto Acotado (1 a 3 Proyectos Muestra)',
    'Piloto por Dependencia / Regional', 'Despliegue Gradual por Fases',
    'Despliegue General / Masivo')
ESTADOS_PRESUPUESTO = ('Por definir', 'Sin Presupuesto Asignado (Pendiente Dimensionamiento)',
    'Reasignación de Recursos Propios PMO (Costo Incremental por validar)',
    'Solicitud Financiera en Evaluación', 'Presupuesto CapEx/OpEx Aprobado')
ESTADOS_APROBACION = ('Borrador de Taller (Diseño Preliminar)',
    'En Concertación con Clientes Internos', 'Pendiente de Aval del Comité PMO',
    'Avalado por Comité de Gobernanza PMO', 'Aprobación Institucional Definitiva')
MADUREZES_SERVICIO = ('Por definir', 'Nivel 1: Básico / Ad-hoc', 'Nivel 2: Normalizado',
    'Nivel 3: Integrado', 'Nivel 4: Estratégico', 'Nivel 5: Optimizado / IA')
TRATAMIENTOS_RIESGO = ('Mitigar', 'Evitar', 'Transferir', 'Aceptar')
COMPLEJIDADES = ('Alta Complejidad (CAPEX / Infraestructura)',
    'Media Complejidad (TI / Transformación)', 'Baja Complejidad (Gestión / Proyectos Menores)')
PRIORIDADES_SOLICITUD = ('Crítica', 'Alta', 'Media', 'Baja / Estándar')
HITOS_TIPO = ('Definir alcance y responsables', 'Concertar ANS y matriz RACI',
    'Aprobar diseño y criterios de piloto', 'Preparar recursos y entorno tecnológico',
    'Ejecutar piloto controlado', 'Evaluar resultados y registrar ajustes',
    'Validar conformidad del cliente', 'Solicitar decisión de incorporación')

# Nuevos campos de la ficha. No sustituyen los campos explicativos ya existentes.
EXTRA_FIELDS = ('naturaleza', 'dominios', 'enfoque_prestacion', 'tipo_integracion',
                'mecanismo_retroalimentacion', 'canal_solicitud', 'variantes_tipo',
                'categorias_riesgo', 'unidad_tiempo_ans', 'periodicidad_revision',
                'nivel_escalamiento', 'estrategia_despliegue', 'estado_piloto',
                'ans_estado','ans_respuesta_valor','ans_respuesta_unidad','ans_entrega_valor',
                'ans_entrega_unidad','ans_horario','ans_inicio_computo','ans_fin_computo',
                'ans_medio_aceptacion','ans_responsable_escalamiento','ans_responsable_revision',
                'ans_cliente_id','ans_archivo','ans_versiones','ans_nivel_servicio',
                'ans_condiciones_nivel','ans_motivo_fecha',
                'ans_sla_respuesta_original','ans_sla_entrega_original',
                'ans_evidencias_historicas',
                'fase_ruta_implementacion','fase_ruta_propuesta','estado_presupuesto',
                'estado_aprobacion_institucional','evidencia_aprobacion_institucional',
                'nivel_madurez_servicio','meta_madurez_propuesta',
                'hitos_lista','hitos_adicionales','riesgos_tratamientos','complejidades_aplicables',
                'prioridades_solicitud','propuesta_srv011_origen','perfil_propietario_propuesto',
                'ans_escenarios_propuestos','raci_matriz_propuesta','riesgos_matriz_propuesta',
                'kpis_propuestos','entregables_mvd_propuestos','evidencia_raci_aprobado',
                'evidencia_piloto_exitoso','propuesta_presupuesto', 'requisitos_servicio',
                'evidencia_presupuesto_aprobado',
                'entregables_items','proceso_actividades','riesgos_registro','hitos_registro',
                'raci_registro','destinatarios_roles')
LIST_EXTRA_FIELDS = ('dominios','variantes_tipo','categorias_riesgo','ans_versiones','ans_evidencias_historicas',
                     'hitos_lista','riesgos_tratamientos','complejidades_aplicables','prioridades_solicitud',
                     'ans_escenarios_propuestos','raci_matriz_propuesta','riesgos_matriz_propuesta',
                     'kpis_propuestos','entregables_mvd_propuestos',
                     'entregables_items','proceso_actividades','riesgos_registro','hitos_registro',
                     'raci_registro','destinatarios_roles')


def infer_naturaleza(caracteristicas: str) -> str:
    """Sólo se infiere para presentar una sugerencia, nunca se cambia una ficha sin guardar."""
    match = re.search(r'Naturaleza del servicio\s*:\s*(Estratégico|Táctico|Operativo)',
                      str(caracteristicas or ''), re.I)
    if match:
        return next(x for x in NATURALEZAS if x.casefold() == match.group(1).casefold())
    match = re.search(r'Tipo de Servicio\s*:\s*(Estratégico|Táctico|Operativo)',
                      str(caracteristicas or ''), re.I)
    if match:
        return next(x for x in NATURALEZAS if x.casefold() == match.group(1).casefold())
    return 'Por definir'


def infer_dominios(caracteristicas: str) -> list[str]:
    text = str(caracteristicas or '')
    match = re.search(r'Dominios?\s*:\s*([^\n]+)', text, re.I)
    if not match:
        return []
    line = match.group(1).split('Tipo de Servicio:')[0]
    return [d for d in DOMINIOS if re.search(r'\b' + re.escape(d) + r'\b', line, re.I)]


def catalog_choice(saved, options):
    """No pierde valores históricos fuera del catálogo cuando se reabre una ficha."""
    value = str(saved or '').strip()
    return value if value in options else options[0]


def clean_empty_import_markers(value: str) -> str:
    """Retira solamente líneas que son marcadores vacíos del PDF, sin tocar frases válidas."""
    lines = str(value or '').splitlines()
    cleaned = [x for x in lines if not re.fullmatch(r'\s*(?:[•-]\s*)?Agregar(?:\s+Agregar)*\s*', x, re.I)]
    return '\n'.join(cleaned).strip()
