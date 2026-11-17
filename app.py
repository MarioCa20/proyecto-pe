"""Calificador Automático con IA — Interfaz Streamlit (Equipo 5)"""
import json
import os
import uuid
import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuración global
# ---------------------------------------------------------------------------
load_dotenv()

st.set_page_config(
    page_title="Calificador Automático — Equipo 5",
    page_icon="📝",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Clave API
# ---------------------------------------------------------------------------
if not os.getenv("GEMINI_API_KEY"):
    st.error(
        "Falta `GEMINI_API_KEY`. Crea un archivo `.env` en la raíz del proyecto "
        "(copia `.env.example`) y agrega tu clave: `GEMINI_API_KEY=tu_clave_aqui`."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Importar backend
# ---------------------------------------------------------------------------
from src.grader import calificar, calificar_multipartida

# ---------------------------------------------------------------------------
# Datos iniciales
# ---------------------------------------------------------------------------
RUBRICA_INICIAL = [
    {
        "nombre": "Contenido",
        "descripcion": "Dominio y precisión conceptual del tema solicitado.",
        "max_puntos": 20,
    },
    {
        "nombre": "Estructura",
        "descripcion": "Organización lógica (introducción, desarrollo y cierre).",
        "max_puntos": 20,
    },
    {
        "nombre": "Argumentación",
        "descripcion": "Solidez de las ideas y uso de ejemplos o evidencias.",
        "max_puntos": 20,
    },
    {
        "nombre": "Claridad",
        "descripcion": "Redacción fluida, ortografía y vocabulario adecuado.",
        "max_puntos": 20,
    },
    {
        "nombre": "Originalidad",
        "descripcion": "Aporte crítico y enfoque propio frente al problema.",
        "max_puntos": 20,
    },
]

RESPUESTA_EJEMPLO = (
    "La inteligencia artificial generativa está transformando la educación superior al "
    "permitir retroalimentación inmediata en tareas escritas. Sin embargo, su implementación "
    "exige diseñar rúbricas claras y prompts bien estructurados para evitar sesgos en la calificación."
)

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def obtener_versiones_prompt() -> list[str]:
    """Detecta automáticamente los archivos .md disponibles en prompts/."""
    carpeta = Path("prompts")
    if not carpeta.exists():
        return ["v1"]
    versiones = sorted(archivo.stem for archivo in carpeta.glob("*.md"))
    return versiones if versiones else ["v1"]


def extraer_texto_archivo(archivo) -> str:
    """Extrae texto de un archivo .txt o .pdf subido por el usuario."""
    if archivo is None:
        return ""
    if archivo.name.endswith(".txt"):
        return archivo.read().decode("utf-8", errors="ignore")
    if archivo.name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            lector = PdfReader(archivo)
            return "\n".join(p.extract_text() or "" for p in lector.pages).strip()
        except ImportError:
            st.error(
                "Para leer PDF instala pypdf: `pip install pypdf` (dentro del venv)."
            )
            return ""
    return ""


def _inicializar_session_state():
    """Asegura variables de session_state que persisten entre reruns."""
    if "historial" not in st.session_state:
        st.session_state.historial = []
    if "modo_demo" not in st.session_state:
        st.session_state.modo_demo = False


# Calificación de demostración (sin API)
CALIFICACION_DEMO = {
    "criterios": [
        {
            "criterio": "Contenido",
            "puntaje": 16,
            "max_puntos": 20,
            "justificacion": (
                "La respuesta aborda el tema central pero carece de profundidad. "
                "Menciona conceptos clave sin desarrollarlos con evidencia."
            ),
        },
        {
            "criterio": "Estructura",
            "puntaje": 14,
            "max_puntos": 20,
            "justificacion": (
                "El texto tiene una introducción clara, pero el desarrollo "
                "podría organizarse mejor con párrafos diferenciados."
            ),
        },
        {
            "criterio": "Argumentación",
            "puntaje": 13,
            "max_puntos": 20,
            "justificacion": (
                "Se presentan ideas pero con poco sustento empírico o ejemplos concretos."
            ),
        },
        {
            "criterio": "Claridad",
            "puntaje": 17,
            "max_puntos": 20,
            "justificacion": (
                "Redacción comprensible y con ortografía correcta. Vocabulario apropiado."
            ),
        },
        {
            "criterio": "Originalidad",
            "puntaje": 12,
            "max_puntos": 20,
            "justificacion": (
                "El enfoque es convencional; no se identifica una perspectiva propia destacada."
            ),
        },
    ],
    "total": 72,
    "total_max": 100,
    "comentario_general": (
        "Respuesta adecuada pero superficial. Mejorar en profundidad del análisis "
        "y aportes críticos personales."
    ),
    "meta": {
        "modelo": "demo (simulado)",
        "prompt": "v1",
        "indice_libertad": 0.0,
        "temperatura": 0.0,
        "segundos": 0.01,
    },
}

# ---------------------------------------------------------------------------
# Estilos CSS personalizados
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
    .stMarkdown h1 { font-size: 2rem; margin-bottom: 0.3rem; }
    .stMarkdown h2 { font-size: 1.5rem; margin-top: 1.5rem; margin-bottom: 0.4rem; }
    .stMarkdown h3 { font-size: 1.2rem; }
    .css-1d3r118, [data-testid="stSidebar"] {
        background-color: var(--background-color) !important;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { height: 40px; border-radius: 8px 8px 0 0; padding: 0 16px; }
    #footer { display: none; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Inicializar estado
# ---------------------------------------------------------------------------
_inicializar_session_state()

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚙️ Configuración")

    versiones_disponibles = obtener_versiones_prompt()
    version_prompt = st.selectbox(
        "📄 Versión del Prompt",
        options=versiones_disponibles,
        index=len(versiones_disponibles) - 1,
        help="Carpeta `prompts/`. Detecta automáticamente *.md.",
    )

    indice_libertad = st.slider(
        "🕊️ Índice de libertad",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.1,
        help="Controla qué tan permisivo o flexible es el modelo al evaluar. 0.0 = Estricto y riguroso. 1.0 = Muy permisivo y flexible.",
    )

    st.divider()

    st.markdown("### 🎭 Modo Demo")
    st.session_state.modo_demo = st.toggle(
        "Simular calificación",
        value=False,
        help="Califica sin gastar cuota de API. Útil para probar la interfaz.",
    )

    st.divider()

    st.markdown("### 🧑‍🏫 Referencia Humana")
    comparar_humano = st.checkbox(
        "Comparar con nota humana",
        value=True,
        help="Muestra una métrica comparativa con la nota que asignes manualmente.",
    )

    st.divider()

    st.markdown("### 📋 Historial")
    st.caption(f"{len(st.session_state.historial)} calificación(es)")
    if st.session_state.historial:
        if st.button("🗑️ Limpiar historial", use_container_width=True, type="secondary"):
            st.session_state.historial = []
            st.rerun()

    st.divider()
    st.caption("Equipo 5 • Prompt Engineering • 2026-2")

# ---------------------------------------------------------------------------
# Pestañas principales
# ---------------------------------------------------------------------------
tab_evaluar, tab_masiva, tab_historial = st.tabs(["📝 Evaluar", "📚 Calificación masiva", "📊 Historial"])

# ===================================================================
# TAB 1: EVALUAR
# ===================================================================
with tab_evaluar:
    st.title("Calificador Automático con Rúbrica")
    st.caption(
        "Evalúa respuestas de estudiantes con criterios estructurados. "
        "Compara el resultado con la calificación humana."
    )

    # --- PASO 1: Rúbrica ---
    st.subheader("1. Rúbrica de evaluación")
    st.caption(
        "Edita criterios en la tabla o sube un archivo `.json` o `.xlsx` con las columnas: "
        "`nombre`, `descripcion`, `max_puntos`."
    )

    archivo_rubrica = st.file_uploader(
        "📂 Cargar rúbrica desde archivo (.json o .xlsx)",
        type=["json", "xlsx"],
        key="file_rubrica",
        help="Reemplaza la rúbrica predeterminada con la tuya.",
    )

    rubrica_base = RUBRICA_INICIAL
    if archivo_rubrica is not None:
        try:
            nombre = archivo_rubrica.name.lower()
            if nombre.endswith(".json"):
                datos_json = json.load(archivo_rubrica)
                if isinstance(datos_json, list) and all(
                    {"nombre", "descripcion", "max_puntos"}.issubset(item.keys())
                    for item in datos_json
                ):
                    rubrica_base = datos_json
                else:
                    st.warning(
                        "⚠️ El JSON debe ser una lista de objetos con las llaves: "
                        "`nombre`, `descripcion` y `max_puntos`."
                    )
            elif nombre.endswith(".xlsx"):
                from src.grader import cargar_rubrica_excel
                archivo_rubrica.seek(0)
                rubrica_base = cargar_rubrica_excel(archivo_rubrica)
                if not rubrica_base:
                    st.warning(
                        "⚠️ No se encontraron criterios en el xlsx. "
                        "Asegúrate de que las columnas sean: "
                        "`nombre`, `descripcion`, `max_puntos`."
                    )
            else:
                st.error(
                    "❌ Formato no soportado. Sube un archivo `.json` o `.xlsx`."
                )
        except Exception as e:
            st.error(f"❌ No se pudo leer el archivo: `{e}`")

    rubrica_editada = st.data_editor(
        rubrica_base,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "nombre": st.column_config.TextColumn("Criterio", required=True),
            "descripcion": st.column_config.TextColumn(
                "Descripción", width="large", required=True
            ),
            "max_puntos": st.column_config.NumberColumn(
                "Puntos Máx.", min_value=1, max_value=100, step=1, required=True
            ),
        },
        hide_index=True,
    )

    rubrica_limpia = [
        {
            "nombre": str(fila["nombre"]).strip(),
            "descripcion": str(fila.get("descripcion") or "").strip(),
            "max_puntos": float(fila["max_puntos"]),
        }
        for fila in rubrica_editada
        if fila.get("nombre") and str(fila["nombre"]).strip() and fila.get("max_puntos")
    ]

    puntaje_max_rubrica = sum(c["max_puntos"] for c in rubrica_limpia)

    if not rubrica_limpia:
        st.warning("⚠️ Debes definir al menos un criterio válido en la rúbrica.")

    st.caption(f"**Puntaje máximo total:** {puntaje_max_rubrica:g} pts")

    nota_humana: float = 0.0  # type: ignore[assignment]

    if rubrica_limpia and puntaje_max_rubrica > 0:
        placeholder_nota_humana = st.empty()
        with placeholder_nota_humana:
            nota_humana = st.number_input(
                f"🧑‍🏫 Calificación humana (0 – {puntaje_max_rubrica:g})",
                min_value=0.0,
                max_value=float(puntaje_max_rubrica),
                value=min(87.0, float(puntaje_max_rubrica)),
                step=0.5,
                disabled=not comparar_humano,
            )

    # --- PASO 2: Pregunta y respuesta ---
    st.subheader("2. Enunciado y respuesta del estudiante")

    pregunta_input = st.text_area(
        "📌 Pregunta o consigna (opcional)",
        placeholder="Ej: Explica cómo influye la IA generativa en la educación superior...",
        height=80,
    )

    archivo_respuesta = st.file_uploader(
        "📄 Subir respuesta del estudiante (.txt o .pdf)",
        type=["txt", "pdf"],
        key="file_respuesta",
    )

    texto_archivo = extraer_texto_archivo(archivo_respuesta) if archivo_respuesta else ""

    respuesta_input = st.text_area(
        "✍️ Respuesta del estudiante",
        value=texto_archivo or RESPUESTA_EJEMPLO,
        height=200,
        help="Escribe o pega aquí la respuesta a calificar.",
    )

    # --- Validaciones previas ---
    errores_previos = []
    if not rubrica_limpia:
        errores_previos.append("Define al menos un criterio en la rúbrica.")
    if not respuesta_input.strip():
        errores_previos.append("El campo de respuesta está vacío.")

    if errores_previos:
        with st.expander("⚠️ Correcciones necesarias antes de calificar", expanded=False):
            for err in errores_previos:
                st.warning(err)

    # --- Botón calificar ---
    col_btn, col_demo = st.columns([1, 3])
    with col_btn:
        boton_calificar = st.button(
            "🚀 Calificar con IA",
            type="primary",
            use_container_width=True,
            disabled=bool(errores_previos),
        )
    with col_demo:
        if st.session_state.modo_demo:
            st.caption("🎭 Modo demo activado — no se usará la API")

    # --- PASO 3: Resultados ---
    resultado: dict = {}  # type: ignore[assignment]

    if boton_calificar:
        texto_final = respuesta_input.strip()
        if pregunta_input.strip():
            texto_final = (
                f"PREGUNTA:\n{pregunta_input.strip()}\n\n"
                f"RESPUESTA:\n{texto_final}"
            )

        if st.session_state.modo_demo:
            with st.spinner("🎭 Simulando calificación en modo demo..."):
                resultado = CALIFICACION_DEMO.copy()
                # Ajustar total_max a la rúbrica real si es distinta
                if rubrica_limpia:
                    nuevo_max = sum(c["max_puntos"] for c in rubrica_limpia)
                    resultado["total_max"] = nuevo_max
                    for c in resultado["criterios"]:
                        c["max_puntos"] = nuevo_max // len(resultado["criterios"])
                    resultado["total"] = sum(c["puntaje"] for c in resultado["criterios"])
                resultado["meta"]["prompt"] = version_prompt
        else:
            with st.spinner(
                f"🔄 Evaluando con Gemini (prompt `{version_prompt}`)..."
            ):
                try:
                    resultado = calificar(
                        rubrica=rubrica_limpia,
                        respuesta=texto_final,
                        version_prompt=version_prompt,
                        indice_libertad=indice_libertad,
                    )
                except Exception as e:
                    st.error(f"❌ Error al evaluar: `{e}`")
                    st.stop()

        # Guardar en historial
        entrada = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "version_prompt": version_prompt,
            "indice_libertad": indice_libertad,
            "temperatura": indice_libertad,
            "total": resultado["total"],
            "total_max": resultado["total_max"],
            "comentario_general": resultado.get("comentario_general", ""),
            "criterios": resultado.get("criterios", []),
            "nota_humana": nota_humana if (comparar_humano and rubrica_limpia) else None,
            "comparar_humano": comparar_humano,
            "simulada": st.session_state.modo_demo,
            "estudiante": "Individual",
            "respuesta": texto_final if not st.session_state.modo_demo else "[demo]",
        }
        st.session_state.historial.insert(0, entrada)

        st.divider()
        st.subheader("3. Resultado de la evaluación")

        total_ia = resultado["total"]
        total_max = resultado["total_max"]

        if comparar_humano and rubrica_limpia:
            m1, m2, m3 = st.columns(3)
            diferencia = total_ia - nota_humana
            m1.metric(
                label=f"🤖 IA ({version_prompt})",
                value=f"{total_ia:g} / {total_max:g}",
            )
            m2.metric(
                label="🧑‍🏫 Humana",
                value=f"{nota_humana:g} / {total_max:g}",
            )
            m3.metric(
                label="📊 Diferencia",
                value=f"{diferencia:+g} pts",
                delta=f"{diferencia:+g} pts",
                delta_color="off",
            )
        else:
            st.metric(
                label=f"🤖 Puntaje Total ({version_prompt})",
                value=f"{total_ia:g} / {total_max:g}",
            )

        if resultado.get("comentario_general"):
            st.info(f"**💬 Comentario general:** {resultado['comentario_general']}")

        st.subheader("4. Desglose por criterio")
        for item in resultado["criterios"]:
            max_p = item["max_puntos"]
            punt = item["puntaje"]
            porcentaje = punt / max_p if max_p > 0 else 0.0

            if porcentaje >= 0.8:
                emoji = "✅"
            elif porcentaje >= 0.5:
                emoji = "⚠️"
            else:
                emoji = "❌"

            with st.container():
                col_icon, col_nombre, col_barra = st.columns([0.3, 1, 3])
                with col_icon:
                    st.markdown(
                        f"<div style='font-size:1.4rem'>{emoji}</div>",
                        unsafe_allow_html=True,
                    )
                with col_nombre:
                    st.markdown(
                        f"**{item['criterio']}**: {punt:g} / {max_p:g}"
                    )
                with col_barra:
                    st.progress(min(1.0, max(0.0, porcentaje)))
                with st.container():
                    with st.expander(f"💡 Justificación de {item['criterio']}"):
                        st.write(item.get("justificacion", "Sin justificación."))

        meta = resultado.get("meta", {})
        libertad_meta = meta.get("indice_libertad", meta.get("temperatura", "?"))
        st.caption(
            f"🔧 Modelo: `{meta.get('modelo', '?')}` • "
            f"Prompt: `{meta.get('prompt', '?')}` • "
            f"Índice de libertad: `{libertad_meta}` • "
            f"Tiempo: `{meta.get('segundos', '?')}s`"
        )

        col_export, col_colap = st.columns([1, 2])
        with col_export:
            json_str = json.dumps(resultado, ensure_ascii=False, indent=2)
            st.download_button(
                label="💾 Descargar resultado (JSON)",
                data=json_str,
                file_name=(
                    f"calificacion_{version_prompt}_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                ),
                mime="application/json",
                use_container_width=True,
            )

# ===================================================================
# TAB 2: CALIFICACIÓN MASIVA
# ===================================================================
with tab_masiva:
    st.title("📚 Calificación masiva de estudiantes")
    st.caption(
        "Sube un `.xlsx` con las respuestas de varios estudiantes y califícalas todas "
        "de una vez con la rúbrica configurada."
    )

    # --- Instrucciones de formato ---
    st.info(
        "**Formato del archivo xlsx:**\n"
        "- Columna **estudiante** (o *nombre_estudiante*, *nombre*): nombre del estudiante.\n"
        "- Columna **respuesta**: texto de la respuesta.\n"
        "- Columna opcional **nota_humana**: nota que asignaste manualmente.\n\n"
        "Puedes usar la rúbrica cargada arriba o la predeterminada."
    )

    # --- Configurar cantidad de intentos ---
    col_attempts, col_demo2 = st.columns(2)
    with col_attempts:
        max_reintentos = st.number_input(
            "🔄 Max. reintentos por respuesta",
            min_value=1,
            max_value=10,
            value=3,
            step=1,
            help="Si la API falla, se reintentará hasta esta cantidad.",
        )
    with col_demo2:
        demo_masiva = st.toggle(
            "🎭 Modo demo",
            value=False,
            help="Califica sin gastar cuota de API.",
        )

    # --- Validar rúbrica ---
    rubrica_limpia_masiva = [
        {
            "nombre": str(fila["nombre"]).strip(),
            "descripcion": str(fila.get("descripcion") or "").strip(),
            "max_puntos": float(fila["max_puntos"]),
        }
        for fila in rubrica_editada
        if fila.get("nombre") and str(fila["nombre"]).strip() and fila.get("max_puntos")
    ]

    if not rubrica_limpia_masiva:
        st.warning("⚠️ Define al menos un criterio en la rúbrica antes de calificar masivamente.")

    puntaje_max_masiva = sum(c["max_puntos"] for c in rubrica_limpia_masiva)

    # --- Subir archivo de respuestas ---
    archivo_respuestas = st.file_uploader(
        "📄 Subir respuestas de estudiantes (.xlsx)",
        type=["xlsx"],
        key="file_respuestas",
        help="Cada fila es un estudiante con su respuesta.",
    )

    # --- Procesar xlsx ---
    respuestas_cargadas: list[dict] = []
    if archivo_respuestas is not None:
        try:
            from src.grader import cargar_respuestas_excel
            archivo_respuestas.seek(0)
            respuestas_cargadas = cargar_respuestas_excel(archivo_respuestas)
            if not respuestas_cargadas:
                st.error("❌ No se encontraron filas válidas en el xlsx.")
            else:
                st.success(f"✅ {len(respuestas_cargadas)} respuesta(s) detectada(s).")
        except Exception as e:
            st.error(f"❌ No se pudo leer el archivo: `{e}`")

    # --- Botón calificar masiva ---
    boton_masivo = st.button(
        "🚀 Calificar todos",
        type="primary",
        use_container_width=True,
        disabled=not respuestas_cargadas or not rubrica_limpia_masiva,
    )

    # --- Resultados masivos ---
    if boton_masivo and respuestas_cargadas and rubrica_limpia_masiva:
        resultados_masivos = []

        if demo_masiva:
            with st.spinner("🎭 Simulando calificación masiva..."):
                for resp in respuestas_cargadas:
                    demo = CALIFICACION_DEMO.copy()
                    nuevo_max = puntaje_max_masiva
                    demo["total_max"] = nuevo_max
                    demo["total"] = sum(c["puntaje"] for c in demo["criterios"])
                    for c in demo["criterios"]:
                        c["max_puntos"] = nuevo_max // len(demo["criterios"])
                    resultados_masivos.append({
                        "nombre": resp["nombre"],
                        "nota_humana": resp.get("nota_humana"),
                        "respuesta": resp["respuesta"],
                        **demo,
                        "error": None,
                    })
        else:
            with st.spinner(f"🔄 Evaluando {len(respuestas_cargadas)} respuesta(s)..."):
                try:
                    resultados_masivos = calificar_multipartida(
                        rubrica=rubrica_limpia_masiva,
                        respuestas=respuestas_cargadas,
                        version_prompt=version_prompt,
                        indice_libertad=indice_libertad,
                        reintentos=max_reintentos,
                    )
                except Exception as e:
                    st.error(f"❌ Error al evaluar: `{e}`")
                    resultados_masivos = []

        if resultados_masivos:
            st.divider()
            st.subheader("📊 Resultados de calificación masiva")

            # Tabla resumen
            resumen_rows = []
            for r in resultados_masivos:
                fila = {
                    "Estudiante": r["nombre"],
                    "Puntaje": f'{r["total"]}/{r["total_max"]}' if r["total"] is not None else "❌ Error",
                }
                if r.get("nota_humana") is not None:
                    diff = (r["total"] or 0) - r["nota_humana"]
                    fila["Diferencia"] = f"{diff:+g}" if r["total"] is not None else "—"
                if r.get("error"):
                    fila["Error"] = "Sí"
                resumen_rows.append(fila)

            # Guardar en historial (una entrada por resultado, en orden con respuestas_cargadas)
            for r, resp in zip(resultados_masivos, respuestas_cargadas):
                entrada = {
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "version_prompt": version_prompt,
                    "indice_libertad": indice_libertad,
                    "temperatura": indice_libertad,
                    "total": r.get("total"),
                    "total_max": r["total_max"],
                    "comentario_general": r.get("comentario_general", ""),
                    "criterios": r.get("criterios", []),
                    "nota_humana": r.get("nota_humana"),
                    "comparar_humano": False,
                    "simulada": demo_masiva,
                    "estudiante": r["nombre"],
                    "respuesta": r.get("respuesta", "") if demo_masiva else resp["respuesta"],
                    "meta": r.get("meta", {}),
                }
                st.session_state.historial.insert(0, entrada)

            resumen_df = pd.DataFrame(resumen_rows)
            st.dataframe(resumen_df, use_container_width=True, hide_index=True)

            # Botón descargar xlsx con todos los resultados
            if not demo_masiva:
                # Convertir a xlsx con desglose
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
                    resumen_df.to_excel(writer, index=False, sheet_name="Resumen")

                    # Hoja con desglose por criterio
                    desglose_rows = []
                    for r in resultados_masivos:
                        for c in r.get("criterios", []):
                            desglose_rows.append({
                                "Estudiante": r["nombre"],
                                "Criterio": c["criterio"],
                                "Puntaje": c["puntaje"],
                                "Máximo": c["max_puntos"],
                                "Justificación": c.get("justificacion", ""),
                            })
                    if desglose_rows:
                        df_desglose = pd.DataFrame(desglose_rows)
                        df_desglose.to_excel(writer, index=False, sheet_name="Desglose")

                excel_buf.seek(0)
                st.download_button(
                    label="💾 Descargar resultados (xlsx)",
                    data=excel_buf,
                    file_name=f"calificaciones_{version_prompt}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

            st.caption(f"**{sum(1 for r in resultados_masivos if not r.get('error'))}/{len(resultados_masivos)}** calificación(es) exitosa(s).")

# ===================================================================
# TAB 3: HISTORIAL
# ===================================================================
with tab_historial:
    st.title("📊 Historial de Calificaciones")
    st.caption("Guarda automáticamente cada calificación durante esta sesión.")

    historial = st.session_state.historial
    if not historial:
        st.info(
            "📭 Aún no hay calificaciones. Ve a la pestaña **Evaluar** para comenzar."
        )
    else:
        st.markdown(f"**{len(historial)} calificación(es) en esta sesión**")

        for i, entry in enumerate(historial):
            est = entry.get("estudiante", "Individual")
            label_est = f" — {est}" if est != "Individual" else ""
            total_str = (
                f'{entry["total"]}/{entry["total_max"]}'
                if entry.get("total") is not None
                else "❌ Error"
            )
            etiqueta = f"📄 #{i + 1} — {total_str} pts — {entry['timestamp']}{label_est}"
            if entry.get("simulada"):
                etiqueta += " (demo)"
            with st.expander(etiqueta, expanded=False):
                # --- Estudiante + puntaje ---
                col_est, col_pts, col_params = st.columns(3)
                with col_est:
                    st.markdown(f"**👤 {est}**")
                with col_pts:
                    st.metric("Puntaje IA", f'{entry["total"]}/{entry["total_max"]}' if entry.get("total") is not None else "❌ Error")
                if entry.get("comparar_humano") and entry.get("nota_humana") is not None:
                    diff = entry["total"] - entry["nota_humana"]
                    col_pts.metric("Nota Humana", f'{entry["nota_humana"]}/{entry["total_max"]}')
                    col_params.metric("Diferencia", f"{diff:+g} pts")
                else:
                    col_pts.metric("Prompt", entry.get("version_prompt", "?"))
                    col_params.metric(
                        "Índice de libertad",
                        entry.get("indice_libertad", entry.get("temperatura", 0)),
                    )

                # --- Respuesta del estudiante ---
                if entry.get("respuesta"):
                    st.markdown("**📝 Respuesta del estudiante:**")
                    st.info(entry["respuesta"])

                # --- Comentario general ---
                if entry.get("comentario_general"):
                    st.info(f"💬 {entry['comentario_general']}")

                # --- Desglose por criterio ---
                criterios = entry.get("criterios", [])
                if criterios:
                    st.subheader("📋 Desglose por criterio:")
                    for crit in criterios:
                        crit_nombre = crit.get("criterio", "Sin nombre")
                        puntaje = crit.get("puntaje", 0)
                        max_p = crit.get("max_puntos", 0)
                        justificacion = crit.get("justificacion", "")
                        pct = puntaje / max_p if max_p > 0 else 0

                        if pct >= 0.8:
                            emoji = "✅"
                        elif pct >= 0.5:
                            emoji = "⚠️"
                        else:
                            emoji = "❌"

                        with st.container():
                            st.markdown(f"{emoji} **{crit_nombre}**: {puntaje} / {max_p}")
                            st.progress(min(1.0, max(0.0, pct)))
                            if justificacion:
                                with st.expander(f"💡 Justificación de {crit_nombre}"):
                                    st.write(justificacion)

                # --- Meta info ---
                meta = entry.get("meta", {})
                if meta:
                    libertad_meta = meta.get("indice_libertad", meta.get("temperatura", "?"))
                    st.caption(
                        f"🔧 Modelo: `{meta.get('modelo', '?')}` • "
                        f"Prompt: `{meta.get('prompt', '?')}` • "
                        f"Índice de libertad: `{libertad_meta}` • "
                        f"Tiempo: `{meta.get('segundos', '?')}s`"
                    )
