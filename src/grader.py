import io
import os, time, json
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types, errors

load_dotenv()
MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")  # verifica el nombre vigente en AI Studio
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def cargar_rubrica_excel(archivo) -> list[dict]:
    """Lee un .xlsx y lo convierte a [{nombre, descripcion, max_puntos}, ...].

    Formato esperado del xlsx:
      Columna A:  nombre     (str)
      Columna B:  descripcion (str)
      Columna C:  max_puntos  (número)

    La primera fila se usa como encabezados. Se omite cualquier fila vacía en
    la columna 'nombre'.
    """
    import pandas as pd

    df = pd.read_excel(archivo)

    # Normalizar nombres de columnas (minúsculas, strip, asegurar str)
    df.columns = df.columns.astype(str).str.strip().str.lower()

    # Mapeo flexible de nombres de columna
    col_map = {}
    for col in df.columns:
        if any(k in col for k in ("nombre", "criterio")):
            col_map.setdefault("nombre", col)
        if any(k in col for k in ("descrip", "desc", "detalle")):
            col_map.setdefault("descripcion", col)
        if any(k in col for k in ("punto", "max", "punt", "valor")):
            col_map.setdefault("max_puntos", col)

    # Fallback: si no se encontraron encabezados, usar posición (col A=nombre, B=desc, C=max)
    if not col_map:
        cols = df.columns.tolist()
        if len(cols) >= 3:
            col_map["nombre"] = cols[0]
            col_map["descripcion"] = cols[1]
            col_map["max_puntos"] = cols[2]
        elif len(cols) == 2:
            col_map["nombre"] = cols[0]
            col_map["descripcion"] = ""
            col_map["max_puntos"] = cols[1]

    rubrica = []
    for _, row in df.iterrows():
        nombre = str(row[col_map["nombre"]]).strip() if col_map.get("nombre") else ""
        if not nombre:
            continue
        rubrica.append({
            "nombre": nombre,
            "descripcion": str(row[col_map.get("descripcion", "")]).strip()
                           if col_map.get("descripcion") else "",
            "max_puntos": float(row[col_map["max_puntos"]]) if col_map.get("max_puntos")
                          else 0,
        })
    return rubrica


# --- Esquema de salida (Gemini lo fuerza a devolver JSON válido) ---
class CriterioCalificado(BaseModel):
    criterio: str
    puntaje: float
    justificacion: str

class Calificacion(BaseModel):
    criterios: list[CriterioCalificado]
    comentario_general: str = Field(default="")


def cargar_prompt(version: str = "v1") -> str:
    return Path(f"prompts/{version}.md").read_text(encoding="utf-8")


def _validar(cal: Calificacion, rubrica: list[dict]) -> dict:
    """Valida contra la rúbrica y recalcula el total en código (no confiar en el LLM para sumar)."""
    esperados = {c["nombre"]: c["max_puntos"] for c in rubrica}
    resultado, total = [], 0.0
    for c in cal.criterios:
        if c.criterio not in esperados:
            raise ValueError(f"Criterio inesperado: {c.criterio}")
        puntaje = max(0.0, min(c.puntaje, esperados[c.criterio]))  # acota al rango
        total += puntaje
        resultado.append({**c.model_dump(), "puntaje": puntaje,
                          "max_puntos": esperados[c.criterio]})
    faltan = set(esperados) - {c.criterio for c in cal.criterios}
    if faltan:
        raise ValueError(f"Faltan criterios: {faltan}")
    return {"criterios": resultado, "total": total,
            "total_max": sum(esperados.values()),
            "comentario_general": cal.comentario_general}


def calificar(rubrica: list[dict], respuesta: str,
              version_prompt: str = "v1", temperatura: float = 0.0,
              reintentos: int = 3) -> dict:
    """
    rubrica: [{"nombre": "Claridad", "descripcion": "...", "max_puntos": 5}, ...]
    Devuelve dict con criterios, total, y metadatos para la evaluación.
    """
    sistema = cargar_prompt(version_prompt)
    contenido = (f"RÚBRICA:\n{json.dumps(rubrica, ensure_ascii=False, indent=2)}\n\n"
                 f"RESPUESTA DEL ESTUDIANTE:\n<<<\n{respuesta}\n>>>")

    config = types.GenerateContentConfig(
        system_instruction=sistema,
        temperature=temperatura,
        response_mime_type="application/json",
        response_schema=Calificacion,
    )

    ultimo_error = None
    for intento in range(reintentos):
        try:
            t0 = time.time()
            r = client.models.generate_content(model=MODELO, contents=contenido, config=config)
            salida = _validar(r.parsed, rubrica)
            salida["meta"] = {"modelo": MODELO, "prompt": version_prompt,
                              "temperatura": temperatura,
                              "segundos": round(time.time() - t0, 2)}
            return salida
        except errors.APIError as e:
            ultimo_error = e
            if e.code in (429, 500, 503):          # cuota o servidor saturado
                time.sleep(2 ** intento)           # backoff: 1s, 2s, 4s
                continue
            raise                                  # 400/401/403: no tiene sentido reintentar
        except (ValueError, TypeError) as e:       # JSON inválido o fuera de rúbrica
            ultimo_error = e
            continue
    raise RuntimeError(f"Falló tras {reintentos} intentos: {ultimo_error}")
