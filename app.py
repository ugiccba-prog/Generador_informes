import streamlit as st
import google.generativeai as genai
import pandas as pd
import tempfile
import os

# =====================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y BASE DE CONOCIMIENTO DURA (MEMORIA)
# =====================================================================
st.set_page_config(
    page_title="Generador Clínico FLENI — Lic. Carla D'Ovidio",
    page_icon="🧠",
    layout="wide"
)

# Textos literales en cursiva extraídos de los ~114 informes de la carpeta Memoria
INTRODUCCIONES_LITERAL = {
    "intelectual": (
        "*La evaluación del funcionamiento intelectual mediante la Escala de Inteligencia de Wechsler "
        "(WISC-V / WPPSI-IV / WAIS-IV) permite obtener una estimación de la capacidad cognitiva general "
        "del niño/adolescente, así como explorar su desempeño en dominios específicos que subyacen al "
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
        "de estos aspectos va a permitir al niño ejecutar y mantener una conducta dirigida hacia una "
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

# =====================================================================
# 2. FUNCIONES DETERMINÍSTICAS (BAREMOS, ESCALAS Z Y HUECOS CONOCIDOS)
# =====================================================================
def calcular_z_y_rango(valor: float, tipo_escala: str):
    """
    Convierte puntajes de manera exacta a puntaje Z y asigna el Rango Clínico
    institucional de la Lic. Carla D'Ovidio.
    """
    if tipo_escala == "CI / Estándar (M=100, DE=15)":
        z = (valor - 100.0) / 15.0
    elif tipo_escala == "Escalar (M=10, DE=3)":
        z = (valor - 10.0) / 3.0
    elif tipo_escala == "T Directo - Mayor es mejor (M=50, DE=10)":
        z = (valor - 50.0) / 10.0
    elif tipo_escala == "T Inverso - Mayor es peor/error (M=50, DE=10)":
        z = (50.0 - valor) / 10.0
    else:
        z = valor  # Ya ingresado en Z

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
        # Zona intermedia (-1.32 a -1.01 o +1.01 a +1.32)
        rango = "Normal (Tendencia baja)" if z < 0 else "Normal (Tendencia alta)"

    return z, rango


def verificar_huecos_baremos(edad_anios: int, sexo: str, pruebas_seleccionadas: list):
    """
    Detecta los huecos conocidos del '00 - Índice de la base (Memoria)'
    en las fotos de tablas y devuelve alertas preventivas.
    """
    alertas = []
    if "TOMAL" in pruebas_seleccionadas and edad_anios in [5, 6, 9, 13, 16, 18, 19]:
        alertas.append(f"⚠️ **TOMAL ({edad_anios} años):** No hay fotos de tablas en la base para esta edad. Verificar PE directo del manual PDF.")
    if "WRAML" in pruebas_seleccionadas and edad_anios >= 14 and edad_anios != 15:
        alertas.append(f"⚠️ **WRAML ({edad_anios} años):** Sin cobertura en fotos desde los 14 años (salvo 15-0). Verificar manual PDF.")
    if "NEPSY-II" in pruebas_seleccionadas and 13 <= edad_anios <= 16:
        alertas.append(f"⚠️ **NEPSY-II ({edad_anios} años):** Faltan fotos de la tabla A4 entre 13 y 16 años. Usar manual PDF.")
    if "BRIEF" in pruebas_seleccionadas and sexo == "Femenino":
        alertas.append("⚠️ **BRIEF (Niñas):** Faltan fotos de tablas de padres para niñas en la carpeta de fotos. Usar software o manual.")
    if "Figura Compleja de Rey" in pruebas_seleccionadas and edad_anios not in [13, 15, 17]:
        alertas.append(f"⚠️ **Figura de Rey - Meyers ({edad_anios} años):** En fotos solo están 13, 15 y 17 años.")
    if any(p in pruebas_seleccionadas for p in ["WISC-V", "WPPSI-IV"]):
        alertas.append("ℹ️ **Wechsler:** Recordá no usar las fotos de tablas (son WISC-IV/WPPSI-III); usar manuales WISC-V / WPPSI-IV.")
    return alertas


# =====================================================================
# 3. PROMPT MAESTRO DEL SISTEMA (REGLAS ESTRICTAS + RAZONAMIENTO GEMINI)
# =====================================================================
def construir_system_prompt():
    return f"""
Actuás como el Motor Senior de Redacción Clínica Neuropsicológica y Psicopedagógica de FLENI, redactando informes con el estilo exacto de la Lic. Carla D'Ovidio (M.N. 55.767).

Tu arquitectura es HÍBRIDA:
1. OBEDECÉS ESTRICTAMENTE las plantillas, introducciones teóricas en cursiva, escalas normativas Z, cláusulas legales y estructura institucional provistas a continuación (Conocimiento duro de la carpeta "Memoria").
2. APLICÁS TODA TU INTELIGENCIA CLÍNICA Y FLEXIBILIDAD ANALÍTICA para cruzar los datos cuantitativos con la observación conductual, explicar disociaciones intra-perfil (ej. potencial conceptual conservado con penalización por velocidad o memoria operativa; o falla en evocación libre que mejora en reconocimiento), y redactar un informe cohesivo, cálido y riguroso en tercera persona.

---
### A. ESCALA NORMATIVA UNIFICADA Y GRILLA Z (-3 a +3)
Clasificación obligatoria:
- **Déficit**: Z <= -2.33 | PE: 1 a 3 | CI: <= 65 | T directo: <= 27 | T inverso (CPT/Nesplora/BRIEF): >= 73 | Pc < 1
- **Dificultad**: Z de -2.00 a -1.33 | PE: 4 a 6 | CI: 70 a 80 | T directo: 30 a 37 | T inverso: 63 a 70 | Pc 2 a 9
- **Normal**: Z de -1.00 a +1.00 | PE: 7 a 13 | CI: 85 a 115 | T: 40 a 60 | Pc 16 a 84
- **Normal Alto**: Z de +1.33 a +2.00 | PE: 14 a 16 | CI: 120 a 130 | T directo: 63 a 70 | T inverso: 30 a 37 | Pc 91 a 98
- **Superior**: Z >= +2.33 | PE: 17 a 19 | CI: >= 135 | T directo: >= 73 | T inverso: <= 27 | Pc > 99

En el cuerpo del análisis cualitativo, destacá siempre en **negrita** los calificadores de rendimiento (**adecuado**, **acorde a lo esperado para su edad**, **dificultades**, **por debajo de lo esperado**, **descenso**, **déficit**, **rango promedio**, **rango promedio alto**, **superior**).

---
### B. INTRODUCCIONES TEÓRICAS EN CURSIVA (TEXTO LITERAL OBLIGATORIO)
Al comenzar cada dominio en la sección "Análisis de los Resultados", debés insertar textualmente el párrafo en cursiva que corresponda antes de analizar al paciente:

- **Funcionamiento Intelectual:** {INTRODUCCIONES_LITERAL["intelectual"]}
- **Memoria y Aprendizaje:** {INTRODUCCIONES_LITERAL["memoria"]}
- **Alerta y Atención:** {INTRODUCCIONES_LITERAL["atencion"]}
- **Funciones Ejecutivas:** {INTRODUCCIONES_LITERAL["ejecutivas"]}
- **Procesamiento Visomotor:** {INTRODUCCIONES_LITERAL["visomotor"]}
- **Lenguaje:** {INTRODUCCIONES_LITERAL["lenguaje"]}

---
### C. REGLAS ESPECÍFICAS POR MODELO Y PRUEBA
1. **Variantes de Estructura:**
   - **Desempeño Cognitivo (solo Wechsler):** Membrete FLENI (Montañeses 2325), Tabla de filiación, Motivo de consulta, Métodos de evaluación y procedimientos, Observación de la conducta, Grilla cuantitativa Z, Funcionamiento Intelectual, Conclusiones y Recomendaciones.
   - **Neuropsicológica Completa:** Igual al anterior pero desarrollando todos los dominios evaluados (Funcionamiento Intelectual, Memoria y Aprendizaje, Alerta y Atención, Funciones Ejecutivas, Visomotor, Lenguaje) y Cuestionarios si los hay.
   - **Psicopedagógica Infantil:** Membrete FLENI (Olazábal 1574 / Montañeses 2325), usa el título **"Técnicas implementadas"** (en lugar de Métodos de evaluación) y estructura los resultados en: **Perfil psicopedagógico, Cálculo, Lectura (PROLEC), Escritura, Ortografía y Lenguaje**.
   - **Combinado:** Integra los dominios neuropsicológicos seguidos de los bloques psicopedagógicos y cuestionarios.
2. **Reglas de Oro de las Pruebas:**
   - **Wechsler (WISC-V / WPPSI-IV / WAIS-IV):** Si hay dispersión significativa entre índices (especialmente descensos en IMT o IVP), interpretá el **ICG (Índice de Capacidad General)** como el indicador más fiel de su capacidad intelectual. Si se informan índices secundarios (IRC, IMTA), dedicales un párrafo específico.
   - **Woodcock-Muñoz:** Informar Puntaje Bruto y Edad Equivalente. Incluir SIEMPRE la cláusula literal: *"Nota: La Batería Woodcock-Muñoz no se encuentra estandarizada para nuestra población, por lo que sus valores deben ser considerados como orientativos."*
   - **CPT-II y Nesplora Aula:** En CPT-II mencionar siempre el porcentaje del *Índice de Confianza Clínico*. En Nesplora Aula analizar el desempeño con vs. sin distractores, canal auditivo vs. visual, y actividad motora.
   - **NALPA / EPL / Woodcock / Ortografía Feldman:** Cuando el usuario provea ejemplos literales de lo que escribió el niño o de errores en cuentas (ej. "4-1=5"), incluí esos ejemplos literales entre comillas dentro del párrafo clínico.
3. **Regla Médico-Legal en Conclusiones:**
   - NUNCA sentenciar un diagnóstico médico cerrado en neuropsicología. Cerrar SIEMPRE la sección de Conclusiones con la fórmula de la Lic. D'Ovidio:
     *"En síntesis, estos indicadores caracterizan a [Nombre] con un perfil compatible con [describir perfil: ej. un déficit atencional / una debilidad ejecutiva / dificultades específicas del aprendizaje]. El diagnóstico definitivo quedará a cargo del médico tratante a partir de la integración clínica de los presentes hallazgos."*
4. **Cierre y Firma:**
   - Dividir recomendaciones en **Recomendaciones generales/terapéuticas** y **Recomendaciones para la escuela** (adaptaciones de acceso, ubicación, segmentación de consignas, tiempos).
   - Nunca inventar datos no provistos: si falta un puntaje o dato, dejar `[Completar]`.
   - Firmar siempre como: **Lic. Carla D'Ovidio — Lic. en Psicología y Psicopedagogía — M.N. 55.767 — Servicio de Psiquiatría Infanto Juvenil (FLENI)**.
"""


# =====================================================================
# 4. INTERFAZ DE USUARIO (STREAMLIT)
# =====================================================================
st.title("🧠 Generador de Informes Clínicos — FLENI")
st.caption("Sistema Híbrido: Base de Conocimiento 'Memoria' (Lic. Carla D'Ovidio) + Motor Analítico Gemini")

# Gestión de API Key (lee automáticamente de st.secrets si está configurado en Streamlit Cloud)
api_key = st.secrets.get("GEMINI_API_KEY", "") if "GEMINI_API_KEY" in st.secrets else ""
with st.sidebar:
    st.header("⚙️ Configuración")
    if not api_key:
        api_key = st.text_input("Ingresá tu Gemini API Key", type="password")
    modelo_gemini = st.selectbox(
        "Modelo de IA",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
        index=0,
        help="gemini-2.5-pro es ideal para razonamiento clínico profundo y redacción extensa."
    )
    temperatura = st.slider("Creatividad / Flexibilidad de redacción", 0.0, 1.0, 0.25, 0.05)

    st.divider()
    st.subheader("🧮 Calculadora Rápida a Z")
    val_calc = st.number_input("Puntaje obtenido", value=10.0, step=1.0)
    esc_calc = st.selectbox(
        "Escala de origen",
        [
            "Escalar (M=10, DE=3)",
            "CI / Estándar (M=100, DE=15)",
            "T Directo - Mayor es mejor (M=50, DE=10)",
            "T Inverso - Mayor es peor/error (M=50, DE=10)"
        ]
    )
    z_res, rango_res = calcular_z_y_rango(val_calc, esc_calc)
    st.metric(label="Puntaje Z y Rango FLENI", value=f"Z = {z_res:+.2f}", delta=rango_res)

# Pestañas principales reflejando la Ficha de Carga y Planilla de Puntuaciones
tab_ficha, tab_puntajes, tab_especificos, tab_cierre = st.tabs([
    "1️⃣ Filiación, Modelo y Conducta",
    "2️⃣ Planilla de Puntuaciones y PDFs",
    "3️⃣ Detalles por Bloque (NP / PSP / Cuestionarios)",
    "4️⃣ Impresión Clínica y Generación"
])

with tab_ficha:
    st.subheader("1. Selección de Modelo e Identificación")
    modelos_seleccionados = st.multiselect(
        "¿Qué modelo(s) de informe corresponde armar? (Podés combinar)",
        [
            "Evaluación Neuropsicológica Completa",
            "Evaluación Neuropsicológica (Versión Desempeño Cognitivo - Wechsler)",
            "Evaluación Psicopedagógica Infantil",
            "Cuestionarios Conductuales (SNAP-IV / BRIEF / Durand / Autoestima)",
            "Conducta Adaptativa (Vineland)",
            "DIVA-5 (Adultos)"
        ],
        default=["Evaluación Neuropsicológica Completa"]
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        nombre = st.text_input("Apellido y Nombre", placeholder="Ej: Pérez, Agustín")
        hc = st.text_input("HC N°", placeholder="Ej: 458921")
        sexo = st.selectbox("Sexo biológico (para alerta de baremos)", ["Masculino", "Femenino"])
    with c2:
        edad_texto = st.text_input("Edad exacta (años y meses)", placeholder="Ej: 9 años, 4 meses")
        edad_num = st.number_input("Edad en años cumplidos (para chequear baremos)", min_value=2, max_value=90, value=9)
        fecha_nac = st.text_input("Fecha de nacimiento", placeholder="DD/MM/AAAA")
    with c3:
        fecha_eval = st.text_input("Fecha de evaluación", value="Octubre 2026")
        escolaridad = st.text_input("Escolaridad (Nivel y Grado/Año)", placeholder="Ej: 4° Grado - Nivel Primario")
        preferencia = st.selectbox("Preferencia manual", ["Diestra", "Zurda", "Ambidiestra / En definición"])
    with c4:
        nacionalidad = st.text_input("Nacionalidad", value="Argentina")
        medico = st.text_input("Médico Solicitante", placeholder="Dr./Dra. ...")
        acompanante = st.text_input("Acompañante", placeholder="Madre / Padre / Ambos")

    st.subheader("2. Motivo de Consulta y Antecedentes")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        quien_deriva = st.text_input("¿Quién deriva y qué preocupa?", placeholder="Derivado por neurología / colegio por desatención...")
        tratamientos = st.text_input("Diagnósticos y tratamientos actuales", placeholder="Ej: Psicopedagogía semanal desde 2025...")
    with col_m2:
        eval_previas = st.text_area("Evaluaciones anteriores y medicación (si aplica)", height=100)

    st.subheader("3. Observación de la Conducta (Checkboxes Ficha de Carga)")
    cb1, cb2, cb3 = st.columns(3)
    with cb1:
        obs_vinculo = st.selectbox("Contacto y vínculo", ["Adecuado", "Reticente al inicio, luego adecuado", "Otro (detallar abajo)"])
        obs_predisp = st.selectbox("Predisposición", ["Buena", "Variable", "Intenta dirigir la situación"])
        obs_consignas = st.selectbox("Comprensión de consignas", ["Comprende adecuadamente", "Requiere repetición y segmentación"])
        obs_desatencion = st.selectbox("Desatención", ["No (Sostiene el foco)", "Tiempos atencionales breves", "Se dispersa frente a estímulos"])
    with cb2:
        obs_motora = st.selectbox("Inquietud motora", ["No (Estable en su silla)", "Movedizo en la silla", "Le cuesta trabajar en silencio"])
        obs_impulsividad = st.selectbox("Impulsividad", ["No (Reflexivo)", "Responde apresurado, errores por descuido"])
        obs_frustracion = st.selectbox("Tolerancia a la frustración", ["Adecuada", "Baja, con conductas de evitación", "Enojo / Fastidio ante la dificultad"])
    with cb3:
        obs_ansiedad = st.selectbox("Ansiedad frente al error", ["No", "Sí, demora respuestas en pruebas con tiempo"])
        obs_ritmo = st.selectbox("Ritmo de trabajo y fatiga", ["Adecuado y sostenido", "Lento", "Se fatiga rápido hacia el final"])
        obs_lenguaje = st.selectbox("Lenguaje expresivo espontáneo", ["Adecuado", "Dificultades fonológicas / articulatorias", "Escaso / Monosilábico"])
    obs_extra = st.text_area("Otras observaciones conductuales cualitativas", height=70)

with tab_puntajes:
    st.subheader("Pruebas Administradas y Detección de Huecos de Baremos")
    pruebas_usadas = st.multiselect(
        "Seleccioná las baterías administradas:",
        [
            "WISC-V", "WPPSI-IV", "WAIS-IV", "NEPSY-II", "TOMAL", "WRAML",
            "Stroop", "Trail Making Test (TMT)", "CPT-II", "Nesplora Aula",
            "SNAP-IV", "BRIEF", "Woodcock-Muñoz", "PROLEC-R / PROLEC-SE-R",
            "Figura Compleja de Rey", "Ortografía Feldman", "NALPA", "TOMA-3",
            "TEMA-3", "Dictado de oraciones", "EPL", "Escala Durand", "WCST",
            "RAVLT", "Vineland", "DIVA-5"
        ],
        default=["WISC-V", "TOMAL", "WRAML", "CPT-II", "NEPSY-II", "Stroop", "Trail Making Test (TMT)"]
    )

    # Mostrar alertas automáticas de la carpeta Memoria
    alertas_baremos = verificar_huecos_baremos(edad_num, sexo, pruebas_usadas)
    if alertas_baremos:
        for alerta in alertas_baremos:
            st.warning(alerta)

    st.markdown("#### 📊 Grilla Interactiva de Puntuaciones (Calcula Z y Rango automáticamente)")
    st.caption("Podés cargar los puntajes acá o pegar directamente tu tabla/planilla en el cuadro de texto de abajo.")

    df_inicial = pd.DataFrame([
        {"Dominio / Prueba": "WISC-V - CIT", "Puntaje": 100.0, "Tipo de Escala": "CI / Estándar (M=100, DE=15)", "Observación": ""},
        {"Dominio / Prueba": "WISC-V - Comprensión Verbal (ICV)", "Puntaje": 105.0, "Tipo de Escala": "CI / Estándar (M=100, DE=15)", "Observación": ""},
        {"Dominio / Prueba": "TOMAL - Recuerdo Selectivo Palabras", "Puntaje": 10.0, "Tipo de Escala": "Escalar (M=10, DE=3)", "Observación": ""},
    ])

    df_editado = st.data_editor(
        df_inicial,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Tipo de Escala": st.column_config.SelectboxColumn(
                "Tipo de Escala",
                options=[
                    "CI / Estándar (M=100, DE=15)",
                    "Escalar (M=10, DE=3)",
                    "T Directo - Mayor es mejor (M=50, DE=10)",
                    "T Inverso - Mayor es peor/error (M=50, DE=10)",
                    "Puntaje Z directo"
                ],
                required=True
            )
        }
    )

    # Procesar tabla con Python para darle a Gemini los Z exactos sin errores de cálculo
    filas_procesadas = []
    for _, row in df_editado.iterrows():
        if row["Dominio / Prueba"] and pd.notnull(row["Puntaje"]):
            z_val, r_val = calcular_z_y_rango(float(row["Puntaje"]), row["Tipo de Escala"])
            filas_procesadas.append({
                "Dominio / Prueba": row["Dominio / Prueba"],
                "Puntaje Original": row["Puntaje"],
                "Escala": row["Tipo de Escala"],
                "Puntaje Z Calculado": f"{z_val:+.2f}",
                "Rango Clínico FLENI": r_val,
                "Notas": row.get("Observación", "")
            })
    df_procesado = pd.DataFrame(filas_procesadas)
    if not df_procesado.empty:
        st.dataframe(df_procesado, use_container_width=True)

    texto_puntajes_libre = st.text_area(
        "O pegá acá directamente los datos crudos de tu Planilla de Puntuaciones / CSV:",
        height=140,
        placeholder="Pegá celdas de Excel/Sheets o notas de puntajes..."
    )

    archivos_adjuntos = st.file_uploader(
        "📎 Adjuntar reportes PDF (CPT-II, Nesplora Aula, Vineland) o CSV de Planilla",
        type=["pdf", "csv", "txt"],
        accept_multiple_files=True
    )

with tab_especificos:
    st.subheader("5. Bloques Cualitativos de la Ficha de Carga")
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        st.markdown("**A. Desempeño Cognitivo (Wechsler)**")
        ic_cit = st.text_input("Intervalo de confianza del CIT (95%) e información de ICG", placeholder="Ej: IC 95% 98-110. Perfil heterogéneo, informar ICG = 108")
        indices_sec = st.text_input("Índices secundarios calculados (IRC, IMTA, etc.)", placeholder="Ej: IRC = 115 (Promedio Alto), IMTA = 95 (Promedio)")
        obs_wechsler = st.text_area("Observaciones cualitativas por índice (conteo dactilar, subitización, impulsividad)", height=90)

        st.markdown("**B. Neuropsicológica Completa**")
        obs_memoria = st.text_area("Memoria (estrategias en lista, pérdida diferida, intrusiones, RAVLT, Reconocimiento Rey)", height=80)
        obs_atencion_fe = st.text_area("Atención y FFEE (momento en que decae, CPT índice confianza, Nesplora distractores, WCST categorías/perseveraciones)", height=80)
        obs_viso_leng = st.text_area("Visomotor y Lenguaje (organización Rey, prensión, fluidez semántica vs fonémica)", height=80)

    with col_q2:
        st.markdown("**C. Bloque Psicopedagógico (si aplica)**")
        alfabetizado = st.selectbox("¿Está alfabetizado/a?", ["No aplica", "Sí", "No", "En proceso"])
        tipo_letra = st.text_input("Tipo de letra, prensión y reconocimiento sonoro de letras")
        nalpa_dictado = st.text_area("Palabras dictadas (NALPA / Dictado) — Escribir en forma LITERAL lo que produjo", height=75)
        lectura_prolec = st.text_area("Lectura y PROLEC-R (velocidad, tipo de errores, comprensión)", height=75)
        calculo_woodcock = st.text_area("Matemática (Woodcock-Muñoz ejemplos literales como '4-1=5', TEMA-3 / TOMA-3 logros y dificultades)", height=75)

        st.markdown("**D. Cuestionarios, Vineland y DIVA-5 (si aplica)**")
        cuestionarios_txt = st.text_area(
            "SNAP-IV / BRIEF / Durand / Autoestima / Vineland / DIVA-5 (Informante e ítems significativos)",
            height=115
        )

with tab_cierre:
    st.subheader("8. Impresión Clínica y Derivaciones")
    impresion_destacar = st.text_area(
        "¿Qué querés que destaque especialmente la conclusión del informe?",
        placeholder="Ej: Destacar que su potencial intelectual es normal alto pero su rendimiento cae por fatiga atencional e impulsividad..."
    )
    perfil_recom = st.selectbox(
        "Perfil de recomendaciones",
        [
            "Combinado o impulsivo",
            "Predominantemente inatento",
            "Dentro de lo esperado con leves vulnerabilidades",
            "Específico del Aprendizaje (DEA - Lectoescritura / Cálculo)",
            "Personalizado según notas"
        ]
    )
    derivaciones = st.multiselect(
        "Derivaciones y sugerencias terapéuticas a incluir:",
        [
            "Psiquiatría o neurología infantil (devolución al médico derivante)",
            "Tratamiento psicopedagógico con orientación neurocognitiva",
            "Tratamiento psicológico cognitivo-conductual (TCC) y orientación a padres",
            "Terapia Ocupacional con enfoque en Integración Sensorial",
            "Evaluación / Tratamiento Neurolingüístico (Fonoaudiología)",
            "Maestra de Apoyo a la Inclusión (MAI)"
        ],
        default=[
            "Psiquiatría o neurología infantil (devolución al médico derivante)",
            "Tratamiento psicopedagógico con orientación neurocognitiva"
        ]
    )
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        frecuencia_sug = st.text_input("Frecuencia sugerida de tratamiento", value="Semanal")
    with col_r2:
        reevaluacion = st.text_input("Sugerencia de reevaluación en", value="1 año / 18 meses")
    recom_escuela_casa = st.text_area("Recomendaciones puntuales extra para la escuela o la casa", height=80)

    st.divider()
    boton_generar = st.button("🚀 Generar Informe Clínico Completo", type="primary", use_container_width=True)

# =====================================================================
# 5. EJECUCIÓN DEL MOTOR HÍBRIDO (PYTHON + GEMINI API)
# =====================================================================
if boton_generar:
    if not api_key:
        st.error("❌ Ingresá tu API Key de Gemini en el panel izquierdo para poder generar el informe.")
    else:
        genai.configure(api_key=api_key)
        with st.spinner("Integrando base 'Memoria', calculando grillas Z y redactando informe con el estilo de la Lic. D'Ovidio..."):
            try:
                # 1. Subir PDFs adjuntos (ej. CPT-II / Nesplora) a la File API de Gemini si existen
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
                        contenido_multimedia.append(f"\n--- Contenido del archivo adjunto ({archivo.name}) ---\n{texto_archivo}\n")

                # 2. Armar el dossier estructurado del paciente
                tabla_z_markdown = df_procesado.to_markdown(index=False) if not df_procesado.empty else "Sin filas en la tabla interactiva."

                prompt_caso = f"""
Redactá el INFORME CLÍNICO COMPLETO Y DEFINITIVO siguiendo estrictamente las reglas del Sistema (FLENI - Lic. Carla D'Ovidio).

### 1. MODELO(S) REQUERIDO(S):
{', '.join(modelos_seleccionados)}

### 2. DATOS DE FILIACIÓN:
- Apellido y Nombre: {nombre or '[Completar]'}
- HC: {hc or '[Completar]'}
- Edad: {edad_texto or f'{edad_num} años'}
- Fecha de nacimiento: {fecha_nac or '[Completar]'}
- Fecha de evaluación: {fecha_eval}
- Escolaridad: {escolaridad or '[Completar]'}
- Nacionalidad: {nacionalidad}
- Preferencia manual: {preferencia}
- Médico Solicitante: {medico or '[Completar]'}
- Acompañante: {acompanante}

### 3. MOTIVO DE CONSULTA Y ANTECEDENTES:
- Quién deriva y motivo: {quien_deriva}
- Diagnósticos y tratamientos actuales: {tratamientos}
- Evaluaciones previas: {eval_previas}

### 4. OBSERVACIÓN DE LA CONDUCTA (Convertir en 2-3 párrafos fluidos y formales):
- Contacto y vínculo: {obs_vinculo}
- Predisposición: {obs_predisp}
- Comprensión de consignas: {obs_consignas}
- Desatención: {obs_desatencion}
- Inquietud motora: {obs_motora}
- Impulsividad: {obs_impulsividad}
- Tolerancia a la frustración: {obs_frustracion}
- Ansiedad frente al error: {obs_ansiedad}
- Ritmo de trabajo y fatiga: {obs_ritmo}
- Lenguaje expresivo: {obs_lenguaje}
- Observaciones adicionales: {obs_extra}

### 5. BATERÍAS ADMINISTRADAS:
{', '.join(pruebas_usadas)}

### 6. TABLA DE PUNTUACIONES YA PROCESADAS A PUNTAJE Z Y RANGO FLENI:
{tabla_z_markdown}

### 7. DATOS ADICIONALES DE LA PLANILLA DE PUNTUACIONES:
{texto_puntajes_libre}

### 8. NOTAS CUALITATIVAS POR DOMINIO (FICHA DE CARGA):
- **Wechsler (IC 95% / ICG / Índices secundarios / Cualitativo):** {ic_cit} | {indices_sec} | {obs_wechsler}
- **Memoria y Aprendizaje:** {obs_memoria}
- **Atención y Funciones Ejecutivas:** {obs_atencion_fe}
- **Visomotor y Lenguaje:** {obs_viso_leng}
- **Psicopedagógico (Alfabetización: {alfabetizado}):**
  - Letra y prensión: {tipo_letra}
  - Ejemplos literales dictado/NALPA: {nalpa_dictado}
  - Lectura / PROLEC: {lectura_prolec}
  - Matemática / Woodcock-Muñoz / TEMA-3: {calculo_woodcock}
- **Cuestionarios / Vineland / DIVA-5:** {cuestionarios_txt}

### 9. IMPRESIÓN CLÍNICA Y RECOMENDACIONES SOLICITADAS:
- Foco a destacar en Conclusiones: {impresion_destacar}
- Perfil de recomendaciones: {perfil_recom}
- Derivaciones seleccionadas: {', '.join(derivaciones)}
- Frecuencia sugerida: {frecuencia_sug} | Reevaluación en: {reevaluacion}
- Recomendaciones puntuales escuela/casa: {recom_escuela_casa}
"""

                # 3. Llamada al modelo Gemini con System Instruction + PDFs + Prompt del Caso
                model = genai.GenerativeModel(
                    model_name=modelo_gemini,
                    system_instruction=construir_system_prompt(),
                    generation_config={"temperature": temperatura}
                )

                payload = contenido_multimedia + [prompt_caso]
                respuesta = model.generate_content(payload)

                # Limpiar archivos temporales
                for path in archivos_temp:
                    if os.path.exists(path):
                        os.remove(path)

                st.success("✅ Informe generado con éxito.")
                st.subheader("📄 Vista Previa del Informe Clínico")
                st.markdown(respuesta.text)

                st.download_button(
                    label="⬇️ Descargar Informe (.md / compatible con Word y Docs)",
                    data=respuesta.text,
                    file_name=f"Informe_FLENI_{(nombre or 'Paciente').replace(' ', '_')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )

            except Exception as e:
                st.error(f"Error durante la generación: {e}")