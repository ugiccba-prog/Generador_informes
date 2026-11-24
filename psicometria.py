"""Cálculos psicométricos, baremos Z, percentiles, edad exacta y utilidades de archivo."""

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
    ESCALA_PERCENTIL,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALA_Z_DIRECTO,
)

COLUMNAS_PROCESADAS = [
    "Dominio / Prueba / Subtest",
    "Puntaje Obtenido",
    "Escala",
    "Puntaje Z",
    "Rango Clínico",
    "Notas",
]

_NORMAL_DIST = statistics.NormalDist(0.0, 1.0)


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


def calcular_z_y_rango(valor: float, tipo_escala: str) -> tuple[float | None, str]:
    """Convierte un puntaje bruto/estándar/percentil a puntaje Z y rango clínico."""
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
    elif tipo_escala == ESCALA_T_DIRECTO:
        z = (val - 50.0) / 10.0
    elif tipo_escala == ESCALA_T_INVERSO:
        z = (50.0 - val) / 10.0
    elif tipo_escala == ESCALA_PERCENTIL:
        if val < 0.01 or val > 99.99:
            return None, "Percentil fuera de rango (0,01 a 99,99)"
        z = _NORMAL_DIST.inv_cdf(val / 100.0)
    elif tipo_escala == ESCALA_Z_DIRECTO:
        z = val
    else:
        return None, "Escala no reconocida"

    z_round = round(z, 2)
    if z_round == 0:
        z_round = 0.0

    return z_round, clasificar_z(z_round)


def _normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return sin_tildes.strip().lower()


def categoria_color_rango(rango: str) -> str:
    """Mapea un rango clínico a una categoría semántica para estilos en UI y Word."""
    if not rango:
        return "cualitativo"

    norm = _normalizar_texto(rango)
    if "fuera de rango" in norm or "invalido" in norm or "no reconocida" in norm:
        return "cualitativo"
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
    return str(valor).strip()


def revisar_carga_puntajes(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Detecta resultados que se perderían o cuya escala necesita revisión."""
    errores = []
    avisos = []
    vistas = {}
    for fila, (_, datos) in enumerate(df.iterrows(), start=1):
        nombre = _texto_limpio(datos.get("Dominio / Prueba / Subtest"))
        puntaje = datos.get("Puntaje")
        nota = _texto_limpio(datos.get("Observación"))
        tiene_puntaje = puntaje is not None and pd.notna(puntaje)
        if not tiene_puntaje and not nota:
            continue
        if not nombre:
            errores.append(f"Fila {fila}: completá el nombre de la prueba o subprueba.")
            continue
        clave = _normalizar_texto(nombre)
        if clave in vistas:
            avisos.append(
                f"Filas {vistas[clave]} y {fila}: identificá cada registro si corresponden a condiciones o tomas distintas."
            )
        else:
            vistas[clave] = fila
        if not tiene_puntaje:
            continue
        escala = _texto_limpio(datos.get("Tipo de Escala"))
        try:
            valor = float(puntaje)
        except (TypeError, ValueError):
            valor = math.nan
        if not math.isfinite(valor):
            errores.append(f"Fila {fila}: ingresá un puntaje numérico válido.")
        elif escala != ESCALA_BRUTO:
            z, motivo = calcular_z_y_rango(valor, escala)
            if z is None:
                errores.append(f"Fila {fila}: {motivo if escala else 'Elegí la escala del puntaje informado'}.")
    return errores, avisos


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
            z_val, r_val = calcular_z_y_rango(puntaje_float, escala_item)
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
