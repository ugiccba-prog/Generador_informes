"""Cálculos psicométricos, baremos Z, percentiles, métricas derivadas y utilidades."""

from __future__ import annotations

from datetime import date
import math
import re
import statistics
import unicodedata
import pandas as pd

from catalogo_clinico import (
    ESCALA_BRUTO,
    ESCALA_CI,
    ESCALA_ESCALAR,
    ESCALA_PERCENTIL_DIRECTO,
    ESCALA_PERCENTIL_INVERSO,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALA_V_SCALE,
    ESCALA_Z_DIRECTO,
    VINELAND_FORMA_B_CATEGORIAS,
)

COLUMNAS_PROCESADAS = [
    "Dominio / Prueba / Subtest",
    "Puntaje Obtenido",
    "Escala",
    "Puntaje Z",
    "Rango Clínico",
    "Notas",
]

TERCIOS_GRILLA_Z = (
    -3.0,
    -2.67,
    -2.33,
    -2.0,
    -1.67,
    -1.33,
    -1.0,
    -0.67,
    -0.33,
    0.0,
    0.33,
    0.67,
    1.0,
    1.33,
    1.67,
    2.0,
    2.33,
    2.67,
    3.0,
)

_NORMAL_DIST = statistics.NormalDist(0.0, 1.0)


def _normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def es_hit_rt(nombre_subtest: str) -> bool:
    """Detecta si el subtest mide velocidad de reacción (Hit RT / TR), excluyendo variabilidad."""
    norm = _normalizar_texto(nombre_subtest)
    if not norm:
        return False
    if "variabilidad" in norm or "std error" in norm or "error estandar" in norm:
        return False
    return "hit rt" in norm or "tiempo de reaccion" in norm


def clasificar_z(z: float) -> str:
    """Clasifica un puntaje Z en 9 franjas simétricas continuas y monótonas."""
    z_val = round(float(z), 2)
    if z_val == 0:
        z_val = 0.0

    if z_val <= -2.33:
        return "Déficit"
    if z_val < -2.00:
        return "Limítrofe (Dificultad / Déficit)"
    if z_val <= -1.33:
        return "Dificultad"
    if z_val < -1.00:
        return "Normal (Tendencia baja)"
    if z_val <= 1.00:
        return "Normal"
    if z_val < 1.33:
        return "Normal (Tendencia alta)"
    if z_val <= 2.00:
        return "Normal Alto"
    if z_val < 2.33:
        return "Normal Alto (Tendencia superior)"
    return "Superior"


def redondear_z_a_tercio(z: float) -> float:
    """Ubica un puntaje Z en el tercio más cercano dentro de la grilla [-3, +3]."""
    z_clamp = max(-3.0, min(3.0, float(z)))
    return min(TERCIOS_GRILLA_Z, key=lambda t: (abs(t - z_clamp), abs(t)))


def calcular_z_y_rango(
    valor: float,
    tipo_escala: str,
    nombre_subtest: str = "",
) -> tuple[float | None, str]:
    """Convierte un puntaje estándar, percentil o v-scale a puntaje Z y rango clínico."""
    if tipo_escala == ESCALA_BRUTO:
        return None, "Puntaje Bruto / Cualitativo"

    try:
        val = float(valor)
    except (TypeError, ValueError):
        return None, "Valor inválido"

    if not math.isfinite(val):
        return None, "Valor inválido"

    if tipo_escala == ESCALA_CI:
        z = (val - 100.0) / 15.0
    elif tipo_escala == ESCALA_ESCALAR:
        z = (val - 10.0) / 3.0
    elif tipo_escala == ESCALA_V_SCALE:
        z = (val - 15.0) / 3.0
    elif tipo_escala == ESCALA_T_DIRECTO:
        z = (val - 50.0) / 10.0
    elif tipo_escala == ESCALA_T_INVERSO:
        z = (50.0 - val) / 10.0
    elif tipo_escala in (ESCALA_PERCENTIL_DIRECTO, "Percentil (Pc 1 a 99)"):
        if val < 0.01 or val > 99.99:
            return None, "Percentil fuera de rango (1-99)"
        z = _NORMAL_DIST.inv_cdf(val / 100.0)
    elif tipo_escala == ESCALA_PERCENTIL_INVERSO:
        if val < 0.01 or val > 99.99:
            return None, "Percentil fuera de rango (1-99)"
        z = _NORMAL_DIST.inv_cdf((100.0 - val) / 100.0)
    elif tipo_escala == ESCALA_Z_DIRECTO:
        z = val
    else:
        return None, "Escala no reconocida"

    z_round = round(z, 2)
    if z_round == 0:
        z_round = 0.0

    # Regla clínica bidireccional: Hit RT / TR demasiado rápido (< T 40 o Pc inv <= 15) indica estilo impulsivo
    if es_hit_rt(nombre_subtest):
        if (tipo_escala == ESCALA_T_INVERSO and val < 40.0) or (
            tipo_escala == ESCALA_PERCENTIL_INVERSO and val <= 15.0
        ):
            return z_round, "Atípico rápido (estilo impulsivo)"

    return z_round, clasificar_z(z_round)


def categoria_color_rango(rango: str) -> str:
    """Mapea un rango clínico a una categoría semántica para estilos en UI y Word."""
    if not rango:
        return "cualitativo"

    norm = _normalizar_texto(rango)
    if "fuera de rango" in norm or "invalido" in norm or "no reconocida" in norm:
        return "cualitativo"
    if "atipico rapido" in norm or "estilo impulsivo" in norm:
        return "dificultad"
    if "limitrofe" in norm or ("dificultad" in norm and "deficit" in norm):
        return "limitrofe_bajo"
    if "deficit" in norm:
        return "deficit"
    if "dificultad" in norm:
        return "dificultad"
    if "tendencia baja" in norm:
        return "tendencia_baja"
    if "normal alto" in norm or "tendencia superior" in norm:
        return "normal_alto"
    if "tendencia alta" in norm:
        return "tendencia_alta"
    if "superior" in norm:
        return "superior"
    if "normal" in norm:
        return "normal"
    return "cualitativo"


def formatear_puntaje(valor: float) -> str:
    """Formatea puntajes enteros sin '.00' y decimales sin ceros redundantes."""
    num = float(valor)
    if not math.isfinite(num):
        return "-"
    if num.is_integer():
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _texto_limpio(valor) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip()


def procesar_tabla_puntajes(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte las filas cargadas en una grilla procesada con Z y rango clínico."""
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNAS_PROCESADAS)

    filas_procesadas = []
    for _, row in df.iterrows():
        nombre_item = _texto_limpio(row.get("Dominio / Prueba / Subtest"))
        puntaje_raw = row.get("Puntaje")
        escala_item = _texto_limpio(row.get("Tipo de Escala"))
        nota_item = _texto_limpio(row.get("Observación"))

        tiene_puntaje = puntaje_raw is not None and pd.notna(puntaje_raw)
        if not nombre_item or (not tiene_puntaje and not nota_item):
            continue

        if tiene_puntaje:
            try:
                puntaje_float = float(puntaje_raw)
            except (TypeError, ValueError):
                tiene_puntaje = False
                puntaje_float = math.nan
        else:
            puntaje_float = math.nan

        if tiene_puntaje and not math.isfinite(puntaje_float):
            tiene_puntaje = False

        if tiene_puntaje and escala_item:
            z_val, r_val = calcular_z_y_rango(
                puntaje_float,
                escala_item,
                nombre_subtest=nombre_item,
            )
            z_str = f"{z_val:+.2f}" if z_val is not None else "N/A"
            puntaje_str = formatear_puntaje(puntaje_float)
        elif tiene_puntaje:
            z_str = "N/A"
            r_val = "Escala no especificada"
            puntaje_str = formatear_puntaje(puntaje_float)
        else:
            z_str = "N/A"
            r_val = "Cualitativo / Ver Notas"
            puntaje_str = "-"

        filas_procesadas.append(
            {
                "Dominio / Prueba / Subtest": nombre_item,
                "Puntaje Obtenido": puntaje_str,
                "Escala": escala_item or "-",
                "Puntaje Z": z_str,
                "Rango Clínico": r_val,
                "Notas": nota_item,
            }
        )

    return pd.DataFrame(filas_procesadas, columns=COLUMNAS_PROCESADAS)


def calcular_stroop_golden(p: float, c: float, pc: float) -> dict | None:
    """Calcula PC' predicho y puntaje de interferencia según fórmula de Golden."""
    if p is None or c is None or pc is None or p <= 0 or c <= 0 or pc < 0:
        return None
    pc_prima = round((p * c) / (p + c), 2)
    interferencia = round(pc - pc_prima, 2)
    return {
        "pc_prima": pc_prima,
        "interferencia": interferencia,
    }


def calcular_tmt_metricas(tiempo_a: float, tiempo_b: float) -> dict | None:
    """Calcula diferencia B-A y ratio B/A para aislar flexibilidad ejecutiva en TMT."""
    if tiempo_a is None or tiempo_b is None or tiempo_a <= 0 or tiempo_b <= 0:
        return None
    ratio = round(tiempo_b / tiempo_a, 2)
    return {
        "diferencia_b_a": round(tiempo_b - tiempo_a, 2),
        "ratio_b_a": ratio,
        "alerta_ejecutiva": ratio > 3.0,
    }


def calcular_ravlt_metricas(
    ensayos_a: list[float],
    b1: float | None = None,
    a6: float | None = None,
    a7: float | None = None,
    rec: float | None = None,
) -> dict | None:
    """Calcula suma A1-A5, ganancia de aprendizaje, pérdida por interferencia y retención."""
    if not ensayos_a or len(ensayos_a) < 5:
        return None
    total = round(sum(float(x) for x in ensayos_a[:5]), 2)
    a1 = float(ensayos_a[0])
    a5 = float(ensayos_a[4])
    res = {
        "total_a1_a5": total,
        "ganancia_aprendizaje": round(a5 - a1, 2),
        "b1": b1,
        "a6": a6,
        "a7": a7,
        "reconocimiento": rec,
        "perdida_interferencia": round(a5 - float(a6), 2) if a6 is not None else None,
        "retencion_pct": round((float(a7) / a5) * 100.0, 1) if (a7 is not None and a5 > 0) else None,
    }
    return res


def calcular_vineland_forma_b(
    edad_social_anos: float,
    edad_cronologica_anos: float,
) -> dict | None:
    """Calcula el Cociente Social (CS) y la clasificación de Vineland Forma B."""
    if (
        edad_social_anos is None
        or edad_cronologica_anos is None
        or edad_social_anos <= 0
        or edad_cronologica_anos <= 0
    ):
        return None

    cs = round((float(edad_social_anos) / float(edad_cronologica_anos)) * 100.0, 1)
    categoria = "Sin clasificar"
    for minimo, maximo, nombre_cat in VINELAND_FORMA_B_CATEGORIAS:
        if minimo <= cs <= maximo:
            categoria = nombre_cat
            break
    if cs >= 130:
        categoria = "Muy superior"
    return {
        "cociente_social": cs,
        "categoria": categoria,
    }


def calcular_edad_exacta(fecha_nac: date, fecha_eval: date) -> tuple[int, int] | None:
    """Calcula años y meses cumplidos exactos entre nacimiento y evaluación."""
    if fecha_nac is None or fecha_eval is None or fecha_eval < fecha_nac:
        return None

    anos = fecha_eval.year - fecha_nac.year
    meses = fecha_eval.month - fecha_nac.month
    if fecha_eval.day < fecha_nac.day:
        meses -= 1
    if meses < 0:
        anos -= 1
        meses += 12

    return anos, meses


def formatear_edad(anos: int, meses: int) -> str:
    """Formatea años y meses cumplidos en español natural."""
    txt_anos = f"{anos} año" if anos == 1 else f"{anos} años"
    txt_meses = f"{meses} mes" if meses == 1 else f"{meses} meses"

    if anos == 0:
        return txt_meses
    if meses == 0:
        return txt_anos
    return f"{txt_anos}, {txt_meses}"


def sanitizar_nombre_archivo(nombre: str, prefijo: str = "Informe") -> str:
    """Genera un nombre de archivo seguro a partir del nombre del paciente."""
    limpio = re.sub(r"[^\w\-]+", "_", (nombre or "").strip(), flags=re.UNICODE).strip("_")
    if not limpio:
        limpio = "Paciente"
    return f"{prefijo}_{limpio}"
