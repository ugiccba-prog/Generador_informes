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


def _analizar_wechsler(
    registros: list[dict],
    edad_anos_meses: tuple[int, int] | None,
    pruebas_usadas: list[str],
    alertas_criticas: list[str],
    hallazgos: list[str],
) -> None:
    claves_primarias = ("icv", "ive", "irp", "irf", "imt", "ivp")
    indices_primarios: dict[str, float] = {}
    cit_val = None
    icg_val = None
    icc_val = None

    for reg in registros:
        if reg["escala"] != ESCALA_CI or reg["puntaje"] is None:
            continue
        norm = reg["norm"]
        if not any(b in norm for b in ("wisc", "wppsi", "wais")):
            continue

        if "cit" in norm or "coeficiente intelectual total" in norm:
            cit_val = reg["puntaje"]
        elif "(icg)" in norm or "capacidad general" in norm:
            icg_val = reg["puntaje"]
        elif "(icc)" in norm or "competencia cognitiva" in norm:
            icc_val = reg["puntaje"]
        else:
            for clave in claves_primarias:
                if f"({clave})" in norm or f" {clave}" in norm:
                    indices_primarios[clave.upper()] = reg["puntaje"]
                    break

    if len(indices_primarios) >= 2:
        max_k = max(indices_primarios, key=lambda k: indices_primarios[k])
        min_k = min(indices_primarios, key=lambda k: indices_primarios[k])
        amplitud = indices_primarios[max_k] - indices_primarios[min_k]
        if amplitud >= 23:
            msg = (
                f"Dispersión marcada Wechsler ({amplitud:.0f} pts entre {max_k}={indices_primarios[max_k]:.0f} "
                f"y {min_k}={indices_primarios[min_k]:.0f}): el CIT"
            )
            if cit_val is not None:
                msg += f" ({cit_val:.0f})"
            msg += " puede no representar una capacidad unitaria; priorizar interpretación del ICG."
            alertas_criticas.append(msg)
        elif amplitud >= 15:
            hallazgos.append(
                f"Heterogeneidad inter-índices moderada en Wechsler ({amplitud:.0f} pts entre {max_k} y {min_k})."
            )

    if icg_val is not None and icc_val is not None and (icg_val - icc_val) >= 12:
        alertas_criticas.append(
            f"Disociación ICG ({icg_val:.0f}) > ICC ({icc_val:.0f}) por {icg_val - icc_val:.0f} pts: "
            "potencial de razonamiento preservado con cuello de botella en eficiencia cognitiva (IMT/IVP)."
        )
    elif icg_val is not None and ("IMT" in indices_primarios or "IVP" in indices_primarios):
        operativos = [indices_primarios[k] for k in ("IMT", "IVP") if k in indices_primarios]
        prom_op = sum(operativos) / len(operativos)
        if (icg_val - prom_op) >= 15:
            hallazgos.append(
                f"Brecha relevante entre ICG ({icg_val:.0f}) e índices operativos IMT/IVP (promedio {prom_op:.0f})."
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
    hit_rt_rapido = False
    comisiones_z = None
    omisiones_z = None

    for reg in registros:
        norm = reg["norm"]
        if not any(b in norm for b in ("cpt", "nesplora")):
            continue
        if "atipico rapido" in _normalizar_texto(reg["rango"]):
            hit_rt_rapido = True
        if "comision" in norm and reg["z"] is not None:
            comisiones_z = reg["z"]
        if "omision" in norm and reg["z"] is not None:
            omisiones_z = reg["z"]

    if hit_rt_rapido:
        if comisiones_z is not None and comisiones_z <= -1.00:
            alertas_criticas.append(
                "CPT/Nesplora: Tiempo de reacción atípicamente rápido (T < 40) combinado con Comisiones elevadas "
                "(patrón consistente con estilo impulsivo / trade-off velocidad-precisión)."
            )
        else:
            alertas_criticas.append(
                "CPT/Nesplora: Tiempo de reacción atípicamente rápido (T < 40 / Pc ≤ 15). No interpretar como "
                "'Normal Alto/Superior', sino como sesgo de respuesta acelerada."
            )

    if omisiones_z is not None and omisiones_z <= -1.50 and comisiones_z is not None and comisiones_z >= 0.50:
        hallazgos.append(
            "CPT/Nesplora: Omisiones muy elevadas (Z ≤ -1.50) con Comisiones bajas — verificar posible desconexión "
            "atencional sostenida que reduce artificialmente las respuestas por comisión."
        )


def _analizar_memoria_diferencial(registros: list[dict], hallazgos: list[str]) -> None:
    z_inm: list[float] = []
    z_dem: list[float] = []
    z_rec: list[float] = []

    for reg in registros:
        if reg["z"] is None:
            continue
        norm = reg["norm"]
        if not any(b in norm for b in ("ravlt", "tomal", "wraml", "rey")):
            continue

        if any(k in norm for k in ("inmediat", "a1-a5", "total aprendizaje", "post-interferencia", "a6")):
            z_inm.append(reg["z"])
        elif any(k in norm for k in ("demorad", "diferid", "a7")):
            z_dem.append(reg["z"])
        elif "reconocimiento" in norm:
            z_rec.append(reg["z"])

    if not z_dem:
        return

    prom_dem = sum(z_dem) / len(z_dem)
    prom_inm = (sum(z_inm) / len(z_inm)) if z_inm else None
    prom_rec = (sum(z_rec) / len(z_rec)) if z_rec else None

    if prom_dem <= -1.33:
        if prom_rec is not None and prom_rec > -1.00:
            hallazgos.append(
                "Perfil mnésico: recuerdo diferido descendido con reconocimiento preservado "
                "(sugiere falla en estrategias de recuperación más que pérdida de almacenamiento)."
            )
        elif prom_inm is not None and prom_inm > -1.00 and prom_rec is not None and prom_rec <= -1.33:
            hallazgos.append(
                "Perfil mnésico: aprendizaje/recuerdo inmediato preservado con descenso en diferido y reconocimiento "
                "(sugiere vulnerabilidad en consolidación/almacenamiento)."
            )
        elif prom_inm is not None and prom_inm <= -1.33:
            hallazgos.append(
                "Perfil mnésico: compromiso desde la fase de recuerdo inmediato y diferido "
                "(sugiere falla primaria de codificación/registro atencional inicial)."
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
            if val >= 70:
                brief_clinico.append(f"{reg['nombre']} (T={val:.0f})")
            elif val >= 65:
                brief_potencial.append(f"{reg['nombre']} (T={val:.0f})")
            elif val >= 60:
                brief_leve.append(f"{reg['nombre']} (T={val:.0f})")

        elif "snap-iv" in norm:
            if "inatencion" in norm and (val >= 15 or (1.67 <= val <= 3.0)):
                alertas_criticas.append(f"SNAP-IV Inatención supera punto de corte clínico ({val:g}).")
            elif ("hiperactividad" in norm or "impulsividad" in norm) and (val >= 16 or (1.67 <= val <= 3.0)):
                alertas_criticas.append(f"SNAP-IV Hiperactividad/Impulsividad supera punto de corte clínico ({val:g}).")

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
