"""Generador clínico local determinista (100% offline, sin envío de datos a APIs externas)."""

from __future__ import annotations

import pandas as pd

from catalogo_clinico import INTRODUCCIONES_DOMINIOS
from psicometria import _normalizar_texto, formatear_puntaje


def _limpio(val, fallback: str = "") -> str:
    txt = str(val or "").strip()
    return txt if txt else fallback


def _clasificar_registro_dominio(nombre: str) -> str:
    n = _normalizar_texto(nombre)
    if any(k in n for k in ("wisc", "wppsi", "wais", "k-bit", "raven")):
        return "intelectual"
    if any(k in n for k in ("ravlt", "tomal", "wraml")) or (
        "rey" in n and any(k in n for k in ("memoria", "reconocimiento", "inmediat", "diferid", "demorad"))
    ):
        return "memoria"
    if any(k in n for k in ("cpt", "nesplora", "d2", "tmt a")):
        return "atencion"
    if any(k in n for k in ("wcst", "stroop", "tmt", "torre", "enfen", "banfe", "fluidez")):
        return "ejecutivas"
    if "brief" in n or "snap-iv" in n or "autoestima" in n or "durand" in n or "vineland" in n or "diva" in n or "ablas" in n:
        return "cuestionarios"
    if any(k in n for k in ("bender", "vmi", "beery", "copia", "visoespacial", "visomotor")):
        return "visomotor"
    if any(k in n for k in ("nepsy", "celf", "itpa", "peabody", "denominacion", "lenguaje", "token")):
        return "lenguaje"
    if any(k in n for k in ("woodcock", "prolec", "tema", "toma", "nalpa", "epl", "feldman", "ortografia", "lectura", "escritura", "calculo")):
        return "psicopedagogico"
    return "otros"


def _formatear_linea_puntaje(row: dict) -> str:
    sub = _limpio(row.get("Dominio / Prueba / Subtest"), "Subtest")
    punt = row.get("Puntaje Obtenido")
    esc = _limpio(row.get("Escala"))
    z_val = row.get("Puntaje Z")
    rango = _limpio(row.get("Rango Clínico"))
    notas = _limpio(row.get("Notas"))

    partes = [f"**{sub}**"]
    if punt is not None and pd.notna(punt):
        try:
            punt_txt = formatear_puntaje(float(punt))
        except (TypeError, ValueError):
            punt_txt = str(punt)
        esc_corta = esc.split(" - ", 1)[0] if " - " in esc else esc
        partes.append(f"puntaje obtenido `{punt_txt}` ({esc_corta})")
    if z_val is not None and str(z_val).strip() not in ("", "-", "N/A"):
        partes.append(f"`Z = {z_val}`")
    if rango:
        partes.append(f"rango **{rango}**")
    if notas:
        partes.append(f"({notas})")
    return "- " + ", ".join(partes) + "."


def _extraer_fortalezas_y_debilidades(df_procesado: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    fortalezas: list[str] = []
    compromisos: list[str] = []
    acordes: list[str] = []
    if df_procesado is None or df_procesado.empty:
        return fortalezas, compromisos, acordes

    for _, row in df_procesado.iterrows():
        nombre = _limpio(row.get("Dominio / Prueba / Subtest"))
        rango = _limpio(row.get("Rango Clínico"))
        rango_norm = _normalizar_texto(rango)
        z_raw = row.get("Puntaje Z")
        try:
            z_num = float(str(z_raw).replace(",", ".")) if z_raw not in (None, "", "-", "N/A") else None
        except ValueError:
            z_num = None

        etiqueta = f"{nombre} (Z={z_num:+.2f}, {rango})" if z_num is not None else f"{nombre} ({rango})"
        if "atipico rapido" in rango_norm or "deficit" in rango_norm or "limitrofe" in rango_norm or rango_norm == "dificultad":
            compromisos.append(etiqueta)
        elif z_num is not None and z_num <= -1.01:
            compromisos.append(etiqueta)
        elif z_num is not None and z_num >= 1.33:
            fortalezas.append(etiqueta)
        elif z_num is not None:
            acordes.append(etiqueta)

    return fortalezas, compromisos, acordes


def _lineas_viñetas(texto: str, fallback: str) -> list[str]:
    bruto = _limpio(texto)
    if not bruto:
        return [f"- {fallback}"]
    salida: list[str] = []
    for linea in bruto.splitlines():
        l = linea.strip().lstrip("-*•").strip()
        if l:
            salida.append(f"- {l}")
    return salida or [f"- {fallback}"]


def generar_borrador_local(
    datos_caso: dict,
    df_procesado: pd.DataFrame,
    analisis_perfil: dict | None = None,
) -> str:
    """Genera un informe clínico estructurado, trazable por puntaje y 100% offline."""
    modelos = datos_caso.get("modelos_seleccionados") or []
    pruebas = datos_caso.get("pruebas_usadas") or []
    modelos_norm = " ".join(_normalizar_texto(m) for m in modelos)

    if "combinado" in modelos_norm or ("neuropsicolog" in modelos_norm and "psicopedagog" in modelos_norm):
        titulo_informe = "INFORME DE EVALUACIÓN NEUROPSICOLÓGICA Y PSICOPEDAGÓGICA"
    elif "psicopedagog" in modelos_norm:
        titulo_informe = "INFORME DE EVALUACIÓN PSICOPEDAGÓGICA"
    else:
        titulo_informe = "INFORME DE EVALUACIÓN NEUROPSICOLÓGICA"

    nombre = _limpio(datos_caso.get("nombre"), "[Completar]")
    hc = _limpio(datos_caso.get("hc"), "[Completar]")
    fecha_nac = _limpio(datos_caso.get("fecha_nac"), "[Completar]")
    fecha_eval = _limpio(datos_caso.get("fecha_eval"), "[Completar]")
    edad_txt = _limpio(datos_caso.get("edad_texto"), "[Completar]")
    escolaridad = _limpio(datos_caso.get("escolaridad"), "[Completar]")
    nacionalidad = _limpio(datos_caso.get("nacionalidad"), "[Completar]")
    preferencia = _limpio(datos_caso.get("preferencia"), "[Completar]")
    medico = _limpio(datos_caso.get("medico"), "[Completar]")
    acompanante = _limpio(datos_caso.get("acompanante"), "No especificado")
    firma = _limpio(datos_caso.get("firma_profesional"), "[Firma y Sello del Profesional]")

    quien_deriva = _limpio(datos_caso.get("quien_deriva"), "No se consignó el motivo de derivación.")
    antecedentes = _limpio(datos_caso.get("antecedentes"), "No se consignaron antecedentes relevantes.")
    conducta = datos_caso.get("conducta") or {}
    obs_cual = datos_caso.get("observaciones_cualitativas") or {}
    tabla_z_md = _limpio(datos_caso.get("tabla_z_markdown"))
    texto_libre = _limpio(datos_caso.get("texto_puntajes_libre"))
    analisis = analisis_perfil or {}

    partes: list[str] = [f"# {titulo_informe}", ""]

    # 1. Datos de Filiación
    partes.extend(
        [
            "## 1. Datos de Filiación",
            "",
            "| Campo | Detalle |",
            "| :--- | :--- |",
            f"| **Apellido y Nombre** | {nombre} |",
            f"| **DNI / Historia Clínica** | {hc} |",
            f"| **Fecha de Nacimiento** | {fecha_nac} |",
            f"| **Fecha de Evaluación** | {fecha_eval} |",
            f"| **Edad Cronológica** | {edad_txt} |",
            f"| **Escolaridad** | {escolaridad} |",
            f"| **Nacionalidad** | {nacionalidad} |",
            f"| **Preferencia Manual** | {preferencia} |",
            f"| **Profesional Solicitante** | {medico} |",
            f"| **Acompañante** | {acompanante} |",
            "",
        ]
    )

    # 2. Motivo de Consulta y Antecedentes
    partes.extend(
        [
            "## 2. Motivo de Consulta y Antecedentes",
            "",
            f"**Motivo de derivación:** {quien_deriva}",
            "",
            f"**Antecedentes clínicos y evolutivos:** {antecedentes}",
            "",
        ]
    )

    # 3. Métodos / Técnicas
    subtitulo_tecnicas = (
        "## 3. Técnicas Implementadas"
        if ("psicopedagog" in modelos_norm and "neuropsicolog" not in modelos_norm)
        else "## 3. Métodos de Evaluación y Procedimientos"
    )
    partes.extend([subtitulo_tecnicas, ""])
    if pruebas:
        for p in pruebas:
            partes.append(f"- {p}")
    else:
        partes.append("- Entrevista clínica, observación conductual y técnicas psicométricas consignadas en la grilla.")
    partes.append("")

    # 4. Observación de la Conducta
    partes.extend(["## 4. Observación de la Conducta", ""])
    conducta_no_vacia = [(k, str(v).strip()) for k, v in conducta.items() if str(v or "").strip()]
    if conducta_no_vacia:
        for k, v in conducta_no_vacia:
            partes.append(f"- **{k}:** {v}")
    else:
        partes.append("- No se consignaron observaciones conductuales específicas en la ficha.")
    partes.append("")

    # 5. Puntuaciones Cuantitativas
    partes.extend(["## 5. Resultados Cuantitativos (Grilla Z)", ""])
    if tabla_z_md:
        partes.append(tabla_z_md)
    else:
        partes.append("No se cargaron puntajes estructurados en la grilla.")
    if texto_libre:
        partes.extend(["", "**Notas / puntajes adicionales:**", texto_libre])
    partes.append("")

    # 6. Análisis Clínico por Dominio
    partes.extend(["## 6. Análisis Clínico por Dominio", ""])
    filas_list = df_procesado.to_dict(orient="records") if (df_procesado is not None and not df_procesado.empty) else []
    por_dominio: dict[str, list[dict]] = {
        "intelectual": [],
        "memoria": [],
        "atencion": [],
        "ejecutivas": [],
        "visomotor": [],
        "lenguaje": [],
        "psicopedagogico": [],
        "cuestionarios": [],
        "otros": [],
    }
    for row in filas_list:
        dom = _clasificar_registro_dominio(str(row.get("Dominio / Prueba / Subtest") or ""))
        por_dominio[dom].append(row)

    titulos_dominios = [
        ("intelectual", "Funcionamiento Intelectual", INTRODUCCIONES_DOMINIOS["intelectual"], "Funcionamiento Intelectual"),
        ("memoria", "Memoria y Aprendizaje", INTRODUCCIONES_DOMINIOS["memoria"], "Memoria y Aprendizaje"),
        ("atencion", "Alerta y Atención", INTRODUCCIONES_DOMINIOS["atencion"], "Atención y Funciones Ejecutivas"),
        ("ejecutivas", "Funciones Ejecutivas", INTRODUCCIONES_DOMINIOS["ejecutivas"], "Atención y Funciones Ejecutivas"),
        ("visomotor", "Procesamiento Visomotor", INTRODUCCIONES_DOMINIOS["visomotor"], "Visomotor y Lenguaje"),
        ("lenguaje", "Lenguaje", INTRODUCCIONES_DOMINIOS["lenguaje"], "Visomotor y Lenguaje"),
    ]

    secciones_escritas = 0
    for clave_dom, titulo_dom, intro_txt, clave_obs in titulos_dominios:
        registros_dom = por_dominio[clave_dom]
        nota_dom = _limpio(obs_cual.get(clave_obs))
        if not registros_dom and not nota_dom:
            continue
        secciones_escritas += 1
        partes.extend([f"### {titulo_dom}", "", f"*{intro_txt}*", ""])
        for r in registros_dom:
            partes.append(_formatear_linea_puntaje(r))
        if nota_dom:
            partes.extend(["", f"**Observación cualitativa ({clave_obs}):** {nota_dom}"])
        partes.append("")

    # Área Psicopedagógica
    nota_lecto = _limpio(obs_cual.get("Lectoescritura / PROLEC"))
    nota_mate = _limpio(obs_cual.get("Matemática / Woodcock"))
    if por_dominio["psicopedagogico"] or nota_lecto or nota_mate:
        secciones_escritas += 1
        partes.extend(["### Perfil Psicopedagógico (Lectura, Escritura y Cálculo)", ""])
        for r in por_dominio["psicopedagogico"]:
            partes.append(_formatear_linea_puntaje(r))
        if nota_lecto:
            partes.append(f"\n**Lectoescritura:** {nota_lecto}")
        if nota_mate:
            partes.append(f"\n**Cálculo / Matemática:** {nota_mate}")
        hay_woodcock = any(
            "woodcock" in _normalizar_texto(str(r.get("Dominio / Prueba / Subtest") or ""))
            for r in por_dominio["psicopedagogico"]
        ) or any("woodcock" in _normalizar_texto(p) for p in pruebas)
        if hay_woodcock:
            partes.extend(
                [
                    "",
                    "*Nota: La Batería Woodcock-Muñoz no se encuentra estandarizada para nuestra población, por lo que sus valores deben ser considerados como orientativos.*",
                ]
            )
        partes.append("")

    # Cuestionarios / Conducta / Adaptación / Otros
    nota_cuest = _limpio(obs_cual.get("Cuestionarios y Auxiliares"))
    if por_dominio["cuestionarios"] or por_dominio["otros"] or nota_cuest:
        secciones_escritas += 1
        partes.extend(["### Escalas Conductuales, Adaptación y Técnicas Complementarias", ""])
        for r in por_dominio["cuestionarios"] + por_dominio["otros"]:
            partes.append(_formatear_linea_puntaje(r))
        if nota_cuest:
            partes.append(f"\n**Detalle de cuestionarios y escalas:** {nota_cuest}")
        partes.append("")

    if secciones_escritas == 0:
        partes.extend(["*No se registraron subpruebas cuantitativas ni notas por dominio.*", ""])

    # Integración determinista
    alertas = analisis.get("alertas_criticas") or []
    hallazgos = analisis.get("hallazgos_automaticos") or []
    baremos = analisis.get("avisos_baremos") or []
    if alertas or hallazgos or baremos:
        partes.extend(["### Síntesis Psicométrica Determinista (Por Batería)", ""])
        for a in alertas:
            partes.append(f"- **Alerta:** {a}")
        for h in hallazgos:
            partes.append(f"- **Hallazgo:** {h}")
        for b in baremos:
            partes.append(f"- **Nota de baremo:** {b}")
        partes.append("")

    # 7. Conclusiones
    fortalezas, compromisos, acordes = _extraer_fortalezas_y_debilidades(df_procesado)
    impresion = _limpio(datos_caso.get("impresion_destacar"))
    partes.extend(["## 7. Conclusiones e Integración Clínica", ""])

    if _limpio(datos_caso.get("quien_deriva")):
        partes.append(f"En respuesta al motivo de consulta (*{quien_deriva}*):")
        partes.append("")

    if fortalezas:
        partes.append(f"- **Fortalezas y rendimientos destacados:** {'; '.join(fortalezas)}.")
    if acordes:
        resumen_acordes = "; ".join(acordes[:6]) + (" (entre otras medidas en rango esperado)" if len(acordes) > 6 else "")
        partes.append(f"- **Rendimientos acordes a lo esperado para la edad:** {resumen_acordes}.")
    if compromisos:
        partes.append(f"- **Áreas de descenso / vulnerabilidad observada:** {'; '.join(compromisos)}.")
    if not (fortalezas or acordes or compromisos):
        partes.append("- **Evidencia cuantitativa:** Sin puntajes Z cargados; las conclusiones se apoyan en las observaciones clínicas consignadas.")

    pendientes_hallazgos = [h for h in hallazgos if "queda pendiente" in _normalizar_texto(h)]
    for pend in pendientes_hallazgos:
        partes.append(f"- **Dato pendiente para precisar hipótesis:** {pend}")

    if impresion:
        partes.append(f"- **Impresión clínica destacada por el evaluador:** {impresion}")

    perfil_desc = impresion if impresion else (
        "fortalezas y áreas de vulnerabilidad descritas en el análisis por batería"
        if (compromisos or fortalezas)
        else "desempeño clínico pendiente de integración cuantitativa completa"
    )
    partes.extend(
        [
            "",
            f"En síntesis, estos indicadores caracterizan a {nombre} con un perfil compatible con {perfil_desc}. "
            "El diagnóstico definitivo quedará a cargo del médico tratante a partir de la integración clínica de los presentes hallazgos.",
            "",
        ]
    )

    # 8. Recomendaciones
    frecuencia = _limpio(datos_caso.get("frecuencia_y_control"))
    terap = _limpio(datos_caso.get("detalle_terapeuticas"))
    recom_extra = _limpio(datos_caso.get("recom_personalizadas"))
    esc = _limpio(datos_caso.get("detalle_escolares"))

    partes.extend(["## 8. Recomendaciones", "", "### Recomendaciones Terapéuticas y Generales", ""])
    partes.extend(_lineas_viñetas(terap, "Definir abordaje terapéutico según evolución clínica."))
    if recom_extra:
        partes.extend(_lineas_viñetas(recom_extra, ""))
    if frecuencia:
        partes.append(f"- **Seguimiento y reevaluación:** {frecuencia}")

    partes.extend(["", "### Recomendaciones para la Escuela (Adaptaciones de Acceso y Contexto)", ""])
    partes.extend(_lineas_viñetas(esc, "Implementar apoyos pedagógicos y adaptaciones de acceso acordes al perfil."))

    partes.extend(["", "---", "", f"**{firma}**"])
    return "\n".join(partes).strip()
