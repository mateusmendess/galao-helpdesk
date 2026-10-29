"""O sabado termina as 17h (hora local) do proprio sabado."""

from datetime import UTC, datetime, time, timedelta
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from escala import datas
from escala.calculo import calendario, congelar_passados
from escala.models import (
    ConfiguracaoEscala,
    SabadoDuasPessoas,
    SabadoFechado,
    SabadoSemEscala,
)

from .conftest import PROXIMO_SABADO, SABADO

pytestmark = pytest.mark.django_db

ANTES = time(16, 59)
FIM = time(17, 0)


@pytest.fixture
def equipe(django_user_model):
    return [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem_escala=n
        )
        for n in range(1, 4)
    ]


@pytest.fixture
def configurada(equipe):
    return ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=equipe[0])


def test_as_16h59_o_sabado_ainda_e_o_destaque(hoje, configurada, equipe):
    hoje(SABADO, ANTES)

    dias = calendario(2)

    assert [(d.data, d.manha) for d in dias] == [
        (SABADO, equipe[0]),
        (PROXIMO_SABADO, equipe[1]),
    ]
    assert not SabadoFechado.objects.exists()


def test_as_17h_o_sabado_e_gravado_e_o_destaque_e_o_seguinte(hoje, configurada, equipe):
    hoje(SABADO, FIM)

    dias = calendario(2)

    assert [d.data for d in dias] == [PROXIMO_SABADO, PROXIMO_SABADO + timedelta(7)]
    assert dias[0].manha == equipe[1]
    fechado = SabadoFechado.objects.get()
    assert (fechado.data, fechado.manha) == (SABADO, equipe[0])


def test_congelar_nao_grava_sabado_nao_terminado(hoje, configurada):
    hoje(PROXIMO_SABADO, ANTES)

    assert congelar_passados() == 1
    assert list(SabadoFechado.objects.values_list("data", flat=True)) == [SABADO]

    hoje(PROXIMO_SABADO, FIM)
    assert congelar_passados() == 1


@pytest.mark.parametrize("modelo", [SabadoSemEscala, SabadoDuasPessoas])
def test_cadastro_aceito_ate_16h59_e_recusado_as_17h(hoje, modelo):
    hoje(SABADO, ANTES)
    modelo(data=SABADO).full_clean()

    hoje(SABADO, FIM)
    with pytest.raises(ValidationError) as erro:
        modelo(data=SABADO).full_clean()
    assert erro.value.message_dict == {
        "data": ["Esse sábado já passou e não pode mais mudar."]
    }


def test_admin_cadastra_as_16h59_e_recusa_as_17h(client, hoje, admin_usuario):
    client.force_login(admin_usuario)
    url = reverse("admin:escala_sabadosemescala_add")
    dados = {"data": "05/12/2026", "motivo": "imprevisto", "passa_para_proximo": "on"}

    hoje(SABADO, FIM)
    recusado = client.post(url, dados)
    hoje(SABADO, ANTES)
    aceito = client.post(url, dados)

    assert "Esse sábado já passou e não pode mais mudar." in recusado.content.decode()
    assert aceito.status_code == 302
    linha = SabadoSemEscala.objects.get()
    alterar = reverse("admin:escala_sabadosemescala_change", args=[linha.pk])
    assert client.get(alterar).status_code == 200
    hoje(SABADO, FIM)
    assert client.post(alterar, dados).status_code == 403


def test_hora_local_e_nao_utc():
    # 00:00 UTC de sabado = 21:00 de sexta em Sao Paulo.
    sexta_21h_local = datetime(2026, 12, 5, 0, 0, tzinfo=UTC)
    with mock.patch("django.utils.timezone.now", return_value=sexta_21h_local):
        assert datas.agora().hour == 21
        assert datas.hoje() == SABADO - timedelta(days=1)
        assert datas.primeiro_sabado_aberto() == SABADO

    # 16:59 de sabado em Sao Paulo = 19:59 UTC: ainda nao terminou.
    sabado_16h59_local = datetime(2026, 12, 5, 19, 59, tzinfo=UTC)
    with mock.patch("django.utils.timezone.now", return_value=sabado_16h59_local):
        assert not datas.sabado_terminou(SABADO)
    with mock.patch(
        "django.utils.timezone.now",
        return_value=sabado_16h59_local + timedelta(minutes=1),
    ):
        assert datas.sabado_terminou(SABADO)


def test_fim_do_sabado_num_so_lugar():
    assert datas.FIM_DO_SABADO == time(17, 0)
