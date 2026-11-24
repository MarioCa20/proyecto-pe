# Calificador Automático con IA

Aplicación web que califica respuestas de estudiantes a partir de una rúbrica, usando IA con una cadena de respaldo automática (**Gemini → Groq → OpenRouter → Ollama → llama.cpp**): si un modelo se cae, la calificación continúa con el siguiente. Devuelve un puntaje por criterio, su justificación y la nota total, de forma individual o masiva.

> Proyecto del curso de Prompt Engineering — Equipo 5.

## Características

- **Evaluación individual**: pega o sube (`.txt`, `.pdf`) la respuesta de un estudiante y obtén la calificación por criterio con retroalimentación.
- **Calificación masiva**: carga un Excel con múltiples respuestas y califícalas en lote.
- **Rúbricas flexibles**: edítalas en la interfaz o cárgalas desde `.json` o `.xlsx`.
- **Prompts versionados**: distintas versiones del prompt de evaluación (`prompts/v1.md` … `v4.md`) seleccionables desde la barra lateral.
- **Ajuste de permisividad**: controla qué tan estricta es la calificación.
- **Salida estructurada y validada** con Pydantic (los puntajes se limitan al máximo de cada criterio).
- **Historial** de evaluaciones y exportación de resultados.

## Requisitos previos

- Python 3.10 o superior
- Una clave de API de Gemini ([Google AI Studio](https://aistudio.google.com/apikey)), gratis
- Recomendado: una clave de Groq y, para la demo, un modelo local (Ollama y/o llama.cpp). Ver la guía paso a paso.

## Instalación

```bash
git clone git@github.com:MarioCa20/proyecto-pe.git
cd proyecto-pe

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Guía de instalación completa (paso a paso)

Pensada para dejar un computador listo para la demo. Sigue los pasos en orden.

**1. Código y dependencias** (dentro del entorno virtual):

```bash
git pull
pip install -r requirements.txt
```

**2. Archivo `.env` y claves en la nube.** Copia el ejemplo y completa tus claves (cada persona usa las suyas; `.env` nunca se sube al repo):

```bash
cp .env.example .env
```

- `GEMINI_API_KEY`: <https://aistudio.google.com/apikey> (principal, gratis).
- `GROQ_API_KEY`: <https://console.groq.com/keys> (respaldo gratis y muy rápido).
- `OPENROUTER_API_KEY`: <https://openrouter.ai/keys> (opcional).

**3. Respaldo local con Ollama + qwen2.5:7b** (unos 4.7 GB de disco):

- Mac: `brew install ollama`. Windows/Linux: instalador de <https://ollama.com>.
- Descarga el modelo: `ollama pull qwen2.5:7b`
- Deja Ollama abierto (en Mac: `brew services start ollama`) y agrega al `.env`: `OLLAMA_MODEL=qwen2.5:7b`
- Prueba: `ollama run qwen2.5:7b "hola"`

**4. Respaldo local con llama-server (Gemma 4)**, el modelo de Ángel. Inicia el servidor con tu modelo `.gguf` (ajusta la ruta de `-m` a donde lo tengas; **no subas el `.gguf` al repo**):

```bash
# Ejemplo:
/usr/bin/llama-server \
    -m "/home/anorak/Models/Gemma 4/gemma-4-E4B-it-Q4_K_M.gguf" \
    -ngl 99 \
    --host 127.0.0.1 \
    --port 8080 \
    --jinja
```

No necesita variables nuevas: por defecto el calificador lo busca en `http://127.0.0.1:8080/v1/chat/completions` con el modelo `gemma-4-E4B-it-Q4_K_M.gguf`. Solo si usas otra URL o nombre, define `LLAMA_API_URL` / `LLAMA_MODEL` en el `.env` (y `LLAMA_TIMEOUT`, 300 s por defecto, si tu equipo es lento).

**5. Verificar que todo funciona:**

```bash
python scripts/verificar_proveedores.py
```

Muestra qué proveedores están configurados, hace una calificación mínima en cada uno (OK / ERROR con el motivo y el tiempo), comprueba que Ollama y llama-server respondan, y termina con el orden de uso real y avisos accionables (por ejemplo «falta GROQ_API_KEY: créala en …»).

**6. Ensayar la demo** sin esperar una caída real:

```bash
SIMULAR_FALLO=gemini streamlit run app.py                    # cae a Groq
SIMULAR_FALLO=gemini,groq,openrouter streamlit run app.py    # cae al modelo local
```

Los modelos locales tardan más en la **primera** llamada porque cargan el modelo en memoria. Antes de presentar, haz una calificación de calentamiento con cada modelo local que vayas a usar.

**7. Memoria.** No hace falta tener los dos modelos locales cargados a la vez (Ollama y llama-server usan RAM/VRAM): basta con uno. Si el equipo es justo, detén el que no uses.

## Configuración

| Variable                 | Obligatoria  | Descripción                                                              |
| ------------------------ | ------------ | ------------------------------------------------------------------------ |
| `GEMINI_API_KEY`         | No (ver nota) | Clave de Gemini (principal).                                            |
| `GEMINI_MODEL`           | No           | Modelo principal (por defecto `gemini-3.5-flash-lite`).                  |
| `GEMINI_FALLBACK_MODELS` | No           | Otros modelos de Gemini, separados por coma.                             |
| `GROQ_API_KEY`           | No (ver nota) | Clave de Groq (respaldo gratis).                                        |
| `GROQ_MODEL`             | No           | Por defecto `openai/gpt-oss-120b`.                                       |
| `OPENROUTER_API_KEY`     | No (ver nota) | Clave de OpenRouter (respaldo opcional).                                |
| `OLLAMA_MODEL`           | No (ver nota) | Modelo local de Ollama, p. ej. `qwen2.5:7b`.                            |
| `OLLAMA_HOST`            | No           | Por defecto `http://localhost:11434`.                                    |
| `LLAMA_API_URL`          | No           | Endpoint de llama-server. Por defecto `http://127.0.0.1:8080/v1/chat/completions`. |
| `LLAMA_MODEL`            | No           | Nombre del modelo en la petición. Por defecto `gemma-4-E4B-it-Q4_K_M.gguf`. |
| `LLAMA_TIMEOUT`          | No           | Segundos de espera para llama.cpp (por defecto 300; es independiente de `LLM_TIMEOUT`). |
| `LLM_FALLBACK_ORDER`     | No           | Orden de proveedores. Por defecto `gemini,groq,openrouter,ollama,llama`. |
| `LLM_TIMEOUT`            | No           | Segundos antes de dar por caído a un proveedor en la nube (por defecto 30). |
| `SIMULAR_FALLO`          | No           | Solo para ensayar: finge que esos proveedores están caídos.              |

Nota: un proveedor entra en la cadena solo si está configurado; **llama.cpp entra siempre con sus valores por defecto** (si el servidor no está corriendo, simplemente falla y se descarta). Los nombres de modelo cambian con frecuencia: si un proveedor devuelve 404, revisa el nombre vigente en su consola y ajústalo en el `.env`.

> Nunca subas tu archivo `.env` al repositorio (ya está en `.gitignore`).

## Modelos de respaldo (fallback)

Si Gemini falla (cuota, caída, timeout o clave inválida), el calificador pasa automáticamente al siguiente proveedor configurado. Orden por defecto: **Gemini → Groq → OpenRouter → Ollama (qwen2.5:7b) → llama.cpp (Gemma 4)**. En cada resultado se indica qué modelo calificó (`meta["proveedor"]`, `meta["fallback"]`) y la app avisa cuando se usó un respaldo.

| Proveedor  | Variable             | Costo / notas                                                       |
| ---------- | -------------------- | ------------------------------------------------------------------- |
| Groq       | `GROQ_API_KEY`       | Plan gratis con límites; muy rápido.                                |
| OpenRouter | `OPENROUTER_API_KEY` | Modelos con sufijo `:free`.                                         |
| Ollama     | `OLLAMA_MODEL`       | Local, sin internet ni cuota (~25–35 s por respuesta).              |
| llama.cpp  | `LLAMA_*` (opcional) | Local, sin internet ni cuota; requiere `llama-server` corriendo.    |

Los modelos locales son un último recurso: más lentos y, en las pruebas, algo más generosos que Gemini.

### Modo solo local (sin internet ni claves)

Para presentar sin conexión, usa solo los modelos locales:

```bash
LLM_FALLBACK_ORDER=ollama,llama streamlit run app.py   # primero Ollama, luego llama.cpp
LLM_FALLBACK_ORDER=ollama streamlit run app.py         # solo Ollama
LLM_FALLBACK_ORDER=llama streamlit run app.py          # solo llama.cpp (Gemma 4)
```

También puedes dejarlo fijo en el `.env`. Los proveedores que no estén en la lista no se usan.

## Uso

```bash
streamlit run app.py
```

La aplicación se abrirá en <http://localhost:8501> con tres pestañas:

1. **Evaluar**: define la rúbrica, sube la respuesta y califica.
2. **Calificación masiva**: califica varias respuestas desde un Excel.
3. **Historial**: consulta evaluaciones anteriores.

### Formato de la rúbrica

Cada criterio requiere un nombre, una descripción y un puntaje máximo:

```json
[
  {
    "nombre": "Contenido",
    "descripcion": "Dominio y precisión conceptual del tema solicitado.",
    "max_puntos": 20
  }
]
```

## Estructura del proyecto

```
.
├── app.py              # Interfaz Streamlit
├── src/
│   └── grader.py       # Calificación y cadena de proveedores (Gemini, Groq, OpenRouter, Ollama, llama.cpp)
├── scripts/
│   └── verificar_proveedores.py   # Diagnóstico de proveedores
├── prompts/            # Versiones del prompt de evaluación (v1–v4)
├── tests/              # Pruebas con pytest
├── data/               # Datos de demo (ver sección «Datos de demo»)
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Datos de demo

La carpeta `data/` contiene material para probar la aplicación y ver el formato esperado de los archivos. Hay una carpeta por libro:

```
data/
├── respuestas_estudiantes_prueba.xlsx   # Ejemplo de carga masiva
├── 1984/
│   ├── 1984 - George Orwell.pdf         # Texto del libro
│   ├── cuestionario.docx                # Preguntas dirigidas a los estudiantes
│   ├── rubrica.xlsx                     # Rúbrica de evaluación
│   ├── respuestas/                      # Respuestas individuales en PDF
│   └── respuestas_estudiantes.xlsx      # Respuestas en lote (solo algunos libros)
├── la_metamorfosis/
├── el_principito/
└── ...                                  # 11 libros en total
```

Libros incluidos: 1984, Drácula, Dr. Jekyll y Mr. Hyde, El corazón delator, El fantasma de Canterville, El principito, Frankenstein, La metamorfosis, Lazarillo de Tormes, Narraciones extraordinarias y Rebelión en la granja.

**Formatos de los archivos**

| Archivo                          | Uso en la app                          | Estructura                                                                                                           |
| -------------------------------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `rubrica.xlsx`                   | Pestaña **Evaluar** (cargar rúbrica)   | Criterio, Descripción, Puntos Máx. y descripción de cada nivel (Excelente, Bueno, Regular, Insuficiente).            |
| `respuestas/*.pdf`               | Pestaña **Evaluar** (respuesta)        | Una respuesta de estudiante por PDF, nombrada `Respuesta_NN_Nombre_Apellido.pdf`.                                    |
| `respuestas_estudiantes*.xlsx`   | Pestaña **Calificación masiva**        | Columnas `estudiante`, `respuesta` y `nota_humana` (nota de referencia para comparar con la calificación de la IA).  |

> Los nombres de estudiantes en los datos de ejemplo son ficticios.

## Pruebas

```bash
pytest                  # pruebas unitarias
pytest -m live          # incluye llamadas reales a los proveedores (consume cuota o recursos locales)
python scripts/verificar_proveedores.py   # diagnóstico de proveedores
```

## Versionado de prompts

Cada archivo en `prompts/` es una iteración del prompt de evaluación. Para añadir una nueva versión, crea `prompts/vN.md`; aparecerá automáticamente en la interfaz.

## Contribuir

1. Crea una rama desde `main` (`git checkout -b feat/mi-cambio`).
2. Haz commits descriptivos (por ejemplo, `fix:`, `feat:`, `docs:`).
3. Asegúrate de que `pytest` pase.
4. Abre un Pull Request.

## Autores

Equipo 5 — Prompt Engineering.
