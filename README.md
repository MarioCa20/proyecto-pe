# Calificador Automático con IA

Aplicación web que califica respuestas de estudiantes a partir de una rúbrica, usando la API de Google Gemini. Devuelve un puntaje por criterio, su justificación y la nota total, de forma individual o masiva.

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
- Una clave de API de Gemini ([Google AI Studio](https://aistudio.google.com/apikey))

## Instalación

```bash
git clone git@github.com:MarioCa20/proyecto-pe.git
cd proyecto-pe

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración

Copia el archivo de ejemplo y agrega tu clave:

```bash
cp .env.example .env
```

| Variable                 | Obligatoria | Descripción                                                              |
| ------------------------ | ----------- | ------------------------------------------------------------------------ |
| `GEMINI_API_KEY`         | Una de las 4 | Clave de Gemini (principal).                                            |
| `GEMINI_MODEL`           | No          | Modelo principal (por defecto `gemini-3.5-flash-lite`). |
| `GEMINI_FALLBACK_MODELS` | No          | Otros modelos de Gemini, separados por coma.                            |
| `GROQ_API_KEY`           | Una de las 4 | Clave de Groq (respaldo gratis).                                        |
| `GROQ_MODEL`             | No          | Por defecto `openai/gpt-oss-120b`.                                      |
| `OPENROUTER_API_KEY`     | Una de las 4 | Clave de OpenRouter (respaldo opcional).                                |
| `OLLAMA_MODEL`           | Una de las 4 | Modelo local de Ollama, p. ej. `qwen2.5:7b`.                            |

Basta con configurar **al menos uno** de los cuatro proveedores; la guía completa de claves y modelos está en `.env.example`. Los nombres de modelo cambian con frecuencia: si un proveedor devuelve 404, revisa el nombre vigente en su consola y ajústalo en el `.env`.

> Nunca subas tu archivo `.env` al repositorio (ya está en `.gitignore`).

## Modelos de respaldo (fallback)

Si Gemini falla (cuota, caída, timeout o clave inválida), el calificador pasa automáticamente al siguiente proveedor configurado. Orden por defecto: **Gemini → Groq → OpenRouter → Ollama (local)**. Solo entran los que tengan clave (o `OLLAMA_MODEL`) en el `.env`; en cada resultado se indica qué modelo calificó.

| Proveedor  | Variable           | Costo / notas                                                         |
| ---------- | ------------------ | --------------------------------------------------------------------- |
| Groq       | `GROQ_API_KEY`     | Plan gratis con límites; muy rápido.                                  |
| OpenRouter | `OPENROUTER_API_KEY` | Modelos con sufijo `:free`.                                         |
| Ollama     | `OLLAMA_MODEL`     | Local, sin internet ni cuota (ver pasos abajo). |

**Configuración paso a paso para el equipo**

1. `cp .env.example .env`
2. Crea tu clave de Gemini en <https://aistudio.google.com/apikey> y pégala en `GEMINI_API_KEY`.
3. Crea tu clave gratis de Groq en <https://console.groq.com/keys> y pégala en `GROQ_API_KEY`.
4. (Recomendado para la demo) Instala Ollama para tener un respaldo local sin internet:
   `brew install ollama` (Mac; en Windows/Linux usa el instalador de <https://ollama.com>), luego `ollama pull qwen2.5:7b`, deja Ollama abierto y descomenta `OLLAMA_MODEL=qwen2.5:7b` en tu `.env`.
5. Ejecuta `pytest` y después `streamlit run app.py`.

Para ensayar la demo sin esperar una caída real: `SIMULAR_FALLO=gemini streamlit run app.py`.

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
│   └── grader.py       # Lógica de calificación y cliente Gemini
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
pytest -m live          # incluye llamadas reales a la API (consume cuota)
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
