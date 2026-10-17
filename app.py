import streamlit as st
import google.generativeai as genai
import pandas as pd
import tempfile
import os

# =====================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y BASE DE CONOCIMIENTO CLÍNICA
# =====================================================================
st.set_page_config(
    page_title="Generador Profesional de Informes Clínicos",
    page_icon="🧠",
    layout="wide"
)

# Introducciones teóricas en cursiva (Base de Conocimiento Clínica)
INTRODUCCIONES_DOMINIOS = {
    "intelectual": (
        "*La evaluación del funcionamiento intelectual mediante la Escala de Inteligencia de Wechsler "
        "(WISC-V / WPPSI-IV / WAIS-IV) permite obtener una estimación de la capacidad cognitiva general "
        "del paciente, así como explorar su desempeño en dominios específicos que subyacen al "
        "aprendizaje y la resolución de problemas.*"
    ),
    "memoria": (
        "*La memoria consiste en una serie de procesos cognitivos: la codificación (procesamiento inicial "
        "de la información), almacenamiento (retención de la información mediante la consolidación) y "
        "evocación (capacidad de acceder a la información almacenada). A su vez, según el contenido a "
        "memorizar, la memoria puede ser subdividida en memoria verbal (palabras, frases y textos) y "
        "memoria visual (dibujos, fotos, etc.).*"
    ),
    "atencion": (
        "*La atención es un proceso complejo que involucra selección, vigilancia y control. Requiere de "
        "focalización en un estímulo, la inhibición de estímulos irrelevantes y la capacidad de sostener "
        "la atención en el tiempo en diferentes tareas. Si bien nos referimos a la atención de manera "
        "global existen diferentes tipos. La atención selectiva, es la capacidad para seleccionar entre "
        "varias posibles la información relevante que se va a procesar. La atención sostenida es la "
        "capacidad para mantener la atención en una misma actividad durante un prolongado periodo de "
        "tiempo. La atención dividida es la capacidad de realizar la selección de más de una información "
        "a la vez o de más de un proceso o esquema de acción simultáneamente. El normal funcionamiento "
        "de estos aspectos va a permitir ejecutar y mantener una conducta dirigida hacia una "
        "meta frente a eventuales distractores.*"
    ),
    "ejecutivas": (
        "*Las funciones ejecutivas son un conjunto de habilidades cognitivas de alto orden que permiten "
        "la anticipación y el establecimiento de metas, el diseño de planes y programas, el inicio de las "
        "actividades y de las operaciones mentales, la autorregulación y la monitorización de las tareas, "
        "la selección precisa de los comportamientos y las conductas, la flexibilidad en el trabajo "
        "cognoscitivo y su organización en el tiempo y en el espacio para obtener resultados eficaces en "
        "la resolución de problemas.*"
    ),
    "visomotor": (
        "*Las habilidades visoconstructivas y visomotoras implican la capacidad de integrar la percepción "
        "visual con la respuesta motriz fina para planificar, organizar y reproducir diseños espaciales "
        "de diversa complejidad.*"
    ),
    "lenguaje": (
        "*El lenguaje es un sistema complejo de símbolos que permite la comunicación interpersonal y actúa "
        "como mediador fundamental del pensamiento, el aprendizaje escolar y la autorregulación conductual.*"
    )
}

# Banco Maestro de Sugerencias y Recomendaciones Clínicas y Escolares
BANCO_SUGERENCIAS = {
    "terapeuticas": {
        "Devolución médica": "Compartir el presente informe con el médico derivante/tratante a fin de evaluar las conductas terapéuticas a seguir.",
        "Tratamiento Psicopedagógico": "Iniciar/continuar tratamiento psicopedagógico con orientación neurocognitiva, orientado a estimular los procesos atencionales, funciones ejecutivas (planificación, organización, monitoreo y memoria de trabajo) y estrategias de aprendizaje.",
        "Psicoterapia Cognitivo-Conductual (TCC) y Orientación a Padres": "Iniciar/continuar espacio de tratamiento psicológico con orientación cognitivo-conductual (TCC) junto con entrevistas periódicas de orientación a padres, para brindar herramientas de autorregulación emocional, tolerancia a la frustración, control de impulsos y organización de rutinas en el hogar.",
        "Terapia Ocupacional (Integración Sensorial)": "Realizar evaluación/tratamiento de Terapia Ocupacional con enfoque en Integración Sensorial y praxias visomotoras para abordar la regulación motora, la postura y la grafomotricidad.",
        "Neurolingüística / Fonoaudiología": "Realizar interconsulta con el área de Neurolingüística / Fonoaudiología para profundizar la evaluación y el abordaje de los aspectos fonológicos, comprensivos y expresivos del lenguaje.",
        "Maestra de Apoyo a la Inclusión (MAI)": "Evaluar la incorporación de dispositivo de apoyo a la inclusión escolar para acompañar la organización de la tarea en el aula y mediar en las adaptaciones pedagógicas.",
        "Control evolutivo / Reevaluación": "Realizar una reevaluación neuropsicológica/psicopedagógica de control en el plazo de 12 a 18 meses para monitorear su evolución."
    },
    "escolares": {
        "Ubicación y control de distractores": "Ubicar al alumno/a en los primeros bancos, cerca del docente y lejos de estímulos distractores (ventanas, puertas o zonas de alto tránsito), manteniendo su escritorio despejado únicamente con los materiales necesarios para la actividad en curso.",
        "Segmentación de consignas": "Brindar consignas breves, claras y secuenciadas de a un paso por vez. Asegurar el contacto visual al darle una indicación y verificar la comprensión pidiéndole que explique con sus propias palabras lo que debe realizar.",
        "Gestión del tiempo y fragmentación de tareas": "Fragmentar las tareas extensas o evaluaciones en bloques más cortos, otorgando tiempo adicional para su resolución y priorizando la calidad conceptual por sobre la cantidad de ejercicios mecánicos repetitivos.",
        "Apoyos visuales y funciones ejecutivas": "Implementar apoyos visuales, agendas anticipatorias, uso de calendarios a la vista y listas de chequeo (checklists) para la organización de materiales, entregas y armado de la mochila.",
        "Pausas activas y regulación motora": "Permitir breves pausas activas programadas y funcionales dentro del ámbito escolar (ej. borrar el pizarrón, repartir material o llevar un recado) cuando se observe fatiga cognitiva o inquietud motora.",
        "Adaptaciones en Lectoescritura": "Priorizar la evaluación oral o el uso de formatos estructurados (opción múltiple, unir con flechas, completar palabras clave) para evitar que la fatiga lectora o grafomotora penalice la demostración de conocimientos. No exponer a la lectura en voz alta frente al grupo sin preparación previa.",
        "Adaptaciones en Matemática y Cálculo": "Permitir el uso de apoyos concretos, tabla pitagórica, grillas numéricas o calculadora en resoluciones complejas, a fin de no penalizar el razonamiento lógico-matemático por fallas en la memoria operativa o en la automatización del cálculo.",
        "Refuerzo positivo y motivación": "Reforzar positivamente sus logros y el esfuerzo sostenido durante el proceso de trabajo, evitando la sobrecorrección punitiva frente al error para preservar su autoestima académica."
    }
}

# =====================================================================
# 2. FUNCIONES DE CONVERSIÓN PSICOMÉTRICA A PUNTAJE Z
# =====================================================================
def calcular_z_y_rango(valor: float, tipo_escala: str):
    if tipo_escala == "CI / Estándar (M=100, DE=15)":
        z = (valor - 100.0) / 15.0
    elif tipo_escala == "Escalar (M=10, DE=3)":
        z = (valor - 10.0) / 3.0
    elif tipo_escala == "T Directo - Mayor es mejor (M=50, DE=10)":
        z = (valor - 50.0) / 10.0
    elif tipo_escala == "T Inverso - Mayor es peor/error (M=50, DE=10)":
        z = (50.0 - valor) / 10.0
    else:
        z = valor

    z = round(z, 2)
    if z <= -2.33:
        rango = "Déficit"
    elif z <= -1.33:
        rango = "Dificultad"
    elif z <= 1.00:
        rango = "Normal"
    elif z <= 2.00:
        rango = "Normal Alto"
    elif z >= 2.33:
        rango = "Superior"
    else:
        rango = "Normal (Tendencia baja)" if z < 0 else "Normal (Tendencia alta)"

    return z, rango


# =====================================================================
# 3. PROMPT MAESTRO DEL SISTEMA (HÍBRIDO: BASE DE CONOCIMIENTO + GEMINI)
# =====================================================================
def construir_system_prompt():
    return f"""
Actuás como un Motor Experto de Redacción Clínica Neuropsicológica y Psicopedagógica.
Tu objetivo es redactar informes clínicos impecables, formales, en tercera persona y listos para entregar, combinando reglas psicométricas estrictas con tu capacidad de análisis clínico para interpretar matices, cruzar datos conductuales con puntajes y explicar disociaciones.

PROHIBICIÓN ESTRICTA DE PRIVACIDAD:
- NUNCA menciones nombres de clínicas, hospitales ni nombres de profesionales que no sean los que el usuario ingresó explícitamente en los datos del caso actual.

---
### 1. ESCALA NORMATIVA UNIFICADA Y GRILLA Z (-3 a +3)
Clasificación obligatoria para la tabla cuantitativa y la redacción:
- **Déficit**: Z <= -2.33 | PE: 1 a 3 | CI: <= 65 | T directo: <= 27 | T inverso (CPT/Nesplora/BRIEF): >= 73 | Pc < 1
- **Dificultad**: Z de -2.00 a -1.33 | PE: 4 a 6 | CI: 70 a 80 | T directo: 30 a 37 | T inverso: 63 a 70 | Pc 2 a 9
- **Normal**: Z de -1.00 a +1.00 | PE: 7 a 13 | CI: 85 a 115 | T: 40 a 60 | Pc 16 a 84
- **Normal Alto**: Z de +1.33 a +2.00 | PE: 14 a 16 | CI: 120 a 130 | T directo: 63 a 70 | T inverso: 30 a 37 | Pc 91 a 98
- **Superior**: Z >= +2.33 | PE: 17 a 19 | CI: >= 135 | T directo: >= 73 | T inverso: <= 27 | Pc > 99

En el cuerpo del análisis cualitativo, destacá siempre en **negrita** los calificadores de rendimiento (**adecuado**, **acorde a lo esperado para su edad**, **dentro de los límites esperados**, **dificultades**, **por debajo de lo esperado**, **descenso**, **déficit**, **rango promedio**, **rango promedio alto**, **superior**).

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
   - **Evaluación Neuropsicológica (Versión Desempeño Cognitivo):** Datos de filiación, Motivo de consulta, Métodos de evaluación y procedimientos, Observación de la conducta, Tabla/Grilla cuantitativa Z, Análisis de Funcionamiento Intelectual, Conclusiones y Recomendaciones (Generales/Terapéuticas y Para la escuela).
   - **Evaluación Neuropsicológica Completa:** Igual al anterior pero desarrollando todos los dominios administrados (Funcionamiento Intelectual, Memoria y Aprendizaje, Alerta y Atención, Funciones Ejecutivas, Visomotor, Lenguaje) y Cuestionarios si aplican.
   - **Evaluación Psicopedagógica:** Usa el subtítulo **"Técnicas implementadas"** y organiza el análisis en: **Perfil psicopedagógico, Cálculo, Lectura (PROLEC), Escritura, Ortografía y Lenguaje**.
   - **Combinado:** Integra los dominios neuropsicológicos seguidos de los apartados psicopedagógicos y cuestionarios.
2. **Criterios de Interpretación de Baterías:**
   - **Wechsler (WISC-V / WPPSI-IV / WAIS-IV):** Analizar CIT e índices primarios (ICV, IVE, IRF, IMT, IVP). Si existe marcada dispersión inter-índices (ej. descenso en IMT o IVP), informar e interpretar el **ICG (Índice de Capacidad General)** como medida más representativa de su potencial intelectual. Si hay índices secundarios (IRC, IMTA), desarrollarlos en párrafos propios.
   - **Memoria (TOMAL, WRAML, RAVLT, Rey):** Contrastar memoria verbal (narrativa vs. lista de palabras, curva de aprendizaje, retención diferida) y memoria visual (abstracta y reproducción/reconocimiento de Figura de Rey).
   - **Atención y FFEE (CPT-II, Nesplora Aula, NEPSY-II, Stroop, TMT A y B, WCST):** En CPT-II consignar siempre el *Índice de Confianza Clínico (%)*. En Nesplora Aula detallar rendimiento con/sin distractores, canal visual vs. auditivo y actividad motora. En TMT, Stroop y WCST analizar flexibilidad cognitiva, atención dividida, velocidad y control inhibitorio.
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
   - Si falta algún dato puntual del paciente, colocar `[Completar]`.
"""


# =====================================================================
# 4. INTERFAZ DE USUARIO EN UNA SOLA PÁGINA (SIN SOLAPAS)
# =====================================================================
st.title("🧠 Generador Profesional de Informes Clínicos")
st.caption("Evaluación Neuropsicológica, Desempeño Cognitivo y Psicopedagógica")

# Panel lateral para configuración técnica y calculadora rápida
api_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
with st.sidebar:
    st.header("⚙️ Configuración")
    if not api_key:
        api_key = st.text_input("Ingresá tu Gemini API Key", type="password")
    modelo_gemini = st.selectbox(
        "Modelo de IA",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
        index=0
    )
    temperatura = st.slider("Flexibilidad de redacción", 0.0, 1.0, 0.25, 0.05)

    st.divider()
    st.subheader("🧮 Calculadora Rápida a Z")
    val_calc = st.number_input("Puntaje", value=10.0, step=1.0)
    esc_calc = st.selectbox(
        "Escala",
        [
            "Escalar (M=10, DE=3)",
            "CI / Estándar (M=100, DE=15)",
            "T Directo - Mayor es mejor (M=50, DE=10)",
            "T Inverso - Mayor es peor/error (M=50, DE=10)"
        ]
    )
    z_res, rango_res = calcular_z_y_rango(val_calc, esc_calc)
    st.metric(label="Equivalencia Z y Rango", value=f"Z = {z_res:+.2f}", delta=rango_res)

# ---------------------------------------------------------------------
# SECCIÓN 1: MODELO DE INFORME Y PRUEBAS ADMINISTRADAS
# (Todo arranca vacío, sin ninguna sugerencia preseleccionada)
# ---------------------------------------------------------------------
st.header("1. Tipo de Informe y Baterías Administradas")

col_mod1, col_mod2 = st.columns(2)
with col_mod1:
    modelos_seleccionados = st.multiselect(
        "Seleccioná el modelo de informe (podés combinar más de uno):",
        [
            "Evaluación Neuropsicológica Completa",
            "Evaluación Neuropsicológica (Versión Desempeño Cognitivo - Wechsler)",
            "Evaluación Psicopedagógica Infantil",
            "Cuestionarios Conductuales (SNAP-IV / BRIEF / Durand / Autoestima)",
            "Conducta Adaptativa (Vineland)",
            "DIVA-5 (Adultos)"
        ],
        default=[],
        placeholder="Elegí el modelo de informe..."
    )

with col_mod2:
    pruebas_usadas = st.multiselect(
        "Seleccioná las pruebas y test administrados:",
        [
            "WISC-V", "WPPSI-IV", "WAIS-IV", "NEPSY-II", "TOMAL", "WRAML",
            "Stroop", "Trail Making Test (TMT)", "CPT-II", "Nesplora Aula",
            "SNAP-IV", "BRIEF", "Woodcock-Muñoz", "PROLEC-R / PROLEC-SE-R",
            "Figura Compleja de Rey", "Ortografía Feldman", "NALPA", "TOMA-3",
            "TEMA-3", "Dictado de oraciones", "EPL", "Escala Durand", "WCST",
            "RAVLT", "Vineland", "DIVA-5"
        ],
        default=[],
        placeholder="Elegí las pruebas administradas..."
    )

st.divider()

# ---------------------------------------------------------------------
# SECCIÓN 2: DATOS DE FILIACIÓN Y PROFESIONAL
# ---------------------------------------------------------------------
st.header("2. Datos del Paciente y del Profesional")
c1, c2, c3, c4 = st.columns(4)
with c1:
    nombre = st.text_input("Apellido y Nombre del Paciente")
    hc = st.text_input("DNI / HC N°")
    fecha_nac = st.text_input("Fecha de nacimiento (DD/MM/AAAA)")
with c2:
    edad_texto = st.text_input("Edad (años y meses)")
    escolaridad = st.text_input("Escolaridad (Nivel y Grado/Año)")
    preferencia = st.selectbox("Preferencia manual", ["", "Diestra", "Zurda", "Ambidiestra / En definición"])
with c3:
    fecha_eval = st.text_input("Fecha de evaluación")
    nacionalidad = st.text_input("Nacionalidad")
    acompanante = st.text_input("Acompañante")
with c4:
    medico = st.text_input("Médico / Institución Solicitante")
    profesional_nombre = st.text_input("Profesional Evaluador/a (para la firma)")
    profesional_matricula = st.text_input("Título y Matrícula Profesional")

st.divider()

# ---------------------------------------------------------------------
# SECCIÓN 3: MOTIVO DE CONSULTA Y OBSERVACIÓN DE CONDUCTA
# ---------------------------------------------------------------------
st.header("3. Motivo de Consulta y Observación de la Conducta")
col_m1, col_m2 = st.columns(2)
with col_m1:
    quien_deriva = st.text_area("¿Quién deriva y qué preocupa? (Motivo de consulta)", height=85)
with col_m2:
    antecedentes = st.text_area("Diagnósticos, tratamientos actuales y evaluaciones previas", height=85)

st.subheader("Indicadores Conductuales Observados")
cb1, cb2, cb3 = st.columns(3)
with cb1:
    obs_vinculo = st.selectbox("Contacto y vínculo", ["", "Adecuado", "Reticente al inicio, luego adecuado", "Otro"])
    obs_predisp = st.selectbox("Predisposición", ["", "Buena", "Variable", "Intenta dirigir la situación"])
    obs_consignas = st.selectbox("Comprensión de consignas", ["", "Comprende adecuadamente", "Requiere repetición y segmentación"])
    obs_desatencion = st.selectbox("Atención durante la evaluación", ["", "Sostiene el foco adecuadamente", "Tiempos atencionales breves", "Se dispersa frente a estímulos"])
with cb2:
    obs_motora = st.selectbox("Actividad motora", ["", "Adecuada (Estable en su silla)", "Movedizo en la silla", "Le cuesta trabajar en silencio"])
    obs_impulsividad = st.selectbox("Estilo de respuesta / Impulsividad", ["", "Reflexivo y organizado", "Responde apresurado, errores por descuido"])
    obs_frustracion = st.selectbox("Tolerancia a la frustración", ["", "Adecuada", "Baja, con conductas de evitación", "Enojo o fastidio ante la dificultad"])
with cb3:
    obs_ansiedad = st.selectbox("Ansiedad frente al error", ["", "No se observa", "Sí, demora respuestas en pruebas con tiempo"])
    obs_ritmo = st.selectbox("Ritmo de trabajo y fatiga", ["", "Adecuado y sostenido", "Lento", "Se fatiga rápido hacia el final"])
    obs_lenguaje = st.selectbox("Lenguaje expresivo espontáneo", ["", "Adecuado", "Dificultades fonológicas / articulatorias", "Escaso"])

obs_extra = st.text_area("Observaciones cualitativas adicionales de la conducta", height=65)

st.divider()

# ---------------------------------------------------------------------
# SECCIÓN 4: CARGA DE PUNTAJES, PLANILLAS Y PDFs
# ---------------------------------------------------------------------
st.header("4. Puntuaciones Cuantitativas y Reportes Adjuntos")
st.caption("Cargá los puntajes en la grilla para que el sistema calcule automáticamente el Puntaje Z y el Rango, o pegá los datos directamente abajo.")

df_vacio = pd.DataFrame(
    columns=["Dominio / Prueba", "Puntaje", "Tipo de Escala", "Observación"]
)

df_editado = st.data_editor(
    df_vacio,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Dominio / Prueba": st.column_config.TextColumn("Dominio / Prueba / Subtest"),
        "Puntaje": st.column_config.NumberColumn("Puntaje Obtenido", format="%.2f"),
        "Tipo de Escala": st.column_config.SelectboxColumn(
            "Tipo de Escala",
            options=[
                "CI / Estándar (M=100, DE=15)",
                "Escalar (M=10, DE=3)",
                "T Directo - Mayor es mejor (M=50, DE=10)",
                "T Inverso - Mayor es peor/error (M=50, DE=10)",
                "Puntaje Z directo"
            ]
        ),
        "Observación": st.column_config.TextColumn("Notas de la prueba")
    }
)

filas_procesadas = []
for _, row in df_editado.iterrows():
    if row.get("Dominio / Prueba") and pd.notnull(row.get("Puntaje")) and row.get("Tipo de Escala"):
        z_val, r_val = calcular_z_y_rango(float(row["Puntaje"]), row["Tipo de Escala"])
        filas_procesadas.append({
            "Dominio / Prueba": row["Dominio / Prueba"],
            "Puntaje": row["Puntaje"],
            "Escala": row["Tipo de Escala"],
            "Puntaje Z": f"{z_val:+.2f}",
            "Rango Clínico": r_val,
            "Notas": row.get("Observación", "")
        })
df_procesado = pd.DataFrame(filas_procesadas)
if not df_procesado.empty:
    st.dataframe(df_procesado, use_container_width=True)

col_p1, col_p2 = st.columns(2)
with col_p1:
    texto_puntajes_libre = st.text_area(
        "Pegar tabla de puntuaciones o resultados crudos (Excel / Planilla / Notas):",
        height=130
    )
with col_p2:
    archivos_adjuntos = st.file_uploader(
        "📎 Subir reportes en PDF (CPT-II, Nesplora Aula, Vineland) o CSV",
        type=["pdf", "csv", "txt"],
        accept_multiple_files=True
    )

st.divider()

# ---------------------------------------------------------------------
# SECCIÓN 5: DETALLES CUALITATIVOS POR DOMINIO
# ---------------------------------------------------------------------
st.header("5. Notas Cualitativas por Dominio y Pruebas")
col_q1, col_q2 = st.columns(2)
with col_q1:
    st.subheader("A. Desempeño Cognitivo y Neuropsicología")
    obs_wechsler = st.text_area(
        "Funcionamiento Intelectual (IC 95%, si se informa ICG, índices secundarios IRC/IMTA, estrategias)",
        height=80
    )
    obs_memoria = st.text_area(
        "Memoria y Aprendizaje (curva de aprendizaje, intrusiones, pérdida diferida, reconocimiento en Rey)",
        height=80
    )
    obs_atencion_fe = st.text_area(
        "Atención y Funciones Ejecutivas (CPT índice de confianza, Nesplora distractores, WCST, Stroop, TMT)",
        height=80
    )
    obs_viso_leng = st.text_area(
        "Visomotor y Lenguaje (estrategia de copia en Rey, prensión, fluidez semántica vs. fonológica)",
        height=80
    )

with col_q2:
    st.subheader("B. Psicopedagogía y Cuestionarios")
    alfabetizado = st.selectbox("Nivel de alfabetización (si aplica)", ["", "Sí", "No", "En proceso"])
    obs_lectoescritura = st.text_area(
        "Lectura, Escritura y Ortografía (PROLEC-R, EPL, velocidad/precisión, ejemplos literales de NALPA o dictado)",
        height=95
    )
    obs_matematica = st.text_area(
        "Cálculo y Matemática (Woodcock-Muñoz ejemplos literales de aciertos/errores, TEMA-3 / TOMA-3)",
        height=95
    )
    cuestionarios_txt = st.text_area(
        "Cuestionarios y Escalas (SNAP-IV, BRIEF, Durand, Autoestima, Vineland, DIVA-5: informante e ítems)",
        height=95
    )

st.divider()

# ---------------------------------------------------------------------
# SECCIÓN 6: CONCLUSIONES Y SUGERENCIAS FINALES (CLARAS Y DESPLEGADAS)
# (Todo arranca sin ninguna opción seleccionada)
# ---------------------------------------------------------------------
st.header("6. Conclusiones y Sugerencias Finales")

col_s1, col_s2 = st.columns(2)
with col_s1:
    impresion_destacar = st.text_area(
        "Síntesis diagnóstica / Qué querés destacar en las Conclusiones:",
        height=100,
        placeholder="Ej: Perfil cognitivo dentro del promedio con vulnerabilidad específica en el sostenimiento atencional y control inhibitorio..."
    )
    frecuencia_y_control = st.text_input(
        "Frecuencia de tratamiento y plazo de reevaluación (opcional)",
        placeholder="Ej: Frecuencia semanal. Reevaluación en 12 meses."
    )

with col_s2:
    sug_terapeuticas_sel = st.multiselect(
        "Sugerencias Terapéuticas y Derivaciones (elegí las que quieras incluir):",
        options=list(BANCO_SUGERENCIAS["terapeuticas"].keys()),
        default=[],
        placeholder="Seleccionar derivaciones y tratamientos..."
    )
    sug_escolares_sel = st.multiselect(
        "Sugerencias y Adaptaciones para la Escuela (elegí las que quieras incluir):",
        options=list(BANCO_SUGERENCIAS["escolares"].keys()),
        default=[],
        placeholder="Seleccionar adaptaciones escolares..."
    )

recom_personalizadas = st.text_area(
    "Agregar otras sugerencias personalizadas (para la familia, escuela o terapeutas):",
    height=75
)

# Vista previa clara de las sugerencias seleccionadas que se redactarán en el informe
if sug_terapeuticas_sel or sug_escolares_sel:
    with st.expander("👁️ Ver texto base de las sugerencias seleccionadas", expanded=True):
        if sug_terapeuticas_sel:
            st.markdown("**Recomendaciones Terapéuticas y Generales seleccionadas:**")
            for item in sug_terapeuticas_sel:
                st.markdown(f"- **{item}:** {BANCO_SUGERENCIAS['terapeuticas'][item]}")
        if sug_escolares_sel:
            st.markdown("**Recomendaciones para la Escuela seleccionadas:**")
            for item in sug_escolares_sel:
                st.markdown(f"- **{item}:** {BANCO_SUGERENCIAS['escolares'][item]}")

st.divider()
boton_generar = st.button("🚀 Generar Informe Clínico Completo", type="primary", use_container_width=True)

# =====================================================================
# 5. EJECUCIÓN DEL MOTOR HÍBRIDO (PYTHON + GEMINI API)
# =====================================================================
if boton_generar:
    if not api_key:
        st.error("Por favor, ingresá tu API Key de Gemini en el menú lateral izquierdo.")
    else:
        genai.configure(api_key=api_key)
        with st.spinner("Analizando perfil clínico, procesando escalas Z y redactando el informe completo..."):
            try:
                contenido_multimedia = []
                archivos_temp = []
                for archivo in archivos_adjuntos:
                    if archivo.name.endswith(".pdf"):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(archivo.read())
                            tmp_path = tmp.name
                            archivos_temp.append(tmp_path)
                        uploaded_file = genai.upload_file(tmp_path, mime_type="application/pdf")
                        contenido_multimedia.append(uploaded_file)
                    else:
                        texto_archivo = archivo.read().decode("utf-8", errors="ignore")
                        contenido_multimedia.append(f"\n--- Archivo adjunto ({archivo.name}) ---\n{texto_archivo}\n")

                tabla_z_markdown = df_procesado.to_markdown(index=False) if not df_procesado.empty else "No se ingresaron filas en la grilla interactiva."

                # Armar el detalle explícito de las sugerencias seleccionadas
                detalle_terapeuticas = "\n".join(
                    [f"- {k}: {BANCO_SUGERENCIAS['terapeuticas'][k]}" for k in sug_terapeuticas_sel]
                ) or "Adaptar automáticamente según el perfil clínico descrito."

                detalle_escolares = "\n".join(
                    [f"- {k}: {BANCO_SUGERENCIAS['escolares'][k]}" for k in sug_escolares_sel]
                ) or "Incluir pautas escolares acordes a las necesidades detectadas en el perfil."

                firma_profesional = (
                    f"{profesional_nombre} — {profesional_matricula}"
                    if profesional_nombre or profesional_matricula
                    else "[Firma y Sello del Profesional]"
                )

                prompt_caso = f"""
Redactá el INFORME CLÍNICO COMPLETO Y DEFINITIVO siguiendo la estructura y el estilo profesional del Sistema.

### 1. MODELO(S) DE INFORME A REDACTAR:
{', '.join(modelos_seleccionados) if modelos_seleccionados else 'Inferir según las pruebas administradas'}

### 2. DATOS DE FILIACIÓN:
- Apellido y Nombre: {nombre or '[Completar]'}
- DNI / HC: {hc or '[Completar]'}
- Edad: {edad_texto or '[Completar]'}
- Fecha de nacimiento: {fecha_nac or '[Completar]'}
- Fecha de evaluación: {fecha_eval or '[Completar]'}
- Escolaridad: {escolaridad or '[Completar]'}
- Nacionalidad: {nacionalidad or '[Completar]'}
- Preferencia manual: {preferencia or '[Completar]'}
- Solicitante: {medico or '[Completar]'}
- Profesional Evaluador: {firma_profesional}
- Acompañante: {acompanante or 'No especificado'}

### 3. MOTIVO DE CONSULTA Y ANTECEDENTES:
- Motivo y derivación: {quien_deriva}
- Antecedentes y tratamientos: {antecedentes}

### 4. OBSERVACIÓN DE LA CONDUCTA:
- Contacto y vínculo: {obs_vinculo}
- Predisposición: {obs_predisp}
- Comprensión de consignas: {obs_consignas}
- Atención observable: {obs_desatencion}
- Actividad motora: {obs_motora}
- Impulsividad: {obs_impulsividad}
- Tolerancia a la frustración: {obs_frustracion}
- Ansiedad frente al error: {obs_ansiedad}
- Ritmo de trabajo y fatiga: {obs_ritmo}
- Lenguaje expresivo: {obs_lenguaje}
- Notas extra de conducta: {obs_extra}

### 5. PRUEBAS Y BATERÍAS ADMINISTRADAS:
{', '.join(pruebas_usadas) if pruebas_usadas else 'Ver puntuaciones y notas adjuntas'}

### 6. GRILLA DE PUNTUACIONES PROCESADAS (PUNTAJE Z Y RANGO CLÍNICO):
{tabla_z_markdown}

### 7. DATOS ADICIONALES DE PUNTUACIONES (TEXTO LIBRE / PLANILLA):
{texto_puntajes_libre}

### 8. OBSERVACIONES CUALITATIVAS POR DOMINIO:
- **Funcionamiento Intelectual (Wechsler):** {obs_wechsler}
- **Memoria y Aprendizaje:** {obs_memoria}
- **Atención y Funciones Ejecutivas:** {obs_atencion_fe}
- **Visomotor y Lenguaje:** {obs_viso_leng}
- **Psicopedagogía (Alfabetización: {alfabetizado}):**
  - Lectura, Escritura y Ortografía: {obs_lectoescritura}
  - Cálculo y Matemática: {obs_matematica}
- **Cuestionarios / Vineland / DIVA-5:** {cuestionarios_txt}

### 9. CONCLUSIONES Y SUGERENCIAS FINALES OBLIGATORIAS:
- **Síntesis clínica a destacar en Conclusiones:** {impresion_destacar}
- **Frecuencia y control evolutivo:** {frecuencia_y_control}
- **Recomendaciones Terapéuticas y Generales a desarrollar:**
{detalle_terapeuticas}
- **Recomendaciones y Adaptaciones para la Escuela a desarrollar:**
{detalle_escolares}
- **Sugerencias personalizadas adicionales:** {recom_personalizadas}
- **Firma al pie del informe:** {firma_profesional}
"""

                model = genai.GenerativeModel(
                    model_name=modelo_gemini,
                    system_instruction=construir_system_prompt(),
                    generation_config={"temperature": temperatura}
                )

                payload = contenido_multimedia + [prompt_caso]
                respuesta = model.generate_content(payload)

                for path in archivos_temp:
                    if os.path.exists(path):
                        os.remove(path)

                st.subheader("📄 Informe Clínico Generado")
                st.markdown(respuesta.text)

                st.download_button(
                    label="⬇️ Descargar Informe (.md / compatible con Word y Google Docs)",
                    data=respuesta.text,
                    file_name=f"Informe_{(nombre or 'Paciente').replace(' ', '_')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"Error al generar el informe: {e}")