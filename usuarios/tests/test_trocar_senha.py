import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import NoReverseMatch, reverse

from conftest import SENHA_DE_TESTE
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db

NOVA_SENHA = "jarra-azul-limpa-77"
MENSAGEM_SENHA_IGUAL = "A nova senha precisa ser diferente da atual."
AVISO = "Por segurança, troque a senha provisória antes de continuar."


def trocar(client, atual, nova, confirmacao=None):
    return client.post(
        reverse("password_change"),
        {
            "old_password": atual,
            "new_password1": nova,
            "new_password2": nova if confirmacao is None else confirmacao,
        },
    )


def senha_entra(email, senha):
    resposta = Client().post(reverse("login"), {"username": email, "password": senha})
    return resposta.status_code == 302


@pytest.fixture
def provisorio(membro):
    membro.precisa_trocar_senha = True
    membro.save()
    return membro


@pytest.fixture
def admin_provisorio(admin_usuario):
    admin_usuario.precisa_trocar_senha = True
    admin_usuario.save()
    return admin_usuario


# Troca de senha


@pytest.mark.parametrize("rota", ["password_change", "password_change_done"])
def test_anonimo_vai_para_o_login(client, rota):
    resposta = client.get(reverse(rota))

    assert resposta.status_code == 302
    assert resposta.url == "/entrar/?next=" + reverse(rota)


def test_logado_ve_a_tela_com_os_tres_campos(client, membro):
    client.force_login(membro)

    resposta = client.get(reverse("password_change"))

    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Trocar senha" in conteudo
    for campo in ("old_password", "new_password1", "new_password2"):
        assert f'name="{campo}"' in conteudo
    assert "Salvar nova senha" in conteudo


def test_senha_atual_errada_nao_troca(client, membro):
    client.force_login(membro)

    resposta = trocar(client, "senha-errada", NOVA_SENHA)

    assert resposta.status_code == 200
    assert resposta.context["form"].has_error("old_password", "password_incorrect")
    membro.refresh_from_db()
    assert membro.check_password(SENHA_DE_TESTE)


def test_confirmacao_diferente_nao_troca(client, membro):
    client.force_login(membro)

    resposta = trocar(client, SENHA_DE_TESTE, NOVA_SENHA, "outra-coisa-99")

    form = resposta.context["form"]
    assert form.has_error("new_password2", "password_mismatch")
    assert "new_password1" not in form.errors
    conteudo = resposta.content.decode()
    erro = form.errors["new_password2"][0]
    assert conteudo.index('name="new_password2"') < conteudo.index(erro)
    membro.refresh_from_db()
    assert membro.check_password(SENHA_DE_TESTE)


@pytest.mark.parametrize(
    "fraca, codigo",
    [
        ("ab1", "password_too_short"),
        ("8461937205", "password_entirely_numeric"),
        ("password123", "password_too_common"),
    ],
)
def test_senha_fraca_nao_troca_e_mostra_o_validador(client, membro, fraca, codigo):
    client.force_login(membro)

    resposta = trocar(client, SENHA_DE_TESTE, fraca)

    form = resposta.context["form"]
    assert form.has_error("new_password1", codigo)
    assert "new_password2" not in form.errors
    # O erro aparece sob "Nova senha", antes do campo de confirmacao.
    conteudo = resposta.content.decode()
    for erro in form.errors["new_password1"]:
        posicao = conteudo.index(erro)
        assert conteudo.index('name="new_password1"') < posicao
        assert posicao < conteudo.index('name="new_password2"')
    membro.refresh_from_db()
    assert membro.check_password(SENHA_DE_TESTE)


def test_nova_senha_igual_a_atual_nao_troca(client, membro):
    client.force_login(membro)

    resposta = trocar(client, SENHA_DE_TESTE, SENHA_DE_TESTE)

    assert resposta.status_code == 200
    assert resposta.context["form"].has_error("new_password1", "senha_igual")
    assert MENSAGEM_SENHA_IGUAL in resposta.content.decode()
    membro.refresh_from_db()
    assert membro.check_password(SENHA_DE_TESTE)


def test_senha_igual_nao_e_dita_se_a_atual_estiver_errada(client, membro):
    # Senao a tela diria se um chute e a senha atual sem conferir a atual.
    client.force_login(membro)

    resposta = trocar(client, "senha-errada", SENHA_DE_TESTE)

    assert resposta.context["form"].has_error("old_password", "password_incorrect")
    assert MENSAGEM_SENHA_IGUAL not in resposta.content.decode()


def test_troca_valida_muda_a_senha_e_continua_logado(client, membro):
    client.force_login(membro)

    resposta = trocar(client, SENHA_DE_TESTE, NOVA_SENHA)

    assert resposta.status_code == 302
    assert resposta.url == reverse("password_change_done")
    assert client.get(reverse("home")).status_code == 200
    assert not senha_entra("pessoa1@exemplo.test", SENHA_DE_TESTE)
    assert senha_entra("pessoa1@exemplo.test", NOVA_SENHA)


def test_troca_encerra_as_outras_sessoes(client, membro):
    outro_navegador = Client()
    outro_navegador.force_login(membro)
    client.force_login(membro)

    trocar(client, SENHA_DE_TESTE, NOVA_SENHA)

    # A outra sessao caiu: "/" mostra a pagina publica, nao o galao.
    fora = outro_navegador.get(reverse("home"))
    assert "publica/inicio.html" in [t.name for t in fora.templates]
    assert client.get(reverse("home")).status_code == 200


def test_admin_troca_a_propria_senha(client, admin_usuario):
    client.force_login(admin_usuario)

    assert trocar(client, SENHA_DE_TESTE, NOVA_SENHA).status_code == 302
    admin_usuario.refresh_from_db()
    assert admin_usuario.check_password(NOVA_SENHA)


def test_membro_troca_a_propria_senha(client, membro):
    client.force_login(membro)

    assert trocar(client, SENHA_DE_TESTE, NOVA_SENHA).status_code == 302
    membro.refresh_from_db()
    assert membro.check_password(NOVA_SENHA)


def test_tela_de_senha_alterada(client, membro):
    client.force_login(membro)

    resposta = client.get(reverse("password_change_done"))

    conteudo = resposta.content.decode()
    assert "Senha alterada" in conteudo
    assert "Sua senha foi alterada com sucesso." in conteudo
    assert "Sua nova senha já vale." not in conteudo


def test_nao_existe_esqueci_a_senha(client):
    with pytest.raises(NoReverseMatch):
        reverse("password_reset")

    assert client.get("/senha/redefinir/").status_code == 404


def test_link_trocar_senha_na_inicial_para_todos(client, membro, admin_usuario):
    link = 'href="{}"'.format(reverse("password_change"))

    client.force_login(membro)
    assert link in client.get(reverse("home")).content.decode()

    client.force_login(admin_usuario)
    assert link in client.get(reverse("home")).content.decode()


# Troca obrigatoria


@pytest.mark.parametrize("rota", ["home", "login"])
def test_com_a_marca_toda_rota_leva_para_a_troca(client, provisorio, rota):
    client.force_login(provisorio)

    resposta = client.get(reverse(rota))

    assert resposta.status_code == 302
    assert resposta.url == reverse("password_change")


@pytest.mark.parametrize(
    "rota",
    [
        "admin:index",
        "admin:usuarios_usuario_changelist",
        "admin:password_change",
        "admin:password_change_done",
    ],
)
def test_admin_com_a_marca_nao_abre_o_painel(client, admin_provisorio, rota):
    client.force_login(admin_provisorio)

    resposta = client.get(reverse(rota))

    assert resposta.status_code == 302
    assert resposta.url == reverse("password_change")


def test_com_a_marca_abre_as_rotas_liberadas(client, provisorio):
    client.force_login(provisorio)

    assert client.get(reverse("password_change")).status_code == 200
    assert client.get(reverse("password_change_done")).status_code == 200
    assert client.get(reverse("saude")).status_code == 200

    saida = client.post(reverse("logout"))
    assert saida.status_code == 302
    assert saida.url == reverse("login")


def test_troca_valida_desliga_a_marca_e_libera_a_inicial(client, provisorio):
    client.force_login(provisorio)

    trocar(client, SENHA_DE_TESTE, NOVA_SENHA)

    provisorio.refresh_from_db()
    assert not provisorio.precisa_trocar_senha
    assert client.get(reverse("home")).status_code == 200


def test_troca_recusada_mantem_a_marca(client, provisorio):
    client.force_login(provisorio)

    trocar(client, SENHA_DE_TESTE, SENHA_DE_TESTE)

    provisorio.refresh_from_db()
    assert provisorio.precisa_trocar_senha
    assert client.get(reverse("home")).status_code == 302


def test_sem_a_marca_nada_e_redirecionado(client, admin_usuario):
    client.force_login(admin_usuario)

    for rota in ("home", "password_change", "password_change_done", "admin:index"):
        assert client.get(reverse(rota)).status_code == 200, rota


def test_anonimo_ve_a_pagina_publica_e_o_login(client):
    inicio = client.get(reverse("home"))
    assert "publica/inicio.html" in [t.name for t in inicio.templates]
    assert client.get(reverse("login")).status_code == 200
    assert client.get(reverse("saude")).status_code == 200


def test_aviso_e_voltar_dependem_da_marca(client, membro):
    voltar = 'href="{}"'.format(reverse("home"))
    client.force_login(membro)

    sem_marca = client.get(reverse("password_change")).content.decode()
    assert AVISO not in sem_marca
    assert voltar in sem_marca

    membro.precisa_trocar_senha = True
    membro.save()
    com_marca = client.get(reverse("password_change")).content.decode()
    assert AVISO in com_marca
    assert 'role="status"' in com_marca
    assert voltar not in com_marca


def test_troca_pelo_painel_nao_libera_o_site(client, admin_provisorio):
    client.force_login(admin_provisorio)

    resposta = client.post(
        reverse("admin:password_change"),
        {
            "old_password": SENHA_DE_TESTE,
            "new_password1": NOVA_SENHA,
            "new_password2": NOVA_SENHA,
        },
    )

    assert resposta.url == reverse("password_change")
    admin_provisorio.refresh_from_db()
    assert admin_provisorio.check_password(SENHA_DE_TESTE)
    assert admin_provisorio.precisa_trocar_senha
    assert client.get(reverse("home")).url == reverse("password_change")


# Quem liga a marca


def dados_do_novo_usuario(**extra):
    return {
        "email": "pessoa7@exemplo.test",
        "first_name": "Pessoa 7",
        "usable_password": "true",
        "password1": SENHA_DE_TESTE,
        "password2": SENHA_DE_TESTE,
        **extra,
    }


def test_adicionar_usuario_abre_com_a_marca_ligada(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.get(reverse("admin:usuarios_usuario_add"))

    campo = resposta.context["adminform"].form["precisa_trocar_senha"]
    assert campo.value() is True
    assert "checked" in str(campo)


def test_adicionar_usuario_marcado_cria_com_a_marca(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"),
        dados_do_novo_usuario(precisa_trocar_senha="on"),
    )

    assert resposta.status_code == 302
    assert Usuario.objects.get(email="pessoa7@exemplo.test").precisa_trocar_senha


def test_adicionar_usuario_desmarcado_cria_sem_a_marca(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"), dados_do_novo_usuario()
    )

    assert resposta.status_code == 302
    assert not Usuario.objects.get(email="pessoa7@exemplo.test").precisa_trocar_senha


def test_alterar_usuario_mostra_o_campo_e_liga_a_marca(client, admin_usuario, membro):
    client.force_login(admin_usuario)
    url = reverse("admin:usuarios_usuario_change", args=[membro.pk])

    tela = client.get(url)
    assert "precisa_trocar_senha" in tela.context["adminform"].form.fields

    dados = {
        "email": membro.email,
        "first_name": membro.first_name,
        "last_name": "",
        "ordem": membro.ordem,
        "is_active": "on",
        "precisa_trocar_senha": "on",
        "date_joined_0": "2026-01-01",
        "date_joined_1": "08:00:00",
    }
    resposta = client.post(url, dados)

    assert resposta.status_code == 302
    membro.refresh_from_db()
    assert membro.precisa_trocar_senha


def test_contas_novas_por_padrao_ficam_sem_a_marca(settings):
    settings.DEBUG = True

    call_command("criar_equipe_de_teste")
    call_command(
        "createsuperuser", interactive=False, email="admin2@exemplo.test", verbosity=0
    )

    assert Usuario.objects.count() == 8
    assert not Usuario.objects.filter(precisa_trocar_senha=True).exists()


# Admin redefine a senha pelo painel


def redefinir_pelo_painel(client, usuario, senha, confirmacao=None):
    return client.post(
        reverse("admin:auth_user_password_change", args=[usuario.pk]),
        {
            "usable_password": "true",
            "password1": senha,
            "password2": senha if confirmacao is None else confirmacao,
        },
    )


def test_redefinir_senha_de_outra_pessoa_liga_a_marca(client, admin_usuario, membro):
    assert not membro.precisa_trocar_senha
    client.force_login(admin_usuario)

    resposta = redefinir_pelo_painel(client, membro, NOVA_SENHA)

    assert resposta.status_code == 302
    membro.refresh_from_db()
    assert membro.check_password(NOVA_SENHA)
    assert membro.precisa_trocar_senha


def test_redefinir_a_propria_senha_nao_liga_a_marca(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = redefinir_pelo_painel(client, admin_usuario, NOVA_SENHA)

    assert resposta.status_code == 302
    admin_usuario.refresh_from_db()
    assert admin_usuario.check_password(NOVA_SENHA)
    assert not admin_usuario.precisa_trocar_senha
    assert client.get(reverse("admin:index")).status_code == 200


@pytest.mark.parametrize(
    "senha, confirmacao", [("ab1", None), (NOVA_SENHA, "outra-coisa-99")]
)
def test_redefinicao_recusada_nao_liga_a_marca(
    client, admin_usuario, membro, senha, confirmacao
):
    client.force_login(admin_usuario)

    resposta = redefinir_pelo_painel(client, membro, senha, confirmacao)

    assert resposta.status_code == 200
    membro.refresh_from_db()
    assert membro.check_password(SENHA_DE_TESTE)
    assert not membro.precisa_trocar_senha


def test_desativar_a_senha_pelo_painel_nao_liga_a_marca(client, admin_usuario, membro):
    client.force_login(admin_usuario)

    client.post(
        reverse("admin:auth_user_password_change", args=[membro.pk]),
        {"usable_password": "false", "unset-password": "1"},
    )

    membro.refresh_from_db()
    assert not membro.has_usable_password()
    assert not membro.precisa_trocar_senha


def test_senha_redefinida_obriga_a_troca_no_proximo_acesso(admin_usuario, membro):
    painel = Client()
    painel.force_login(admin_usuario)
    redefinir_pelo_painel(painel, membro, NOVA_SENHA)

    pessoa = Client()
    entrada = pessoa.post(
        reverse("login"), {"username": "pessoa1@exemplo.test", "password": NOVA_SENHA}
    )
    assert pessoa.get(entrada.url).url == reverse("password_change")

    trocar(pessoa, NOVA_SENHA, "copo-verde-cheio-31")

    membro.refresh_from_db()
    assert not membro.precisa_trocar_senha
    assert pessoa.get(reverse("home")).status_code == 200
