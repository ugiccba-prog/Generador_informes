"""Suite de tests integrales para la Plataforma Clínica de Informes Neuropsicológicos."""

from datetime import date
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from zipfile import ZipFile
import warnings

from docx import Document
from docx.oxml.ns import qn
import pandas as pd

import analisis_clinico
import borrador
import catalogo_clinico
import exportador_docx
import memoria_drive
import motor_ia
import psicometria


class TestCatalogoClinico(unittest.TestCase):
    def test_escalas_y_subpruebas_sin_hints_ui(self):
        self.assertIn(catalogo_clinico.ESCALA_PERCENTIL, catalogo_clinico.ESCALAS_DISPONIBLES)
        self.assertIn(catalogo_clinico.ESCALA_PERCENTIL, catalogo_clinico.ESCALAS_CALCULADORA)

        todas_subpruebas = [
            nombre
            for lista in catalogo_clinico.CATALOGO_SUBPRUEBAS.values()
            for nombre, _ in lista
        ]
        for sub in todas_subpruebas:
            self.assertNotIn("Colocar Edad Equivalente", sub)
            self.assertNotIn("Detallar en Notas", sub)

        # Verificar escalas válidas en catálogo
        escalas_set = set(catalogo_clinico.ESCALAS_DISPONIBLES)
        for bateria, lista in catalogo_clinico.CATALOGO_SUBPRUEBAS.items():
            self.assertTrue(len(lista) > 0, f"Batería vacía: {bateria}")
            for nombre, esc in lista:
                self.assertIn(esc, escalas_set, f"Escala inválida en {nombre}: {esc}")

        # Verificar índices secundarios WISC-V
        wisc_nombres = [n for n, _ in catalogo_clinico.CATALOGO_SUBPRUEBAS["WISC-V"]]
        self.assertTrue(any("(IRC)" in n for n in wisc_nombres))
        self.assertTrue(any("(IMTA)" in n for n in wisc_nombres))
        self.assertTrue(any("(ICC)" in n for n in wisc_nombres))

    def test_modelos_gemini_vigentes(self):
        self.assertGreater(len(catalogo_clinico.MODELOS_GEMINI), 0)
        for modelo_id, cfg in catalogo_clinico.MODELOS_GEMINI.items():
            self.assertNotIn("1.5", modelo_id)
            self.assertNotIn("2.0", modelo_id)
            self.assertNotIn("2.5", modelo_id)
            self.assertIn(cfg["default_thinking"], cfg["thinking_levels"])


class TestPsicometria(unittest.TestCase):
    def test_clasificar_z_9_franjas_y_limites_exactos(self):
        casos = [
            (-3.00, "Déficit"),
            (-2.33, "Déficit"),
            (-2.32, "Limítrofe (Dificultad / Déficit)"),
            (-2.01, "Limítrofe (Dificultad / Déficit)"),
            (-2.00, "Dificultad"),
            (-1.33, "Dificultad"),
            (-1.32, "Normal (Tendencia baja)"),
            (-1.01, "Normal (Tendencia baja)"),
            (-1.00, "Normal"),
            (0.00, "Normal"),
            (1.00, "Normal"),
            (1.01, "Normal (Tendencia alta)"),
            (1.32, "Normal (Tendencia alta)"),
            (1.33, "Normal Alto"),
            (2.00, "Normal Alto"),
            (2.01, "Normal Alto (Tendencia superior)"),
            (2.32, "Normal Alto (Tendencia superior)"),
            (2.33, "Superior"),
            (3.00, "Superior"),
        ]
        for z, esperado in casos:
            with self.subTest(z=z):
                self.assertEqual(psicometria.clasificar_z(z), esperado)

    def test_regresion_ci_y_escalas(self):
        # Casos de regresión críticos del bug original
        z132, r132 = psicometria.calcular_z_y_rango(132, catalogo_clinico.ESCALA_CI)
        self.assertEqual(z132, 2.13)
        self.assertEqual(r132, "Normal Alto (Tendencia superior)")

        z134, r134 = psicometria.calcular_z_y_rango(134, catalogo_clinico.ESCALA_CI)
        self.assertEqual(z134, 2.27)
        self.assertEqual(r134, "Normal Alto (Tendencia superior)")

        z81, r81 = psicometria.calcular_z_y_rango(81, catalogo_clinico.ESCALA_CI)
        self.assertEqual(z81, -1.27)
        self.assertEqual(r81, "Normal (Tendencia baja)")

        z116, r116 = psicometria.calcular_z_y_rango(116, catalogo_clinico.ESCALA_CI)
        self.assertEqual(z116, 1.07)
        self.assertEqual(r116, "Normal (Tendencia alta)")

        z68, r68 = psicometria.calcular_z_y_rango(68, catalogo_clinico.ESCALA_CI)
        self.assertEqual(z68, -2.13)
        self.assertEqual(r68, "Limítrofe (Dificultad / Déficit)")

        # Escalar y T directo / inverso
        self.assertEqual(psicometria.calcular_z_y_rango(10, catalogo_clinico.ESCALA_ESCALAR), (0.0, "Normal"))
        self.assertEqual(psicometria.calcular_z_y_rango(60, catalogo_clinico.ESCALA_T_DIRECTO), (1.0, "Normal"))
        self.assertEqual(psicometria.calcular_z_y_rango(66, catalogo_clinico.ESCALA_T_INVERSO), (-1.6, "Dificultad"))
        self.assertEqual(psicometria.calcular_z_y_rango(5, catalogo_clinico.ESCALA_BRUTO), (None, "Puntaje Bruto / Cualitativo"))

    def test_percentiles(self):
        esperados = [
            (1, -2.33, "Déficit"),
            (5, -1.64, "Dificultad"),
            (9, -1.34, "Dificultad"),
            (16, -0.99, "Normal"),
            (50, 0.0, "Normal"),
            (84, 0.99, "Normal"),
            (91, 1.34, "Normal Alto"),
            (98, 2.05, "Normal Alto (Tendencia superior)"),
            (99, 2.33, "Superior"),
        ]
        for pc, z_esp, r_esp in esperados:
            with self.subTest(pc=pc):
                z, r = psicometria.calcular_z_y_rango(pc, catalogo_clinico.ESCALA_PERCENTIL)
                self.assertEqual(z, z_esp)
                self.assertEqual(r, r_esp)

        # Fuera de rango y valores no finitos
        z_low, r_low = psicometria.calcular_z_y_rango(0, catalogo_clinico.ESCALA_PERCENTIL)
        self.assertIsNone(z_low)
        self.assertIn("fuera de rango", r_low.lower())

        z_high, r_high = psicometria.calcular_z_y_rango(100, catalogo_clinico.ESCALA_PERCENTIL)
        self.assertIsNone(z_high)
        self.assertIn("fuera de rango", r_high.lower())

        z_nan, _ = psicometria.calcular_z_y_rango(float("nan"), catalogo_clinico.ESCALA_CI)
        self.assertIsNone(z_nan)

    def test_edad_exacta_y_formato(self):
        # Caso estándar
        self.assertEqual(psicometria.calcular_edad_exacta(date(2017, 6, 10), date(2026, 10, 20)), (9, 4))
        # Día aún no cumplido en el mes
        self.assertEqual(psicometria.calcular_edad_exacta(date(2017, 6, 25), date(2026, 10, 20)), (9, 3))
        # Mes anterior y día cumplido -> resta 1 año y suma meses
        self.assertEqual(psicometria.calcular_edad_exacta(date(2017, 11, 5), date(2026, 10, 20)), (8, 11))
        # Año bisiesto
        self.assertEqual(psicometria.calcular_edad_exacta(date(2020, 2, 29), date(2024, 2, 29)), (4, 0))
        self.assertEqual(psicometria.calcular_edad_exacta(date(2020, 2, 29), date(2025, 2, 28)), (4, 11))
        # Fecha invertida
        self.assertIsNone(psicometria.calcular_edad_exacta(date(2026, 11, 1), date(2026, 10, 1)))

        self.assertEqual(psicometria.formatear_edad(9, 4), "9 años, 4 meses")
        self.assertEqual(psicometria.formatear_edad(1, 1), "1 año, 1 mes")
        self.assertEqual(psicometria.formatear_edad(9, 0), "9 años")
        self.assertEqual(psicometria.formatear_edad(0, 10), "10 meses")

    def test_sanitizar_nombre_y_procesar_tabla(self):
        self.assertEqual(psicometria.sanitizar_nombre_archivo("Pérez, Mateo / HC:123"), "Informe_Pérez_Mateo_HC_123")
        self.assertEqual(psicometria.sanitizar_nombre_archivo("   "), "Informe_Paciente")

        df_in = pd.DataFrame(
            [
                {
                    "Dominio / Prueba / Subtest": "WISC-V - CIT",
                    "Puntaje": 100.0,
                    "Tipo de Escala": catalogo_clinico.ESCALA_CI,
                    "Observación": float("nan"),
                },
                {
                    "Dominio / Prueba / Subtest": "NALPA - Nivel de Alfabetización",
                    "Puntaje": None,
                    "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO,
                    "Observación": "Silábico-alfabético",
                },
                {
                    "Dominio / Prueba / Subtest": "WISC-V - Vacía",
                    "Puntaje": None,
                    "Tipo de Escala": catalogo_clinico.ESCALA_ESCALAR,
                    "Observación": "",
                },
            ]
        )
        out = psicometria.procesar_tabla_puntajes(df_in)
        self.assertEqual(len(out), 2)
        self.assertEqual(out.iloc[0]["Puntaje Obtenido"], "100")
        self.assertEqual(out.iloc[0]["Notas"], "")
        self.assertEqual(out.iloc[1]["Puntaje Obtenido"], "-")
        self.assertEqual(out.iloc[1]["Rango Clínico"], "Cualitativo / Ver Notas")


class TestMotorIA(unittest.TestCase):
    def test_system_prompt_y_prompt_caso_omision_vacios(self):
        self.assertIn("No inventes pruebas", motor_ia.construir_system_prompt())
        prompt = motor_ia.construir_prompt_caso(
            {
                "nombre": "Caso ficticio",
                "impresion_destacar": "Síntesis local",
                "tabla_z_markdown": "Grilla privada",
                "observaciones_cualitativas": {"Memoria y Aprendizaje": "", "Atención": "Descenso sostenido"},
            }
        )
        self.assertEqual(prompt, '{"dominios": {"Atención": "Descenso sostenido"}}')

    def test_rechaza_secciones_nuevas_y_adjuntos_no_cargados(self):
        ejemplos = (
            '{"dominios":{"Dominio inventado":"Hallazgo"},"datos_adjuntos":""}',
            '{"dominios":{},"datos_adjuntos":"Resultado inventado"}',
            '{"dominios":{},"datos_adjuntos":"","conclusiones":"Diagnóstico inventado"}',
            '{"dominios":{"Atención":["no es texto"]},"datos_adjuntos":""}',
        )
        for texto in ejemplos:
            with self.subTest(texto=texto), self.assertRaises(motor_ia.RespuestaRedaccionInvalida):
                motor_ia.validar_redaccion(texto, {"Atención": "Nota de prueba"}, False)

    def test_conserva_nota_original_si_la_redaccion_cambia_cifras(self):
        salida = motor_ia.validar_redaccion(
            '{"dominios":{"Lectura":"Registró 16 respuestas."},"datos_adjuntos":""}',
            {"Lectura": "Registró 15 respuestas."},
            False,
        )
        self.assertEqual(salida["dominios"], {})

    def test_resolver_api_key_con_permission_error(self):
        class SecretsQueFalla:
            def get(self, *_args, **_kwargs):
                raise PermissionError("Acceso denegado")

        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_sec = Path(tmpdir) / "secrets.toml"
            ruta_sec.write_text('GEMINI_API_KEY = "clave-desde-archivo"\n', encoding="utf-8")

            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                self.assertEqual(
                    motor_ia.resolver_api_key(SecretsQueFalla(), secrets_file=ruta_sec),
                    "clave-desde-archivo",
                )

            with patch.dict(os.environ, {"GEMINI_API_KEY": "clave-env"}, clear=False):
                self.assertEqual(
                    motor_ia.resolver_api_key(SecretsQueFalla(), secrets_file=ruta_sec),
                    "clave-env",
                )

    def test_preparar_adjuntos_pdf_mayusculas_y_grande(self):
        fake_client = MagicMock()
        fake_uploaded = MagicMock(uri="files/abc123")
        fake_uploaded.name = "files/abc123"
        fake_uploaded.state = "ACTIVE"
        fake_client.files.upload.return_value = fake_uploaded

        archivos = [
            {"name": "REPORTE.PDF", "bytes": b"%PDF-1.4 peque"},
            {"name": "notas.csv", "bytes": "col1,col2\n1,2".encode("utf-8")},
            {"name": "grande.pdf", "bytes": b"%PDF-1.4 " + b"0" * 1024},
        ]
        # Usar umbral bajo para ejercitar la ruta de Files API con grande.pdf
        bloques, temp_paths, uploaded_names = motor_ia.preparar_adjuntos_interaccion(
            archivos, fake_client, max_inline_bytes=100
        )
        try:
            self.assertEqual(len(bloques), 5)
            self.assertEqual(bloques[1]["type"], "document")
            self.assertIn("data", bloques[1])
            self.assertEqual(bloques[2]["type"], "text")
            self.assertIn("Adjunto 2 (csv)", bloques[2]["text"])
            self.assertNotIn("notas.csv", bloques[2]["text"])
            self.assertEqual(bloques[4], {"type": "document", "uri": "files/abc123", "mime_type": "application/pdf"})
            self.assertEqual(uploaded_names, ["files/abc123"])
            self.assertEqual(len(temp_paths), 1)
            self.assertTrue(os.path.exists(temp_paths[0]))
        finally:
            for p in temp_paths:
                if os.path.exists(p):
                    os.remove(p)

    def test_generar_informe_clinico_mock_y_limpieza_en_error(self):
        fake_client = MagicMock()
        fake_uploaded = MagicMock(uri="files/remoto-1")
        fake_uploaded.name = "files/remoto-1"
        fake_uploaded.state = "ACTIVE"
        fake_client.files.upload.return_value = fake_uploaded
        fake_client.interactions.create.return_value = MagicMock(output_text='{"dominios":{},"datos_adjuntos":"Adjunto 1, página 2. Resultado registrado."}')

        with patch("motor_ia.genai.Client", return_value=fake_client):
            texto = motor_ia.generar_informe_clinico(
                api_key="test-key",
                modelo="gemini-4-hydrogen",
                thinking_level="xhigh",
                datos_caso={"nombre": "Paciente Test", "hc": "DEMO-123", "tabla_z_markdown": "| Puntaje |\n| --- |\n| +0.40 |"},
                guia_estilo="Guía de prueba",
                archivos=[{"name": "CPT.PDF", "bytes": b"%PDF-1.4 inline"}],
                store=False,
            )

        self.assertIn("Adjunto 1, página 2. Resultado registrado.", texto)
        self.assertIn("verificar con el original", texto)
        self.assertIn("Paciente Test", texto)
        self.assertIn("| +0.40 |", texto)
        call_kwargs = fake_client.interactions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-4-hydrogen")
        self.assertNotIn("Paciente Test", str(call_kwargs["input"]))
        self.assertNotIn("DEMO-123", str(call_kwargs["input"]))
        self.assertNotIn("+0.40", str(call_kwargs["input"]))
        self.assertIn("Guía de prueba", str(call_kwargs["input"]))
        self.assertFalse(call_kwargs["store"])
        self.assertEqual(call_kwargs["generation_config"]["thinking_level"], "xhigh")
        self.assertNotIn("temperature", call_kwargs["generation_config"])

        # Simular fallo de API con archivo subido > umbral para verificar cleanup en finally
        fake_client.interactions.create.side_effect = RuntimeError("Fallo de red simulado")
        with patch("motor_ia.MAX_INLINE_PDF_BYTES", 5), patch(
            "motor_ia.genai.Client", return_value=fake_client
        ):
            with self.assertRaises(RuntimeError):
                motor_ia.generar_informe_clinico(
                    api_key="test-key",
                    modelo="gemini-4-hydrogen",
                    thinking_level="high",
                    datos_caso={"nombre": "Paciente Error"},
                    archivos=[{"name": "grande.pdf", "bytes": b"%PDF-1.4 contenido_largo"}],
                    store=False,
                )
        fake_client.files.delete.assert_called_once_with(name="files/remoto-1")


    def test_pdf_grande_espera_active_antes_de_generar(self):
        cliente = MagicMock()
        cliente.files.upload.return_value = SimpleNamespace(name="files/demo", state="PROCESSING")
        cliente.files.get.return_value = SimpleNamespace(name="files/demo", state="ACTIVE", uri="uri-demo")
        cliente.interactions.create.return_value.output_text = '{"dominios":{},"datos_adjuntos":"Dato ficticio"}'
        archivo = {"name": "demo.pdf", "bytes": b"%PDF-1.4" + b"0" * 20_000_000}
        with patch("motor_ia.genai.Client", return_value=cliente), patch("motor_ia.time.sleep"):
            borrador_final = motor_ia.generar_informe_clinico("clave", "modelo", "low", {}, [archivo])
        self.assertIn("Dato ficticio", borrador_final)
        self.assertEqual([llamada[0] for llamada in cliente.mock_calls], [
            "files.upload", "files.get", "interactions.create", "files.delete",
        ])

    def test_polling_de_adjuntos_y_limpieza_si_falla_procesamiento(self):
        cliente = MagicMock()
        cliente.files.upload.return_value = SimpleNamespace(name="files/demo", state="PROCESSING")
        cliente.files.get.return_value = SimpleNamespace(name="files/demo", state="FAILED")
        archivos = [{"name": "demo.pdf", "bytes": b"%PDF-1.4 bytes de prueba"}]
        with patch("motor_ia.genai.Client", return_value=cliente), patch("motor_ia.time.sleep"), patch(
            "motor_ia.MAX_INLINE_PDF_BYTES", 2
        ):
            with self.assertRaisesRegex(ValueError, "procesar"):
                motor_ia.generar_informe_clinico("clave", "modelo", "low", {}, archivos)

        cliente.files.get.assert_called_once_with(name="files/demo")
        cliente.files.delete.assert_called_once_with(name="files/demo")
        cliente.interactions.create.assert_not_called()
        ruta_temporal = cliente.files.upload.call_args.kwargs["file"]
        self.assertFalse(Path(ruta_temporal).exists())

    def test_adjunta_imagen_y_extrae_parrafos_y_tabla_word(self):
        archivo_word = io.BytesIO()
        doc = Document()
        doc.add_paragraph("Nota del caso ficticio")
        doc.add_table(rows=1, cols=1).cell(0, 0).text = "Puntaje ficticio"
        doc.save(archivo_word)
        bloques, _, _ = motor_ia.preparar_adjuntos_interaccion(
            [{"name": "foto.webp", "bytes": b"imagen"}, {"name": "ficha.docx", "bytes": archivo_word.getvalue()}],
            MagicMock(),
        )
        self.assertEqual(bloques[1]["mime_type"], "image/webp")
        self.assertIn("Adjunto 2 (docx)", bloques[2]["text"])
        self.assertIn("Nota del caso ficticio\nPuntaje ficticio", bloques[2]["text"])

    def test_excel_extrae_solo_filas_con_datos_y_conserva_cero(self):
        archivo = io.BytesIO()
        with ZipFile(archivo, "w") as libro:
            libro.writestr("xl/workbook.xml", "<workbook/>")
        hoja = SimpleNamespace(title="Datos", max_row=3, max_column=2, values=[(None, None), (0, "dato"), (" ", None)])
        libro_simulado = MagicMock()
        libro_simulado.worksheets = [hoja]
        modulo = SimpleNamespace(load_workbook=MagicMock(return_value=libro_simulado))
        with patch.dict("sys.modules", {"openpyxl": modulo}):
            texto = motor_ia._texto_adjunto(archivo.getvalue(), ".xlsx")
        self.assertEqual(texto, "Datos, fila 2: 0 | dato")
        libro_simulado.close.assert_called_once()


class TestExportadorDocx(unittest.TestCase):
    def test_generacion_docx_markdown_tablas_y_colores(self):
        md = """# INFORME DE EVALUACIÓN NEUROPSICOLÓGICA

## 1. Análisis Cualitativo
*Introducción teórica en cursiva sobre la función.*

El rendimiento en memoria operativa fue **adecuado** con ***excelente*** disposición.
3 * 4 = 12 (no debe romperse por asterisco aritmético).

| Prueba / Subtest | Puntaje | Puntaje Z | Rango Clínico |
| --- | --- | --- | --- |
| WISC-V - ICV | 106 | +0.40 | Normal |
| WISC-V - IMT | 78 | -1.47 | Dificultad |
| CPT-II - Omisiones | 75 | -2.50 | Déficit |

## 2. Sugerencias
- Primera viñeta con **negrita**
- Segunda viñeta
1. Paso numerado uno
2. Paso numerado dos
"""
        docx_bytes = exportador_docx.generar_docx_bytes(
            texto_markdown=md,
            datos_filiacion={"nombre": "Pérez, Mateo", "fecha_eval": "20/10/2026"},
            incluir_tabla_filiacion=False,
            incluir_tabla_z=False,
            firma_profesional="Lic. Juan Machado — MP 1234",
        )
        doc = Document(io.BytesIO(docx_bytes))
        textos_parrafos = [p.text for p in doc.paragraphs if p.text.strip()]

        # Sin marcas literales de markdown ni H1 duplicado
        todo_texto = "\n".join(textos_parrafos)
        self.assertNotIn("**", todo_texto)
        self.assertEqual(todo_texto.count("INFORME DE EVALUACIÓN NEUROPSICOLÓGICA"), 1)
        self.assertIn("3 * 4 = 12", todo_texto)
        self.assertIn("Lic. Juan Machado — MP 1234", todo_texto)

        # Runs en negrita y cursiva aplicados correctamente
        runs_bold = [r.text for p in doc.paragraphs for r in p.runs if r.bold]
        runs_italic = [r.text for p in doc.paragraphs for r in p.runs if r.italic]
        self.assertIn("adecuado", runs_bold)
        self.assertIn("excelente", runs_bold)
        self.assertIn("excelente", runs_italic)

        # Tabla Word generada con sombreado clínico XML
        self.assertEqual(len(doc.tables), 1)
        tabla = doc.tables[0]
        self.assertEqual(len(tabla.rows), 4)
        shd_deficit = tabla.rows[3].cells[3]._tc.tcPr.find(qn("w:shd"))
        self.assertIsNotNone(shd_deficit)
        self.assertEqual(shd_deficit.get(qn("w:fill")), "FADBD8")


    def test_grilla_visual_membrete_y_confidencialidad(self):
        df = pd.DataFrame({"Dominio / Prueba / Subtest": ["Prueba 1", "Prueba 2", "Texto"], "Puntaje Z": ["-1.64", "+4.10", "N/A"]})
        doc = Document(io.BytesIO(exportador_docx.generar_docx_bytes(
            "# Informe de prueba", datos_filiacion={"institucion": "Servicio de ejemplo"},
            df_puntajes=df, incluir_grilla_visual=True, incluir_confidencialidad=True,
        )))
        tabla = doc.tables[0]
        self.assertEqual(len(tabla.columns), 20)
        self.assertEqual(len(tabla.rows), 4)
        self.assertEqual(tabla.rows[1].cells[10].text, "0")
        self.assertEqual(tabla.rows[2].cells[5].text, "X")
        self.assertEqual(tabla.rows[3].cells[19].text, "X")
        self.assertIn("Servicio de ejemplo", doc.sections[0].header.paragraphs[0].text)
        self.assertIn("Confidencial", doc.sections[0].footer.paragraphs[0].text)


class TestAnalisisClinico(unittest.TestCase):
    def fila(self, nombre, valor, escala, nota=""):
        return {"Dominio / Prueba / Subtest": nombre, "Puntaje": valor, "Tipo de Escala": escala, "Observación": nota}

    def test_percentil_inverso_y_tiempo_bidireccional(self):
        c = catalogo_clinico
        self.assertEqual(psicometria.calcular_z_y_rango(95, c.ESCALA_PERCENTIL_INVERSO), (-1.64, "Dificultad"))
        self.assertEqual(psicometria.calcular_z_y_rango(95, c.ESCALA_PERCENTIL_LEGADO), (1.64, "Normal Alto"))
        self.assertEqual(psicometria.redondear_z_a_tercio(-1.64), -5/3)
        self.assertEqual(psicometria.redondear_z_a_tercio(3.8), 3.0)
        filas = [
            self.fila("Nesplora Aula - Omisiones Totales", 95, c.ESCALA_PERCENTIL_DIRECTO),
            self.fila("CPT-II - Tiempo de Reacción (Hit RT)", 39, c.ESCALA_T_INVERSO),
        ]
        df = pd.DataFrame(filas)
        self.assertEqual(len(psicometria.revisar_carga_puntajes(df)[0]), 1)
        self.assertEqual(psicometria.procesar_tabla_puntajes(df).iloc[1]["Rango Clínico"], "Atípico rápido")

    def test_comparaciones_usan_la_misma_bateria_y_escala(self):
        c = catalogo_clinico
        filas = [
            self.fila("WISC-V - Índice de Comprensión Verbal (ICV)", 120, c.ESCALA_CI),
            self.fila("WISC-V - Índice de Memoria de Trabajo (IMT)", 90, c.ESCALA_CI),
            self.fila("WISC-V - Índice de Capacidad General (ICG)", 122, c.ESCALA_CI),
            self.fila("WISC-V - Índice de Competencia Cognitiva (ICC)", 104, c.ESCALA_CI),
            self.fila("CPT-3 - Tiempo de Reacción (Hit RT)", 38, c.ESCALA_T_REACCION),
            self.fila("CPT-3 - Comisiones (T)", 64, c.ESCALA_T_INVERSO),
            self.fila("Nesplora Aula - Omisiones Totales", 66, c.ESCALA_T_INVERSO),
            self.fila("Nesplora Aula - Comisiones Totales", 45, c.ESCALA_T_INVERSO),
        ]
        indicadores = analisis_clinico.analizar_resultados(filas, ["WISC-V"], 204)
        self.assertTrue(any("fuera del rango" in i.detalle for i in indicadores))
        self.assertTrue(any("Amplitud 30" in i.detalle and "2/5" in i.detalle for i in indicadores))
        self.assertTrue(any("ICG menos ICC: +18" in i.detalle for i in indicadores))
        self.assertTrue(any(i.prueba == "CPT-3" and "velocidad y precisión" in i.detalle for i in indicadores))
        self.assertTrue(any(i.prueba == "Nesplora Aula" and "frecuencia de respuesta" in i.detalle for i in indicadores))
        ambiguas = filas + [self.fila("CPT-3 - Comisiones (T)", 42, c.ESCALA_T_INVERSO)]
        self.assertFalse(any("velocidad y precisión" in i.detalle for i in analisis_clinico.analizar_resultados(ambiguas)))

    def test_derivados_memoria_y_cortes(self):
        c = catalogo_clinico
        filas = [
            self.fila("Stroop Golden - P bruto", 100, c.ESCALA_BRUTO),
            self.fila("Stroop Golden - C bruto", 60, c.ESCALA_BRUTO),
            self.fila("Stroop Golden - PC bruto", 30, c.ESCALA_BRUTO),
            self.fila("Trail Making Test - Parte A (segundos)", 30, c.ESCALA_SEGUNDOS),
            self.fila("Trail Making Test - Parte B (segundos)", 93, c.ESCALA_SEGUNDOS),
            self.fila("RAVLT - Total Aprendizaje (Ensayos A1-A5)", 0.10, c.ESCALA_Z_DIRECTO),
            self.fila("RAVLT - Recuerdo Diferido (A7)", -1.9, c.ESCALA_Z_DIRECTO),
            self.fila("RAVLT - Reconocimiento", -1.4, c.ESCALA_Z_DIRECTO),
            self.fila("BRIEF-2 - Inhibición", 69, c.ESCALA_T_INVERSO),
            self.fila("SNAP-IV - Desatención (suma 0 a 27, Planilla Memoria)", 15, c.ESCALA_BRUTO),
            self.fila("Vineland Forma B - Edad social (meses)", 90, c.ESCALA_BRUTO),
        ]
        resumen = "\n".join(x.detalle for x in analisis_clinico.analizar_resultados(filas, edad_meses=120))
        for texto in ("37.50", "-7.50", "3.10", "+63.00", "hipótesis de dificultad de retención",
                      "potencialmente clínico", "corte de la Planilla Memoria", "75.00"):
            self.assertIn(texto, resumen)

    def test_planilla_autoestima_vineland_y_empate_durand(self):
        bruto = catalogo_clinico.ESCALA_BRUTO
        filas = [
            self.fila("Autoestima - Corporal (Planilla Memoria)", 12, bruto),
            self.fila("Autoestima - Social (Planilla Memoria)", 13, bruto),
            self.fila("Vineland Forma B - Edad social (meses)", 270, bruto),
            *[self.fila(f"Durand MAS - {funcion} (suma 0 a 24)", valor, bruto)
              for funcion, valor in zip(("Sensorial", "Escape", "Atención", "Tangible"), (8, 16, 16, 4))],
        ]
        salida = analisis_clinico.analizar_resultados(filas, edad_meses=360)
        por_prueba = {i.prueba: i.detalle for i in salida}
        self.assertIn("Área corporal", por_prueba["Autoestima"])
        self.assertNotIn("social", por_prueba["Autoestima"])
        self.assertIn("sin tope 75.00", por_prueba["Vineland Forma B"])
        self.assertIn("90, normal promedio", por_prueba["Vineland Forma B"])
        self.assertIn("Mayor media: Escape / Atención", por_prueba["Durand MAS"])



class TestMemoriaYBorrador(unittest.TestCase):
    def test_guia_solo_lectura(self):
        sesion = MagicMock()
        sesion.get.return_value.json.return_value = {
            "title": "Guía de prueba",
            "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "Texto de estilo\n"}}]}}]},
        }
        with patch("memoria_drive.google.auth.default", return_value=(object(), "proyecto")), patch(
            "memoria_drive.AuthorizedSession"
        ) as cliente:
            cliente.return_value.__enter__.return_value = sesion
            self.assertEqual(memoria_drive.leer_guia("ID_demo"), ("Guía de prueba", "Texto de estilo"))
            with self.assertRaises(ValueError):
                memoria_drive.leer_guia("../ID_demo")
        self.assertEqual(sesion.get.call_args.args[0], "https://docs.googleapis.com/v1/documents/ID_demo")
        with self.assertRaises(ValueError):
            memoria_drive.validar_guia(" ")

    def test_exporta_grilla_con_signo_y_notas_literales(self):
        datos = pd.DataFrame([{"Prueba": "Prueba_A", "Puntaje Z": "+0.40", "Notas": "A | B\n*C*"}])
        tabla = borrador.grilla_markdown(datos)
        md = borrador.construir_borrador({"tabla_z_markdown": tabla})
        doc = Document(io.BytesIO(exportador_docx.generar_docx_bytes(md)))
        self.assertEqual([celda.text for celda in doc.tables[0].rows[1].cells], ["Prueba_A", "+0.40", "A | B *C*"])


    def test_informe_psicopedagogico_con_fuentes_e_integracion(self):
        md = borrador.construir_borrador(
            {
                "modelos_seleccionados": ["Evaluación Psicopedagógica Infantil"],
                "quien_deriva": "Primera observación\nSegunda observación",
                "pruebas_usadas": ["Prueba ficticia"],
                "fuentes_resultados": "Protocolo de práctica",
                "tabla_z_markdown": "| Resultado |\n| --- |\n| +0.50 |",
                "observaciones_cualitativas": {"Lectura": "Observación original", "Cálculo": ""},
                "fortalezas": "Fortaleza consignada",
                "limitaciones": "Limitación explícita",
                "fundamento_recomendaciones": "Vínculo con el hallazgo",
                "detalle_escolares": "- Recomendación acordada",
            },
            redaccion={"dominios": {"Lectura": "Observación revisada"}, "datos_adjuntos": ""},
        )
        self.assertTrue(md.startswith("# Evaluación Psicopedagógica Infantil"))
        self.assertLess(md.index("## Técnicas implementadas"), md.index("## Resultados registrados"))
        self.assertIn("Primera observación\n\nSegunda observación", md)
        self.assertIn("### Lectura\n\nObservación revisada", md)
        self.assertNotIn("### Cálculo", md)
        self.assertIn("Protocolo de práctica", md)
        self.assertIn("+0.50", md)
        self.assertIn("Completar la integración profesional", md)
        self.assertIn("Vínculo con el hallazgo", md)
        self.assertIn("### Para la escuela", md)
        self.assertNotIn("### Terapéuticas", md)

    def test_revision_identifica_filas_con_datos_invalidos_y_posibles_duplicados(self):
        columnas = ["Dominio / Prueba / Subtest", "Puntaje", "Tipo de Escala", "Observación"]
        pc = catalogo_clinico.ESCALA_PERCENTIL
        filas = [
            ["Sin completar", None, "", ""],
            ["", 50, pc, ""],
            ["Prueba A", 0, pc, ""],
            ["prueba a", None, "", "Segunda condición"],
            ["Prueba B", 30, "", ""],
            ["Prueba C", 10, catalogo_clinico.ESCALA_BRUTO, ""],
        ]
        errores, avisos = psicometria.revisar_carga_puntajes(pd.DataFrame(filas, columns=columnas))
        self.assertEqual([mensaje.split(":")[0] for mensaje in errores], ["Fila 2", "Fila 3", "Fila 5"])
        self.assertEqual(len(avisos), 1)
        self.assertIn("Filas 3 y 4", avisos[0])


class TestAppStreamlit(unittest.TestCase):
    def test_apptest_flujo_completo_y_persistencia(self):
        from streamlit.testing.v1 import AppTest

        app_path = str(Path(__file__).resolve().parent.parent / "app.py")
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            at = AppTest.from_file(app_path, default_timeout=20)
            at.run()
            self.assertFalse(at.exception, f"Excepción al arrancar app.py: {at.exception}")

            # Verificar calculadora Z con Percentil en sidebar
            at.sidebar.selectbox(key="calc_escala").set_value(catalogo_clinico.ESCALA_PERCENTIL).run()
            self.assertFalse(at.exception)
            at.sidebar.number_input[0].set_value(91.0).run()
            self.assertEqual(at.sidebar.metric[0].value, "Z = +1.34")

            # Verificar cálculo automático de edad exacta desde fechas
            at.date_input[0].set_value(date(2017, 6, 10)).run()
            at.date_input[1].set_value(date(2026, 10, 20)).run()
            self.assertEqual(at.session_state["edad_texto_input"], "9 años, 4 meses")

            # Seleccionar y luego deseleccionar baterías sin errores
            at.multiselect[1].set_value(["WISC-V", "CPT-II"]).run()
            self.assertFalse(at.exception)
            at.multiselect[1].set_value(["WISC-V"]).run()
            self.assertFalse(at.exception)

            at.text_input[0].set_value("Caso de prueba").run()
            with patch("motor_ia.generar_informe_clinico") as generar:
                at.button[0].click().run()
                generar.assert_not_called()
                self.assertFalse(at.exception)
                self.assertIn("Caso de prueba", at.session_state["informe_actual"])
                self.assertIn("WISC-V", at.session_state["informe_actual"])

                siguiente = next(campo for campo in at.text_area if campo.label.startswith("Funcionamiento Intelectual"))
                siguiente.set_value("Observación sintética de prueba").run()
                self.assertTrue(all(boton.proto.disabled for boton in at.get("download_button")))
                at.sidebar.toggle[0].set_value(True).run()
                if at.sidebar.text_input:
                    at.sidebar.text_input[0].set_value("fake-api-key").run()
                at.button[0].click().run()
                generar.assert_not_called()
                at.checkbox(key="confirmar_envio_gemini_0").check().run()
                generar.return_value = "## Conclusiones\n\nTexto asistido de prueba"
                at.button[0].click().run()
                generar.assert_called_once()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.error), 0)

            at.sidebar.number_input[0].set_value(50.0).run()
            self.assertIn("Texto asistido de prueba", at.session_state["informe_actual"])
            self.assertFalse(any(boton.proto.disabled for boton in at.get("download_button")))

            deprecations = [
                str(w.message)
                for w in captured
                if "use_container_width" in str(w.message)
            ]
            self.assertEqual(deprecations, [], f"Warnings de deprecación detectados: {deprecations}")


if __name__ == "__main__":
    unittest.main()
