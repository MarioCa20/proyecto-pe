#!/usr/bin/env python
"""Diagnóstico de los proveedores de IA del calificador.

Uso (desde la raíz del proyecto, con el venv activo):
    python scripts/verificar_proveedores.py

Para cada proveedor dice si está CONFIGURADO, hace una calificación mínima de verificación
(rúbrica de 1 criterio) y muestra OK / ERROR con el motivo y el tiempo. Al final imprime el
orden de uso real y avisos accionables. Nunca imprime claves.
Código de salida: 0 si al menos un proveedor funciona, 1 si ninguno.
"""
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src import grader  # noqa: E402  (carga el .env)

ORDEN_DEFECTO = "gemini,groq,openrouter,ollama,llama"
RUBRICA_MINIMA = [{"nombre": "Claridad", "descripcion": "La respuesta es clara.", "max_puntos": 5}]
SISTEMA = "Eres un calificador. Califica la respuesta del estudiante con la rúbrica dada."
CONTENIDO = ('RÚBRICA:\n[{"nombre": "Claridad", "descripcion": "La respuesta es clara.", "max_puntos": 5}]\n\n'
             "RESPUESTA DEL ESTUDIANTE:\n<<<\nUn índice acelera las búsquedas en una base de datos.\n>>>")


def _corto(e: Exception, n: int = 160) -> str:
    return f"{type(e).__name__}: {str(e)[:n]}".replace("\n", " ")


def configuracion() -> dict[str, dict]:
    """Por proveedor: {'configurado': bool, 'detalle': str, 'modelos': [..], 'ayuda': str}."""
    gemini_ok = os.getenv("GEMINI_API_KEY") and grader.client is not None
    modelos_g = [grader.MODELO] + [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
    ayuda_g = "falta GEMINI_API_KEY: créala en https://aistudio.google.com/apikey"
    if os.getenv("GEMINI_API_KEY") and grader.client is None:
        ayuda_g = "google-genai no está instalado: pip install -r requirements.txt"
    return {
        "gemini": {"configurado": bool(gemini_ok), "modelos": modelos_g if gemini_ok else [],
                   "detalle": "GEMINI_API_KEY", "ayuda": ayuda_g},
        "groq": {"configurado": bool(os.getenv("GROQ_API_KEY")),
                 "modelos": [os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")],
                 "detalle": "GROQ_API_KEY",
                 "ayuda": "falta GROQ_API_KEY: créala en https://console.groq.com/keys"},
        "openrouter": {"configurado": bool(os.getenv("OPENROUTER_API_KEY")),
                       "modelos": [os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")],
                       "detalle": "OPENROUTER_API_KEY (opcional)",
                       "ayuda": "falta OPENROUTER_API_KEY (opcional): https://openrouter.ai/keys"},
        "ollama": {"configurado": bool(os.getenv("OLLAMA_MODEL")),
                   "modelos": [os.getenv("OLLAMA_MODEL")] if os.getenv("OLLAMA_MODEL") else [],
                   "detalle": "OLLAMA_MODEL",
                   "ayuda": "falta OLLAMA_MODEL: agrega OLLAMA_MODEL=qwen2.5:7b al .env (ver README)"},
        "llama": {"configurado": True, "modelos": [os.getenv("LLAMA_MODEL", grader.LLAMA_MODEL)],
                  "detalle": "valores por defecto" if not os.getenv("LLAMA_MODEL") and not os.getenv("LLAMA_API_URL")
                  else "LLAMA_API_URL / LLAMA_MODEL",
                  "ayuda": ""},
    }


def comprobar_ollama() -> tuple[bool, str]:
    """¿Responde el servicio y está descargado OLLAMA_MODEL?"""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    modelo = os.getenv("OLLAMA_MODEL", "")
    try:
        r = requests.get(f"{host}/api/tags", timeout=5)
        r.raise_for_status()
    except requests.RequestException:
        return False, f"Ollama no está corriendo en {host}: ejecuta `brew services start ollama` (Mac) o `ollama serve`"
    nombres = {m.get("name", "") for m in r.json().get("models", [])}
    if modelo and modelo not in nombres and f"{modelo}:latest" not in nombres:
        return False, f"el modelo {modelo} no está descargado: ejecuta `ollama pull {modelo}`"
    return True, f"servicio activo en {host}, modelo {modelo} descargado"


def comprobar_llama() -> tuple[bool, str]:
    """¿Responde llama-server en LLAMA_API_URL?"""
    url = os.getenv("LLAMA_API_URL", grader.LLAMA_API_URL)
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    try:
        r = requests.get(f"{base}/health", timeout=5)
        return (r.status_code < 500), f"servidor responde en {base} (HTTP {r.status_code})"
    except requests.RequestException:
        return False, (f"llama-server no responde en {url}: inícialo con el comando de la sección "
                       "'llama-server' del README (necesita el archivo .gguf)")


def verificar(prov: str, modelo: str) -> tuple[bool, str, float]:
    """Una calificación mínima contra el proveedor. Devuelve (ok, mensaje, segundos)."""
    t0 = time.time()
    try:
        cal = grader._llamar(prov, modelo, SISTEMA, CONTENIDO, 0.0)
        salida = grader._validar(cal, RUBRICA_MINIMA)
        return True, f"calificó {salida['total']}/{salida['total_max']}", time.time() - t0
    except grader._FalloSimulado:
        return False, "simulado como caído (SIMULAR_FALLO)", time.time() - t0
    except Exception as e:                                   # noqa: BLE001 - es un diagnóstico, mostramos todo
        return False, _corto(e), time.time() - t0


def main() -> int:
    print("Verificación de proveedores de IA\n" + "=" * 34)
    conf = configuracion()
    orden = [p.strip().lower() for p in os.getenv("LLM_FALLBACK_ORDER", ORDEN_DEFECTO).split(",") if p.strip()]
    avisos: list[str] = []
    funcionan: list[str] = []

    for prov in orden:
        c = conf.get(prov)
        if c is None:
            print(f"\n[{prov}] proveedor desconocido en LLM_FALLBACK_ORDER")
            continue
        estado = "CONFIGURADO" if c["configurado"] else "NO CONFIGURADO"
        print(f"\n[{prov}] {estado}" + (f" ({c['detalle']})" if c["configurado"] else ""))
        if not c["configurado"]:
            avisos.append(c["ayuda"])
            continue

        if prov in ("ollama", "llama"):
            ok_srv, msg = (comprobar_ollama() if prov == "ollama" else comprobar_llama())
            print(f"    servicio: {'OK' if ok_srv else 'ERROR'} - {msg}")
            if not ok_srv:
                avisos.append(msg)
                continue

        alguno = False
        for modelo in c["modelos"]:
            print(f"    probando {modelo} ...", flush=True)
            ok, msg, seg = verificar(prov, modelo)
            print(f"    {'OK   ' if ok else 'ERROR'} {modelo}: {msg} ({seg:.1f}s)")
            alguno = alguno or ok
            if not ok and "simulado" not in msg:
                avisos.append(f"{prov}:{modelo} falló: {msg}")
        if alguno:
            funcionan.append(prov)

    print("\n" + "=" * 34)
    print("Orden de uso: " + (" → ".join(funcionan) if funcionan else "(ningún proveedor disponible)"))
    if avisos:
        print("\nAvisos:")
        for a in dict.fromkeys(avisos):
            print(f"  - {a}")
    if not funcionan:
        print("\nNinguno funciona: revisa la guía de instalación del README.")
    return 0 if funcionan else 1


if __name__ == "__main__":
    sys.exit(main())
