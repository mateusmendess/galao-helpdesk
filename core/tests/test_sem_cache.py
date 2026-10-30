import pytest
from django.templatetags.static import static
from django.test import Client, override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


def nao_guarda(resposta):
    return "no-store" in resposta.get("Cache-Control", "")


@pytest.mark.parametrize("nome", ["home", "escala", "historico", "escala_trocas"])
def test_telas_logadas_nao_ficam_no_cache(client, membro, nome):
    client.force_login(membro)

    resposta = client.get(reverse(nome))

    assert resposta.status_code == 200
    assert nao_guarda(resposta)


def test_entrada_nao_fica_no_cache(client):
    assert nao_guarda(client.get(reverse("login")))


def test_resposta_do_logout_nao_fica_no_cache(client, membro):
    client.force_login(membro)

    resposta = client.post(reverse("logout"))

    assert resposta.status_code == 302
    assert nao_guarda(resposta)


def test_pagina_publica_e_saude_continuam_como_estao(client):
    for nome in ("home", "saude"):
        resposta = client.get(reverse(nome))
        assert resposta.status_code == 200
        assert "Cache-Control" not in resposta, nome


def test_estatico_continua_sem_no_store(membro):
    # Nos testes nao ha collectstatic: o WhiteNoise procura direto em static/.
    # Cliente novo dentro do override, para o WhiteNoise ler a configuracao.
    with override_settings(WHITENOISE_USE_FINDERS=True, WHITENOISE_AUTOREFRESH=True):
        cliente = Client()
        cliente.force_login(membro)
        resposta = cliente.get(static("css/output.css"))

    assert resposta.status_code == 200
    assert not nao_guarda(resposta)
