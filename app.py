"""Interfaz Streamlit para la Plataforma Clínica de Informes Neuropsicológicos."""

from datetime import date, datetime
import hashlib
import json
import pandas as pd
import streamlit as st

from analisis_clinico import analizar_perfil_clinico
from catalogo_clinico import (
    BANCO_SUGERENCIAS,
    CATALOGO_SUBPRUEBAS,
    CONDUCTA_ACORDE_DEFAULTS,
    ESCALA_CI,
    ESCALA_ESCALAR,
    ESCALA_PERCENTIL_DIRECTO,
    ESCALA_PERCENTIL_INVERSO,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALA_V_SCALE,
    ESCALAS_CALCULADORA,
    ESCALAS_DISPONIBLES,
    MODELOS_GEMINI,
    MODELOS_INFORME,
    PERFILES_RECOMENDACIONES,
    PRESETS_BATERIAS,
)
from exportador_docx import generar_docx_bytes
from generador_local import generar_borrador_local
from importador_archivos import (
    exportar_borrador_json,
    importar_borrador_json,
    importar_ficha_carga_docx,
    importar_planilla_excel_o_csv,
    listar_hojas_planilla,
)
import motor_ia
from motor_ia import resolver_api_key
from psicometria import (
    calcular_edad_exacta,
    calcular_ravlt_metricas,
    calcular_stroop_golden,
    calcular_tmt_metricas,
    calcular_vineland_forma_b,
    calcular_z_y_rango,
    categoria_color_rango,
    formatear_edad,
    procesar_tabla_puntajes,
    sanitizar_nombre_archivo,
)

# =====================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTADO INICIAL
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
    ESCALA_V_SCALE: 15.0,
    ESCALA_T_DIRECTO: 50.0,
    ESCALA_T_INVERSO: 50.0,
    ESCALA_PERCENTIL_DIRECTO: 50.0,
    ESCALA_PERCENTIL_INVERSO: 50.0,
}


def _crear_df_base_vacio() -> pd.DataFrame:
    df_vacio = pd.DataFrame(columns=COLUMNAS_EDITOR)
    df_vacio["Puntaje"] = pd.to_numeric(df_vacio["Puntaje"], errors="coerce").astype("float64")
    return df_vacio


def _parsear_fecha_segura(val) -> date | None:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    txt = str(val or "").strip()
    if not txt:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def _normalizar_preferencia(val: str) -> str:
    low = (val or "").strip().lower()
    if "diestr" in low:
        return "Diestra"
    if "zurd" in low:
        return "Zurda"
    if "ambid" in low or "defin" in low:
        return "Ambidiestra / En definición"
    return ""


def _normalizar_alfabetizado(val: str) -> str:
    low = (val or "").strip().lower()
    if low in ("si", "sí"):
        return "Sí"
    if low == "no":
        return "No"
    if "proceso" in low:
        return "En proceso"
    return ""


def _inicializar_estado() -> None:
    defaults = {
        "modelos_sel": [],
        "pruebas_sel": [],
        "nombre_input": "",
        "hc_input": "",
        "fecha_nac_input": None,
        "fecha_eval_input": None,
        "edad_texto_input": "",
        "escolaridad_input": "",
        "preferencia_input": "",
        "nacionalidad_input": "",
        "acompanante_input": "",
        "medico_input": "",
        "profesional_nombre_input": "",
        "profesional_matricula_input": "",
        "membrete_input": "",
        "quien_deriva_input": "",
        "antecedentes_input": "",
        "obs_vinculo": "",
        "obs_predisp": "",
        "obs_consignas": "",
        "obs_desatencion": "",
        "obs_motora": "",
        "obs_impulsividad": "",
        "obs_frustracion": "",
        "obs_ansiedad": "",
        "obs_ritmo": "",
        "obs_lenguaje": "",
        "obs_extra_input": "",
        "texto_puntajes_libre_input": "",
        "obs_wechsler_input": "",
        "obs_memoria_input": "",
        "obs_atencion_fe_input": "",
        "obs_viso_leng_input": "",
        "alfabetizado_input": "",
        "obs_lectoescritura_input": "",
        "obs_matematica_input": "",
        "cuestionarios_txt_input": "",
        "diva_ad_inat": 0,
        "diva_ad_hi": 0,
        "diva_inf_inat": 0,
        "diva_inf_hi": 0,
        "diva_inicio_12": False,
        "diva_ambitos": 0,
        "diva_otros_input": "",
        "impresion_destacar_input": "",
        "frecuencia_control_input": "",
        "sug_terapeuticas_sel": [],
        "sug_escolares_sel": [],
        "recom_personalizadas_input": "",
        "pruebas_previas": [],
        "editor_version": 0,
        "cache_subpruebas": {},
        "filas_personalizadas": [],
        "df_base_puntajes": _crear_df_base_vacio(),
        "ultimo_df_editado": _crear_df_base_vacio(),
        "ultimo_resumen_importacion": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _calcular_huella_caso(payload: dict) -> str:
    """Genera una huella determinista del caso actual para invalidar descargas obsoletas."""
    serializado = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()[:16]


def _aplicar_filas_importadas(filas_importadas: list[dict]) -> None:
    if not filas_importadas:
        return
    personalizadas_existentes = {
        r["Dominio / Prueba / Subtest"]: i
        for i, r in enumerate(st.session_state["filas_personalizadas"])
    }
    for fila in filas_importadas:
        sub = str(fila.get("Dominio / Prueba / Subtest") or "").strip()
        if not sub:
            continue
        punt = fila.get("Puntaje")
        esc = str(fila.get("Tipo de Escala") or ESCALAS_DISPONIBLES[0])
        obs = str(fila.get("Observación") or "").strip()
        if sub in SUBPRUEBAS_CATALOGO_SET:
            st.session_state["cache_subpruebas"][sub] = (punt, esc, obs)
        else:
            registro = {
                "Dominio / Prueba / Subtest": sub,
                "Puntaje": punt,
                "Tipo de Escala": esc,
                "Observación": obs,
            }
            if sub in personalizadas_existentes:
                st.session_state["filas_personalizadas"][personalizadas_existentes[sub]] = registro
            else:
                personalizadas_existentes[sub] = len(st.session_state["filas_personalizadas"])
                st.session_state["filas_personalizadas"].append(registro)

    # Forzar reconstrucción de grilla en la Sección 4
    st.session_state["pruebas_previas"] = None


def _procesar_pending_apply() -> None:
    pending = st.session_state.pop("pending_apply", None)
    if not pending:
        return

    imported_rows = pending.pop("imported_rows", None)
    for k, v in pending.items():
        st.session_state[k] = v

    if imported_rows:
        _aplicar_filas_importadas(imported_rows)

    # Si llegaron ambas fechas por importación y no hay edad explícita, recalcular edad
    f_nac = st.session_state.get("fecha_nac_input")
    f_eval = st.session_state.get("fecha_eval_input")
    if f_nac is not None and f_eval is not None:
        edad_calc = calcular_edad_exacta(f_nac, f_eval)
        if edad_calc is not None:
            st.session_state["edad_texto_input"] = formatear_edad(*edad_calc)
            st.session_state["prev_fechas_edad"] = (f_nac, f_eval)


_inicializar_estado()
_procesar_pending_apply()

# =====================================================================
# 2. PANEL LATERAL: CONFIGURACIÓN, CALCULADORA Z Y BORRADOR JSON
# =====================================================================
st.title("🧠 Generador Profesional de Informes Clínicos")
st.caption("Evaluación Neuropsicológica, Desempeño Cognitivo y Psicopedagógica")

api_key = resolver_api_key(st.secrets)
with st.sidebar:
    st.header("⚙️ Configuración")
    if api_key:
        st.caption("🔑 API Key cargada desde secretos o entorno.")
    else:
        api_key = st.text_input("Ingresá tu Gemini API Key", type="password")

    modelo_gemini = st.selectbox(
        "Modelo de IA",
        options=list(MODELOS_GEMINI.keys()),
        format_func=lambda m: MODELOS_GEMINI[m]["label"],
        index=0,
    )

    niveles_disp = MODELOS_GEMINI[modelo_gemini]["thinking_levels"]
    default_thinking = MODELOS_GEMINI[modelo_gemini]["default_thinking"]
    if st.session_state.get("prev_modelo_ia") != modelo_gemini:
        st.session_state["thinking_level_sel"] = default_thinking
        st.session_state["prev_modelo_ia"] = modelo_gemini
    elif st.session_state.get("thinking_level_sel") not in niveles_disp:
        st.session_state["thinking_level_sel"] = default_thinking

    thinking_level = st.selectbox(
        "Nivel de razonamiento",
        options=niveles_disp,
        key="thinking_level_sel",
        help="Controla la profundidad de análisis clínico en Gemini 4.",
    )
    anonimizar_ia = st.checkbox(
        "Seudonimizar identidad antes de enviar a Gemini",
        value=True,
        key="anonimizar_ia_chk",
        help="Reemplaza nombre, HC/DNI, fecha de nacimiento, solicitante, acompañante y firma antes de enviar texto a la API.",
    )
    st.caption(
        "🔒 Privacidad clínica: podés generar el borrador y el Word 100% offline sin enviar datos. "
        "Si elegís Gemini 4 (opcional), la seudonimización oculta los datos identificatorios del texto y "
        "`store=False` desactiva el historial de Interactions API; no obstante, Google no certifica la API estándar "
        "para práctica clínica asistencial y los PDFs/imágenes adjuntos se envían con su contenido visual intacto."
    )

    st.divider()
    st.subheader("🧮 Calculadora Rápida a Z")
    esc_calc = st.selectbox("Escala", ESCALAS_CALCULADORA, key="calc_escala")

    if st.session_state.get("prev_calc_escala") != esc_calc:
        st.session_state["calc_valor"] = DEFAULTS_CALCULADORA.get(esc_calc, 10.0)
        st.session_state["prev_calc_escala"] = esc_calc
    elif "calc_valor" not in st.session_state:
        st.session_state["calc_valor"] = DEFAULTS_CALCULADORA.get(esc_calc, 10.0)

    if esc_calc in (ESCALA_PERCENTIL_DIRECTO, ESCALA_PERCENTIL_INVERSO):
        val_calc = st.number_input(
            "Puntaje (Percentil 1-99)",
            min_value=1.0,
            max_value=99.0,
            step=1.0,
            key="calc_valor",
        )
    else:
        val_calc = st.number_input("Puntaje", step=1.0, key="calc_valor")

    es_hit_rt_calc = False
    if esc_calc in (ESCALA_T_INVERSO, ESCALA_PERCENTIL_INVERSO):
        es_hit_rt_calc = st.checkbox(
            "Es Tiempo de Reacción (Hit RT)",
            value=False,
            help="Evalúa si un puntaje muy bajo (< T 40 / Pc ≤ 15) indica estilo rápido/impulsivo.",
        )

    z_res, rango_res = calcular_z_y_rango(
        val_calc,
        esc_calc,
        nombre_subtest="Hit RT" if es_hit_rt_calc else "",
    )
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

    st.divider()
    st.subheader("💾 Borrador del Caso (.json)")
    borrador_payload = {
        "modelos_sel": st.session_state["modelos_sel"],
        "pruebas_sel": st.session_state["pruebas_sel"],
        "nombre_input": st.session_state["nombre_input"],
        "hc_input": st.session_state["hc_input"],
        "fecha_nac": st.session_state["fecha_nac_input"].strftime("%d/%m/%Y")
        if st.session_state["fecha_nac_input"]
        else "",
        "fecha_eval": st.session_state["fecha_eval_input"].strftime("%d/%m/%Y")
        if st.session_state["fecha_eval_input"]
        else "",
        "edad_texto_input": st.session_state["edad_texto_input"],
        "escolaridad_input": st.session_state["escolaridad_input"],
        "preferencia_input": st.session_state["preferencia_input"],
        "nacionalidad_input": st.session_state["nacionalidad_input"],
        "acompanante_input": st.session_state["acompanante_input"],
        "medico_input": st.session_state["medico_input"],
        "profesional_nombre_input": st.session_state["profesional_nombre_input"],
        "profesional_matricula_input": st.session_state["profesional_matricula_input"],
        "membrete_input": st.session_state["membrete_input"],
        "quien_deriva_input": st.session_state["quien_deriva_input"],
        "antecedentes_input": st.session_state["antecedentes_input"],
        "obs_vinculo": st.session_state["obs_vinculo"],
        "obs_predisp": st.session_state["obs_predisp"],
        "obs_consignas": st.session_state["obs_consignas"],
        "obs_desatencion": st.session_state["obs_desatencion"],
        "obs_motora": st.session_state["obs_motora"],
        "obs_impulsividad": st.session_state["obs_impulsividad"],
        "obs_frustracion": st.session_state["obs_frustracion"],
        "obs_ansiedad": st.session_state["obs_ansiedad"],
        "obs_ritmo": st.session_state["obs_ritmo"],
        "obs_lenguaje": st.session_state["obs_lenguaje"],
        "obs_extra_input": st.session_state["obs_extra_input"],
        "texto_puntajes_libre_input": st.session_state["texto_puntajes_libre_input"],
        "obs_wechsler_input": st.session_state["obs_wechsler_input"],
        "obs_memoria_input": st.session_state["obs_memoria_input"],
        "obs_atencion_fe_input": st.session_state["obs_atencion_fe_input"],
        "obs_viso_leng_input": st.session_state["obs_viso_leng_input"],
        "alfabetizado_input": st.session_state["alfabetizado_input"],
        "obs_lectoescritura_input": st.session_state["obs_lectoescritura_input"],
        "obs_matematica_input": st.session_state["obs_matematica_input"],
        "cuestionarios_txt_input": st.session_state["cuestionarios_txt_input"],
        "impresion_destacar_input": st.session_state["impresion_destacar_input"],
        "frecuencia_control_input": st.session_state["frecuencia_control_input"],
        "sug_terapeuticas_sel": st.session_state["sug_terapeuticas_sel"],
        "sug_escolares_sel": st.session_state["sug_escolares_sel"],
        "recom_personalizadas_input": st.session_state["recom_personalizadas_input"],
        "filas_puntajes": st.session_state["ultimo_df_editado"].fillna("").to_dict(orient="records")
        if not st.session_state["ultimo_df_editado"].empty
        else [],
    }
    st.download_button(
        label="⬇️ Guardar borrador (.json)",
        data=exportar_borrador_json(borrador_payload),
        file_name=f"{sanitizar_nombre_archivo(st.session_state['nombre_input'], 'Borrador')}.json",
        mime="application/json",
        width="stretch",
    )
    json_subido = st.file_uploader("Cargar borrador (.json)", type=["json"], key="uploader_borrador_json")
    if json_subido is not None and st.button("📂 Aplicar borrador cargado", width="stretch"):
        try:
            data_b = importar_borrador_json(json_subido.getvalue())
            nuevo_apply: dict = {}
            for campo in (
                "modelos_sel",
                "pruebas_sel",
                "nombre_input",
                "hc_input",
                "edad_texto_input",
                "escolaridad_input",
                "preferencia_input",
                "nacionalidad_input",
                "acompanante_input",
                "medico_input",
                "profesional_nombre_input",
                "profesional_matricula_input",
                "membrete_input",
                "quien_deriva_input",
                "antecedentes_input",
                "obs_vinculo",
                "obs_predisp",
                "obs_consignas",
                "obs_desatencion",
                "obs_motora",
                "obs_impulsividad",
                "obs_frustracion",
                "obs_ansiedad",
                "obs_ritmo",
                "obs_lenguaje",
                "obs_extra_input",
                "texto_puntajes_libre_input",
                "obs_wechsler_input",
                "obs_memoria_input",
                "obs_atencion_fe_input",
                "obs_viso_leng_input",
                "alfabetizado_input",
                "obs_lectoescritura_input",
                "obs_matematica_input",
                "cuestionarios_txt_input",
                "impresion_destacar_input",
                "frecuencia_control_input",
                "sug_terapeuticas_sel",
                "sug_escolares_sel",
                "recom_personalizadas_input",
            ):
                if campo in data_b:
                    nuevo_apply[campo] = data_b[campo]
            if data_b.get("fecha_nac"):
                nuevo_apply["fecha_nac_input"] = _parsear_fecha_segura(data_b["fecha_nac"])
            if data_b.get("fecha_eval"):
                nuevo_apply["fecha_eval_input"] = _parsear_fecha_segura(data_b["fecha_eval"])
            filas_b = data_b.get("filas_puntajes") or []
            if filas_b:
                filas_limpias = []
                for f in filas_b:
                    p_raw = f.get("Puntaje")
                    p_val = float(p_raw) if p_raw not in ("", None) else None
                    filas_limpias.append(
                        {
                            "Dominio / Prueba / Subtest": f.get("Dominio / Prueba / Subtest", ""),
                            "Puntaje": p_val,
                            "Tipo de Escala": f.get("Tipo de Escala", ESCALAS_DISPONIBLES[0]),
                            "Observación": f.get("Observación", ""),
                        }
                    )
                nuevo_apply["imported_rows"] = filas_limpias
            st.session_state["pending_apply"] = nuevo_apply
            st.session_state["flash_import_msg"] = ("success", "Borrador JSON restaurado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo cargar el borrador JSON: {exc}")

# Mostrar mensaje flash tras rerun de importación
if "flash_import_msg" in st.session_state:
    tipo_msg, txt_msg = st.session_state.pop("flash_import_msg")
    if tipo_msg == "success":
        st.success(txt_msg)
    elif tipo_msg == "warning":
        st.warning(txt_msg)
    else:
        st.info(txt_msg)

# =====================================================================
# 3. SECCIÓN 0: CARGA RÁPIDA E IMPORTACIÓN DE ADJUNTOS
# =====================================================================
hay_algo_cargado = bool(st.session_state["pruebas_sel"] or st.session_state["nombre_input"])
with st.expander("⚡ Carga Rápida desde Planilla Excel, Ficha Word, PDFs o Capturas", expanded=not hay_algo_cargado):
    st.caption(
        "Adjuntá acá todos los archivos del caso (Planilla de puntuaciones `.xlsx`/`.csv`, Ficha de carga `.docx`, "
        "reportes PDF de CPT-II / Nesplora / Vineland o fotos de protocolos `.png`/`.jpg`). "
        "Podés prellenar el formulario con 1 clic y además se envían al generar el informe."
    )
    archivos_adjuntos = st.file_uploader(
        "📎 Subir archivos clínicos del paciente",
        type=["pdf", "png", "jpg", "jpeg", "webp", "xlsx", "csv", "docx", "txt"],
        accept_multiple_files=True,
        key="archivos_clinicos_uploader",
    )

    hojas_seleccionadas: dict[str, str] = {}
    if archivos_adjuntos:
        for idx_arch, arch in enumerate(archivos_adjuntos):
            if arch.name.lower().endswith(".xlsx"):
                try:
                    hojas_info = listar_hojas_planilla(arch.getvalue())
                except Exception:
                    hojas_info = []
                hojas_con_datos = [h for h in hojas_info if h["tiene_datos"]]
                if len(hojas_con_datos) > 1:
                    st.warning(
                        f"El archivo `{arch.name}` tiene {len(hojas_con_datos)} hojas con evaluaciones. "
                        "Elegí la hoja correspondiente al paciente antes de importar para no mezclar casos."
                    )
                    opciones_hojas = [h["hoja"] for h in hojas_con_datos]
                    etiquetas_hojas = {
                        h["hoja"]: (
                            f"{h['hoja']} — Paciente: {h['paciente'] or 'Sin nombre'} | "
                            f"Eval: {h['fecha_eval'] or 'Sin fecha'} | {h['filas_con_valor']} filas"
                        )
                        for h in hojas_con_datos
                    }
                    hojas_seleccionadas[arch.name] = st.selectbox(
                        f"Hoja a importar de `{arch.name}`",
                        options=opciones_hojas,
                        format_func=lambda h_nom, mp=etiquetas_hojas: mp.get(h_nom, h_nom),
                        key=f"sel_hoja_xlsx_{idx_arch}_{arch.name}",
                    )
                elif len(hojas_con_datos) == 1:
                    hojas_seleccionadas[arch.name] = hojas_con_datos[0]["hoja"]

    col_imp1, col_imp2 = st.columns(2)
    with col_imp1:
        btn_importar_local = st.button(
            "📥 Importar Planilla Excel/CSV o Ficha Word (sin IA)",
            width="stretch",
            disabled=not archivos_adjuntos,
        )
    with col_imp2:
        btn_extraer_ia = st.button(
            "✨ Extraer datos y puntajes de adjuntos con IA",
            width="stretch",
            disabled=not archivos_adjuntos,
        )

    if btn_importar_local and archivos_adjuntos:
        apply_data: dict = {"imported_rows": []}
        pruebas_nuevas = list(st.session_state["pruebas_sel"])
        notas_acum = []
        resumenes_imp = []
        archivos_leidos = 0

        for arch in archivos_adjuntos:
            nombre_a = arch.name.lower()
            raw_a = arch.getvalue()
            if nombre_a.endswith((".xlsx", ".csv")):
                archivos_leidos += 1
                res_x = importar_planilla_excel_o_csv(
                    raw_a,
                    arch.name,
                    hoja_seleccionada=hojas_seleccionadas.get(arch.name),
                )
                if res_x.get("requiere_seleccion_hoja"):
                    st.warning(
                        f"El archivo `{arch.name}` requiere selección explícita de hoja antes de importar."
                    )
                    continue
                fil = res_x["filiacion"]
                if fil.get("nombre"):
                    apply_data["nombre_input"] = fil["nombre"]
                if fil.get("hc"):
                    apply_data["hc_input"] = fil["hc"]
                if fil.get("escolaridad"):
                    apply_data["escolaridad_input"] = fil["escolaridad"]
                if fil.get("edad_texto"):
                    apply_data["edad_texto_input"] = fil["edad_texto"]
                if fil.get("fecha_nac"):
                    fn = _parsear_fecha_segura(fil["fecha_nac"])
                    if fn:
                        apply_data["fecha_nac_input"] = fn
                if fil.get("fecha_eval"):
                    fe = _parsear_fecha_segura(fil["fecha_eval"])
                    if fe:
                        apply_data["fecha_eval_input"] = fe
                for b in res_x["pruebas_detectadas"]:
                    if b not in pruebas_nuevas:
                        pruebas_nuevas.append(b)
                apply_data["imported_rows"].extend(res_x["filas_puntajes"])
                if res_x["texto_extra"]:
                    notas_acum.append(res_x["texto_extra"])
                if res_x.get("resumen_importacion"):
                    resumenes_imp.append({"archivo": arch.name, **res_x["resumen_importacion"]})
            elif nombre_a.endswith(".docx"):
                archivos_leidos += 1
                res_d = importar_ficha_carga_docx(raw_a)
                fil = res_d["filiacion"]
                if fil.get("nombre"):
                    apply_data["nombre_input"] = fil["nombre"]
                if fil.get("hc"):
                    apply_data["hc_input"] = fil["hc"]
                if fil.get("escolaridad"):
                    apply_data["escolaridad_input"] = fil["escolaridad"]
                if fil.get("nacionalidad"):
                    apply_data["nacionalidad_input"] = fil["nacionalidad"]
                if fil.get("preferencia"):
                    apply_data["preferencia_input"] = _normalizar_preferencia(fil["preferencia"])
                if fil.get("medico"):
                    apply_data["medico_input"] = fil["medico"]
                if fil.get("acompanante"):
                    apply_data["acompanante_input"] = fil["acompanante"]
                if fil.get("fecha_nac"):
                    fn = _parsear_fecha_segura(fil["fecha_nac"])
                    if fn:
                        apply_data["fecha_nac_input"] = fn
                if fil.get("fecha_eval"):
                    fe = _parsear_fecha_segura(fil["fecha_eval"])
                    if fe:
                        apply_data["fecha_eval_input"] = fe
                if res_d["motivo"].get("quien_deriva"):
                    apply_data["quien_deriva_input"] = res_d["motivo"]["quien_deriva"]
                if res_d["motivo"].get("antecedentes"):
                    apply_data["antecedentes_input"] = res_d["motivo"]["antecedentes"]
                if res_d["texto_extra"]:
                    notas_acum.append(res_d["texto_extra"])

        if archivos_leidos == 0:
            st.warning("Para importación directa sin IA adjuntá al menos un `.xlsx`, `.csv` o `.docx`. Para PDFs o fotos usá 'Extraer con IA'.")
        else:
            apply_data["pruebas_sel"] = pruebas_nuevas
            apply_data["ultimo_resumen_importacion"] = resumenes_imp
            if notas_acum:
                prev_libre = st.session_state["texto_puntajes_libre_input"].strip()
                nuevo_txt = "\n".join(notas_acum)
                apply_data["texto_puntajes_libre_input"] = f"{prev_libre}\n{nuevo_txt}".strip() if prev_libre else nuevo_txt
            st.session_state["pending_apply"] = apply_data
            st.session_state["flash_import_msg"] = (
                "success",
                f"Importación local lista: {len(apply_data['imported_rows'])} puntajes y {len(pruebas_nuevas)} baterías cargadas.",
            )
            st.rerun()

    resumenes_recientes = st.session_state.get("ultimo_resumen_importacion") or []
    if resumenes_recientes:
        with st.expander("📋 Auditoría de la última importación de planilla", expanded=False):
            for rep in resumenes_recientes:
                st.markdown(
                    f"- **{rep.get('archivo', '')}** (hoja `{rep.get('hoja') or '-'}`): "
                    f"leídas **{rep.get('filas_leidas', 0)}**, "
                    f"importadas **{rep.get('filas_importadas', 0)}**, "
                    f"descartadas **{rep.get('filas_descartadas', 0)}**."
                )
                for motivo in rep.get("motivos_descarte") or []:
                    st.caption(f"  ↳ Descarte: {motivo}")

    if btn_extraer_ia and archivos_adjuntos:
        if not api_key:
            st.error("Ingresá tu API Key de Gemini en el panel lateral para usar la extracción con IA.")
        else:
            with st.spinner("Leyendo adjuntos (PDFs / imágenes / planillas) y extrayendo datos estructurados..."):
                try:
                    payload_files = [{"name": a.name, "bytes": a.getvalue()} for a in archivos_adjuntos]
                    ext = motor_ia.extraer_datos_de_adjuntos(
                        api_key=api_key,
                        archivos=payload_files,
                        modelo=modelo_gemini,
                        store=False,
                    )
                    apply_ia: dict = {}
                    f = ext.filiacion
                    if f.nombre:
                        apply_ia["nombre_input"] = f.nombre
                    if f.hc:
                        apply_ia["hc_input"] = f.hc
                    if f.edad_texto:
                        apply_ia["edad_texto_input"] = f.edad_texto
                    if f.escolaridad:
                        apply_ia["escolaridad_input"] = f.escolaridad
                    if f.nacionalidad:
                        apply_ia["nacionalidad_input"] = f.nacionalidad
                    if f.preferencia:
                        apply_ia["preferencia_input"] = _normalizar_preferencia(f.preferencia)
                    if f.medico:
                        apply_ia["medico_input"] = f.medico
                    if f.acompanante:
                        apply_ia["acompanante_input"] = f.acompanante
                    if f.fecha_nac:
                        fn = _parsear_fecha_segura(f.fecha_nac)
                        if fn:
                            apply_ia["fecha_nac_input"] = fn
                    if f.fecha_eval:
                        fe = _parsear_fecha_segura(f.fecha_eval)
                        if fe:
                            apply_ia["fecha_eval_input"] = fe

                    modelos_validos = [m for m in ext.modelos_sugeridos if m in MODELOS_INFORME]
                    if modelos_validos:
                        apply_ia["modelos_sel"] = modelos_validos
                    pruebas_validas = list(st.session_state["pruebas_sel"])
                    for p in ext.pruebas_detectadas:
                        if p in CATALOGO_SUBPRUEBAS and p not in pruebas_validas:
                            pruebas_validas.append(p)
                    if pruebas_validas:
                        apply_ia["pruebas_sel"] = pruebas_validas

                    n = ext.notas
                    for k_n, k_ss in (
                        ("quien_deriva", "quien_deriva_input"),
                        ("antecedentes", "antecedentes_input"),
                        ("obs_wechsler", "obs_wechsler_input"),
                        ("obs_memoria", "obs_memoria_input"),
                        ("obs_atencion_fe", "obs_atencion_fe_input"),
                        ("obs_viso_leng", "obs_viso_leng_input"),
                        ("obs_lectoescritura", "obs_lectoescritura_input"),
                        ("obs_matematica", "obs_matematica_input"),
                        ("cuestionarios_txt", "cuestionarios_txt_input"),
                    ):
                        val_n = getattr(n, k_n, "")
                        if val_n:
                            apply_ia[k_ss] = val_n

                    apply_ia["imported_rows"] = [
                        {
                            "Dominio / Prueba / Subtest": item.subtest,
                            "Puntaje": item.puntaje,
                            "Tipo de Escala": item.escala
                            if item.escala in ESCALAS_DISPONIBLES
                            else ESCALAS_DISPONIBLES[0],
                            "Observación": item.observacion,
                        }
                        for item in ext.puntajes
                    ]

                    msg = f"Extracción completada: {len(apply_ia['imported_rows'])} puntajes cargados para revisión."
                    if ext.advertencias_extraccion:
                        msg += " Revisá advertencias: " + " | ".join(ext.advertencias_extraccion)
                        st.session_state["flash_import_msg"] = ("warning", msg)
                    else:
                        st.session_state["flash_import_msg"] = ("success", msg)

                    st.session_state["pending_apply"] = apply_ia
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error durante la extracción con IA: {exc}")

# =====================================================================
# 4. SECCIÓN 1: MODELO DE INFORME, PRESETS Y BATERÍAS ADMINISTRADAS
# =====================================================================
st.header("1. Tipo de Informe y Baterías Administradas")

st.caption("Presets de carga rápida (opcional):")
cols_preset = st.columns(len(PRESETS_BATERIAS))
for idx_p, (nombre_preset, cfg_preset) in enumerate(PRESETS_BATERIAS.items()):
    if cols_preset[idx_p].button(f"⚡ {nombre_preset}", width="stretch", key=f"preset_btn_{idx_p}"):
        st.session_state["pending_apply"] = {
            "modelos_sel": list(cfg_preset["modelos"]),
            "pruebas_sel": list(cfg_preset["pruebas"]),
        }
        st.rerun()

col_mod1, col_mod2 = st.columns(2)
with col_mod1:
    modelos_seleccionados = st.multiselect(
        "Seleccioná el modelo de informe (podés combinar más de uno):",
        MODELOS_INFORME,
        key="modelos_sel",
        placeholder="Elegí el modelo de informe...",
    )

with col_mod2:
    pruebas_usadas = st.multiselect(
        "Seleccioná las pruebas y test administrados (cargará sus subpruebas en el Paso 4):",
        list(CATALOGO_SUBPRUEBAS.keys()),
        key="pruebas_sel",
        placeholder="Elegí las pruebas administradas...",
    )

st.divider()

# =====================================================================
# 5. SECCIÓN 2: DATOS DE FILIACIÓN Y PROFESIONAL
# =====================================================================
st.header("2. Datos del Paciente y del Profesional")

c1, c2, c3, c4 = st.columns(4)
with c1:
    nombre = st.text_input("Apellido y Nombre del Paciente", key="nombre_input")
    hc = st.text_input("DNI / HC N°", key="hc_input")
    fecha_nac = st.date_input(
        "Fecha de nacimiento",
        format="DD/MM/YYYY",
        min_value=date(1920, 1, 1),
        max_value=date(2035, 12, 31),
        key="fecha_nac_input",
    )
with c2:
    fecha_eval = st.date_input(
        "Fecha de evaluación",
        format="DD/MM/YYYY",
        min_value=date(1920, 1, 1),
        max_value=date(2035, 12, 31),
        key="fecha_eval_input",
    )
    edad_calc_tupla: tuple[int, int] | None = None
    if fecha_nac is not None and fecha_eval is not None:
        edad_calc_tupla = calcular_edad_exacta(fecha_nac, fecha_eval)
        if edad_calc_tupla is None:
            st.warning("La fecha de evaluación es anterior a la fecha de nacimiento.")
        else:
            fechas_actuales = (fecha_nac, fecha_eval)
            if st.session_state.get("prev_fechas_edad") != fechas_actuales:
                st.session_state["edad_texto_input"] = formatear_edad(*edad_calc_tupla)
                st.session_state["prev_fechas_edad"] = fechas_actuales

    edad_texto = st.text_input(
        "Edad (años y meses)",
        key="edad_texto_input",
        placeholder="Se calcula al ingresar ambas fechas o escribí manual",
    )
    escolaridad = st.text_input("Escolaridad (Nivel y Grado/Año)", key="escolaridad_input")
with c3:
    preferencia = st.selectbox(
        "Preferencia manual",
        ["", "Diestra", "Zurda", "Ambidiestra / En definición"],
        key="preferencia_input",
    )
    nacionalidad = st.text_input("Nacionalidad", key="nacionalidad_input")
    acompanante = st.text_input("Acompañante", key="acompanante_input")
with c4:
    medico = st.text_input("Médico / Institución Solicitante", key="medico_input")
    profesional_nombre = st.text_input("Profesional Evaluador/a (para la firma)", key="profesional_nombre_input")
    profesional_matricula = st.text_input("Título y Matrícula Profesional", key="profesional_matricula_input")

membrete_institucional = st.text_input(
    "Institución / Servicio (membrete opcional para el Word)",
    key="membrete_input",
    placeholder="Opcional — ej. Servicio de Neuropsicología Clínica",
)

st.divider()

# =====================================================================
# 6. SECCIÓN 3: MOTIVO DE CONSULTA Y OBSERVACIÓN DE CONDUCTA
# =====================================================================
st.header("3. Motivo de Consulta y Observación de la Conducta")
col_m1, col_m2 = st.columns(2)
with col_m1:
    quien_deriva = st.text_area(
        "¿Quién deriva y qué preocupa? (Motivo de consulta)",
        height=85,
        key="quien_deriva_input",
    )
with col_m2:
    antecedentes = st.text_area(
        "Diagnósticos, tratamientos actuales y evaluaciones previas",
        height=85,
        key="antecedentes_input",
    )

col_sub_c1, col_sub_c2 = st.columns([3, 1])
with col_sub_c1:
    st.subheader("Indicadores Conductuales Observados")
with col_sub_c2:
    if st.button("✅ Conducta acorde (prellenar todo adecuado)", width="stretch"):
        st.session_state["pending_apply"] = dict(CONDUCTA_ACORDE_DEFAULTS)
        st.rerun()

cb1, cb2, cb3 = st.columns(3)
with cb1:
    obs_vinculo = st.selectbox(
        "Contacto y vínculo",
        ["", "Adecuado", "Reticente al inicio, luego adecuado", "Otro"],
        key="obs_vinculo",
    )
    obs_predisp = st.selectbox(
        "Predisposición",
        ["", "Buena", "Variable", "Intenta dirigir la situación"],
        key="obs_predisp",
    )
    obs_consignas = st.selectbox(
        "Comprensión de consignas",
        ["", "Comprende adecuadamente", "Requiere repetición y segmentación"],
        key="obs_consignas",
    )
    obs_desatencion = st.selectbox(
        "Atención durante la evaluación",
        ["", "Sostiene el foco adecuadamente", "Tiempos atencionales breves", "Se dispersa frente a estímulos"],
        key="obs_desatencion",
    )
with cb2:
    obs_motora = st.selectbox(
        "Actividad motora",
        ["", "Adecuada (Estable en su silla)", "Movedizo en la silla", "Le cuesta trabajar en silencio"],
        key="obs_motora",
    )
    obs_impulsividad = st.selectbox(
        "Estilo de respuesta / Impulsividad",
        ["", "Reflexivo y organizado", "Responde apresurado, errores por descuido"],
        key="obs_impulsividad",
    )
    obs_frustracion = st.selectbox(
        "Tolerancia a la frustración",
        ["", "Adecuada", "Baja, con conductas de evitación", "Enojo o fastidio ante la dificultad"],
        key="obs_frustracion",
    )
with cb3:
    obs_ansiedad = st.selectbox(
        "Ansiedad frente al error",
        ["", "No se observa", "Sí, demora respuestas en pruebas con tiempo"],
        key="obs_ansiedad",
    )
    obs_ritmo = st.selectbox(
        "Ritmo de trabajo y fatiga",
        ["", "Adecuado y sostenido", "Lento", "Se fatiga rápido hacia el final"],
        key="obs_ritmo",
    )
    obs_lenguaje = st.selectbox(
        "Lenguaje expresivo espontáneo",
        ["", "Adecuado", "Dificultades fonológicas / articulatorias", "Escaso"],
        key="obs_lenguaje",
    )

obs_extra = st.text_area(
    "Observaciones cualitativas adicionales de la conducta",
    height=65,
    key="obs_extra_input",
)

st.divider()

# =====================================================================
# 7. SECCIÓN 4: GRILLA SINCRONIZADA, MINI-ASISTENTES Y ALERTAS CLÍNICAS
# =====================================================================
st.header("4. Puntuaciones Cuantitativas y Análisis Automático")
st.caption(
    "Las subpruebas y sus escalas se cargan automáticamente según lo que elegiste en el Paso 1. "
    "Solo completá 'Puntaje Obtenido' o 'Notas' (las filas vacías se ignoran automáticamente)."
)

if list(pruebas_usadas) != st.session_state["pruebas_previas"]:
    df_prev = st.session_state["ultimo_df_editado"]
    nuevas_personalizadas = list(st.session_state["filas_personalizadas"])
    if st.session_state["pruebas_previas"] is not None and df_prev is not None and not df_prev.empty:
        nuevas_personalizadas = []
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

# Mini-asistentes contextuales según baterías seleccionadas
datos_auxiliares: dict = {}
pruebas_set = set(pruebas_usadas)

if "Stroop" in pruebas_set:
    with st.expander("🧮 Asistente Stroop (Cálculo de PC' e Interferencia Golden)", expanded=False):
        sc1, sc2, sc3 = st.columns(3)
        st_p = sc1.number_input("Palabras (P) bruto", min_value=0.0, step=1.0, key="aux_stroop_p")
        st_c = sc2.number_input("Colores (C) bruto", min_value=0.0, step=1.0, key="aux_stroop_c")
        st_pc = sc3.number_input("Palabra-Color (PC) bruto", min_value=0.0, step=1.0, key="aux_stroop_pc")
        res_stroop = calcular_stroop_golden(st_p, st_c, st_pc)
        if res_stroop:
            datos_auxiliares["stroop"] = res_stroop
            st.caption(f"PC' predicho: **{res_stroop['pc_prima']}** | Interferencia (PC - PC'): **{res_stroop['interferencia']:+g}**")

if "Trail Making Test (TMT)" in pruebas_set:
    with st.expander("⏱️ Asistente TMT (Tiempos A y B, Ratio B/A)", expanded=False):
        tc1, tc2 = st.columns(2)
        tmt_a = tc1.number_input("Tiempo Parte A (seg)", min_value=0.0, step=1.0, key="aux_tmt_a")
        tmt_b = tc2.number_input("Tiempo Parte B (seg)", min_value=0.0, step=1.0, key="aux_tmt_b")
        res_tmt = calcular_tmt_metricas(tmt_a, tmt_b)
        if res_tmt:
            datos_auxiliares["tmt"] = res_tmt
            st.caption(
                f"Diferencia B-A: **{res_tmt['diferencia_b_a']:g} s** | Ratio B/A: **{res_tmt['ratio_b_a']}** "
                + ("⚠️ (> 3.0 costo ejecutivo)" if res_tmt["alerta_ejecutiva"] else "")
            )

if "RAVLT" in pruebas_set:
    with st.expander("📝 Asistente RAVLT (Curva de aprendizaje A1-A5, B1, A6, A7)", expanded=False):
        rc = st.columns(8)
        rav_a1 = rc[0].number_input("A1", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a1")
        rav_a2 = rc[1].number_input("A2", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a2")
        rav_a3 = rc[2].number_input("A3", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a3")
        rav_a4 = rc[3].number_input("A4", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a4")
        rav_a5 = rc[4].number_input("A5", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a5")
        rav_b1 = rc[5].number_input("B1", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_b1")
        rav_a6 = rc[6].number_input("A6", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a6")
        rav_a7 = rc[7].number_input("A7", min_value=0.0, max_value=15.0, step=1.0, key="aux_rav_a7")
        if sum([rav_a1, rav_a2, rav_a3, rav_a4, rav_a5]) > 0:
            res_rav = calcular_ravlt_metricas(
                [rav_a1, rav_a2, rav_a3, rav_a4, rav_a5],
                b1=rav_b1,
                a6=rav_a6,
                a7=rav_a7,
            )
            if res_rav:
                datos_auxiliares["ravlt"] = res_rav
                st.caption(
                    f"Total A1-A5: **{res_rav['total_a1_a5']:g}** | Ganancia: **{res_rav['ganancia_aprendizaje']:+g}** | "
                    f"Retención A7/A5: **{res_rav['retencion_pct'] or 0}%**"
                )

if "Vineland" in pruebas_set:
    with st.expander("🤝 Asistente Vineland Forma B (Cociente Social)", expanded=False):
        edad_cron_anos = (
            round(edad_calc_tupla[0] + edad_calc_tupla[1] / 12.0, 2)
            if edad_calc_tupla is not None
            else 0.0
        )
        vc1, vc2 = st.columns(2)
        edad_soc = vc1.number_input("Edad Social (años, ej. 7.5)", min_value=0.0, step=0.1, key="aux_vin_es")
        edad_cron_in = vc2.number_input(
            "Edad Cronológica (años)",
            min_value=0.0,
            value=edad_cron_anos,
            step=0.1,
            key="aux_vin_ec",
        )
        res_vin = calcular_vineland_forma_b(edad_soc, edad_cron_in)
        if res_vin:
            datos_auxiliares["vineland_forma_b"] = res_vin
            st.caption(f"Cociente Social: **{res_vin['cociente_social']}** — **{res_vin['categoria']}**")

# Panel determinista de indicadores y alertas clínicas
if "DIVA-5" in pruebas_set or "DIVA-5 (Adultos)" in modelos_seleccionados:
    datos_auxiliares["diva5"] = {
        "adultez_inat": st.session_state["diva_ad_inat"],
        "adultez_hi": st.session_state["diva_ad_hi"],
        "infancia_inat": st.session_state["diva_inf_inat"],
        "infancia_hi": st.session_state["diva_inf_hi"],
        "inicio_antes_12": st.session_state["diva_inicio_12"],
        "ambitos": st.session_state["diva_ambitos"],
    }

analisis_perfil = analizar_perfil_clinico(
    df_procesado=df_procesado,
    edad_anos_meses=edad_calc_tupla,
    pruebas_usadas=pruebas_usadas,
    datos_auxiliares=datos_auxiliares,
)

if (
    analisis_perfil["alertas_criticas"]
    or analisis_perfil["hallazgos_automaticos"]
    or analisis_perfil["avisos_baremos"]
):
    with st.expander("🩺 Indicadores Psicométricos y Alertas Clínicas Detectadas", expanded=True):
        for alerta in analisis_perfil["alertas_criticas"]:
            st.error(alerta)
        for hallazgo in analisis_perfil["hallazgos_automaticos"]:
            st.info(hallazgo)
        for aviso in analisis_perfil["avisos_baremos"]:
            st.warning(aviso)

texto_puntajes_libre = st.text_area(
    "Pegar tabla de puntuaciones o resultados crudos adicionales (Excel / Planilla / Notas):",
    height=110,
    key="texto_puntajes_libre_input",
)

st.divider()

# =====================================================================
# 8. SECCIÓN 5: DETALLES CUALITATIVOS ADAPTATIVOS POR DOMINIO
# =====================================================================
st.header("5. Notas Cualitativas por Dominio y Pruebas")

pruebas_neuro_set = {
    "WISC-V",
    "WPPSI-IV",
    "WAIS-IV",
    "NEPSY-II",
    "TOMAL",
    "WRAML",
    "Stroop",
    "Trail Making Test (TMT)",
    "CPT-II",
    "Nesplora Aula",
    "Figura Compleja de Rey",
    "WCST",
    "RAVLT",
}
pruebas_psicoed_set = {
    "PROLEC-R / PROLEC-SE-R",
    "Woodcock-Muñoz",
    "TEMA-3",
    "TOMA-3",
    "Ortografía Feldman",
    "NALPA",
    "EPL",
    "Dictado de oraciones",
}
pruebas_cuest_set = {"SNAP-IV", "BRIEF", "Escala Durand", "Escala de Autoestima", "Vineland"}

mostrar_neuro = (
    not modelos_seleccionados and not pruebas_usadas
) or any("Neuropsicológica" in m for m in modelos_seleccionados) or bool(pruebas_set & pruebas_neuro_set)
mostrar_psicoed = (
    not modelos_seleccionados and not pruebas_usadas
) or any("Psicopedagógica" in m for m in modelos_seleccionados) or bool(pruebas_set & pruebas_psicoed_set)
mostrar_cuest = (
    any(k in m for m in modelos_seleccionados for k in ("Cuestionarios", "Vineland"))
    or bool(pruebas_set & pruebas_cuest_set)
)
mostrar_diva = ("DIVA-5" in pruebas_set) or ("DIVA-5 (Adultos)" in modelos_seleccionados)


def _render_bloque_neuro() -> tuple[str, str, str, str]:
    st.subheader("A. Desempeño Cognitivo y Neuropsicología")
    nc1, nc2 = st.columns(2)
    with nc1:
        w = st.text_area(
            "Funcionamiento Intelectual (IC 95%, si se informa ICG, índices secundarios IRC/IMTA/INV/ICC)",
            height=80,
            key="obs_wechsler_input",
        )
        m = st.text_area(
            "Memoria y Aprendizaje (curva de aprendizaje, intrusiones, pérdida diferida, reconocimiento en Rey)",
            height=80,
            key="obs_memoria_input",
        )
    with nc2:
        a = st.text_area(
            "Atención y Funciones Ejecutivas (CPT índice de confianza, Nesplora distractores, WCST, Stroop, TMT)",
            height=80,
            key="obs_atencion_fe_input",
        )
        v = st.text_area(
            "Visomotor y Lenguaje (tipo de copia Rey I-VII, prensión, fluidez semántica vs. fonológica)",
            height=80,
            key="obs_viso_leng_input",
        )
    return w, m, a, v


def _render_bloque_psicoed() -> tuple[str, str, str]:
    st.subheader("B. Psicopedagogía (Lectoescritura, Ortografía y Cálculo)")
    pc1, pc2 = st.columns(2)
    with pc1:
        alf = st.selectbox(
            "Nivel de alfabetización (si aplica)",
            ["", "Sí", "No", "En proceso"],
            key="alfabetizado_input",
        )
        lect = st.text_area(
            "Lectura, Escritura y Ortografía (PROLEC-R, EPL, velocidad/precisión, ejemplos literales de NALPA, Feldman)",
            height=95,
            key="obs_lectoescritura_input",
        )
    with pc2:
        mat = st.text_area(
            "Cálculo y Matemática (Woodcock-Muñoz ejemplos literales de aciertos/errores, TEMA-3 / TOMA-3)",
            height=130,
            key="obs_matematica_input",
        )
    return alf, lect, mat


def _render_bloque_cuestionarios() -> str:
    st.subheader("C. Cuestionarios y Conducta Adaptativa")
    return st.text_area(
        "Cuestionarios y Escalas (SNAP-IV, BRIEF, Durand, Autoestima, Vineland: informante e ítems destacados)",
        height=90,
        key="cuestionarios_txt_input",
    )


def _render_bloque_diva() -> str:
    st.subheader("D. DIVA-5 (Criterios DSM-5 Adultos)")
    dc1, dc2, dc3 = st.columns(3)
    dc1.number_input("Inatención Adultez (A1, 0-9)", min_value=0, max_value=9, step=1, key="diva_ad_inat")
    dc1.number_input("Hiperact./Impuls. Adultez (A2, 0-9)", min_value=0, max_value=9, step=1, key="diva_ad_hi")
    dc2.number_input("Inatención Infancia (0-9)", min_value=0, max_value=9, step=1, key="diva_inf_inat")
    dc2.number_input("Hiperact./Impuls. Infancia (0-9)", min_value=0, max_value=9, step=1, key="diva_inf_hi")
    dc3.checkbox("Inicio antes de los 12 años", key="diva_inicio_12")
    dc3.number_input("Ámbitos afectados (0-5)", min_value=0, max_value=5, step=1, key="diva_ambitos")
    return st.text_area("Notas clínicas DIVA-5 y diagnóstico diferencial", height=75, key="diva_otros_input")


if mostrar_neuro:
    obs_wechsler, obs_memoria, obs_atencion_fe, obs_viso_leng = _render_bloque_neuro()
if mostrar_psicoed:
    alfabetizado, obs_lectoescritura, obs_matematica = _render_bloque_psicoed()
if mostrar_cuest:
    cuestionarios_txt = _render_bloque_cuestionarios()
if mostrar_diva:
    diva_otros = _render_bloque_diva()

if not (mostrar_neuro and mostrar_psicoed and mostrar_cuest and mostrar_diva):
    with st.expander("📝 Otras áreas cualitativas (opcional)", expanded=False):
        if not mostrar_neuro:
            obs_wechsler, obs_memoria, obs_atencion_fe, obs_viso_leng = _render_bloque_neuro()
        if not mostrar_psicoed:
            alfabetizado, obs_lectoescritura, obs_matematica = _render_bloque_psicoed()
        if not mostrar_cuest:
            cuestionarios_txt = _render_bloque_cuestionarios()
        if not mostrar_diva:
            diva_otros = _render_bloque_diva()

st.divider()

# =====================================================================
# 9. SECCIÓN 6: CONCLUSIONES Y PERFILES DE RECOMENDACIONES
# =====================================================================
st.header("6. Conclusiones y Sugerencias Finales")

st.caption("Perfiles rápidos de recomendaciones (1 clic):")
cols_rec = st.columns(len(PERFILES_RECOMENDACIONES))
for idx_r, (nombre_perf, cfg_perf) in enumerate(PERFILES_RECOMENDACIONES.items()):
    if cols_rec[idx_r].button(f"🎯 {nombre_perf}", width="stretch", key=f"perf_rec_btn_{idx_r}"):
        st.session_state["pending_apply"] = {
            "sug_terapeuticas_sel": list(cfg_perf["terapeuticas"]),
            "sug_escolares_sel": list(cfg_perf["escolares"]),
        }
        st.rerun()

col_s1, col_s2 = st.columns(2)
with col_s1:
    impresion_destacar = st.text_area(
        "Síntesis diagnóstica / Qué querés destacar en las Conclusiones:",
        height=100,
        key="impresion_destacar_input",
        placeholder="Ej: Perfil cognitivo dentro del promedio con vulnerabilidad específica en el sostenimiento atencional...",
    )
    frecuencia_y_control = st.text_input(
        "Frecuencia de tratamiento y plazo de reevaluación (opcional)",
        key="frecuencia_control_input",
        placeholder="Ej: Frecuencia semanal. Reevaluación en 12 meses.",
    )

with col_s2:
    sug_terapeuticas_sel = st.multiselect(
        "Sugerencias Terapéuticas y Derivaciones (elegí las que quieras incluir):",
        options=list(BANCO_SUGERENCIAS["terapeuticas"].keys()),
        key="sug_terapeuticas_sel",
        placeholder="Seleccionar derivaciones y tratamientos...",
    )
    sug_escolares_sel = st.multiselect(
        "Sugerencias y Adaptaciones para la Escuela (elegí las que quieras incluir):",
        options=list(BANCO_SUGERENCIAS["escolares"].keys()),
        key="sug_escolares_sel",
        placeholder="Seleccionar adaptaciones escolares...",
    )

recom_personalizadas = st.text_area(
    "Agregar otras sugerencias personalizadas (para la familia, escuela o terapeutas):",
    height=75,
    key="recom_personalizadas_input",
)

if sug_terapeuticas_sel or sug_escolares_sel:
    with st.expander("👁️ Ver texto base de las sugerencias seleccionadas", expanded=False):
        if sug_terapeuticas_sel:
            st.markdown("**Recomendaciones Terapéuticas y Generales seleccionadas:**")
            for item in sug_terapeuticas_sel:
                st.markdown(f"- **{item}:** {BANCO_SUGERENCIAS['terapeuticas'][item]}")
        if sug_escolares_sel:
            st.markdown("**Recomendaciones para la Escuela seleccionadas:**")
            for item in sug_escolares_sel:
                st.markdown(f"- **{item}:** {BANCO_SUGERENCIAS['escolares'][item]}")

st.divider()
col_gen_local, col_gen_ia = st.columns(2)
with col_gen_local:
    boton_generar_local = st.button(
        "📝 Generar Borrador Local (Offline, sin IA)",
        type="primary",
        width="stretch",
    )
with col_gen_ia:
    boton_generar = st.button(
        "✨ Generar Informe Clínico Completo con Gemini 4 (Opcional)",
        width="stretch",
    )

# =====================================================================
# 10. CONSTRUCCIÓN DEL CASO, HUELLA DE IDENTIDAD Y GENERACIÓN
# =====================================================================
fecha_nac_str = fecha_nac.strftime("%d/%m/%Y") if fecha_nac else ""
fecha_eval_str = fecha_eval.strftime("%d/%m/%Y") if fecha_eval else ""

tabla_z_markdown = (
    df_procesado.to_markdown(index=False)
    if not df_procesado.empty
    else "No se completaron puntajes en la grilla interactiva."
)

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

cuestionarios_completo = cuestionarios_txt.strip()
if diva_otros.strip():
    cuestionarios_completo = f"{cuestionarios_completo}\nDIVA-5: {diva_otros.strip()}".strip()

datos_caso = {
    "modelos_seleccionados": modelos_seleccionados,
    "pruebas_usadas": pruebas_usadas,
    "nombre": nombre,
    "hc": hc,
    "edad_texto": edad_texto,
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
        "Funcionamiento Intelectual": obs_wechsler,
        "Memoria y Aprendizaje": obs_memoria,
        "Atención y Funciones Ejecutivas": obs_atencion_fe,
        "Visomotor y Lenguaje": obs_viso_leng,
        "Nivel de alfabetización": alfabetizado,
        "Lectoescritura / PROLEC": obs_lectoescritura,
        "Matemática / Woodcock": obs_matematica,
        "Cuestionarios y Auxiliares": cuestionarios_completo,
    },
    "analisis_clinico_markdown": analisis_perfil["resumen_markdown"],
    "impresion_destacar": impresion_destacar,
    "frecuencia_y_control": frecuencia_y_control,
    "detalle_terapeuticas": detalle_terapeuticas,
    "detalle_escolares": detalle_escolares,
    "recom_personalizadas": recom_personalizadas,
}

huella_actual = _calcular_huella_caso(
    {
        **datos_caso,
        "membrete": membrete_institucional,
        "puntajes_rows": df_procesado.to_dict(orient="records") if not df_procesado.empty else [],
        "datos_auxiliares": datos_auxiliares,
        "adjuntos": [a.name for a in (archivos_adjuntos or [])],
    }
)

conducta_tiene_evidencia = any(str(v or "").strip() for v in datos_caso["conducta"].values())
obs_tiene_evidencia = any(str(v or "").strip() for v in datos_caso["observaciones_cualitativas"].values())
hay_evidencia_clinica = any(
    [
        not df_procesado.empty,
        bool(texto_puntajes_libre.strip()),
        bool(archivos_adjuntos),
        bool(quien_deriva.strip()),
        bool(antecedentes.strip()),
        conducta_tiene_evidencia,
        obs_tiene_evidencia,
        bool(datos_auxiliares),
        bool(impresion_destacar.strip()),
        bool(sug_terapeuticas_sel),
        bool(sug_escolares_sel),
        bool(recom_personalizadas.strip()),
    ]
)

if boton_generar_local:
    if not hay_evidencia_clinica:
        st.warning(
            "Para generar un informe, cargá al menos puntajes en la grilla, notas clínicas, "
            "motivo de consulta, indicadores conductuales o adjuntos (no alcanza solo con elegir modelo y nombre)."
        )
    else:
        texto_local = generar_borrador_local(
            datos_caso=datos_caso,
            df_procesado=df_procesado,
            analisis_perfil=analisis_perfil,
        )
        st.session_state["informe_original"] = texto_local
        st.session_state["informe_actual"] = texto_local
        st.session_state["informe_version"] = st.session_state.get("informe_version", 0) + 1
        st.session_state["informe_meta"] = {
            "nombre": nombre,
            "fecha_eval": fecha_eval_str,
            "profesional": firma_profesional,
            "membrete": membrete_institucional,
            "origen": "Local (Offline)",
        }
        st.session_state["informe_df_puntajes"] = df_procesado.copy()
        st.session_state["informe_huella"] = huella_actual

if boton_generar:
    if not api_key:
        st.error("Por favor, ingresá tu API Key de Gemini en el menú lateral izquierdo (o usá 'Generar Borrador Local').")
    elif not hay_evidencia_clinica:
        st.warning(
            "Para generar un informe, cargá al menos puntajes en la grilla, notas clínicas, "
            "motivo de consulta, indicadores conductuales o adjuntos (no alcanza solo con elegir modelo y nombre)."
        )
    else:
        with st.spinner("Analizando perfil clínico, procesando escalas Z y redactando el informe completo..."):
            try:
                archivos_payload = [
                    {"name": archivo.name, "bytes": archivo.getvalue()}
                    for archivo in (archivos_adjuntos or [])
                ]

                texto_generado = motor_ia.generar_informe_clinico(
                    api_key=api_key,
                    modelo=modelo_gemini,
                    thinking_level=thinking_level,
                    datos_caso=datos_caso,
                    archivos=archivos_payload,
                    store=False,
                    anonimizar=anonimizar_ia,
                )

                st.session_state["informe_original"] = texto_generado
                st.session_state["informe_actual"] = texto_generado
                st.session_state["informe_version"] = st.session_state.get("informe_version", 0) + 1
                st.session_state["informe_meta"] = {
                    "nombre": nombre,
                    "fecha_eval": fecha_eval_str,
                    "profesional": firma_profesional,
                    "membrete": membrete_institucional,
                    "origen": f"Gemini ({modelo_gemini})",
                }
                st.session_state["informe_df_puntajes"] = df_procesado.copy()
                st.session_state["informe_huella"] = huella_actual

            except Exception as e:
                st.error(f"Error al generar el informe: {e}")

if st.session_state.get("informe_original"):
    st.subheader("📄 Informe Clínico Generado y Revisión")
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
        st.markdown(texto_vigente)
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
    huella_generada = st.session_state.get("informe_huella")
    borrador_desactualizado = bool(huella_generada and huella_generada != huella_actual)
    if borrador_desactualizado:
        st.warning(
            f"⚠️ La ficha actual ({nombre or 'sin nombre'} / {fecha_eval_str or 'sin fecha'}) cambió desde el "
            f"borrador generado para ({meta.get('nombre') or 'sin nombre'} / {meta.get('fecha_eval') or 'sin fecha'}). "
            "Regenerá el informe para habilitar las descargas actualizadas y evitar mezclar pacientes."
        )

    df_inf = st.session_state.get("informe_df_puntajes")
    tiene_z_numerico = bool(
        df_inf is not None
        and not df_inf.empty
        and any(str(z).strip() not in ("", "N/A", "-") for z in df_inf["Puntaje Z"])
    )

    col_opt1, col_opt2 = st.columns(2)
    incluir_grilla_z_word = col_opt1.checkbox(
        "Incluir Grilla Visual Z (-3 a +3 con X) en el Word",
        value=tiene_z_numerico,
        disabled=not tiene_z_numerico,
    )
    incluir_clausula = col_opt2.checkbox(
        "Incluir cláusula confidencial y alcance no judicial al pie",
        value=True,
    )

    texto_para_descarga = st.session_state["informe_actual"]
    docx_bytes = generar_docx_bytes(
        texto_markdown=texto_para_descarga,
        datos_filiacion=meta,
        df_puntajes=df_inf,
        incluir_tabla_filiacion=False,
        incluir_tabla_z=False,
        incluir_grilla_visual_z=incluir_grilla_z_word,
        membrete_institucional=meta.get("membrete", ""),
        incluir_clausula_confidencial=incluir_clausula,
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
            disabled=borrador_desactualizado,
        )
    with col_dl2:
        st.download_button(
            label="⬇️ Descargar en Markdown (.md)",
            data=texto_para_descarga,
            file_name=f"{nombre_base}.md",
            mime="text/markdown",
            width="stretch",
            disabled=borrador_desactualizado,
        )
