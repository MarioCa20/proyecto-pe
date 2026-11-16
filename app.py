"""Interfaz Streamlit del calificador con IA.

Ejecutar desde la raíz del repo:  streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import streamlit as st

PROMPTS_DIR = Path("prompts")

# ---------------------------------------------------------------------------
# Conexión con el backend (grader.py, de Angel).
# Si cambia el nombre/firma de la función, solo hay que tocar calificar().
# Formato de salida esperado:
# {"criterios": [{"nombre": str, "puntaje": float, "maximo": float,
#                 "justificacion": str}, ...], "total": float}
# ---------------------------------------------------------------------------
try:
    from grader import grade_response  # ajustar al nombre real
    BACKEND_OK = True
except Exception:
    BACKEND_OK = False


def calificar(rubrica: list[dict], respuesta: str, prompt_path: Path) -> dict:
    if BACKEND_OK:
        return grade_response(rubrica, respuesta, prompt_path.read_text(encoding="utf-8"))
    # Datos de prueba para poder avanzar con la interfaz sin backend
    criterios = [
        {
            "nombre": c["criterio"],
            "puntaje": round(c["maximo"] * 0.7, 1),
            "maximo": c["maximo"],
            "justificacion": "(demo) Justificación de ejemplo.",
        }
        for c in rubrica
    ]
    return {"criterios": criterios, "total": sum(c["puntaje"] for c in criterios)}


def listar_prompts() -> list[Path]:
    return sorted(PROMPTS_DIR.glob("*.md")) if PROMPTS_DIR.exists() else []


# ---------------------------------------------------------------------------
st.set_page_config(page_title="Calificador con IA", layout="wide")
st.title("Calificador con IA")

if not BACKEND_OK:
    st.warning("No se pudo importar grader.py: usando resultados de demostración.")

with st.sidebar:
    st.header("Configuración")
    prompts = listar_prompts()
    prompt_sel = st.selectbox(
        "Versión del prompt", prompts, format_func=lambda p: p.stem
    ) if prompts else None
    if not prompts:
        st.info("No hay archivos .md en prompts/.")

col_in, col_out = st.columns(2)

with col_in:
    st.subheader("1. Rúbrica")
    rubrica_df = st.data_editor(
        pd.DataFrame(
            [
                {"criterio": "Claridad", "descripcion": "Ideas bien explicadas", "maximo": 5.0},
                {"criterio": "Contenido", "descripcion": "Precisión conceptual", "maximo": 5.0},
            ]
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="rubrica",
    )
    st.subheader("2. Respuesta del estudiante")
    respuesta = st.text_area("Pega la respuesta", height=250)
    archivo = st.file_uploader("...o sube un .txt", type=["txt"])
    if archivo:
        respuesta = archivo.read().decode("utf-8")

    st.subheader("3. Nota humana (opcional)")
    nota_humana = st.number_input("Nota humana total", min_value=0.0, value=0.0, step=0.5)

    ejecutar = st.button("Calificar", type="primary", disabled=prompt_sel is None)

if ejecutar:
    rubrica = rubrica_df.dropna(subset=["criterio"]).to_dict("records")
    if not rubrica or not respuesta.strip():
        st.error("Falta la rúbrica o la respuesta.")
    else:
        try:
            with st.spinner("Calificando..."):
                st.session_state["resultado"] = calificar(rubrica, respuesta, prompt_sel)
                st.session_state["nota_humana"] = nota_humana
                st.session_state["version"] = prompt_sel.stem
        except Exception as e:
            st.error(f"Error al calificar: {e}")

with col_out:
    st.subheader("Resultado")
    res = st.session_state.get("resultado")
    if res:
        st.caption(f"Prompt usado: {st.session_state['version']}")
        for c in res["criterios"]:
            with st.expander(f"{c['nombre']}: {c['puntaje']} / {c['maximo']}", expanded=True):
                st.progress(min(c["puntaje"] / c["maximo"], 1.0) if c["maximo"] else 0)
                st.write(c["justificacion"])

        total_max = sum(c["maximo"] for c in res["criterios"])
        st.metric("Total IA", f"{res['total']} / {total_max}")

        humana = st.session_state.get("nota_humana", 0.0)
        if humana > 0:
            st.divider()
            st.subheader("IA vs. humano")
            m1, m2, m3 = st.columns(3)
            m1.metric("IA", res["total"])
            m2.metric("Humano", humana)
            m3.metric("Diferencia", round(res["total"] - humana, 2))
    else:
        st.info("Aquí aparecerá el resultado.")