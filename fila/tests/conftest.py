import pytest

from fila.models import Troca
from fila.regras import rodada_atual

TAMANHO_DA_EQUIPE = 7


@pytest.fixture
def equipe(django_user_model):
    """Pessoa 1 a Pessoa 7, ordem 1 a 7 (contas ficticias)."""
    return [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem=n
        )
        for n in range(1, TAMANHO_DA_EQUIPE + 1)
    ]


@pytest.fixture
def registrar(admin_usuario):
    """Grava uma troca como o admin faria (executor = titular sem cobertura)."""

    def _registrar(titular, executor=None, rodada=None):
        return Troca.objects.create(
            rodada=rodada or rodada_atual(),
            titular=titular,
            executor=executor or titular,
            registrada_por=admin_usuario,
        )

    return _registrar
