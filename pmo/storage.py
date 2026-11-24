"""SQLite transaccional con tablas compartidas y auditoría mínima."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path
from .config import database_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pmo_dependencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pmo_clientes (
  id TEXT PRIMARY KEY,
  codigo TEXT NOT NULL UNIQUE COLLATE NOCASE,
  nombre TEXT NOT NULL,
  dependencia_id INTEGER NOT NULL REFERENCES pmo_dependencias(id),
  cargo TEXT NOT NULL DEFAULT '',
  correo TEXT UNIQUE COLLATE NOCASE,
  sede TEXT NOT NULL DEFAULT '',
  segmento TEXT NOT NULL DEFAULT '',
  influencia TEXT NOT NULL DEFAULT 'Sin evaluar' CHECK(influencia IN ('Sin evaluar','Baja','Media','Alta')),
  interes TEXT NOT NULL DEFAULT 'Sin evaluar' CHECK(interes IN ('Sin evaluar','Bajo','Medio','Alto')),
  conocimiento INTEGER CHECK(conocimiento BETWEEN 1 AND 5),
  participa_proyectos TEXT NOT NULL DEFAULT 'Sin evaluar',
  canal TEXT NOT NULL DEFAULT '',
  retos TEXT NOT NULL DEFAULT '',
  necesidades_preliminares TEXT NOT NULL DEFAULT '',
  beneficios_esperados TEXT NOT NULL DEFAULT '',
  barreras TEXT NOT NULL DEFAULT '',
  observaciones TEXT NOT NULL DEFAULT '',
  responsable TEXT NOT NULL DEFAULT '',
  primer_contacto TEXT,
  relacionamiento TEXT NOT NULL DEFAULT 'Sin contacto',
  embajador INTEGER NOT NULL DEFAULT 0 CHECK(embajador IN (0,1)),
  activo INTEGER NOT NULL DEFAULT 1 CHECK(activo IN (0,1)),
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pmo_auditoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entidad TEXT NOT NULL,
  entidad_id TEXT NOT NULL,
  accion TEXT NOT NULL,
  antes_json TEXT,
  despues_json TEXT,
  actor TEXT NOT NULL,
  fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pmo_clientes_dependencia ON pmo_clientes(dependencia_id);
CREATE INDEX IF NOT EXISTS idx_pmo_clientes_estado ON pmo_clientes(activo);
CREATE INDEX IF NOT EXISTS idx_auditoria_entidad ON pmo_auditoria(entidad, entidad_id);
"""

# Actualización aditiva V0.2. Ningún registro V0.1 se borra o sustituye.
EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS p1_recursos (
  id TEXT PRIMARY KEY, titulo TEXT NOT NULL, categoria TEXT NOT NULL,
  descripcion TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL CHECK(tipo IN ('Material','Servicio','Historia')),
  estado TEXT NOT NULL, responsable TEXT NOT NULL,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p1_eventos (
  id TEXT PRIMARY KEY, titulo TEXT NOT NULL, tipo TEXT NOT NULL,
  fecha TEXT NOT NULL, publico TEXT NOT NULL DEFAULT '',
  modalidad TEXT NOT NULL DEFAULT '', responsable TEXT NOT NULL,
  estado TEXT NOT NULL CHECK(estado IN ('Borrador','Programado','Realizado','Cancelado')),
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p1_asistencias (
  evento_id TEXT NOT NULL REFERENCES p1_eventos(id),
  cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
  asistio INTEGER NOT NULL DEFAULT 0 CHECK(asistio IN (0,1)),
  PRIMARY KEY(evento_id,cliente_id)
);
CREATE TABLE IF NOT EXISTS p1_campanas (
  id TEXT PRIMARY KEY, titulo TEXT NOT NULL, audiencia TEXT NOT NULL DEFAULT '',
  canal TEXT NOT NULL DEFAULT '', fecha_inicio TEXT NOT NULL,
  estado TEXT NOT NULL, responsable TEXT NOT NULL,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p1_consultas (
  id TEXT PRIMARY KEY, cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
  asunto TEXT NOT NULL, categoria TEXT NOT NULL,
  descripcion TEXT NOT NULL, responsable TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT 'Recibida' CHECK(estado IN ('Recibida','En análisis','En gestión','Respondida','Cerrada')),
  respuesta TEXT NOT NULL DEFAULT '', creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  respondido_en TEXT
);
CREATE TABLE IF NOT EXISTS p1_encuestas (
  id TEXT PRIMARY KEY, cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),
  evento_id TEXT REFERENCES p1_eventos(id), fase TEXT NOT NULL CHECK(fase IN ('Antes','Después')),
  familiaridad INTEGER NOT NULL CHECK(familiaridad BETWEEN 1 AND 5),
  proposito INTEGER NOT NULL CHECK(proposito BETWEEN 1 AND 5),
  servicios INTEGER NOT NULL CHECK(servicios BETWEEN 1 AND 5),
  utilidad INTEGER NOT NULL CHECK(utilidad BETWEEN 1 AND 5),
  interes INTEGER NOT NULL CHECK(interes BETWEEN 1 AND 5),
  responsable TEXT NOT NULL, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p1_autoevaluaciones (
  id TEXT PRIMARY KEY, periodo TEXT NOT NULL, evaluador TEXT NOT NULL,
  instrumento TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'Borrador'
  CHECK(estado IN ('Borrador','Finalizada')), puntaje INTEGER,
  clasificacion TEXT, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finalizada_en TEXT
);
CREATE TABLE IF NOT EXISTS p1_respuestas_autoevaluacion (
  evaluacion_id TEXT NOT NULL REFERENCES p1_autoevaluaciones(id),
  numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 25),
  valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5), observacion TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(evaluacion_id,numero)
);
CREATE TABLE IF NOT EXISTS p1_excel_referencias (
  entidad TEXT NOT NULL,
  codigo_excel TEXT NOT NULL COLLATE NOCASE,
  objeto_id TEXT NOT NULL,
  importado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (entidad, codigo_excel)
);
CREATE TABLE IF NOT EXISTS p1_excel_cargas (
  id TEXT PRIMARY KEY,
  huella_sha256 TEXT NOT NULL,
  actor TEXT NOT NULL,
  resumen TEXT NOT NULL,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_p1_tickets_cliente ON p1_consultas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_p1_encuestas_cliente ON p1_encuestas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_p1_asistencias_cliente ON p1_asistencias(cliente_id);
"""


STEP2_SCHEMA = "-- Extensión aditiva V0.4: no altera tablas del Paso 1.\nCREATE TABLE IF NOT EXISTS p2_diagnosticos (\n id TEXT PRIMARY KEY, nombre TEXT NOT NULL, ciclo TEXT NOT NULL, objetivo TEXT NOT NULL DEFAULT '',\n alcance TEXT NOT NULL DEFAULT '', responsable TEXT NOT NULL,\n poblacion_objetivo INTEGER CHECK(poblacion_objetivo IS NULL OR poblacion_objetivo>=0),\n estado TEXT NOT NULL DEFAULT 'En diseño' CHECK(estado IN ('En diseño','Programado','En levantamiento','En análisis','Cerrado')),\n creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\nCREATE TABLE IF NOT EXISTS p2_madurez (\n diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n dimension TEXT NOT NULL, actual INTEGER NOT NULL CHECK(actual BETWEEN 1 AND 5),\n deseado INTEGER NOT NULL CHECK(deseado BETWEEN 1 AND 5),\n fuente TEXT NOT NULL, responsable TEXT NOT NULL,\n registrado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n PRIMARY KEY(diagnostico_id,dimension)\n);\nCREATE TABLE IF NOT EXISTS p2_levantamientos (\n id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),\n metodo TEXT NOT NULL CHECK(metodo IN ('Entrevista','Encuesta','Grupo focal','Revisión documental')),\n fecha TEXT NOT NULL, estado TEXT NOT NULL CHECK(estado IN ('Programada','En curso','Completada','Cancelada')),\n observaciones TEXT NOT NULL DEFAULT '', fuente TEXT NOT NULL DEFAULT '',\n actor TEXT NOT NULL, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\nCREATE INDEX IF NOT EXISTS idx_p2_leva_diagnostico ON p2_levantamientos(diagnostico_id);\nCREATE TABLE IF NOT EXISTS p2_expectativas (\n diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id),\n posicion INTEGER NOT NULL CHECK(posicion BETWEEN 1 AND 5),\n resultado_id INTEGER NOT NULL CHECK(resultado_id BETWEEN 1 AND 30),\n notas TEXT NOT NULL DEFAULT '',\n actor TEXT NOT NULL, actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n PRIMARY KEY(diagnostico_id,cliente_id,posicion),\n UNIQUE(diagnostico_id,cliente_id,resultado_id)\n);\nCREATE INDEX IF NOT EXISTS idx_p2_expectativas_resultado ON p2_expectativas(diagnostico_id,resultado_id);\nCREATE TABLE IF NOT EXISTS p2_necesidades (\n id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n cliente_id TEXT REFERENCES pmo_clientes(id), dependencia TEXT NOT NULL,\n problema TEXT NOT NULL, ganancia TEXT NOT NULL, resultado_id INTEGER CHECK(resultado_id IS NULL OR resultado_id BETWEEN 1 AND 30),\n impacto TEXT NOT NULL CHECK(impacto IN ('Sin evaluar','Bajo','Medio','Alto')),\n fuente TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'Registrada'\n CHECK(estado IN ('Registrada','En validación','Validada','Descartada')),\n actor TEXT NOT NULL, validador TEXT, justificacion_validacion TEXT NOT NULL DEFAULT '',\n validado_en TEXT, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\nCREATE INDEX IF NOT EXISTS idx_p2_necesidades_diagnostico ON p2_necesidades(diagnostico_id);\nCREATE TABLE IF NOT EXISTS p2_evidencias (\n id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n necesidad_id TEXT REFERENCES p2_necesidades(id), levantamiento_id TEXT REFERENCES p2_levantamientos(id),\n titulo TEXT NOT NULL, tipo TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',\n responsable TEXT NOT NULL, fecha TEXT NOT NULL, creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\nCREATE TABLE IF NOT EXISTS p2_pesos (\n diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id), grupo TEXT NOT NULL,\n peso REAL NOT NULL CHECK(peso BETWEEN 0 AND 100),\n actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n PRIMARY KEY(diagnostico_id,grupo)\n);\nCREATE TABLE IF NOT EXISTS p2_corridas (\n id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n origen TEXT NOT NULL, modelo TEXT NOT NULL, matriz_json TEXT NOT NULL,\n pesos_json TEXT NOT NULL, respuestas_json TEXT NOT NULL, resultados_json TEXT NOT NULL,\n actor TEXT NOT NULL, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\nCREATE INDEX IF NOT EXISTS idx_p2_corridas_diag ON p2_corridas(diagnostico_id,fecha);\nCREATE TABLE IF NOT EXISTS p2_servicios_candidatos (\n diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id), servicio_id INTEGER NOT NULL CHECK(servicio_id BETWEEN 1 AND 26),\n estado TEXT NOT NULL CHECK(estado IN ('Preseleccionado','En validación','Validado','Descartado')),\n justificacion TEXT NOT NULL, responsable TEXT NOT NULL,\n actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n PRIMARY KEY(diagnostico_id,servicio_id)\n);\nCREATE TABLE IF NOT EXISTS p2_autoevaluaciones (\n id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n evaluador TEXT NOT NULL, instrumento TEXT NOT NULL,\n estado TEXT NOT NULL DEFAULT 'Borrador' CHECK(estado IN ('Borrador','Finalizada')),\n puntaje INTEGER, clasificacion TEXT,\n creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finalizada_en TEXT\n);\nCREATE TABLE IF NOT EXISTS p2_respuestas_autoevaluacion (\n evaluacion_id TEXT NOT NULL REFERENCES p2_autoevaluaciones(id),\n numero INTEGER NOT NULL CHECK(numero BETWEEN 1 AND 25),\n valor INTEGER NOT NULL CHECK(valor BETWEEN 1 AND 5),\n observacion TEXT NOT NULL DEFAULT '', evidencia TEXT NOT NULL DEFAULT '',\n PRIMARY KEY(evaluacion_id,numero)\n);\nCREATE TABLE IF NOT EXISTS p2_cargas_excel (\n id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),\n sha256 TEXT NOT NULL, filas INTEGER NOT NULL, actor TEXT NOT NULL,\n cargado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\n"


STEP2_EXCEL_V06_SCHEMA = """
CREATE TABLE IF NOT EXISTS p2_excel_diagnosticos (
 codigo_externo TEXT PRIMARY KEY COLLATE NOCASE,
 diagnostico_id TEXT NOT NULL UNIQUE REFERENCES p2_diagnosticos(id)
);
CREATE TABLE IF NOT EXISTS p2_excel_registros (
 diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),
 seccion TEXT NOT NULL CHECK(seccion IN ('Levantamientos','Necesidades','Evidencias')),
 codigo_externo TEXT NOT NULL COLLATE NOCASE, registro_id TEXT NOT NULL,
 PRIMARY KEY (diagnostico_id,seccion,codigo_externo),
 UNIQUE(diagnostico_id,seccion,registro_id)
);
CREATE TABLE IF NOT EXISTS p2_importaciones_integrales (
 id TEXT PRIMARY KEY, diagnostico_id TEXT NOT NULL REFERENCES p2_diagnosticos(id),
 archivo TEXT NOT NULL, sha256 TEXT NOT NULL, filas INTEGER NOT NULL,
 detalle_json TEXT NOT NULL, actor TEXT NOT NULL, fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""



# V0.36: histórico anual de madurez 0–5 (independiente de p2_madurez 1–5).
ANNUAL_MATURITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS p2_madurez_anual_periodos (
  ano INTEGER PRIMARY KEY CHECK(ano BETWEEN 2000 AND 2100),
  participantes INTEGER CHECK(participantes IS NULL OR participantes>=0),
  encuestas INTEGER CHECK(encuestas IS NULL OR encuestas>=0),
  equipos INTEGER CHECK(equipos IS NULL OR equipos>=0),
  dependencias INTEGER CHECK(dependencias IS NULL OR dependencias>=0),
  hallazgos TEXT NOT NULL DEFAULT '', fuente TEXT NOT NULL, responsable TEXT NOT NULL,
  actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS p2_madurez_anual_escenarios (
  ano INTEGER NOT NULL REFERENCES p2_madurez_anual_periodos(ano),
  escenario TEXT NOT NULL CHECK(escenario IN ('Con enfoques y metodologías','Sin enfoques y metodologías')),
  indice REAL NOT NULL CHECK(indice BETWEEN 0 AND 5),
  fuente TEXT NOT NULL, responsable TEXT NOT NULL,
  actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(ano,escenario)
);
CREATE TABLE IF NOT EXISTS p2_madurez_anual_dimensiones (
  ano INTEGER NOT NULL, escenario TEXT NOT NULL, dimension TEXT NOT NULL,
  puntaje REAL NOT NULL CHECK(puntaje BETWEEN 0 AND 5),
  PRIMARY KEY(ano,escenario,dimension),
  FOREIGN KEY(ano,escenario) REFERENCES p2_madurez_anual_escenarios(ano,escenario) ON DELETE CASCADE
);
"""


def _upgrade_annual_maturity_to_zero_five(con: sqlite3.Connection, target: Path) -> None:
    """One-time, backed-up schema adjustment for annual scores 0..5.

    Does not touch PMOGA, the old 1..5 assessment, or any annual value.
    """
    row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='p2_madurez_anual_escenarios'").fetchone()
    if row is None or 'BETWEEN 0 AND 4' not in row['sql']:
        return
    # Before touching existing data, create a consistent, SQLite-native backup.
    from datetime import datetime as _dt
    destdir = Path(target).parent / 'respaldos'
    destdir.mkdir(parents=True, exist_ok=True)
    backup_path = destdir / ('madurez_antes_escala_0_5_' + _dt.now().strftime('%Y%m%d_%H%M%S_%f') + '.sqlite3')
    with sqlite3.connect(str(backup_path)) as out:
        con.backup(out)
    con.commit()
    con.execute('PRAGMA foreign_keys=OFF')
    try:
        con.execute('BEGIN IMMEDIATE')
        con.execute("""CREATE TABLE p2_madurez_anual_escenarios_v0381 (
          ano INTEGER NOT NULL REFERENCES p2_madurez_anual_periodos(ano),
          escenario TEXT NOT NULL CHECK(escenario IN ('Con enfoques y metodologías','Sin enfoques y metodologías')),
          indice REAL NOT NULL CHECK(indice BETWEEN 0 AND 5),
          fuente TEXT NOT NULL, responsable TEXT NOT NULL,
          actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(ano,escenario))""")
        con.execute("""CREATE TABLE p2_madurez_anual_dimensiones_v0381 (
          ano INTEGER NOT NULL, escenario TEXT NOT NULL, dimension TEXT NOT NULL,
          puntaje REAL NOT NULL CHECK(puntaje BETWEEN 0 AND 5),
          PRIMARY KEY(ano,escenario,dimension),
          FOREIGN KEY(ano,escenario) REFERENCES p2_madurez_anual_escenarios_v0381(ano,escenario) ON DELETE CASCADE)""")
        con.execute("""INSERT INTO p2_madurez_anual_escenarios_v0381
          (ano,escenario,indice,fuente,responsable,actualizado_en)
          SELECT ano,escenario,indice,fuente,responsable,actualizado_en FROM p2_madurez_anual_escenarios""")
        con.execute("""INSERT INTO p2_madurez_anual_dimensiones_v0381
          (ano,escenario,dimension,puntaje)
          SELECT ano,escenario,dimension,puntaje FROM p2_madurez_anual_dimensiones""")
        con.execute('DROP TABLE p2_madurez_anual_dimensiones')
        con.execute('DROP TABLE p2_madurez_anual_escenarios')
        con.execute('ALTER TABLE p2_madurez_anual_escenarios_v0381 RENAME TO p2_madurez_anual_escenarios')
        con.execute('ALTER TABLE p2_madurez_anual_dimensiones_v0381 RENAME TO p2_madurez_anual_dimensiones')
        bad = con.execute('PRAGMA foreign_key_check').fetchall()
        if bad:
            raise RuntimeError('No se completó la migración: referencias de madurez no válidas.')
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute('PRAGMA foreign_keys=ON')


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(target), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=15000")
    return con


def initialize(path: Path | None = None) -> None:
    with closing(connect(path)) as con:
        con.executescript(SCHEMA)
        con.executescript(EXTENSION_SCHEMA)
        con.executescript(STEP2_SCHEMA)
        con.executescript(STEP2_EXCEL_V06_SCHEMA)
        con.executescript(ANNUAL_MATURITY_SCHEMA)
        _upgrade_annual_maturity_to_zero_five(con, Path(path) if path is not None else database_path())
        # V0.24: ampliación no destructiva del directorio maestro de interesados.
        existing_cols = {row["name"] for row in con.execute("PRAGMA table_info(pmo_clientes)")}
        for field in ("equipo_trabajo", "rol_especifico", "estado_gestion"):
            if field not in existing_cols:
                con.execute(f"ALTER TABLE pmo_clientes ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS p1_client_custom_columns (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
            tipo TEXT NOT NULL DEFAULT 'Texto' CHECK(tipo IN ('Texto','Número','Fecha')),
            posicion INTEGER NOT NULL DEFAULT 0,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS p1_client_custom_values (
            cliente_id TEXT NOT NULL REFERENCES pmo_clientes(id) ON DELETE CASCADE,
            columna_id TEXT NOT NULL REFERENCES p1_client_custom_columns(id) ON DELETE CASCADE,
            valor TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(cliente_id, columna_id)
        );
        """)
        con.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)")
        con.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (2)")
        con.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (3)")
        con.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (4)")
        con.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (6)")
        con.commit()
    from .matrix import initialize as init_matrix
    init_matrix(path)


@contextmanager
def transaction(path: Path | None = None):
    con = connect(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
