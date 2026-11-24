# QA · V1.0.0 Cloud Edition

Base: ZIP local V1.0.0. Pruebas ejecutadas en Linux con Python 3.13.5.

- `PYTHONPATH=. pytest -q tests/test_cloud.py`: **6 aprobadas, 0 fallidas**. Incluye integridad y conteos de la semilla, aislamiento de dos sesiones simuladas con cambios de SQLite reales y reinicio, inicialización SQL idempotente, alcance del paquete, corrida V5 con seis participantes ficticios y navegación simulada de los 53 componentes de los diez pasos.
- `PRAGMA integrity_check`: ok. `PRAGMA foreign_key_check`: 0 violaciones. Se verificaron 6 clientes genéricos sin correo, 30 preferencias, 6 necesidades, 2 eventos, 2 servicios en borrador y 0 fuentes de madurez institucional.
- Comparación byte a byte: 13 archivos protegidos coinciden con la versión local (V5, matriz, catálogos de coeficientes, motores pasos 02–10). Ver `PROTECTED_SHA256.json`.
- Análisis sintáctico: 122 archivos Python (módulos, entrada, generador de semilla y prueba).
- Intento de instalar Streamlit >=1.51,<2: no se encontró distribución disponible en el entorno. No hubo prueba de renderizado real, ejecución del servidor ni despliegue Community Cloud. La regresión completa histórica de V1.0.0 no se ejecutó sobre Cloud. No se certifica seguridad o concurrencia productiva.
- Se eliminaron los datos iniciales reales, talleres, PDF, bases históricas, referencias originales y accesos Windows. Se adaptó la configuración, administración, cargas institucionales y descargas de matriz original. Los catálogos metodológicos y código requieren revisión de autorización antes de su alojamiento externo.
- El ZIP contiene exclusivamente la semilla ficticia de SQLite. No es copia anonimizada de una base real. No incluye credenciales ni secretos configurados. No se realizó auditoría de seguridad exhaustiva.
