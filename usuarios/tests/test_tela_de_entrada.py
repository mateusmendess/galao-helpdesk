import re

import pytest
from django.urls import reverse

from conftest import SENHA_DE_TESTE

pytestmark = pytest.mark.django_db

# Senha errada derivada da do conftest (nada de senha escrita no teste).
SENHA_ERRADA = SENHA_DE_TESTE + "-errada"


def entrada(client):
    resposta = client.get(reverse("login"))
    assert resposta.status_code == 200
    return resposta.content.decode()


def com_autofocus(html):
    return re.findall(r'<input type="(\w+)"[^>]*\bautofocus\b', html)


def test_subtitulo_novo_e_recado_da_senha(client):
    html = entrada(client)

    assert "Acesso só para quem foi cadastrado." in html
    assert "Entre com seu e-mail" not in html
    assert "Esqueceu a senha? Fale com um admin da equipe." in html


def test_link_de_volta_para_a_pagina_inicial(client):
    html = entrada(client)

    link = re.search(
        r'<a href="([^"]+)" class="([^"]*)">&lsaquo; Página inicial</a>', html
    )
    assert link and link.group(1) == reverse("home") == "/"
    # Area de toque de 44 px de altura.
    assert "min-h-11" in link.group(2).split()


def test_primeira_visita_foca_o_email(client):
    assert com_autofocus(entrada(client)) == ["text"]


def test_depois_do_erro_com_email_o_foco_vai_para_a_senha(client, membro):
    resposta = client.post(
        reverse("login"),
        {"username": "pessoa1@exemplo.test", "password": SENHA_ERRADA},
    )

    html = resposta.content.decode()
    assert "Matrícula ou senha incorretas." in html
    assert com_autofocus(html) == ["password"]
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html


def test_um_so_h1_e_sem_faixa_nem_menu(client):
    html = entrada(client)

    assert re.findall(r"<h1\b[^>]*>(.*?)</h1>", html) == ["Help Desk Equipe"]
    assert "<header" not in html and "bg-tinta text-white" not in html
    assert "Menu da conta" not in html and "<nav" not in html


def test_cartao_dentro_do_main_e_um_so_h1(client):
    html = entrada(client)
    main = html[html.index("<main") : html.index("</main>")]

    assert html.count("<h1") == 1 and "<h1" in main
    assert re.search(r'<section class="rounded-\[14px\][^"]*bg-white', main)
    assert "<form" in main.split("<section", 1)[1]
