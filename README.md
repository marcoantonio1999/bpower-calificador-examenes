# BPower · Calificador de exámenes

[![Descargar instalador para Windows](https://img.shields.io/badge/DESCARGAR_CALIFICADOR_PARA_WINDOWS-2357A5?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/marcoantonio1999/bpower-calificador-examenes/releases/download/v1.0.0/BPower-Calificador-Instalador.exe)

Aplicación independiente para Windows 10/11 de 64 bits. Selecciona una carpeta de exámenes PDF y genera un Excel con participantes, calificaciones y detalle por pregunta. No necesita Python, servidor ni Excel instalado para generar el archivo.

## Para Vero

1. Instala y abre **BPower Calificador de examenes**.
2. Carga las respuestas correctas: **Clave desde PDF resuelto** para el formulario BPower de opción múltiple, o **Cargar respuestas JSON / CSV** para una clave propia. También puedes crear o editar la clave en la app.
3. Selecciona una carpeta que contenga únicamente los PDF de los participantes, no el PDF maestro de respuestas. No se revisan subcarpetas.
4. Si hay preguntas abiertas, introduce **tu propia API key de OpenAI** y marca la autorización de envío de texto. La opción múltiple no usa IA ni necesita API key. No compartas tu clave por chat ni con los candidatos.
5. Pulsa **Calificar y generar Excel**. Abre el resultado con los botones de la app.

Se crea una carpeta nueva `Calificaciones-fecha-...` con **Calificaciones.xlsx**, **avance.json** y **LEEME.txt**. No se sobrescriben los PDF ni un Excel existente. La calificación es de 0 a 10, ponderada por los puntos de la clave. El Excel incluye una hoja de resultados y otra con respuesta, criterio, puntos y explicación por pregunta. Los teléfonos se conservan como texto, incluidos ceros iniciales.

## Formatos y límites

- **PDF rellenable BPower:** campos `nombre_completo`, `correo_electronico`, `telefono`, `fecha` y `pregunta_01`, `pregunta_02`, etc. Los campos de cada pregunta se pueden configurar en la clave. Un campo reconocido pero vacío cuenta como no contestado; un campo que no se encuentra deja la nota pendiente.
- **PDF digital con texto:** nombre/contacto con etiquetas `Nombre completo:`, `Correo:`, `Teléfono:`, `Fecha:`. Cada pregunta debe empezar en línea propia con `1.`, `2.`, etc., seguida de una línea **Respuesta:**. Las respuestas abiertas pueden continuar en varias líneas. No se adivina una selección por la mera presencia de las alternativas A/B/C/D.
- **Escaneos, fotos, marcas a mano o PDF aplanados sin marcadores de respuesta:** se señalan para revisión, no se asigna un cero inventado. No incluye OCR ni visión.
- PDF hasta 25 MB, 50 páginas, 250,000 caracteres y 30 segundos de lectura; respuesta individual hasta 15,000 caracteres; de 1 a 200 preguntas. Archivos ilegibles se documentan y se continúa con los demás.
- PDF con contenido idéntico dentro del mismo lote: duplicado omitido, sin volver a cobrar ni contar una nota nueva. No se unen personas sólo por nombre o teléfono.

## Respuestas correctas y preguntas abiertas

No se incluye una clave de respuestas real ni se inventa. Debe proporcionarla la persona responsable. Un PDF maestro resuelto se acepta sólo para opción múltiple con campos `pregunta_XX`, todos seleccionados. No debe ser el examen de un candidato.

El [CSV de ejemplo](examples/clave-mixta.csv) es **ficticio**. Puedes abrirlo en Excel, modificarlo y guardarlo como CSV UTF-8. Columnas: `id`, `type` (`choice` u `open`), `expected` (letra correcta o respuesta de referencia), `points`, `prompt` (enunciado obligatorio para abiertas), `rubric` y `field` (nombre del campo PDF). Para opción múltiple admite una única letra A-H. Cada pregunta necesita identificador único y puntos positivos.

Las abiertas utilizan **gpt-5.6-luna**, esfuerzo **low**, a través de Responses API con salida estructurada. No se sustituye silenciosamente por otro modelo. Si la cuenta no tiene acceso o saldo, el fallo queda visible. Sólo se manda el texto de preguntas abiertas, respuestas del participante y criterios; **no se suben PDF, imágenes ni campos separados de nombre, correo o teléfono**. El texto que el participante escriba dentro de una respuesta puede contener información personal: revisa tus reglas de privacidad antes de autorizar.

La API key se mantiene en memoria durante la ejecución, no se lee del entorno y nunca se guarda en configuración, caché, Excel ni Git. El campo se limpia al terminar el lote o cerrar la app. Cada usuario proporciona su propia clave. Se solicita `store=false`; esto no equivale a prometer retención cero por parte del proveedor.

No hay reintentos automáticos ni tareas programadas. Si una consulta API falla, las siguientes abiertas quedan pendientes en ese lote; las cerradas se siguen calificando. Puedes revisar el fallo e iniciar otra ejecución manualmente. Una caché SQLite local reutiliza calificaciones de respuestas idénticas con el mismo enunciado, referencia, rúbrica, puntos y modelo. Cambiar esos criterios obliga a una nueva evaluación. Las respuestas fallidas no se guardan como calificaciones válidas.

**Revisión humana:** las notas de IA son preliminares y pueden equivocarse. El Excel conserva el detalle para revisarlas; no toma decisiones automáticas de contratación ni evalúa rasgos personales. Una nota vacía significa pendiente, no cero. Si falta el nombre también se marca para revisión. No hay umbral de aprobación/rechazo inventado.

## Privacidad

Los exámenes, claves de respuestas, resultados y `.bpower-examenes-cache.sqlite3` contienen información privada; guárdalos en una carpeta con acceso restringido. El repositorio y el instalador contienen sólo código y ejemplos ficticios. No hay telemetría, descarga automática de componentes ni almacenamiento en servidores de BPower. La única comunicación externa ocurre al autorizar calificación de abiertas y pulsar Calificar.

Instalador por usuario en `%LOCALAPPDATA%/BPower-Calificador-Examenes`; acceso directo en escritorio e Inicio. Independiente de las apps OCC/Indeed. No tiene firma digital: si Windows lo bloquea, pide ayuda al responsable; no desactives las protecciones.

## Pruebas y desarrollo

Python 3.12+, Tkinter y dependencias de `requirements.txt`. ReportLab se utiliza únicamente para crear PDF ficticios de prueba, no se empaqueta en la app.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -v
powershell -File build.ps1
```

El ejecutable admite `--self-test ruta.txt`: comprueba lectura de dos PDF ficticios, resultados 10/10 y 4/10 y generación de Excel sin conectarse a OpenAI. Las pruebas de IA usan un transporte simulado con el formato Responses, verifican razonamiento bajo, privacidad del payload, límites de puntuación, errores HTTP, ausencia de reintentos y caché. **No se ha ejecutado una evaluación real pagada con una API key del usuario.**

Documentación técnica: [Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna), [reasoning](https://developers.openai.com/api/docs/guides/reasoning), [salida estructurada](https://developers.openai.com/api/docs/guides/structured-outputs).
