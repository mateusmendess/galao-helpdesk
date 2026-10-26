import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

FORM_SAIR = re.compile(
    r'<form method="post" action="/sair/"[^>]*>\s*'
    r'<input type="hidden" name="csrfmiddlewaretoken" value="[^"]+">\s*'
    r"<button[^>]*>\s*Sair\s*</button>\s*</form>"
)


def tela_de_senha(client, usuario):
    client.force_login(usuario)
    resposta = client.get(reverse("password_change"))
    assert resposta.status_code == 200
    return resposta.content.decode()


def test_troca_obrigatoria_tem_o_botao_sair_e_nao_tem_voltar(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()

    conteudo = tela_de_senha(client, membro)

    assert FORM_SAIR.search(conteudo)
    assert "Voltar" not in conteudo


def test_troca_normal_tem_voltar_e_nao_tem_sair(client, membro):
    conteudo = tela_de_senha(client, membro)

    assert not FORM_SAIR.search(conteudo)
    assert 'action="/sair/"' not in conteudo
    assert "Voltar" in conteudo


def test_sair_na_troca_obrigatoria_encerra_a_sessao(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()
    client.force_login(membro)

    resposta = client.post(reverse("logout"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("login")
    # Sem sessao: a tela inicial e a de senha voltam a pedir o login.
    for nome in ("home", "password_change"):
        depois = client.get(reverse(nome))
        assert depois.status_code == 302
        assert depois.url.startswith(reverse("login"))
