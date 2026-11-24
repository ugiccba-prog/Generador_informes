"""Análisis psicométrico determinista de perfil clínico y alertas de baremos."""

from __future__ import annotations

import pandas as pd

from catalogo_clinico import ESCALA_CI, ESCALA_T_INVERSO
from psicometria import _normalizar_texto


def _a_float(valor) -> float | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto in ("-", "N/A"):
        return None
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return None


def _extraer_registros(df_procesado: pd.DataFrame) -> list[dict]:
    if df_procesado is None or df_procesado.empty:
        return []
    registros = []
    for _, row in df_procesado.iterrows():
        nombre = str(row.get("Dominio / Prueba / Subtest") or "").strip()
        norm = _normalizar_texto(nombre)
        puntaje = _a_float(row.get("Puntaje Obtenido"))
        escala = str(row.get("Escala") or "").strip()
        z_val = _a_float(row.get("Puntaje Z"))
        rango = str(row.get("Rango Clínico") or "").strip()
        notas = str(row.get("Notas") or "").strip()
        registros.append(
            {
                "nombre": nombre,
                "norm": norm,
                "puntaje": puntaje,
                "escala": escala,
                "z": z_val,
                "rango": rango,
                "notas": notas,
            }
        )
    return registros


def _detectar_bateria(norm: str) -> str | None:
    """Identifica de forma estricta la batería/edición a la que pertenece una fila."""
    if "wisc-v" in norm or "wisc v" in norm:
        return "WISC-V"
    if "wppsi-iv" in norm or "wppsi iv" in norm:
        return "WPPSI-IV"
    if "wais-iv" in norm or "wais iv" in norm:
        return "WAIS-IV"
    if "cpt-ii" in norm or "cpt ii" in norm or norm.startswith("cpt"):
        return "CPT-II"
    if "nesplora" in norm:
        return "Nesplora Aula"
    if "ravlt" in norm:
        return "RAVLT"
    if "tomal" in norm:
        return "TOMAL"
    if "wraml" in norm:
        return "WRAML"
    if "figura compleja de rey" in norm or ("rey" in norm and any(k in norm for k in ("figura", "copia", "memoria", "reconocimiento"))):
        return "Figura Compleja de Rey"
    if "brief" in norm:
        return "BRIEF"
    if "snap-iv" in norm:
        return "SNAP-IV"
    if "autoestima" in norm:
        return "Escala de Autoestima"
    if "durand" in norm:
        return "Escala Durand"
    if "vineland" in norm:
        return "Vineland"
    return None


def _formatear_z(z_val: float | None) -> str:
    return f"Z={z_val:+.2f}" if z_val is not None else "Z=N/A"


def _analizar_wechsler(
    registros: list[dict],
    edad_anos_meses: tuple[int, int] | None,
    pruebas_usadas: list[str],
    alertas_criticas: list[str],
    hallazgos: list[str],
) -> None:
    claves_primarias = ("icv", "ive", "irp", "irf", "imt", "ivp")
    por_edicion: dict[str, dict] = {}

    for reg in registros:
        if reg["escala"] != ESCALA_CI or reg["puntaje"] is None:
            continue
        norm = reg["norm"]
        edicion = _detectar_bateria(norm)
        if edicion not in ("WISC-V", "WPPSI-IV", "WAIS-IV"):
            continue

        bucket = por_edicion.setdefault(
            edicion,
            {"primarios": {}, "cit": None, "icg": None, "icc": None},
        )
        if "cit" in norm or "coeficiente intelectual total" in norm:
            bucket["cit"] = reg["puntaje"]
        elif "(icg)" in norm or "capacidad general" in norm:
            bucket["icg"] = reg["puntaje"]
        elif "(icc)" in norm or "competencia cognitiva" in norm:
            bucket["icc"] = reg["puntaje"]
        else:
            for clave in claves_primarias:
                if f"({clave})" in norm or f" {clave}" in norm:
                    bucket["primarios"][clave.upper()] = reg["puntaje"]
                    break

    for edicion, datos_ed in por_edicion.items():
        indices_primarios = datos_ed["primarios"]
        cit_val = datos_ed["cit"]
        icg_val = datos_ed["icg"]
        icc_val = datos_ed["icc"]

        if len(indices_primarios) >= 2:
            max_k = max(indices_primarios, key=lambda k: indices_primarios[k])
            min_k = min(indices_primarios, key=lambda k: indices_primarios[k])
            amplitud = indices_primarios[max_k] - indices_primarios[min_k]
            if amplitud >= 23:
                msg = (
                    f"Dispersión marcada Wechsler ({edicion}: {amplitud:.0f} pts entre "
                    f"{max_k}={indices_primarios[max_k]:.0f} y {min_k}={indices_primarios[min_k]:.0f}): el CIT"
                )
                if cit_val is not None:
                    msg += f" ({cit_val:.0f})"
                msg += " puede no representar una capacidad unitaria; priorizar interpretación del ICG."
                alertas_criticas.append(msg)
            elif amplitud >= 15:
                hallazgos.append(
                    f"Heterogeneidad inter-índices moderada en {edicion} ({amplitud:.0f} pts entre "
                    f"{max_k}={indices_primarios[max_k]:.0f} y {min_k}={indices_primarios[min_k]:.0f})."
                )

        if icg_val is not None and icc_val is not None and (icg_val - icc_val) >= 12:
            alertas_criticas.append(
                f"Disociación ICG ({icg_val:.0f}) > ICC ({icc_val:.0f}) en {edicion} por {icg_val - icc_val:.0f} pts: "
                "potencial de razonamiento preservado con cuello de botella en eficiencia cognitiva (IMT/IVP)."
            )
        elif icg_val is not None and ("IMT" in indices_primarios or "IVP" in indices_primarios):
            operativos = [indices_primarios[k] for k in ("IMT", "IVP") if k in indices_primarios]
            prom_op = sum(operativos) / len(operativos)
            if (icg_val - prom_op) >= 15:
                detalle_op = ", ".join(f"{k}={indices_primarios[k]:.0f}" for k in ("IMT", "IVP") if k in indices_primarios)
                hallazgos.append(
                    f"Brecha relevante en {edicion} entre ICG ({icg_val:.0f}) e índices operativos ({detalle_op}; promedio {prom_op:.0f})."
                )

    # Coherencia etaria de escalas Wechsler
    if edad_anos_meses is not None:
        anos, meses = edad_anos_meses
        meses_tot = anos * 12 + meses
        baterias_norm = {_normalizar_texto(p) for p in pruebas_usadas}
        if "wppsi-iv" in baterias_norm and not (30 <= meses_tot <= 91):
            alertas_criticas.append(
                f"Coherencia etaria: se seleccionó WPPSI-IV (2:6 a 7:7 años) para una edad de {anos} años y {meses} meses."
            )
        if "wisc-v" in baterias_norm and not (72 <= meses_tot <= 203):
            alertas_criticas.append(
                f"Coherencia etaria: se seleccionó WISC-V (6:0 a 16:11 años) para una edad de {anos} años y {meses} meses."
            )
        if "wais-iv" in baterias_norm and meses_tot < 192:
            alertas_criticas.append(
                f"Coherencia etaria: se seleccionó WAIS-IV (≥ 16:0 años) para una edad de {anos} años y {meses} meses."
            )


def _analizar_atencion_cpt_nesplora(
    registros: list[dict],
    alertas_criticas: list[str],
    hallazgos: list[str],
) -> None:
    por_bateria: dict[str, dict] = {}

    for reg in registros:
        bat = _detectar_bateria(reg["norm"])
        if bat not in ("CPT-II", "Nesplora Aula"):
            continue
        bucket = por_bateria.setdefault(bat, {"rt_rapido": [], "comisiones": [], "omisiones": []})
        if "atipico rapido" in _normalizar_texto(reg["rango"]):
            bucket["rt_rapido"].append(reg)
        if "comision" in reg["norm"] and reg["z"] is not None:
            bucket["comisiones"].append(reg)
        if "omision" in reg["norm"] and reg["z"] is not None:
            bucket["omisiones"].append(reg)

    for bat, datos_bat in por_bateria.items():
        rt_list = datos_bat["rt_rapido"]
        com_list = datos_bat["comisiones"]
        om_list = datos_bat["omisiones"]

        com_bajas_z = [r for r in com_list if r["z"] is not None and r["z"] <= -1.00]
        if rt_list:
            rt_txt = ", ".join(
                f"{r['nombre']}={r['puntaje']:g} ({_formatear_z(r['z'])})"
                for r in rt_list
                if r["puntaje"] is not None
            ) or bat
            if com_bajas_z:
                com_txt = ", ".join(
                    f"{r['nombre']}={r['puntaje']:g} ({_formatear_z(r['z'])})"
                    for r in com_bajas_z
                    if r["puntaje"] is not None
                )
                alertas_criticas.append(
                    f"{bat}: Tiempo de reacción atípicamente rápido ({rt_txt}) combinado con Comisiones elevadas "
                    f"({com_txt}) (patrón consistente con estilo impulsivo / trade-off velocidad-precisión)."
                )
            else:
                alertas_criticas.append(
                    f"{bat}: Tiempo de reacción atípicamente rápido ({rt_txt}). No interpretar como "
                    "'Normal Alto/Superior', sino como sesgo de respuesta acelerada."
                )

        om_severas = [r for r in om_list if r["z"] is not None and r["z"] <= -1.50]
        com_preservadas = [r for r in com_list if r["z"] is not None and r["z"] >= 0.50]
        if om_severas and com_preservadas:
            om_txt = ", ".join(f"{r['nombre']} ({_formatear_z(r['z'])})" for r in om_severas)
            com_txt = ", ".join(f"{r['nombre']} ({_formatear_z(r['z'])})" for r in com_preservadas)
            hallazgos.append(
                f"{bat}: Omisiones muy elevadas ({om_txt}) con Comisiones bajas ({com_txt}) — verificar posible "
                "desconexión atencional sostenida que reduce artificialmente las respuestas por comisión."
            )


def _analizar_memoria_diferencial(registros: list[dict], hallazgos: list[str]) -> None:
    baterias_memoria = ("RAVLT", "TOMAL", "WRAML", "Figura Compleja de Rey")
    por_bateria: dict[str, dict[str, list[dict]]] = {}

    for reg in registros:
        if reg["z"] is None:
            continue
        bat = _detectar_bateria(reg["norm"])
        if bat not in baterias_memoria:
            continue
        norm = reg["norm"]
        bucket = por_bateria.setdefault(bat, {"inm": [], "dem": [], "rec": []})

        if any(k in norm for k in ("inmediat", "a1-a5", "total aprendizaje", "post-interferencia", "a6")):
            bucket["inm"].append(reg)
        elif any(k in norm for k in ("demorad", "diferid", "a7")):
            bucket["dem"].append(reg)
        elif "reconocimiento" in norm:
            bucket["rec"].append(reg)

    for bat, fases in por_bateria.items():
        if not fases["dem"]:
            continue

        prom_dem = sum(r["z"] for r in fases["dem"]) / len(fases["dem"])
        prom_inm = (sum(r["z"] for r in fases["inm"]) / len(fases["inm"])) if fases["inm"] else None
        prom_rec = (sum(r["z"] for r in fases["rec"]) / len(fases["rec"])) if fases["rec"] else None

        dem_desc = ", ".join(f"{r['nombre']} ({_formatear_z(r['z'])})" for r in fases["dem"])
        inm_desc = ", ".join(f"{r['nombre']} ({_formatear_z(r['z'])})" for r in fases["inm"])
        rec_desc = ", ".join(f"{r['nombre']} ({_formatear_z(r['z'])})" for r in fases["rec"])

        if prom_dem <= -1.33:
            if prom_rec is not None and prom_rec > -1.00:
                hallazgos.append(
                    f"Perfil mnésico en {bat} ({dem_desc}): recuerdo diferido descendido con reconocimiento "
                    f"preservado ({rec_desc}) (sugiere falla en estrategias de recuperación más que pérdida de almacenamiento)."
                )
            elif prom_inm is not None and prom_inm > -1.00 and prom_rec is not None and prom_rec <= -1.33:
                hallazgos.append(
                    f"Perfil mnésico en {bat}: recuerdo inmediato preservado ({inm_desc}) con descenso en "
                    f"diferido ({dem_desc}) y reconocimiento ({rec_desc}) (sugiere vulnerabilidad en consolidación/almacenamiento)."
                )
            elif prom_inm is not None and prom_inm <= -1.33 and prom_rec is not None and prom_rec <= -1.33:
                hallazgos.append(
                    f"Perfil mnésico en {bat}: compromiso en fase inmediata ({inm_desc}), diferido ({dem_desc}) "
                    f"y reconocimiento ({rec_desc}) (sugiere falla primaria de codificación/registro atencional inicial)."
                )
            else:
                otras_rec = [b for b, f in por_bateria.items() if b != bat and f["rec"]]
                aviso_rec = (
                    f" El reconocimiento disponible pertenece a {', '.join(otras_rec)} y no se cruza con {bat}."
                    if otras_rec
                    else ""
                )
                extra_inm = f" El recuerdo inmediato de {bat} obtuvo {inm_desc}." if inm_desc else ""
                hallazgos.append(
                    f"En {bat}, el recuerdo diferido obtuvo {dem_desc}.{extra_inm}{aviso_rec} "
                    f"Para caracterizar codificación/almacenamiento vs. recuperación queda pendiente el reconocimiento de {bat}."
                )


def _analizar_cuestionarios_y_auxiliares(
    registros: list[dict],
    datos_auxiliares: dict,
    alertas_criticas: list[str],
    hallazgos: list[str],
) -> None:
    brief_clinico = []
    brief_potencial = []
    brief_leve = []
    durand_scores: list[tuple[str, float]] = []

    for reg in registros:
        norm = reg["norm"]
        val = reg["puntaje"]
        if val is None:
            continue

        if "brief" in norm and (reg["escala"] == ESCALA_T_INVERSO or "t " in _normalizar_texto(reg["escala"])):
            etiqueta_brief = reg["nombre"]
            notas_b = reg.get("notas", "")
            if "informante:" in _normalizar_texto(notas_b) and not any(
                inf in _normalizar_texto(etiqueta_brief) for inf in ("madre", "padre", "docente")
            ):
                etiqueta_brief = f"{etiqueta_brief} ({notas_b})"
            if val >= 70:
                brief_clinico.append(f"{etiqueta_brief} (T={val:.0f})")
            elif val >= 65:
                brief_potencial.append(f"{etiqueta_brief} (T={val:.0f})")
            elif val >= 60:
                brief_leve.append(f"{etiqueta_brief} (T={val:.0f})")

        elif "snap-iv" in norm:
            es_promedio = any(
                k in norm or k in _normalizar_texto(reg.get("notas", ""))
                for k in ("promedio", "media", "item")
            )
            if "inatencion" in norm and (val >= 15 or (es_promedio and 1.67 <= val <= 3.0)):
                alertas_criticas.append(
                    f"SNAP-IV Inatención supera punto de corte clínico ({val:g}; {reg['nombre']})."
                )
            elif ("hiperactividad" in norm or "impulsividad" in norm) and (
                val >= 16 or (es_promedio and 1.67 <= val <= 3.0)
            ):
                alertas_criticas.append(
                    f"SNAP-IV Hiperactividad/Impulsividad supera punto de corte clínico ({val:g}; {reg['nombre']})."
                )

        elif "autoestima" in norm and val <= 12:
            alertas_criticas.append(f"{reg['nombre']} en rango significativo (puntaje {val:g} ≤ 12).")

        elif "durand" in norm:
            etiqueta = reg["nombre"].split("-")[-1].strip()
            durand_scores.append((etiqueta, val))

    if brief_clinico:
        alertas_criticas.append("BRIEF clínicamente elevado (T ≥ 70): " + ", ".join(brief_clinico) + ".")
    if brief_potencial:
        hallazgos.append("BRIEF potencialmente clínico (T 65–69): " + ", ".join(brief_potencial) + ".")
    if brief_leve:
        hallazgos.append("BRIEF levemente elevado (T 60–64): " + ", ".join(brief_leve) + ".")

    if len(durand_scores) >= 2:
        max_val = max(v for _, v in durand_scores)
        if max_val > 0:
            predominantes = [k for k, v in durand_scores if v == max_val]
            hallazgos.append(
                f"Escala Durand (MAS): función conductual predominante → {', '.join(predominantes)} ({max_val:g})."
            )

    # Auxiliares calculados (Stroop, TMT, RAVLT, Vineland Forma B, DIVA-5)
    stroop = datos_auxiliares.get("stroop")
    if isinstance(stroop, dict) and "interferencia" in stroop:
        hallazgos.append(
            f"Stroop Golden calculado: PC' predicho = {stroop['pc_prima']}, Interferencia = {stroop['interferencia']:+g}."
        )

    tmt = datos_auxiliares.get("tmt")
    if isinstance(tmt, dict) and "ratio_b_a" in tmt:
        msg_tmt = f"TMT calculado: B - A = {tmt['diferencia_b_a']:g} s, Ratio B/A = {tmt['ratio_b_a']}"
        if tmt.get("alerta_ejecutiva"):
            alertas_criticas.append(f"{msg_tmt} (> 3.0: marcador de rigidez/costo ejecutivo desproporcionado).")
        else:
            hallazgos.append(f"{msg_tmt} (sin desproporción B/A > 3.0).")

    ravlt = datos_auxiliares.get("ravlt")
    if isinstance(ravlt, dict) and ravlt.get("total_a1_a5") is not None:
        partes = [
            f"Total A1-A5 = {ravlt['total_a1_a5']:g}",
            f"Ganancia (A5-A1) = {ravlt['ganancia_aprendizaje']:+g}",
        ]
        if ravlt.get("retencion_pct") is not None:
            partes.append(f"Retención A7/A5 = {ravlt['retencion_pct']}%")
        hallazgos.append("RAVLT auxiliar: " + ", ".join(partes) + ".")

    vineland_b = datos_auxiliares.get("vineland_forma_b")
    if isinstance(vineland_b, dict) and vineland_b.get("cociente_social") is not None:
        hallazgos.append(
            f"Vineland Forma B: Cociente Social = {vineland_b['cociente_social']} ({vineland_b['categoria']})."
        )

    diva = datos_auxiliares.get("diva5")
    if isinstance(diva, dict):
        ad_in = diva.get("adultez_inat", 0)
        ad_hi = diva.get("adultez_hi", 0)
        inf_in = diva.get("infancia_inat", 0)
        inf_hi = diva.get("infancia_hi", 0)
        inicio_12 = diva.get("inicio_antes_12", False)
        ambitos = diva.get("ambitos", 0)
        if any([ad_in, ad_hi, inf_in, inf_hi]):
            cumple_ad = ad_in >= 5 or ad_hi >= 5
            cumple_inf = inf_in >= 6 or inf_hi >= 6
            hallazgos.append(
                f"DIVA-5 (DSM-5): Adultez ({ad_in}/9 inat, {ad_hi}/9 H/I; umbral ≥5), "
                f"Infancia ({inf_in}/9 inat, {inf_hi}/9 H/I; umbral ≥6), "
                f"Inicio <12 años: {'Sí' if inicio_12 else 'No'}, Ámbitos: {ambitos}/≥2 → "
                f"{'Cumple umbrales DSM-5' if (cumple_ad and cumple_inf and inicio_12 and ambitos >= 2) else 'Evaluación parcial / no alcanza todos los umbrales'}."
            )


def _avisos_huecos_baremos(
    edad_anos_meses: tuple[int, int] | None,
    pruebas_usadas: list[str],
) -> list[str]:
    avisos: list[str] = []
    baterias = {_normalizar_texto(p) for p in pruebas_usadas}

    if "brief" in baterias:
        avisos.append(
            "Hueco conocido en fotos de baremos (Memoria): BRIEF no tiene fotos de tablas de padres para niñas; verificar manual PDF si aplica."
        )

    if edad_anos_meses is None:
        return avisos

    anos, meses = edad_anos_meses
    if "tomal" in baterias and anos in {5, 6, 9, 13, 16, 18, 19}:
        avisos.append(
            f"Hueco conocido en fotos de baremos (Memoria): TOMAL no tiene fotos de baremo para {anos} años; consultar manual PDF."
        )
    if "wraml" in baterias and anos >= 14 and not (anos == 15 and meses == 0):
        avisos.append(
            f"Hueco conocido en fotos de baremos (Memoria): WRAML no tiene fotos de baremo para {anos} años (salvo 15:0); consultar manual PDF."
        )
    if "nepsy-ii" in baterias and 13 <= anos <= 16:
        avisos.append(
            f"Hueco conocido en fotos de baremos (Memoria): NEPSY-II Tabla A4 sin fotos para 13–16 años (edad {anos} años); consultar manual PDF."
        )
    if "figura compleja de rey" in baterias and anos not in {13, 15, 17}:
        avisos.append(
            f"Hueco conocido en fotos de baremos (Memoria): Figura de Rey (Meyers) en fotos solo cubre 13, 15 y 17 años (edad {anos} años); consultar manual PDF."
        )

    return avisos


def analizar_perfil_clinico(
    df_procesado: pd.DataFrame,
    edad_anos_meses: tuple[int, int] | None = None,
    pruebas_usadas: list[str] | None = None,
    datos_auxiliares: dict | None = None,
) -> dict:
    """Ejecuta reglas psicométricas deterministas y devuelve alertas, hallazgos y resumen."""
    registros = _extraer_registros(df_procesado)
    pruebas = list(pruebas_usadas or [])
    aux = dict(datos_auxiliares or {})

    alertas_criticas: list[str] = []
    hallazgos_automaticos: list[str] = []

    _analizar_wechsler(registros, edad_anos_meses, pruebas, alertas_criticas, hallazgos_automaticos)
    _analizar_atencion_cpt_nesplora(registros, alertas_criticas, hallazgos_automaticos)
    _analizar_memoria_diferencial(registros, hallazgos_automaticos)
    _analizar_cuestionarios_y_auxiliares(registros, aux, alertas_criticas, hallazgos_automaticos)
    avisos_baremos = _avisos_huecos_baremos(edad_anos_meses, pruebas)

    secciones_md: list[str] = []
    if alertas_criticas:
        secciones_md.append("**Alertas críticas detectadas:**\n" + "\n".join(f"- {a}" for a in alertas_criticas))
    if hallazgos_automaticos:
        secciones_md.append("**Hallazgos psicométricos cruzados:**\n" + "\n".join(f"- {h}" for h in hallazgos_automaticos))
    if avisos_baremos:
        secciones_md.append("**Recordatorios de baremos:**\n" + "\n".join(f"- {v}" for v in avisos_baremos))

    resumen_md = "\n\n".join(secciones_md) if secciones_md else "Sin alertas o disociaciones automáticas destacadas."

    return {
        "alertas_criticas": alertas_criticas,
        "hallazgos_automaticos": hallazgos_automaticos,
        "avisos_baremos": avisos_baremos,
        "resumen_markdown": resumen_md,
    }
