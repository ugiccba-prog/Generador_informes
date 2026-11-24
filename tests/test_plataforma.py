"""Suite de tests integrales para la Plataforma Clínica de Informes Neuropsicológicos (Fase 2)."""

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
import openpyxl
import pandas as pd

import analisis_clinico
import catalogo_clinico
import exportador_docx
import generador_local
import importador_archivos
import motor_ia
import psicometria


class TestCatalogoClinico(unittest.TestCase):
    def test_escalas_y_subpruebas_sin_hints_ui(self):
        self.assertIn(catalogo_clinico.ESCALA_V_SCALE, catalogo_clinico.ESCALAS_DISPONIBLES)
        self.assertIn(catalogo_clinico.ESCALA_PERCENTIL_DIRECTO, catalogo_clinico.ESCALAS_DISPONIBLES)
        self.assertIn(catalogo_clinico.ESCALA_PERCENTIL_INVERSO, catalogo_clinico.ESCALAS_DISPONIBLES)
        self.assertIn(catalogo_clinico.ESCALA_PERCENTIL_INVERSO, catalogo_clinico.ESCALAS_CALCULADORA)

        todas_subpruebas = [
            nombre
            for lista in catalogo_clinico.CATALOGO_SUBPRUEBAS.values()
            for nombre, _ in lista
        ]
        for sub in todas_subpruebas:
            self.assertNotIn("Colocar Edad Equivalente", sub)
            self.assertNotIn("Detallar en Notas", sub)

        escalas_set = set(catalogo_clinico.ESCALAS_DISPONIBLES)
        for bateria, lista in catalogo_clinico.CATALOGO_SUBPRUEBAS.items():
            self.assertTrue(len(lista) > 0, f"Batería vacía: {bateria}")
            for nombre, esc in lista:
                self.assertIn(esc, escalas_set, f"Escala inválida en {nombre}: {esc}")

        # Cobertura de nuevas entradas alineadas a Planilla Modelo
        self.assertIn("Escala de Autoestima", catalogo_clinico.CATALOGO_SUBPRUEBAS)
        self.assertEqual(len(catalogo_clinico.CATALOGO_SUBPRUEBAS["Escala Durand"]), 4)
        self.assertEqual(
            catalogo_clinico.CATALOGO_SUBPRUEBAS["Figura Compleja de Rey"][0][1],
            catalogo_clinico.ESCALA_PERCENTIL_DIRECTO,
        )
        tomal_nombres = [n for n, _ in catalogo_clinico.CATALOGO_SUBPRUEBAS["TOMAL"]]
        self.assertTrue(any("(IMV)" in n for n in tomal_nombres))
        self.assertTrue(any("(IRD)" in n for n in tomal_nombres))

        # Verificar consistencia de presets y perfiles de recomendaciones
        for cfg in catalogo_clinico.PRESETS_BATERIAS.values():
            for m in cfg["modelos"]:
                self.assertIn(m, catalogo_clinico.MODELOS_INFORME)
            for p in cfg["pruebas"]:
                self.assertIn(p, catalogo_clinico.CATALOGO_SUBPRUEBAS)

        for perf in catalogo_clinico.PERFILES_RECOMENDACIONES.values():
            for k in perf["terapeuticas"]:
                self.assertIn(k, catalogo_clinico.BANCO_SUGERENCIAS["terapeuticas"])
            for k in perf["escolares"]:
                self.assertIn(k, catalogo_clinico.BANCO_SUGERENCIAS["escolares"])

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

    def test_regresion_ci_vscale_y_percentiles_directo_inverso(self):
        self.assertEqual(
            psicometria.calcular_z_y_rango(132, catalogo_clinico.ESCALA_CI),
            (2.13, "Normal Alto (Tendencia superior)"),
        )
        self.assertEqual(
            psicometria.calcular_z_y_rango(81, catalogo_clinico.ESCALA_CI),
            (-1.27, "Normal (Tendencia baja)"),
        )
        # v-scale Vineland (M=15, DE=3)
        self.assertEqual(psicometria.calcular_z_y_rango(15, catalogo_clinico.ESCALA_V_SCALE), (0.0, "Normal"))
        self.assertEqual(psicometria.calcular_z_y_rango(9, catalogo_clinico.ESCALA_V_SCALE), (-2.0, "Dificultad"))

        # Percentil Directo vs Inverso
        self.assertEqual(
            psicometria.calcular_z_y_rango(95, catalogo_clinico.ESCALA_PERCENTIL_DIRECTO),
            (1.64, "Normal Alto"),
        )
        self.assertEqual(
            psicometria.calcular_z_y_rango(95, catalogo_clinico.ESCALA_PERCENTIL_INVERSO),
            (-1.64, "Dificultad"),
        )
        z_bad, r_bad = psicometria.calcular_z_y_rango(100, catalogo_clinico.ESCALA_PERCENTIL_INVERSO)
        self.assertIsNone(z_bad)
        self.assertIn("fuera de rango", r_bad.lower())

    def test_hit_rt_bidireccional_y_redondeo_tercio(self):
        # Hit RT < 40 en T inverso es atípico rápido/impulsivo (no Normal Alto)
        z_rt, r_rt = psicometria.calcular_z_y_rango(
            35.0,
            catalogo_clinico.ESCALA_T_INVERSO,
            nombre_subtest="CPT-II - Tiempo de Reacción (Hit RT)",
        )
        self.assertEqual(z_rt, 1.5)
        self.assertEqual(r_rt, "Atípico rápido (estilo impulsivo)")
        self.assertEqual(psicometria.categoria_color_rango(r_rt), "dificultad")

        # Hit RT Std Error / Variabilidad T=35 SÍ es Normal Alto
        z_var, r_var = psicometria.calcular_z_y_rango(
            35.0,
            catalogo_clinico.ESCALA_T_INVERSO,
            nombre_subtest="CPT-II - Variabilidad / Consistencia (Hit RT Std Error)",
        )
        self.assertEqual(z_var, 1.5)
        self.assertEqual(r_var, "Normal Alto")

        # Redondeo a tercios
        self.assertEqual(psicometria.redondear_z_a_tercio(-1.47), -1.33)
        self.assertEqual(psicometria.redondear_z_a_tercio(-1.55), -1.67)
        self.assertEqual(psicometria.redondear_z_a_tercio(-4.50), -3.0)
        self.assertEqual(psicometria.redondear_z_a_tercio(4.20), 3.0)

    def test_metricas_derivadas_stroop_tmt_ravlt_vineland_y_edad(self):
        stroop = psicometria.calcular_stroop_golden(90, 60, 40)
        self.assertEqual(stroop["pc_prima"], 36.0)
        self.assertEqual(stroop["interferencia"], 4.0)

        tmt = psicometria.calcular_tmt_metricas(25, 85)
        self.assertEqual(tmt["diferencia_b_a"], 60.0)
        self.assertEqual(tmt["ratio_b_a"], 3.4)
        self.assertTrue(tmt["alerta_ejecutiva"])

        rav = psicometria.calcular_ravlt_metricas([5, 7, 9, 10, 12], b1=5, a6=10, a7=9)
        self.assertEqual(rav["total_a1_a5"], 43.0)
        self.assertEqual(rav["ganancia_aprendizaje"], 7.0)
        self.assertEqual(rav["retencion_pct"], 75.0)

        vin = psicometria.calcular_vineland_forma_b(9.0, 10.0)
        self.assertEqual(vin["cociente_social"], 90)
        self.assertEqual(vin["categoria"], "Normal promedio")

        # Redondeo al entero más cercano (8.95 / 10 * 100 = 89.5 -> 90, no 89.5 sin clasificar)
        vin_borde = psicometria.calcular_vineland_forma_b(8.95, 10.0)
        self.assertEqual(vin_borde["cociente_social"], 90)
        self.assertEqual(vin_borde["categoria"], "Normal promedio")

        # Tope cronológico de 25 años en Vineland Forma B
        vin_adulto = psicometria.calcular_vineland_forma_b(18.0, 32.0)
        self.assertEqual(vin_adulto["edad_cronologica_efectiva"], 25.0)
        self.assertEqual(vin_adulto["cociente_social"], 72)
        self.assertEqual(vin_adulto["categoria"], "Fronterizo")

        self.assertEqual(psicometria.calcular_edad_exacta(date(2017, 6, 10), date(2026, 10, 20)), (9, 4))
        self.assertEqual(psicometria.formatear_edad(9, 4), "9 años, 4 meses")

    def test_procesar_tabla_sanitiza_saltos_de_linea(self):
        df_in = pd.DataFrame(
            [
                {
                    "Dominio / Prueba / Subtest": "CPT-II - Tiempo de Reacción (Hit RT)",
                    "Puntaje": 36.0,
                    "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO,
                    "Observación": "Línea 1\nLínea 2",
                }
            ]
        )
        out = psicometria.procesar_tabla_puntajes(df_in)
        self.assertEqual(out.iloc[0]["Notas"], "Línea 1 Línea 2")
        self.assertEqual(out.iloc[0]["Rango Clínico"], "Atípico rápido (estilo impulsivo)")


class TestAnalisisClinico(unittest.TestCase):
    def test_alertas_wechsler_cpt_memoria_cuestionarios_y_baremos(self):
        df_in = pd.DataFrame(
            [
                {"Dominio / Prueba / Subtest": "WISC-V - Coeficiente Intelectual Total (CIT)", "Puntaje": 90.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "WISC-V - Índice de Capacidad General (ICG)", "Puntaje": 106.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "WISC-V - Índice de Competencia Cognitiva (ICC)", "Puntaje": 80.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "WISC-V - Índice de Comprensión Verbal (ICV)", "Puntaje": 110.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "WISC-V - Índice de Memoria de Trabajo (IMT)", "Puntaje": 78.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "CPT-II - Tiempo de Reacción (Hit RT)", "Puntaje": 35.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "CPT-II - Comisiones (Impulsividad)", "Puntaje": 64.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "RAVLT - Recuerdo Diferido (A7)", "Puntaje": -1.8, "Tipo de Escala": catalogo_clinico.ESCALA_Z_DIRECTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "RAVLT - Reconocimiento", "Puntaje": 0.2, "Tipo de Escala": catalogo_clinico.ESCALA_Z_DIRECTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "BRIEF - Inhibición", "Puntaje": 72.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "SNAP-IV - Indicadores de Inatención", "Puntaje": 18.0, "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "Escala de Autoestima - Académica", "Puntaje": 10.0, "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "Escala Durand - Escape", "Puntaje": 24.0, "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "Escala Durand - Sensorial", "Puntaje": 8.0, "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO, "Observación": ""},
            ]
        )
        df_proc = psicometria.procesar_tabla_puntajes(df_in)
        res = analisis_clinico.analizar_perfil_clinico(
            df_procesado=df_proc,
            edad_anos_meses=(9, 4),
            pruebas_usadas=["WISC-V", "WPPSI-IV", "TOMAL", "BRIEF", "Figura Compleja de Rey"],
            datos_auxiliares={"tmt": {"diferencia_b_a": 60, "ratio_b_a": 3.4, "alerta_ejecutiva": True}},
        )

        alertas_txt = "\n".join(res["alertas_criticas"])
        hallazgos_txt = "\n".join(res["hallazgos_automaticos"])
        baremos_txt = "\n".join(res["avisos_baremos"])

        self.assertIn("Dispersión marcada Wechsler", alertas_txt)
        self.assertIn("Disociación ICG", alertas_txt)
        self.assertIn("WPPSI-IV", alertas_txt)
        self.assertIn("estilo impulsivo", alertas_txt)
        self.assertIn("BRIEF clínicamente elevado", alertas_txt)
        self.assertIn("SNAP-IV Inatención", alertas_txt)
        self.assertIn("Autoestima", alertas_txt)
        self.assertIn("Ratio B/A = 3.4", alertas_txt)

        self.assertIn("estrategias de recuperación", hallazgos_txt)
        self.assertIn("Escape (24)", hallazgos_txt)
        self.assertIn("TOMAL", baremos_txt)
        self.assertIn("BRIEF", baremos_txt)
        self.assertIn("Figura de Rey", baremos_txt)

    def test_aislamiento_baterias_snap_y_brief_doble_informante(self):
        df_in = pd.DataFrame(
            [
                # Ediciones distintas de Wechsler (NO deben generar dispersión conjunta de 30 pts)
                {"Dominio / Prueba / Subtest": "WISC-V - Índice de Comprensión Verbal (ICV)", "Puntaje": 115.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "WAIS-IV - Índice de Velocidad de Procesamiento (IVP)", "Puntaje": 85.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                # Atención cruzada CPT-II vs Nesplora (NO deben combinarse)
                {"Dominio / Prueba / Subtest": "CPT-II - Tiempo de Reacción (Hit RT)", "Puntaje": 35.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "Nesplora Aula: Comisiones", "Puntaje": 96.0, "Tipo de Escala": catalogo_clinico.ESCALA_PERCENTIL_INVERSO, "Observación": ""},
                # Memoria cruzada RAVLT vs Figura de Rey (NO debe atribuir falla de recuperación sin reconocimiento RAVLT)
                {"Dominio / Prueba / Subtest": "RAVLT - Recuerdo Diferido (A7)", "Puntaje": -1.8, "Tipo de Escala": catalogo_clinico.ESCALA_Z_DIRECTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "Figura Compleja de Rey - Reconocimiento", "Puntaje": 0.5, "Tipo de Escala": catalogo_clinico.ESCALA_Z_DIRECTO, "Observación": ""},
                # SNAP-IV suma cruda 2 (< 15) NO debe alertar
                {"Dominio / Prueba / Subtest": "SNAP-IV - Indicadores de Inatención (Madre)", "Puntaje": 2.0, "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO, "Observación": "Informante: Madre"},
                # BRIEF Madre y Padre por separado
                {"Dominio / Prueba / Subtest": "BRIEF - Inhibición (Madre)", "Puntaje": 71.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": "Informante: Madre"},
                {"Dominio / Prueba / Subtest": "BRIEF - Inhibición (Padre)", "Puntaje": 75.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": "Informante: Padre"},
            ]
        )
        df_proc = psicometria.procesar_tabla_puntajes(df_in)
        res = analisis_clinico.analizar_perfil_clinico(df_proc, pruebas_usadas=["WISC-V", "WAIS-IV", "CPT-II", "Nesplora Aula", "RAVLT", "Figura Compleja de Rey", "SNAP-IV", "BRIEF"])

        alertas_txt = "\n".join(res["alertas_criticas"])
        hallazgos_txt = "\n".join(res["hallazgos_automaticos"])

        self.assertNotIn("Dispersión marcada Wechsler", alertas_txt)
        self.assertNotIn("Heterogeneidad inter-índices", hallazgos_txt)
        self.assertNotIn("combinado con Comisiones elevadas", alertas_txt)
        self.assertIn("CPT-II: Tiempo de reacción atípicamente rápido", alertas_txt)
        self.assertNotIn("estrategias de recuperación", hallazgos_txt)
        self.assertIn("queda pendiente el reconocimiento de RAVLT", hallazgos_txt)
        self.assertIn("Figura Compleja de Rey", hallazgos_txt)
        self.assertNotIn("SNAP-IV Inatención", alertas_txt)
        self.assertIn("BRIEF - Inhibición (Madre) (T=71)", alertas_txt)
        self.assertIn("BRIEF - Inhibición (Padre) (T=75)", alertas_txt)


class TestImportadorArchivos(unittest.TestCase):
    def test_importar_planilla_xlsx_estilo_memoria(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Neuropsicológica"
        ws.append(["PLANILLA DE PUNTUACIONES – MODELO"])
        ws.append(["Paciente (Apellido, Nombre)", "Pérez, Mateo"])
        ws.append(["HC", "402891"])
        ws.append(["Fecha de nacimiento (dd/mm/aaaa)", "10/06/2017"])
        ws.append(["Fecha de evaluación (dd/mm/aaaa)", "20/10/2026"])
        ws.append(["Escolaridad", "4° Grado"])
        ws.append(["FUNCIONAMIENTO INTELECTUAL · WISC-V (6 a 16 años)"])
        ws.append(["Índice de Comprensión Verbal (ICV)", "CI", 106])
        ws.append(["Matrices", "PE", "10,5"])
        # Tabla de referencia en columna 26 que debe ignorarse
        ws.cell(row=8, column=26, value="TablaReferencia")
        ws.cell(row=8, column=27, value=999)

        ws.append(["ATENCIÓN SOSTENIDA"])
        ws.append(["Nesplora Aula: Omisiones", "Pc", 95])
        ws.append(["MEMORIA VISUAL"])
        ws.append(["Figura Compleja de Rey: copia", "Pc", 75])
        ws.append(["WOODCOCK-MUÑOZ"])
        ws.append(["Cálculo", 18, "9 años y 7 meses", "4.2°"])
        ws.append(["PROLEC-R"])
        ws.append(["Lectura de Palabras", 33, "Dificultad severa", "72\""])
        ws.append(["SNAP-IV"])
        ws.append(["Madre", 18, 12])
        ws.append(["BRIEF"])
        ws.append(["Inhibición", 71, 68])
        ws.append(["ESCALA DURAND (función de la conducta)"])
        ws.append(["Escape", 22])

        buf = io.BytesIO()
        wb.save(buf)
        res = importador_archivos.importar_planilla_excel_o_csv(buf.getvalue(), "planilla_mateo.xlsx")

        self.assertEqual(res["filiacion"]["nombre"], "Pérez, Mateo")
        self.assertEqual(res["filiacion"]["hc"], "402891")
        self.assertIn("WISC-V", res["pruebas_detectadas"])
        self.assertIn("Nesplora Aula", res["pruebas_detectadas"])
        self.assertIn("Woodcock-Muñoz", res["pruebas_detectadas"])
        self.assertIn("PROLEC-R / PROLEC-SE-R", res["pruebas_detectadas"])
        self.assertIn("BRIEF", res["pruebas_detectadas"])

        por_nombre = {r["Dominio / Prueba / Subtest"]: r for r in res["filas_puntajes"]}
        self.assertEqual(por_nombre["WISC-V - Matrices"]["Puntaje"], 10.5)
        self.assertEqual(
            por_nombre["Nesplora Aula: Omisiones"]["Tipo de Escala"],
            catalogo_clinico.ESCALA_PERCENTIL_INVERSO,
        )
        self.assertEqual(
            por_nombre["Figura Compleja de Rey - Copia"]["Tipo de Escala"],
            catalogo_clinico.ESCALA_PERCENTIL_DIRECTO,
        )
        self.assertIn("EE: 9 años y 7 meses", por_nombre["Woodcock-Muñoz - Cálculo"]["Observación"])
        self.assertNotIn("TablaReferencia", por_nombre)

    def test_importar_planilla_fidelidad_wisc_nesplora_brief_y_multihija(self):
        wb = openpyxl.Workbook()
        ws_alfa = wb.active
        ws_alfa.title = "Caso Alfa"
        ws_alfa.append(["Paciente (Apellido, Nombre)", "Alfa, Uno"])
        ws_alfa.append(["Fecha de evaluación (dd/mm/aaaa)", "01/10/2026"])
        ws_alfa.append(["FUNCIONAMIENTO INTELECTUAL · WISC-V (6 a 16 años)"])
        ws_alfa.append(["Búsqueda de Símbolos (WISC-V)", "PE", 8])
        ws_alfa.append(["Claves (WISC-V)", "PE", 9])
        ws_alfa.append(["ATENCIÓN SOSTENIDA"])
        ws_alfa.append(["Nesplora Aula: Tiempo de reacción", "Pc", 10])
        ws_alfa.append(["BRIEF"])
        ws_alfa.append(["Inhibición", 71, 75])
        ws_alfa.append(["Subtest Error", "PE", "#N/A"])

        ws_beta = wb.create_sheet("Caso Beta")
        ws_beta.append(["Paciente (Apellido, Nombre)", "Beta, Dos"])
        ws_beta.append(["Fecha de evaluación (dd/mm/aaaa)", "02/10/2026"])
        ws_beta.append(["FUNCIONAMIENTO INTELECTUAL · WAIS-IV"])
        ws_beta.append(["Comprensión Verbal (ICV)", "CI", 120])

        buf = io.BytesIO()
        wb.save(buf)
        raw_xlsx = buf.getvalue()

        # Sin hoja_seleccionada debe exigir selección y NO mezclar Alfa y Beta
        res_pend = importador_archivos.importar_planilla_excel_o_csv(raw_xlsx, "doble.xlsx")
        self.assertTrue(res_pend["requiere_seleccion_hoja"])
        self.assertEqual(len(res_pend["filas_puntajes"]), 0)
        self.assertEqual([h["paciente"] for h in res_pend["hojas_disponibles"]], ["Alfa, Uno", "Beta, Dos"])

        # Seleccionando Caso Alfa importa sus filas completas + auditoría
        res_alfa = importador_archivos.importar_planilla_excel_o_csv(raw_xlsx, "doble.xlsx", hoja_seleccionada="Caso Alfa")
        self.assertFalse(res_alfa["requiere_seleccion_hoja"])
        self.assertEqual(res_alfa["filiacion"]["nombre"], "Alfa, Uno")
        por_nombre = {r["Dominio / Prueba / Subtest"]: r for r in res_alfa["filas_puntajes"]}

        self.assertIn("WISC-V - Búsqueda de Símbolos", por_nombre)
        self.assertEqual(por_nombre["WISC-V - Búsqueda de Símbolos"]["Puntaje"], 8.0)
        self.assertIn("WISC-V - Claves", por_nombre)
        self.assertEqual(por_nombre["WISC-V - Claves"]["Puntaje"], 9.0)
        self.assertNotIn("WISC-V - Índice de Comprensión Verbal (ICV)", por_nombre)

        # Nesplora TR Pc 10 -> Percentil Inverso -> Atípico rápido
        esc_tr = por_nombre["Nesplora Aula: Tiempo de reacción"]["Tipo de Escala"]
        self.assertEqual(esc_tr, catalogo_clinico.ESCALA_PERCENTIL_INVERSO)
        _, rango_tr = psicometria.calcular_z_y_rango(10.0, esc_tr, nombre_subtest="Nesplora Aula: Tiempo de reacción")
        self.assertEqual(rango_tr, "Atípico rápido (estilo impulsivo)")

        # BRIEF Madre y Padre separados
        self.assertEqual(por_nombre["BRIEF - Inhibición (Madre)"]["Puntaje"], 71.0)
        self.assertEqual(por_nombre["BRIEF - Inhibición (Padre)"]["Puntaje"], 75.0)

        # Resumen de importación registra fila descartada por #N/A
        rep = res_alfa["resumen_importacion"]
        self.assertEqual(rep["filas_descartadas"], 1)
        self.assertEqual(len(rep["motivos_descarte"]), 1)
        self.assertIn("#N/A", rep["motivos_descarte"][0])

    def test_importar_ficha_docx_y_borrador_json(self):
        doc = Document()
        doc.add_paragraph("Apellido y nombre: Gómez, Lucía")
        doc.add_paragraph("HC: 98765")
        doc.add_paragraph("Preferencia manual: Zurda")
        doc.add_paragraph("Quién deriva (colegio, médico, familia): Derivación neurológica")
        buf = io.BytesIO()
        doc.save(buf)

        res = importador_archivos.importar_ficha_carga_docx(buf.getvalue())
        self.assertEqual(res["filiacion"]["nombre"], "Gómez, Lucía")
        self.assertEqual(res["filiacion"]["hc"], "98765")
        self.assertEqual(res["filiacion"]["preferencia"], "Zurda")
        self.assertIn("Derivación neurológica", res["motivo"]["quien_deriva"])

        raw_json = importador_archivos.exportar_borrador_json({"nombre_input": "Gómez, Lucía"}).encode("utf-8")
        cargado = importador_archivos.importar_borrador_json(raw_json)
        self.assertEqual(cargado["schema_version"], 2)
        self.assertEqual(cargado["nombre_input"], "Gómez, Lucía")


class TestMotorIA(unittest.TestCase):
    def test_system_prompt_y_prompt_caso_con_analisis_determinista(self):
        sys_prompt = motor_ia.construir_system_prompt()
        self.assertIn("Limítrofe (Dificultad / Déficit)", sys_prompt)
        self.assertIn("v-scale Vineland", sys_prompt)
        self.assertIn("Hit RT", sys_prompt)
        self.assertIn("Woodcock-Muñoz", sys_prompt)

        prompt_caso = motor_ia.construir_prompt_caso(
            {
                "nombre": "Ana Gómez",
                "conducta": {"Contacto y vínculo": "Adecuado", "Predisposición": ""},
                "observaciones_cualitativas": {"Memoria y Aprendizaje": "", "Atención": "Descenso"},
                "analisis_clinico_markdown": "- Alerta test",
            }
        )
        self.assertIn("- **Contacto y vínculo:** Adecuado", prompt_caso)
        self.assertNotIn("Predisposición", prompt_caso)
        self.assertIn("### 8B. ANÁLISIS PSICOMÉTRICO DETERMINISTA", prompt_caso)
        self.assertIn("- Alerta test", prompt_caso)

    def test_preparar_adjuntos_multimodales_y_polling_active(self):
        fake_client = MagicMock()
        fake_uploaded = MagicMock(uri="files/pdf-pesado")
        fake_uploaded.name = "files/pdf-pesado"
        fake_client.files.upload.return_value = fake_uploaded

        # Simular transición PROCESSING -> ACTIVE
        state_proc = MagicMock()
        state_proc.name = "PROCESSING"
        state_act = MagicMock()
        state_act.name = "ACTIVE"
        fake_client.files.get.side_effect = [MagicMock(state=state_proc), MagicMock(state=state_act)]

        wb = openpyxl.Workbook()
        wb.active.append(["WISC-V", "CIT", 100])
        buf_xlsx = io.BytesIO()
        wb.save(buf_xlsx)

        doc = Document()
        doc.add_paragraph("Ficha paciente prueba")
        buf_docx = io.BytesIO()
        doc.save(buf_docx)

        archivos = [
            {"name": "captura.PNG", "bytes": b"\x89PNG\r\n\x1a\n"},
            {"name": "planilla.xlsx", "bytes": buf_xlsx.getvalue()},
            {"name": "ficha.docx", "bytes": buf_docx.getvalue()},
            {"name": "escaneado.pdf", "bytes": b"%PDF-1.4 " + b"x" * 200},
        ]

        with patch("motor_ia.time.sleep"):
            bloques, temp_paths, uploaded_names = motor_ia.preparar_adjuntos_interaccion(
                archivos, fake_client, max_inline_bytes=50
            )
        try:
            self.assertEqual(len(bloques), 4)
            self.assertEqual(bloques[0]["type"], "image")
            self.assertEqual(bloques[0]["mime_type"], "image/png")
            self.assertEqual(bloques[1]["type"], "text")
            self.assertIn("WISC-V", bloques[1]["text"])
            self.assertEqual(bloques[2]["type"], "text")
            self.assertIn("Ficha paciente prueba", bloques[2]["text"])
            self.assertEqual(bloques[3], {"type": "document", "uri": "files/pdf-pesado", "mime_type": "application/pdf"})
            self.assertEqual(fake_client.files.get.call_count, 2)
            self.assertEqual(uploaded_names, ["files/pdf-pesado"])
        finally:
            for p in temp_paths:
                if os.path.exists(p):
                    os.remove(p)

    def test_extraer_datos_de_adjuntos_structured_output(self):
        fake_client = MagicMock()
        json_resp = (
            '{"filiacion": {"nombre": "Pérez, Mateo", "hc": "402"}, '
            '"modelos_sugeridos": ["Evaluación Neuropsicológica Completa"], '
            '"pruebas_detectadas": ["Nesplora Aula"], '
            '"puntajes": [{"subtest": "Nesplora Aula - Omisiones Totales", "puntaje": 92, '
            '"escala": "Percentil Inverso - Mayor es peor/error (Pc 1 a 99)", "observacion": ""}], '
            '"notas": {"obs_atencion_fe": "Distractores visuales"}, '
            '"advertencias_extraccion": []}'
        )
        fake_client.interactions.create.return_value = MagicMock(output_text=json_resp)

        with patch("motor_ia.genai.Client", return_value=fake_client):
            datos = motor_ia.extraer_datos_de_adjuntos(
                api_key="test-key",
                archivos=[{"name": "captura.jpg", "bytes": b"\xff\xd8\xff"}],
                modelo="gemini-4-hydrogen",
                store=False,
            )

        self.assertEqual(datos.filiacion.nombre, "Pérez, Mateo")
        self.assertEqual(datos.puntajes[0].puntaje, 92.0)
        kwargs = fake_client.interactions.create.call_args.kwargs
        self.assertFalse(kwargs["store"])
        self.assertIn("schema", kwargs["response_format"])

    def test_limpieza_archivos_ante_failed_y_timeout(self):
        # 1. Llamada directa a preparar_adjuntos_interaccion cuando File API devuelve FAILED
        fake_client = MagicMock()
        fake_uploaded = MagicMock(uri="files/pdf-fallido")
        fake_uploaded.name = "files/pdf-fallido"
        fake_client.files.upload.return_value = fake_uploaded
        state_failed = MagicMock()
        state_failed.name = "FAILED"
        fake_client.files.get.return_value = MagicMock(state=state_failed)

        created_paths = []
        orig_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            tmp = orig_ntf(*args, **kwargs)
            created_paths.append(tmp.name)
            return tmp

        with patch("motor_ia.tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
            with self.assertRaises(RuntimeError):
                motor_ia.preparar_adjuntos_interaccion(
                    [{"name": "grande.pdf", "bytes": b"%PDF-1.4 " + b"x" * 120}],
                    fake_client,
                    max_inline_bytes=20,
                )

        fake_client.files.delete.assert_called_once_with(name="files/pdf-fallido")
        self.assertEqual(len(created_paths), 1)
        self.assertFalse(os.path.exists(created_paths[0]))

        # 2. TimeoutError dentro de generar_informe_clinico también limpia local + remoto
        fake_client_to = MagicMock()
        fake_uploaded_to = MagicMock(uri="files/pdf-timeout")
        fake_uploaded_to.name = "files/pdf-timeout"
        fake_client_to.files.upload.return_value = fake_uploaded_to
        state_proc = MagicMock()
        state_proc.name = "PROCESSING"
        fake_client_to.files.get.return_value = MagicMock(state=state_proc)

        with patch("motor_ia.genai.Client", return_value=fake_client_to), patch(
            "motor_ia.MAX_INLINE_PDF_BYTES", 20
        ), patch(
            "motor_ia._esperar_archivo_activo",
            side_effect=TimeoutError("Timeout simulado"),
        ):
            with self.assertRaises(TimeoutError):
                motor_ia.generar_informe_clinico(
                    api_key="test-key",
                    modelo="gemini-4-hydrogen",
                    thinking_level="low",
                    datos_caso={"nombre": "Paciente Prueba"},
                    archivos=[{"name": "grande.pdf", "bytes": b"%PDF-1.4 " + b"x" * 120}],
                )
        fake_client_to.files.delete.assert_called_once_with(name="files/pdf-timeout")

    def test_seudonimizacion_y_reinyeccion_gemini(self):
        fake_client = MagicMock()
        fake_client.interactions.create.return_value = MagicMock(
            output_text="# INFORME\nPaciente [PACIENTE] (HC [ID_CASO]), derivado por [SOLICITANTE]. Firma: [PROFESIONAL_EVALUADOR]."
        )
        datos_caso = {
            "nombre": "Pérez, Mateo",
            "hc": "402891",
            "fecha_nac": "10/06/2017",
            "fecha_eval": "20/10/2026",
            "medico": "Dr. Gregory House",
            "firma_profesional": "Lic. Ana Gómez — MP 999",
            "quien_deriva": "Mateo Pérez derivado por Dr. Gregory House",
            "modelos_seleccionados": ["Evaluación Neuropsicológica Completa"],
        }

        with patch("motor_ia.genai.Client", return_value=fake_client):
            salida = motor_ia.generar_informe_clinico(
                api_key="test-key",
                modelo="gemini-4-hydrogen",
                thinking_level="low",
                datos_caso=datos_caso,
                anonimizar=True,
            )

        prompt_enviado = fake_client.interactions.create.call_args.kwargs["input"][0]["text"]
        self.assertNotIn("Pérez, Mateo", prompt_enviado)
        self.assertNotIn("402891", prompt_enviado)
        self.assertNotIn("10/06/2017", prompt_enviado)
        self.assertNotIn("Dr. Gregory House", prompt_enviado)
        self.assertIn("[PACIENTE]", prompt_enviado)
        self.assertIn("[ID_CASO]", prompt_enviado)

        self.assertIn("Pérez, Mateo", salida)
        self.assertIn("402891", salida)
        self.assertIn("Dr. Gregory House", salida)
        self.assertIn("Lic. Ana Gómez — MP 999", salida)


class TestGeneradorLocal(unittest.TestCase):
    def test_borrador_local_offline_y_exportacion_docx(self):
        df_in = pd.DataFrame(
            [
                {"Dominio / Prueba / Subtest": "WISC-V - Índice de Comprensión Verbal (ICV)", "Puntaje": 110.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "RAVLT - Recuerdo Diferido (A7)", "Puntaje": -1.8, "Tipo de Escala": catalogo_clinico.ESCALA_Z_DIRECTO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "Woodcock-Muñoz - Cálculo", "Puntaje": 18.0, "Tipo de Escala": catalogo_clinico.ESCALA_BRUTO, "Observación": "EE: 9 años"},
            ]
        )
        df_proc = psicometria.procesar_tabla_puntajes(df_in)
        analisis = analisis_clinico.analizar_perfil_clinico(df_proc, pruebas_usadas=["WISC-V", "RAVLT", "Woodcock-Muñoz"])
        datos_caso = {
            "modelos_seleccionados": ["Evaluación Neuropsicológica Completa"],
            "pruebas_usadas": ["WISC-V", "RAVLT", "Woodcock-Muñoz"],
            "nombre": "Pérez, Mateo",
            "hc": "402891",
            "fecha_eval": "20/10/2026",
            "quien_deriva": "Dificultades de memoria verbal reportadas por el colegio.",
            "conducta": {"Contacto y vínculo": "Adecuado"},
            "tabla_z_markdown": df_proc.to_markdown(index=False),
            "detalle_terapeuticas": "- Apoyo psicopedagógico semanal.",
            "detalle_escolares": "- Brindar consignas escritas paso a paso.",
            "firma_profesional": "Lic. Ana Gómez — MP 999",
        }
        md_local = generador_local.generar_borrador_local(datos_caso, df_proc, analisis)
        self.assertIn("Pérez, Mateo", md_local)
        self.assertIn("queda pendiente el reconocimiento de RAVLT", md_local)
        self.assertIn("no se encuentra estandarizada para nuestra población", md_local)
        self.assertIn("El diagnóstico definitivo quedará a cargo del médico tratante", md_local)

        docx_bytes = exportador_docx.generar_docx_bytes(
            texto_markdown=md_local,
            datos_filiacion={"nombre": "Pérez, Mateo", "fecha_eval": "20/10/2026"},
            df_puntajes=df_proc,
            incluir_grilla_visual_z=True,
        )
        self.assertGreater(len(docx_bytes), 2000)


class TestExportadorDocx(unittest.TestCase):
    def test_grilla_visual_z_membrete_clausula_y_citas(self):
        df_in = pd.DataFrame(
            [
                {"Dominio / Prueba / Subtest": "WISC-V - ICV", "Puntaje": 106.0, "Tipo de Escala": catalogo_clinico.ESCALA_CI, "Observación": ""},
                {"Dominio / Prueba / Subtest": "CPT-II - Tiempo de Reacción (Hit RT)", "Puntaje": 35.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": ""},
                {"Dominio / Prueba / Subtest": "CPT-II - Omisiones (Inatención)", "Puntaje": 75.0, "Tipo de Escala": catalogo_clinico.ESCALA_T_INVERSO, "Observación": ""},
            ]
        )
        df_proc = psicometria.procesar_tabla_puntajes(df_in)

        md = """# INFORME DE EVALUACIÓN NEUROPSICOLÓGICA

## 1. Conclusiones
Desempeño **adecuado** en lenguaje y estilo rápido en tiempo de reacción.

## 2. Recomendaciones
> * Mantener pautas de organización diaria.
"""
        docx_bytes = exportador_docx.generar_docx_bytes(
            texto_markdown=md,
            datos_filiacion={"nombre": "Pérez, Mateo", "fecha_eval": "20/10/2026"},
            df_puntajes=df_proc,
            incluir_grilla_visual_z=True,
            membrete_institucional="Servicio de Neuropsicología Clínica",
            incluir_clausula_confidencial=True,
            firma_profesional="Lic. Juan Machado — MP 1234",
        )
        doc = Document(io.BytesIO(docx_bytes))
        todo_texto = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        self.assertIn("Servicio de Neuropsicología Clínica", todo_texto)
        self.assertIn("carecen de cualquier valor judicial", todo_texto)
        self.assertIn("Mantener pautas de organización diaria.", todo_texto)
        self.assertNotIn("> *", todo_texto)
        self.assertIn("R*: Tiempo de reacción atípicamente rápido", todo_texto)

        # La tabla 0 debe ser la Grilla Visual Z de 22 columnas
        grilla = doc.tables[0]
        self.assertEqual(len(grilla.columns), 22)
        self.assertEqual(len(grilla.rows), 5)  # 2 cabeceras + 3 filas

        # Fila 2 (WISC-V ICV, Z=+0.40 -> tercio 0.33 -> col 3 + 10 = 13)
        self.assertEqual(grilla.rows[2].cells[13].text.strip(), "X")
        # Fila 3 (Hit RT rápido -> R* en tercio 1.33 -> col 3 + 13 = 16)
        self.assertEqual(grilla.rows[3].cells[16].text.strip(), "R*")
        # Fila 4 (CPT Omisiones Z=-2.50 -> tercio -2.33 -> col 3 + 2 = 5)
        self.assertEqual(grilla.rows[4].cells[5].text.strip(), "X")
        shd_def = grilla.rows[4].cells[5]._tc.tcPr.find(qn("w:shd"))
        self.assertEqual(shd_def.get(qn("w:fill")), "FADBD8")


class TestAppStreamlit(unittest.TestCase):
    def test_apptest_carga_rapida_presets_asistentes_y_persistencia(self):
        from streamlit.testing.v1 import AppTest

        app_path = str(Path(__file__).resolve().parent.parent / "app.py")
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            at = AppTest.from_file(app_path, default_timeout=25)
            at.run()
            self.assertFalse(at.exception, f"Excepción al arrancar app.py: {at.exception}")

            # 1. Calculadora Z con Percentil Inverso + Hit RT
            at.sidebar.selectbox[2].set_value(catalogo_clinico.ESCALA_PERCENTIL_INVERSO).run()
            self.assertFalse(at.exception)
            at.sidebar.number_input[0].set_value(95.0).run()
            self.assertEqual(at.sidebar.metric[0].value, "Z = -1.64")

            # 2. Edad automática desde fechas
            at.date_input[0].set_value(date(2017, 6, 10)).run()
            at.date_input[1].set_value(date(2026, 10, 20)).run()
            self.assertEqual(at.session_state["edad_texto_input"], "9 años, 4 meses")

            # 3. Preset de batería (Neuropsicológica Infantil Completa)
            btn_preset = next(b for b in at.button if "Neuropsicológica Infantil Completa" in b.label)
            btn_preset.click().run()
            self.assertFalse(at.exception)
            self.assertIn("WISC-V", at.session_state["pruebas_sel"])
            self.assertIn("CPT-II", at.session_state["pruebas_sel"])

            # 4. Botón conducta acorde en 1 clic
            btn_cond = next(b for b in at.button if "Conducta acorde" in b.label)
            btn_cond.click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["obs_vinculo"], "Adecuado")
            self.assertEqual(at.session_state["obs_frustracion"], "Adecuada")

            # 5. Perfil de recomendaciones en 1 clic
            btn_rec = next(b for b in at.button if "Aprendizaje (DEA)" in b.label)
            btn_rec.click().run()
            self.assertFalse(at.exception)
            self.assertIn("Velocidad lectora y apoyos de lectura", at.session_state["sug_escolares_sel"])

            # 6. Generación y persistencia del informe
            at.text_input[0].set_value("Pérez, Mateo").run()
            if at.sidebar.text_input:
                at.sidebar.text_input[0].set_value("fake-api-key").run()

            btn_gen = next(b for b in at.button if "Generar Informe Clínico Completo" in b.label)
            with patch(
                "motor_ia.generar_informe_clinico",
                return_value="# INFORME FASE 2\n\n## Conclusiones\nDesempeño **adecuado**.",
            ):
                btn_gen.click().run()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.error), 0, f"Errores en UI: {[e.value for e in at.error]}")

            self.assertIn("INFORME FASE 2", at.session_state["informe_actual"])
            # Rerun extra en sidebar: persiste el informe
            at.sidebar.number_input[0].set_value(50.0).run()
            self.assertIn("INFORME FASE 2", at.session_state["informe_actual"])

            deprecations = [
                str(w.message)
                for w in captured
                if "use_container_width" in str(w.message)
            ]
            self.assertEqual(deprecations, [], f"Warnings de deprecación detectados: {deprecations}")

    def test_apptest_bloqueo_sin_evidencia_flujo_local_y_huella_alfa_beta(self):
        from streamlit.testing.v1 import AppTest

        app_path = str(Path(__file__).resolve().parent.parent / "app.py")
        at = AppTest.from_file(app_path, default_timeout=25)
        at.run()
        self.assertFalse(at.exception)

        # Elegir solo modelo + nombre sin evidencia clínica NO debe generar informe
        at.multiselect[0].set_value(["Evaluación Neuropsicológica Completa"]).run()
        at.text_input[0].set_value("Alfa, Paciente").run()
        btn_local = next(b for b in at.button if "Generar Borrador Local" in b.label)
        btn_local.click().run()
        self.assertFalse(at.session_state.get("informe_actual"))
        self.assertTrue(any("no alcanza solo con elegir modelo y nombre" in w.value for w in at.warning))

        # Al cargar evidencia (Conducta acorde), genera borrador offline y habilita descargas
        btn_cond = next(b for b in at.button if "Conducta acorde" in b.label)
        btn_cond.click().run()
        btn_local = next(b for b in at.button if "Generar Borrador Local" in b.label)
        btn_local.click().run()
        self.assertIn("Alfa, Paciente", at.session_state["informe_actual"])
        dls_activos = [
            dl for dl in at.get("download_button")
            if "Word" in dl.label or "Markdown" in dl.label
        ]
        self.assertEqual(len(dls_activos), 2)
        self.assertTrue(all(not dl.disabled for dl in dls_activos))

        # Cambiar nombre de Alfa a Beta debe advertir y deshabilitar descargas del borrador anterior
        at.text_input[0].set_value("Beta, Paciente").run()
        self.assertTrue(any("Regenerá el informe" in w.value for w in at.warning))
        dls_bloqueados = [
            dl for dl in at.get("download_button")
            if "Word" in dl.label or "Markdown" in dl.label
        ]
        self.assertEqual(len(dls_bloqueados), 2)
        self.assertTrue(all(dl.disabled for dl in dls_bloqueados))


if __name__ == "__main__":
    unittest.main()
