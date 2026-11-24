# Generador de informes

Aplicación Streamlit para preparar borradores de evaluación neuropsicológica y psicopedagógica. Los puntajes cargados y la grilla orientativa Z se insertan desde la aplicación. El borrador se puede revisar y editar antes de descargarlo en Word o Markdown.

## Puesta en marcha

Requiere Python 3.11 o posterior.

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

El modo local arranca sin clave. Completá el formulario en orden. Cargá resultados y fuentes, describí los dominios que observaste y consigná las fortalezas, dificultades, impacto y límites que correspondan. Registrá qué hallazgos fundamentan las recomendaciones. El borrador indica cuando la integración profesional está pendiente. Si cambiás la ficha después de generar, la aplicación pide actualizar el borrador antes de descargar. Si registrás puntajes brutos o categorías, usá el manual correspondiente para verificar edición, edad o población normativa. La conversión Z para puntajes estandarizados es orientativa y se rige por la escala indicada en cada fila.

## Memoria de Drive

Usá la carpeta Memoria para consultar plantillas y localizar manuales. Una referencia de estilo sin datos de pacientes se puede pegar en **Guía de redacción**. Para cargarla directamente desde Drive:

1. Definí `MEMORIA_DRIVE_CARPETA_ID` con el ID de la carpeta para mostrar su acceso directo.
2. Prepará un Google Doc de una sola pestaña, con párrafos de estilo y estructura aprobados para ese uso. Definí su ID en `MEMORIA_DRIVE_GUIA_ID`. Ambos IDs pueden configurarse en el entorno o en `.streamlit/secrets.toml`.
3. Habilitá la API de Google Docs en el proyecto de Google Cloud. Configurá Application Default Credentials para una cuenta de servicio y compartí con ella únicamente el Google Doc de la guía, como lectora. Para desarrollo con credenciales en archivo, `GOOGLE_APPLICATION_CREDENTIALS` apunta al archivo privado fuera del repositorio.
4. Usá **Cargar guía de redacción de Drive**. Revisá el texto antes de incluirlo como referencia de estilo en Gemini. La aplicación lee el documento configurado mediante el alcance `documents.readonly`.

Los informes históricos, las planillas de casos y los manuales completos quedan en Drive para consulta según los permisos existentes. El repositorio es público y guarda únicamente código y documentación de uso.

## Redacción opcional con Gemini

Activá **Asistencia de redacción con Gemini**. Configurá `GEMINI_API_KEY` en el entorno o en los secretos de Streamlit, o ingresala en la sesión. Verificá qué modelos están habilitados para la clave. El envío requiere confirmación y se limita a las notas por dominio, la guía de estilo aprobada, los adjuntos revisados y los indicadores seleccionados para ese envío. El texto propuesto se incorpora solamente en los dominios con notas. Las extracciones de adjuntos se presentan en un apartado que pide cotejo con el original. Los campos de filiación, la grilla, las conclusiones y las recomendaciones se ensamblan en la aplicación. Revisá que las notas por dominio y adjuntos estén desidentificados antes de enviarlos. La opción `store=False` controla el almacenamiento de la interacción para recuperarla vía API. El tratamiento de los datos enviados se rige por los términos del servicio Gemini.

Probá el flujo con casos ficticios y ejecutá la app en un entorno privado. Revisá la fuente de los puntajes y el borrador completo antes de compartir un informe.

```sh
python -m unittest discover -s tests -v
```

## Indicadores psicométricos

En **Indicadores y controles psicométricos** aparecen controles de escala, edad, contrastes dentro de una batería y cálculos descriptivos. La amplitud de 23 puntos, la brecha ICG–ICC desde 12 y el ratio TMT B/A superior a 3 son señales de revisión. Usá los valores críticos y las tasas base del manual para las comparaciones normativas. Las alertas de memoria orientan qué contrastar con el protocolo y su baremo, y la cobertura de fotos se refiere al inventario de Memoria. Los cortes identificados como Planilla Memoria pertenecen a ese flujo y requieren corroborar edición, informante y norma. Vineland Forma B muestra el cociente sin tope y, por separado, el cociente y tramo de la Planilla Memoria con tope de edad de 25 años. Los nombres de los tramos inferiores se muestran como rangos de la escala histórica.

La calculadora distingue percentiles directos e inversos. Los porcentajes acumulados se registran con la categoría consignada por la fuente. Para calcular Stroop Golden cargá P, C y PC brutos. Para calcular TMT B/A y B−A cargá los segundos de ambas partes. Para Wechsler, ingresá ambas fechas para cotejar el rango etario.

## Adjuntos y Word

En modo asistido se aceptan PDF, PNG, JPG, JPEG, WebP, XLSX, DOCX, CSV y TXT, hasta 50 MB entre todos. Los adjuntos binarios usan un presupuesto inline de 12 MB. Si se supera, el archivo se carga temporalmente a Files API y se espera a que quede activo antes de pedir la redacción. Se intenta eliminar la copia temporal al finalizar, incluso ante fallos. De Excel se extraen filas con datos y valores calculados ya guardados. De Word se extraen párrafos y celdas. El banco de fraseo de Memoria se puede incorporar completo como guía revisada si es apto para el envío, sin incluirlo en el repositorio.

La grilla visual de Word trae 19 posiciones de −3 a +3 en tercios, con el valor original en la tabla de resultados. El membrete se activa al consignar institución o servicio. La nota de confidencialidad y alcance clínico es opcional.

Las opciones escolares de fluidez y seguimiento se apoyan en la [guía de intervención lectora de What Works Clearinghouse](https://ies.ed.gov/ncee/wwc/PracticeGuide/29) y requieren selección profesional según el caso.
