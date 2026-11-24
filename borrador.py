"""Composición local del informe, independiente del proveedor de IA."""

import re


CAMPOS_FILIACION = {
    "nombre": "Apellido y nombre",
    "hc": "DNI / HC",
    "edad_texto": "Edad",
    "fecha_nac": "Fecha de nacimiento",
    "fecha_eval": "Fecha de evaluación",
    "escolaridad": "Escolaridad",
    "nacionalidad": "Nacionalidad",
    "preferencia": "Preferencia manual",
    "medico": "Solicitante",
    "acompanante": "Acompañante",
}


def texto_literal(valor: str) -> str:
    """Representa un campo de texto como una sola línea Markdown."""
    linea = " ".join(str(valor or "").splitlines()).strip()
    return re.sub(r"[&\\`*_{}\[\]<>|!]", lambda m: f"&#{ord(m[0])};", linea)


def grilla_markdown(df) -> str:
    """Conserva las notas y los puntajes dentro de sus celdas."""
    if df.empty:
        return ""
    celdas = df.map(texto_literal)
    return celdas.to_markdown(index=False, disable_numparse=True)


def _campo(datos, clave, faltante="[Completar]"):
    return texto_literal(datos.get(clave, "")) or faltante


def _lista(pares, faltante):
    items = [f"- **{clave}** {texto_literal(valor)}" for clave, valor in pares if str(valor or "").strip()]
    return "\n".join(items) or faltante


def construir_borrador(datos: dict, redaccion: str | None = None) -> str:
    """Inserta filiación y resultados de forma determinística en ambos modos."""
    filiacion = _lista(
        [(etiqueta, datos.get(clave)) for clave, etiqueta in CAMPOS_FILIACION.items()],
        "[Completar datos de filiación]",
    )
    tabla = datos.get("tabla_z_markdown") or "No se cargaron puntajes en la grilla."
    cuerpo = [
        "# Borrador de evaluación clínica",
        "## Datos de filiación\n\n" + filiacion,
        "## Puntuaciones registradas\n\n" + tabla,
    ]
    if redaccion is not None:
        cuerpo.append(redaccion.strip())
        return "\n\n".join(cuerpo)

    for clave, titulo in (
        ("modelos_seleccionados", "Tipo de evaluación"),
        ("pruebas_usadas", "Métodos de evaluación y procedimientos"),
    ):
        valores = datos.get(clave) or []
        if valores:
            cuerpo.append(f"## {titulo}\n\n" + "\n".join(f"- {texto_literal(v)}" for v in valores))

    conducta = _lista((datos.get("conducta") or {}).items(), "[Consignar observaciones]")
    observaciones = _lista(
        (datos.get("observaciones_cualitativas") or {}).items(), "[Completar análisis por dominio]"
    )
    cuerpo.extend(
        [
            "## Motivo de consulta y antecedentes\n\n"
            + _lista(
                [("Motivo y derivación", datos.get("quien_deriva")), ("Antecedentes", datos.get("antecedentes"))],
                "[Completar motivo de consulta y antecedentes]",
            ),
            "## Observación de la conducta\n\n" + conducta,
            "## Análisis por dominio\n\n" + observaciones,
        ]
    )
    if datos.get("texto_puntajes_libre", "").strip():
        notas = "\n".join(texto_literal(linea) for linea in datos["texto_puntajes_libre"].splitlines())
        cuerpo.append("## Notas de puntuaciones\n\n" + notas)
    cuerpo.append("## Conclusiones\n\n" + _campo(datos, "impresion_destacar", "[Completar síntesis]"))
    recomendaciones = [
        "## Recomendaciones",
        "### Terapéuticas y generales\n\n" + (datos.get("detalle_terapeuticas") or "[Completar si corresponde]"),
        "### Para la escuela\n\n" + (datos.get("detalle_escolares") or "[Completar si corresponde]"),
    ]
    for clave in ("frecuencia_y_control", "recom_personalizadas"):
        if datos.get(clave, "").strip():
            recomendaciones.append(_campo(datos, clave))
    cuerpo.extend(recomendaciones)
    return "\n\n".join(cuerpo)
