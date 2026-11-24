import io
import os, time, json, re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import requests
import pandas as pd

load_dotenv()
LLAMA_API_URL = os.getenv("LLAMA_API_URL", "http://127.0.0.1:8080/v1/chat/completions")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "gemma-4-E4B-it-Q4_K_M.gguf")



def _obtener_esquema_calificacion() -> dict:
    return {
        "type": "object",
        "properties": {
            "criterios": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "criterio": {"type": "string"},
                        "puntaje": {"type": "number"},
                        "justificacion": {"type": "string"}
                    },
                    "required": [
                        "criterio",
                        "puntaje",
                        "justificacion"
                    ],
                    "additionalProperties": False
                }
            },
            "comentario_general": {
                "type": "string"
            }
        },
        "required": [
            "criterios",
            "comentario_general"
        ],
        "additionalProperties": False
    }

def _remover_acentos(texto: str) -> str:
    """Remover acentos y ñ para comparacion flexible de columnas."""
    import unicodedata
    texto = str(texto)  # asegurar que sea str
    nfkc = unicodedata.normalize("NFKC", texto)
    return "".join(c for c in nfkc if not unicodedata.combining(c))


def _construir_instruccion_permisividad(indice_libertad: float) -> str:
    """Construye la directriz de evaluación basada en el índice de libertad (permisividad)."""
    return (
        f"ÍNDICE DE LIBERTAD / PERMISIVIDAD: {indice_libertad:.1f} (escala 0.0 a 1.0)\n"
        f"Directriz de evaluación según este índice:\n"
        f"- 0.0 (Estricto): Sé riguroso y exigente. Aplica la rúbrica con estricto apego literal, penalizando imprecisiones, ambigüedades u omisiones.\n"
        f"- 1.0 (Permisivo): Sé muy flexible, comprensivo y benevolente. Valora principalmente la intención y el entendimiento conceptual del estudiante, otorgando el beneficio de la duda ante redacción informal o errores menores.\n"
        f"- Nivel actual ({indice_libertad:.1f}): Calibra tu nivel de rigurosidad y permisividad proporcionalmente a este valor."
    )


def cargar_rubrica_excel(archivo) -> list[dict]:
    """Lee un .xlsx y lo convierte a [{nombre, descripcion, max_puntos, escalas}, ...].

    Soporta:
      - Archivos con hoja 'Criterios_JSON', 'Rúbrica' o primera hoja disponible.
      - Encabezados en fila 1 o dentro de las primeras 10 filas.
      - Columnas de criterios simples: nombre/criterio, descripción, max_puntos/puntos.
      - Columnas de escalas opcionales: Excelente (100%), Bueno (75%), Regular (50%), Insuficiente (<=25%).
    """
    import pandas as pd

    xl = pd.ExcelFile(archivo)
    sheet_name = None
    if "Criterios_JSON" in xl.sheet_names:
        sheet_name = "Criterios_JSON"
    else:
        for s in xl.sheet_names:
            if "rubrica" in _remover_acentos(s).lower():
                sheet_name = s
                break
        if sheet_name is None:
            sheet_name = xl.sheet_names[0]

    df_raw = pd.read_excel(xl, sheet_name=sheet_name, header=None)

    # Buscar fila de encabezados en las primeras 10 filas
    indice_encabezado = 0
    encabezado_encontrado = False
    for idx in range(min(10, len(df_raw))):
        non_null_vals = df_raw.iloc[idx].dropna()
        if len(non_null_vals) < 2:
            continue
        fila_texto = " ".join(str(v).lower() for v in non_null_vals)
        fila_limpia = _remover_acentos(fila_texto)
        if any(k in fila_limpia for k in ("criterio", "nombre")):
            indice_encabezado = idx
            encabezado_encontrado = True
            break

    if encabezado_encontrado:
        encabezados = [str(v).strip() for v in df_raw.iloc[indice_encabezado].values]
        df = df_raw.iloc[indice_encabezado + 1:].reset_index(drop=True)
        df.columns = encabezados
    else:
        df = df_raw

    # Normalizar nombres de columnas
    df.columns = df.columns.astype(str).str.strip()

    col_map = {}
    escalas_cols = []

    for col in df.columns:
        col_norm = _remover_acentos(col.lower())
        if any(k in col_norm for k in ("nombre", "criterio")) and "nombre" not in col_map:
            col_map["nombre"] = col
        elif any(k in col_norm for k in ("descrip", "desc", "detalle")) and "descripcion" not in col_map:
            col_map["descripcion"] = col
        elif any(k in col_norm for k in ("punto", "max", "punt", "valor")) and "max_puntos" not in col_map:
            col_map["max_puntos"] = col
        elif "excelente" in col_norm:
            escalas_cols.append(("excelente", 1.0, col))
        elif any(k in col_norm for k in ("bueno", "notable")):
            escalas_cols.append(("bueno", 0.75, col))
        elif any(k in col_norm for k in ("regular", "basico")):
            escalas_cols.append(("regular", 0.5, col))
        elif "insuficiente" in col_norm:
            escalas_cols.append(("insuficiente", 0.25, col))

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
        if not nombre or nombre.lower() in ("nan", "none", ""):
            continue
        try:
            max_p = float(row[col_map["max_puntos"]]) if col_map.get("max_puntos") and pd.notna(row[col_map["max_puntos"]]) else 0.0
        except (ValueError, TypeError):
            max_p = 0.0

        item = {
            "nombre": nombre,
            "descripcion": str(row[col_map.get("descripcion", "")]).strip()
                           if col_map.get("descripcion") and pd.notna(row[col_map["descripcion"]]) else "",
            "max_puntos": max_p,
            "escalas": [],
        }

        if escalas_cols:
            for nivel, pct, c_name in escalas_cols:
                desc_esc = str(row[c_name]).strip() if pd.notna(row[c_name]) else ""
                item["escalas"].append({
                    "nivel": nivel,
                    "porcentaje": pct,
                    "descripcion": desc_esc,
                })

        rubrica.append(item)
    return rubrica


# --- Esquema de salida ---
class CriterioCalificado(BaseModel):
    criterio: str
    puntaje: float
    justificacion: str

class Calificacion(BaseModel):
    criterios: list[CriterioCalificado]
    comentario_general: str = Field(default="")


def cargar_prompt(version: str = "v1") -> str:
    return Path(f"prompts/{version}.md").read_text(encoding="utf-8")


# --- Extracción de JSON de la respuesta del modelo ---
def _extraer_json(texto: str) -> str | None:
    """Intenta extraer un bloque JSON válido del texto del modelo.

    El modelo local puede responder:
      - JSON puro
      - JSON rodeado de ```json ... ```
      - JSON rodeado de ``` ... ```
      - Texto libre + JSON al final
    """
    # 1. Buscar bloque ```json ... ``` o ``` ... ```
    bloque = re.search(r'```(?:json)?\s*\n(.*?)\n```', texto, re.DOTALL)
    if bloque:
        return bloque.group(1).strip()

    # 2. Buscar el primer { ... } válido
    inicio = texto.find('{')
    if inicio == -1:
        return None

    # Intentar múltiples cierres
    for fin in range(texto.rfind('}'), inicio - 1, -1):
        candidato = texto[inicio:fin + 1]
        try:
            json.loads(candidato)
            return candidato
        except json.JSONDecodeError:
            continue
    return None


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


def _llamar_llama(system_prompt: str, user_content: str,
                   temperatura: float = 0.0, reintentos: int = 3) -> tuple[str, float]:
    """Envía el prompt a llama.cpp y devuelve el texto crudo de la respuesta.

    Usa el endpoint /v1/chat/completions compatible con OpenAI.
    """
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    payload = {
        "model": LLAMA_MODEL,
        "messages": mensajes,
        "temperature": temperatura,
        "max_tokens": 4096,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "schema": _obtener_esquema_calificacion()
        }
    }
    ultimo_error = None
    for intento in range(reintentos):
        try:
            t0 = time.time()
            resp = requests.post(LLAMA_API_URL, json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()

            # Verificar que hay choices
            if not data.get("choices"):
                raise ValueError("La respuesta no contiene 'choices': " + str(data)[:500])

            contenido = data["choices"][0]["message"]["content"]
            if not contenido:
                raise ValueError("La respuesta está vacía")

            segundos = round(time.time() - t0, 2)
            return contenido, segundos

        except requests.exceptions.ConnectionError as e:
            ultimo_error = e
            if intento < reintentos - 1:
                time.sleep(2 ** intento)
                continue
            raise ConnectionError(f"No se pudo conectar a {LLAMA_API_URL}: {e}")
        except requests.exceptions.Timeout as e:
            ultimo_error = e
            if intento < reintentos - 1:
                time.sleep(2 ** intento)
                continue
            raise TimeoutError(f"Timeout al llamar a {LLAMA_API_URL}: {e}")
        except (requests.exceptions.RequestException, ValueError) as e:
            ultimo_error = e
            if intento < reintentos - 1:
                continue
            raise RuntimeError(f"Falló al llamar a llama.cpp tras {reintentos} intentos: {e}")

    raise RuntimeError(f"Falló tras {reintentos} intentos: {ultimo_error}")


def calificar(rubrica: list[dict], respuesta: str,
              version_prompt: str = "v1", indice_libertad: float = 0.0,
              temperatura: float | None = None,
              reintentos: int = 3) -> dict:
    """
    rubrica: [{"nombre": "Claridad", "descripcion": "...", "max_puntos": 5}, ...]
    respuesta: texto de la respuesta del estudiante
    version_prompt: versión del prompt (archivo en prompts/)
    indice_libertad: 0.0 (estricto) a 1.0 (permisivo)
    temperatura: alias compatible hacia atrás para indice_libertad
    Devuelve dict con criterios, total, y metadatos para la evaluación.
    """
    if temperatura is not None:
        indice_libertad = temperatura

    sistema = cargar_prompt(version_prompt)
    instruccion_permisividad = _construir_instruccion_permisividad(indice_libertad)
    contenido = (
        f"RÚBRICA:\n{json.dumps(rubrica, ensure_ascii=False, indent=2)}\n\n"
        f"{instruccion_permisividad}\n\n"
        f"RESPUESTA DEL ESTUDIANTE:\n<<<\n{respuesta}\n>>>"
    )

    ultimo_error = None
    for intento in range(reintentos):
        try:
            texto_raw, segundos = _llamar_llama(sistema, contenido, indice_libertad, reintentos=1)
            # Extraer JSON del texto
            json_str = _extraer_json(texto_raw)
            if json_str is None:
                raise ValueError(f"No se pudo extraer JSON de la respuesta del modelo. Texto: {texto_raw[:300]}")
            cal = Calificacion.model_validate(json.loads(json_str))
            salida = _validar(cal, rubrica)
            salida["meta"] = {
                "modelo": LLAMA_MODEL,
                "api_url": LLAMA_API_URL,
                "prompt": version_prompt,
                "indice_libertad": indice_libertad,
                "temperatura": indice_libertad,
                "segundos": segundos,
            }
            return salida
        except (ValueError, TypeError) as e:
            ultimo_error = e
        if intento == reintentos - 1:
            raise RuntimeError(f"Falló tras {reintentos} intentos: {ultimo_error}")


def cargar_respuestas_excel(archivo) -> list[dict]:
    """Lee un .xlsx con respuestas de estudiantes y devuelve una lista.

    Formato esperado:
      - Columna 'nombre_estudiante' o 'estudiante' o 'nombre' (str)
      - Columna 'respuesta' o 'respuesta_estudiante' (str)
      - Columna opcional 'nota_humana' (número)

    Los encabezados pueden estar en cualquier fila (se buscan en las primeras 10).
    Fallback por posición: col A=estudiante, B=respuesta, C=nota_humana.
    Se omiten filas donde la respuesta esté vacía.
    """
    import pandas as pd

    df = pd.read_excel(archivo, header=None, dtype=str)

    # Buscar la fila de encabezados por palabras clave (primeras 10 filas)
    encabezado_encontrado = False
    indice_encabezado = 0
    claves_resp = ["nombre", "estudiante", "respuesta", "nota", "calificacion"]
    for idx in range(min(10, len(df))):
        fila_texto = " ".join(str(v).lower() for v in df.iloc[idx].dropna())
        if any(k in fila_texto for k in claves_resp):
            indice_encabezado = idx
            encabezado_encontrado = True
            break

    if encabezado_encontrado:
        encabezados = [str(v).strip() for v in df.iloc[indice_encabezado].values]
        df = df.iloc[indice_encabezado + 1:].reset_index(drop=True)
        df.columns = encabezados
        df = df.dropna(subset=[df.columns[0]] if len(df.columns) > 0 else [])
    else:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]

    df.columns = pd.Index([str(c).strip().lower() for c in df.columns])

    col_map = {}
    for col in df.columns:
        col_sin_acento = _remover_acentos(col)
        if any(k in col_sin_acento for k in ("nombre_estud", "estudiante", "nombre")):
            col_map.setdefault("nombre", col)
        if any(k in col_sin_acento for k in ("respuesta", "resp")):
            col_map.setdefault("respuesta", col)
        if any(k in col_sin_acento for k in ("nota_humana", "nota", "calificacion_humana")):
            col_map.setdefault("nota_humana", col)

    if not col_map:
        cols = df.columns.tolist()
        if len(cols) >= 2:
            col_map["nombre"] = cols[0]
            col_map["respuesta"] = cols[1]
        if len(cols) >= 3:
            col_map["nota_humana"] = cols[2]

    respuestas = []
    for _, row in df.iterrows():
        nombre = str(row[col_map["nombre"]]).strip() if col_map.get("nombre") else ""
        respuesta = str(row[col_map["respuesta"]]).strip() if col_map.get("respuesta") else ""
        raw_nota = row[col_map["nota_humana"]] if col_map.get("nota_humana") else None
        nota_humana = None
        if raw_nota and str(raw_nota).strip():
            try:
                nota_humana = float(raw_nota)
            except (ValueError, TypeError):
                nota_humana = None
        if nombre and respuesta:
            respuestas.append({
                "nombre": nombre,
                "respuesta": respuesta,
                "nota_humana": nota_humana,
            })
    return respuestas


def calificar_multipartida(
    rubrica: list[dict],
    respuestas: list[dict],
    version_prompt: str = "v1",
    indice_libertad: float = 0.0,
    temperatura: float | None = None,
    reintentos: int = 3,
) -> list[dict]:
    """Califica una lista de respuestas de estudiantes.

    Devuelve una lista de dicts, cada uno con:
      nombre, criterios, total, total_max, comentario_general,
      nota_humana, meta, error (si hubo fallo).
    """
    if temperatura is not None:
        indice_libertad = temperatura

    resultados = []
    for idx, resp in enumerate(respuestas, 1):
        try:
            resultado = calificar(
                rubrica=rubrica,
                respuesta=resp["respuesta"],
                version_prompt=version_prompt,
                indice_libertad=indice_libertad,
                reintentos=reintentos,
            )
            resultados.append({
                "nombre": resp["nombre"],
                "nota_humana": resp.get("nota_humana"),
                **resultado,
            })
        except Exception as e:
            resultados.append({
                "nombre": resp["nombre"],
                "nota_humana": resp.get("nota_humana"),
                "total": None,
                "total_max": sum(c["max_puntos"] for c in rubrica),
                "criterios": [],
                "comentario_general": "",
                "error": str(e),
                "meta": {
                    "modelo": LLAMA_MODEL,
                    "api_url": LLAMA_API_URL,
                    "prompt": version_prompt,
                    "indice_libertad": indice_libertad,
                    "temperatura": indice_libertad,
                    "segundos": 0,
                },
            })
    return resultados
