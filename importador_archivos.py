"""Importación determinista de planillas Excel/CSV, fichas Word (.docx) y borradores JSON."""

from __future__ import annotations

import csv
from datetime import date, datetime
import io
import json
import re
from docx import Document
import openpyxl

from catalogo_clinico import (
    CATALOGO_SUBPRUEBAS,
    ESCALA_BRUTO,
    ESCALA_CI,
    ESCALA_ESCALAR,
    ESCALA_PERCENTIL_DIRECTO,
    ESCALA_PERCENTIL_INVERSO,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALA_V_SCALE,
    ESCALA_Z_DIRECTO,
)
from psicometria import _normalizar_texto

_ERRORES_EXCEL = {"#error!", "#n/a", "#div/0!", "#value!", "#ref!", "#name?", "nan", "none"}

# Mapeo de alias comunes en Planilla Modelo hacia subpruebas canónicas del catálogo
_INDICE_CATALOGO: list[tuple[str, str, str, str]] = []
for _bat, _items in CATALOGO_SUBPRUEBAS.items():
    _bat_norm = _normalizar_texto(_bat)
    for _sub_nombre, _esc_def in _items:
        _sub_norm = _normalizar_texto(_sub_nombre)
        _sufijo = _sub_nombre.split(" - ", 1)[-1]
        _sufijo_norm = _normalizar_texto(_sufijo)
        _INDICE_CATALOGO.append((_bat, _bat_norm, _sub_nombre, _sufijo_norm))


def _celda_a_texto(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    return re.sub(r"\s+", " ", str(val)).strip()


def _parsear_numero(val) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    txt = str(val).strip()
    if not txt or txt.lower() in _ERRORES_EXCEL:
        return None
    txt_limpio = txt.replace("%", "").replace('"', "").replace("'", "").strip()
    if "," in txt_limpio and "." not in txt_limpio:
        txt_limpio = txt_limpio.replace(",", ".")
    try:
        return float(txt_limpio)
    except ValueError:
        return None


def _mapear_escala(tipo_str: str, nombre_prueba: str) -> str:
    t = _normalizar_texto(tipo_str)
    n = _normalizar_texto(nombre_prueba)
    if t == "ci":
        return ESCALA_CI
    if t in ("pe", "escalar"):
        return ESCALA_ESCALAR
    if t in ("v-scale", "vscale", "v scale"):
        return ESCALA_V_SCALE
    if t in ("t inv", "t_inv", "t inverso"):
        return ESCALA_T_INVERSO
    if t == "t":
        if any(b in n for b in ("cpt", "nesplora", "brief")):
            return ESCALA_T_INVERSO
        return ESCALA_T_DIRECTO
    if t in ("pc", "percentil"):
        if any(b in n for b in ("nesplora", "cpt")) and any(
            k in n
            for k in (
                "omision",
                "comision",
                "actividad motora",
                "variabilidad",
                "perseveracion",
                "error",
                "tiempo de reaccion",
                "hit rt",
            )
        ):
            return ESCALA_PERCENTIL_INVERSO
        return ESCALA_PERCENTIL_DIRECTO
    if t == "z":
        return ESCALA_Z_DIRECTO
    return ESCALA_BRUTO


def _resolver_nombre_y_bateria(nombre_raw: str, seccion_actual: str) -> tuple[str, str | None]:
    norm_raw = _normalizar_texto(nombre_raw)
    sec_norm = _normalizar_texto(seccion_actual)

    # Normalización rápida de variantes de Planilla Modelo
    reemplazos = {
        "construccion con cubos": "cubos",
        "retencion de digitos": "digitos",
        "clave de numeros": "clave de numeros",
        "memoria de listas, recuerdo libre (tomal)": "recuerdo selectivo de palabras (inmediato)",
        "memoria de listas, recuerdo demorado (tomal)": "recuerdo selectivo de palabras (demorado)",
        "memoria narrativa, recuerdo libre (wraml)": "memoria narrativa (recuerdo inmediato)",
        "memoria narrativa, recuerdo demorado (wraml)": "memoria narrativa (recuerdo demorado)",
        "velocidad de denominacion": "denominacion veloz",
        "fluidez verbal": "generacion de palabras (semantica)",
        "indice de funcionamiento ejecutivo": "indice global de funcion ejecutiva (gec)",
        "indice de regulacion conductual": "indice de regulacion conductual (bri)",
        "planificacion/organizacion": "planificacion y organizacion",
        "cambio": "cambio / flexibilidad",
        "flexibilidad": "cambio / flexibilidad",
        "monitoreo": "monitoreo / supervision",
        "iniciacion": "iniciativa",
        "error estandar del tr (ritmo de respuesta)": "variabilidad / consistencia (hit rt std error)",
        "tiempo de reaccion": "tiempo de reaccion (hit rt)",
    }
    norm_buscado = reemplazos.get(norm_raw, norm_raw)

    # 1. Coincidencia exacta con batería activa en sección
    for bat, bat_norm, sub_nombre, sufijo_norm in _INDICE_CATALOGO:
        if sec_norm and (bat_norm in sec_norm or sec_norm in bat_norm):
            if norm_buscado == sufijo_norm or norm_buscado == _normalizar_texto(sub_nombre):
                return sub_nombre, bat

    # 2. Coincidencia por contenido en cualquier batería cuando nombre_raw incluye prefijo o sigla
    for bat, bat_norm, sub_nombre, sufijo_norm in _INDICE_CATALOGO:
        if norm_buscado == _normalizar_texto(sub_nombre):
            return sub_nombre, bat
        if bat_norm in norm_raw and sufijo_norm in norm_buscado:
            return sub_nombre, bat

    # 3. Coincidencia única por sufijo
    candidatos = [
        (sub_nombre, bat)
        for bat, _bn, sub_nombre, sufijo_norm in _INDICE_CATALOGO
        if norm_buscado == sufijo_norm or (len(norm_buscado) >= 6 and norm_buscado in sufijo_norm)
    ]
    if len(candidatos) == 1:
        return candidatos[0]

    # Si no matchea exacto: priorizar coincidencia explícita de batería en el nombre de la fila
    bat_inferida = None
    for bat in CATALOGO_SUBPRUEBAS:
        if _normalizar_texto(bat) in norm_raw:
            bat_inferida = bat
            break
    if not bat_inferida and sec_norm:
        for bat in CATALOGO_SUBPRUEBAS:
            if _normalizar_texto(bat) in sec_norm:
                bat_inferida = bat
                break
    if not bat_inferida and "prolec" in sec_norm:
        bat_inferida = "PROLEC-R / PROLEC-SE-R"
    elif not bat_inferida and "woodcock" in sec_norm:
        bat_inferida = "Woodcock-Muñoz"
    elif not bat_inferida and "durand" in sec_norm:
        bat_inferida = "Escala Durand"
    elif not bat_inferida and "autoestima" in sec_norm:
        bat_inferida = "Escala de Autoestima"

    return nombre_raw, bat_inferida


def _leer_filas_csv(raw_bytes: bytes) -> list[list[str]]:
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        texto = raw_bytes.decode("utf-8", errors="replace")

    muestra = "\n".join(texto.splitlines()[:10])
    delim = ";" if muestra.count(";") > muestra.count(",") else ","
    reader = csv.reader(io.StringIO(texto), delimiter=delim)
    return [[_celda_a_texto(c) for c in fila[:8]] for fila in reader]


def _leer_filas_xlsx(raw_bytes: bytes) -> list[tuple[str, list[list[str]]]]:
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True, read_only=True)
    hojas: list[tuple[str, list[list[str]]]] = []
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            filas: list[list[str]] = []
            for row in ws.iter_rows(max_col=8, values_only=True):
                filas.append([_celda_a_texto(v) for v in row])
            hojas.append((sheet_name, filas))
    finally:
        wb.close()
    return hojas


def _resumir_hojas_xlsx(hojas: list[tuple[str, list[list[str]]]]) -> list[dict]:
    """Resume cada hoja de un libro .xlsx con paciente, fecha de evaluación y conteo de filas."""
    resumen: list[dict] = []
    for nombre_hoja, filas in hojas:
        paciente = ""
        fecha_eval = ""
        hc = ""
        filas_con_valor = 0
        for fila in filas:
            c0 = fila[0] if len(fila) > 0 else ""
            c1 = fila[1] if len(fila) > 1 else ""
            c2 = fila[2] if len(fila) > 2 else ""
            c3 = fila[3] if len(fila) > 3 else ""
            c0_norm = _normalizar_texto(c0)
            if c0_norm.startswith("paciente") and c1 and not paciente:
                paciente = c1
                continue
            if "fecha de evaluacion" in c0_norm and c1 and not fecha_eval:
                fecha_eval = c1
                continue
            if c0_norm == "hc" and c1 and not hc:
                hc = c1
                continue
            if c0_norm.startswith(
                (
                    "planilla de puntuaciones",
                    "como se usa",
                    "1. ",
                    "2. ",
                    "3. ",
                    "4. ",
                    "5. ",
                    "corte ",
                    "dificultad si",
                    "significativo si",
                )
            ):
                continue
            if any(_parsear_numero(col) is not None for col in (c1, c2, c3)) or (
                any((c1, c2)) and c0_norm not in ("prueba", "subtest", "informante", "escala", "funcion", "area", "")
            ):
                filas_con_valor += 1
        resumen.append(
            {
                "hoja": nombre_hoja,
                "paciente": paciente,
                "fecha_eval": fecha_eval,
                "hc": hc,
                "filas_con_valor": filas_con_valor,
                "tiene_datos": bool(paciente or fecha_eval or hc or filas_con_valor > 0),
            }
        )
    return resumen


def listar_hojas_planilla(raw_bytes: bytes) -> list[dict]:
    """Inspecciona las hojas de un .xlsx y devuelve metadatos clave de cada evaluación."""
    return _resumir_hojas_xlsx(_leer_filas_xlsx(raw_bytes))


def importar_planilla_excel_o_csv(
    raw_bytes: bytes,
    nombre_archivo: str = "",
    hoja_seleccionada: str | None = None,
) -> dict:
    """Importa filiación, pruebas detectadas y puntajes desde Planilla Modelo (.xlsx o .csv)."""
    es_xlsx = nombre_archivo.lower().endswith(".xlsx")
    if es_xlsx:
        hojas = _leer_filas_xlsx(raw_bytes)
        hojas_info = _resumir_hojas_xlsx(hojas)
        hojas_con_datos = [h for h in hojas_info if h["tiene_datos"]]
        if hoja_seleccionada is not None:
            coincidencias = [h for h in hojas if h[0] == hoja_seleccionada]
            if not coincidencias:
                raise ValueError(f"No se encontró la hoja '{hoja_seleccionada}' en el archivo.")
            hojas_a_procesar = coincidencias
        elif len(hojas_con_datos) > 1:
            return {
                "requiere_seleccion_hoja": True,
                "hojas_disponibles": hojas_info,
                "hoja_importada": None,
                "filiacion": {},
                "filas_puntajes": [],
                "pruebas_detectadas": [],
                "texto_extra": "",
                "resumen_importacion": {
                    "hoja": None,
                    "filas_leidas": 0,
                    "filas_importadas": 0,
                    "filas_descartadas": 0,
                    "motivos_descarte": [
                        f"El archivo contiene {len(hojas_con_datos)} hojas con evaluaciones; seleccioná una hoja antes de importar."
                    ],
                },
            }
        elif len(hojas_con_datos) == 1:
            objetivo = hojas_con_datos[0]["hoja"]
            hojas_a_procesar = [h for h in hojas if h[0] == objetivo]
        else:
            hojas_a_procesar = hojas[:1]
    else:
        hojas_a_procesar = [("CSV", _leer_filas_csv(raw_bytes))]
        hojas_info = []

    filiacion: dict[str, str] = {}
    filas_puntajes: list[dict] = []
    pruebas_detectadas: list[str] = []
    notas_extra: list[str] = []
    filas_leidas = 0
    filas_descartadas = 0
    motivos_descarte: list[str] = []
    hoja_importada = hojas_a_procesar[0][0] if hojas_a_procesar else None

    def _registrar_bateria(bat: str | None) -> None:
        if bat and bat in CATALOGO_SUBPRUEBAS and bat not in pruebas_detectadas:
            pruebas_detectadas.append(bat)

    for nombre_hoja, filas in hojas_a_procesar:
        seccion_actual = ""
        modo_especial = ""

        for idx_fila, fila in enumerate(filas, start=1):
            c0 = fila[0] if len(fila) > 0 else ""
            c1 = fila[1] if len(fila) > 1 else ""
            c2 = fila[2] if len(fila) > 2 else ""
            c3 = fila[3] if len(fila) > 3 else ""
            c4 = fila[4] if len(fila) > 4 else ""

            if not any((c0, c1, c2, c3, c4)):
                continue

            c0_norm = _normalizar_texto(c0)

            # Metadatos de filiación en primeras filas
            if c0_norm.startswith("paciente") and c1 and "nombre" not in filiacion:
                filiacion["nombre"] = c1
                continue
            if c0_norm == "hc" and c1 and "hc" not in filiacion:
                filiacion["hc"] = c1
                continue
            if "fecha de nacimiento" in c0_norm and c1 and "fecha_nac" not in filiacion:
                filiacion["fecha_nac"] = c1
                continue
            if "fecha de evaluacion" in c0_norm and c1 and "fecha_eval" not in filiacion:
                filiacion["fecha_eval"] = c1
                continue
            if c0_norm == "edad" and c1 and "edad_texto" not in filiacion:
                filiacion["edad_texto"] = c1
                continue
            if c0_norm == "escolaridad" and c1 and "escolaridad" not in filiacion:
                filiacion["escolaridad"] = c1
                continue

            # Ignorar filas de título general, encabezado de columnas o ayuda
            if c0_norm in ("prueba", "subtest", "informante", "escala", "funcion", "area") or c0_norm.startswith(
                (
                    "planilla de puntuaciones",
                    "como se usa",
                    "1. ",
                    "2. ",
                    "3. ",
                    "4. ",
                    "5. ",
                    "corte ",
                    "dificultad si",
                    "significativo si",
                )
            ):
                continue

            # Solo interpretar una fila como cabecera de sección si NO contiene puntajes ni código de escala
            c1_norm = _normalizar_texto(c1)
            es_escala_en_c1 = c1_norm in (
                "ci",
                "pe",
                "escalar",
                "pc",
                "percentil",
                "t",
                "t inv",
                "t_inv",
                "t inverso",
                "z",
                "v-scale",
                "vscale",
                "v scale",
                "bruto",
                "pb",
            )
            tiene_num = any(_parsear_numero(col) is not None for col in (c1, c2, c3))
            es_cabecera_seccion = not tiene_num and not es_escala_en_c1 and not (
                modo_especial in ("woodcock", "prolec") and (c2 or c3)
            )

            if es_cabecera_seccion:
                if "wisc-v" in c0_norm:
                    seccion_actual, modo_especial = "WISC-V", ""
                    continue
                if "wppsi-iv" in c0_norm:
                    seccion_actual, modo_especial = "WPPSI-IV", ""
                    continue
                if "wais-iv" in c0_norm:
                    seccion_actual, modo_especial = "WAIS-IV", ""
                    continue
                if "lenguaje (nepsy-ii)" in c0_norm:
                    seccion_actual, modo_especial = "NEPSY-II", ""
                    continue
                if "woodcock" in c0_norm:
                    seccion_actual, modo_especial = "Woodcock-Muñoz", "woodcock"
                    continue
                if "prolec" in c0_norm:
                    seccion_actual, modo_especial = "PROLEC-R / PROLEC-SE-R", "prolec"
                    continue
                if c0_norm == "snap-iv":
                    seccion_actual, modo_especial = "SNAP-IV", "snap"
                    continue
                if c0_norm == "brief":
                    seccion_actual, modo_especial = "BRIEF", "brief"
                    continue
                if "escala durand" in c0_norm:
                    seccion_actual, modo_especial = "Escala Durand", "durand"
                    continue
                if "escala de autoestima" in c0_norm:
                    seccion_actual, modo_especial = "Escala de Autoestima", "autoestima"
                    continue
                if "vineland" in c0_norm and "madurez social" in c0_norm:
                    seccion_actual, modo_especial = "Vineland", "vineland_b"
                    continue
                if c0_norm.startswith(
                    (
                        "atencion ",
                        "memoria ",
                        "funciones ejecutivas",
                        "habilidades visoespaciales",
                        "matematica",
                    )
                ):
                    seccion_actual, modo_especial = "", ""
                    continue

            # Ignorar filas de plantilla sin completar (sin ningún valor en B..E)
            if not any((c1, c2, c3, c4)):
                continue

            filas_leidas += 1

            # Procesamiento por modo de sección
            if modo_especial == "woodcock":
                num = _parsear_numero(c1)
                if num is not None or c2 or c3:
                    obs_partes = []
                    if c2:
                        obs_partes.append(f"EE: {c2}")
                    if c3:
                        obs_partes.append(f"GE: {c3}")
                    sub_nom, bat = _resolver_nombre_y_bateria(c0, seccion_actual)
                    _registrar_bateria(bat)
                    filas_puntajes.append(
                        {
                            "Dominio / Prueba / Subtest": sub_nom,
                            "Puntaje": num,
                            "Tipo de Escala": ESCALA_BRUTO,
                            "Observación": " | ".join(obs_partes),
                        }
                    )
                else:
                    filas_descartadas += 1
                    motivos_descarte.append(f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): sin valor válido para Woodcock-Muñoz.")
                continue

            if modo_especial == "prolec":
                num = _parsear_numero(c1)
                if num is not None or c2 or c3:
                    obs_partes = []
                    if c2:
                        obs_partes.append(f"Categoría: {c2}")
                    if c3:
                        obs_partes.append(f"Velocidad: {c3}")
                    sub_nom, bat = _resolver_nombre_y_bateria(c0, seccion_actual)
                    _registrar_bateria(bat)
                    filas_puntajes.append(
                        {
                            "Dominio / Prueba / Subtest": sub_nom,
                            "Puntaje": num,
                            "Tipo de Escala": ESCALA_BRUTO,
                            "Observación": " | ".join(obs_partes),
                        }
                    )
                else:
                    filas_descartadas += 1
                    motivos_descarte.append(f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): sin valor válido para PROLEC.")
                continue

            if modo_especial == "snap":
                desat = _parsear_numero(c1)
                hi = _parsear_numero(c2)
                if desat is not None or hi is not None:
                    _registrar_bateria("SNAP-IV")
                    notas_extra.append(f"SNAP-IV ({c0}): Desatención={c1 or '-'}, H/I={c2 or '-'}")
                    if desat is not None:
                        filas_puntajes.append(
                            {
                                "Dominio / Prueba / Subtest": f"SNAP-IV - Indicadores de Inatención ({c0})",
                                "Puntaje": desat,
                                "Tipo de Escala": ESCALA_BRUTO,
                                "Observación": f"Informante: {c0}",
                            }
                        )
                    if hi is not None:
                        filas_puntajes.append(
                            {
                                "Dominio / Prueba / Subtest": f"SNAP-IV - Indicadores de Hiperactividad / Impulsividad ({c0})",
                                "Puntaje": hi,
                                "Tipo de Escala": ESCALA_BRUTO,
                                "Observación": f"Informante: {c0}",
                            }
                        )
                else:
                    filas_descartadas += 1
                    motivos_descarte.append(
                        f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): valores SNAP-IV no numéricos ({c1!r}, {c2!r})."
                    )
                continue

            if modo_especial == "brief":
                t_madre = _parsear_numero(c1)
                t_padre = _parsear_numero(c2)
                if t_madre is not None or t_padre is not None:
                    _registrar_bateria("BRIEF")
                    sub_nom, _ = _resolver_nombre_y_bateria(c0, "BRIEF")
                    if t_madre is not None:
                        filas_puntajes.append(
                            {
                                "Dominio / Prueba / Subtest": f"{sub_nom} (Madre)",
                                "Puntaje": t_madre,
                                "Tipo de Escala": ESCALA_T_INVERSO,
                                "Observación": "Informante: Madre",
                            }
                        )
                    if t_padre is not None:
                        filas_puntajes.append(
                            {
                                "Dominio / Prueba / Subtest": f"{sub_nom} (Padre)",
                                "Puntaje": t_padre,
                                "Tipo de Escala": ESCALA_T_INVERSO,
                                "Observación": "Informante: Padre",
                            }
                        )
                    notas_extra.append(f"BRIEF {sub_nom}: Madre={c1 or '-'}, Padre={c2 or '-'}")
                else:
                    filas_descartadas += 1
                    motivos_descarte.append(
                        f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): valores BRIEF no numéricos ({c1!r}, {c2!r})."
                    )
                continue

            if modo_especial in ("durand", "autoestima"):
                num = _parsear_numero(c1)
                if num is not None or c2:
                    sub_nom, bat = _resolver_nombre_y_bateria(c0, seccion_actual)
                    _registrar_bateria(bat)
                    filas_puntajes.append(
                        {
                            "Dominio / Prueba / Subtest": sub_nom,
                            "Puntaje": num,
                            "Tipo de Escala": ESCALA_BRUTO,
                            "Observación": c2,
                        }
                    )
                else:
                    filas_descartadas += 1
                    motivos_descarte.append(f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): valor inválido o vacío.")
                continue

            if modo_especial == "vineland_b":
                if c1:
                    _registrar_bateria("Vineland")
                    notas_extra.append(f"Vineland Forma B — {c0}: {c1}")
                else:
                    filas_descartadas += 1
                    motivos_descarte.append(f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): sin dato en Vineland Forma B.")
                continue

            # Filas estándar de tabla (Prueba, Tipo, Puntaje)
            num_c2 = _parsear_numero(c2)
            if c1 and num_c2 is not None:
                sub_nom, bat = _resolver_nombre_y_bateria(c0, seccion_actual)
                _registrar_bateria(bat)
                escala = _mapear_escala(c1, sub_nom)
                filas_puntajes.append(
                    {
                        "Dominio / Prueba / Subtest": sub_nom,
                        "Puntaje": num_c2,
                        "Tipo de Escala": escala,
                        "Observación": c3,
                    }
                )
            else:
                filas_descartadas += 1
                motivos_descarte.append(
                    f"Hoja '{nombre_hoja}' fila {idx_fila} ('{c0}'): formato no reconocido o puntaje no numérico (Tipo={c1!r}, Puntaje={c2!r})."
                )

    return {
        "requiere_seleccion_hoja": False,
        "hojas_disponibles": hojas_info,
        "hoja_importada": hoja_importada,
        "filiacion": filiacion,
        "filas_puntajes": filas_puntajes,
        "pruebas_detectadas": pruebas_detectadas,
        "texto_extra": "\n".join(notas_extra),
        "resumen_importacion": {
            "hoja": hoja_importada,
            "filas_leidas": filas_leidas,
            "filas_importadas": len(filas_puntajes),
            "filas_descartadas": filas_descartadas,
            "motivos_descarte": motivos_descarte,
        },
    }


def importar_ficha_carga_docx(raw_bytes: bytes) -> dict:
    """Extrae datos de filiación, motivo de consulta y notas de una Ficha de carga (.docx)."""
    doc = Document(io.BytesIO(raw_bytes))
    filiacion: dict[str, str] = {}
    motivo: dict[str, str] = {}
    lineas_extra: list[str] = []

    def _procesar_par(clave_raw: str, val_raw: str) -> None:
        clave = _normalizar_texto(clave_raw)
        val = val_raw.strip()
        if not val:
            return
        if "apellido y nombre" in clave:
            filiacion["nombre"] = val
        elif clave in ("hc", "dni / hc", "dni"):
            filiacion["hc"] = val
        elif "fecha de nacimiento" in clave:
            filiacion["fecha_nac"] = val
        elif "fecha de evaluacion" in clave:
            filiacion["fecha_eval"] = val
        elif "escolaridad" in clave:
            filiacion["escolaridad"] = val
        elif "nacionalidad" in clave:
            filiacion["nacionalidad"] = val
        elif "preferencia manual" in clave:
            filiacion["preferencia"] = val
        elif "medico solicitante" in clave or "solicitante" in clave:
            filiacion["medico"] = val
        elif "acompanante" in clave:
            filiacion["acompanante"] = val
        elif "quien deriva" in clave or "que observan" in clave:
            prev = motivo.get("quien_deriva", "")
            motivo["quien_deriva"] = f"{prev}\n{val}".strip() if prev else val
        elif "diagnosticos" in clave or "evaluaciones anteriores" in clave:
            prev = motivo.get("antecedentes", "")
            motivo["antecedentes"] = f"{prev}\n{val}".strip() if prev else val
        else:
            lineas_extra.append(f"{clave_raw.strip()}: {val}")

    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            continue
        if ":" in txt:
            k, v = txt.split(":", 1)
            _procesar_par(k, v)
        else:
            lineas_extra.append(txt)

    for table in doc.tables:
        for row in table.rows:
            celdas = [re.sub(r"\s+", " ", c.text).strip() for c in row.cells]
            celdas_no_vacias = [c for c in celdas if c]
            if not celdas_no_vacias:
                continue
            if len(celdas) >= 2 and celdas[0] and celdas[1]:
                _procesar_par(celdas[0], celdas[1])
            else:
                lineas_extra.append(" | ".join(celdas_no_vacias))

    return {
        "filiacion": filiacion,
        "motivo": motivo,
        "texto_extra": "\n".join(lineas_extra),
    }


def extraer_texto_xlsx_compacto(raw_bytes: bytes, nombre_archivo: str = "planilla.xlsx") -> str:
    """Convierte un Excel (.xlsx) a texto compacto omitiendo filas vacías y columnas de referencia."""
    hojas = _leer_filas_xlsx(raw_bytes)
    partes = [f"--- Planilla Excel adjunta ({nombre_archivo}) ---"]
    for nombre_hoja, filas in hojas:
        partes.append(f"[Hoja: {nombre_hoja}]")
        for fila in filas:
            recortada = [c for c in fila if c]
            if not recortada:
                continue
            partes.append(" | ".join(c for c in fila[:6] if c))
    return "\n".join(partes)


def extraer_texto_docx_compacto(raw_bytes: bytes, nombre_archivo: str = "documento.docx") -> str:
    """Extrae el texto no vacío de párrafos y tablas de un .docx para adjuntar al prompt."""
    doc = Document(io.BytesIO(raw_bytes))
    partes = [f"--- Documento Word adjunto ({nombre_archivo}) ---"]
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            partes.append(t)
    for table in doc.tables:
        for row in table.rows:
            celdas = [re.sub(r"\s+", " ", c.text).strip() for c in row.cells]
            if any(celdas):
                partes.append(" | ".join(c for c in celdas if c))
    return "\n".join(partes)


def exportar_borrador_json(estado: dict) -> str:
    """Serializa el estado del caso clínico a JSON UTF-8."""
    payload = {"schema_version": 2, **estado}
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def importar_borrador_json(raw_bytes: bytes) -> dict:
    """Deserializa y valida un borrador JSON de caso clínico."""
    data = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("El archivo JSON no contiene un objeto de borrador válido.")
    return data
