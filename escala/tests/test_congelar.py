from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from escala import calculo
from escala.calculo import ConfiguracaoInvalida, calendario, congelar_passados
from escala.models import (
    ESCALA_JA_COMECOU,
    ConfiguracaoEscala,
    SabadoDuasPessoas,
    SabadoFechado,
    SabadoSemEscala,
)
from fila.models import Ausencia

from .conftest import SABADO

pytestmark = pytest.mark.django_db


def s(k):
    return SABADO + timedelta(weeks=k)


@pytest.fixture
def equipe(django_user_model):
    """Pessoa 1 a Pessoa 7, posicao na escala 1 a 7 (contas ficticias)."""
    return [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem_escala=n
        )
        for n in range(1, 8)
    ]


@pytest.fixture
def configurada(equipe):
    return ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=equipe[0])


def gravados():
    """[(data, manha, tarde, pulados, cursor_depois)] em ordem de data."""
    return [
        (
            f.data,
            f.manha,
            f.tarde,
            tuple(f.pulados.order_by("ordem_escala")),
            f.cursor_depois,
        )
        for f in SabadoFechado.objects.order_by("data")
    ]


def test_sem_configuracao_nao_faz_nada(hoje, equipe):
    hoje(s(5))

    assert congelar_passados() == 0
    assert calendario(3) == []
    assert not SabadoFechado.objects.exists()


@pytest.mark.parametrize("dia", [SABADO - timedelta(days=10), SABADO])
def test_ate_o_inicio_nao_congela(hoje, configurada, dia):
    hoje(dia)

    assert congelar_passados() == 0
    assert not SabadoFechado.objects.exists()


def test_recupera_varias_semanas_e_continua_do_cursor(hoje, configurada, equipe):
    hoje(s(3) + timedelta(days=2))  # segunda depois do 4o sabado

    assert congelar_passados() == 4
    assert [(d, m) for d, m, *_ in gravados()] == [
        (s(0), equipe[0]),
        (s(1), equipe[1]),
        (s(2), equipe[2]),
        (s(3), equipe[3]),
    ]
    assert gravados()[-1][-1] == 4

    hoje(s(5) + timedelta(days=4))
    assert congelar_passados() == 2
    assert [m for _, m, *_ in gravados()][4:] == [equipe[4], equipe[5]]


def test_idempotente(hoje, configurada):
    hoje(s(2) + timedelta(days=1))

    assert congelar_passados() == 3
    antes = gravados()
    assert congelar_passados() == 0
    assert gravados() == antes
    assert SabadoFechado.objects.count() == 3


def test_nao_congela_hoje_nem_o_futuro(hoje, configurada):
    hoje(s(2))  # um sabado

    assert congelar_passados() == 2
    assert SabadoFechado.objects.order_by("-data").first().data == s(1)

    hoje(s(2) + timedelta(days=1))  # domingo
    assert congelar_passados() == 1
    assert SabadoFechado.objects.order_by("-data").first().data == s(2)


def test_grava_cadastros_ausencias_e_pulados(hoje, configurada, equipe):
    SabadoDuasPessoas.objects.create(data=s(0))
    SabadoSemEscala.objects.create(data=s(1), motivo="feriado", passa_para_proximo=True)
    Ausencia.objects.create(usuario=equipe[2], inicio=s(2), fim=s(2))
    hoje(s(3))

    assert congelar_passados() == 3

    assert gravados() == [
        (s(0), equipe[0], equipe[1], (), 2),
        (s(1), None, None, (), 2),
        (s(2), equipe[3], None, (equipe[2],), 4),
    ]
    feriado = SabadoFechado.objects.get(data=s(1))
    assert (feriado.sem_escala, feriado.motivo, feriado.passa_para_proximo) == (
        True,
        "feriado",
        True,
    )
    assert [f.vagas for f in SabadoFechado.objects.order_by("data")] == [2, 1, 1]


def test_mudar_depois_de_congelado_nao_altera_o_gravado(hoje, configurada, equipe):
    hoje(s(2) + timedelta(days=1))
    congelar_passados()
    antes = gravados()

    # Mudancas pelo banco (o admin ja recusaria as datas passadas).
    Ausencia.objects.create(usuario=equipe[0], inicio=s(0), fim=s(2))
    equipe[1].ordem_escala = 20
    equipe[1].save()
    SabadoSemEscala.objects.create(data=s(1), passa_para_proximo=False)
    SabadoDuasPessoas.objects.create(data=s(2))
    hoje(s(3) + timedelta(days=1))
    congelar_passados()
    calendario(3)

    assert gravados()[:3] == antes


def test_outro_processo_gravou_antes(hoje, configurada, equipe):
    hoje(s(2) + timedelta(days=1))
    # Outro processo ja gravou o 1o sabado; esta chamada leu o estado antigo.
    SabadoFechado.objects.create(data=s(0), manha=equipe[0], vagas=1, cursor_depois=1)
    real = calculo.estado_atual
    with mock.patch(
        "escala.calculo.estado_atual",
        side_effect=[(0, s(0)), real(configurada)],
    ):
        assert congelar_passados() == 2

    assert [(d, m) for d, m, *_ in gravados()] == [
        (s(0), equipe[0]),
        (s(1), equipe[1]),
        (s(2), equipe[2]),
    ]


def test_configuracao_invalida_tem_mensagem(hoje, configurada, equipe):
    equipe[0].is_active = False
    equipe[0].save()
    hoje(s(1))

    with pytest.raises(ConfiguracaoInvalida, match="não está na escala"):
        congelar_passados()


def test_calendario_a_partir_de_hoje_continuando_dos_congelados(
    hoje, configurada, equipe
):
    hoje(s(1) + timedelta(days=4))  # quarta depois do 2o sabado

    dias = calendario(3)

    assert [(d.data, d.manha, d.tarde) for d in dias] == [
        (s(2), equipe[2], None),
        (s(3), equipe[3], None),
        (s(4), equipe[4], None),
    ]
    assert SabadoFechado.objects.count() == 2


def test_calendario_com_hoje_sabado_e_antes_do_inicio(hoje, configurada, equipe):
    hoje(s(1))
    assert [d.data for d in calendario(2)] == [s(1), s(2)]
    assert calendario(1)[0].manha == equipe[1]

    SabadoFechado.objects.all().delete()
    hoje(SABADO - timedelta(days=20))
    assert [(d.data, d.manha) for d in calendario(2)] == [
        (s(0), equipe[0]),
        (s(1), equipe[1]),
    ]


def test_calendario_resolve_pulados_e_tarde(hoje, configurada, equipe):
    hoje(s(0) - timedelta(days=1))
    SabadoDuasPessoas.objects.create(data=s(0))
    Ausencia.objects.create(usuario=equipe[1], inicio=s(0), fim=s(0))

    dia = calendario(1)[0]

    assert (dia.manha, dia.tarde, dia.pulados) == (equipe[0], equipe[2], (equipe[1],))


@pytest.mark.parametrize("quantos", [2, 30])
def test_calendario_numero_fixo_de_consultas(hoje, configurada, equipe, quantos):
    Ausencia.objects.create(usuario=equipe[3], inicio=s(0), fim=None)
    SabadoDuasPessoas.objects.create(data=s(6))
    SabadoSemEscala.objects.create(data=s(8))
    hoje(s(4) + timedelta(days=2))
    congelar_passados()

    with CaptureQueriesContext(connection) as consultas:
        dias = calendario(quantos)

    assert len(dias) == quantos
    # congelar sem nada pendente (config, fila, ultimo fechado) + config,
    # fila, ultimo fechado, ausencias, 2 cadastros e usuarios.
    assert len(consultas) == 10


def test_comando_congela_e_conta(hoje, configurada):
    hoje(s(1) + timedelta(days=1))
    saida = StringIO()

    call_command("congelar_escala", stdout=saida)
    call_command("congelar_escala", stdout=saida)

    assert saida.getvalue().splitlines() == [
        "Sábados congelados: 2",
        "Sábados congelados: 0",
    ]


def test_configuracao_livre_antes_e_travada_depois(hoje, configurada, equipe):
    configurada.inicio = s(1)
    configurada.full_clean()  # livre antes do primeiro congelado
    configurada.inicio = SABADO

    hoje(s(1))
    congelar_passados()

    for campo, valor in (("inicio", s(1)), ("primeiro", equipe[1])):
        config = ConfiguracaoEscala.obter()
        setattr(config, campo, valor)
        with pytest.raises(ValidationError) as erro:
            config.full_clean()
        assert erro.value.messages == [ESCALA_JA_COMECOU]
    ConfiguracaoEscala.obter().full_clean()  # sem mudanca, continua valida


def test_admin_trava_inicio_e_primeiro_depois_do_congelado(
    client, hoje, admin_usuario, configurada
):
    client.force_login(admin_usuario)
    url = reverse("admin:escala_configuracaoescala_change", args=[1])

    assert 'name="inicio"' in client.get(url).content.decode()

    hoje(s(1))
    congelar_passados()
    html = client.get(url).content.decode()

    assert 'name="inicio"' not in html and 'name="primeiro"' not in html
    assert html.count('<div class="readonly">') == 2


def test_admin_de_sabado_fechado_so_consulta(client, hoje, admin_usuario, configurada):
    hoje(s(1))
    congelar_passados()
    client.force_login(admin_usuario)
    fechado = SabadoFechado.objects.get()

    assert (
        client.get(reverse("admin:escala_sabadofechado_changelist")).status_code == 200
    )
    tela = client.get(reverse("admin:escala_sabadofechado_change", args=[fechado.pk]))
    assert tela.status_code == 200 and 'name="_save"' not in tela.content.decode()
    assert client.get(reverse("admin:escala_sabadofechado_add")).status_code == 403
    alterar = client.post(
        reverse("admin:escala_sabadofechado_change", args=[fechado.pk]), {}
    )
    assert alterar.status_code == 403
    apagar = client.post(
        reverse("admin:escala_sabadofechado_delete", args=[fechado.pk]), {"post": "yes"}
    )
    assert apagar.status_code == 403
    assert SabadoFechado.objects.count() == 1
