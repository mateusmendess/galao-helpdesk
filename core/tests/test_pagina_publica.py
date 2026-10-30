import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def publica(client):
    resposta = client.get(reverse("home"))
    assert resposta.status_code == 200
    return resposta.content.decode()


def test_anonimo_ve_o_titulo_e_os_botoes_entrar(client):
    html = publica(client)

    assert re.findall(r"<h1[^>]*>(.*?)</h1>", html) == ["Cada um na sua vez."]
    entrar = re.findall(r'<a href="([^"]+)"[^>]*>Entrar</a>', html)
    assert entrar == [reverse("login")] * 3
    assert "<title>Help Desk Equipe</title>" in html
    assert '<meta name="description" content="O sistema da equipe' in html


def test_logado_continua_vendo_o_galao(client, membro):
    client.force_login(membro)

    resposta = client.get(reverse("home"))

    nomes = [t.name for t in resposta.templates]
    assert resposta.status_code == 200
    assert "core/home.html" in nomes and "publica/inicio.html" not in nomes


def test_sem_dado_do_banco_e_sem_consulta(client, membro, django_assert_num_queries):
    with django_assert_num_queries(0):
        html = publica(client)

    assert "Rodada" not in html
    assert membro.first_name not in html and membro.email not in html


@pytest.mark.parametrize(
    "nome",
    [
        "historico",
        "registrar_troca",
        "escala",
        "escala_trocar",
        "escala_regras",
        "escala_proximos",
        "escala_trocas",
    ],
)
def test_telas_logadas_continuam_pedindo_login(client, nome):
    resposta = client.get(reverse(nome))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))


def test_pular_para_o_conteudo_e_um_so_h1(client):
    html = publica(client)

    assert html.count("<h1") == 1
    assert '<a href="#modulos"' in html and ">Pular para o conteúdo</a>" in html
    assert 'id="modulos"' in html
