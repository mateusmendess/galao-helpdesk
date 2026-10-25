import pytest
from django.urls import reverse

from conftest import SENHA_DE_TESTE
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


def test_membro_nao_acessa_o_painel(client, membro):
    client.force_login(membro)

    resposta = client.get(reverse("admin:index"))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("admin:login"))


def test_admin_acessa_a_lista_e_a_tela_de_criar_usuario(client, admin_usuario):
    client.force_login(admin_usuario)

    lista = client.get(reverse("admin:usuarios_usuario_changelist"))
    criar = client.get(reverse("admin:usuarios_usuario_add"))

    assert lista.status_code == 200
    assert criar.status_code == 200


def test_admin_cria_usuario_pelo_painel_com_email(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"),
        {
            "email": "Pessoa7@Exemplo.test",
            "first_name": "Pessoa 7",
            "ordem": "7",
            "usable_password": "true",
            "password1": SENHA_DE_TESTE,
            "password2": SENHA_DE_TESTE,
        },
    )

    assert resposta.status_code == 302
    novo = Usuario.objects.get(email="pessoa7@exemplo.test")
    assert novo.ordem == 7
    assert novo.check_password(SENHA_DE_TESTE)
    assert not novo.is_staff


@pytest.mark.parametrize("metodo", ["get", "post"])
def test_redefinir_senha_de_usuario_inexistente_da_404(client, admin_usuario, metodo):
    client.force_login(admin_usuario)
    url = reverse("admin:auth_user_password_change", args=["999999"])

    resposta = getattr(client, metodo)(url)

    assert resposta.status_code == 404
