"""Calificador Automático con IA — Interfaz Streamlit (Equipo 5)"""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

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
from src.grader import calificar

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

    temperatura = st.slider(
        "🌡️ Temperatura",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.1,
        help="0.0 = más determinista. 1.0 = más creativo/varied.",
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
tab_evaluar, tab_historial = st.tabs(["📝 Evaluar", "📊 Historial"])

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
                    texto_final = respuesta_input.strip()
                    if pregunta_input.strip():
                        texto_final = (
                            f"PREGUNTA:\n{pregunta_input.strip()}\n\n"
                            f"RESPUESTA:\n{texto_final}"
                        )

                    resultado = calificar(
                        rubrica=rubrica_limpia,
                        respuesta=texto_final,
                        version_prompt=version_prompt,
                        temperatura=temperatura,
                    )
                except Exception as e:
                    st.error(f"❌ Error al evaluar: `{e}`")
                    st.stop()

        # Guardar en historial
        entrada = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "version_prompt": version_prompt,
            "temperatura": temperatura,
            "total": resultado["total"],
            "total_max": resultado["total_max"],
            "comentario_general": resultado.get("comentario_general", ""),
            "criterios": resultado.get("criterios", []),
            "nota_humana": nota_humana if (comparar_humano and rubrica_limpia) else None,
            "comparar_humano": comparar_humano,
            "simulada": st.session_state.modo_demo,
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
        st.caption(
            f"🔧 Modelo: `{meta.get('modelo', '?')}` • "
            f"Prompt: `{meta.get('prompt', '?')}` • "
            f"Temperatura: `{meta.get('temperatura', '?')}` • "
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
# TAB 2: HISTORIAL
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
            etiqueta = f"📄 #{i + 1} — {entry['total']:g}/{entry['total_max']} pts — {entry['timestamp']}"
            if entry.get("simulada"):
                etiqueta += " (demo)"
            with st.expander(etiqueta, expanded=False):
                col_info1, col_info2, col_info3 = st.columns(3)
                col_info1.metric(
                    "Puntaje IA", f"{entry['total']} / {entry['total_max']}"
                )
                if entry.get("comparar_humano") and entry.get("nota_humana") is not None:
                    diff = entry["total"] - entry["nota_humana"]
                    col_info2.metric(
                        "Nota Humana",
                        f"{entry['nota_humana']} / {entry['total_max']}",
                    )
                    col_info3.metric("Diferencia", f"{diff:+g} pts")
                else:
                    col_info2.metric("Prompt", entry.get("version_prompt", "?"))
                    col_info3.metric("Temperatura", entry.get("temperatura", 0))

                if entry.get("comentario_general"):
                    st.info(f"**💬 {entry['comentario_general']}")

                st.subheader("Desglose por criterio:")
                for crit in entry.get("criterios", []):
                    pct = (
                        crit["puntaje"] / crit["max_puntos"]
                        if crit["max_puntos"] > 0
                        else 0
                    )
                    st.progress(min(1.0, max(0.0, pct)))
                    st.markdown(
                        f"**{crit['criterio']}**: {crit['puntaje']} / {crit['max_puntos']}"
                    )
                    if crit.get("justificacion"):
                        st.caption(crit["justificacion"])
