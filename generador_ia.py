"""Script de consola de ejemplo usando el motor clínico modular (google-genai + Word)."""

import pandas as pd

from borrador import grilla_markdown
from catalogo_clinico import BANCO_SUGERENCIAS, ESCALA_CI, ESCALA_T_INVERSO
from exportador_docx import guardar_docx
from motor_ia import generar_informe_clinico, resolver_api_key
from psicometria import procesar_tabla_puntajes


def generar_informe_completo_con_ia() -> int:
    api_key = resolver_api_key()
    if not api_key:
        print(
            "No se encontró GEMINI_API_KEY. Configurala como variable de entorno "
            "o en .streamlit/secrets.toml antes de ejecutar este script."
        )
        return 1

    paciente = "Caso ficticio"
    hc = "DEMO-001"
    edad = "9 años, 4 meses"
    escolaridad = "4° Grado Primaria"
    fecha_eval = "Octubre 2026"
    profesional = "Profesional de ejemplo"
    firma = f"{profesional} — Matrícula Provincial / Nacional"

    df_entrada = pd.DataFrame(
        [
            {
                "Dominio / Prueba / Subtest": "WISC-V - Índice de Comprensión Verbal (ICV)",
                "Puntaje": 106.0,
                "Tipo de Escala": ESCALA_CI,
                "Observación": "",
            },
            {
                "Dominio / Prueba / Subtest": "WISC-V - Índice Visoespacial (IVE)",
                "Puntaje": 97.0,
                "Tipo de Escala": ESCALA_CI,
                "Observación": "",
            },
            {
                "Dominio / Prueba / Subtest": "WISC-V - Índice de Razonamiento Fluido (IRF)",
                "Puntaje": 100.0,
                "Tipo de Escala": ESCALA_CI,
                "Observación": "",
            },
            {
                "Dominio / Prueba / Subtest": "WISC-V - Índice de Memoria de Trabajo (IMT)",
                "Puntaje": 78.0,
                "Tipo de Escala": ESCALA_CI,
                "Observación": "",
            },
            {
                "Dominio / Prueba / Subtest": "WISC-V - Índice de Velocidad de Procesamiento (IVP)",
                "Puntaje": 81.0,
                "Tipo de Escala": ESCALA_CI,
                "Observación": "",
            },
            {
                "Dominio / Prueba / Subtest": "CPT-II - Omisiones (Inatención)",
                "Puntaje": 66.0,
                "Tipo de Escala": ESCALA_T_INVERSO,
                "Observación": "",
            },
            {
                "Dominio / Prueba / Subtest": "CPT-II - Comisiones (Impulsividad)",
                "Puntaje": 52.0,
                "Tipo de Escala": ESCALA_T_INVERSO,
                "Observación": "",
            },
        ]
    )
    df_procesado = procesar_tabla_puntajes(df_entrada)

    datos_caso = {
        "modelos_seleccionados": ["Evaluación Neuropsicológica Completa"],
        "pruebas_usadas": ["WISC-V", "CPT-II"],
        "nombre": paciente,
        "hc": hc,
        "edad_texto": edad,
        "escolaridad": escolaridad,
        "fecha_eval": fecha_eval,
        "medico": "Equipo Médico / Escolar",
        "firma_profesional": firma,
        "quien_deriva": "Derivación escolar/médica por dificultades atencionales y rendimiento operativo.",
        "conducta": {
            "Notas extra de conducta": (
                "Ingresó al consultorio con adecuada autonomía y buen contacto vincular. "
                "Durante la administración de las primeras pruebas mantuvo la atención y el interés. "
                "Hacia los 25-30 minutos evidenció signos de fatiga física, inquietud motora leve y "
                "verbalizaciones de agobio, requiriendo instigación verbal y pausas breves."
            )
        },
        "tabla_z_markdown": grilla_markdown(df_procesado),
        "observaciones_cualitativas": {
            "Funcionamiento Intelectual (Wechsler)": (
                "Marcada dispersión entre índices cristalizados/fluidos y los índices operativos (IMT, IVP)."
            ),
        },
        "impresion_destacar": (
            "Perfil cognitivo con recursos verbales y de razonamiento acorde a lo esperado y "
            "descenso específico en memoria operativa, velocidad de procesamiento y atención sostenida."
        ),
        "detalle_terapeuticas": "\n".join(
            [
                f"- {k}: {BANCO_SUGERENCIAS['terapeuticas'][k]}"
                for k in ("Devolución médica", "Tratamiento Psicopedagógico")
            ]
        ),
        "detalle_escolares": "\n".join(
            [
                f"- {k}: {BANCO_SUGERENCIAS['escolares'][k]}"
                for k in ("Ubicación y control de distractores", "Segmentación de consignas")
            ]
        ),
    }

    print("Consultando a Gemini 3.8 Flash mediante el motor clínico modular...")
    texto_ia = generar_informe_clinico(
        api_key=api_key,
        modelo="gemini-3.8-flash",
        thinking_level="high",
        datos_caso=datos_caso,
        store=False,
    )

    nombre_salida = "Informe_Neuropsicologico_Completo.docx"
    guardar_docx(
        nombre_salida,
        texto_markdown=texto_ia,
        datos_filiacion={"nombre": paciente, "fecha_eval": fecha_eval},
        incluir_tabla_filiacion=False,
        incluir_tabla_z=False,
        firma_profesional=firma,
    )
    print(f"¡Éxito! Informe Word generado correctamente como: {nombre_salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(generar_informe_completo_con_ia())
