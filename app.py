"""Interfaz Streamlit para la Plataforma Clínica de Informes Neuropsicológicos."""

from datetime import date
from pathlib import PurePath
import pandas as pd
import streamlit as st

from catalogo_clinico import (
    BANCO_SUGERENCIAS,
    CATALOGO_SUBPRUEBAS,
    ESCALA_CI,
    ESCALA_ESCALAR,
    ESCALA_PERCENTIL,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALAS_CALCULADORA,
    ESCALAS_DISPONIBLES,
    MODELOS_GEMINI,
    MODELOS_INFORME,
)
from borrador import construir_borrador, grilla_markdown
from exportador_docx import generar_docx_bytes
from memoria_drive import leer_guia, recurso_configurado, validar_guia
import motor_ia
from motor_ia import resolver_api_key
from psicometria import (
    calcular_edad_exacta,
    calcular_z_y_rango,
    categoria_color_rango,
    formatear_edad,
    procesar_tabla_puntajes,
    sanitizar_nombre_archivo,
)

# =====================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =====================================================================
st.set_page_config(
    page_title="Generador Profesional de Informes Clínicos",
    page_icon="🧠",
    layout="wide",
)

COLUMNAS_EDITOR = ["Dominio / Prueba / Subtest", "Puntaje", "Tipo de Escala", "Observación"]
SUBPRUEBAS_CATALOGO_SET = {sub for lista in CATALOGO_SUBPRUEBAS.values() for sub, _ in lista}

DEFAULTS_CALCULADORA = {
    ESCALA_ESCALAR: 10.0,
    ESCALA_CI: 100.0,
    ESCALA_T_DIRECTO: 50.0,
    ESCALA_T_INVERSO: 50.0,
    ESCALA_PERCENTIL: 50.0,
}

# =====================================================================
# 2. PANEL LATERAL: CONFIGURACIÓN Y CALCULADORA RÁPIDA Z
# =====================================================================
st.title("🧠 Generador Profesional de Informes Clínicos")
st.caption("Evaluación Neuropsicológica, Desempeño Cognitivo y Psicopedagógica")

with st.sidebar:
    st.header("Configuración")
    usar_ia = st.toggle("Asistencia de redacción con Gemini", value=False)
    api_key = ""
    modelo_gemini = ""
    thinking_level = ""
    guia_aprobada = ""

    if usar_ia:
        api_key = resolver_api_key(st.secrets)
        if not api_key:
            api_key = st.text_input("Clave de Gemini", type="password")

        modelo_gemini = st.selectbox(
            "Modelo de IA",
            options=list(MODELOS_GEMINI),
            format_func=lambda modelo: MODELOS_GEMINI[modelo]["label"],
        )
        config_modelo = MODELOS_GEMINI[modelo_gemini]
        thinking_level = st.selectbox(
            "Nivel de razonamiento",
            options=config_modelo["thinking_levels"],
            index=config_modelo["thinking_levels"].index(config_modelo["default_thinking"]),
            key=f"razonamiento_{modelo_gemini}",
        )
        st.caption("Gemini recibe los puntajes, las notas y los adjuntos que confirmes.")

    st.divider()
    st.subheader("Memoria de Drive")
    carpeta_id = recurso_configurado("MEMORIA_DRIVE_CARPETA_ID", st.secrets)
    guia_id = recurso_configurado("MEMORIA_DRIVE_GUIA_ID", st.secrets)
    if carpeta_id:
        st.link_button("Abrir carpeta Memoria", f"https://drive.google.com/drive/folders/{carpeta_id}")
    if guia_id and st.button("Cargar guía de redacción de Drive"):
        try:
            titulo_guia, texto_guia = leer_guia(guia_id)
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            st.session_state["titulo_guia_memoria"] = titulo_guia
            st.session_state["guia_memoria"] = texto_guia
            st.session_state["revision_guia_memoria"] = st.session_state.get("revision_guia_memoria", 0) + 1

    if st.session_state.get("titulo_guia_memoria"):
        st.caption(f"Fuente cargada: {st.session_state['titulo_guia_memoria']}")
    with st.expander("Guía de redacción"):
        revision_guia = st.session_state.get("revision_guia_memoria", 0)
        texto_guia = st.text_area(
            "Referencia de estilo revisada (opcional)",
            value=st.session_state.get("guia_memoria", ""),
            key=f"texto_guia_{revision_guia}",
            height=180,
            placeholder="Pegá un extracto de estilo de Memoria sin datos de casos.",
        )
        if usar_ia and texto_guia.strip():
            if st.checkbox("Incluir esta guía revisada en la solicitud a Gemini", key=f"confirmar_guia_{revision_guia}"):
                try:
                    guia_aprobada = validar_guia(texto_guia)
                except ValueError as error:
                    st.error(str(error))
                    guia_aprobada = None
        st.caption("Usá el manual de la edición y población correspondiente para confirmar cada baremo.")

    st.divider()
    st.subheader("🧮 Calculadora Rápida a Z")
    esc_calc = st.selectbox("Escala", ESCALAS_CALCULADORA, key="calc_escala")

    if st.session_state.get("prev_calc_escala") != esc_calc:
        st.session_state["calc_valor"] = DEFAULTS_CALCULADORA.get(esc_calc, 10.0)
        st.session_state["prev_calc_escala"] = esc_calc
    elif "calc_valor" not in st.session_state:
        st.session_state["calc_valor"] = DEFAULTS_CALCULADORA.get(esc_calc, 10.0)

    if esc_calc == ESCALA_PERCENTIL:
        val_calc = st.number_input(
            "Puntaje (Percentil 1-99)",
            min_value=1.0,
            max_value=99.0,
            step=1.0,
            key="calc_valor",
        )
    else:
        val_calc = st.number_input("Puntaje", step=1.0, key="calc_valor")

    z_res, rango_res = calcular_z_y_rango(val_calc, esc_calc)
    st.metric(
        label="Equivalencia Z",
        value=f"Z = {z_res:+.2f}" if z_res is not None else "N/A",
    )

    cat_color = categoria_color_rango(rango_res)
    if cat_color == "deficit":
        st.error(f"**Rango:** {rango_res}")
    elif cat_color in ("limitrofe_bajo", "dificultad", "tendencia_baja"):
        st.warning(f"**Rango:** {rango_res}")
    elif cat_color == "normal":
        st.success(f"**Rango:** {rango_res}")
    elif cat_color in ("tendencia_alta", "normal_alto", "superior"):
        st.info(f"**Rango:** {rango_res}")
    else:
        st.caption(f"**Rango:** {rango_res}")

# =====================================================================
# 3. SECCIÓN 1: MODELO DE INFORME Y PRUEBAS ADMINISTRADAS
# =====================================================================
st.header("1. Tipo de Informe y Baterías Administradas")

col_mod1, col_mod2 = st.columns(2)
with col_mod1:
    modelos_seleccionados = st.multiselect(
        "Seleccioná el modelo de informe (podés combinar más de uno):",
        MODELOS_INFORME,
        default=[],
        placeholder="Elegí el modelo de informe...",
    )

with col_mod2:
    pruebas_usadas = st.multiselect(
        "Seleccioná las pruebas y test administrados (cargará sus subpruebas en el Paso 4):",
        list(CATALOGO_SUBPRUEBAS.keys()),
        default=[],
        placeholder="Elegí las pruebas administradas...",
    )

st.divider()

# =====================================================================
# 4. SECCIÓN 2: DATOS DE FILIACIÓN Y PROFESIONAL
# =====================================================================
st.header("2. Datos del Paciente y del Profesional")
st.session_state.setdefault("edad_texto_input", "")

c1, c2, c3, c4 = st.columns(4)
with c1:
    nombre = st.text_input("Apellido y Nombre del Paciente")
    hc = st.text_input("DNI / HC N°")
    fecha_nac = st.date_input(
        "Fecha de nacimiento",
        value=None,
        format="DD/MM/YYYY",
        min_value=date(1920, 1, 1),
        max_value=date(2035, 12, 31),
        key="fecha_nac_input",
    )
with c2:
    fecha_eval = st.date_input(
        "Fecha de evaluación",
        value=None,
        format="DD/MM/YYYY",
        min_value=date(1920, 1, 1),
        max_value=date(2035, 12, 31),
        key="fecha_eval_input",
    )
    fechas_actuales = (fecha_nac, fecha_eval)
    edad_calc = calcular_edad_exacta(fecha_nac, fecha_eval)
    if fecha_nac and fecha_eval and edad_calc is None:
        st.warning("La fecha de evaluación es anterior a la fecha de nacimiento.")
    if st.session_state.get("prev_fechas_edad") != fechas_actuales:
        edad_anterior = st.session_state.get("edad_calculada_previa")
        if edad_calc is not None:
            st.session_state["edad_texto_input"] = formatear_edad(*edad_calc)
        elif st.session_state["edad_texto_input"] == edad_anterior:
            st.session_state["edad_texto_input"] = ""
        st.session_state["edad_calculada_previa"] = formatear_edad(*edad_calc) if edad_calc else None
        st.session_state["prev_fechas_edad"] = fechas_actuales

    edad_texto = st.text_input(
        "Edad (años y meses)",
        key="edad_texto_input",
        placeholder="Se calcula al ingresar ambas fechas o escribí manual",
    )
    escolaridad = st.text_input("Escolaridad (Nivel y Grado/Año)")
with c3:
    preferencia = st.selectbox(
        "Preferencia manual",
        ["", "Diestra", "Zurda", "Ambidiestra / En definición"],
    )
    nacionalidad = st.text_input("Nacionalidad")
    acompanante = st.text_input("Acompañante")
with c4:
    medico = st.text_input("Médico / Institución Solicitante")
    profesional_nombre = st.text_input("Profesional Evaluador/a (para la firma)")
    profesional_matricula = st.text_input("Título y Matrícula Profesional")

st.divider()

# =====================================================================
# 5. SECCIÓN 3: MOTIVO DE CONSULTA Y OBSERVACIÓN DE CONDUCTA
# =====================================================================
st.header("3. Motivo de Consulta y Observación de la Conducta")
col_m1, col_m2 = st.columns(2)
with col_m1:
    quien_deriva = st.text_area("¿Quién deriva y qué preocupa? (Motivo de consulta)", height=85)
with col_m2:
    antecedentes = st.text_area("Diagnósticos, tratamientos actuales y evaluaciones previas", height=85)

st.subheader("Indicadores Conductuales Observados")
cb1, cb2, cb3 = st.columns(3)
with cb1:
    obs_vinculo = st.selectbox(
        "Contacto y vínculo",
        ["", "Adecuado", "Reticente al inicio, luego adecuado", "Otro"],
    )
    obs_predisp = st.selectbox(
        "Predisposición",
        ["", "Buena", "Variable", "Intenta dirigir la situación"],
    )
    obs_consignas = st.selectbox(
        "Comprensión de consignas",
        ["", "Comprende adecuadamente", "Requiere repetición y segmentación"],
    )
    obs_desatencion = st.selectbox(
        "Atención durante la evaluación",
        ["", "Sostiene el foco adecuadamente", "Tiempos atencionales breves", "Se dispersa frente a estímulos"],
    )
with cb2:
    obs_motora = st.selectbox(
        "Actividad motora",
        ["", "Adecuada (Estable en su silla)", "Movedizo en la silla", "Le cuesta trabajar en silencio"],
    )
    obs_impulsividad = st.selectbox(
        "Estilo de respuesta / Impulsividad",
        ["", "Reflexivo y organizado", "Responde apresurado, errores por descuido"],
    )
    obs_frustracion = st.selectbox(
        "Tolerancia a la frustración",
        ["", "Adecuada", "Baja, con conductas de evitación", "Enojo o fastidio ante la dificultad"],
    )
with cb3:
    obs_ansiedad = st.selectbox(
        "Ansiedad frente al error",
        ["", "No se observa", "Sí, demora respuestas en pruebas con tiempo"],
    )
    obs_ritmo = st.selectbox(
        "Ritmo de trabajo y fatiga",
        ["", "Adecuado y sostenido", "Lento", "Se fatiga rápido hacia el final"],
    )
    obs_lenguaje = st.selectbox(
        "Lenguaje expresivo espontáneo",
        ["", "Adecuado", "Dificultades fonológicas / articulatorias", "Escaso"],
    )

obs_extra = st.text_area("Observaciones cualitativas adicionales de la conducta", height=65)

st.divider()

# =====================================================================
# 6. SECCIÓN 4: CARGA DE PUNTAJES SINCRONIZADA POR BATERÍA
# =====================================================================
st.header("4. Puntuaciones Cuantitativas y Reportes Adjuntos")
st.caption(
    "Las subpruebas y sus escalas se cargan automáticamente según lo que elegiste en el Paso 1. "
    "Solo completá 'Puntaje Obtenido' o 'Notas' (las filas vacías se ignoran automáticamente)."
)


def _crear_df_base_vacio() -> pd.DataFrame:
    df_vacio = pd.DataFrame(columns=COLUMNAS_EDITOR)
    df_vacio["Puntaje"] = pd.to_numeric(df_vacio["Puntaje"], errors="coerce").astype("float64")
    return df_vacio


if "pruebas_previas" not in st.session_state:
    st.session_state["pruebas_previas"] = []
if "editor_version" not in st.session_state:
    st.session_state["editor_version"] = 0
if "cache_subpruebas" not in st.session_state:
    st.session_state["cache_subpruebas"] = {}
if "filas_personalizadas" not in st.session_state:
    st.session_state["filas_personalizadas"] = []
if "df_base_puntajes" not in st.session_state:
    st.session_state["df_base_puntajes"] = _crear_df_base_vacio()
if "ultimo_df_editado" not in st.session_state:
    st.session_state["ultimo_df_editado"] = _crear_df_base_vacio()

if list(pruebas_usadas) != st.session_state["pruebas_previas"]:
    df_prev = st.session_state["ultimo_df_editado"]
    nuevas_personalizadas = []

    if df_prev is not None and not df_prev.empty:
        for _, r in df_prev.iterrows():
            sub_raw = r.get("Dominio / Prueba / Subtest")
            sub_key = "" if pd.isna(sub_raw) else str(sub_raw).strip()
            if not sub_key:
                continue

            punt_raw = r.get("Puntaje")
            punt_val = float(punt_raw) if pd.notna(punt_raw) else None
            esc_raw = r.get("Tipo de Escala")
            esc_val = "" if pd.isna(esc_raw) else str(esc_raw).strip()
            obs_raw = r.get("Observación")
            obs_val = "" if pd.isna(obs_raw) else str(obs_raw).strip()

            if sub_key in SUBPRUEBAS_CATALOGO_SET:
                if punt_val is not None or obs_val:
                    st.session_state["cache_subpruebas"][sub_key] = (punt_val, esc_val, obs_val)
                else:
                    st.session_state["cache_subpruebas"].pop(sub_key, None)
            elif punt_val is not None or obs_val:
                nuevas_personalizadas.append(
                    {
                        "Dominio / Prueba / Subtest": sub_key,
                        "Puntaje": punt_val,
                        "Tipo de Escala": esc_val or ESCALAS_DISPONIBLES[0],
                        "Observación": obs_val,
                    }
                )

    st.session_state["filas_personalizadas"] = nuevas_personalizadas

    filas_auto = []
    vistas = set()
    for prueba in pruebas_usadas:
        for nombre_sub, escala_defecto in CATALOGO_SUBPRUEBAS.get(prueba, []):
            if nombre_sub in vistas:
                continue
            vistas.add(nombre_sub)
            if nombre_sub in st.session_state["cache_subpruebas"]:
                punt_prev, esc_prev, obs_prev = st.session_state["cache_subpruebas"][nombre_sub]
                filas_auto.append(
                    {
                        "Dominio / Prueba / Subtest": nombre_sub,
                        "Puntaje": punt_prev,
                        "Tipo de Escala": esc_prev or escala_defecto,
                        "Observación": obs_prev,
                    }
                )
            else:
                filas_auto.append(
                    {
                        "Dominio / Prueba / Subtest": nombre_sub,
                        "Puntaje": None,
                        "Tipo de Escala": escala_defecto,
                        "Observación": "",
                    }
                )

    filas_auto.extend(st.session_state["filas_personalizadas"])

    df_nuevo = pd.DataFrame(filas_auto, columns=COLUMNAS_EDITOR)
    df_nuevo["Puntaje"] = pd.to_numeric(df_nuevo["Puntaje"], errors="coerce").astype("float64")
    df_nuevo["Dominio / Prueba / Subtest"] = df_nuevo["Dominio / Prueba / Subtest"].fillna("").astype(str)
    df_nuevo["Observación"] = df_nuevo["Observación"].fillna("").astype(str)

    st.session_state["df_base_puntajes"] = df_nuevo
    st.session_state["pruebas_previas"] = list(pruebas_usadas)
    st.session_state["editor_version"] += 1

df_editado = st.data_editor(
    st.session_state["df_base_puntajes"],
    num_rows="dynamic",
    width="stretch",
    key=f"editor_subpruebas_{st.session_state['editor_version']}",
    column_config={
        "Dominio / Prueba / Subtest": st.column_config.TextColumn(
            "Dominio / Prueba / Subtest",
            width="large",
        ),
        "Puntaje": st.column_config.NumberColumn(
            "Puntaje Obtenido",
            format="%.2f",
            help="Ingresá el puntaje. Si no tomaste este subtest, dejalo vacío.",
        ),
        "Tipo de Escala": st.column_config.SelectboxColumn(
            "Tipo de Escala",
            options=ESCALAS_DISPONIBLES,
        ),
        "Observación": st.column_config.TextColumn(
            "Notas de la prueba (ej. Edad Equivalente / Categoría PROLEC)"
        ),
    },
)

st.session_state["ultimo_df_editado"] = df_editado.copy()
df_procesado = procesar_tabla_puntajes(df_editado)

if not df_procesado.empty:
    st.markdown("##### ✅ Resumen de Puntuaciones Calculadas (que se enviarán al informe):")
    st.dataframe(df_procesado, width="stretch", hide_index=True)
    st.caption("La conversión Z es orientativa. Registrá el manual, edición y grupo normativo en Notas.")

col_p1, col_p2 = st.columns(2)
with col_p1:
    texto_puntajes_libre = st.text_area(
        "Pegar tabla de puntuaciones o resultados crudos adicionales (Excel / Planilla / Notas):",
        height=130,
    )
with col_p2:
    archivos_adjuntos = []
    if usar_ia:
        archivos_adjuntos = st.file_uploader(
            "Adjuntar reportes desidentificados (PDF, CSV o TXT)",
            type=["pdf", "csv", "txt"],
            accept_multiple_files=True,
        ) or []
    else:
        st.caption("Para usar un reporte en el borrador local, transcribí sus resultados y la referencia en las notas.")

st.divider()

# =====================================================================
# 7. SECCIÓN 5: DETALLES CUALITATIVOS POR DOMINIO
# =====================================================================
st.header("5. Notas Cualitativas por Dominio y Pruebas")
col_q1, col_q2 = st.columns(2)
with col_q1:
    st.subheader("A. Desempeño Cognitivo y Neuropsicología")
    obs_wechsler = st.text_area(
        "Funcionamiento Intelectual (IC 95%, si se informa ICG, índices secundarios IRC/IMTA, estrategias)",
        height=80,
    )
    obs_memoria = st.text_area(
        "Memoria y Aprendizaje (curva de aprendizaje, intrusiones, pérdida diferida, reconocimiento en Rey)",
        height=80,
    )
    obs_atencion_fe = st.text_area(
        "Atención y Funciones Ejecutivas (CPT índice de confianza, Nesplora distractores, WCST, Stroop, TMT)",
        height=80,
    )
    obs_viso_leng = st.text_area(
        "Visomotor y Lenguaje (estrategia de copia en Rey, prensión, fluidez semántica vs. fonológica)",
        height=80,
    )

with col_q2:
    st.subheader("B. Psicopedagogía y Cuestionarios")
    alfabetizado = st.selectbox("Nivel de alfabetización (si aplica)", ["", "Sí", "No", "En proceso"])
    obs_lectoescritura = st.text_area(
        "Lectura, Escritura y Ortografía (PROLEC-R, EPL, velocidad/precisión, ejemplos literales de NALPA o dictado)",
        height=95,
    )
    obs_matematica = st.text_area(
        "Cálculo y Matemática (Woodcock-Muñoz ejemplos literales de aciertos/errores, TEMA-3 / TOMA-3)",
        height=95,
    )
    cuestionarios_txt = st.text_area(
        "Cuestionarios y Escalas (SNAP-IV, BRIEF, Durand, Autoestima, Vineland, DIVA-5: informante e ítems)",
        height=95,
    )

st.divider()

# =====================================================================
# 8. SECCIÓN 6: CONCLUSIONES Y SUGERENCIAS FINALES
# =====================================================================
st.header("6. Conclusiones y Sugerencias Finales")

col_s1, col_s2 = st.columns(2)
with col_s1:
    impresion_destacar = st.text_area(
        "Síntesis diagnóstica / Qué querés destacar en las Conclusiones:",
        height=100,
        placeholder="Ej: Perfil cognitivo dentro del promedio con vulnerabilidad específica en el sostenimiento atencional y control inhibitorio...",
    )
    frecuencia_y_control = st.text_input(
        "Frecuencia de tratamiento y plazo de reevaluación (opcional)",
        placeholder="Ej: Frecuencia semanal. Reevaluación en 12 meses.",
    )

with col_s2:
    sug_terapeuticas_sel = st.multiselect(
        "Sugerencias Terapéuticas y Derivaciones (elegí las que quieras incluir):",
        options=list(BANCO_SUGERENCIAS["terapeuticas"].keys()),
        default=[],
        placeholder="Seleccionar derivaciones y tratamientos...",
    )
    sug_escolares_sel = st.multiselect(
        "Sugerencias y Adaptaciones para la Escuela (elegí las que quieras incluir):",
        options=list(BANCO_SUGERENCIAS["escolares"].keys()),
        default=[],
        placeholder="Seleccionar adaptaciones escolares...",
    )

recom_personalizadas = st.text_area(
    "Agregar otras sugerencias personalizadas (para la familia, escuela o terapeutas):",
    height=75,
)

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
confirmar_envio = usar_ia and st.checkbox(
    "Revisé que los datos libres, la grilla y los adjuntos estén desidentificados y autorizo enviarlos a Gemini.",
    key=f"confirmar_envio_gemini_{st.session_state.get('envios_gemini', 0)}",
)
boton_generar = st.button("Generar borrador", type="primary", width="stretch")

# =====================================================================
# 9. EJECUCIÓN DEL MOTOR HÍBRIDO Y REVISIÓN PERSISTENTE
# =====================================================================
if boton_generar:
    hay_datos_caso = any(
        [
            pruebas_usadas,
            not df_procesado.empty,
            texto_puntajes_libre.strip(),
            archivos_adjuntos,
            quien_deriva.strip(),
            antecedentes.strip(),
            obs_extra.strip(),
            obs_vinculo, obs_predisp, obs_consignas, obs_desatencion, obs_motora,
            obs_impulsividad, obs_frustracion, obs_ansiedad, obs_ritmo, obs_lenguaje,
            alfabetizado,
            obs_wechsler.strip(),
            obs_memoria.strip(),
            obs_atencion_fe.strip(),
            obs_viso_leng.strip(),
            obs_lectoescritura.strip(),
            obs_matematica.strip(),
            cuestionarios_txt.strip(),
            impresion_destacar.strip(),
        ]
    )

    if not hay_datos_caso:
        st.warning("Cargá pruebas, puntajes, adjuntos u observaciones antes de generar.")
    elif fecha_nac and fecha_eval and fecha_eval < fecha_nac:
        st.error("Corregí las fechas antes de generar el borrador.")
    elif usar_ia and not api_key:
        st.error("Ingresá la clave de Gemini en el menú lateral.")
    elif usar_ia and not confirmar_envio:
        st.error("Revisá la desidentificación y confirmá el envío a Gemini.")
    elif usar_ia and guia_aprobada is None:
        st.error("Corregí la guía de redacción o desmarcá su envío.")
    elif usar_ia and sum(archivo.size for archivo in archivos_adjuntos) > motor_ia.MAX_INLINE_PDF_BYTES:
        st.error("Los adjuntos pueden sumar hasta 12 MB por solicitud.")
    else:
        with st.spinner("Preparando el borrador…"):
            try:
                fecha_nac_str = fecha_nac.strftime("%d/%m/%Y") if fecha_nac else ""
                fecha_eval_str = fecha_eval.strftime("%d/%m/%Y") if fecha_eval else ""

                tabla_z_markdown = grilla_markdown(df_procesado)

                detalle_terapeuticas = "\n".join(
                    [f"- {k}: {BANCO_SUGERENCIAS['terapeuticas'][k]}" for k in sug_terapeuticas_sel]
                )
                detalle_escolares = "\n".join(
                    [f"- {k}: {BANCO_SUGERENCIAS['escolares'][k]}" for k in sug_escolares_sel]
                )

                firma_profesional = (
                    f"{profesional_nombre} — {profesional_matricula}".strip(" —")
                    if profesional_nombre or profesional_matricula
                    else "[Firma y Sello del Profesional]"
                )

                datos_caso = {
                    "modelos_seleccionados": modelos_seleccionados,
                    "pruebas_usadas": pruebas_usadas,
                    "nombre": nombre,
                    "hc": hc,
                    "edad_texto": edad_texto,
                    "edad_para_ia": formatear_edad(*edad_calc) if edad_calc else "",
                    "fecha_nac": fecha_nac_str,
                    "fecha_eval": fecha_eval_str,
                    "escolaridad": escolaridad,
                    "nacionalidad": nacionalidad,
                    "preferencia": preferencia,
                    "medico": medico,
                    "firma_profesional": firma_profesional,
                    "acompanante": acompanante,
                    "quien_deriva": quien_deriva,
                    "antecedentes": antecedentes,
                    "conducta": {
                        "Contacto y vínculo": obs_vinculo,
                        "Predisposición": obs_predisp,
                        "Comprensión de consignas": obs_consignas,
                        "Atención observable": obs_desatencion,
                        "Actividad motora": obs_motora,
                        "Impulsividad": obs_impulsividad,
                        "Tolerancia a la frustración": obs_frustracion,
                        "Ansiedad frente al error": obs_ansiedad,
                        "Ritmo de trabajo y fatiga": obs_ritmo,
                        "Lenguaje expresivo": obs_lenguaje,
                        "Notas extra de conducta": obs_extra,
                    },
                    "tabla_z_markdown": tabla_z_markdown,
                    "texto_puntajes_libre": texto_puntajes_libre,
                    "observaciones_cualitativas": {
                        "Funcionamiento Intelectual (Wechsler)": obs_wechsler,
                        "Memoria y Aprendizaje": obs_memoria,
                        "Atención y Funciones Ejecutivas": obs_atencion_fe,
                        "Visomotor y Lenguaje": obs_viso_leng,
                        "Nivel de alfabetización": alfabetizado,
                        "Lectura, Escritura y Ortografía": obs_lectoescritura,
                        "Cálculo y Matemática": obs_matematica,
                        "Cuestionarios / Vineland / DIVA-5": cuestionarios_txt,
                    },
                    "impresion_destacar": impresion_destacar,
                    "frecuencia_y_control": frecuencia_y_control,
                    "detalle_terapeuticas": detalle_terapeuticas,
                    "detalle_escolares": detalle_escolares,
                    "recom_personalizadas": recom_personalizadas,
                }

                if usar_ia:
                    st.session_state["envios_gemini"] = st.session_state.get("envios_gemini", 0) + 1
                    archivos_payload = [
                        {
                            "name": f"Adjunto {indice}{PurePath(archivo.name).suffix.lower()}",
                            "bytes": archivo.getvalue(),
                        }
                        for indice, archivo in enumerate(archivos_adjuntos, start=1)
                    ]
                    texto_generado = motor_ia.generar_informe_clinico(
                        api_key=api_key,
                        modelo=modelo_gemini,
                        thinking_level=thinking_level,
                        datos_caso=datos_caso,
                        archivos=archivos_payload,
                        guia_estilo=guia_aprobada,
                    )
                else:
                    texto_generado = construir_borrador(datos_caso)

                st.session_state["informe_original"] = texto_generado
                st.session_state["informe_actual"] = texto_generado
                st.session_state["informe_version"] = st.session_state.get("informe_version", 0) + 1
                st.session_state["informe_meta"] = {
                    "nombre": nombre,
                    "fecha_eval": fecha_eval_str,
                    "profesional": firma_profesional,
                }

            except Exception:
                st.error("No se pudo generar el borrador. Revisá la configuración o volvé a intentar en modo local.")

if st.session_state.get("informe_original"):
    st.subheader("Borrador y revisión")
    st.caption("Verificá los resultados, su fuente y las conclusiones antes de entregar el informe.")
    version_inf = st.session_state.get("informe_version", 1)
    editor_key = f"editor_informe_{version_inf}"
    if editor_key not in st.session_state:
        st.session_state[editor_key] = st.session_state["informe_actual"]

    texto_vigente = st.session_state.get(editor_key, st.session_state["informe_actual"])
    st.session_state["informe_actual"] = texto_vigente

    tab_vista, tab_editar = st.tabs(
        ["👁️ Vista Previa Formateada", "✏️ Editar Informe antes de Descargar"]
    )
    with tab_vista:
        st.markdown(texto_vigente.replace("![", r"\!\["))
    with tab_editar:
        texto_editado = st.text_area(
            "Editá o ajustá el texto del informe (Markdown):",
            height=550,
            key=editor_key,
        )
        st.session_state["informe_actual"] = texto_editado
        if st.button("↩️ Restaurar versión original generada"):
            st.session_state["informe_actual"] = st.session_state["informe_original"]
            st.session_state["informe_version"] = version_inf + 1
            st.rerun()

    meta = st.session_state.get("informe_meta") or {}
    texto_para_descarga = st.session_state["informe_actual"]
    docx_bytes = generar_docx_bytes(
        texto_markdown=texto_para_descarga,
        datos_filiacion=meta,
        incluir_tabla_filiacion=False,
        incluir_tabla_z=False,
        firma_profesional=meta.get("profesional", ""),
    )
    nombre_base = sanitizar_nombre_archivo(meta.get("nombre", ""))

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            label="⬇️ Descargar en Word (.docx)",
            data=docx_bytes,
            file_name=f"{nombre_base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch",
            type="primary",
        )
    with col_dl2:
        st.download_button(
            label="⬇️ Descargar en Markdown (.md)",
            data=texto_para_descarga,
            file_name=f"{nombre_base}.md",
            mime="text/markdown",
            width="stretch",
        )
