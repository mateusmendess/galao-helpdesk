import importlib.util
from pathlib import Path

import environ
import pytest
from django.test import Client

ARQUIVO_SETTINGS = Path(__file__).resolve().parents[2] / "config" / "settings.py"

# Opcoes que so podem mudar quando HTTPS_SEGURO estiver ligado.
OPCOES_HTTPS = [
    "SECURE_PROXY_SSL_HEADER",
    "SECURE_SSL_REDIRECT",
    "SECURE_REDIRECT_EXEMPT",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SECURE_HSTS_SECONDS",
]


def carregar_settings(monkeypatch, **variaveis):
    """Executa config/settings.py como um modulo novo, com o ambiente dado.

    Nao recarrega as configuracoes do Django em uso (os outros testes nao
    sao afetados) e ignora o .env, para "ausente" ser ausente de verdade.
    """
    monkeypatch.setattr(environ.Env, "read_env", staticmethod(lambda *a, **k: None))
    for nome in ("HTTPS_SEGURO", "CSRF_TRUSTED_ORIGINS"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("SECRET_KEY", "chave-falsa-somente-para-teste")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    for nome, valor in variaveis.items():
        monkeypatch.setenv(nome, valor)

    spec = importlib.util.spec_from_file_location("settings_em_teste", ARQUIVO_SETTINGS)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def producao_https(settings, monkeypatch):
    """Aplica nas configuracoes do teste as opcoes geradas com HTTPS_SEGURO=True."""
    modulo = carregar_settings(monkeypatch, HTTPS_SEGURO="True")
    for nome in OPCOES_HTTPS:
        setattr(settings, nome, getattr(modulo, nome))
    return settings


def test_sem_https_seguro_nada_muda(monkeypatch):
    modulo = carregar_settings(monkeypatch)

    assert modulo.HTTPS_SEGURO is False
    assert modulo.CSRF_TRUSTED_ORIGINS == []
    for nome in OPCOES_HTTPS:
        assert not hasattr(modulo, nome), nome


def test_com_https_seguro_liga_o_endurecimento(monkeypatch):
    modulo = carregar_settings(
        monkeypatch,
        HTTPS_SEGURO="True",
        CSRF_TRUSTED_ORIGINS="https://meu-app.up.railway.app",
    )

    assert modulo.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert modulo.SECURE_SSL_REDIRECT is True
    assert modulo.SECURE_REDIRECT_EXEMPT == [r"^saude/$"]
    assert modulo.SESSION_COOKIE_SECURE is True
    assert modulo.CSRF_COOKIE_SECURE is True
    assert modulo.SECURE_HSTS_SECONDS == 3600
    assert not getattr(modulo, "SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    assert not getattr(modulo, "SECURE_HSTS_PRELOAD", False)
    assert modulo.CSRF_TRUSTED_ORIGINS == ["https://meu-app.up.railway.app"]


@pytest.mark.django_db
def test_http_na_inicial_redireciona_para_https(producao_https):
    # Cliente novo: o middleware le as configuracoes ao iniciar.
    resposta = Client().get("/")

    assert resposta.status_code == 301
    assert resposta["Location"] == "https://testserver/"


@pytest.mark.django_db
def test_http_na_saude_nao_redireciona(producao_https):
    resposta = Client().get("/saude/")

    assert resposta.status_code == 200
    assert resposta.content == b"ok"


@pytest.mark.django_db
def test_https_pelo_proxy_entra_com_cookie_csrf_seguro(producao_https):
    resposta = Client().get("/entrar/", HTTP_X_FORWARDED_PROTO="https")

    assert resposta.status_code == 200
    assert resposta.cookies["csrftoken"]["secure"]
    assert resposta["Strict-Transport-Security"] == "max-age=3600"
