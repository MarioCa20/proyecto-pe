import json
import os
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st

# Cargar variables de entorno (.env) antes de importar grader.py
load_dotenv()

st.set_page_config(
    page_title="Calificador Automático - Equipo 5", page_icon="📝", layout="wide"
)

# Verificar que exista la API Key antes de importar grader.py
if not os.getenv("GEMINI_API_KEY"):
    st.error(
        "Falta configurar `GEMINI_API_KEY`. Crea un archivo `.env` en la raíz del proyecto "
        "(puedes copiar `.env.example`) y agrega tu clave: `GEMINI_API_KEY=tu_clave_aqui`."
    )
    st.stop()

from grader import calificar

# --- DATOS INICIALES DE EJEMPLO ---
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


def obtener_versiones_prompt() -> list[str]:
    """Detecta automáticamente los archivos .md disponibles en la carpeta prompts/."""
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
            st.error("Para leer PDF instala pypdf en tu terminal: `pip install pypdf`")
            return ""
    return ""


# --- BARRA LATERAL ---
with st.sidebar:
    st.header("Configuración del Modelo")
    versiones_disponibles = obtener_versiones_prompt()
    version_prompt = st.selectbox(
        "Versión del Prompt (`prompts/*.md`)",
        options=versiones_disponibles,
        index=len(versiones_disponibles) - 1,
        help="Lista automáticamente los prompts disponibles en la carpeta prompts/.",
    )

    temperatura = st.slider(
        "Temperatura",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.1,
        help="0.0 hace que la calificación sea lo más consistente y determinista posible.",
    )

    st.divider()
    st.subheader("Referencia Humana")
    comparar_humano = st.checkbox("Comparar con nota humana", value=True)
    # El límite máximo de la nota humana se ajusta más abajo según la suma de la rúbrica
    placeholder_nota_humana = st.empty()

    st.divider()
    st.caption("Equipo 5 • Prompt Engineering")

# --- PANTALLA PRINCIPAL ---
st.title("Calificador Automático con Rúbrica")
st.write(
    "Evalúa respuestas de estudiantes con criterios estructurados y compáralas con la calificación humana."
)

# PASO 1: Configurar rúbrica (formato list[dict] que espera grader.py)
st.subheader("1. Rúbrica de evaluación")
st.caption(
    "Edita los criterios directamente en la tabla, agrega/elimina filas o sube un archivo `.json`."
)

archivo_rubrica = st.file_uploader(
    "Cargar rúbrica desde archivo (.json opcional)",
    type=["json"],
    key="file_rubrica",
)

rubrica_base = RUBRICA_INICIAL
if archivo_rubrica is not None:
    try:
        datos_json = json.load(archivo_rubrica)
        if isinstance(datos_json, list) and all(
            {"nombre", "descripcion", "max_puntos"}.issubset(item.keys())
            for item in datos_json
        ):
            rubrica_base = datos_json
        else:
            st.warning(
                "El JSON debe ser una lista de objetos con las llaves: `nombre`, `descripcion` y `max_puntos`."
            )
    except Exception as e:
        st.error(f"No se pudo leer el JSON de la rúbrica: {e}")

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
)

# Limpiar filas vacías para cumplir exactamente con grader.py
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
st.caption(f"**Puntaje máximo total de la rúbrica:** {puntaje_max_rubrica:g} pts")

# Completar el input de nota humana en la barra lateral con el máximo real de la rúbrica
with placeholder_nota_humana:
    nota_humana = st.number_input(
        f"Calificación humana (0 - {puntaje_max_rubrica:g})",
        min_value=0.0,
        max_value=float(puntaje_max_rubrica) if puntaje_max_rubrica > 0 else 100.0,
        value=min(87.0, float(puntaje_max_rubrica)),
        step=0.5,
        disabled=not comparar_humano,
    )

# PASO 2: Pregunta (opcional) y respuesta del estudiante
st.subheader("2. Enunciado y respuesta del estudiante")

pregunta_input = st.text_area(
    "Pregunta o consigna (opcional — se incluye junto a la respuesta si la completas)",
    placeholder="Ej: Explica cómo influye la IA generativa en la educación superior...",
    height=80,
)

archivo_respuesta = st.file_uploader(
    "Subir respuesta del estudiante (.txt o .pdf)",
    type=["txt", "pdf"],
    key="file_respuesta",
)
texto_respuesta = (
    extraer_texto_archivo(archivo_respuesta)
    if archivo_respuesta is not None
    else RESPUESTA_EJEMPLO
)

respuesta_input = st.text_area(
    "Respuesta del estudiante",
    value=texto_respuesta,
    height=180,
)

boton_calificar = st.button(
    "Calificar con IA", type="primary", use_container_width=True
)

# PASO 3: Llamada real a grader.py y visualización de resultados
if boton_calificar:
    if not rubrica_limpia:
        st.warning("Debes definir al menos un criterio válido en la rúbrica.")
    elif not respuesta_input.strip():
        st.warning("Por favor ingresa o sube la respuesta del estudiante.")
    else:
        # Como grader.calificar recibe (rubrica, respuesta), si hay pregunta la integramos arriba
        texto_final = respuesta_input.strip()
        if pregunta_input.strip():
            texto_final = (
                f"PREGUNTA:\n{pregunta_input.strip()}\n\n"
                f"RESPUESTA:\n{texto_final}"
            )

        with st.spinner(
            f"Evaluando con Gemini usando el prompt `{version_prompt}`..."
        ):
            try:
                resultado = calificar(
                    rubrica=rubrica_limpia,
                    respuesta=texto_final,
                    version_prompt=version_prompt,
                    temperatura=temperatura,
                )
            except Exception as e:
                st.error(f"Error al evaluar con `grader.py`: {e}")
                st.stop()

        st.divider()
        st.subheader("3. Resultado de la evaluación")

        total_ia = resultado["total"]
        total_max = resultado["total_max"]

        if comparar_humano:
            m1, m2, m3 = st.columns(3)
            diferencia = total_ia - nota_humana
            m1.metric(
                label=f"Puntaje IA ({resultado['meta']['prompt']})",
                value=f"{total_ia:g} / {total_max:g}",
            )
            m2.metric(
                label="Calificación Humana",
                value=f"{nota_humana:g} / {total_max:g}",
            )
            m3.metric(
                label="Diferencia (IA - Humano)",
                value=f"{diferencia:+g} pts",
                delta=f"{diferencia:+g} pts",
                delta_color="off",
            )
        else:
            st.metric(
                label=f"Puntaje Total ({resultado['meta']['prompt']})",
                value=f"{total_ia:g} / {total_max:g}",
            )

        if resultado.get("comentario_general"):
            st.info(f"**Comentario general:** {resultado['comentario_general']}")

        # Desglose por criterio usando las llaves exactas de grader.py
        st.subheader("4. Desglose por criterio")
        for item in resultado["criterios"]:
            porcentaje = (
                item["puntaje"] / item["max_puntos"] if item["max_puntos"] > 0 else 0.0
            )
            col_nombre, col_barra = st.columns([1, 3])
            with col_nombre:
                st.markdown(
                    f"**{item['criterio']}**: {item['puntaje']:g} / {item['max_puntos']:g}"
                )
            with col_barra:
                st.progress(min(1.0, max(0.0, porcentaje)))

            with st.expander(f"Ver justificación de {item['criterio']}"):
                st.write(item["justificacion"])

        # Metadatos técnicos que devuelve grader.py
        meta = resultado.get("meta", {})
        if meta:
            st.caption(
                f"Modelo: `{meta.get('modelo')}` • Prompt: `{meta.get('prompt')}` • "
                f"Temperatura: `{meta.get('temperatura')}` • Tiempo: `{meta.get('segundos')}s`"
            )