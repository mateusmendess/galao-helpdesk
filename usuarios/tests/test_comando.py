import pytest
from django.core.management import CommandError, call_command

from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


def test_cria_sete_pessoas_ficticias_sem_senha_e_sem_admin(settings):
    settings.DEBUG = True

    call_command("criar_equipe_de_teste")

    pessoas = list(Usuario.objects.order_by("ordem"))
    assert [p.ordem for p in pessoas] == [1, 2, 3, 4, 5, 6, 7]
    assert [p.email for p in pessoas] == [
        f"pessoa{n}@exemplo.test" for n in range(1, 8)
    ]
    assert [p.first_name for p in pessoas] == [f"Pessoa {n}" for n in range(1, 8)]
    for pessoa in pessoas:
        assert pessoa.is_active
        assert not pessoa.is_staff
        assert not pessoa.is_superuser
        assert not pessoa.has_usable_password()


def test_rodar_duas_vezes_nao_duplica(settings):
    settings.DEBUG = True

    call_command("criar_equipe_de_teste")
    call_command("criar_equipe_de_teste")

    assert Usuario.objects.count() == 7


def test_recusa_com_debug_desligado(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        call_command("criar_equipe_de_teste")

    assert Usuario.objects.count() == 0


def test_ordem_ocupada_por_outra_conta_nao_cria_ninguem(settings):
    settings.DEBUG = True
    Usuario.objects.create_user(email="outra@exemplo.test", ordem=3)

    with pytest.raises(CommandError, match="ordem 3"):
        call_command("criar_equipe_de_teste")

    assert Usuario.objects.count() == 1
