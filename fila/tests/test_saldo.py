import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from fila.regras import rodada_atual, saldos_devendo

pytestmark = pytest.mark.django_db


def test_sem_trocas_ninguem_deve(equipe):
    assert saldos_devendo() == {}


def test_quem_foi_coberto_passa_a_dever_1(equipe, registrar):
    a, b = equipe[:2]

    registrar(a, executor=b)

    assert saldos_devendo() == {a.pk: 1}


def test_cobrir_outra_pessoa_quita_a_divida(equipe, registrar):
    a, b, c = equipe[:3]
    registrar(a, executor=b)
    assert saldos_devendo() == {a.pk: 1}

    registrar(c, executor=a)  # A cobre C

    # A volta a 0 e some; C passa a dever; B (credito) nao aparece.
    assert saldos_devendo() == {c.pk: 1}


def test_troca_do_proprio_titular_nao_muda_o_saldo(equipe, registrar):
    for pessoa in equipe[:3]:
        registrar(pessoa)

    assert saldos_devendo() == {}


def test_divida_atravessa_a_rodada(equipe, registrar):
    a, b = equipe[:2]
    registrar(a, executor=b)
    for pessoa in equipe[1:]:
        registrar(pessoa)

    assert rodada_atual().numero == 2
    assert saldos_devendo() == {a.pk: 1}


def test_quem_cobriu_mais_nao_aparece(equipe, registrar):
    a, b, c = equipe[:3]

    registrar(a, executor=c)
    registrar(b, executor=c)

    saldos = saldos_devendo()
    assert saldos == {a.pk: 1, b.pk: 1}
    assert c.pk not in saldos


def test_saldo_usa_no_maximo_2_consultas(equipe, registrar):
    for i, pessoa in enumerate(equipe):
        registrar(pessoa, executor=equipe[(i + 1) % len(equipe)])

    with CaptureQueriesContext(connection) as consultas:
        saldos_devendo()

    assert len(consultas) <= 2
