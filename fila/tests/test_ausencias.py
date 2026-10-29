import datetime
import re

import pytest
from django.contrib.admin import site as admin_site
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from fila.models import FIM_ANTES_DO_INICIO, Ausencia, Rodada
from fila.regras import (
    ausencias_de_hoje,
    ausentes_hoje,
    de_quem_e_a_vez,
    rodada_atual,
    saldos_devendo,
)

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
HOJE = datetime.date(2026, 11, 10)


def d(dia, mes=11):
    return datetime.date(2026, mes, dia)


@pytest.fixture
def dia(monkeypatch):
    """Fixa o "hoje" local de todo o sistema; dia(x) muda para outra data."""

    def _dia(data):
        monkeypatch.setattr(timezone, "localdate", lambda *a, **k: data)

    _dia(HOJE)
    return _dia


def nova(usuario, inicio, fim=None):
    return Ausencia(usuario=usuario, inicio=inicio, fim=fim)


def erros(ausencia):
    with pytest.raises(ValidationError) as erro:
        ausencia.full_clean()
    return erro.value.message_dict


# 1. Modelo


def test_fim_antes_do_inicio_e_recusado_no_clean(equipe):
    assert erros(nova(equipe[0], d(10), d(9))) == {"fim": [FIM_ANTES_DO_INICIO]}


def test_fim_antes_do_inicio_e_recusado_pelo_banco(equipe):
    with pytest.raises(IntegrityError), transaction.atomic():
        Ausencia.objects.create(usuario=equipe[0], inicio=d(10), fim=d(9))


def test_fim_vazio_e_fim_igual_ao_inicio_sao_aceitos(equipe):
    nova(equipe[0], d(10)).full_clean()
    nova(equipe[1], d(10), d(10)).full_clean()


# 2. Sobreposicao

COM_FIM = (
    "Esta pessoa já tem uma ausência neste período (10/11 a 20/11). "
    "Ajuste a ausência existente em vez de criar outra."
)
EM_ABERTO = (
    "Esta pessoa já tem uma ausência neste período (10/11 em diante, em aberto). "
    "Preencha o fim da ausência anterior antes de cadastrar outra."
)


@pytest.mark.parametrize(
    "inicio, fim",
    [
        (d(12), d(15)),  # dentro
        (d(5), d(12)),  # cruza o inicio
        (d(18), d(25)),  # cruza o fim
        (d(20), d(22)),  # comeca no ultimo dia
        (d(1), d(10)),  # termina no primeiro dia
        (d(5), d(25)),  # cobre inteira
        (d(5), None),  # em aberto cobrindo a existente
        (d(20), None),  # em aberto a partir do ultimo dia
    ],
)
def test_sobreposicao_com_periodo_fechado_e_bloqueada(equipe, inicio, fim):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10), fim=d(20))

    assert erros(nova(equipe[0], inicio, fim)) == {"__all__": [COM_FIM]}


@pytest.mark.parametrize("inicio, fim", [(d(21), d(25)), (d(1), d(9)), (d(21), None)])
def test_periodos_vizinhos_sao_permitidos(equipe, inicio, fim):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10), fim=d(20))

    nova(equipe[0], inicio, fim).full_clean()


def test_ausencia_em_aberto_bloqueia_novas_depois_dela(equipe):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10))

    assert erros(nova(equipe[0], d(15), d(16))) == {"__all__": [EM_ABERTO]}
    assert erros(nova(equipe[0], d(10), d(10))) == {"__all__": [EM_ABERTO]}
    nova(equipe[0], d(5), d(9)).full_clean()  # antes dela: tudo bem


def test_outra_pessoa_nao_e_afetada(equipe):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10))

    nova(equipe[1], d(12), d(15)).full_clean()


def test_editar_a_propria_ausencia_nao_conflita_consigo(equipe):
    ausencia = Ausencia.objects.create(usuario=equipe[0], inicio=d(10))

    ausencia.fim = d(20)
    ausencia.full_clean()
    ausencia.inicio = d(8)
    ausencia.full_clean()


# 3. ausentes_hoje


@pytest.mark.parametrize(
    "hoje, ausente",
    [
        (d(9), False),  # dia anterior ao inicio
        (d(10), True),  # primeiro dia
        (d(11), True),  # meio
        (d(12), True),  # ultimo dia (fim inclusivo)
        (d(13), False),  # dia seguinte ao fim: voltou
    ],
)
def test_periodo_vale_do_inicio_ao_fim_inclusive(equipe, hoje, ausente):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10), fim=d(12))

    assert (equipe[0] in ausentes_hoje(hoje)) is ausente


def test_em_aberto_vale_do_inicio_em_diante(equipe):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10))

    assert equipe[0] not in ausentes_hoje(d(9))
    assert equipe[0] in ausentes_hoje(d(10))
    assert equipe[0] in ausentes_hoje(datetime.date(2027, 6, 1))


def test_futura_e_encerrada_nao_contam(equipe):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(20), fim=d(25))
    Ausencia.objects.create(usuario=equipe[1], inicio=d(1), fim=d(5))

    assert ausentes_hoje(d(10)) == set()


def test_duas_pessoas_ausentes_ao_mesmo_tempo(equipe):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10), fim=d(12))
    Ausencia.objects.create(usuario=equipe[3], inicio=d(11))

    assert ausentes_hoje(d(11)) == {equipe[0], equipe[3]}
    assert ausencias_de_hoje(d(11)) == {equipe[0]: d(12), equipe[3]: None}


def test_ausencias_de_hoje_faz_uma_consulta(equipe, django_assert_num_queries):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10))
    Ausencia.objects.create(usuario=equipe[1], inicio=d(10))

    with django_assert_num_queries(1):
        # O nome de cada pessoa ja vem junto (sem consulta por pessoa).
        nomes = sorted(u.first_name for u in ausencias_de_hoje(d(10)))

    assert nomes == ["Pessoa 1", "Pessoa 2"]


def test_hoje_e_a_data_local_e_nao_a_utc(equipe, monkeypatch):
    # 26/10 01:00 em UTC ainda e 25/10 22:00 em Sao Paulo.
    agora = datetime.datetime(2026, 10, 26, 1, 0, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: agora)
    Ausencia.objects.create(usuario=equipe[0], inicio=d(25, 10), fim=d(25, 10))
    Ausencia.objects.create(usuario=equipe[1], inicio=d(26, 10), fim=d(26, 10))

    assert ausentes_hoje() == {equipe[0]}


# 4. Fila


def test_ausente_na_vez_e_pulado(equipe, dia):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(9), fim=d(11))

    assert de_quem_e_a_vez() == equipe[1]


def test_rodada_fecha_quando_os_presentes_trocam(equipe, registrar, dia):
    Ausencia.objects.create(usuario=equipe[2], inicio=d(1))
    for pessoa in equipe:
        if pessoa != equipe[2]:
            registrar(pessoa)

    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert rodada_atual().numero == 2


def test_ao_voltar_fica_pulada_e_troca_na_proxima_rodada(equipe, registrar, dia):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(9), fim=HOJE)
    for pessoa in equipe[1:6]:
        registrar(pessoa)
    assert de_quem_e_a_vez() == equipe[6]

    dia(HOJE + datetime.timedelta(days=1))  # a ausencia acabou ontem

    # Sempre para a frente: a ordem 1 nao volta nesta rodada.
    assert de_quem_e_a_vez() == equipe[6]
    registrar(equipe[6])
    # A rodada fecha sem ela; na proxima, ela troca no lugar de sempre.
    assert rodada_atual().numero == 2
    assert de_quem_e_a_vez() == equipe[0]


# 5. Divida


def test_ausencia_nao_cria_divida(equipe, registrar, dia):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(1))
    for pessoa in equipe[1:]:
        registrar(pessoa)

    assert saldos_devendo() == {}


def test_divida_antiga_continua_durante_a_ausencia(equipe, registrar, dia):
    registrar(equipe[0], executor=equipe[1])
    Ausencia.objects.create(usuario=equipe[0], inicio=d(1))

    assert saldos_devendo() == {equipe[0].pk: 1}


def test_cobertura_de_quem_esta_presente_continua_gerando_divida(
    equipe, registrar, dia
):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(1))

    registrar(equipe[1], executor=equipe[3])

    assert saldos_devendo() == {equipe[1].pk: 1}


# 6. Todos ausentes


def test_todos_ausentes_nao_fecha_nem_cria_rodada(client, equipe, admin_usuario, dia):
    for pessoa in equipe:
        Ausencia.objects.create(usuario=pessoa, inicio=d(1))
    client.force_login(admin_usuario)

    for _ in range(3):
        conteudo = client.get(reverse("home")).content.decode()

    assert "Ninguém disponível agora." in conteudo
    assert list(Rodada.objects.values_list("numero", "fechada_em")) == [(1, None)]


def test_quem_resta_ausente_fecha_uma_vez_so(client, equipe, registrar, dia):
    for pessoa in equipe[:3]:
        registrar(pessoa)
    for pessoa in equipe[3:]:
        Ausencia.objects.create(usuario=pessoa, inicio=d(1))
    client.force_login(equipe[0])

    for _ in range(3):
        client.get(reverse("home"))

    assert list(Rodada.objects.values_list("numero", flat=True)) == [2, 1]
    assert de_quem_e_a_vez() == equipe[0]


# 7. Tela inicial


def linha(client, usuario, ordem):
    client.force_login(usuario)
    html = client.get(reverse("home")).content.decode()
    itens = re.findall(r"<li\b.*?</li>", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", itens[ordem - 1]).split())


def test_tela_mostra_ausente_ate_a_data_de_fim(client, equipe, dia):
    Ausencia.objects.create(usuario=equipe[1], inicio=d(9), fim=d(14))

    assert linha(client, equipe[3], 2) == "2 Pessoa 2 ausente até 14/11"
    assert linha(client, equipe[3], 1) == "1 Pessoa 1 vez agora"
    assert linha(client, equipe[3], 3) == "3 Pessoa 3 aguardando"


def test_tela_mostra_so_ausente_sem_fim(client, equipe, dia):
    Ausencia.objects.create(usuario=equipe[1], inicio=d(9))

    assert linha(client, equipe[3], 2) == "2 Pessoa 2 ausente"


def test_quem_ja_trocou_continua_ja_trocou_mesmo_ausente(
    client, equipe, registrar, dia
):
    registrar(equipe[0])
    Ausencia.objects.create(usuario=equipe[0], inicio=HOJE)

    assert linha(client, equipe[3], 1) == "1 Pessoa 1 ✓ já trocou"


def test_vez_de_mostra_a_proxima_presente(client, equipe, dia):
    Ausencia.objects.create(usuario=equipe[0], inicio=HOJE)
    client.force_login(equipe[3])

    conteudo = client.get(reverse("home")).content.decode()

    assert "Vez de" in conteudo
    assert linha(client, equipe[3], 2) == "2 Pessoa 2 vez agora"


def test_ausencia_futura_nao_aparece_na_tela(client, equipe, dia):
    Ausencia.objects.create(usuario=equipe[1], inicio=d(20))

    assert linha(client, equipe[3], 2) == "2 Pessoa 2 aguardando"


# 8. Admin


def data_br(data):
    return data.strftime("%d/%m/%Y")


def test_admin_adiciona_altera_e_apaga_com_historico(
    client, admin_usuario, equipe, dia
):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:fila_ausencia_add"),
        {"usuario": equipe[0].pk, "inicio": data_br(d(9)), "fim": ""},
    )
    assert resposta.status_code == 302
    ausencia = Ausencia.objects.get()
    assert ausencia.fim is None

    url = reverse("admin:fila_ausencia_change", args=[ausencia.pk])
    resposta = client.post(
        url, {"usuario": equipe[0].pk, "inicio": data_br(d(9)), "fim": data_br(d(12))}
    )
    assert resposta.status_code == 302
    ausencia.refresh_from_db()
    assert ausencia.fim == d(12)

    apagar = reverse("admin:fila_ausencia_delete", args=[ausencia.pk])
    assert client.post(apagar, {"post": "yes"}).status_code == 302
    assert not Ausencia.objects.exists()

    acoes = set(
        LogEntry.objects.filter(object_id=str(ausencia.pk)).values_list(
            "action_flag", flat=True
        )
    )
    assert acoes == {ADDITION, CHANGE, DELETION}


@pytest.mark.parametrize(
    "fim_existente, mensagem", [(None, EM_ABERTO), (d(20), COM_FIM)]
)
def test_admin_mostra_os_erros_de_sobreposicao(
    client, admin_usuario, equipe, fim_existente, mensagem
):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(10), fim=fim_existente)
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:fila_ausencia_add"),
        {"usuario": equipe[0].pk, "inicio": data_br(d(15)), "fim": data_br(d(16))},
    )

    assert resposta.status_code == 200
    assert resposta.context["adminform"].form.non_field_errors() == [mensagem]
    assert Ausencia.objects.count() == 1


def test_admin_mostra_o_erro_de_fim_antes_do_inicio(client, admin_usuario, equipe):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:fila_ausencia_add"),
        {"usuario": equipe[0].pk, "inicio": data_br(d(15)), "fim": data_br(d(14))},
    )

    assert resposta.context["adminform"].form.errors["fim"] == [FIM_ANTES_DO_INICIO]
    assert not Ausencia.objects.exists()


def test_admin_situacao_calculada(equipe, dia):
    situacao = admin_site.get_model_admin(Ausencia).situacao

    assert situacao(nova(equipe[0], d(9), d(11))) == "ausente hoje"
    assert situacao(nova(equipe[0], HOJE)) == "ausente hoje"
    assert situacao(nova(equipe[0], d(11))) == "futura"
    assert situacao(nova(equipe[0], d(1), d(9))) == "encerrada"


def test_admin_seletor_de_pessoa(client, admin_usuario, equipe):
    equipe[6].is_active = False
    equipe[6].save()
    client.force_login(admin_usuario)

    form = client.get(reverse("admin:fila_ausencia_add")).context["adminform"].form
    opcoes = list(form.fields["usuario"].queryset)
    assert opcoes == equipe[:6]  # ativos da fila, sem admin e sem inativo
    assert "Pessoa 1" in [rotulo for _, rotulo in form.fields["usuario"].choices]

    ausencia = Ausencia.objects.create(usuario=equipe[6], inicio=d(1))
    url = reverse("admin:fila_ausencia_change", args=[ausencia.pk])
    form = client.get(url).context["adminform"].form
    assert equipe[6] in form.fields["usuario"].queryset


@pytest.mark.parametrize("como", ["anonimo", "membro"])
def test_membro_e_anonimo_nao_entram(client, equipe, como):
    ausencia = Ausencia.objects.create(usuario=equipe[0], inicio=d(1))
    if como == "membro":
        client.force_login(equipe[1])

    for url in (
        reverse("admin:fila_ausencia_changelist"),
        reverse("admin:fila_ausencia_add"),
        reverse("admin:fila_ausencia_change", args=[ausencia.pk]),
    ):
        resposta = client.get(url)
        assert resposta.status_code == 302
        assert resposta.url.startswith(reverse("admin:login"))


# 9. Ausente continua usando o sistema


def test_ausente_entra_e_registra_troca(client, equipe, dia):
    Ausencia.objects.create(usuario=equipe[0], inicio=d(1))
    client.force_login(equipe[0])

    assert client.get(reverse("home")).status_code == 200
    resposta = client.post(
        reverse("registrar_troca"), {"titular": equipe[1].pk, "quem": "eu"}
    )

    assert resposta.status_code == 302
    troca = equipe[1].trocas_como_titular.get()
    assert troca.executor == equipe[0]


def test_texto_da_ausencia(equipe):
    assert str(nova(equipe[0], d(10), d(12))) == "Pessoa 1: 10/11/2026 a 12/11/2026"
    assert str(nova(equipe[0], d(10))) == "Pessoa 1: 10/11/2026 em diante (em aberto)"
