import pytest

# Senha ficticia, usada so no banco temporario dos testes.
SENHA_DE_TESTE = "galao-teste-2026"


@pytest.fixture
def membro(django_user_model):
    return django_user_model.objects.create_user(
        email="pessoa1@exemplo.test",
        password=SENHA_DE_TESTE,
        first_name="Pessoa 1",
        ordem=1,
    )


@pytest.fixture
def admin_usuario(django_user_model):
    return django_user_model.objects.create_superuser(
        email="admin@exemplo.test",
        password=SENHA_DE_TESTE,
        first_name="Pessoa Admin",
    )
