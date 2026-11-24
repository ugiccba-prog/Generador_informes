"""Motor híbrido de redacción clínica usando google-genai (Interactions API) y Gemini 4."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import tempfile
import tomllib

from google import genai

from catalogo_clinico import INTRODUCCIONES_DOMINIOS, MODELOS_GEMINI

MAX_INLINE_PDF_BYTES = 12 * 1024 * 1024  # 12 MB
DEFAULT_MAX_OUTPUT_TOKENS = 32768


def resolver_api_key(streamlit_secrets=None, secrets_file: Path | None = None) -> str:
    """Obtiene GEMINI_API_KEY de st.secrets, variables de entorno o secrets.toml local."""
    if streamlit_secrets is not None:
        try:
            val = streamlit_secrets.get("GEMINI_API_KEY", "")
            if isinstance(val, str) and val.strip():
                return val.strip()
        except Exception:
            pass

    env_key = os.environ.get("GEMINI_API_KEY", "")
    if env_key and env_key.strip():
        return env_key.strip()

    target_file = (
        secrets_file
        if secrets_file is not None
        else Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    )
    try:
        if target_file.exists():
            with open(target_file, "rb") as f:
                val = tomllib.load(f).get("GEMINI_API_KEY", "")
                if isinstance(val, str) and val.strip():
                    return val.strip()
    except Exception:
        pass

    return ""


def construir_system_prompt() -> str:
    """Construye el system prompt clínico con las 9 franjas simétricas Z y reglas clínicas."""
    return f"""
Actuás como un Motor Experto de Redacción Clínica Neuropsicológica y Psicopedagógica.
Tu objetivo es redactar informes clínicos impecables, formales, en tercera persona y listos para entregar, combinando reglas psicométricas estrictas con tu capacidad de análisis clínico para interpretar matices, cruzar datos conductuales con puntajes y explicar disociaciones.

PROHIBICIÓN ESTRICTA DE PRIVACIDAD Y FIDELIDAD CUANTITATIVA:
- NUNCA menciones nombres de clínicas, hospitales ni nombres de profesionales que no sean los que el usuario ingresó explícitamente en los datos del caso actual.
- NUNCA inventes, recalcules ni modifiques los puntajes obtenidos, puntajes Z ni rangos clínicos provistos en la Grilla Cuantitativa. Respetá con exactitud matemática los valores suministrados.
- Si algún dato puntual del paciente falta, colocá `[Completar]` sin inventar información clínica.

---
### 1. ESCALA NORMATIVA UNIFICADA Y GRILLA Z (-3 a +3) — 9 FRANJAS SIMÉTRICAS
Clasificación obligatoria para la tabla cuantitativa y la redacción:
- **Déficit**: Z <= -2.33 | PE: 1 a 3 | CI: <= 65 | T directo: <= 27 | T inverso (CPT/Nesplora/BRIEF): >= 73 | Pc < 1
- **Limítrofe (Dificultad / Déficit)**: Z de -2.32 a -2.01 | PE: ~3 a 4 | CI: 66 a 69 | T directo: 28 a 29 | T inverso: 71 a 72 | Pc ~1 a 2
- **Dificultad**: Z de -2.00 a -1.33 | PE: 4 a 6 | CI: 70 a 80 | T directo: 30 a 37 | T inverso: 63 a 70 | Pc 2 a 9
- **Normal (Tendencia baja)**: Z de -1.32 a -1.01 | PE: ~6 a 7 | CI: 81 a 84 | T directo: 38 a 39 | T inverso: 61 a 62 | Pc 10 a 15
- **Normal**: Z de -1.00 a +1.00 | PE: 7 a 13 | CI: 85 a 115 | T: 40 a 60 | Pc 16 a 84
- **Normal (Tendencia alta)**: Z de +1.01 a +1.32 | PE: ~13 a 14 | CI: 116 a 119 | T directo: 61 a 62 | T inverso: 38 a 39 | Pc 85 a 90
- **Normal Alto**: Z de +1.33 a +2.00 | PE: 14 a 16 | CI: 120 a 130 | T directo: 63 a 70 | T inverso: 30 a 37 | Pc 91 a 98
- **Normal Alto (Tendencia superior)**: Z de +2.01 a +2.32 | PE: ~16 a 17 | CI: 131 a 134 | T directo: 71 a 72 | T inverso: 28 a 29 | Pc 98 a 99
- **Superior**: Z >= +2.33 | PE: 17 a 19 | CI: >= 135 | T directo: >= 73 | T inverso: <= 27 | Pc > 99

En el cuerpo del análisis cualitativo, destacá siempre en **negrita** los calificadores de rendimiento (**adecuado**, **acorde a lo esperado para su edad**, **dentro de los límites esperados**, **tendencia baja**, **dificultades**, **por debajo de lo esperado**, **descenso**, **limítrofe**, **déficit**, **rango promedio**, **rango promedio alto**, **superior**).

---
### 2. INTRODUCCIONES TEÓRICAS EN CURSIVA (TEXTO LITERAL OBLIGATORIO)
Al comenzar cada dominio evaluado en la sección de análisis cualitativo, insertá textualmente el párrafo introductorio en cursiva correspondiente antes de desarrollar los resultados del paciente:

- **Funcionamiento Intelectual:** {INTRODUCCIONES_DOMINIOS["intelectual"]}
- **Memoria y Aprendizaje:** {INTRODUCCIONES_DOMINIOS["memoria"]}
- **Alerta y Atención:** {INTRODUCCIONES_DOMINIOS["atencion"]}
- **Funciones Ejecutivas:** {INTRODUCCIONES_DOMINIOS["ejecutivas"]}
- **Procesamiento Visomotor:** {INTRODUCCIONES_DOMINIOS["visomotor"]}
- **Lenguaje:** {INTRODUCCIONES_DOMINIOS["lenguaje"]}

---
### 3. ESTRUCTURA Y REGLAS CLÍNICAS POR PRUEBA
1. **Estructura según el Modelo elegido:**
   - **Evaluación Neuropsicológica (Versión Desempeño Cognitivo):** Datos de filiación, Motivo de consulta, Métodos de evaluación y procedimientos, Observación de la conducta, Tabla/Grilla cuantitativa Z, Análisis de Funcionamiento Intelectual, Conclusiones y Recomendaciones (Terapéuticas/Generales y Para la escuela).
   - **Evaluación Neuropsicológica Completa:** Igual al anterior pero desarrollando todos los dominios administrados (Funcionamiento Intelectual, Memoria y Aprendizaje, Alerta y Atención, Funciones Ejecutivas, Visomotor, Lenguaje) y Cuestionarios si aplican.
   - **Evaluación Psicopedagógica:** Usa el subtítulo **"Técnicas implementadas"** y organiza el análisis en: **Perfil psicopedagógico, Cálculo, Lectura (PROLEC), Escritura, Ortografía y Lenguaje**.
   - **Combinado:** Integra los dominios neuropsicológicos seguidos de los apartados psicopedagógicos y cuestionarios.
2. **Criterios de Interpretación de Baterías:**
   - **Wechsler (WISC-V / WPPSI-IV / WAIS-IV):** Analizar CIT e índices primarios (ICV, IVE, IRF, IMT, IVP). Si existe marcada dispersión inter-índices (ej. descenso en IMT o IVP), informar e interpretar el **ICG (Índice de Capacidad General)** como medida más representativa de su potencial intelectual. Si hay índices secundarios (IRC, IMTA, ICC), desarrollarlos en párrafos propios.
   - **Memoria (TOMAL, WRAML, RAVLT, Rey):** Contrastar memoria verbal (narrativa vs. lista de palabras, curva de aprendizaje, retención diferida) y memoria visual (abstracta y reproducción/reconocimiento de Figura de Rey).
   - **Atención y FFEE (CPT-II, Nesplora Aula, NEPSY-II, Stroop, TMT A y B, WCST):**
     - En **CPT-II** consignar siempre el *Índice de Confianza Clínico (%)* si figura en los datos o adjuntos. Un puntaje T muy bajo (< 40) en **Tiempo de Reacción (Hit RT)** indica respuestas atípicamente rápidas/impulsivas (no desempeño "Superior"): interpretarlo en articulación con Comisiones.
     - En **Nesplora Aula** detallar rendimiento con/sin distractores, canal visual vs. auditivo y actividad motora.
     - En **TMT, Stroop y WCST** analizar flexibilidad cognitiva, atención dividida, velocidad y control inhibitorio.
   - **Pruebas Psicopedagógicas (Woodcock-Muñoz, PROLEC-R/SE-R, TEMA-3, TOMA-3, NALPA, EPL, Ortografía Feldman, Dictado):**
     - Si se administra **Woodcock-Muñoz**, informar Puntaje Bruto y Edad Equivalente, e incluir SIEMPRE esta nota literal: *"Nota: La Batería Woodcock-Muñoz no se encuentra estandarizada para nuestra población, por lo que sus valores deben ser considerados como orientativos."*
     - Incluir de forma literal entre comillas los ejemplos de escritura (NALPA/dictado) o errores de cálculo provistos por el profesional.
3. **Conclusiones y Cierre Médico-Legal:**
   - Integrar fortalezas y debilidades del perfil.
   - Cerrar las conclusiones con la siguiente fórmula profesional: *"En síntesis, estos indicadores caracterizan a [Nombre] con un perfil compatible con [describir perfil]. El diagnóstico definitivo quedará a cargo del médico tratante a partir de la integración clínica de los presentes hallazgos."*
4. **Sección Final de Recomendaciones (Obligatoria y Detallada):**
   - Dividir siempre en dos bloques claros con viñetas bien redactadas:
     1) **Recomendaciones terapéuticas y generales**
     2) **Recomendaciones para la escuela (Adaptaciones de acceso y contexto)**
5. **Formato de Salida (Markdown limpio para exportación Word):**
   - Utilizá encabezados Markdown jerárquicos (`#` título principal, `##` secciones, `###` subsecciones), tablas Markdown estándar para Datos de Filiación y Grilla Cuantitativa Z, `*cursiva*` solo donde corresponda (introducciones teóricas y notas aclaratorias), `**negrita**` en calificadores clínicos y viñetas `- ` limpias. No encierres el informe dentro de bloques de código ```.
""".strip()


def _formatear_bloque_no_vacio(pares: list[tuple[str, str]], texto_vacio: str) -> str:
    lineas = []
    for etiqueta, valor in pares:
        val = (valor or "").strip()
        if val:
            lineas.append(f"- **{etiqueta}:** {val}")
    if not lineas:
        return f"- {texto_vacio}"
    return "\n".join(lineas)


def construir_prompt_caso(datos_caso: dict) -> str:
    """Construye el prompt del caso clínico omitiendo campos cualitativos vacíos."""
    modelos = datos_caso.get("modelos_seleccionados") or []
    pruebas = datos_caso.get("pruebas_usadas") or []

    nombre = (datos_caso.get("nombre") or "").strip() or "[Completar]"
    hc = (datos_caso.get("hc") or "").strip() or "[Completar]"
    edad = (datos_caso.get("edad_texto") or "").strip() or "[Completar]"
    fecha_nac = (datos_caso.get("fecha_nac") or "").strip() or "[Completar]"
    fecha_eval = (datos_caso.get("fecha_eval") or "").strip() or "[Completar]"
    escolaridad = (datos_caso.get("escolaridad") or "").strip() or "[Completar]"
    nacionalidad = (datos_caso.get("nacionalidad") or "").strip() or "[Completar]"
    preferencia = (datos_caso.get("preferencia") or "").strip() or "[Completar]"
    medico = (datos_caso.get("medico") or "").strip() or "[Completar]"
    firma = (datos_caso.get("firma_profesional") or "").strip() or "[Firma y Sello del Profesional]"
    acompanante = (datos_caso.get("acompanante") or "").strip() or "No especificado"

    quien_deriva = (datos_caso.get("quien_deriva") or "").strip() or "No especificado"
    antecedentes = (datos_caso.get("antecedentes") or "").strip() or "No consignados"

    conducta_dict = datos_caso.get("conducta") or {}
    bloque_conducta = _formatear_bloque_no_vacio(
        list(conducta_dict.items()),
        "No se consignaron indicadores conductuales específicos.",
    )

    tabla_z_markdown = (datos_caso.get("tabla_z_markdown") or "").strip()
    if not tabla_z_markdown:
        tabla_z_markdown = "No se completaron puntajes en la grilla interactiva."

    texto_puntajes_libre = (datos_caso.get("texto_puntajes_libre") or "").strip() or "Sin datos adicionales."

    obs_dict = datos_caso.get("observaciones_cualitativas") or {}
    bloque_cualitativo = _formatear_bloque_no_vacio(
        list(obs_dict.items()),
        "No se consignaron notas cualitativas adicionales por dominio.",
    )

    impresion = (datos_caso.get("impresion_destacar") or "").strip() or "Integrar según hallazgos del perfil."
    frecuencia = (datos_caso.get("frecuencia_y_control") or "").strip() or "A definir según evolución clínica."
    detalle_terapeuticas = (
        (datos_caso.get("detalle_terapeuticas") or "").strip()
        or "Adaptar automáticamente según el perfil clínico descrito."
    )
    detalle_escolares = (
        (datos_caso.get("detalle_escolares") or "").strip()
        or "Incluir pautas escolares acordes a las necesidades detectadas en el perfil."
    )
    recom_personalizadas = (datos_caso.get("recom_personalizadas") or "").strip()

    extra_recom_linea = (
        f"- **Sugerencias personalizadas adicionales:** {recom_personalizadas}\n"
        if recom_personalizadas
        else ""
    )

    return f"""
Redactá el INFORME CLÍNICO COMPLETO Y DEFINITIVO siguiendo la estructura y el estilo profesional del Sistema.

### 1. MODELO(S) DE INFORME A REDACTAR:
{', '.join(modelos) if modelos else 'Inferir según las pruebas administradas'}

### 2. DATOS DE FILIACIÓN:
- Apellido y Nombre: {nombre}
- DNI / HC: {hc}
- Edad: {edad}
- Fecha de nacimiento: {fecha_nac}
- Fecha de evaluación: {fecha_eval}
- Escolaridad: {escolaridad}
- Nacionalidad: {nacionalidad}
- Preferencia manual: {preferencia}
- Solicitante: {medico}
- Profesional Evaluador: {firma}
- Acompañante: {acompanante}

### 3. MOTIVO DE CONSULTA Y ANTECEDENTES:
- Motivo y derivación: {quien_deriva}
- Antecedentes y tratamientos: {antecedentes}

### 4. OBSERVACIÓN DE LA CONDUCTA:
{bloque_conducta}

### 5. PRUEBAS Y BATERÍAS ADMINISTRADAS:
{', '.join(pruebas) if pruebas else 'Ver puntuaciones y notas adjuntas'}

### 6. GRILLA DE PUNTUACIONES PROCESADAS (PUNTAJE Z Y RANGO CLÍNICO):
{tabla_z_markdown}

### 7. DATOS ADICIONALES DE PUNTUACIONES (TEXTO LIBRE / PLANILLA):
{texto_puntajes_libre}

### 8. OBSERVACIONES CUALITATIVAS POR DOMINIO:
{bloque_cualitativo}

### 9. CONCLUSIONES Y SUGERENCIAS FINALES OBLIGATORIAS:
- **Síntesis clínica a destacar en Conclusiones:** {impresion}
- **Frecuencia y control evolutivo:** {frecuencia}
- **Recomendaciones Terapéuticas y Generales a desarrollar:**
{detalle_terapeuticas}
- **Recomendaciones y Adaptaciones para la Escuela a desarrollar:**
{detalle_escolares}
{extra_recom_linea}- **Firma al pie del informe:** {firma}
""".strip()


def preparar_adjuntos_interaccion(
    archivos: list[dict] | None,
    client,
    max_inline_bytes: int | None = None,
) -> tuple[list[dict], list[str], list[str]]:
    """Convierte archivos adjuntos en bloques para Interactions API (PDF inline o Files API)."""
    bloques: list[dict] = []
    temp_paths: list[str] = []
    uploaded_names: list[str] = []

    if not archivos:
        return bloques, temp_paths, uploaded_names

    limite_inline = MAX_INLINE_PDF_BYTES if max_inline_bytes is None else max_inline_bytes

    for archivo in archivos:
        nombre = str(archivo.get("name") or "adjunto")
        raw_bytes = archivo.get("bytes") or b""
        if not raw_bytes:
            continue

        if nombre.lower().endswith(".pdf"):
            if len(raw_bytes) <= limite_inline:
                bloques.append(
                    {
                        "type": "document",
                        "data": base64.b64encode(raw_bytes).decode("utf-8"),
                        "mime_type": "application/pdf",
                    }
                )
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(raw_bytes)
                    tmp_path = tmp.name
                    temp_paths.append(tmp_path)
                uploaded = client.files.upload(file=tmp_path)
                uploaded_name = getattr(uploaded, "name", None)
                if uploaded_name:
                    uploaded_names.append(uploaded_name)
                bloques.append(
                    {
                        "type": "document",
                        "uri": uploaded.uri,
                        "mime_type": "application/pdf",
                    }
                )
        else:
            texto_archivo = raw_bytes.decode("utf-8", errors="replace")
            bloques.append(
                {
                    "type": "text",
                    "text": f"\n--- Archivo adjunto ({nombre}) ---\n{texto_archivo}\n",
                }
            )

    return bloques, temp_paths, uploaded_names


def extraer_texto_interaccion(interaction) -> str:
    """Extrae el texto final de un objeto Interaction de google-genai."""
    output_text = getattr(interaction, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    partes_texto: list[str] = []
    steps = getattr(interaction, "steps", None) or []
    for step in steps:
        step_type = step.get("type") if isinstance(step, dict) else getattr(step, "type", None)
        if step_type != "model_output":
            continue
        content = step.get("content") if isinstance(step, dict) else getattr(step, "content", None)
        for item in content or []:
            text_val = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if isinstance(text_val, str) and text_val.strip():
                partes_texto.append(text_val.strip())

    return "\n\n".join(partes_texto).strip()


def generar_informe_clinico(
    api_key: str,
    modelo: str,
    thinking_level: str,
    datos_caso: dict,
    archivos: list[dict] | None = None,
    store: bool = False,
) -> str:
    """Ejecuta la generación clínica mediante google-genai Interactions API."""
    key_limpia = (api_key or "").strip()
    if not key_limpia:
        raise ValueError("Se requiere una API Key de Gemini válida.")

    config_modelo = MODELOS_GEMINI.get(modelo)
    if config_modelo:
        niveles = config_modelo["thinking_levels"]
        nivel_efectivo = thinking_level if thinking_level in niveles else config_modelo["default_thinking"]
    else:
        nivel_efectivo = thinking_level or "high"

    client = genai.Client(api_key=key_limpia)
    temp_paths: list[str] = []
    uploaded_names: list[str] = []

    try:
        bloques_adjuntos, temp_paths, uploaded_names = preparar_adjuntos_interaccion(archivos, client)
        prompt_caso = construir_prompt_caso(datos_caso)
        input_blocks = bloques_adjuntos + [{"type": "text", "text": prompt_caso}]

        interaction = client.interactions.create(
            model=modelo,
            system_instruction=construir_system_prompt(),
            input=input_blocks,
            generation_config={
                "thinking_level": nivel_efectivo,
                "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
            },
            store=store,
        )

        texto = extraer_texto_interaccion(interaction)
        if not texto:
            raise RuntimeError("El modelo no devolvió contenido de texto.")
        return texto
    finally:
        for path in temp_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        for remote_name in uploaded_names:
            try:
                client.files.delete(name=remote_name)
            except Exception:
                pass
