"""Motor híbrido de redacción y extracción clínica con google-genai (Interactions API)."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import tempfile
import time
import tomllib
from typing import List, Optional

from google import genai
from pydantic import BaseModel, Field

from catalogo_clinico import ESCALAS_DISPONIBLES, INTRODUCCIONES_DOMINIOS, MODELOS_GEMINI
from importador_archivos import extraer_texto_docx_compacto, extraer_texto_xlsx_compacto

MAX_INLINE_PDF_BYTES = 12 * 1024 * 1024  # 12 MB
DEFAULT_MAX_OUTPUT_TOKENS = 32768

_MIME_IMAGENES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class PuntajeExtraido(BaseModel):
    subtest: str = Field(description="Batería y subtest/índice, ej. 'WISC-V - Índice de Comprensión Verbal (ICV)'")
    puntaje: Optional[float] = Field(default=None, description="Puntaje numérico obtenido, o null si es solo cualitativo")
    escala: str = Field(description=f"Escala exacta entre: {', '.join(ESCALAS_DISPONIBLES)}")
    observacion: str = Field(default="", description="Notas breves (Edad Equivalente, categoría PROLEC, informante, etc.)")


class FiliacionExtraida(BaseModel):
    nombre: str = ""
    hc: str = ""
    fecha_nac: str = ""
    fecha_eval: str = ""
    edad_texto: str = ""
    escolaridad: str = ""
    nacionalidad: str = ""
    preferencia: str = ""
    medico: str = ""
    acompanante: str = ""


class NotasExtraidas(BaseModel):
    quien_deriva: str = ""
    antecedentes: str = ""
    obs_wechsler: str = ""
    obs_memoria: str = ""
    obs_atencion_fe: str = ""
    obs_viso_leng: str = ""
    obs_lectoescritura: str = ""
    obs_matematica: str = ""
    cuestionarios_txt: str = ""


class DatosExtraidosAdjuntos(BaseModel):
    filiacion: FiliacionExtraida = Field(default_factory=FiliacionExtraida)
    modelos_sugeridos: List[str] = Field(default_factory=list)
    pruebas_detectadas: List[str] = Field(default_factory=list)
    puntajes: List[PuntajeExtraido] = Field(default_factory=list)
    notas: NotasExtraidas = Field(default_factory=NotasExtraidas)
    advertencias_extraccion: List[str] = Field(default_factory=list)


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
    """Construye el system prompt clínico completo alineado con la base Memoria e investigación psicométrica."""
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
- **Déficit**: Z <= -2.33 | PE: 1 a 3 | CI: <= 65 | T directo: <= 27 | T inverso: >= 73 | Pc dir: < 1 | Pc inv: > 99
- **Limítrofe (Dificultad / Déficit)**: Z de -2.32 a -2.01 | PE: ~3 a 4 | CI: 66 a 69 | T directo: 28 a 29 | T inverso: 71 a 72 | Pc dir: ~1 a 2
- **Dificultad**: Z de -2.00 a -1.33 | PE: 4 a 6 | CI: 70 a 80 | T directo: 30 a 37 | T inverso: 63 a 70 | Pc dir: 2 a 9 | Pc inv: 91 a 98
- **Normal (Tendencia baja)**: Z de -1.32 a -1.01 | PE: ~6 a 7 | CI: 81 a 84 | T directo: 38 a 39 | T inverso: 61 a 62 | Pc dir: 10 a 15
- **Normal**: Z de -1.00 a +1.00 | PE: 7 a 13 | CI: 85 a 115 | T: 40 a 60 | Pc: 16 a 84
- **Normal (Tendencia alta)**: Z de +1.01 a +1.32 | PE: ~13 a 14 | CI: 116 a 119 | T directo: 61 a 62 | T inverso: 38 a 39 | Pc dir: 85 a 90
- **Normal Alto**: Z de +1.33 a +2.00 | PE: 14 a 16 | CI: 120 a 130 | T directo: 63 a 70 | T inverso: 30 a 37 | Pc dir: 91 a 98
- **Normal Alto (Tendencia superior)**: Z de +2.01 a +2.32 | PE: ~16 a 17 | CI: 131 a 134 | T directo: 71 a 72 | T inverso: 28 a 29 | Pc dir: 98 a 99
- **Superior**: Z >= +2.33 | PE: 17 a 19 | CI: >= 135 | T directo: >= 73 | T inverso: <= 27 | Pc dir: > 99

Escalas adicionales soportadas: `v-scale Vineland (M=15, DE=3)`, `Percentil Directo` (mayor = mejor), `Percentil Inverso` (mayor = peor, ej. errores en Nesplora Aula).

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
   - **Evaluación Neuropsicológica Completa:** Igual al anterior pero desarrollando todos los dominios administrados (Funcionamiento Intelectual, Memoria y Aprendizaje, Alerta y Atención, Funciones Ejecutivas, Visomotor, Lenguaje) y Cuestionarios / Vineland / DIVA-5 si aplican.
   - **Evaluación Psicopedagógica:** Usa el subtítulo **"Técnicas implementadas"** y organiza el análisis en: **Perfil psicopedagógico, Cálculo, Lectura (PROLEC), Escritura, Ortografía y Lenguaje**.
   - **Combinado:** Integra los dominios neuropsicológicos seguidos de los apartados psicopedagógicos y cuestionarios.
2. **Criterios de Interpretación Psicométrica:**
   - **Wechsler (WISC-V / WPPSI-IV / WAIS-IV):** Analizar CIT e índices primarios (ICV, IVE/IRP, IRF, IMT, IVP). Si hay marcada dispersión inter-índices (ej. `>= 23 pts` o descenso en IMT/IVP), explicar que el CIT puede no ser unitario e informar el **ICG (Índice de Capacidad General)** como medida más fiel del potencial razonador, contrastándolo con **ICC** si está disponible. Desarrollar índices secundarios (IRC, IMTA, INV, ICC) en párrafos específicos si se consignan.
   - **Memoria (TOMAL, WRAML, RAVLT, Rey):** Contrastar memoria verbal (narrativa vs. lista de palabras, curva `A1-A5`, interferencia `B1`, retención `A7/A5`, reconocimiento) y memoria visual (TOMAL abstracta y Figura de Rey: tipo de copia de Osterrieth I-VII, memoria inmediata/diferida y reconocimiento de 12 elementos + falsos positivos). Diferenciar fallas de **codificación**, **consolidación** y **recuperación**.
   - **Atención y FFEE (CPT-II, Nesplora Aula, NEPSY-II, Stroop, TMT A y B, WCST):**
     - En **CPT-II** consignar el *Índice de Confianza Clínico (%)* si figura en los datos/adjuntos. Un puntaje T `< 40` en **Tiempo de Reacción (Hit RT)** indica respuestas atípicamente rápidas/impulsivas (NUNCA lo llames "Superior"), y debe articularse con Comisiones. Si hay Omisiones muy altas (`T >= 65`) y Comisiones bajas (`T <= 45`), considerar posible desconexión atencional sostenida.
     - En **Nesplora Aula** detallar rendimiento global y contrastar **con/sin distractores**, **canal visual vs. auditivo**, **tarea simple (NO) vs. compleja (SI)** y actividad motora.
     - En **WCST (Heaton)** recordar que los T normativos mayores implican menos errores perseverativos (mejor flexibilidad). En **Stroop** y **TMT** analizar interferencia y ratio `B/A` si están informados.
   - **Pruebas Psicopedagógicas (Woodcock-Muñoz, PROLEC-R/SE-R, TEMA-3, TOMA-3, NALPA, EPL, Ortografía Feldman, Dictado):**
     - Si se administra **Woodcock-Muñoz**, informar Puntaje Bruto y Edad/Grado Equivalente, e incluir SIEMPRE esta nota literal: *"Nota: La Batería Woodcock-Muñoz no se encuentra estandarizada para nuestra población, por lo que sus valores deben ser considerados como orientativos."*
     - En **PROLEC-R** organizar en **Índices Principales, Precisión y Velocidad**, diferenciando **ruta léxica (palabras)** y **ruta fonológica (pseudopalabras)**.
     - En **Ortografía Feldman** discriminar errores (*disléxicos, disengramas, códigos, ortografía*) señalando las tasas `> 5%` como significativas. Incluir literalmente entre comillas los ejemplos de escritura (NALPA/dictado) o errores de cálculo provistos.
   - **Cuestionarios, Vineland y DIVA-5:**
     - **BRIEF:** `T 65-69` potencialmente clínico, `T >= 70` clínicamente elevado. **SNAP-IV:** cortes `>= 15` (Desatención) y `>= 16` (H/I). **Autoestima:** `<= 12` significativo. **Durand:** identificar función mantenedora predominante. **DIVA-5:** verificar criterios DSM-5 (`>= 5/9` adultez, `>= 6/9` infancia antes de los 12 años, `>= 2` ámbitos). **Vineland:** integrar dominios/v-scale o Cociente Social de Forma B.
3. **Conclusiones y Cierre Médico-Legal:**
   - Integrar fortalezas y debilidades del perfil.
   - Cerrar las conclusiones con la siguiente fórmula profesional: *"En síntesis, estos indicadores caracterizan a [Nombre] con un perfil compatible con [describir perfil]. El diagnóstico definitivo quedará a cargo del médico tratante a partir de la integración clínica de los presentes hallazgos."*
4. **Sección Final de Recomendaciones (Obligatoria y Detallada):**
   - Dividir siempre en dos bloques claros con viñetas bien redactadas:
     1) **Recomendaciones terapéuticas y generales**
     2) **Recomendaciones para la escuela (Adaptaciones de acceso y contexto)**
5. **Formato de Salida (Markdown limpio para exportación Word):**
   - Utilizá encabezados Markdown jerárquicos (`#` título principal, `##` secciones, `###` subsecciones), tablas Markdown estándar para Datos de Filiación y Grilla Cuantitativa Z, `*cursiva*` solo donde corresponda, `**negrita**` en calificadores clínicos y viñetas `- ` limpias. No encierres el informe dentro de bloques de código ```.
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

    analisis_clinico_md = (datos_caso.get("analisis_clinico_markdown") or "").strip()
    if not analisis_clinico_md:
        analisis_clinico_md = "Sin alertas o disociaciones automáticas destacadas."

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

### 8B. ANÁLISIS PSICOMÉTRICO DETERMINISTA Y ALERTAS DETECTADAS (VERIFICADAS POR SISTEMA):
{analisis_clinico_md}

### 9. CONCLUSIONES Y SUGERENCIAS FINALES OBLIGATORIAS:
- **Síntesis clínica a destacar en Conclusiones:** {impresion}
- **Frecuencia y control evolutivo:** {frecuencia}
- **Recomendaciones Terapéuticas y Generales a desarrollar:**
{detalle_terapeuticas}
- **Recomendaciones y Adaptaciones para la Escuela a desarrollar:**
{detalle_escolares}
{extra_recom_linea}- **Firma al pie del informe:** {firma}
""".strip()


def _esperar_archivo_activo(
    client,
    file_name: str,
    max_wait_s: float = 90.0,
    poll_interval: float = 2.0,
) -> None:
    """Espera a que un archivo subido por Files API pase a estado ACTIVE."""
    if not file_name or not hasattr(client.files, "get"):
        return

    deadline = time.monotonic() + max_wait_s
    while True:
        info = client.files.get(name=file_name)
        state_obj = getattr(info, "state", None)
        if state_obj is None:
            return
        name_attr = getattr(state_obj, "name", None)
        if isinstance(name_attr, str):
            state_str = name_attr
        elif isinstance(state_obj, str):
            state_str = state_obj
        else:
            return
        state_upper = state_str.strip().upper()
        if state_upper in ("ACTIVE", "STATE_ACTIVE", ""):
            return
        if "FAILED" in state_upper:
            raise RuntimeError(f"Error al procesar el archivo subido ({file_name}): estado {state_str}.")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Tiempo de espera agotado al procesar el archivo ({file_name}).")
        time.sleep(poll_interval)


def preparar_adjuntos_interaccion(
    archivos: list[dict] | None,
    client,
    max_inline_bytes: int | None = None,
) -> tuple[list[dict], list[str], list[str]]:
    """Convierte PDFs, imágenes, Excel, Word y CSV/TXT en bloques para Interactions API."""
    bloques: list[dict] = []
    temp_paths: list[str] = []
    uploaded_names: list[str] = []

    if not archivos:
        return bloques, temp_paths, uploaded_names

    limite_inline = MAX_INLINE_PDF_BYTES if max_inline_bytes is None else max_inline_bytes

    for archivo in archivos:
        nombre = str(archivo.get("name") or "adjunto")
        nombre_lower = nombre.lower()
        raw_bytes = archivo.get("bytes") or b""
        if not raw_bytes:
            continue

        ext = Path(nombre_lower).suffix
        if ext == ".pdf":
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
                if isinstance(uploaded_name, str) and uploaded_name:
                    uploaded_names.append(uploaded_name)
                    _esperar_archivo_activo(client, uploaded_name)
                bloques.append(
                    {
                        "type": "document",
                        "uri": uploaded.uri,
                        "mime_type": "application/pdf",
                    }
                )
        elif ext in _MIME_IMAGENES:
            bloques.append(
                {
                    "type": "image",
                    "data": base64.b64encode(raw_bytes).decode("utf-8"),
                    "mime_type": _MIME_IMAGENES[ext],
                }
            )
        elif ext == ".xlsx":
            bloques.append(
                {
                    "type": "text",
                    "text": extraer_texto_xlsx_compacto(raw_bytes, nombre),
                }
            )
        elif ext == ".docx":
            bloques.append(
                {
                    "type": "text",
                    "text": extraer_texto_docx_compacto(raw_bytes, nombre),
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


def _limpiar_recursos_temporales(client, temp_paths: list[str], uploaded_names: list[str]) -> None:
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


def extraer_datos_de_adjuntos(
    api_key: str,
    archivos: list[dict],
    modelo: str = "gemini-4-hydrogen",
    store: bool = False,
) -> DatosExtraidosAdjuntos:
    """Extrae filiación, baterías, puntajes y notas clínicas en JSON estructurado desde adjuntos."""
    key_limpia = (api_key or "").strip()
    if not key_limpia:
        raise ValueError("Se requiere una API Key de Gemini válida.")
    if not archivos:
        raise ValueError("Adjuntá al menos un archivo (PDF, imagen, Excel, Word o CSV) para extraer datos.")

    client = genai.Client(api_key=key_limpia)
    temp_paths: list[str] = []
    uploaded_names: list[str] = []

    instruccion_extraccion = (
        "Sos un asistente clínico de extracción psicométrica de alta precisión. "
        "Extraé ÚNICAMENTE los datos presentes de manera explícita en los archivos o imágenes adjuntas. "
        "NUNCA inventes puntajes, edades ni diagnósticos. "
        f"En el campo 'escala', elegí exactamente una de las siguientes opciones: {ESCALAS_DISPONIBLES}. "
        "Recordá que en Nesplora Aula (Omisiones, Comisiones, Actividad Motora, Variabilidad) un Percentil alto indica más errores -> usá 'Percentil Inverso - Mayor es peor/error (Pc 1 a 99)', y en puntajes T de CPT-II, Nesplora o BRIEF usá 'T Inverso - Mayor es peor/error (M=50, DE=10)'. "
        "Si algún número está borroso, cortado o ambiguo, no lo adivines y agregá una nota en 'advertencias_extraccion'."
    )

    try:
        bloques_adjuntos, temp_paths, uploaded_names = preparar_adjuntos_interaccion(archivos, client)
        input_blocks = bloques_adjuntos + [
            {
                "type": "text",
                "text": "Extraé los datos de filiación, baterías administradas, puntajes cuantitativos y observaciones clínicas relevantes de los adjuntos.",
            }
        ]

        interaction = client.interactions.create(
            model=modelo,
            system_instruction=instruccion_extraccion,
            input=input_blocks,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": DatosExtraidosAdjuntos.model_json_schema(),
            },
            generation_config={
                "thinking_level": "medium",
                "max_output_tokens": 16384,
            },
            store=store,
        )

        json_raw = extraer_texto_interaccion(interaction)
        if not json_raw:
            raise RuntimeError("El modelo no devolvió datos extraídos.")
        json_limpio = re.sub(r"^```(?:json)?\s*|\s*```$", "", json_raw.strip(), flags=re.IGNORECASE)
        return DatosExtraidosAdjuntos.model_validate_json(json_limpio)
    finally:
        _limpiar_recursos_temporales(client, temp_paths, uploaded_names)


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
        _limpiar_recursos_temporales(client, temp_paths, uploaded_names)
