# PMO FLYWHEEL CENS · V1.0.0 Cloud Edition

Edición de **demostración privada**, derivada de V1.0.0 local. Conserva los diez pasos, las nueve herramientas transversales, los motores metodológicos y los catálogos de cálculo. No es un despliegue de producción ni una aprobación institucional.

## Publicación en Streamlit Community Cloud

1. Descomprime el ZIP completo. Crea un repositorio **privado** en GitHub, por ejemplo `pmo-flywheel-cens-cloud`. Antes de cargar el código, verifica que tienes autorización de CENS y derechos de uso de matrices, catálogos e instrumentos metodológicos de terceros. La edición excluye fuentes documentales y resultados institucionales, pero conserva código y catálogos metodológicos; no autoriza su redistribución pública.
2. Carga el contenido de esta carpeta, no el ZIP: `app.py`, `requirements.txt`, `pmo/`, `cloud_seed/`, `plantillas/`, `.streamlit/` y los demás archivos incluidos. Mantén la estructura y los nombres exactos, incluyendo directorios ocultos. Puedes usar GitHub Desktop para copiar toda la carpeta y publicar un commit sin abrir VS Code. Asegúrate de que `cloud_seed/demo.sqlite3` esté incluido; es la única base que debe subirse. No agregues el ZIP local, bases personales ni archivos de CENS.
3. Accede a https://share.streamlit.io/ con tu cuenta y conecta GitHub. Selecciona **Create app** y la opción de desplegar un repositorio existente. Indica repositorio `TU_USUARIO/pmo-flywheel-cens-cloud`, rama `main` (o la real), archivo principal `app.py`. En Advanced settings selecciona Python 3.13 si está disponible. No requiere secretos ni credenciales de base de datos. El subdominio sugerido `pmo-flywheel-cens-cloud` está sujeto a disponibilidad.
4. Selecciona Deploy y revisa los logs. Mantén la aplicación **privada** en Share/App settings y comparte exclusivamente con personas autorizadas. El repositorio privado no sustituye los permisos institucionales; verifica también la privacidad de la aplicación.
5. Ejecuta las pruebas de aceptación indicadas abajo. Si el despliegue falla, conserva el mensaje de error y el log sin datos sensibles. No publiques la versión local para solucionar un error.

Documentación oficial: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy y https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app.

## Datos y seguridad

- Semilla creada desde cero con seis clientes de nombre genérico, tres dependencias ficticias, un diagnóstico de 2027, 30 preferencias, seis necesidades, dos eventos y dos servicios en borrador. Sin correos, historiales reales, corridas oficiales, beneficios validados ni decisiones MVS.
- Se copia la semilla a un directorio temporal distinto por sesión de Streamlit. Las operaciones se ejecutan sobre esa copia. No se conecta a LocalAppData ni respeta PMO_CENS_DATA_DIR de la edición local. El aislamiento se comprobó a nivel de código, no es una auditoría de seguridad multiusuario.
- Cambios temporales: una recarga que conserve la sesión puede mantenerlos; una sesión nueva, reinicio o redeploy puede perderlos. Reiniciar laboratorio requiere confirmación y elimina la copia de la sesión actual. La eliminación física al cerrar la conexión depende del ciclo de vida del proceso; no se garantiza eliminación inmediata. Descarga los informes antes de salir.
- Las cargas de Excel/JSON/evidencias siguen disponibles para ejercicios ficticios (límite de carga 10 MB por archivo configurado). No cargar datos personales, respaldos operativos ni documentos reales. No hay autenticación corporativa, autorización por roles, almacenamiento duradero ni revisión integral de seguridad. No usar como sistema institucional.
- Se excluyen las tres bases de la versión local, datos iniciales, talleres, resultados reales de madurez, archivos de referencia originales, escenarios históricos externos, PDF, scripts Windows y pruebas históricas con datos adjuntos. Se reconstruyen plantillas genéricas a partir de sus encabezados e instrucciones (sin estilos ni validaciones de las originales). Algunas descargas y cargas institucionales del Paso 02 al 04 no están disponibles en Cloud; se conserva la edición manual y los motores de cálculo. Las referencias PMI/PMOGA contenidas en catálogos deben ser autorizadas antes de alojarlas fuera de CENS.

## Aceptación tras desplegar

- Abrir Inicio y verificar el aviso permanente de laboratorio y la etiqueta Cloud Edition.
- Verificar los diez pasos, iconos y colores; abrir cada uno de los 53 componentes. Probar las nueve herramientas de Inicio.
- Consultar seis clientes ficticios y seis necesidades. Ejecutar una corrida V5 con ponderaciones de ensayo que sumen 100; no aprobar decisiones oficiales.
- Crear un registro ficticio, navegar a otro paso y regresar; abrir otra sesión (ventana privada con acceso autorizado) y comprobar que no comparte el registro. Reiniciar laboratorio con confirmación y comprobar la restauración de la semilla.
- Probar exportaciones y los componentes HTML interactivos del lienzo y Kanban. Consultar logs para diagnosticar errores.
- Mantener el acceso privado y comprobar que un usuario no autorizado no puede abrir la aplicación.

## Ensayo local opcional (sin editor)

Desde una terminal en la carpeta, con Python 3.13 y entorno virtual: `python -m pip install -r requirements.txt`; después `python -m streamlit run app.py`. Esta prueba usa el mismo laboratorio temporal, no la base local. La V1.0.0 local debe mantenerse aparte.

## Estado de entrega

Paquete preparado, **no publicado**. Pruebas específicas de código realizadas en Linux con Python 3.13.5. No se ha podido instalar Streamlit real en el entorno de validación; la revisión visual, el servidor Cloud y la aceptación funcional están pendientes. Consultar `QA_CLOUD.md`.
