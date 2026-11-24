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

Activá **Asistencia de redacción con Gemini**. Configurá `GEMINI_API_KEY` en el entorno o en los secretos de Streamlit, o ingresala en la sesión. Verificá qué modelos están habilitados para la clave. El envío requiere confirmación y se limita a las notas por dominio, la guía de estilo aprobada para ese envío y los adjuntos revisados. El texto propuesto se incorpora solamente en los dominios con notas. Las extracciones de adjuntos se presentan en un apartado que pide cotejo con el original. Los campos de filiación, la grilla, las conclusiones y las recomendaciones se ensamblan en la aplicación. Revisá que las notas por dominio y adjuntos estén desidentificados antes de enviarlos. La opción `store=False` controla el almacenamiento de la interacción para recuperarla vía API. El tratamiento de los datos enviados se rige por los términos del servicio Gemini.

Probá el flujo con casos ficticios y ejecutá la app en un entorno privado. Revisá la fuente de los puntajes y el borrador completo antes de compartir un informe.

```sh
python -m unittest discover -s tests -v
```
