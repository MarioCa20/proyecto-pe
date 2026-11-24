# Calificador Automático con IA

Aplicación web que califica respuestas de estudiantes a partir de una rúbrica, usando un modelo de IA local con llama.cpp. Devuelve un puntaje por criterio, su justificación y la nota total, de forma individual o masiva.

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
- [llama.cpp](https://github.com/ggerganov/llama.cpp) con `llama-server` instalado
- Un modelo GGUF (por ejemplo, Gemma 4)

## Instalación

```bash
git clone git@github.com:MarioCa20/proyecto-pe.git
cd proyecto-pe

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración del modelo local

1. Inicia llama-server con tu modelo:

```bash
# Ejemplo:
/usr/bin/llama-server \
    -m "/home/anorak/Models/Gemma 4/gemma-4-E4B-it-Q4_K_M.gguf" \
    -ngl 99 \
    --host 127.0.0.1 \
    --port 8080 \
    --jinja
```

2. Copia el archivo de configuración:

```bash
cp .env.example .env
```

| Variable        | Obligatoria | Descripción                                                       |
| --------------- | ----------- | ----------------------------------------------------------------- |
| `LLAMA_API_URL` | No          | URL del endpoint de chat. Por defecto `http://127.0.0.1:8080/v1/chat/completions` |
| `LLAMA_MODEL`   | No          | Nombre del modelo en la petición. Por defecto `gemma-4-E4B-it-Q4_K_M.gguf` |

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
│   └── grader.py       # Lógica de calificación y cliente llama.cpp
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
pytest                  # pruebas unitarias (no requieren modelo local)
pytest -m live          # incluye llamadas reales al servidor llama.cpp
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
