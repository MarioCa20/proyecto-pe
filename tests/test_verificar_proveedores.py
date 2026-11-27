"""Pruebas del script de diagnóstico scripts/verificar_proveedores.py (todo con mocks, sin red)."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "verificar_proveedores.py"
os.environ.setdefault("GEMINI_API_KEY", "clave-falsa-para-tests")


@pytest.fixture
def v(monkeypatch):
    spec = importlib.util.spec_from_file_location("verificar_proveedores", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_MODEL", "LLAMA_MODEL", "LLAMA_API_URL",
                "LLM_FALLBACK_ORDER", "SIMULAR_FALLO", "GEMINI_FALLBACK_MODELS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-falsa-para-tests")
    return mod


def test_configuracion_no_expone_claves(v, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "SECRETO_NO_IMPRIMIR_123")
    conf = v.configuracion()
    assert conf["groq"]["configurado"] is True and conf["openrouter"]["configurado"] is False
    assert conf["llama"]["configurado"] is True            # entra con sus valores por defecto
    assert "SECRETO_NO_IMPRIMIR_123" not in repr(conf)


def test_main_ok_con_mocks_y_orden_de_uso(v, monkeypatch, capsys):
    monkeypatch.setenv("GROQ_API_KEY", "SECRETO_NO_IMPRIMIR_123")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(v, "comprobar_ollama", lambda: (True, "servicio activo, modelo descargado"))
    monkeypatch.setattr(v, "comprobar_llama", lambda: (False, "llama-server no responde en http://x: inícialo"))

    def fake_verificar(prov, modelo):
        return (prov != "gemini"), ("calificó 4/5" if prov != "gemini" else "ServerError: 503"), 0.1
    monkeypatch.setattr(v, "verificar", fake_verificar)

    codigo = v.main()
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "[groq] CONFIGURADO" in salida and "[openrouter] NO CONFIGURADO" in salida
    assert "Orden de uso: groq → ollama" in salida
    assert "falta OPENROUTER_API_KEY" in salida              # aviso accionable
    assert "llama-server no responde" in salida
    assert "SECRETO_NO_IMPRIMIR_123" not in salida           # nunca imprime claves


def test_main_devuelve_1_si_nada_funciona(v, monkeypatch, capsys):
    monkeypatch.setattr(v, "comprobar_llama", lambda: (False, "llama-server no responde"))
    monkeypatch.setattr(v, "verificar", lambda p, m: (False, "ConnectionError", 0.0))
    assert v.main() == 1
    assert "ningún proveedor disponible" in capsys.readouterr().out


def test_verificar_usa_grader_y_valida_la_rubrica(v, monkeypatch):
    monkeypatch.setattr(v.grader, "_llamar", lambda *a: v.grader.Calificacion(
        criterios=[v.grader.CriterioCalificado(criterio="Claridad", puntaje=4, justificacion="j")]))
    ok, msg, _ = v.verificar("groq", "m")
    assert ok and msg == "calificó 4.0/5"


def test_verificar_reporta_el_error_sin_romper(v, monkeypatch):
    def boom(*a):
        raise v.requests.ConnectionError("sin red")
    monkeypatch.setattr(v.grader, "_llamar", boom)
    ok, msg, seg = v.verificar("llama", "m")
    assert not ok and "ConnectionError" in msg


def test_comprobar_ollama_modelo_no_descargado(v, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(v.requests, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"models": [{"name": "otro:1b"}]}))
    ok, msg = v.comprobar_ollama()
    assert not ok and "ollama pull qwen2.5:7b" in msg


def test_comprobar_ollama_apagado(v, monkeypatch):
    def boom(*a, **k):
        raise v.requests.ConnectionError("rechazada")
    monkeypatch.setattr(v.requests, "get", boom)
    ok, msg = v.comprobar_ollama()
    assert not ok and "ollama serve" in msg


def test_comprobar_llama_responde(v, monkeypatch):
    monkeypatch.setattr(v.requests, "get", lambda *a, **k: SimpleNamespace(status_code=200))
    ok, msg = v.comprobar_llama()
    assert ok and "127.0.0.1:8080" in msg
