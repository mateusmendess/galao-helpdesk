import re

import pytest
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.urls import reverse

pytestmark = pytest.mark.django_db

LOGO = "M36 4L50 4C55.52 4 60 8.48 60 14"
GALAO = "M12 3h8v3l2 2v3"


def html_de(client, nome, usuario=None):
    if usuario is not None:
        client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


def marca(html):
    """O trecho com a marca: o comeco do <header>, ou da tela de entrada."""
    inicio = html.find("<header")
    if inicio < 0:
        inicio = html.index("<main")
    return html[inicio : html.index("Help Desk Equipe", inicio)]


def test_aba_aponta_para_o_favicon_que_existe(client):
    cabeca = html_de(client, "login").split("</head>")[0]

    href = static("img/favicon.svg")
    assert f'<link rel="icon" href="{href}" type="image/svg+xml">' in cabeca
    assert finders.find("img/favicon.svg")


@pytest.mark.parametrize(
    "nome, logado, cor",
    [
        ("home", True, "text-white"),
        ("escala", True, "text-white"),
        ("registrar_troca", True, "text-white"),
        ("login", False, "text-tinta"),
        ("home", False, "text-white"),
    ],
)
def test_marca_e_a_logo_nova(client, membro, nome, logado, cor):
    html = html_de(client, nome, membro if logado else None)
    trecho = marca(html)

    svg = re.search(r'<svg class="([^"]*)" viewBox="0 0 64 64"[^>]*>', trecho)
    assert svg and cor in svg.group(1).split()
    assert 'aria-hidden="true" focusable="false"' in svg.group(0)
    assert LOGO in trecho and GALAO not in trecho
    tons = re.findall(r'<path d="[^"]+" opacity="([^"]+)"/>', trecho)
    assert tons == [".3", ".6", "1"]


def test_galao_so_fica_como_modulo_na_pagina_publica(client, membro):
    publica = html_de(client, "home")
    entrada = html_de(client, "login")
    galao = html_de(client, "home", membro)

    # Na pagina publica o galao e so o marcador que anda na fila.
    assert publica.count(GALAO) == 1
    jarro = r'fila-anda[^>]*>\s*<svg class="h-8 w-7"[^>]*><path d="'
    assert re.search(jarro + GALAO, publica)
    assert GALAO not in entrada and GALAO not in galao
