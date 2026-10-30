import re

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from conftest import SENHA_DE_TESTE
from usuarios.models import FalhaLogin, Usuario

pytestmark = pytest.mark.django_db

# Senha errada derivada da do conftest (nada de senha escrita no teste).
SENHA_ERRADA = SENHA_DE_TESTE + "-errada"
MENSAGEM_ERRO = "Matrícula ou senha incorretas."
MENSAGEM_BLOQUEIO = "Muitas tentativas de entrada. Tente de novo em alguns minutos."


def entrar(client, identificador, senha):
    return client.post(reverse("login"), {"username": identificador, "password": senha})


def esta_logado(client):
    return "_auth_user_id" in client.session


@pytest.fixture
def com_matricula(membro):
    membro.matricula = "1001"
    membro.save()
    return membro


# Entrar


def test_matricula_e_senha_certas_entram(client, com_matricula):
    resposta = entrar(client, "1001", SENHA_DE_TESTE)

    assert resposta.status_code == 302
    assert resposta.url == reverse("home")
    assert client.session["_auth_user_id"] == str(com_matricula.pk)


def test_email_com_maiusculas_misturadas_continua_entrando(client, com_matricula):
    assert entrar(client, "PeSSoa1@Exemplo.TEST", SENHA_DE_TESTE).status_code == 302
    assert esta_logado(client)


def test_quem_nao_tem_matricula_entra_pelo_email(client, membro):
    assert membro.matricula is None

    assert entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE).status_code == 302


def test_matricula_com_espacos_nas_pontas_entra(client, com_matricula):
    assert entrar(client, "  1001 ", SENHA_DE_TESTE).status_code == 302


def test_zeros_a_esquerda_contam(client, django_user_model):
    django_user_model.objects.create_user(
        email="pessoa2@exemplo.test", password=SENHA_DE_TESTE, matricula="0123"
    )

    assert entrar(client, "123", SENHA_DE_TESTE).status_code == 200
    assert not esta_logado(client)
    assert entrar(client, "0123", SENHA_DE_TESTE).status_code == 302


def test_matricula_inexistente_e_senha_errada_dao_a_mesma_resposta(
    client, com_matricula
):
    def erro(resposta):
        html = resposta.content.decode()
        return re.search(r'role="alert">.*?</div>\s*</div>', html, flags=re.S)[0]

    inexistente = entrar(client, "9999", SENHA_DE_TESTE)
    senha_errada = entrar(client, "1001", SENHA_ERRADA)

    assert inexistente.status_code == senha_errada.status_code == 200
    assert MENSAGEM_ERRO in erro(inexistente)
    assert erro(inexistente) == erro(senha_errada)
    assert not esta_logado(client)


@pytest.mark.parametrize("identificador", ["1001", "pessoa1@exemplo.test"])
def test_usuario_inativo_nao_entra_por_nenhuma_das_formas(
    client, com_matricula, identificador
):
    com_matricula.is_active = False
    com_matricula.save()

    resposta = entrar(client, identificador, SENHA_DE_TESTE)

    assert resposta.status_code == 200
    assert not esta_logado(client)


# Bloqueio de tentativas


def test_erros_pela_matricula_e_pelo_email_contam_juntos(client, com_matricula):
    for _ in range(3):
        entrar(client, "1001", SENHA_ERRADA)
    for _ in range(2):
        entrar(client, "Pessoa1@exemplo.test", SENHA_ERRADA)

    pela_matricula = entrar(client, "1001", SENHA_DE_TESTE)
    pelo_email = entrar(client, "pessoa1@exemplo.test", SENHA_DE_TESTE)

    assert MENSAGEM_BLOQUEIO in pela_matricula.content.decode()
    assert MENSAGEM_BLOQUEIO in pelo_email.content.decode()
    assert not esta_logado(client)
    # A falha fica guardada pelo e-mail da pessoa, nao pela matricula.
    assert set(FalhaLogin.objects.values_list("email", flat=True)) == {
        "pessoa1@exemplo.test"
    }


def test_painel_tambem_bloqueia_pela_matricula(client, admin_usuario):
    admin_usuario.matricula = "1002"
    admin_usuario.save()
    for _ in range(5):
        entrar(client, "admin@exemplo.test", SENHA_ERRADA)

    resposta = client.post(
        reverse("admin:login"), {"username": "1002", "password": SENHA_DE_TESTE}
    )

    assert resposta.status_code == 200
    assert not esta_logado(client)


def test_identificador_de_ninguem_conta_pelo_texto_digitado(client):
    for _ in range(5):
        entrar(client, " 9999 ", SENHA_ERRADA)
    entrar(client, "Ninguem@Exemplo.test", SENHA_ERRADA)

    assert set(FalhaLogin.objects.values_list("email", flat=True)) == {
        "9999",
        "ninguem@exemplo.test",
    }
    assert MENSAGEM_BLOQUEIO in entrar(client, "9999", SENHA_ERRADA).content.decode()


# Cadastro da matricula


def test_duas_pessoas_sem_matricula_convivem(django_user_model):
    um = django_user_model.objects.create_user(email="p1@exemplo.test", matricula="")
    dois = django_user_model.objects.create_user(
        email="p2@exemplo.test", matricula="   "
    )

    um.refresh_from_db()
    dois.refresh_from_db()
    assert um.matricula is None and dois.matricula is None


def test_matricula_repetida_e_recusada(django_user_model):
    django_user_model.objects.create_user(email="p1@exemplo.test", matricula="1001")
    outro = Usuario(email="p2@exemplo.test", matricula=" 1001 ")
    outro.set_unusable_password()

    with pytest.raises(ValidationError) as erro:
        outro.full_clean()
    assert "matricula" in erro.value.message_dict

    with pytest.raises(IntegrityError), transaction.atomic():
        outro.save()


@pytest.mark.parametrize("valor", ["12a3", "abc", "1 2", "-12", "1.0"])
def test_matricula_so_aceita_numeros(valor):
    usuario = Usuario(email="p1@exemplo.test", matricula=valor)
    usuario.set_unusable_password()

    with pytest.raises(ValidationError) as erro:
        usuario.full_clean()
    assert erro.value.message_dict["matricula"] == ["A matrícula deve ter só números."]


def test_espacos_nas_pontas_somem_ao_validar_e_salvar():
    usuario = Usuario(email="p1@exemplo.test", matricula="  0042 ")
    usuario.set_unusable_password()

    usuario.full_clean()
    assert usuario.matricula == "0042"


# Painel


def dados_novo_usuario(matricula):
    return {
        "email": "pessoa8@exemplo.test",
        "matricula": matricula,
        "first_name": "Pessoa 8",
        "usable_password": "true",
        "password1": SENHA_DE_TESTE,
        "password2": SENHA_DE_TESTE,
    }


def test_admin_cria_usuario_com_matricula_e_ve_na_lista_e_na_busca(
    client, admin_usuario
):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"), dados_novo_usuario(" 1008 ")
    )

    assert resposta.status_code == 302
    novo = Usuario.objects.get(email="pessoa8@exemplo.test")
    assert novo.matricula == "1008"
    edicao = client.get(reverse("admin:usuarios_usuario_change", args=[novo.pk]))
    assert 'name="matricula"' in edicao.content.decode()
    busca = client.get(reverse("admin:usuarios_usuario_changelist"), {"q": "1008"})
    html = busca.content.decode()
    assert "pessoa8@exemplo.test" in html and "admin@exemplo.test" not in html
    assert "column-matricula" in html


def test_admin_cria_usuario_sem_matricula(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"), dados_novo_usuario("")
    )

    assert resposta.status_code == 302
    assert Usuario.objects.get(email="pessoa8@exemplo.test").matricula is None


def test_admin_recusa_matricula_com_letras(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"), dados_novo_usuario("10a8")
    )

    assert resposta.status_code == 200
    assert "A matrícula deve ter só números." in resposta.content.decode()
    assert not Usuario.objects.filter(email="pessoa8@exemplo.test").exists()


# Tela e troca obrigatoria


def test_tela_pede_matricula_em_campo_de_texto(client):
    html = client.get(reverse("login")).content.decode()

    campo = re.search(r'<input type="text" name="username"[^>]*>', html)[0]
    assert re.search(r'<label for="id_username"[^>]*>Matrícula</label>', html)
    assert ">E-mail</label>" not in html
    assert 'autocomplete="username"' in campo
    assert 'autocapitalize="none"' in campo and 'spellcheck="false"' in campo
    assert "inputmode" not in campo


def test_troca_obrigatoria_continua_depois_de_entrar_pela_matricula(
    client, com_matricula
):
    com_matricula.precisa_trocar_senha = True
    com_matricula.save()

    resposta = entrar(client, "1001", SENHA_DE_TESTE)

    assert client.get(resposta.url).url == reverse("password_change")
