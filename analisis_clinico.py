"""Indicadores deterministas para revisar fuentes y resultados antes de redactar."""

from collections import Counter
from dataclasses import dataclass
from math import floor, isfinite
import re

from catalogo_clinico import (
    CATALOGO_SUBPRUEBAS, ESCALA_BRUTO, ESCALA_CI, ESCALA_SEGUNDOS, ESCALA_T_INVERSO, ESCALA_T_REACCION,
    ESCALA_T_DIRECTO, ESCALA_ESCALAR, ESCALA_Z_DIRECTO, ESCALA_PERCENTIL_DIRECTO,
    ESCALA_PERCENTIL_LEGADO,
)
from psicometria import calcular_z_y_rango


@dataclass(frozen=True)
class Indicador:
    prueba: str
    detalle: str


@dataclass(frozen=True)
class Resultado:
    nombre: str
    escala: str
    valor: float | None
    nota: str


MESES_WECHSLER = {"WPPSI-IV": (30, 91), "WISC-V": (72, 203), "WAIS-IV": (192, 1091)}
PRIMARIOS = {
    "WPPSI-IV": ("ICV", "IVE", "IRF", "IMT", "IVP"),
    "WISC-V": ("ICV", "IVE", "IRF", "IMT", "IVP"),
    "WAIS-IV": ("ICV", "IRP", "IMT", "IVP"),
}
MEDIDAS_MEMORIA = {
    "RAVLT": ("Total Aprendizaje (Ensayos A1-A5)", "Recuerdo Diferido (A7)", "Reconocimiento"),
    "TOMAL": ("Recuerdo Selectivo de Palabras (Inmediato)", "Recuerdo Selectivo de Palabras (Demorado)",
              "Reconocimiento de Palabras (si figura en la fuente)"),
    "WRAML": ("Memoria Narrativa (Recuerdo Inmediato)", "Memoria Narrativa (Recuerdo Demorado)", "Reconocimiento Narrativo"),
    "Figura Compleja de Rey": ("Memoria Inmediata (3 min)", "Memoria Diferida (30 min)", "Reconocimiento"),
}
TABLA_SOCIAL_MEMORIA = (
    (0, "Rango social profundo"),
    (21, "Rango social severo"),
    (36, "Rango social moderado"),
    (52, "Rango social leve"),
    (70, "Fronterizo"),
    (80, "Normal inferior"),
    (90, "Normal promedio"),
    (110, "Normal alto"),
    (120, "Superior"),
    (130, "Muy superior"),
)
AREAS_AUTOESTIMA = {
    "Autoestima - Académica (Planilla Memoria)",
    "Autoestima - Corporal (Planilla Memoria)",
    "Autoestima - Familiar (Planilla Memoria)",
    "Autoestima - Social (Planilla Memoria)",
}
NOMBRES_BRIEF2 = {nombre for nombre, _ in CATALOGO_SUBPRUEBAS["BRIEF-2"]}
ESCALAS_MEMORIA = {
    ESCALA_CI, ESCALA_ESCALAR, ESCALA_Z_DIRECTO, ESCALA_T_DIRECTO, ESCALA_PERCENTIL_DIRECTO,
    ESCALA_PERCENTIL_LEGADO,
}


def _cargar_resultados(filas):
    resultados = []
    for fila in filas:
        nombre = fila.get("Dominio / Prueba / Subtest")
        if not isinstance(nombre, str) or not nombre.strip():
            continue
        nota = fila.get("Observación")
        escala = fila.get("Tipo de Escala")
        try:
            valor = float(fila.get("Puntaje"))
        except (ValueError, TypeError):
            valor = float("nan")
        if not isfinite(valor) and not (isinstance(nota, str) and nota.strip()):
            continue
        resultados.append(Resultado(
            nombre.strip(), escala if isinstance(escala, str) else "",
            valor if isfinite(valor) else None, nota.strip() if isinstance(nota, str) else "",
        ))
    cuentas = Counter(r.nombre for r in resultados)
    return {r.nombre: r for r in resultados if cuentas[r.nombre] == 1}


def _valor(datos, nombre, escalas):
    registro = datos.get(nombre)
    return registro.valor if registro and registro.escala in escalas else None


def _wechsler(datos, pruebas, edad):
    for prueba, (minimo, maximo) in MESES_WECHSLER.items():
        filas = [r for r in datos.values() if r.nombre.startswith(prueba + " - ") and r.escala == ESCALA_CI]
        if filas or prueba in pruebas:
            if edad is None:
                yield Indicador(prueba, "Rango etario pendiente de verificar. Cargá ambas fechas.")
            elif not minimo <= edad <= maximo:
                yield Indicador(prueba, "La edad queda fuera del rango de referencia de esta edición. Verificá la adaptación utilizada.")
        indices = {}
        for fila in filas:
            sigla = re.search(r"\(([A-Z]+)\)$", fila.nombre)
            if sigla and fila.valor is not None:
                indices[sigla[1]] = fila.valor
        esperados = PRIMARIOS[prueba]
        if prueba == "WPPSI-IV" and edad is not None and 30 <= edad < 48:
            esperados = ("ICV", "IVE", "IMT")
        primarios = {k: indices[k] for k in esperados if k in indices}
        if len(primarios) >= 2:
            bajo = min(primarios, key=primarios.get)
            alto = max(primarios, key=primarios.get)
            brecha = primarios[alto] - primarios[bajo]
            cobertura = f"{len(primarios)}/{len(esperados)} índices primarios cargados"
            detalle = f"Amplitud {brecha:g} puntos ({alto} {primarios[alto]:g}; {bajo} {primarios[bajo]:g}; {cobertura})."
            if brecha >= 23:
                detalle += " Alcanza la señal de revisión de 23 puntos. Consultá valor crítico y tasa base en el manual antes de interpretar el CIT."
            yield Indicador(prueba, detalle)
        if "ICG" in indices:
            for sigla in ("CIT", "ICC", "IMT", "IVP"):
                if sigla not in indices:
                    continue
                diferencia = indices["ICG"] - indices[sigla]
                detalle = f"ICG menos {sigla}: {diferencia:+g} puntos."
                if sigla == "ICC" and diferencia >= 12:
                    detalle += " Brecha descriptiva para revisar con las tablas de la edición y tasa base correspondiente."
                yield Indicador(prueba, detalle)


def _atencion(datos):
    series = {
        "CPT-II": ("Tiempo de Reacción (Hit RT)", "Omisiones (Inatención)", "Comisiones (Impulsividad)"),
        "CPT-3": ("Tiempo de Reacción (Hit RT)", "Omisiones (T)", "Comisiones (T)"),
        "Nesplora Aula": ("Tiempo de Reacción (TR)", "Omisiones Totales", "Comisiones Totales"),
    }
    for prueba, (tr, om, co) in series.items():
        reaccion = _valor(datos, f"{prueba} - {tr}", (ESCALA_T_REACCION, ESCALA_T_INVERSO))
        omisiones = _valor(datos, f"{prueba} - {om}", (ESCALA_T_INVERSO,))
        comisiones = _valor(datos, f"{prueba} - {co}", (ESCALA_T_INVERSO,))
        if reaccion is not None and reaccion < 40:
            detalle = f"Tiempo de reacción atípicamente rápido (T {reaccion:g})."
            if comisiones is not None and comisiones >= 60:
                detalle += f" Coincide con comisiones elevadas (T {comisiones:g}). Revisá el equilibrio entre velocidad y precisión."
            yield Indicador(prueba, detalle)
        if reaccion is not None and reaccion >= 60:
            yield Indicador(prueba, f"Tiempo de reacción lento (T {reaccion:g}). Revisá junto con los errores y la conducta observada.")
        if omisiones is not None and comisiones is not None and omisiones >= 65 and comisiones <= 45:
            yield Indicador(prueba, f"Omisiones T {omisiones:g} y comisiones T {comisiones:g}. Revisá frecuencia de respuesta y validez antes de interpretar la baja tasa de comisiones.")


def _memoria(datos):
    for prueba, medidas in MEDIDAS_MEMORIA.items():
        zs = []
        for medida in medidas:
            fila = datos.get(f"{prueba} - {medida}")
            z = None
            if fila and fila.valor is not None and fila.escala in ESCALAS_MEMORIA:
                z, _ = calcular_z_y_rango(fila.valor, fila.escala)
            zs.append(z)
        inmediato, demorado, reconocimiento = zs
        if demorado is None or reconocimiento is None or demorado > -1.33:
            continue
        if reconocimiento >= -1:
            hipotesis = "revisar la hipótesis de dificultad de recuperación"
        elif reconocimiento <= -1.33 and inmediato is not None and inmediato <= -1.33:
            hipotesis = "revisar la hipótesis de dificultad de codificación o adquisición inicial"
        elif reconocimiento <= -1.33 and inmediato is not None and inmediato >= -1:
            hipotesis = "revisar la hipótesis de dificultad de retención"
        else:
            continue
        medidas_z = [f"{etiqueta} Z {z:+.2f}" for etiqueta, z in zip(("inmediato", "demorado", "reconocimiento"), zs) if z is not None]
        yield Indicador(prueba, f"{', '.join(medidas_z)}. Patrón para {hipotesis}. Cotejá la misma tarea, el baremo y los errores de reconocimiento.")


def _derivados(datos, edad):
    p, c, pc = [_valor(datos, f"Stroop Golden - {m} bruto", (ESCALA_BRUTO,)) for m in ("P", "C", "PC")]
    if all(v is not None and v >= 0 for v in (p, c, pc)) and p + c > 0:
        esperado = p * c / (p + c)
        yield Indicador("Stroop Golden", f"PC esperado {esperado:.2f}; interferencia bruta {pc - esperado:+.2f}. Verificá las correcciones de la edición.")
    a, b = [_valor(datos, f"Trail Making Test - Parte {m} (segundos)", (ESCALA_SEGUNDOS,)) for m in ("A", "B")]
    if a is not None and b is not None and a > 0 and b > 0:
        relacion = b / a
        detalle = f"B/A {relacion:.2f}; B−A {b - a:+.2f} s."
        if relacion > 3:
            detalle += " Supera la referencia descriptiva de 3,0. Contrastá con edad, escolaridad y norma local."
        yield Indicador("TMT", detalle)
    social = _valor(datos, "Vineland Forma B - Edad social (meses)", (ESCALA_BRUTO,))
    if social is not None and social >= 0 and edad is not None and edad > 0:
        directo = social / edad * 100
        cociente_planilla = floor(social / min(edad, 300) * 100 + 0.5)
        categoria = next(categoria for desde, categoria in reversed(TABLA_SOCIAL_MEMORIA) if cociente_planilla >= desde)
        yield Indicador(
            "Vineland Forma B",
            f"Cociente social sin tope {directo:.2f}. Planilla Memoria (edad hasta 25 años): "
            f"{cociente_planilla}, {categoria.lower()} en la clasificación histórica. Verificá edición y fuente.",
        )


def _cuestionarios(datos):
    for fila in datos.values():
        n, v, e = fila.nombre, fila.valor, fila.escala
        if v is None:
            continue
        if n in NOMBRES_BRIEF2 and e == ESCALA_T_INVERSO and v >= 60:
            rango = "clínicamente elevado" if v >= 70 else "potencialmente clínico" if v >= 65 else "levemente elevado"
            yield Indicador("BRIEF-2", f"{n.removeprefix('BRIEF-2 - ')}: T {v:g}, {rango}. Revisá la validez del protocolo.")
        if n.startswith("BRIEF - ") and e == ESCALA_T_INVERSO and v > 65:
            yield Indicador("BRIEF", f"{n.removeprefix('BRIEF - ')}: T {v:g}, supera el corte de la Planilla Memoria. Cotejá el formulario.")
        if e != ESCALA_BRUTO:
            continue
        if n.startswith("SNAP-IV - ") and "Planilla Memoria" in n:
            if "suma" in n and v.is_integer() and (16 if "Hiperactividad" in n else 15) <= v <= 27:
                yield Indicador("SNAP-IV", f"{n}: {v:g}, alcanza el corte de la Planilla Memoria. Verificá versión e informante.")
            if "promedio" in n and 1.67 < v <= 3:
                yield Indicador("SNAP-IV", f"{n}: {v:g}, supera el corte de promedio de la Planilla Memoria. Verificá versión e informante.")
        if n in AREAS_AUTOESTIMA and 0 <= v <= 12:
            area = n.removeprefix("Autoestima - ").removesuffix(" (Planilla Memoria)")
            yield Indicador("Autoestima", f"Área {area.lower()}: {v:g}, alcanza el punto de revisión de la Planilla Memoria. Verificá instrumento y baremo.")
        if n.startswith("Feldman - ") and n.endswith("(% informado)") and 5 < v <= 100:
            yield Indicador("Feldman", f"{n.removeprefix('Feldman - ')}: {v:g}%, sobre la referencia de la Planilla Memoria.")
        if n.startswith("DIVA-5 - ") and v.is_integer():
            if ("adultez" in n and 5 <= v <= 9) or ("infancia" in n and 6 <= v <= 9):
                yield Indicador("DIVA-5", f"{n.removeprefix('DIVA-5 - ')}: {v:g}. Umbral de recuento alcanzado. Revisá inicio, persistencia y contexto.")
            if n == "DIVA-5 - Ámbitos afectados" and v >= 2:
                yield Indicador("DIVA-5", f"{v:g} ámbitos consignados. Cotejá su descripción y el deterioro funcional.")

    funciones = ("Sensorial", "Escape", "Atención", "Tangible")
    medias = {f: _valor(datos, f"Durand MAS - {f} (media 0 a 6)", (ESCALA_BRUTO,)) for f in funciones}
    if not all(v is not None and 0 <= v <= 6 for v in medias.values()):
        sumas = {f: _valor(datos, f"Durand MAS - {f} (suma 0 a 24)", (ESCALA_BRUTO,)) for f in funciones}
        medias = {f: v / 4 if v is not None and v.is_integer() else None for f, v in sumas.items()}
    if all(v is not None and 0 <= v <= 6 for v in medias.values()):
        orden = sorted(medias, key=medias.get, reverse=True)
        resumen = ", ".join(f"{k} {medias[k]:g}" for k in orden)
        empatadas = [k for k in orden if medias[k] == medias[orden[0]]]
        lideres = " / ".join(empatadas)
        yield Indicador("Durand MAS", f"Ranking: {resumen}. Mayor media: {lideres}. Hipótesis indirecta para contrastar con observación.")


def _rey_meyers(datos):
    aciertos = _valor(datos, "Figura Compleja de Rey - Meyers, aciertos (de 12)", (ESCALA_BRUTO,))
    falsos = _valor(datos, "Figura Compleja de Rey - Meyers, falsos positivos (de 12)", (ESCALA_BRUTO,))
    if all(v is not None and v.is_integer() and 0 <= v <= 12 for v in (aciertos, falsos)):
        yield Indicador("Rey Meyers", f"Reconocimiento: {aciertos:g}/12 aciertos; {falsos:g}/12 falsos positivos. Cotejá el baremo correspondiente.")
    fila = datos.get("Figura Compleja de Rey - Osterrieth, tipo de copia (I a VII en notas)")
    if fila and fila.nota.upper() in {"I", "II", "III", "IV", "V", "VI", "VII"}:
        yield Indicador("Rey Osterrieth", f"Tipo de copia consignado: {fila.nota.upper()}.")


def _lectura(datos):
    categorias = {
        "normal": "Normal", "dificultad": "Dificultad", "dificultad leve": "Dificultad leve",
        "dificultad severa": "Dificultad severa", "lento": "Lento", "muy lento": "Muy lento",
        "rápido": "Rápido", "muy rápido": "Muy rápido", "rápida": "Rápida", "muy rápida": "Muy rápida",
        "lenta": "Lenta", "muy lenta": "Muy lenta", "media": "Media", "baja": "Baja",
        "d": "D", "dd": "DD",
    }
    for medida in ("Principal", "Precisión", "Velocidad"):
        valores = []
        for tarea in ("Palabras", "Pseudopalabras"):
            fila = datos.get(f"PROLEC-R - {tarea}, {medida} (categoría en notas)")
            valores.append(categorias.get(fila.nota.casefold()) if fila else None)
        palabras, pseudopalabras = valores
        if palabras and pseudopalabras:
            yield Indicador("PROLEC-R", f"{medida}: palabras (ruta léxica) {palabras}; pseudopalabras (ruta fonológica) {pseudopalabras}.")


def avisos_baremos_memoria(pruebas, edad_meses, brief_padres_ninas=False):
    """Inventario de fotos consultado en Memoria. Se limita al material inventariado."""
    if edad_meses is not None:
        edad = edad_meses // 12
        if "TOMAL" in pruebas and edad in {5, 6, 9, 13, 16, 18, 19}:
            yield "TOMAL: el índice de Memoria registra un faltante en las fotos para esta edad."
        if "WRAML" in pruebas and edad >= 14 and edad_meses != 180:
            yield "WRAML: faltan fotos desde los 14 años en el inventario, excepto 15:0."
        if "NEPSY-II" in pruebas and 13 <= edad <= 16:
            yield "NEPSY-II: faltan fotos del baremo A4 para 13–16 años en Memoria."
        if "Figura Compleja de Rey" in pruebas and edad not in {13, 15, 17}:
            yield "Rey Meyers: el índice registra fotos únicamente para 13, 15 y 17 años."
    if brief_padres_ninas and {"BRIEF", "BRIEF-2"}.intersection(pruebas):
        yield "BRIEF: el índice de Memoria registra un faltante en las fotos del formulario de padres para niñas. Verificá edición y formulario."


def analizar_resultados(filas, pruebas=(), edad_meses=None):
    """Devuelve indicadores descriptivos sobre filas únicas y escalas explícitas."""
    datos = _cargar_resultados(filas)
    return [
        *_wechsler(datos, pruebas, edad_meses),
        *_atencion(datos),
        *_derivados(datos, edad_meses),
        *_memoria(datos),
        *_cuestionarios(datos),
        *_rey_meyers(datos),
        *_lectura(datos),
    ]
