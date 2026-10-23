import pytest
from django.urls import reverse

from conftest import SENHA_DE_TESTE

pytestmark = pytest.mark.django_db


def entrar(client, email, senha):
    return client.post(reverse("login"), {"username": email, "password": senha})


def esta_logado(client):
    return "_auth_user_id" in client.session


def test_email_e_senha_corretos_entram_e_vao_para_a_inicial(client, membro):
    resposta = entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE)

    assert resposta.status_code == 302
    assert resposta.url == reverse("home")
    assert esta_logado(client)


def test_email_com_maiusculas_diferentes_tambem_entra(client, membro):
    resposta = entrar(client, "Pessoa1@EXEMPLO.test", SENHA_DE_TESTE)

    assert resposta.status_code == 302
    assert esta_logado(client)


def test_senha_errada_nao_entra_e_mostra_o_erro(client, membro):
    resposta = entrar(client, "pessoa1@exemplo.test", "senha-errada")

    assert resposta.status_code == 200
    assert "E-mail ou senha incorretos." in resposta.content.decode()
    assert not esta_logado(client)


def test_usuario_inativo_nao_entra(client, membro):
    membro.is_active = False
    membro.save()

    resposta = entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE)

    assert resposta.status_code == 200
    assert not esta_logado(client)


def test_logout_por_post_sai_e_volta_para_o_login(client, membro):
    client.force_login(membro)

    resposta = client.post(reverse("logout"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("login")
    assert not esta_logado(client)


def test_get_em_sair_nao_desloga(client, membro):
    client.force_login(membro)

    resposta = client.get(reverse("logout"))

    assert resposta.status_code == 405
    assert esta_logado(client)
