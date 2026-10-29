import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_anonimo_e_mandado_para_o_login(client):
    resposta = client.get(reverse("home"))

    assert resposta.status_code == 302
    assert resposta.url == "/entrar/?next=/"


def test_logado_ve_a_pagina_inicial_com_o_nome(client, membro):
    client.force_login(membro)

    resposta = client.get(reverse("home"))

    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "core/home.html" in [t.name for t in resposta.templates]
    assert "Help Desk Equipe" in conteudo
    assert "Olá, Pessoa 1" in conteudo


def test_sem_nome_mostra_o_email(client, membro):
    membro.first_name = ""
    membro.save()
    client.force_login(membro)

    resposta = client.get(reverse("home"))

    assert "Olá, pessoa1@exemplo.test" in resposta.content.decode()


def test_link_do_painel_so_aparece_para_admin(client, membro, admin_usuario):
    link = 'href="{}"'.format(reverse("admin:index"))

    client.force_login(membro)
    assert link not in client.get(reverse("home")).content.decode()

    client.force_login(admin_usuario)
    assert link in client.get(reverse("home")).content.decode()
