from datetime import timedelta

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from conftest import SENHA_DE_TESTE
from usuarios.limite import esta_bloqueado, registrar_falha
from usuarios.models import FalhaLogin

pytestmark = pytest.mark.django_db

MENSAGEM_BLOQUEIO = "Muitas tentativas de entrada. Tente de novo em alguns minutos."
MENSAGEM_ERRO = "E-mail, matrícula ou senha incorretos."


def entrar(client, email, senha):
    return client.post(reverse("login"), {"username": email, "password": senha})


def esta_logado(client):
    return "_auth_user_id" in client.session


def errar(client, email, vezes):
    for _ in range(vezes):
        entrar(client, email, "senha-errada")


def falhas_antigas(email, quantidade):
    antes_da_janela = timezone.now() - timedelta(
        minutes=settings.LOGIN_JANELA_MINUTOS + 1
    )
    for _ in range(quantidade):
        FalhaLogin.objects.create(email=email, criada_em=antes_da_janela)


def test_cinco_erros_bloqueiam_ate_a_senha_certa(client, membro):
    errar(client, "pessoa1@exemplo.test", 5)

    resposta = entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE)

    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert not esta_logado(client)
    assert MENSAGEM_BLOQUEIO in conteudo
    assert MENSAGEM_ERRO not in conteudo


def test_quatro_erros_nao_bloqueiam_e_o_sucesso_zera_o_contador(client, membro):
    errar(client, "pessoa1@exemplo.test", 4)

    assert entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE).status_code == 302
    assert FalhaLogin.objects.count() == 0

    client.post(reverse("logout"))
    errar(client, "pessoa1@exemplo.test", 4)
    assert entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE).status_code == 302
    assert esta_logado(client)


def test_falhas_fora_da_janela_nao_contam(client, membro):
    falhas_antigas("pessoa1@exemplo.test", 5)

    assert entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE).status_code == 302


def test_bloqueio_acaba_quando_as_falhas_saem_da_janela(client, membro):
    errar(client, "pessoa1@exemplo.test", 5)
    assert (
        MENSAGEM_BLOQUEIO
        in entrar(client, "pessoa1@exemplo.test", "x").content.decode()
    )

    antes_da_janela = timezone.now() - timedelta(
        minutes=settings.LOGIN_JANELA_MINUTOS + 1
    )
    FalhaLogin.objects.update(criada_em=antes_da_janela)

    assert entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE).status_code == 302


def test_maiusculas_e_espacos_contam_juntos(client, membro):
    errar(client, "Pessoa1@Exemplo.test", 2)
    errar(client, "  pessoa1@EXEMPLO.TEST ", 2)
    errar(client, "pessoa1@exemplo.test", 1)

    resposta = entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE)

    assert MENSAGEM_BLOQUEIO in resposta.content.decode()
    assert set(FalhaLogin.objects.values_list("email", flat=True)) == {
        "pessoa1@exemplo.test"
    }


def test_email_inexistente_tambem_e_bloqueado_com_a_mesma_mensagem(client):
    errar(client, "ninguem@exemplo.test", 5)

    resposta = entrar(client, "ninguem@exemplo.test", "senha-errada")

    assert MENSAGEM_BLOQUEIO in resposta.content.decode()


def test_tentativas_durante_o_bloqueio_nao_sao_registradas(client, membro):
    errar(client, "pessoa1@exemplo.test", 5)
    assert FalhaLogin.objects.count() == 5

    errar(client, "pessoa1@exemplo.test", 3)
    entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE)

    assert FalhaLogin.objects.count() == 5


def test_outro_email_nao_e_afetado(client, membro, django_user_model):
    django_user_model.objects.create_user(
        email="pessoa2@exemplo.test", password=SENHA_DE_TESTE
    )
    errar(client, "pessoa1@exemplo.test", 5)

    assert entrar(client, "pessoa2@exemplo.test", SENHA_DE_TESTE).status_code == 302


def test_login_do_painel_tambem_e_bloqueado(client, admin_usuario):
    errar(client, "admin@exemplo.test", 5)

    resposta = client.post(
        reverse("admin:login"),
        {"username": "admin@exemplo.test", "password": SENHA_DE_TESTE},
    )

    assert resposta.status_code == 200
    assert not esta_logado(client)


def test_tentativas_no_painel_durante_o_bloqueio_nao_sao_registradas(
    client, admin_usuario
):
    # No painel o backend recusa e o Django envia user_login_failed mesmo assim.
    errar(client, "admin@exemplo.test", 5)

    for _ in range(3):
        client.post(
            reverse("admin:login"),
            {"username": "admin@exemplo.test", "password": SENHA_DE_TESTE},
        )

    assert FalhaLogin.objects.count() == 5


def test_funcoes_normalizam_maiusculas_e_espacos():
    for _ in range(5):
        registrar_falha("  Pessoa6@Exemplo.TEST ")

    assert set(FalhaLogin.objects.values_list("email", flat=True)) == {
        "pessoa6@exemplo.test"
    }
    assert esta_bloqueado(" PESSOA6@exemplo.test  ")


def test_login_do_painel_registra_falhas_e_entra_sem_bloqueio(client, admin_usuario):
    for _ in range(4):
        client.post(
            reverse("admin:login"),
            {"username": "admin@exemplo.test", "password": "senha-errada"},
        )
    assert FalhaLogin.objects.count() == 4

    resposta = client.post(
        reverse("admin:login"),
        {"username": "admin@exemplo.test", "password": SENHA_DE_TESTE},
    )

    assert resposta.status_code == 302
    assert FalhaLogin.objects.count() == 0


def test_mensagem_uniforme_continua_antes_do_bloqueio(client, membro):
    for tentativa in range(5):
        resposta = entrar(client, "pessoa1@exemplo.test", "senha-errada")
        conteudo = resposta.content.decode()
        assert MENSAGEM_ERRO in conteudo, tentativa
        assert MENSAGEM_BLOQUEIO not in conteudo, tentativa


def test_registrar_falha_apaga_linhas_fora_da_janela():
    falhas_antigas("pessoa3@exemplo.test", 3)
    falhas_antigas("pessoa4@exemplo.test", 2)

    registrar_falha("pessoa5@exemplo.test")

    assert list(FalhaLogin.objects.values_list("email", flat=True)) == [
        "pessoa5@exemplo.test"
    ]
