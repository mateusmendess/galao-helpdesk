import pytest
from django.urls import reverse

from fila.models import Rodada, Troca
from fila.regras import rodada_atual

pytestmark = pytest.mark.django_db


def test_membro_comum_nao_entra_no_admin_da_fila(client, equipe):
    client.force_login(equipe[0])

    for nome in ("admin:fila_troca_changelist", "admin:fila_troca_add"):
        resposta = client.get(reverse(nome))
        assert resposta.status_code == 302
        assert resposta.url.startswith(reverse("admin:login"))


def test_admin_abre_as_listas_e_o_formulario(client, admin_usuario, equipe):
    client.force_login(admin_usuario)

    assert client.get(reverse("admin:fila_rodada_changelist")).status_code == 200
    assert client.get(reverse("admin:fila_troca_changelist")).status_code == 200
    formulario = client.get(reverse("admin:fila_troca_add"))
    assert formulario.status_code == 200


def test_formulario_tem_so_os_campos_combinados_e_abre_com_a_vez(
    client, admin_usuario, equipe
):
    client.force_login(admin_usuario)

    form = client.get(reverse("admin:fila_troca_add")).context["adminform"].form

    assert list(form.fields) == ["titular", "executor", "data_hora", "observacao"]
    assert form.initial["titular"] == equipe[0].pk
    assert form.initial["executor"] == equipe[0].pk
    # Escolhas mostram o primeiro nome.
    nomes = [rotulo for _, rotulo in form.fields["titular"].choices]
    assert "Pessoa 1" in nomes


def test_admin_adiciona_troca_com_rodada_e_registrada_por_automaticos(
    client, admin_usuario, equipe
):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:fila_troca_add"),
        {
            "titular": equipe[1].pk,
            "executor": equipe[6].pk,
            "data_hora_0": "2026-10-25",
            "data_hora_1": "10:00:00",
            "observacao": "cobertura combinada",
        },
    )

    assert resposta.status_code == 302
    troca = Troca.objects.get()
    assert troca.rodada == rodada_atual()
    assert troca.registrada_por == admin_usuario
    assert troca.titular == equipe[1]
    assert troca.executor == equipe[6]


def test_admin_recebe_erro_ao_repetir_o_titular(client, admin_usuario, equipe):
    client.force_login(admin_usuario)
    dados = {
        "titular": equipe[0].pk,
        "executor": equipe[0].pk,
        "data_hora_0": "2026-10-25",
        "data_hora_1": "10:00:00",
    }
    client.post(reverse("admin:fila_troca_add"), dados)

    resposta = client.post(reverse("admin:fila_troca_add"), dados)

    assert resposta.status_code == 200
    assert "titular" in resposta.context["adminform"].form.errors
    assert Troca.objects.count() == 1


def test_troca_nao_pode_ser_alterada_nem_apagada(
    client, admin_usuario, equipe, registrar
):
    pessoa, pessoa2 = equipe[:2]
    troca = registrar(pessoa)
    client.force_login(admin_usuario)
    url = reverse("admin:fila_troca_change", args=[troca.pk])

    # Consulta abre (so leitura), mas a alteracao nao grava.
    consulta = client.get(url)
    assert consulta.status_code == 200
    assert consulta.context["has_change_permission"] is False
    client.post(url, {"titular": pessoa2.pk, "executor": pessoa2.pk})
    troca.refresh_from_db()
    assert troca.titular == pessoa

    apagar = client.post(
        reverse("admin:fila_troca_delete", args=[troca.pk]), {"post": "yes"}
    )
    assert apagar.status_code == 403
    assert Troca.objects.filter(pk=troca.pk).exists()


def test_rodada_nao_pode_ser_adicionada_alterada_nem_apagada(client, admin_usuario):
    rodada = rodada_atual()
    client.force_login(admin_usuario)

    assert client.get(reverse("admin:fila_rodada_add")).status_code == 403
    consulta = client.get(reverse("admin:fila_rodada_change", args=[rodada.pk]))
    assert consulta.status_code == 200
    assert consulta.context["has_change_permission"] is False
    apagar = client.post(
        reverse("admin:fila_rodada_delete", args=[rodada.pk]), {"post": "yes"}
    )
    assert apagar.status_code == 403
    assert Rodada.objects.filter(pk=rodada.pk).exists()
