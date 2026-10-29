"""Regra "sempre para a frente": quem foi pulado por ausencia nao volta na
mesma rodada; troca na proxima, no lugar de sempre (Pessoa N = ordem N)."""

import datetime
import re

import pytest
from django.urls import reverse
from django.utils import timezone

from fila.models import Ausencia, Troca
from fila.regras import (
    AGUARDANDO,
    AUSENTE,
    PULADO,
    TROCOU,
    VEZ,
    apagar_troca,
    de_quem_e_a_vez,
    rodada_atual,
    saldos_devendo,
    situacao_da_fila,
)

pytestmark = pytest.mark.django_db

HOJE = datetime.date(2026, 11, 10)
AMANHA = HOJE + datetime.timedelta(days=1)
T, V, A, AU, P = TROCOU, VEZ, AGUARDANDO, AUSENTE, PULADO


@pytest.fixture
def dia(monkeypatch):
    """Fixa o "hoje" local; dia(x) muda para outra data."""

    def _dia(data):
        monkeypatch.setattr(timezone, "localdate", lambda *a, **k: data)

    _dia(HOJE)
    return _dia


def estados():
    return [p.estado for p in situacao_da_fila()]


def ausente_hoje(pessoa, fim=HOJE):
    return Ausencia.objects.create(usuario=pessoa, inicio=HOJE, fim=fim)


def test_1_exemplo_obrigatorio(equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[2])
    registrar(p[0])
    registrar(p[1])
    assert de_quem_e_a_vez() == p[3]  # a 3 ausente na vez dela
    registrar(p[3])

    dia(AMANHA)  # a 3 voltou

    assert estados() == [T, T, P, T, V, A, A]
    assert de_quem_e_a_vez() == p[4]
    registrar(p[4])
    assert de_quem_e_a_vez() == p[5]
    registrar(p[5])
    primeira = rodada_atual()
    registrar(p[6])

    # A rodada fecha sem a 3; a nova recomeca na 1 e a 3 troca no lugar dela.
    primeira.refresh_from_db()
    assert primeira.fechada_em is not None
    assert not Troca.objects.filter(rodada=primeira, titular=p[2]).exists()
    assert rodada_atual().numero == 2
    assert estados() == [V, A, A, A, A, A, A]
    registrar(p[0])
    registrar(p[1])
    assert de_quem_e_a_vez() == p[2]
    registrar(p[2])
    assert estados() == [T, T, T, V, A, A, A]


def test_2_volta_antes_de_alguem_depois_trocar_continua_sendo_a_vez(
    equipe, registrar, dia
):
    p = equipe
    ausente_hoje(p[2])
    registrar(p[0])
    registrar(p[1])

    dia(AMANHA)  # voltou antes de a 4 trocar

    assert estados() == [T, T, V, A, A, A, A]
    assert de_quem_e_a_vez() == p[2]


def test_3_quem_continua_ausente_e_ausente_e_nao_pulado(equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[2], fim=None)
    registrar(p[0])
    registrar(p[1])
    registrar(p[3])

    assert estados() == [T, T, AU, T, V, A, A]


def test_4_duas_pessoas_puladas(equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[1])
    ausente_hoje(p[3])
    registrar(p[0])
    registrar(p[2])
    registrar(p[4])

    dia(AMANHA)

    assert estados() == [T, P, T, P, T, V, A]
    registrar(p[5])
    registrar(p[6])
    assert rodada_atual().numero == 2


def test_5_ultima_da_fila_ausente_fecha_sem_ela(equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[6], fim=None)
    for pessoa in p[:6]:
        registrar(pessoa)

    assert rodada_atual().numero == 2
    assert de_quem_e_a_vez() == p[0]


def test_6_todos_ausentes_nao_fecha_e_ninguem_e_a_vez(equipe, dia):
    for pessoa in equipe:
        ausente_hoje(pessoa, fim=None)

    assert de_quem_e_a_vez() is None
    assert estados() == [AU] * 7
    assert rodada_atual().numero == 1


def test_7_ausencia_em_aberto_que_termina_no_meio_da_rodada(equipe, registrar, dia):
    p = equipe
    ausencia = ausente_hoje(p[2], fim=None)
    registrar(p[0])
    registrar(p[1])
    registrar(p[3])

    ausencia.fim = HOJE  # o admin preenche a volta
    ausencia.save()
    dia(AMANHA)

    assert estados() == [T, T, P, T, V, A, A]
    assert de_quem_e_a_vez() == p[4]


def test_8_pessoa_nova_antes_do_ultimo_fica_pulada(
    equipe, registrar, dia, django_user_model
):
    p = equipe
    p[1].ordem = 20  # abre a ordem 2 para a pessoa nova
    p[1].save()
    for pessoa in (p[0], p[2], p[3]):
        registrar(pessoa)

    nova = django_user_model.objects.create_user(
        email="pessoa8@exemplo.test", first_name="Pessoa 8", ordem=2
    )

    situacao = {pos.usuario: pos.estado for pos in situacao_da_fila()}
    assert situacao[nova] == PULADO
    assert de_quem_e_a_vez() == p[4]


def test_9_na_cobertura_quem_define_o_ultimo_e_o_titular(equipe, registrar, dia):
    p = equipe
    registrar(p[0])
    registrar(p[1], executor=p[5])  # a 6 cobriu a vez da 2

    # Se o executor contasse, 3, 4 e 5 ficariam pulados.
    assert estados() == [T, T, V, A, A, A, A]


def test_9b_ultimo_e_a_maior_ordem_mesmo_com_troca_lancada_com_data_antiga(
    equipe, registrar, dia, admin_usuario
):
    # O admin lanca a troca da 4 com a hora de ontem (esqueceu de registrar),
    # depois da troca da 2: a mais recente na hora nao e a de maior ordem.
    p = equipe
    ausente_hoje(p[2])
    rodada = rodada_atual()
    registrar(p[0])
    registrar(p[1])
    Troca.objects.create(
        rodada=rodada,
        titular=p[3],
        executor=p[3],
        registrada_por=admin_usuario,
        data_hora=timezone.now() - datetime.timedelta(days=1),
    )
    dia(AMANHA)

    assert estados() == [T, T, P, T, V, A, A]


def test_10_apagar_a_ultima_troca_reabre_o_estado_anterior(equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[2])
    registrar(p[0])
    registrar(p[1])
    troca_da_4 = registrar(p[3])
    dia(AMANHA)
    assert estados() == [T, T, P, T, V, A, A]

    apagar_troca(troca_da_4)

    assert estados() == [T, T, V, A, A, A, A]
    assert de_quem_e_a_vez() == p[2]


def test_11_saldos_devendo_nao_mudam(equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[2])
    registrar(p[0], executor=p[1])  # a 2 cobriu a 1
    registrar(p[1])
    registrar(p[3])
    dia(AMANHA)
    assert PULADO in estados()

    # Ser pulado nao gera divida; so a cobertura conta.
    assert saldos_devendo() == {p[0].pk: 1}


def tela(client, usuario):
    client.force_login(usuario)
    resposta = client.get(reverse("home"))
    assert resposta.status_code == 200
    return resposta


def linhas(html):
    return [
        " ".join(re.sub(r"<[^>]+>", " ", li).split())
        for li in re.findall(r"<li\b.*?</li>", html, flags=re.S)
    ]


def test_12_barra_e_contagens_com_pulado(client, equipe, registrar, dia):
    p = equipe
    ausente_hoje(p[2])
    registrar(p[0])
    registrar(p[1])
    registrar(p[3])
    dia(AMANHA)

    resposta = tela(client, p[0])

    # Esperados = trocou + vez + aguardando (a pulada nao conta).
    assert (resposta.context["trocaram"], resposta.context["presentes"]) == (3, 6)
    assert resposta.context["segmentos"] == [True] * 3 + [False] * 3
    assert "3 de 6 já trocaram nesta rodada" in resposta.content.decode()


def test_13_texto_volta_na_proxima_rodada_so_para_o_pulado(
    client, equipe, registrar, dia
):
    p = equipe
    ausente_hoje(p[2])
    ausente_hoje(p[5], fim=None)
    registrar(p[0])
    registrar(p[1])
    registrar(p[3])
    dia(AMANHA)

    html = tela(client, p[0]).content.decode()
    fila = linhas(html)

    assert fila[2] == "3 Pessoa 3 volta na próxima rodada"
    assert html.count("volta na próxima rodada") == 1
    assert fila[5] == "6 Pessoa 6 ausente"
    assert re.search(r'<li data-estado="pulado" class="[^"]*">', html)

    # Sem ninguem pulado, o texto nao aparece.
    dia(HOJE)
    assert "volta na próxima rodada" not in tela(client, p[0]).content.decode()
