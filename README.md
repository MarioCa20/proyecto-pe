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
pip install pypdf                # opcional: necesario para subir respuestas en PDF
```

## Configuración

Copia el archivo de ejemplo y agrega tu clave:

```bash
cp .env.example .env
```

| Variable         | Obligatoria | Descripción                                              |
| ---------------- | ----------- | -------------------------------------------------------- |
| `GEMINI_API_KEY` | Sí          | Clave de la API de Gemini.                               |
| `GEMINI_MODEL`   | No          | Modelo a usar (por defecto `gemini-3.5-flash-lite`).     |

> Nunca subas tu archivo `.env` al repositorio (ya está en `.gitignore`).

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
├── requirements.txt
├── pytest.ini
└── .env.example
```

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
