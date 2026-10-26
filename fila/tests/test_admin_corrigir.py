import datetime

import pytest
from django.contrib.admin import site as admin_site
from django.contrib.admin.models import CHANGE, DELETION, LogEntry
from django.contrib.messages import get_messages
from django.urls import reverse

from fila import admin as fila_admin
from fila.models import Rodada, Troca
from fila.regras import (
    MOTIVO_NAO_APAGA,
    TrocaNaoPodeSerApagada,
    apagar_troca,
    de_quem_e_a_vez,
    rodada_atual,
    saldos_devendo,
)

pytestmark = pytest.mark.django_db


def url_alterar(troca):
    return reverse("admin:fila_troca_change", args=[troca.pk])


def url_apagar(troca):
    return reverse("admin:fila_troca_delete", args=[troca.pk])


def corrigir(client, troca, executor, observacao="", **extra):
    dados = {"executor": executor.pk, "observacao": observacao, **extra}
    return client.post(url_alterar(troca), dados)


def apagar(client, troca):
    return client.post(url_apagar(troca), {"post": "yes"})


def mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


def fechar_a_rodada_1(equipe, registrar):
    """Todos trocam: a rodada 1 fecha e a 2 abre vazia. Devolve a ultima troca."""
    for pessoa in equipe:
        ultima = registrar(pessoa)
    return ultima


# 1. Corrigir o executor acerta o "devendo"


def test_corrigir_executor_acerta_o_devendo(client, admin_usuario, equipe, registrar):
    a, b, c = equipe[:3]
    troca = registrar(a, executor=b)
    client.force_login(admin_usuario)
    assert saldos_devendo() == {a.pk: 1}

    assert corrigir(client, troca, a, "foi a propria").status_code == 302
    troca.refresh_from_db()
    assert troca.executor == a
    assert troca.observacao == "foi a propria"
    assert saldos_devendo() == {}

    corrigir(client, troca, c)
    troca.refresh_from_db()
    assert troca.executor == c
    # A volta a dever; B (que nao cobriu mais) some; C fica com credito.
    assert saldos_devendo() == {a.pk: 1}


def test_tela_de_correcao_so_edita_executor_e_observacao(
    client, admin_usuario, equipe, registrar
):
    troca = registrar(equipe[0])
    client.force_login(admin_usuario)

    resposta = client.get(url_alterar(troca))

    assert resposta.status_code == 200
    form = resposta.context["adminform"].form
    assert list(form.fields) == ["executor", "observacao"]
    conteudo = resposta.content.decode()
    assert "Pessoa 1" in conteudo  # titular mostrado pelo nome
    assert "Rodada 1" in conteudo


# 2. Campos fixos ignorados num POST forcado


def test_post_forcado_nao_muda_titular_rodada_data_nem_quem_registrou(
    client, admin_usuario, equipe, registrar
):
    troca = registrar(equipe[0])
    antes = Troca.objects.values().get(pk=troca.pk)
    outra_rodada = Rodada.objects.create(
        numero=99, fechada_em=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    )
    client.force_login(admin_usuario)

    corrigir(
        client,
        troca,
        equipe[0],
        "nova",
        titular=equipe[4].pk,
        rodada=outra_rodada.pk,
        registrada_por=equipe[5].pk,
        data_hora_0="2020-01-01",
        data_hora_1="08:00:00",
    )

    depois = Troca.objects.values().get(pk=troca.pk)
    assert depois["observacao"] == "nova"
    for campo in ("titular_id", "rodada_id", "registrada_por_id", "data_hora"):
        assert depois[campo] == antes[campo]


# 3. Editar com pessoas desativadas depois


def test_corrige_observacao_com_titular_e_executor_desativados(
    client, admin_usuario, equipe, registrar
):
    a, b = equipe[:2]
    troca = registrar(a, executor=b)
    a.is_active = False
    a.save()
    b.is_active = False
    b.save()
    client.force_login(admin_usuario)

    resposta = corrigir(client, troca, b, "corrigida")

    assert resposta.status_code == 302
    troca.refresh_from_db()
    assert troca.observacao == "corrigida"
    assert troca.executor == b


def test_trocar_para_executor_inativo_e_recusado(
    client, admin_usuario, equipe, registrar
):
    troca = registrar(equipe[0])
    equipe[2].is_active = False
    equipe[2].save()
    client.force_login(admin_usuario)

    resposta = corrigir(client, troca, equipe[2])

    assert resposta.status_code == 200
    assert "executor" in resposta.context["adminform"].form.errors
    troca.refresh_from_db()
    assert troca.executor == equipe[0]


# 4. Editar nao fecha nem abre rodada


def test_editar_nao_fecha_rodada_que_ja_estaria_completa(
    client, admin_usuario, equipe, registrar
):
    for pessoa in equipe[:6]:
        troca = registrar(pessoa)
    equipe[6].is_active = False  # a rodada 1 ficou completa sem nova troca
    equipe[6].save()
    client.force_login(admin_usuario)

    corrigir(client, troca, equipe[5], "so a observacao")

    assert list(Rodada.objects.values_list("numero", "fechada_em")) == [(1, None)]


# 5. Apagar caso (a): rodada atual


def test_apagar_troca_da_rodada_atual(client, admin_usuario, equipe, registrar):
    a, b = equipe[:2]
    troca = registrar(a, executor=b)
    client.force_login(admin_usuario)
    assert de_quem_e_a_vez() == b
    assert saldos_devendo() == {a.pk: 1}

    assert client.get(url_apagar(troca)).status_code == 200
    resposta = apagar(client, troca)

    assert resposta.status_code == 302
    assert not Troca.objects.exists()
    assert de_quem_e_a_vez() == a
    assert saldos_devendo() == {}
    assert Rodada.objects.count() == 1


# 6. Apagar caso (b): ultima rodada fechada com a atual vazia


def test_apagar_a_troca_que_fechou_a_rodada_reabre_a_rodada(
    client, admin_usuario, equipe, registrar
):
    ultima = fechar_a_rodada_1(equipe, registrar)
    assert rodada_atual().numero == 2
    client.force_login(admin_usuario)

    assert client.get(url_apagar(ultima)).status_code == 200
    resposta = apagar(client, ultima)

    assert resposta.status_code == 302
    assert "A rodada 1 foi reaberta." in mensagens(resposta)
    assert list(Rodada.objects.values_list("numero", "fechada_em")) == [(1, None)]
    assert not Troca.objects.filter(pk=ultima.pk).exists()
    assert de_quem_e_a_vez() == equipe[6]

    # Registrar de novo fecha a rodada 1 e abre uma nova rodada 2.
    registrar(equipe[6])
    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert rodada_atual().numero == 2


# 7. Negado


def test_nao_apaga_troca_de_rodada_fechada_se_a_atual_ja_tem_troca(
    client, admin_usuario, equipe, registrar
):
    ultima = fechar_a_rodada_1(equipe, registrar)
    registrar(equipe[0])  # rodada 2 com 1 troca
    client.force_login(admin_usuario)

    assert client.get(url_apagar(ultima)).status_code == 403
    assert apagar(client, ultima).status_code == 403
    assert Troca.objects.filter(pk=ultima.pk).exists()
    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert Rodada.objects.count() == 2


def test_nao_apaga_troca_de_duas_rodadas_atras(
    client, admin_usuario, equipe, registrar
):
    antiga = fechar_a_rodada_1(equipe, registrar)
    fechar_a_rodada_1(equipe, registrar)  # fecha a rodada 2; a 3 abre vazia
    assert rodada_atual().numero == 3
    client.force_login(admin_usuario)

    assert client.get(url_apagar(antiga)).status_code == 403
    assert apagar(client, antiga).status_code == 403
    assert Troca.objects.filter(pk=antiga.pk).exists()
    assert Rodada.objects.filter(fechada_em__isnull=True).get().numero == 3


def test_tela_da_troca_antiga_nao_oferece_apagar(
    client, admin_usuario, equipe, registrar
):
    ultima = fechar_a_rodada_1(equipe, registrar)
    registrar(equipe[0])
    client.force_login(admin_usuario)

    resposta = client.get(url_alterar(ultima))

    assert resposta.context["has_delete_permission"] is False
    assert url_apagar(ultima) not in resposta.content.decode()


# 8. A regra e conferida no POST


def test_regra_e_conferida_no_post(client, admin_usuario, equipe, registrar):
    ultima = fechar_a_rodada_1(equipe, registrar)
    client.force_login(admin_usuario)
    assert client.get(url_apagar(ultima)).status_code == 200

    registrar(equipe[0])  # a rodada 2 deixou de estar vazia
    resposta = apagar(client, ultima)

    assert resposta.status_code == 403
    assert Troca.objects.filter(pk=ultima.pk).exists()
    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert Rodada.objects.count() == 2


def test_apagar_troca_reconfere_dentro_da_transacao(equipe, registrar):
    ultima = fechar_a_rodada_1(equipe, registrar)
    registrar(equipe[0])

    with pytest.raises(TrocaNaoPodeSerApagada):
        apagar_troca(ultima)

    assert Troca.objects.filter(pk=ultima.pk).exists()
    assert Rodada.objects.get(numero=1).fechada_em is not None


def test_recusa_dentro_do_post_mostra_erro_e_nao_registra_no_historico(
    client, admin_usuario, equipe, registrar, monkeypatch
):
    # Simula a regra mudando entre a permissao e a exclusao.
    ultima = fechar_a_rodada_1(equipe, registrar)
    registrar(equipe[0])
    monkeypatch.setattr(fila_admin, "pode_apagar_troca", lambda troca: True)
    client.force_login(admin_usuario)

    resposta = apagar(client, ultima)

    assert resposta.status_code == 302
    assert resposta.url == reverse("admin:fila_troca_changelist")
    assert mensagens(resposta) == [f"Não foi possível apagar: {MOTIVO_NAO_APAGA}"]
    assert Troca.objects.filter(pk=ultima.pk).exists()
    assert not LogEntry.objects.filter(action_flag=DELETION).exists()


# 9. Sem acao em massa


def test_nao_ha_acao_de_apagar_selecionadas(client, admin_usuario, equipe, registrar):
    troca = registrar(equipe[0])
    client.force_login(admin_usuario)
    lista = reverse("admin:fila_troca_changelist")

    resposta = client.get(lista)
    assert "delete_selected" not in resposta.content.decode()

    client.post(
        lista,
        {"action": "delete_selected", "_selected_action": [troca.pk], "post": "yes"},
    )
    assert Troca.objects.filter(pk=troca.pk).exists()


# 10. Membro comum e anonimo


@pytest.mark.parametrize("como", ["anonimo", "membro"])
def test_membro_e_anonimo_nao_alteram_nem_apagam(client, equipe, registrar, como):
    troca = registrar(equipe[0])
    if como == "membro":
        client.force_login(equipe[1])

    for url in (url_alterar(troca), url_apagar(troca)):
        for resposta in (client.get(url), client.post(url, {"post": "yes"})):
            assert resposta.status_code == 302
            assert resposta.url.startswith(reverse("admin:login"))
    assert Troca.objects.filter(pk=troca.pk).exists()


# 11. Historico do admin


def test_historico_do_admin_registra_correcao_e_exclusao(
    client, admin_usuario, equipe, registrar
):
    troca = registrar(equipe[0])
    client.force_login(admin_usuario)

    corrigir(client, troca, equipe[0], "corrigida")
    apagar(client, troca)

    acoes = list(
        LogEntry.objects.filter(object_id=str(troca.pk)).values_list(
            "action_flag", "user_id"
        )
    )
    assert (CHANGE, admin_usuario.pk) in acoes
    assert (DELETION, admin_usuario.pk) in acoes


# 12. Adicionar continua igual


def test_adicionar_continua_com_os_campos_de_antes(client, admin_usuario, equipe):
    client.force_login(admin_usuario)

    form = client.get(reverse("admin:fila_troca_add")).context["adminform"].form

    assert list(form.fields) == ["titular", "executor", "data_hora", "observacao"]


def test_sem_objeto_nao_ha_permissao_de_apagar(rf, admin_usuario):
    pedido = rf.get("/")
    pedido.user = admin_usuario
    troca_admin = admin_site.get_model_admin(Troca)

    assert troca_admin.has_delete_permission(pedido) is False
    assert "delete_selected" not in troca_admin.get_actions(pedido)
