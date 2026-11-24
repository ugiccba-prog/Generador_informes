"""Suite de tests integrales para la Plataforma Clínica de Informes Neuropsicológicos."""

from datetime import date
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import warnings

from docx import Document
from docx.oxml.ns import qn
import pandas as pd

import catalogo_clinico
import exportador_docx
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
        sys_prompt = motor_ia.construir_system_prompt()
        self.assertIn("Limítrofe (Dificultad / Déficit)", sys_prompt)
        self.assertIn("Normal Alto (Tendencia superior)", sys_prompt)
        self.assertIn("Woodcock-Muñoz", sys_prompt)
        self.assertIn("Hit RT", sys_prompt)
        self.assertIn(catalogo_clinico.INTRODUCCIONES_DOMINIOS["intelectual"], sys_prompt)

        prompt_caso = motor_ia.construir_prompt_caso(
            {
                "nombre": "Ana Gómez",
                "conducta": {"Contacto y vínculo": "Adecuado", "Predisposición": ""},
                "observaciones_cualitativas": {"Memoria y Aprendizaje": "", "Atención": "Descenso sostenido"},
            }
        )
        self.assertIn("- **Contacto y vínculo:** Adecuado", prompt_caso)
        self.assertNotIn("Predisposición", prompt_caso)
        self.assertNotIn("Memoria y Aprendizaje", prompt_caso)
        self.assertIn("- **Atención:** Descenso sostenido", prompt_caso)

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
            self.assertEqual(len(bloques), 3)
            self.assertEqual(bloques[0]["type"], "document")
            self.assertIn("data", bloques[0])
            self.assertEqual(bloques[1]["type"], "text")
            self.assertIn("notas.csv", bloques[1]["text"])
            self.assertEqual(bloques[2], {"type": "document", "uri": "files/abc123", "mime_type": "application/pdf"})
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
        fake_client.files.upload.return_value = fake_uploaded
        fake_client.interactions.create.return_value = MagicMock(output_text="# INFORME\n\nTexto final")

        with patch("motor_ia.genai.Client", return_value=fake_client):
            texto = motor_ia.generar_informe_clinico(
                api_key="test-key",
                modelo="gemini-4-hydrogen",
                thinking_level="xhigh",
                datos_caso={"nombre": "Paciente Test"},
                archivos=[{"name": "CPT.PDF", "bytes": b"%PDF-1.4 inline"}],
                store=False,
            )

        self.assertEqual(texto, "# INFORME\n\nTexto final")
        call_kwargs = fake_client.interactions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-4-hydrogen")
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
            at.sidebar.selectbox[2].set_value(catalogo_clinico.ESCALA_PERCENTIL).run()
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

            # Simular generación con motor_ia mockeado y verificar persistencia tras rerun
            at.text_input[0].set_value("Pérez, Mateo").run()
            if at.sidebar.text_input:
                at.sidebar.text_input[0].set_value("fake-api-key").run()

            with patch(
                "motor_ia.generar_informe_clinico",
                return_value="# INFORME DE PRUEBA\n\n## Conclusiones\nDesempeño **adecuado**.",
            ):
                at.button[0].click().run()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.error), 0, f"Errores en UI: {[e.value for e in at.error]}")

            self.assertIn("INFORME DE PRUEBA", at.session_state["informe_actual"])
            # Rerun adicional (por ejemplo cambio en calculadora): el informe persiste
            at.sidebar.number_input[0].set_value(50.0).run()
            self.assertIn("INFORME DE PRUEBA", at.session_state["informe_actual"])

            deprecations = [
                str(w.message)
                for w in captured
                if "use_container_width" in str(w.message)
            ]
            self.assertEqual(deprecations, [], f"Warnings de deprecación detectados: {deprecations}")


if __name__ == "__main__":
    unittest.main()
