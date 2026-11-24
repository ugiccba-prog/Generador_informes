"""Exportador institucional a Microsoft Word (.docx) con parser Markdown completo."""

from __future__ import annotations

import io
from pathlib import Path
from html import unescape
import re
import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Mm, Pt, RGBColor

from psicometria import categoria_color_rango, redondear_z_a_tercio

COLOR_TEXTO_BASE = RGBColor(0x1E, 0x1E, 0x1E)
COLOR_AZUL_INSTITUCIONAL = RGBColor(0x1B, 0x36, 0x5D)
COLOR_AZUL_SECUNDARIO = RGBColor(0x2C, 0x52, 0x82)
COLOR_GRIS_SUAVE = RGBColor(0x66, 0x66, 0x66)
COLOR_BLANCO = RGBColor(0xFF, 0xFF, 0xFF)

HEX_AZUL_CABECERA = "1B365D"
HEX_FILA_ALTERNA = "F8FAFC"
HEX_BORDE_TABLA = "CBD5E0"

ESTILOS_RANGO_TABLA: dict[str, tuple[str, RGBColor, bool]] = {
    "deficit": ("FADBD8", RGBColor(0x92, 0x2B, 0x21), True),
    "limitrofe_bajo": ("F5CBA7", RGBColor(0x7E, 0x51, 0x09), True),
    "dificultad": ("FDEBD0", RGBColor(0x9C, 0x64, 0x0C), True),
    "tendencia_baja": ("FCF3CF", RGBColor(0x7D, 0x66, 0x08), False),
    "normal": ("E8F8F5", RGBColor(0x14, 0x5A, 0x32), False),
    "tendencia_alta": ("EBF5FB", RGBColor(0x1B, 0x4F, 0x72), False),
    "normal_alto": ("EBF5FB", RGBColor(0x1B, 0x4F, 0x72), False),
    "superior": ("EBF5FB", RGBColor(0x1B, 0x4F, 0x72), True),
    "cualitativo": ("F4F6F7", RGBColor(0x42, 0x49, 0x49), False),
}

_INLINE_TOKEN_RE = re.compile(
    r"\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*"
    r"|\*\*(?!\s)(.+?)(?<!\s)\*\*"
    r"|\*(?!\s|\*)([^*\n]+?)(?<!\s|\*)\*"
    r"|(?<![\w_])_(?!\s|_)([^_\n]+?)(?<!\s|_)_(?![\w_])"
    r"|`([^`\n]+?)`"
)

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$")
_BULLET_RE = re.compile(r"^(\s*)[-*•]\s+(.+?)\s*$")
_NUMBERED_RE = re.compile(r"^(\s*)\d+[.)]\s+(.+?)\s*$")
_HR_RE = re.compile(r"^\s*(?:---|\*\*\*|___)\s*$")


def _set_cell_shading(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for existing in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(existing)
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tc_pr.append(shd)


def _set_cell_margins(cell, top: int = 75, bottom: int = 75, left: int = 110, right: int = 110) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for existing in tc_pr.findall(qn("w:tcMar")):
        tc_pr.remove(existing)
    tc_mar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tc_mar.append(node)
    tc_pr.append(tc_mar)


def _set_table_borders(table, color: str = HEX_BORDE_TABLA) -> None:
    tbl_pr = table._tbl.tblPr
    for existing in tbl_pr.findall(qn("w:tblBorders")):
        tbl_pr.remove(existing)
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:right w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        "</w:tblBorders>"
    )
    tbl_pr.append(borders)


def _set_repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if not tr_pr.findall(qn("w:tblHeader")):
        tr_pr.append(OxmlElement("w:tblHeader"))


def _prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if not tr_pr.findall(qn("w:cantSplit")):
        tr_pr.append(OxmlElement("w:cantSplit"))


def _set_paragraph_bottom_border(paragraph, color: str = HEX_BORDE_TABLA) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    for existing in p_pr.findall(qn("w:pBdr")):
        p_pr.remove(existing)
    pbdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'<w:bottom w:val="single" w:sz="6" w:space="3" w:color="{color}"/>'
        "</w:pBdr>"
    )
    p_pr.append(pbdr)


def _agregar_campo_pagina(paragraph, font_size: Pt = Pt(8.5), color: RGBColor = COLOR_GRIS_SUAVE) -> None:
    def _add_styled_run(text: str):
        r = paragraph.add_run(text)
        r.font.name = "Arial"
        r.font.size = font_size
        r.font.color.rgb = color
        return r

    _add_styled_run("Página ")
    run_campo = paragraph.add_run()
    run_campo.font.name = "Arial"
    run_campo.font.size = font_size
    run_campo.font.color.rgb = color

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    run_campo._r.append(fld_begin)
    run_campo._r.append(instr)
    run_campo._r.append(fld_sep)
    run_campo._r.append(fld_end)


def agregar_runs_inline(
    paragraph,
    texto: str,
    bold: bool = False,
    italic: bool = False,
    font_size: Pt = Pt(10.5),
    color: RGBColor = COLOR_TEXTO_BASE,
) -> None:
    """Agrega runs al párrafo interpretando ***negrita cursiva***, **negrita** y *cursiva*."""
    if not texto:
        return

    pos = 0
    for match in _INLINE_TOKEN_RE.finditer(texto):
        if match.start() > pos:
            r = paragraph.add_run(unescape(texto[pos:match.start()]))
            r.bold = bold
            r.italic = italic
            r.font.name = "Arial"
            r.font.size = font_size
            r.font.color.rgb = color

        g_bi, g_b, g_i1, g_i2, g_code = match.groups()
        if g_bi is not None:
            agregar_runs_inline(paragraph, g_bi, bold=True, italic=True, font_size=font_size, color=color)
        elif g_b is not None:
            agregar_runs_inline(paragraph, g_b, bold=True, italic=italic, font_size=font_size, color=color)
        elif g_i1 is not None:
            agregar_runs_inline(paragraph, g_i1, bold=bold, italic=True, font_size=font_size, color=color)
        elif g_i2 is not None:
            agregar_runs_inline(paragraph, g_i2, bold=bold, italic=True, font_size=font_size, color=color)
        elif g_code is not None:
            r = paragraph.add_run(unescape(g_code))
            r.bold = bold
            r.italic = italic
            r.font.name = "Arial"
            r.font.size = font_size
            r.font.color.rgb = color

        pos = match.end()

    if pos < len(texto):
        r = paragraph.add_run(unescape(texto[pos:]))
        r.bold = bold
        r.italic = italic
        r.font.name = "Arial"
        r.font.size = font_size
        r.font.color.rgb = color


def _limpiar_markdown_simple(texto: str) -> str:
    return re.sub(r"[*_`]+", "", texto or "").strip()


def _parse_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [c.strip() for c in stripped.split("|")]


def _renderizar_tabla(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    if not headers:
        return

    num_cols = len(headers)
    table = doc.add_table(rows=1, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table)

    hdr_row = table.rows[0]
    _set_repeat_header(hdr_row)
    _prevent_row_split(hdr_row)

    idx_rango = [i for i, h in enumerate(headers) if "rango" in h.lower()]

    for i, h_text in enumerate(headers):
        cell = hdr_row.cells[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _set_cell_shading(cell, HEX_AZUL_CABECERA)
        _set_cell_margins(cell)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        agregar_runs_inline(
            p,
            _limpiar_markdown_simple(h_text),
            bold=True,
            font_size=Pt(9.5),
            color=COLOR_BLANCO,
        )

    for row_idx, raw_row in enumerate(rows):
        padded = list(raw_row[:num_cols]) + [""] * max(0, num_cols - len(raw_row))
        row_obj = table.add_row()
        _prevent_row_split(row_obj)
        bg_alterno = HEX_FILA_ALTERNA if row_idx % 2 == 1 else None

        for col_idx, cell_text in enumerate(padded):
            cell = row_obj.cells[col_idx]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_margins(cell)

            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)

            if col_idx in idx_rango and cell_text.strip():
                cat = categoria_color_rango(_limpiar_markdown_simple(cell_text))
                bg_hex, txt_color, es_negrita = ESTILOS_RANGO_TABLA.get(
                    cat, ("F4F6F7", COLOR_TEXTO_BASE, False)
                )
                _set_cell_shading(cell, bg_hex)
                agregar_runs_inline(
                    p,
                    cell_text,
                    bold=es_negrita,
                    font_size=Pt(9.0),
                    color=txt_color,
                )
            else:
                if bg_alterno:
                    _set_cell_shading(cell, bg_alterno)
                agregar_runs_inline(
                    p,
                    cell_text,
                    bold=False,
                    font_size=Pt(9.0),
                    color=COLOR_TEXTO_BASE,
                )

    espacio = doc.add_paragraph()
    espacio.paragraph_format.space_before = Pt(0)
    espacio.paragraph_format.space_after = Pt(4)


def _agregar_heading_personalizado(doc: Document, nivel: int, texto: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.keep_with_next = True
    texto_limpio = _limpiar_markdown_simple(texto)

    if nivel == 1:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(10)
        agregar_runs_inline(p, texto_limpio, bold=True, font_size=Pt(13.5), color=COLOR_AZUL_INSTITUCIONAL)
    elif nivel == 2:
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(5)
        _set_paragraph_bottom_border(p)
        agregar_runs_inline(p, texto_limpio, bold=True, font_size=Pt(11.5), color=COLOR_AZUL_INSTITUCIONAL)
    elif nivel == 3:
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        agregar_runs_inline(p, texto_limpio, bold=True, font_size=Pt(10.5), color=COLOR_AZUL_SECUNDARIO)
    else:
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        agregar_runs_inline(
            p, texto_limpio, bold=True, italic=True, font_size=Pt(10.5), color=COLOR_AZUL_SECUNDARIO
        )


def _desenvolver_bloque_codigo_markdown(texto: str) -> str:
    stripped = (texto or "").strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lineas = stripped.splitlines()
        if len(lineas) >= 2:
            return "\n".join(lineas[1:-1]).strip()
    return stripped


def agregar_markdown_a_doc(doc: Document, texto_markdown: str, omitir_primer_h1: bool = False) -> None:
    """Convierte texto Markdown completo (títulos, tablas, listas, negritas, cursivas) a Word."""
    texto_limpio = _desenvolver_bloque_codigo_markdown(texto_markdown)
    if not texto_limpio:
        return

    lineas = texto_limpio.splitlines()
    i = 0
    primer_h1_visto = False

    while i < len(lineas):
        linea = lineas[i]
        stripped = linea.strip()

        if not stripped:
            i += 1
            continue

        # 1. Separador horizontal
        if _HR_RE.match(stripped):
            p_hr = doc.add_paragraph()
            p_hr.paragraph_format.space_before = Pt(4)
            p_hr.paragraph_format.space_after = Pt(6)
            _set_paragraph_bottom_border(p_hr)
            i += 1
            continue

        # 2. Encabezados (# a ####)
        m_head = _HEADING_RE.match(stripped)
        if m_head:
            nivel = len(m_head.group(1))
            contenido_head = m_head.group(2)
            if nivel == 1 and not primer_h1_visto:
                primer_h1_visto = True
                if omitir_primer_h1:
                    i += 1
                    continue
            _agregar_heading_personalizado(doc, nivel, contenido_head)
            i += 1
            continue

        # 3. Tablas Markdown
        if "|" in stripped and i + 1 < len(lineas) and _TABLE_SEP_RE.match(lineas[i + 1]):
            headers = _parse_table_row(stripped)
            i += 2  # Salta cabecera y fila separadora
            filas_tabla: list[list[str]] = []
            while i < len(lineas):
                cand = lineas[i].strip()
                if not cand or "|" not in cand:
                    break
                if _TABLE_SEP_RE.match(cand):
                    i += 1
                    continue
                filas_tabla.append(_parse_table_row(cand))
                i += 1
            _renderizar_tabla(doc, headers, filas_tabla)
            continue

        # 4. Viñetas
        m_bullet = _BULLET_RE.match(linea)
        if m_bullet:
            indent_len = len(m_bullet.group(1))
            contenido_item = m_bullet.group(2)
            p_item = doc.add_paragraph(style="List Bullet")
            p_item.paragraph_format.space_before = Pt(1)
            p_item.paragraph_format.space_after = Pt(3)
            p_item.paragraph_format.line_spacing = 1.15
            if indent_len >= 2:
                p_item.paragraph_format.left_indent = Cm(1.25)
            agregar_runs_inline(p_item, contenido_item)
            i += 1
            continue

        # 5. Listas numeradas
        m_num = _NUMBERED_RE.match(linea)
        if m_num:
            indent_len = len(m_num.group(1))
            contenido_item = m_num.group(2)
            p_item = doc.add_paragraph(style="List Number")
            p_item.paragraph_format.space_before = Pt(1)
            p_item.paragraph_format.space_after = Pt(3)
            p_item.paragraph_format.line_spacing = 1.15
            if indent_len >= 2:
                p_item.paragraph_format.left_indent = Cm(1.25)
            agregar_runs_inline(p_item, contenido_item)
            i += 1
            continue

        # 6. Citas (> ...)
        if stripped.startswith(">"):
            contenido_cita = stripped.lstrip(">").strip()
            p_cita = doc.add_paragraph()
            p_cita.paragraph_format.left_indent = Cm(0.8)
            p_cita.paragraph_format.space_before = Pt(3)
            p_cita.paragraph_format.space_after = Pt(5)
            agregar_runs_inline(p_cita, contenido_cita, italic=True, color=COLOR_GRIS_SUAVE)
            i += 1
            continue

        # 7. Párrafo estándar
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.line_spacing = 1.15
        agregar_runs_inline(p, stripped)
        i += 1


def _configurar_documento_base(
    doc: Document, datos_filiacion: dict | None = None, incluir_confidencialidad: bool = False
) -> None:
    for section in doc.sections:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

        # Encabezado discreto
        header = section.header
        p_hdr = header.paragraphs[0]
        p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        institucion = ((datos_filiacion or {}).get("institucion") or "").strip()
        if institucion:
            p_hdr.alignment = WD_ALIGN_PARAGRAPH.LEFT
            membrete = p_hdr.add_run(institucion)
            membrete.bold = True
            membrete.font.size = Pt(11)
            p_hdr = header.add_paragraph()
            p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        nombre = ((datos_filiacion or {}).get("nombre") or "").strip()
        fecha = ((datos_filiacion or {}).get("fecha_eval") or "").strip()
        if nombre and fecha:
            texto_hdr = f"Informe Clínico — {nombre} ({fecha})"
        elif nombre:
            texto_hdr = f"Informe Clínico — {nombre}"
        elif fecha:
            texto_hdr = f"Informe de Evaluación Neuropsicológica ({fecha})"
        else:
            texto_hdr = "Informe de Evaluación Neuropsicológica"
        r_hdr = p_hdr.add_run(texto_hdr)
        r_hdr.font.name = "Arial"
        r_hdr.font.size = Pt(8.5)
        r_hdr.font.color.rgb = COLOR_GRIS_SUAVE

        # Pie de página con número de página nativo
        footer = section.footer
        p_ftr = footer.paragraphs[0]
        p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if incluir_confidencialidad:
            p_ftr.add_run(
                "Confidencial. Informe elaborado con alcance clínico. "
                "Su finalidad es orientar la atención y no constituye una pericia judicial."
            ).font.size = Pt(8)
            p_ftr = footer.add_paragraph()
            p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _agregar_campo_pagina(p_ftr)

    style_normal = doc.styles["Normal"]
    style_normal.font.name = "Arial"
    style_normal.font.size = Pt(10.5)
    style_normal.font.color.rgb = COLOR_TEXTO_BASE
    style_normal.paragraph_format.line_spacing = 1.15

    for nombre_estilo in ("List Bullet", "List Number"):
        if nombre_estilo in doc.styles:
            st = doc.styles[nombre_estilo]
            st.font.name = "Arial"
            st.font.size = Pt(10.5)
            st.font.color.rgb = COLOR_TEXTO_BASE


def _agregar_tabla_filiacion(doc: Document, datos: dict) -> None:
    _agregar_heading_personalizado(doc, 2, "1. Datos de Filiación")
    pares = [
        (f"Apellido y Nombre: {datos.get('nombre') or '[Completar]'}", f"DNI / N° HC: {datos.get('hc') or '[Completar]'}"),
        (f"Edad: {datos.get('edad') or '[Completar]'}", f"Escolaridad: {datos.get('escolaridad') or '[Completar]'}"),
        (f"Fecha de Evaluación: {datos.get('fecha_eval') or '[Completar]'}", f"Solicitante: {datos.get('solicitante') or '[Completar]'}"),
        (f"Profesional Actuante: {datos.get('profesional') or '[Completar]'}", f"Matrícula: {datos.get('matricula') or '[Completar]'}"),
    ]
    tabla = doc.add_table(rows=len(pares), cols=2)
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tabla)

    for idx, (c1, c2) in enumerate(pares):
        row = tabla.rows[idx]
        _prevent_row_split(row)
        for col_i, val in enumerate((c1, c2)):
            cell = row.cells[col_i]
            _set_cell_margins(cell)
            if idx % 2 == 0:
                _set_cell_shading(cell, HEX_FILA_ALTERNA)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            agregar_runs_inline(p, val, font_size=Pt(9.5))

    espacio = doc.add_paragraph()
    espacio.paragraph_format.space_after = Pt(4)


def _agregar_tabla_z_dataframe(doc: Document, df_puntajes: pd.DataFrame) -> None:
    _agregar_heading_personalizado(doc, 2, "2. Resultados Cuantitativos (Grilla Z)")
    headers = [str(col) for col in df_puntajes.columns]
    rows = [["" if pd.isna(v) else str(v) for v in fila] for fila in df_puntajes.to_numpy()]
    _renderizar_tabla(doc, headers, rows)


def _agregar_grilla_visual_z(doc: Document, df_puntajes: pd.DataFrame) -> None:
    resultados = []
    for _, fila in df_puntajes.iterrows():
        try:
            z = float(fila["Puntaje Z"])
            tercio = redondear_z_a_tercio(z)
        except (TypeError, ValueError):
            continue
        resultados.append((str(fila["Dominio / Prueba / Subtest"]), z, round(tercio * 3) + 10))
    if not resultados:
        return

    _agregar_heading_personalizado(doc, 2, "Grilla visual de puntuaciones Z")
    nota = doc.add_paragraph(
        "Cada X indica el tercio más cercano. Los valores fuera de escala se marcan en el extremo. "
        "La cifra exacta figura en los resultados registrados."
    )
    for run in nota.runs:
        run.font.size = Pt(8)

    tabla = doc.add_table(rows=2, cols=20)
    tabla.autofit = False
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(tabla)
    anchos = [Cm(4.45)] + [Cm(0.635)] * 19
    for columna, ancho in zip(tabla.columns, anchos):
        columna.width = ancho
    for fila in tabla.rows:
        for celda, ancho in zip(fila.cells, anchos):
            celda.width = ancho

    def celda_texto(celda, texto, tam=8, fondo=None):
        _set_cell_margins(celda, top=30, bottom=30, left=15, right=15)
        celda.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = celda.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1
        run = p.add_run(texto)
        run.font.size = Pt(tam)
        if fondo:
            _set_cell_shading(celda, fondo)
            run.font.bold = True

    celda_texto(tabla.cell(0, 0).merge(tabla.cell(1, 0)), "Prueba / Subprueba", 8, "E2E8F0")
    for desde, hasta, etiqueta, fondo in (
        (1, 3, "Déficit", "FADBD8"),
        (4, 6, "Dificultad", "FDEBD0"),
        (7, 13, "Normal", "E8F8F5"),
        (14, 16, "Normal alto", "EBF5FB"),
        (17, 19, "Superior", "D6EAF8"),
    ):
        celda_texto(tabla.cell(0, desde).merge(tabla.cell(0, hasta)), etiqueta, 7.5, fondo)
    for columna, tercio in enumerate(range(-9, 10), start=1):
        entero, fraccion = divmod(abs(tercio), 3)
        signo = "−" if tercio < 0 else "+" if tercio > 0 else ""
        marca = f"{signo}{entero or ''}{('', '⅓', '⅔')[fraccion]}" if tercio else "0"
        celda_texto(tabla.cell(1, columna), marca, 6.5)
    for fila in tabla.rows:
        _set_repeat_header(fila)
        _prevent_row_split(fila)
    for nombre, z, columna_activa in resultados:
        fila = tabla.add_row()
        _prevent_row_split(fila)
        celda_texto(fila.cells[0], f"{nombre} ({z:+.2f})", 7.5)
        for columna in range(1, 20):
            activa = columna == columna_activa
            celda_texto(fila.cells[columna], "X" if activa else "", 8, "DFEAF7" if activa else None)


def _contiene_firma(texto_markdown: str, firma_profesional: str) -> bool:
    lineas = [ln.strip().lower() for ln in (texto_markdown or "").splitlines() if ln.strip()]
    ultimas = " ".join(lineas[-8:])
    if "firma" in ultimas or "____" in ultimas:
        return True
    nombre_base = (firma_profesional or "").split("—")[0].strip().lower()
    if nombre_base and nombre_base != "[firma y sello del profesional]" and nombre_base in ultimas:
        return True
    return False


def generar_docx_bytes(
    texto_markdown: str,
    datos_filiacion: dict | None = None,
    df_puntajes: pd.DataFrame | None = None,
    titulo_informe: str = "INFORME DE EVALUACIÓN NEUROPSICOLÓGICA Y PSICOPEDAGÓGICA",
    incluir_tabla_filiacion: bool = False,
    incluir_tabla_z: bool = False,
    firma_profesional: str = "",
    incluir_grilla_visual: bool = False,
    incluir_confidencialidad: bool = False,
) -> bytes:
    """Genera un documento Word (.docx) institucional en memoria a partir de Markdown."""
    doc = Document()
    _configurar_documento_base(doc, datos_filiacion=datos_filiacion, incluir_confidencialidad=incluir_confidencialidad)

    texto_limpio = _desenvolver_bloque_codigo_markdown(texto_markdown)
    primera_linea = next((ln.strip() for ln in texto_limpio.splitlines() if ln.strip()), "")
    empieza_con_h1 = bool(re.match(r"^#\s+", primera_linea))

    if incluir_tabla_filiacion or not empieza_con_h1:
        _agregar_heading_personalizado(doc, 1, titulo_informe)

    if incluir_tabla_filiacion and datos_filiacion:
        _agregar_tabla_filiacion(doc, datos_filiacion)

    if incluir_tabla_z and df_puntajes is not None and not df_puntajes.empty:
        _agregar_tabla_z_dataframe(doc, df_puntajes)

    agregar_markdown_a_doc(doc, texto_limpio, omitir_primer_h1=incluir_tabla_filiacion)

    if incluir_grilla_visual and df_puntajes is not None:
        _agregar_grilla_visual_z(doc, df_puntajes)

    firma_limpia = (firma_profesional or "").strip()
    if (
        firma_limpia
        and firma_limpia != "[Firma y Sello del Profesional]"
        and not _contiene_firma(texto_limpio, firma_limpia)
    ):
        p_sep = doc.add_paragraph()
        p_sep.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_sep.paragraph_format.space_before = Pt(20)
        p_sep.paragraph_format.space_after = Pt(2)
        p_sep.paragraph_format.keep_with_next = True
        agregar_runs_inline(p_sep, "________________________________________", font_size=Pt(10.0))

        p_firma = doc.add_paragraph()
        p_firma.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_firma.paragraph_format.space_before = Pt(0)
        agregar_runs_inline(p_firma, firma_limpia, bold=True, font_size=Pt(10.0))

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def guardar_docx(ruta: str | Path, **kwargs) -> Path:
    """Guarda el informe .docx generado en la ruta indicada."""
    destino = Path(ruta)
    destino.write_bytes(generar_docx_bytes(**kwargs))
    return destino
