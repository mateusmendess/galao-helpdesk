from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from escala.calculo import calendario, congelar_passados
from escala.models import (
    ConfiguracaoEscala,
    SabadoDuasPessoas,
    SabadoFechado,
    SabadoSemEscala,
    TrocaSabado,
)
from escala.trocas import (
    DESFACA_A_MAIS_RECENTE,
    ESCALA_MUDOU,
    calendario_com_trocas,
    desfazer_troca,
    pode_desfazer,
    registrar_troca,
    sabados_em,
)
from fila.models import Ausencia

from .conftest import SABADO

pytestmark = pytest.mark.django_db
M, T = "manha", "tarde"


def s(k):
    return SABADO + timedelta(weeks=k)


@pytest.fixture
def equipe(django_user_model, hoje):
    """Pessoa 1 a 7 (posicao 1 a 7); escala de 05/12 com a Pessoa 1 primeiro.
    Hoje: 10 dias antes (sabados s(0)=P1, s(1)=P2, s(2)=P3...)."""
    pessoas = [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem_escala=n
        )
        for n in range(1, 8)
    ]
    ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=pessoas[0])
    hoje(SABADO - timedelta(days=10))
    return pessoas


def manhas(quantos):
    return [item.dia.manha for item in calendario_com_trocas(quantos)]


def erro_de(**kwargs):
    with pytest.raises(ValidationError) as erro:
        registrar_troca(**kwargs)
    return " ".join(erro.value.messages)


def troca(a, da, b, db, por, ta=M, tb=M, **extra):
    return dict(
        pessoa_a=a,
        data_a=da,
        turno_a=ta,
        pessoa_b=b,
        data_b=db,
        turno_b=tb,
        por=por,
        **extra,
    )


# Efeito


def test_troca_vale_nas_duas_datas_no_sentido_certo(equipe):
    p1, p2, p3 = equipe[:3]

    registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))

    itens = calendario_com_trocas(3)
    assert [i.dia.manha for i in itens] == [p3, p2, p1]
    assert [i.antes.manha for i in itens] == [p1, p2, p3]
    assert (itens[0].no_lugar_de(M), itens[2].no_lugar_de(M)) == (p1, p3)
    assert itens[1].no_lugar_de(M) is None and not itens[1].trocado


def test_fila_e_cursor_nao_mudam(equipe, hoje, admin_usuario):
    p1, p3 = equipe[0], equipe[2]
    antes = [(d.data, d.manha, d.cursor_depois) for d in calendario(5)]

    registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))

    assert [(d.data, d.manha, d.cursor_depois) for d in calendario(5)] == antes
    hoje(s(2), time(18))
    congelar_passados()
    assert [f.manha for f in SabadoFechado.objects.order_by("data")] == equipe[:3]


def test_admin_troca_sabado_ja_gravado(equipe, hoje, admin_usuario):
    p1, p2 = equipe[:2]
    hoje(s(1), time(18))

    registrar_troca(**troca(p1, s(0), p2, s(1), por=admin_usuario))

    sabados = sabados_em([s(0), s(1)])
    assert (sabados[s(0)].dono(M), sabados[s(1)].dono(M)) == (p2, p1)
    assert [f.manha for f in SabadoFechado.objects.order_by("data")] == [p1, p2]


# Permissoes


def test_membro_nao_registra_troca_de_terceiros(equipe):
    p1, p3, p5 = equipe[0], equipe[2], equipe[4]

    assert erro_de(**troca(p1, s(0), p3, s(2), por=p5)) == (
        "Você só pode registrar trocas suas."
    )


def test_membro_nao_troca_o_sabado_de_hoje_mas_admin_troca(equipe, hoje, admin_usuario):
    p1, p2 = equipe[:2]
    hoje(s(0), time(8))

    assert "ainda não chegaram" in erro_de(**troca(p1, s(0), p2, s(1), por=p1))
    registrar_troca(**troca(p1, s(0), p2, s(1), por=admin_usuario))


def test_membro_troca_a_partir_de_amanha(equipe, hoje):
    p1, p2 = equipe[:2]
    hoje(s(0) - timedelta(days=1), time(23, 59))

    registrar_troca(**troca(p1, s(0), p2, s(1), por=p1))


def test_emergencia_so_pelo_admin(equipe, admin_usuario):
    p1, p2 = equipe[:2]

    assert erro_de(**troca(p1, s(0), p2, s(1), por=p1, tipo="emergencia")) == (
        "Só um admin registra troca de emergência."
    )
    feita = registrar_troca(
        **troca(p1, s(0), p2, s(1), por=admin_usuario, tipo="emergencia")
    )
    assert feita.tipo == "emergencia"


# Conferencias


def test_dono_atual_errado(equipe):
    p1, p2, p3 = equipe[:3]

    assert erro_de(**troca(p2, s(0), p3, s(2), por=p2)) == ESCALA_MUDOU


def test_turno_vazio(equipe):
    p1, p2 = equipe[:2]

    assert erro_de(**troca(p1, s(0), p2, s(1), por=p1, ta=T)) == (
        "Esse turno não tem ninguém escalado."
    )


def test_sabado_sem_escala(equipe):
    SabadoSemEscala.objects.create(data=s(1))
    p1, p2 = equipe[:2]

    assert erro_de(**troca(p1, s(0), p2, s(1), por=p1)) == (
        "Esse sábado não tem escala para trocar."
    )


def test_mesma_pessoa_e_mesma_data(equipe, admin_usuario):
    p1, p2 = equipe[:2]

    assert erro_de(**troca(p1, s(0), p1, s(1), por=admin_usuario)) == (
        "A troca precisa ser entre duas pessoas diferentes."
    )
    assert erro_de(**troca(p1, s(0), p2, s(0), por=admin_usuario, tb=T)) == (
        "Escolha dois sábados diferentes."
    )


def test_ninguem_duas_vezes_no_mesmo_sabado(equipe):
    # 05/12 com 2 pessoas: Pessoa 1 e Pessoa 2; a Pessoa 2 volta em s(7).
    SabadoDuasPessoas.objects.create(data=s(0))
    p1, p2 = equipe[:2]
    assert calendario(8)[7].manha == p2

    assert erro_de(**troca(p1, s(0), p2, s(7), por=p1)) == (
        "Pessoa 2 já está na escala de 05/12."
    )


def test_ninguem_assume_data_em_que_esta_ausente(equipe):
    p1, p3 = equipe[0], equipe[2]
    Ausencia.objects.create(usuario=p3, inicio=s(0) - timedelta(days=2), fim=s(0))

    assert erro_de(**troca(p1, s(0), p3, s(2), por=p1)) == (
        "Pessoa 3 está ausente em 05/12."
    )


def test_disputa_pelo_mesmo_turno(equipe):
    p1, p2, p3 = equipe[:3]
    registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))

    # Formularios abertos antes: viram a Pessoa 1 em 05/12.
    assert erro_de(**troca(p1, s(0), p3, s(2), por=p1)) == ESCALA_MUDOU
    assert erro_de(**troca(p2, s(1), p1, s(0), por=p2)) == ESCALA_MUDOU
    assert TrocaSabado.objects.count() == 1


# Desfazer


def test_membro_desfaz_ate_a_vespera(equipe, hoje):
    p1, p3 = equipe[0], equipe[2]
    feita = registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))
    hoje(s(0) - timedelta(days=1))

    assert pode_desfazer(feita, p3)
    desfazer_troca(feita, p3)

    feita.refresh_from_db()
    assert (feita.desfeita_por, feita.ativa) == (p3, False)
    assert manhas(3) == equipe[:3]
    assert TrocaSabado.objects.filter(pk=feita.pk).exists()


def test_membro_nao_desfaz_no_dia_nem_troca_de_terceiro(equipe, hoje, admin_usuario):
    p1, p3, p5 = equipe[0], equipe[2], equipe[4]
    feita = registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))

    with pytest.raises(ValidationError, match="Só quem participa"):
        desfazer_troca(feita, p5)
    hoje(s(0), time(8))
    assert not pode_desfazer(feita, p1)
    with pytest.raises(ValidationError, match="prazo"):
        desfazer_troca(feita, p1)

    hoje(s(3))  # admin desfaz sempre, mesmo depois
    desfazer_troca(feita, admin_usuario)
    feita.refresh_from_db()
    assert not feita.ativa


def test_desfazer_comeca_pela_mais_recente(equipe):
    p1, p3, p4 = equipe[0], equipe[2], equipe[3]
    primeira = registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))
    segunda = registrar_troca(**troca(p3, s(0), p4, s(3), por=p3))
    assert manhas(4)[0] == p4

    with pytest.raises(ValidationError) as erro:
        desfazer_troca(primeira, p1)
    assert erro.value.messages == [DESFACA_A_MAIS_RECENTE]

    desfazer_troca(segunda, p4)
    desfazer_troca(primeira, p1)
    assert manhas(4) == equipe[:4]
    with pytest.raises(ValidationError, match="já foi desfeita"):
        desfazer_troca(primeira, p1)


def test_acao_do_admin_desfaz_selecionadas(client, equipe, admin_usuario):
    p1, p3, p4 = equipe[0], equipe[2], equipe[3]
    primeira = registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))
    segunda = registrar_troca(**troca(p3, s(0), p4, s(3), por=p3))
    client.force_login(admin_usuario)
    lista = reverse("admin:escala_trocasabado_changelist")

    so_a_antiga = client.post(
        lista,
        {"action": "desfazer_selecionadas", "_selected_action": [primeira.pk]},
        follow=True,
    )
    mensagens = [str(m) for m in so_a_antiga.context["messages"]]
    assert any(DESFACA_A_MAIS_RECENTE in m for m in mensagens)

    client.post(
        lista,
        {
            "action": "desfazer_selecionadas",
            "_selected_action": [primeira.pk, segunda.pk],
        },
    )
    assert TrocaSabado.objects.filter(desfeita_em__isnull=True).count() == 0


def test_admin_de_trocas_so_consulta(client, equipe, admin_usuario):
    p1, p3 = equipe[0], equipe[2]
    feita = registrar_troca(**troca(p1, s(0), p3, s(2), por=p1))
    client.force_login(admin_usuario)

    lista = client.get(reverse("admin:escala_trocasabado_changelist"))
    assert lista.status_code == 200
    assert "Desfazer trocas selecionadas" in lista.content.decode()
    assert client.get(reverse("admin:escala_trocasabado_add")).status_code == 403
    mudar = reverse("admin:escala_trocasabado_change", args=[feita.pk])
    assert client.post(mudar, {}).status_code == 403
    apagar = reverse("admin:escala_trocasabado_delete", args=[feita.pk])
    assert client.post(apagar, {"post": "yes"}).status_code == 403
    assert TrocaSabado.objects.count() == 1


@pytest.mark.parametrize("quantas", [2, 30])
def test_calendario_com_trocas_numero_fixo_de_consultas(equipe, admin_usuario, quantas):
    for n in range(quantas):
        a, b = n % 7, (n + 1) % 7
        TrocaSabado.objects.create(
            pessoa_a=equipe[a],
            data_a=s(n % 9),
            turno_a=M,
            pessoa_b=equipe[b],
            data_b=s((n + 1) % 9 or 1),
            turno_b=M,
            registrada_por=admin_usuario,
        )
    calendario_com_trocas(9)  # congela o que tiver para congelar

    with CaptureQueriesContext(connection) as consultas:
        calendario_com_trocas(9)

    # Antes do inicio: congelar (1, a configuracao) + calendario (7) + 1 das
    # trocas (com as pessoas juntas), com 2 ou com 30 trocas.
    assert len(consultas) == 9


@pytest.mark.django_db(transaction=True)
def test_migracao_0004_do_zero():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([("escala", None)])
        executor.loader.build_graph()
        executor.migrate([("escala", "0004_troca_sabado")])
        assert "escala_trocasabado" in connection.introspection.table_names()
    finally:
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
