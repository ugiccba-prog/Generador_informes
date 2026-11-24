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
    return re.sub(r"[&\\`*_{}\[\]<>|!#]", lambda m: f"&#{ord(m[0])};", linea)


def grilla_markdown(df) -> str:
    """Conserva las notas y los puntajes dentro de sus celdas."""
    if df.empty:
        return ""
    celdas = df.map(texto_literal)
    return celdas.to_markdown(index=False, disable_numparse=True)


def _lista(pares, faltante=""):
    items = [f"- **{clave}** {texto_literal(valor)}" for clave, valor in pares if str(valor or "").strip()]
    return "\n".join(items) or faltante


def _parrafos(texto: str) -> str:
    """Mantiene el orden y los párrafos de la evidencia consignada."""
    return "\n\n".join(texto_literal(linea) for linea in texto.splitlines() if linea.strip())


def _seccion(titulo: str, contenido: str) -> str:
    return f"## {titulo}\n\n{contenido}"


def construir_borrador(datos: dict, redaccion: dict | None = None) -> str:
    """Compone ambos modos con la misma estructura y las mismas fuentes."""
    modelos = datos.get("modelos_seleccionados") or []
    titulo = modelos[0] if len(modelos) == 1 else "Informe de evaluación"
    cuerpo = [f"# {texto_literal(titulo)}"]
    if len(modelos) > 1:
        cuerpo.append(_seccion("Alcance de la evaluación", "\n".join(f"- {texto_literal(m)}" for m in modelos)))

    filiacion = _lista(
        [(etiqueta, datos.get(clave)) for clave, etiqueta in CAMPOS_FILIACION.items()],
        "[Completar datos de filiación]",
    )
    cuerpo.append(_seccion("Datos de filiación", filiacion))

    motivo = _parrafos(datos.get("quien_deriva") or "") or "[Completar motivo de consulta]"
    antecedentes = _parrafos(datos.get("antecedentes") or "")
    cuerpo.append(_seccion("Motivo de consulta y antecedentes", motivo))
    if antecedentes:
        cuerpo.append("### Antecedentes consignados\n\n" + antecedentes)

    metodos = "\n".join(f"- {texto_literal(prueba)}" for prueba in datos.get("pruebas_usadas") or [])
    titulo_metodos = "Técnicas implementadas" if any("Psicopedagógica" in m for m in modelos) else "Métodos de evaluación"
    cuerpo.append(_seccion(titulo_metodos, metodos or "[Completar técnicas y fuentes de evaluación]"))
    if datos.get("fuentes_resultados", "").strip():
        cuerpo.append("### Fuentes de los resultados\n\n" + _parrafos(datos["fuentes_resultados"]))

    conducta = _lista((datos.get("conducta") or {}).items(), "[Consignar observaciones de la evaluación]")
    cuerpo.append(_seccion("Observación de la conducta", conducta))

    tabla = (datos.get("tabla_z_markdown") or "").strip()
    registro = _parrafos(datos.get("texto_puntajes_libre") or "")
    adjuntos = _parrafos((redaccion or {}).get("datos_adjuntos", ""))
    if tabla or registro or adjuntos:
        cuerpo.append("## Resultados registrados")
        if tabla:
            cuerpo.append(tabla)
        if registro:
            cuerpo.append("### Resultados consignados por el profesional\n\n" + registro)
        if adjuntos:
            cuerpo.append("### Resultados extraídos de adjuntos · verificar con el original\n\n" + adjuntos)

    observaciones = datos.get("observaciones_cualitativas") or {}
    versiones_asistidas = (redaccion or {}).get("dominios", {})
    apartados = [
        f"### {texto_literal(dominio)}\n\n{_parrafos(versiones_asistidas.get(dominio) or nota)}"
        for dominio, nota in observaciones.items()
        if nota.strip()
    ]
    if apartados:
        cuerpo.append(_seccion("Análisis por dominio", "\n\n".join(apartados)))

    sintesis = [
        (titulo_bloque, _parrafos(datos.get(clave) or ""))
        for clave, titulo_bloque in (
            ("fortalezas", "Fortalezas observadas"),
            ("dificultades", "Dificultades observadas"),
            ("impacto_funcional", "Impacto registrado en la vida cotidiana o escolar"),
            ("limitaciones", "Alcance y limitaciones"),
            ("impresion_destacar", "Síntesis profesional"),
        )
    ]
    bloques = [f"### {etiqueta}\n\n{contenido}" for etiqueta, contenido in sintesis if contenido]
    if not (datos.get("impresion_destacar") or "").strip():
        bloques.append("[Completar la integración profesional de los hallazgos]")
    cuerpo.append(_seccion("Conclusiones", "\n\n".join(bloques)))

    recomendaciones = [
        (titulo_bloque, datos.get(clave) or "")
        for clave, titulo_bloque in (
            ("detalle_terapeuticas", "Terapéuticas y generales"),
            ("detalle_escolares", "Para la escuela"),
            ("recom_personalizadas", "Sugerencias específicas"),
            ("frecuencia_y_control", "Seguimiento"),
        )
    ]
    if any(contenido.strip() for _, contenido in recomendaciones):
        cuerpo.append("## Recomendaciones")
        fundamento = _parrafos(datos.get("fundamento_recomendaciones") or "")
        if fundamento:
            cuerpo.append(fundamento)
        for titulo_bloque, contenido in recomendaciones:
            if contenido.strip():
                lista = "\n".join(f"- {texto_literal(linea.removeprefix('- '))}"
                                  for linea in contenido.splitlines() if linea.strip())
                cuerpo.append(f"### {titulo_bloque}\n\n{lista}")
    return "\n\n".join(cuerpo)
