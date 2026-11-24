"""Base de conocimiento clínica, escalas psicométricas y catálogo de baterías."""

ESCALA_CI = "CI / Estándar (M=100, DE=15)"
ESCALA_ESCALAR = "Escalar (M=10, DE=3)"
ESCALA_T_DIRECTO = "T Directo - Mayor es mejor (M=50, DE=10)"
ESCALA_T_INVERSO = "T Inverso - Mayor es peor/error (M=50, DE=10)"
ESCALA_PERCENTIL = "Percentil (Pc 1 a 99)"
ESCALA_Z_DIRECTO = "Puntaje Z directo"
ESCALA_BRUTO = "Puntaje Bruto / Categoría (Ver Notas)"

ESCALAS_DISPONIBLES = [
    ESCALA_CI,
    ESCALA_ESCALAR,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALA_PERCENTIL,
    ESCALA_Z_DIRECTO,
    ESCALA_BRUTO,
]

ESCALAS_CALCULADORA = [
    ESCALA_ESCALAR,
    ESCALA_CI,
    ESCALA_T_DIRECTO,
    ESCALA_T_INVERSO,
    ESCALA_PERCENTIL,
]

MODELOS_INFORME = [
    "Evaluación Neuropsicológica Completa",
    "Evaluación Neuropsicológica (Versión Desempeño Cognitivo - Wechsler)",
    "Evaluación Psicopedagógica Infantil",
    "Cuestionarios Conductuales (SNAP-IV / BRIEF / Durand / Autoestima)",
    "Conducta Adaptativa (Vineland)",
    "DIVA-5 (Adultos)",
]

MODELOS_GEMINI = {
    "gemini-3.8-flash": {
        "label": "Gemini 3.8 Flash",
        "thinking_levels": ["low", "medium", "high"],
        "default_thinking": "medium",
    },
    "gemini-3.5-flash-lite": {
        "label": "Gemini 3.5 Flash-Lite",
        "thinking_levels": ["minimal", "low", "medium", "high"],
        "default_thinking": "minimal",
    },
}

# Catálogo Maestro de Baterías -> Subpruebas y su Escala por defecto
CATALOGO_SUBPRUEBAS = {
    "WISC-V": [
        ("WISC-V - Coeficiente Intelectual Total (CIT)", ESCALA_CI),
        ("WISC-V - Índice de Capacidad General (ICG)", ESCALA_CI),
        ("WISC-V - Índice de Comprensión Verbal (ICV)", ESCALA_CI),
        ("WISC-V - Índice Visoespacial (IVE)", ESCALA_CI),
        ("WISC-V - Índice de Razonamiento Fluido (IRF)", ESCALA_CI),
        ("WISC-V - Índice de Memoria de Trabajo (IMT)", ESCALA_CI),
        ("WISC-V - Índice de Velocidad de Procesamiento (IVP)", ESCALA_CI),
        ("WISC-V - Índice de Razonamiento Cuantitativo (IRC)", ESCALA_CI),
        ("WISC-V - Índice de Memoria de Trabajo Auditiva (IMTA)", ESCALA_CI),
        ("WISC-V - Índice de Competencia Cognitiva (ICC)", ESCALA_CI),
        ("WISC-V - Semejanzas", ESCALA_ESCALAR),
        ("WISC-V - Vocabulario", ESCALA_ESCALAR),
        ("WISC-V - Cubos", ESCALA_ESCALAR),
        ("WISC-V - Puzles Visuales", ESCALA_ESCALAR),
        ("WISC-V - Matrices", ESCALA_ESCALAR),
        ("WISC-V - Balanzas", ESCALA_ESCALAR),
        ("WISC-V - Dígitos", ESCALA_ESCALAR),
        ("WISC-V - Span de Dibujos", ESCALA_ESCALAR),
        ("WISC-V - Claves", ESCALA_ESCALAR),
        ("WISC-V - Búsqueda de Símbolos", ESCALA_ESCALAR),
        ("WISC-V - Aritmética", ESCALA_ESCALAR),
    ],
    "WPPSI-IV": [
        ("WPPSI-IV - Coeficiente Intelectual Total (CIT)", ESCALA_CI),
        ("WPPSI-IV - Índice de Comprensión Verbal (ICV)", ESCALA_CI),
        ("WPPSI-IV - Índice Visoespacial (IVE)", ESCALA_CI),
        ("WPPSI-IV - Índice de Razonamiento Fluido (IRF)", ESCALA_CI),
        ("WPPSI-IV - Índice de Memoria de Trabajo (IMT)", ESCALA_CI),
        ("WPPSI-IV - Índice de Velocidad de Procesamiento (IVP)", ESCALA_CI),
        ("WPPSI-IV - Información", ESCALA_ESCALAR),
        ("WPPSI-IV - Semejanzas", ESCALA_ESCALAR),
        ("WPPSI-IV - Cubos", ESCALA_ESCALAR),
        ("WPPSI-IV - Rompecabezas", ESCALA_ESCALAR),
        ("WPPSI-IV - Matrices", ESCALA_ESCALAR),
        ("WPPSI-IV - Conceptos", ESCALA_ESCALAR),
        ("WPPSI-IV - Reconocimiento", ESCALA_ESCALAR),
        ("WPPSI-IV - Localización", ESCALA_ESCALAR),
        ("WPPSI-IV - Búsqueda de Animales", ESCALA_ESCALAR),
        ("WPPSI-IV - Cancelación", ESCALA_ESCALAR),
    ],
    "WAIS-IV": [
        ("WAIS-IV - Coeficiente Intelectual Total (CIT)", ESCALA_CI),
        ("WAIS-IV - Índice de Comprensión Verbal (ICV)", ESCALA_CI),
        ("WAIS-IV - Índice de Razonamiento Perceptivo (IRP)", ESCALA_CI),
        ("WAIS-IV - Índice de Memoria de Trabajo (IMT)", ESCALA_CI),
        ("WAIS-IV - Índice de Velocidad de Procesamiento (IVP)", ESCALA_CI),
        ("WAIS-IV - Semejanzas", ESCALA_ESCALAR),
        ("WAIS-IV - Vocabulario", ESCALA_ESCALAR),
        ("WAIS-IV - Información", ESCALA_ESCALAR),
        ("WAIS-IV - Cubos", ESCALA_ESCALAR),
        ("WAIS-IV - Matrices", ESCALA_ESCALAR),
        ("WAIS-IV - Puzles Visuales", ESCALA_ESCALAR),
        ("WAIS-IV - Dígitos", ESCALA_ESCALAR),
        ("WAIS-IV - Aritmética", ESCALA_ESCALAR),
        ("WAIS-IV - Letras y Números", ESCALA_ESCALAR),
        ("WAIS-IV - Búsqueda de Símbolos", ESCALA_ESCALAR),
        ("WAIS-IV - Clave de Números", ESCALA_ESCALAR),
    ],
    "NEPSY-II": [
        ("NEPSY-II - Atención Auditiva", ESCALA_ESCALAR),
        ("NEPSY-II - Flexibilidad Cognitiva (Cambio de criterio)", ESCALA_ESCALAR),
        ("NEPSY-II - Estatua (Control Inhibitorio)", ESCALA_ESCALAR),
        ("NEPSY-II - Fluidez de Diseños", ESCALA_ESCALAR),
        ("NEPSY-II - Procesamiento Fonológico", ESCALA_ESCALAR),
        ("NEPSY-II - Denominación Veloz", ESCALA_ESCALAR),
        ("NEPSY-II - Comprensión de Instrucciones", ESCALA_ESCALAR),
        ("NEPSY-II - Generación de Palabras (Semántica)", ESCALA_ESCALAR),
        ("NEPSY-II - Generación de Palabras (Fonológica)", ESCALA_ESCALAR),
        ("NEPSY-II - Copia de Diseños", ESCALA_ESCALAR),
        ("NEPSY-II - Precisión Visomotora", ESCALA_ESCALAR),
    ],
    "TOMAL": [
        ("TOMAL - Recuerdo Selectivo de Palabras (Inmediato)", ESCALA_ESCALAR),
        ("TOMAL - Recuerdo Selectivo de Palabras (Demorado)", ESCALA_ESCALAR),
        ("TOMAL - Memoria Visual Abstracta", ESCALA_ESCALAR),
        ("TOMAL - Memoria de Secuencias / Dígitos", ESCALA_ESCALAR),
    ],
    "WRAML": [
        ("WRAML - Memoria Narrativa (Recuerdo Inmediato)", ESCALA_ESCALAR),
        ("WRAML - Memoria Narrativa (Recuerdo Demorado)", ESCALA_ESCALAR),
        ("WRAML - Reconocimiento Narrativo", ESCALA_ESCALAR),
    ],
    "Stroop": [
        ("Stroop - Lectura de Palabras (P)", ESCALA_T_DIRECTO),
        ("Stroop - Denominación de Colores (C)", ESCALA_T_DIRECTO),
        ("Stroop - Palabra-Color (PC)", ESCALA_T_DIRECTO),
        ("Stroop - Índice de Interferencia", ESCALA_T_DIRECTO),
    ],
    "Trail Making Test (TMT)": [
        ("Trail Making Test - Parte A (Atención Sostenida/Selectiva)", ESCALA_T_DIRECTO),
        ("Trail Making Test - Parte B (Atención Dividida/Flexibilidad)", ESCALA_T_DIRECTO),
    ],
    "CPT-II": [
        ("CPT-II - Omisiones (Inatención)", ESCALA_T_INVERSO),
        ("CPT-II - Comisiones (Impulsividad)", ESCALA_T_INVERSO),
        ("CPT-II - Tiempo de Reacción (Hit RT)", ESCALA_T_INVERSO),
        ("CPT-II - Variabilidad / Consistencia (Hit RT Std Error)", ESCALA_T_INVERSO),
        ("CPT-II - Perseveraciones", ESCALA_T_INVERSO),
    ],
    "Nesplora Aula": [
        ("Nesplora Aula - Omisiones Totales", ESCALA_T_INVERSO),
        ("Nesplora Aula - Comisiones Totales", ESCALA_T_INVERSO),
        ("Nesplora Aula - Tiempo de Reacción (TR)", ESCALA_T_INVERSO),
        ("Nesplora Aula - Variabilidad del TR", ESCALA_T_INVERSO),
        ("Nesplora Aula - Actividad Motora", ESCALA_T_INVERSO),
    ],
    "Figura Compleja de Rey": [
        ("Figura Compleja de Rey - Copia", ESCALA_T_DIRECTO),
        ("Figura Compleja de Rey - Memoria Inmediata (3 min)", ESCALA_T_DIRECTO),
        ("Figura Compleja de Rey - Memoria Diferida (30 min)", ESCALA_T_DIRECTO),
        ("Figura Compleja de Rey - Reconocimiento", ESCALA_T_DIRECTO),
    ],
    "WCST": [
        ("WCST - Categorías Completadas", ESCALA_T_DIRECTO),
        ("WCST - Respuestas Perseverativas", ESCALA_T_DIRECTO),
        ("WCST - Errores Perseverativos", ESCALA_T_DIRECTO),
    ],
    "RAVLT": [
        ("RAVLT - Total Aprendizaje (Ensayos A1-A5)", ESCALA_Z_DIRECTO),
        ("RAVLT - Lista Interferencia (B1)", ESCALA_Z_DIRECTO),
        ("RAVLT - Recuerdo Inmediato Post-Interferencia (A6)", ESCALA_Z_DIRECTO),
        ("RAVLT - Recuerdo Diferido (A7)", ESCALA_Z_DIRECTO),
        ("RAVLT - Reconocimiento", ESCALA_Z_DIRECTO),
    ],
    "BRIEF": [
        ("BRIEF - Inhibición", ESCALA_T_INVERSO),
        ("BRIEF - Cambio / Flexibilidad", ESCALA_T_INVERSO),
        ("BRIEF - Control Emocional", ESCALA_T_INVERSO),
        ("BRIEF - Índice de Regulación Conductual (BRI)", ESCALA_T_INVERSO),
        ("BRIEF - Iniciativa", ESCALA_T_INVERSO),
        ("BRIEF - Memoria de Trabajo", ESCALA_T_INVERSO),
        ("BRIEF - Planificación y Organización", ESCALA_T_INVERSO),
        ("BRIEF - Organización de Materiales", ESCALA_T_INVERSO),
        ("BRIEF - Monitoreo / Supervisión", ESCALA_T_INVERSO),
        ("BRIEF - Índice de Metacognición (MI)", ESCALA_T_INVERSO),
        ("BRIEF - Índice Global de Función Ejecutiva (GEC)", ESCALA_T_INVERSO),
    ],
    "Vineland": [
        ("Vineland - Comunicación", ESCALA_CI),
        ("Vineland - Habilidades de la Vida Diaria", ESCALA_CI),
        ("Vineland - Socialización", ESCALA_CI),
        ("Vineland - Habilidades Motoras", ESCALA_CI),
        ("Vineland - Índice Compuesto de Conducta Adaptativa", ESCALA_CI),
    ],
    "PROLEC-R / PROLEC-SE-R": [
        ("PROLEC - Nombre o Sonido de Letras", ESCALA_BRUTO),
        ("PROLEC - Igual-Diferente", ESCALA_BRUTO),
        ("PROLEC - Lectura de Palabras (Precisión y Velocidad)", ESCALA_BRUTO),
        ("PROLEC - Lectura de Pseudopalabras (Precisión y Velocidad)", ESCALA_BRUTO),
        ("PROLEC - Estructuras Gramaticales", ESCALA_BRUTO),
        ("PROLEC - Signos de Puntuación", ESCALA_BRUTO),
        ("PROLEC - Comprensión de Oraciones", ESCALA_BRUTO),
        ("PROLEC - Comprensión de Textos", ESCALA_BRUTO),
        ("PROLEC - Comprensión Oral", ESCALA_BRUTO),
    ],
    "Woodcock-Muñoz": [
        ("Woodcock-Muñoz - Cálculo", ESCALA_BRUTO),
        ("Woodcock-Muñoz - Problemas Aplicados", ESCALA_BRUTO),
        ("Woodcock-Muñoz - Identificación de Letras y Palabras", ESCALA_BRUTO),
        ("Woodcock-Muñoz - Comprensión de Textos", ESCALA_BRUTO),
    ],
    "TEMA-3": [
        ("TEMA-3 - Índice de Competencia Matemática", ESCALA_CI),
    ],
    "TOMA-3": [
        ("TOMA-3 - Cociente Matemático Global", ESCALA_CI),
    ],
    "Ortografía Feldman": [
        ("Escala de Ortografía (Feldman) - Puntaje Total", ESCALA_BRUTO),
    ],
    "NALPA": [
        ("NALPA - Nivel de Alfabetización", ESCALA_BRUTO),
    ],
    "EPL": [
        ("EPL - Evaluación de las Primeras Letras", ESCALA_BRUTO),
    ],
    "Dictado de oraciones": [
        ("Dictado de Oraciones - Rendimiento Global", ESCALA_BRUTO),
    ],
    "SNAP-IV": [
        ("SNAP-IV - Indicadores de Inatención", ESCALA_BRUTO),
        ("SNAP-IV - Indicadores de Hiperactividad / Impulsividad", ESCALA_BRUTO),
    ],
    "Escala Durand": [
        ("Escala Motivacional de Durand - Perfil", ESCALA_BRUTO),
    ],
    "DIVA-5": [
        ("DIVA-5 - Criterios Déficit de Atención (Adultez / Infancia)", ESCALA_BRUTO),
        ("DIVA-5 - Criterios Hiperactividad-Impulsividad (Adultez / Infancia)", ESCALA_BRUTO),
    ],
}

# Introducciones teóricas en cursiva (Base de Conocimiento Clínica)
INTRODUCCIONES_DOMINIOS = {
    "intelectual": (
        "*La evaluación del funcionamiento intelectual mediante la Escala de Inteligencia de Wechsler "
        "(WISC-V / WPPSI-IV / WAIS-IV) permite obtener una estimación de la capacidad cognitiva general "
        "del paciente, así como explorar su desempeño en dominios específicos que subyacen al "
        "aprendizaje y la resolución de problemas.*"
    ),
    "memoria": (
        "*La memoria consiste en una serie de procesos cognitivos: la codificación (procesamiento inicial "
        "de la información), almacenamiento (retención de la información mediante la consolidación) y "
        "evocación (capacidad de acceder a la información almacenada). A su vez, según el contenido a "
        "memorizar, la memoria puede ser subdividida en memoria verbal (palabras, frases y textos) y "
        "memoria visual (dibujos, fotos, etc.).*"
    ),
    "atencion": (
        "*La atención es un proceso complejo que involucra selección, vigilancia y control. Requiere de "
        "focalización en un estímulo, la inhibición de estímulos irrelevantes y la capacidad de sostener "
        "la atención en el tiempo en diferentes tareas. Si bien nos referimos a la atención de manera "
        "global existen diferentes tipos. La atención selectiva, es la capacidad para seleccionar entre "
        "varias posibles la información relevante que se va a procesar. La atención sostenida es la "
        "capacidad para mantener la atención en una misma actividad durante un prolongado periodo de "
        "tiempo. La atención dividida es la capacidad de realizar la selección de más de una información "
        "a la vez o de más de un proceso o esquema de acción simultáneamente. El normal funcionamiento "
        "de estos aspectos va a permitir ejecutar y mantener una conducta dirigida hacia una "
        "meta frente a eventuales distractores.*"
    ),
    "ejecutivas": (
        "*Las funciones ejecutivas son un conjunto de habilidades cognitivas de alto orden que permiten "
        "la anticipación y el establecimiento de metas, el diseño de planes y programas, el inicio de las "
        "actividades y de las operaciones mentales, la autorregulación y la monitorización de las tareas, "
        "la selección precisa de los comportamientos y las conductas, la flexibilidad en el trabajo "
        "cognoscitivo y su organización en el tiempo y en el espacio para obtener resultados eficaces en "
        "la resolución de problemas.*"
    ),
    "visomotor": (
        "*Las habilidades visoconstructivas y visomotoras implican la capacidad de integrar la percepción "
        "visual con la respuesta motriz fina para planificar, organizar y reproducir diseños espaciales "
        "de diversa complejidad.*"
    ),
    "lenguaje": (
        "*El lenguaje es un sistema complejo de símbolos que permite la comunicación interpersonal y actúa "
        "como mediador fundamental del pensamiento, el aprendizaje escolar y la autorregulación conductual.*"
    ),
}

# Banco Maestro de Sugerencias y Recomendaciones Clínicas y Escolares
BANCO_SUGERENCIAS = {
    "terapeuticas": {
        "Devolución médica": "Compartir el presente informe con el médico derivante/tratante a fin de evaluar las conductas terapéuticas a seguir.",
        "Tratamiento Psicopedagógico": "Iniciar/continuar tratamiento psicopedagógico con orientación neurocognitiva, orientado a estimular los procesos atencionales, funciones ejecutivas (planificación, organización, monitoreo y memoria de trabajo) y estrategias de aprendizaje.",
        "Psicoterapia Cognitivo-Conductual (TCC) y Orientación a Padres": "Iniciar/continuar espacio de tratamiento psicológico con orientación cognitivo-conductual (TCC) junto con entrevistas periódicas de orientación a padres, para brindar herramientas de autorregulación emocional, tolerancia a la frustración, control de impulsos y organización de rutinas en el hogar.",
        "Terapia Ocupacional (Integración Sensorial)": "Realizar evaluación/tratamiento de Terapia Ocupacional con enfoque en Integración Sensorial y praxias visomotoras para abordar la regulación motora, la postura y la grafomotricidad.",
        "Neurolingüística / Fonoaudiología": "Realizar interconsulta con el área de Neurolingüística / Fonoaudiología para profundizar la evaluación y el abordaje de los aspectos fonológicos, comprensivos y expresivos del lenguaje.",
        "Maestra de Apoyo a la Inclusión (MAI)": "Evaluar la incorporación de dispositivo de apoyo a la inclusión escolar para acompañar la organización de la tarea en el aula y mediar en las adaptaciones pedagógicas.",
        "Control evolutivo / Reevaluación": "Realizar una reevaluación neuropsicológica/psicopedagógica de control en el plazo de 12 a 18 meses para monitorear su evolución.",
    },
    "escolares": {
        "Ubicación y control de distractores": "Ubicar al alumno/a en los primeros bancos, cerca del docente y lejos de estímulos distractores (ventanas, puertas o zonas de alto tránsito), manteniendo su escritorio despejado únicamente con los materiales necesarios para la actividad en curso.",
        "Segmentación de consignas": "Brindar consignas breves, claras y secuenciadas de a un paso por vez. Asegurar el contacto visual al darle una indicación y verificar la comprensión pidiéndole que explique con sus propias palabras lo que debe realizar.",
        "Gestión del tiempo y fragmentación de tareas": "Fragmentar las tareas extensas o evaluaciones en bloques más cortos, otorgando tiempo adicional para su resolución y priorizando la calidad conceptual por sobre la cantidad de ejercicios mecánicos repetitivos.",
        "Apoyos visuales y funciones ejecutivas": "Implementar apoyos visuales, agendas anticipatorias, uso de calendarios a la vista y listas de chequeo (checklists) para la organización de materiales, entregas y armado de la mochila.",
        "Pausas activas y regulación motora": "Permitir breves pausas activas programadas y funcionales dentro del ámbito escolar (ej. borrar el pizarrón, repartir material o llevar un recado) cuando se observe fatiga cognitiva o inquietud motora.",
        "Adaptaciones en Lectoescritura": "Priorizar la evaluación oral o el uso de formatos estructurados (opción múltiple, unir con flechas, completar palabras clave) para evitar que la fatiga lectora o grafomotora penalice la demostración de conocimientos. No exponer a la lectura en voz alta frente al grupo sin preparación previa.",
        "Adaptaciones en Matemática y Cálculo": "Permitir el uso de apoyos concretos, tabla pitagórica, grillas numéricas o calculadora en resoluciones complejas, a fin de no penalizar el razonamiento lógico-matemático por fallas en la memoria operativa o en la automatización del cálculo.",
        "Refuerzo positivo y motivación": "Reforzar positivamente sus logros y el esfuerzo sostenido durante el proceso de trabajo, evitando la sobrecorrección punitiva frente al error para preservar su autoestima académica.",
    },
}
