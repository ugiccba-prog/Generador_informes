import streamlit as st
import google.generativeai as genai
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import io
import re

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y GESTIÓN DE MEMORIA DE SESIÓN
# ==============================================================================
st.set_page_config(
    page_title="Plataforma Clínica de Informes Neuropsicológicos",
    page_icon="🧠",
    layout="wide"
)

if "informe_texto" not in st.session_state:
    st.session_state.informe_texto = None
if "informe_docx" not in st.session_state:
    st.session_state.informe_docx = None
if "nombre_archivo" not in st.session_state:
    st.session_state.nombre_archivo = "Informe_Clinico.docx"
if "grilla_final" not in st.session_state:
    st.session_state.grilla_final = []

# Lectura segura de API Key (Nube en Streamlit Secrets o Local en PC)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    API_KEY = "TU_API_KEY_LOCAL"

genai.configure(api_key=API_KEY)


# ==============================================================================
# 2. MOTOR MATEMÁTICO DETERMINISTA (CÁLCULO EXACTO DE PUNTAJE Z Y DISCREPANCIAS)
# ==============================================================================
def calcular_metricas_psicometricas(valor: float, tipo_escala: str, invertido: bool = False):
    """
    Calcula el Puntaje Z exacto y el percentil estimado sin intervención de IA:
    - CI / Estándar: Media = 100, DE = 15
    - Escalar: Media = 10, DE = 3
    - Puntaje T: Media = 50, DE = 10 (Si invertido=True, +T indica mayor síntoma/dificultad)
    - Puntaje Z Directo: Media = 0, DE = 1
    """
    if tipo_escala == "CI (M=100, DE=15)":
        z = (valor - 100.0) / 15.0
    elif tipo_escala == "Escalar (M=10, DE=3)":
        z = (valor - 10.0) / 3.0
    elif tipo_escala == "Puntaje T (M=50, DE=10)":
        z = (valor - 50.0) / 10.0
        if invertido:
            z = -z
    elif tipo_escala == "Puntaje Z Directo":
        z = float(valor)
    else:
        z = 0.0

    # Clasificación normativa institucional según Puntaje Z
    if z >= 1.33:
        rango = "Superior"
    elif 0.67 <= z < 1.33:
        rango = "Normal Alto"
    elif -0.67 <= z < 0.67:
        rango = "Normal (Promedio)"
    elif -1.33 <= z < -0.67:
        rango = "Normal Bajo (Riesgo Leve)"
    elif -2.00 <= z < -1.33:
        rango = "Dificultad Moderada (Descenso)"
    else:
        rango = "Dificultad Severa (Déficit)"

    return round(z, 2), f"{z:+.2f}", rango


def analizar_discrepancia_wisc(icv: int, ive: int, irf: int, imt: int, ivp: int) -> str:
    """
    Detecta matemáticamente si existe discrepancia clínica entre el potencial
    conceptual (ICV/IRF) y la eficiencia operativa (IMT/IVP).
    """
    promedio_conceptual = (icv + irf) / 2.0
    promedio_operativo = (imt + ivp) / 2.0
    brecha = promedio_conceptual - promedio_operativo

    if brecha >= 15:
        return (
            f"ALERTA PSICOMÉTRICA DETECTADA POR EL MOTOR: Existe una discrepancia estadísticamente "
            f"significativa de {brecha:.1f} puntos entre los índices conceptuales/razonamiento "
            f"(promedio {promedio_conceptual:.0f}) y los índices de eficiencia operativa IMT/IVP "
            f"(promedio {promedio_operativo:.0f}). Explicá rigurosamente en el informe que el CI Total "
            f"debe interpretarse con cautela por esta dispersión, y detallá cómo el cuello de botella "
            f"en memoria operativa y velocidad penaliza su rendimiento áulico pese a su buen potencial conceptual."
        )
    return "Perfil intelectual sin discrepancias extremas entre el área conceptual y la operativa."


# ==============================================================================
# 3. DISEÑO AVANZADO EN WORD (COLORES DE CELDA, PADDING Y NEGRITAS NATIVAS)
# ==============================================================================
def estilizar_celda_word(cell, color_hex: str = None, padding_pt: int = 4):
    """Aplica color de fondo hexadecimal y márgenes internos a una celda de Word."""
    tcPr = cell._tc.get_or_add_tcPr()
    if color_hex:
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), color_hex)
        tcPr.append(shd)

    tcMar = OxmlElement("w:tcMar")
    for lado in ["top", "bottom", "left", "right"]:
        nodo = OxmlElement(f"w:{lado}")
        nodo.set(qn("w:w"), str(padding_pt * 20))
        nodo.set(qn("w:type"), "dxa")
        tcMar.append(nodo)
    tcPr.append(tcMar)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def inyectar_texto_formateado_en_word(doc: Document, texto_ia: str):
    """
    Convierte los subtítulos ### y las **negritas** de Gemini en formato nativo
    de Microsoft Word justificado, eliminando cualquier asterisco residual.
    """
    for linea in texto_ia.split("\n"):
        linea_limpia = linea.strip()
        if not linea_limpia:
            continue

        # Subtítulos de dominios
        if linea_limpia.startswith("### ") or linea_limpia.startswith("## "):
            titulo_limpio = linea_limpia.replace("### ", "").replace("## ", "").replace("**", "")
            h = doc.add_heading(titulo_limpio, level=3)
            h.paragraph_format.space_before = Pt(10)
            h.paragraph_format.space_after = Pt(4)
            for run in h.runs:
                run.font.name = "Arial"
                run.font.size = Pt(11)
                run.font.bold = True
                run.font.color.rgb = RGBColor(31, 78, 121)
            continue

        # Viñetas
        es_lista = False
        if linea_limpia.startswith("* ") or linea_limpia.startswith("- "):
            linea_limpia = linea_limpia[2:]
            es_lista = True

        p = doc.add_paragraph(style="List Bullet" if es_lista else "Normal")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15

        # Conversión de **calificadores** a negritas nativas
        partes = re.split(r"(\*\*.*?\*\*)", linea_limpia)
        for parte in partes:
            if parte.startswith("**") and parte.endswith("**"):
                run = p.add_run(parte[2:-2])
                run.bold = True
            else:
                run = p.add_run(parte)
            run.font.name = "Arial"
            run.font.size = Pt(10.5)


def construir_documento_word(datos_fil: dict, grilla: list, texto_ia: str, sugerencias: list) -> io.BytesIO:
    doc = Document()

    # Márgenes institucionales (2.54 cm)
    for section in doc.sections:
        section.top_margin = Inches(0.9)
        section.bottom_margin = Inches(0.9)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10.5)
    style.font.color.rgb = RGBColor(25, 25, 25)

    # Membrete Superior
    p_enc = doc.add_paragraph()
    p_enc.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run_enc = p_enc.add_run("SERVICIO DE NEUROPSICOLOGÍA Y PSICOPEDAGOGÍA CLÍNICA\nProtocolo Institucional de Evaluación")
    run_enc.font.name = "Arial"
    run_enc.font.size = Pt(8.5)
    run_enc.font.color.rgb = RGBColor(110, 110, 110)

    # Título Central
    titulo = doc.add_heading("INFORME DE EVALUACIÓN NEUROPSICOLÓGICA Y PSICOPEDAGÓGICA", level=1)
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    titulo.paragraph_format.space_after = Pt(12)
    for run in titulo.runs:
        run.font.name = "Arial"
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = RGBColor(20, 50, 90)

    # 1. Tabla de Datos de Filiación
    h1 = doc.add_heading("1. Datos de Filiación", level=2)
    for r in h1.runs:
        r.font.name = "Arial"
        r.font.size = Pt(11.5)
        r.font.color.rgb = RGBColor(20, 50, 90)

    tabla_fil = doc.add_table(rows=3, cols=2)
    tabla_fil.style = "Table Grid"
    tabla_fil.alignment = WD_TABLE_ALIGNMENT.CENTER

    pares_fil = [
        (f"Paciente: {datos_fil['paciente']}", f"N° HC / Legajo: {datos_fil['hc']}"),
        (f"Edad Cronológica: {datos_fil['edad']}", f"Escolaridad: {datos_fil['escolaridad']}"),
        (f"Fecha de Evaluación: {datos_fil['fecha']}", f"Profesional Actuante: {datos_fil['profesional']}")
    ]
    for idx, (col1, col2) in enumerate(pares_fil):
        celdas = tabla_fil.rows[idx].cells
        celdas[0].text = col1
        celdas[1].text = col2
        for c in celdas:
            estilizar_celda_word(c, color_hex="F9FAFB", padding_pt=5)
            for p in c.paragraphs:
                for r in p.runs:
                    r.font.name = "Arial"
                    r.font.size = Pt(9.5)

    doc.add_paragraph()

    # 2. Tabla Cuantitativa Z con Semáforo Suave Institucional
    h2 = doc.add_heading("2. Grilla Cuantitativa de Resultados (Puntajes Estándar y Z)", level=2)
    for r in h2.runs:
        r.font.name = "Arial"
        r.font.size = Pt(11.5)
        r.font.color.rgb = RGBColor(20, 50, 90)

    tabla_res = doc.add_table(rows=1, cols=6)
    tabla_res.style = "Table Grid"
    tabla_res.alignment = WD_TABLE_ALIGNMENT.CENTER

    encabezados = ["Dominio", "Batería / Test", "Índice / Subtest", "Puntaje", "Puntaje Z", "Clasificación Clínica"]
    hdr_cells = tabla_res.rows[0].cells
    for i, texto_h in enumerate(encabezados):
        hdr_cells[i].text = texto_h
        estilizar_celda_word(hdr_cells[i], color_hex="D9E2F3", padding_pt=5)
        for p in hdr_cells[i].paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True
                r.font.name = "Arial"
                r.font.size = Pt(9)

    for fila in grilla:
        row_cells = tabla_res.add_row().cells
        row_cells[0].text = fila["dominio"]
        row_cells[1].text = fila["bateria"]
        row_cells[2].text = fila["subtest"]
        row_cells[3].text = f"{fila['valor']} ({fila['escala_corta']})"
        row_cells[4].text = fila["z_str"]
        row_cells[5].text = fila["rango"]

        color_fila = "FCE4D6" if fila["z_num"] <= -1.33 else None

        for idx_c, c in enumerate(row_cells):
            estilizar_celda_word(c, color_hex=color_fila if idx_c in [4, 5] else None, padding_pt=4)
            for p in c.paragraphs:
                if idx_c in [3, 4]:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.name = "Arial"
                    r.font.size = Pt(9)
                    if idx_c == 4:
                        r.bold = True

    doc.add_paragraph()

    # 3. Análisis Cualitativo y Teórico redactado por IA
    h3 = doc.add_heading("3. Análisis Cualitativo por Dominios y Conclusiones", level=2)
    for r in h3.runs:
        r.font.name = "Arial"
        r.font.size = Pt(11.5)
        r.font.color.rgb = RGBColor(20, 50, 90)

    inyectar_texto_formateado_en_word(doc, texto_ia)

    doc.add_paragraph()

    # 4. Banco de Sugerencias y Adaptaciones
    h4 = doc.add_heading("4. Sugerencias Terapéuticas y Adaptaciones Escolares", level=2)
    for r in h4.runs:
        r.font.name = "Arial"
        r.font.size = Pt(11.5)
        r.font.color.rgb = RGBColor(20, 50, 90)

    for sug in sugerencias:
        p_sug = doc.add_paragraph(style="List Bullet")
        p_sug.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p_sug.paragraph_format.space_after = Pt(4)
        run_s = p_sug.add_run(sug)
        run_s.font.name = "Arial"
        run_s.font.size = Pt(10.5)

    # Recuadro Ético Médico Obligatorio
    doc.add_paragraph()
    tabla_etica = doc.add_table(rows=1, cols=1)
    tabla_etica.style = "Table Grid"
    celda_etica = tabla_etica.rows[0].cells[0]
    estilizar_celda_word(celda_etica, color_hex="F2F4F8", padding_pt=8)
    p_legal = celda_etica.paragraphs[0]
    p_legal.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run_legal = p_legal.add_run(
        "ACLARACIÓN ÉTICA Y DIAGNÓSTICA: Los hallazgos expuestos en el presente informe describen el perfil "
        "cuantitativo y cualitativo de funcionamiento neurocognitivo y psicopedagógico al momento de la evaluación. "
        "Se deja constancia expresa de que el diagnóstico clínico definitivo será dado exclusivamente por un médico "
        "(neurólogo infantil, psiquiatra o pediatra del desarrollo tratante) a través de la integración médica integral."
    )
    run_legal.bold = True
    run_legal.font.name = "Arial"
    run_legal.font.size = Pt(9.5)

    # Firma Profesional
    p_firma = doc.add_paragraph("\n\n________________________________________\n")
    p_firma.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run_f = p_firma.add_run(f"{datos_fil['profesional']}\nEvaluación Neuropsicológica y Psicopedagógica")
    run_f.bold = True
    run_f.font.name = "Arial"
    run_f.font.size = Pt(10)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


# ==============================================================================
# 4. INTERFAZ WEB COMPLETA CON PESTAÑAS CLÍNICAS (CAMPOS VACÍOS)
# ==============================================================================
st.title("🧠 Plataforma de Informes Neuropsicológicos y Psicopedagógicos")
st.markdown("Cálculo psicométrico determinista en Puntaje Z + Redacción clínica asistida con estándar institucional.")

with st.form("formulario_integral"):
    st.subheader("1. Datos de Filiación y Contexto Clínico")
    col1, col2, col3 = st.columns(3)
    with col1:
        paciente = st.text_input("Apellido y Nombre / Iniciales", value="")
        edad = st.text_input("Edad (Años y meses)", value="")
    with col2:
        hc = st.text_input("N° de HC / Legajo", value="")
        escolaridad = st.text_input("Escolaridad / Grado", value="")
    with col3:
        fecha_eval = st.text_input("Fecha de Evaluación", value="")
        profesional = st.text_input("Profesional Actuante", value="")

    col_mot, col_obs = st.columns(2)
    with col_mot:
        motivo_consulta = st.text_area(
            "Motivo de Consulta / Derivación",
            value=""
        )
    with col_obs:
        observacion_conducta = st.text_area(
            "Observación Conductual en Sesión",
            value=""
        )

    st.divider()
    st.subheader("2. Carga de Baterías Administradas (Cálculo Z Determinista)")
    st.caption("Tildá las baterías que administraste para que el motor calcule sus Puntajes Z e integre sus análisis.")

    tab_wisc, tab_atencion, tab_memoria, tab_lecto, tab_conducta = st.tabs([
        "🧩 1. Intelectual (WISC-V)",
        "🎯 2. Atención y FE (CPT / Nesplora / NEPSY)",
        "🧠 3. Memoria (TOMAL / NEPSY)",
        "📖 4. Lectoescritura y Cálculo (PROLEC / WM)",
        "📋 5. Escalas Conductuales (BRIEF-2 / SNAP)"
    ])

    with tab_wisc:
        incluir_wisc = st.checkbox("Incluir batería WISC-V en el informe", value=False)
        w1, w2, w3, w4, w5, w6 = st.columns(6)
        with w1:
            icv = st.number_input("Comp. Verbal (ICV)", 40, 160, 100, step=1)
        with w2:
            ive = st.number_input("Visuoespacial (IVE)", 40, 160, 100, step=1)
        with w3:
            irf = st.number_input("Raz. Fluido (IRF)", 40, 160, 100, step=1)
        with w4:
            imt = st.number_input("Mem. Trabajo (IMT)", 40, 160, 100, step=1)
        with w5:
            ivp = st.number_input("Vel. Procesam. (IVP)", 40, 160, 100, step=1)
        with w6:
            cit = st.number_input("CI Total (CIT)", 40, 160, 100, step=1)

    with tab_atencion:
        incluir_atencion = st.checkbox("Incluir pruebas de Atención y Funciones Ejecutivas", value=False)
        a1, a2, a3, a4, a5 = st.columns(5)
        with a1:
            cpt_omi = st.number_input("CPT / Nesplora: Omisiones (T)", 20, 100, 50, step=1)
        with a2:
            cpt_com = st.number_input("CPT / Nesplora: Comisiones (T)", 20, 100, 50, step=1)
        with a3:
            cpt_rt = st.number_input("CPT / Nesplora: Tiempo Reacción (T)", 20, 100, 50, step=1)
        with a4:
            nepsy_inh = st.number_input("NEPSY-II: Inhibición (Escalar)", 1, 19, 10, step=1)
        with a5:
            nepsy_flu = st.number_input("NEPSY-II: Fluidez Diseños (Escalar)", 1, 19, 10, step=1)

    with tab_memoria:
        incluir_memoria = st.checkbox("Incluir pruebas de Memoria y Aprendizaje (TOMAL)", value=False)
        m1, m2, m3 = st.columns(3)
        with m1:
            tomal_mv = st.number_input("TOMAL: Memoria Verbal (Escalar)", 1, 19, 10, step=1)
        with m2:
            tomal_mnv = st.number_input("TOMAL: Memoria No Verbal (Escalar)", 1, 19, 10, step=1)
        with m3:
            tomal_rd = st.number_input("TOMAL: Recuerdo Demorado (Escalar)", 1, 19, 10, step=1)

    with tab_lecto:
        incluir_lecto = st.checkbox("Incluir Lectoescritura y Cálculo (PROLEC-R / Woodcock-Muñoz)", value=False)
        l1, l2, l3, l4, l5 = st.columns(5)
        with l1:
            prolec_pal = st.number_input("PROLEC-R: Lectura Palabras (Z)", -4.0, 4.0, 0.0, step=0.1)
        with l2:
            prolec_pse = st.number_input("PROLEC-R: Pseudopalabras (Z)", -4.0, 4.0, 0.0, step=0.1)
        with l3:
            prolec_com = st.number_input("PROLEC-R: Comprensión Textos (Z)", -4.0, 4.0, 0.0, step=0.1)
        with l4:
            wm_calc = st.number_input("Woodcock-Muñoz: Cálculo (CI)", 40, 160, 100, step=1)
        with l5:
            wm_prob = st.number_input("Woodcock-Muñoz: Problemas Aplicados (CI)", 40, 160, 100, step=1)

    with tab_conducta:
        incluir_brief = st.checkbox("Incluir Cuestionario Ejecutivo Conductual (BRIEF-2)", value=False)
        b1, b2, b3 = st.columns(3)
        with b1:
            brief_inh = st.number_input("BRIEF-2: Regulación Conductual (T)", 30, 100, 50, step=1)
        with b2:
            brief_emo = st.number_input("BRIEF-2: Regulación Emocional (T)", 30, 100, 50, step=1)
        with b3:
            brief_cog = st.number_input("BRIEF-2: Regulación Cognitiva (T)", 30, 100, 50, step=1)

    st.divider()
    st.subheader("3. Banco de Recomendaciones Terapéuticas y Adaptaciones Escolares")
    opciones_sugerencias = [
        "Terapéutico: Tratamiento psicopedagógico clínico orientado a la rehabilitación de procesos lectores, funciones ejecutivas y memoria operativa.",
        "Terapéutico: Espacio psicoterapéutico de orientación cognitivo-conductual (TCC) para el fortalecimiento de la autorregulación emocional y tolerancia a la frustración.",
        "Terapéutico: Seguimiento e interconsulta con Neurología Infantil para valoración médica integral del perfil neurobiológico y atencional.",
        "Escolar (Acceso): Ubicación preferencial en las primeras filas del aula, cercana al docente y alejada de ventanas o pasillos de alta circulación.",
        "Escolar (Metodológica): Segmentación de consignas extensas en pasos breves, secuenciados y con apoyo de organizadores visuales.",
        "Escolar (Evaluación): Otorgamiento de tiempo adicional en evaluaciones escritas, priorizando la resolución conceptual por sobre el volumen de copiado.",
        "Escolar (Lectoescritura): Uso de tipografía clara (imprenta mayúscula o Arial 12 con interlineado 1.5) y verificación oral de la comprensión de consignas.",
        "Escolar (Regulación): Implementación de pausas activas programadas cada 20-25 minutos de demanda cognitiva sostenida para mitigar la fatiga atencional."
    ]
sugerencias_seleccionadas = st.multiselect(
        "Seleccioná las recomendaciones estandarizadas:",
        options=opciones_sugerencias,
        default=[]
    )
    sugerencia_extra = st.text_input(
        "Agregar recomendación personalizada adicional (opcional):",
        placeholder="Ej: Articulación periódica entre el equipo tratante externo y el gabinete escolar."
    )

    boton_generar = st.form_submit_button("🚀 Calcular Baremos Z y Generar Informe Word Completo")

# ==============================================================================
# 5. EJECUCIÓN DEL MOTOR PSICOMÉTRICO Y REDACCIÓN CLÍNICA
# ==============================================================================
if boton_generar:
    pruebas_crudas = []
    alerta_discrepancia = ""

    if incluir_wisc:
        alerta_discrepancia = analizar_discrepancia_wisc(icv, ive, irf, imt, ivp)
        pruebas_crudas.extend([
            ("Intelectual", "WISC-V", "Comprensión Verbal (ICV)", icv, "CI (M=100, DE=15)", "CI", False),
            ("Intelectual", "WISC-V", "Visuoespacial (IVE)", ive, "CI (M=100, DE=15)", "CI", False),
            ("Intelectual", "WISC-V", "Razonamiento Fluido (IRF)", irf, "CI (M=100, DE=15)", "CI", False),
            ("Intelectual", "WISC-V", "Memoria de Trabajo (IMT)", imt, "CI (M=100, DE=15)", "CI", False),
            ("Intelectual", "WISC-V", "Velocidad de Procesamiento (IVP)", ivp, "CI (M=100, DE=15)", "CI", False),
            ("Intelectual", "WISC-V", "Escala Total (CIT)", cit, "CI (M=100, DE=15)", "CI", False),
        ])

    if incluir_atencion:
        pruebas_crudas.extend([
            ("Atención / FE", "CPT / Nesplora", "Omisiones (Atención Sostenida)", cpt_omi, "Puntaje T (M=50, DE=10)", "T", True),
            ("Atención / FE", "CPT / Nesplora", "Comisiones (Control Inhibitorio)", cpt_com, "Puntaje T (M=50, DE=10)", "T", True),
            ("Atención / FE", "CPT / Nesplora", "Tiempo de Reacción (Velocidad)", cpt_rt, "Puntaje T (M=50, DE=10)", "T", True),
            ("Atención / FE", "NEPSY-II", "Inhibición y Flexibilidad Cognitiva", nepsy_inh, "Escalar (M=10, DE=3)", "Escalar", False),
            ("Atención / FE", "NEPSY-II", "Fluidez de Diseños (Productividad)", nepsy_flu, "Escalar (M=10, DE=3)", "Escalar", False),
        ])

    if incluir_memoria:
        pruebas_crudas.extend([
            ("Memoria", "TOMAL", "Memoria Verbal Inmediata", tomal_mv, "Escalar (M=10, DE=3)", "Escalar", False),
            ("Memoria", "TOMAL", "Memoria No Verbal", tomal_mnv, "Escalar (M=10, DE=3)", "Escalar", False),
            ("Memoria", "TOMAL", "Recuerdo Demorado Asociativo", tomal_rd, "Escalar (M=10, DE=3)", "Escalar", False),
        ])

    if incluir_lecto:
        pruebas_crudas.extend([
            ("Académico", "PROLEC-R", "Lectura de Palabras (Ruta Léxica)", prolec_pal, "Puntaje Z Directo", "Z", False),
            ("Académico", "PROLEC-R", "Lectura de Pseudopalabras (Ruta Fonológica)", prolec_pse, "Puntaje Z Directo", "Z", False),
            ("Académico", "PROLEC-R", "Comprensión Lectora de Textos", prolec_com, "Puntaje Z Directo", "Z", False),
            ("Académico", "Woodcock-Muñoz", "Cálculo y Fluidez Matemática", wm_calc, "CI (M=100, DE=15)", "Estándar", False),
            ("Académico", "Woodcock-Muñoz", "Problemas Aplicados (Razonamiento Mat.)", wm_prob, "CI (M=100, DE=15)", "Estándar", False),
        ])

    if incluir_brief:
        pruebas_crudas.extend([
            ("Conductual", "BRIEF-2", "Índice de Regulación Conductual (BRI)", brief_inh, "Puntaje T (M=50, DE=10)", "T", True),
            ("Conductual", "BRIEF-2", "Índice de Regulación Emocional (ERI)", brief_emo, "Puntaje T (M=50, DE=10)", "T", True),
            ("Conductual", "BRIEF-2", "Índice de Regulación Cognitiva (CRI)", brief_cog, "Puntaje T (M=50, DE=10)", "T", True),
        ])

    grilla_calculada = []
    for dom, bat, sub, val, escala_larga, escala_corta, inv in pruebas_crudas:
        z_num, z_str, rango = calcular_metricas_psicometricas(val, escala_larga, inv)
        grilla_calculada.append({
            "dominio": dom,
            "bateria": bat,
            "subtest": sub,
            "valor": val,
            "escala_corta": escala_corta,
            "z_num": z_num,
            "z_str": z_str,
            "rango": rango
        })

    lista_sugerencias_final = list(sugerencias_seleccionadas)
    if sugerencia_extra.strip():
        lista_sugerencias_final.append(sugerencia_extra.strip())

    prompt_clinico = f"""
    Actuá como un neuropsicólogo y psicopedagogo clínico senior redactando un informe institucional formal (estilo FLENI).
    
    DATOS DEL PACIENTE:
    - Paciente: {paciente} | Edad: {edad} | Escolaridad: {escolaridad}
    - Motivo de consulta: {motivo_consulta}
    - Observación conductual: {observacion_conducta}
    - Análisis matemático de discrepancia WISC-V: {alerta_discrepancia}
    - Resultados cuantitativos exactos (NO modifiques ni inventes ningún valor numérico): {grilla_calculada}

    ESTRUCTURA Y REGLAS CLÍNICAS OBLIGATORIAS:
    1. Usá subtítulos con formato '### Nombre del Apartado'.
    2. Redactá únicamente los apartados de las baterías incluidas en los datos:
       - ### Motivo de Consulta y Antecedentes
       - ### Observación de la Conducta y Modalidad de Trabajo
       - ### Funcionamiento Intelectual y Discrepancias Operativas (si se incluyó WISC-V)
       - ### Atención y Funciones Ejecutivas (si se incluyó CPT / NEPSY-II)
       - ### Memoria y Aprendizaje (si se incluyó TOMAL)
       - ### Habilidades Académicas, Lectoescritura y Cálculo (si se incluyó PROLEC-R / Woodcock-Muñoz)
       - ### Funcionamiento Ejecutivo Ecológico y Conductual (si se incluyó BRIEF-2)
       - ### Conclusiones e Integración del Perfil Neuropsicológico
    3. SUSTENTO TEÓRICO: Iniciá cada dominio con una introducción teórica rigurosa sobre qué evalúa ese proceso neurocognitivo y su impacto funcional en el aprendizaje escolar.
    4. REGLA DE NEGRITAS: Utilizá **negritas** ÚNICAMENTE en los calificadores de desempeño cuantitativo y cualitativo (ej. **adecuado**, **acorde a lo esperado**, **dificultades**, **por debajo de la media**, **descenso significativo**, **fortaleza**). Jamás uses negritas en nombres de pruebas ni en conceptos teóricos.
    5. REGLA ÉTICA MÉDICA INQUEBRANTABLE: En el apartado de 'Conclusiones e Integración del Perfil Neuropsicológico', integrá las fortalezas y debilidades halladas, pero ACLARÁ SIEMPRE Y DE FORMA EXPLÍCITA que el diagnóstico clínico definitivo será dado por un médico tratante. Nunca emitas un diagnóstico médico cerrado por cuenta propia.
    """

    with st.spinner("🧠 Analizando perfil neurocognitivo y maquetando documento Word institucional..."):
        model = genai.GenerativeModel("gemini-3.8-flash")
        respuesta = model.generate_content(prompt_clinico)
        texto_ia = respuesta.text

        datos_fil = {
            "paciente": paciente,
            "hc": hc,
            "edad": edad,
            "escolaridad": escolaridad,
            "fecha": fecha_eval,
            "profesional": profesional
        }

        archivo_word_memoria = construir_documento_word(
            datos_fil=datos_fil,
            grilla=grilla_calculada,
            texto_ia=texto_ia,
            sugerencias=lista_sugerencias_final
        )

        st.session_state.grilla_final = grilla_calculada
        st.session_state.informe_texto = texto_ia
        st.session_state.informe_docx = archivo_word_memoria
        st.session_state.nombre_archivo = f"Informe_Clinico_{paciente.replace(', ', '_').replace(' ', '_')}.docx"

# ==============================================================================
# 6. PANEL DE RESULTADOS PERSISTENTE Y DESCARGA
# ==============================================================================
if st.session_state.informe_docx is not None:
    st.success("✅ ¡Informe clínico integral generado y listo para descargar!")

    st.download_button(
        label="📥 Descargar Informe Word Institucional (.docx)",
        data=st.session_state.informe_docx,
        file_name=st.session_state.nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )

    with st.expander("📊 Ver Tabla Psicométrica Calculada (Puntajes Z)", expanded=True):
        st.dataframe(st.session_state.grilla_final, use_container_width=True)

    with st.expander("📄 Vista Previa del Texto Clínico Redactado", expanded=False):
        st.markdown(st.session_state.informe_texto)