import pytest
from django.urls import reverse

from fila.models import Rodada, Troca
from fila.regras import de_quem_e_a_vez, rodada_atual

pytestmark = pytest.mark.django_db


def seis_trocam_e_a_7_sai(equipe, registrar):
    for pessoa in equipe[:6]:
        registrar(pessoa)
    equipe[6].is_active = False
    equipe[6].save()


def test_desativar_o_ultimo_que_faltava_fecha_ao_pedir_a_rodada(equipe, registrar):
    seis_trocam_e_a_7_sai(equipe, registrar)

    atual = rodada_atual()

    assert atual.numero == 2
    assert atual.fechada_em is None
    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert Rodada.objects.filter(fechada_em__isnull=True).count() == 1
    assert de_quem_e_a_vez() == equipe[0]


def test_tela_inicial_destrava_e_o_admin_registra_na_rodada_2(
    client, admin_usuario, equipe, registrar
):
    seis_trocam_e_a_7_sai(equipe, registrar)
    client.force_login(admin_usuario)

    conteudo = client.get(reverse("home")).content.decode()
    assert "Rodada 2" in conteudo
    assert "Vez de" in conteudo
    assert "Ninguém disponível agora." not in conteudo

    form = client.get(reverse("admin:fila_troca_add")).context["adminform"].form
    assert form.initial["titular"] == equipe[0].pk
    resposta = client.post(
        reverse("admin:fila_troca_add"),
        {
            "titular": equipe[0].pk,
            "executor": equipe[0].pk,
            "data_hora_0": "2026-10-26",
            "data_hora_1": "09:00:00",
        },
    )
    assert resposta.status_code == 302
    troca = Troca.objects.get(rodada__numero=2)
    assert troca.titular == equipe[0]


def test_ausente_passado_a_rodada_atual_fecha_e_sem_ausentes_nao(equipe, registrar):
    for pessoa in equipe[:6]:
        registrar(pessoa)

    # Sem ausentes a 7 continua exigida: nada fecha.
    assert rodada_atual().numero == 1
    assert de_quem_e_a_vez() == equipe[6]

    # Com a 7 ausente, todos os presentes ja trocaram: fecha.
    assert rodada_atual(ausentes={equipe[6]}).numero == 2
    assert Rodada.objects.get(numero=1).fechada_em is not None


def test_rodada_nova_nao_fecha_ao_ser_lida(equipe, registrar):
    for pessoa in equipe:
        registrar(pessoa)

    for _ in range(3):
        assert rodada_atual().numero == 2
        assert rodada_atual(ausentes=set()).numero == 2

    assert list(Rodada.objects.values_list("numero", flat=True)) == [2, 1]
    assert Rodada.objects.filter(fechada_em__isnull=True).count() == 1


def test_fila_vazia_continua_abrindo_a_rodada_1(admin_usuario):
    assert rodada_atual().numero == 1
    assert rodada_atual().numero == 1
    assert Rodada.objects.count() == 1


def test_de_quem_e_a_vez_repassa_os_ausentes_para_a_conferencia(equipe, registrar):
    for pessoa in equipe[:6]:
        registrar(pessoa)

    assert de_quem_e_a_vez(ausentes={equipe[6]}) == equipe[0]
    assert rodada_atual().numero == 2
