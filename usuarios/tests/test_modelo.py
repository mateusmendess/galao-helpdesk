import pytest
from django.db import IntegrityError, transaction

from conftest import SENHA_DE_TESTE
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


def test_create_user_guarda_email_em_minusculas_sem_username():
    usuario = Usuario.objects.create_user(
        email="Pessoa2@Exemplo.TEST", password=SENHA_DE_TESTE
    )

    usuario.refresh_from_db()
    assert usuario.email == "pessoa2@exemplo.test"
    assert usuario.username is None
    assert usuario.password != SENHA_DE_TESTE
    assert usuario.check_password(SENHA_DE_TESTE)
    assert not usuario.is_staff
    assert not usuario.is_superuser


def test_save_e_clean_guardam_email_em_minusculas():
    usuario = Usuario(email="Pessoa3@EXEMPLO.test")
    usuario.clean()
    assert usuario.email == "pessoa3@exemplo.test"

    usuario.email = "PESSOA3@exemplo.test"
    usuario.set_unusable_password()
    usuario.save()
    usuario.refresh_from_db()
    assert usuario.email == "pessoa3@exemplo.test"


def test_email_repetido_com_maiusculas_diferentes_e_recusado():
    Usuario.objects.create_user(email="pessoa4@exemplo.test")

    with pytest.raises(IntegrityError), transaction.atomic():
        Usuario.objects.create_user(email="PESSOA4@exemplo.test")


def test_create_superuser_liga_is_staff_e_is_superuser():
    admin = Usuario.objects.create_superuser(
        email="admin@exemplo.test", password=SENHA_DE_TESTE
    )

    assert admin.is_staff
    assert admin.is_superuser


def test_duas_pessoas_nao_podem_ter_a_mesma_ordem():
    Usuario.objects.create_user(email="pessoa5@exemplo.test", ordem=5)

    with pytest.raises(IntegrityError), transaction.atomic():
        Usuario.objects.create_user(email="pessoa6@exemplo.test", ordem=5)


def test_varias_pessoas_sem_ordem_sao_permitidas():
    Usuario.objects.create_user(email="pessoa5@exemplo.test")
    Usuario.objects.create_user(email="pessoa6@exemplo.test")

    assert Usuario.objects.filter(ordem__isnull=True).count() == 2
