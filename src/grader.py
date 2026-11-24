import io
import os, time, json, re, logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types, errors
import pandas as pd
import requests

load_dotenv()
log = logging.getLogger("calificador")

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")  # verifica el nombre vigente en AI Studio
TIMEOUT_S = float(os.getenv("LLM_TIMEOUT", "30"))            # si un proveedor no responde, pasamos al siguiente
COOLDOWN_S = float(os.getenv("LLM_COOLDOWN", "60"))          # tiempo que se "descansa" un proveedor caído

_GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = (
    genai.Client(api_key=_GEMINI_KEY, http_options=types.HttpOptions(timeout=int(TIMEOUT_S * 1000)))
    if _GEMINI_KEY else None
)

# Códigos HTTP que justifican reintentar (cuota o servidor saturado)
_TRANSITORIOS = (429, 500, 502, 503, 504)

# (proveedor, modelo) -> instante en que se marcó como caído (circuit breaker)
_caidos: dict[tuple[str, str], float] = {}


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


# ---------------------------------------------------------------------------
# Proveedores de LLM con respaldo (fallback)
#   Orden por defecto: gemini -> groq -> openrouter -> ollama (local)
#   Un proveedor solo entra en la cadena si está configurado en el .env.
# ---------------------------------------------------------------------------
class _FalloSimulado(Exception):
    """Se lanza cuando el proveedor está en SIMULAR_FALLO (para la demo)."""


def _cadena() -> list[tuple[str, str]]:
    """Lista ordenada de (proveedor, modelo) disponibles según las variables de entorno."""
    orden = [p.strip().lower() for p in os.getenv(
        "LLM_FALLBACK_ORDER", "gemini,groq,openrouter,ollama").split(",") if p.strip()]
    cadena: list[tuple[str, str]] = []
    for prov in orden:
        if prov == "gemini" and client is not None:
            cadena.append(("gemini", MODELO))
            for extra in os.getenv("GEMINI_FALLBACK_MODELS", "").split(","):
                if extra.strip():
                    cadena.append(("gemini", extra.strip()))
        elif prov == "groq" and os.getenv("GROQ_API_KEY"):
            cadena.append(("groq", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")))
        elif prov == "openrouter" and os.getenv("OPENROUTER_API_KEY"):
            cadena.append(("openrouter", os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")))
        elif prov == "ollama" and os.getenv("OLLAMA_MODEL"):
            cadena.append(("ollama", os.getenv("OLLAMA_MODEL")))
    if not cadena:
        raise RuntimeError(
            "No hay ningún proveedor de IA configurado. Define GEMINI_API_KEY, GROQ_API_KEY, "
            "OPENROUTER_API_KEY u OLLAMA_MODEL en el archivo .env."
        )
    return cadena


def _extraer_json(texto: str) -> str:
    """Los modelos open-source a veces envuelven el JSON en ```json ... ```; nos quedamos con el objeto."""
    m = re.search(r"\{.*\}", texto, re.S)
    return m.group(0) if m else texto.strip()


def _mensajes(sistema: str, contenido: str) -> list[dict]:
    esquema = json.dumps(Calificacion.model_json_schema(), ensure_ascii=False)
    return [
        {"role": "system", "content": f"{sistema}\n\nResponde ÚNICAMENTE con un objeto JSON válido "
                                      f"que cumpla este esquema:\n{esquema}"},
        {"role": "user", "content": contenido},
    ]


def _llamar_gemini(modelo, sistema, contenido, temp) -> "Calificacion":
    config = types.GenerateContentConfig(
        system_instruction=sistema,
        temperature=temp,
        response_mime_type="application/json",
        response_schema=Calificacion,
    )
    r = client.models.generate_content(model=modelo, contents=contenido, config=config)
    return r.parsed


def _llamar_openai_compat(url, api_key, modelo, sistema, contenido, temp, extra_headers=None) -> "Calificacion":
    """Groq y OpenRouter hablan el mismo protocolo (chat/completions de OpenAI)."""
    headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}
    body = {
        "model": modelo,
        "temperature": temp,
        "response_format": {"type": "json_object"},
        "messages": _mensajes(sistema, contenido),
    }
    r = requests.post(url, headers=headers, json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    texto = r.json()["choices"][0]["message"]["content"]
    return Calificacion.model_validate_json(_extraer_json(texto))


def _llamar_ollama(modelo, sistema, contenido, temp) -> "Calificacion":
    """Modelo local (Ollama). Corre en tu equipo: sin internet, sin cuota, sin API key."""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    body = {
        "model": modelo,
        "stream": False,
        "format": Calificacion.model_json_schema(),   # salida estructurada
        "options": {"temperature": temp},
        "messages": _mensajes(sistema, contenido),
    }
    r = requests.post(f"{host}/api/chat", json=body,
                      timeout=float(os.getenv("OLLAMA_TIMEOUT", "120")))  # el modelo local es más lento
    r.raise_for_status()
    return Calificacion.model_validate_json(_extraer_json(r.json()["message"]["content"]))


def _llamar(prov, modelo, sistema, contenido, temp) -> "Calificacion":
    if prov in {p.strip().lower() for p in os.getenv("SIMULAR_FALLO", "").split(",") if p.strip()}:
        raise _FalloSimulado(f"{prov} simulado como caído (SIMULAR_FALLO)")
    if prov == "gemini":
        return _llamar_gemini(modelo, sistema, contenido, temp)
    if prov == "groq":
        return _llamar_openai_compat("https://api.groq.com/openai/v1/chat/completions",
                                     os.environ["GROQ_API_KEY"], modelo, sistema, contenido, temp)
    if prov == "openrouter":
        return _llamar_openai_compat("https://openrouter.ai/api/v1/chat/completions",
                                     os.environ["OPENROUTER_API_KEY"], modelo, sistema, contenido, temp,
                                     {"X-Title": "Calificador Automatico PE"})
    if prov == "ollama":
        return _llamar_ollama(modelo, sistema, contenido, temp)
    raise ValueError(f"Proveedor desconocido: {prov}")


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

    cadena = _cadena()
    fallos: list[str] = []          # bitácora de por qué se descartó cada proveedor
    ultimo_error = None
    intentos = 0

    for pos, (prov, modelo) in enumerate(cadena):
        es_ultimo = pos == len(cadena) - 1
        # Si ya lo marcamos como caído hace poco, no perdemos tiempo (salvo que sea la última opción)
        if not es_ultimo and time.time() - _caidos.get((prov, modelo), 0) < COOLDOWN_S:
            fallos.append(f"{prov}:{modelo} (en pausa)")
            continue
        max_int = reintentos if es_ultimo else min(reintentos, 2)   # con respaldo, no insistas tanto

        for intento in range(max_int):
            intentos += 1
            transitorio = False
            try:
                t0 = time.time()
                cal = _llamar(prov, modelo, sistema, contenido, indice_libertad)
                salida = _validar(cal, rubrica)
                _caidos.pop((prov, modelo), None)
                salida["meta"] = {
                    "modelo": modelo if prov == "gemini" else f"{prov}:{modelo}",
                    "proveedor": prov,
                    "fallback": pos > 0,
                    "fallos_previos": fallos,
                    "prompt": version_prompt,
                    "indice_libertad": indice_libertad,
                    "temperatura": indice_libertad,
                    "segundos": round(time.time() - t0, 2),
                }
                if fallos:
                    log.warning("Se usó %s:%s tras fallar: %s", prov, modelo, "; ".join(fallos))
                return salida
            except _FalloSimulado as e:
                ultimo_error, fatal = e, True
            except errors.APIError as e:               # Gemini
                ultimo_error = e
                transitorio = e.code in _TRANSITORIOS
                fatal = not transitorio                # 400/401/403: reintentar no sirve
            except requests.ConnectionError as e:      # servicio apagado / sin internet
                ultimo_error, fatal = e, True
            except requests.Timeout as e:
                ultimo_error, transitorio, fatal = e, True, False
            except requests.HTTPError as e:            # Groq / OpenRouter / Ollama
                ultimo_error = e
                codigo = e.response.status_code if e.response is not None else 0
                transitorio = codigo in _TRANSITORIOS
                fatal = not transitorio
            except (ValueError, TypeError) as e:       # JSON inválido o fuera de rúbrica
                ultimo_error = e
                continue
            except Exception as e:                     # red del SDK de Gemini (httpx): timeout, conexión
                if type(e).__module__.split(".")[0] not in ("httpx", "httpcore", "httpx2", "httpcore2"):
                    raise                              # un bug real no se disfraza de "proveedor caído"
                ultimo_error = e
                transitorio = "Timeout" in type(e).__name__
                fatal = not transitorio

            if fatal:
                break
            if intento < max_int - 1:                  # backoff solo si vamos a reintentar el mismo
                time.sleep(2 ** intento)

        if ultimo_error is not None:
            fallos.append(f"{prov}:{modelo} ({type(ultimo_error).__name__})")
            if not isinstance(ultimo_error, (ValueError, TypeError)):
                _caidos[(prov, modelo)] = time.time()
            if len(cadena) == 1 and isinstance(ultimo_error, errors.APIError) and ultimo_error.code not in _TRANSITORIOS:
                raise ultimo_error                     # sin respaldo: 401/403 se muestran tal cual

    detalle = "" if len(cadena) == 1 else f" | Proveedores probados: {', '.join(fallos)}"
    raise RuntimeError(f"Falló tras {intentos} intentos: {ultimo_error}{detalle}")


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
                "comentario_general": f"",
                "error": str(e),
                "meta": {
                    "modelo": MODELO,
                    "prompt": version_prompt,
                    "indice_libertad": indice_libertad,
                    "temperatura": indice_libertad,
                    "segundos": 0,
                },
            })
    return resultados
