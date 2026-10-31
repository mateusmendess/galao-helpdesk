import re

import pytest
from django.urls import reverse

from conftest import SENHA_DE_TESTE

pytestmark = pytest.mark.django_db

# Senha errada derivada da do conftest (nada de senha escrita no teste).
SENHA_ERRADA = SENHA_DE_TESTE + "-errada"
ROTULO = "E-mail ou matrícula"
MENSAGEM_ERRO = "E-mail, matrícula ou senha incorretos."


def rotulo(html):
    return re.search(r'<label for="id_username"[^>]*>(.*?)</label>', html)[1]


def test_entrar_mostra_o_rotulo_email_ou_matricula(client):
    html = client.get(reverse("login")).content.decode()

    assert rotulo(html) == ROTULO


def test_login_do_painel_mostra_o_mesmo_rotulo(client):
    html = client.get(reverse("admin:login")).content.decode()

    # O admin do Django poe ":" depois do rotulo.
    assert rotulo(html) == ROTULO + ":"
    assert ">E-mail:</label>" not in html


def test_erro_de_login_e_o_mesmo_nas_duas_telas(client, admin_usuario):
    dados = {"username": "admin@exemplo.test", "password": SENHA_ERRADA}

    entrar = client.post(reverse("login"), dados).content.decode()
    painel = client.post(reverse("admin:login"), dados).content.decode()

    assert MENSAGEM_ERRO in entrar
    assert MENSAGEM_ERRO in painel
    assert "conta de equipe" not in painel
