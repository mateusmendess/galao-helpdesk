import datetime
import re

import pytest
from django.contrib import admin as admin_django
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from fila.models import Ausencia, Rodada, Troca

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
BASE = datetime.datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def pagina(client, usuario, nome="historico", **params):
    client.force_login(usuario)
    resposta = client.get(reverse(nome), params)
    assert resposta.status_code == 200
    return resposta.content.decode()


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def grupos(html):
    """[(titulo, contagem), ...] na ordem da pagina."""
    return [
        (texto(t), texto(c))
        for t, c in re.findall(
            r"<h2[^>]*>\s*<span>(.*?)</span>\s*<span[^>]*>(.*?)</span>", html, re.S
        )
    ]


def cartoes(html):
    return re.findall(r"<li\b.*?</li>", html, flags=re.S)


@pytest.fixture
def pessoas(django_user_model, equipe):
    """A equipe mais 23 contas ficticias (sem senha), para rodadas grandes."""
    extras = [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}"
        )
        for n in range(8, 31)
    ]
    return equipe + extras


def trocas_na_rodada(numero, quem, inicio, admin_usuario, observacao=""):
    rodada = Rodada.objects.create(numero=numero, fechada_em=BASE)
    Troca.objects.bulk_create(
        Troca(
            rodada=rodada,
            titular=pessoa,
            executor=pessoa,
            registrada_por=admin_usuario,
            data_hora=inicio + datetime.timedelta(hours=i),
            observacao=observacao,
        )
        for i, pessoa in enumerate(quem)
    )
    return rodada


# Parte A: historico


def test_grupos_da_rodada_mais_recente_para_a_mais_antiga(
    client, admin_usuario, equipe
):
    trocas_na_rodada(1, equipe[:1], BASE, admin_usuario)
    trocas_na_rodada(2, equipe[:3], BASE + datetime.timedelta(days=1), admin_usuario)

    html = pagina(client, admin_usuario)

    assert grupos(html) == [("Rodada 2", "3 trocas"), ("Rodada 1", "1 troca")]
    assert len(cartoes(html)) == 4


def test_rodada_que_atravessa_a_pagina_mostra_o_total_nas_duas(
    client, admin_usuario, pessoas
):
    # 45 trocas: a rodada 99 (20, mais antigas) e a 100 (25, mais recentes).
    trocas_na_rodada(99, pessoas[:20], BASE, admin_usuario)
    trocas_na_rodada(
        100, pessoas[:25], BASE + datetime.timedelta(days=5), admin_usuario
    )

    primeira = pagina(client, admin_usuario)
    segunda = pagina(client, admin_usuario, pagina=2)

    assert grupos(primeira) == [("Rodada 100", "25 trocas"), ("Rodada 99", "20 trocas")]
    assert grupos(segunda) == [("Rodada 99", "20 trocas")]
    assert len(cartoes(primeira)) == 30 and len(cartoes(segunda)) == 15


def test_cartao_com_data_e_hora_empilhadas_e_sem_rodada(client, admin_usuario, equipe):
    rodada = Rodada.objects.create(numero=7, fechada_em=BASE)
    Troca.objects.create(
        rodada=rodada,
        titular=equipe[1],
        executor=equipe[6],
        registrada_por=admin_usuario,
        data_hora=datetime.datetime(2026, 10, 26, 12, 10, tzinfo=UTC),
        observacao="galão novo",
    )

    html = pagina(client, admin_usuario)
    (cartao,) = cartoes(html)

    hora = re.search(r"<time [^>]*>(.*?)</time>", cartao).group(1)
    assert hora == "26/10<br>09:10"
    assert "tabular-nums" in re.search(r'<time class="([^"]*)"', cartao).group(1)
    assert texto(cartao) == (
        "26/10 09:10 Pessoa 7 trocou no lugar de Pessoa 2 cobertura "
        "registrada por Pessoa Admin “galão novo”"
    )
    assert "Rodada" not in cartao and " às " not in cartao


def test_etiqueta_cobertura_so_nas_coberturas(client, admin_usuario, equipe, registrar):
    registrar(equipe[0])
    registrar(equipe[1], executor=equipe[5])

    itens = cartoes(pagina(client, admin_usuario))

    assert ["cobertura" in item for item in itens] == [True, False]
    etiqueta = re.search(r'<span class="([^"]*)">cobertura</span>', itens[0]).group(1)
    assert {"bg-aviso-fundo", "text-aviso", "border-[#e3b878]"} <= set(etiqueta.split())


def test_voltar_no_topo_menu_e_h1_unico(client, admin_usuario, registrar, equipe):
    registrar(equipe[0])

    html = pagina(client, admin_usuario)

    assert len(re.findall(r"<h1\b", html)) == 1
    assert "Histórico de trocas</h1>" in html
    assert re.search(r"<p [^>]*>Help Desk Equipe</p>", html)
    voltar = re.search(r'<a href="/" class="([^"]*)">&lsaquo; Voltar</a>', html)
    assert voltar and "min-h-11" in voltar.group(1).split()
    assert html.index("&lsaquo; Voltar") < html.index("Histórico de trocas</h1>")
    assert html.count("Voltar") == 1
    assert 'aria-label="Menu da conta"' in html
    assert 'href="{}"'.format(reverse("password_change")) in html
    assert html.count('action="/sair/"') == 1


def botoes_de_pagina(html):
    return re.findall(r'<a href="\?pagina=\d+" class="([^"]*)">([^<]*)</a>', html)


def test_paginacao_com_botoes(client, admin_usuario, pessoas):
    trocas_na_rodada(99, pessoas[:20], BASE, admin_usuario)
    trocas_na_rodada(
        100, pessoas[:25], BASE + datetime.timedelta(days=5), admin_usuario
    )

    primeira = botoes_de_pagina(pagina(client, admin_usuario))
    segunda = botoes_de_pagina(pagina(client, admin_usuario, pagina=2))

    assert [t for _, t in primeira] == ["Mais antigas &rsaquo;"]
    assert [t for _, t in segunda] == ["&lsaquo; Mais recentes"]
    for classes, _ in primeira + segunda:
        assert {"min-h-12", "flex-1", "border-2", "border-tinta"} <= set(
            classes.split()
        )


def test_historico_vazio(client, admin_usuario):
    html = pagina(client, admin_usuario)

    assert "Nenhuma troca registrada ainda." in html
    assert "<h2" not in html and not cartoes(html)


def consultas(client, usuario):
    client.force_login(usuario)
    with CaptureQueriesContext(connection) as feitas:
        client.get(reverse("historico"))
    return len(feitas)


def test_consultas_constantes_com_1_e_30_trocas(client, admin_usuario, pessoas):
    trocas_na_rodada(1, pessoas[:1], BASE, admin_usuario)
    com_1 = consultas(client, admin_usuario)

    trocas_na_rodada(2, pessoas[:29], BASE + datetime.timedelta(days=1), admin_usuario)
    com_30 = consultas(client, admin_usuario)

    # sessao, usuario, contagem da paginacao, pagina e totais por rodada.
    assert com_1 == com_30 == 5


# B1: senha alterada


def test_senha_alterada_com_a_frase_nova(client, membro):
    html = pagina(client, membro, "password_change_done")

    assert "Sua senha foi alterada com sucesso." in html
    assert "Sua nova senha já vale." not in html


# B2: borda de erro no seletor


def select_executor(html):
    return re.search(r'<select name="executor"[^>]*>', html).group(0)


def test_seletor_com_erro_ganha_borda_e_aria_invalid(client, equipe):
    client.force_login(equipe[0])

    resposta = client.post(
        reverse("registrar_troca"), {"titular": equipe[0].pk, "quem": "outra"}
    )

    tag = select_executor(resposta.content.decode())
    assert "border-erro" in tag and "border-[#7f8f97]" not in tag
    assert 'aria-invalid="true"' in tag


def test_seletor_sem_erro_fica_normal(client, equipe):
    tag = select_executor(pagina(client, equipe[0], "registrar_troca"))

    assert "border-[#7f8f97]" in tag and "border-erro" not in tag
    assert "aria-invalid" not in tag


# B3: mensagens do admin no feminino


def mensagens(resposta):
    # So o texto: o Django poe o nome do objeto como link.
    return [re.sub(r"<[^>]+>", "", str(m)) for m in get_messages(resposta.wsgi_request)]


def data_br(data):
    return data.strftime("%d/%m/%Y")


def test_mensagens_da_troca_no_feminino(client, admin_usuario, equipe):
    client.force_login(admin_usuario)
    dados = {
        "titular": equipe[0].pk,
        "executor": equipe[0].pk,
        "data_hora_0": "26/10/2026",
        "data_hora_1": "10:00:00",
    }

    adicionada = client.post(reverse("admin:fila_troca_add"), dados)
    troca = Troca.objects.get()
    alterada = client.post(
        reverse("admin:fila_troca_change", args=[troca.pk]),
        {"executor": equipe[0].pk, "observacao": "ok", "_continue": "1"},
    )
    excluida = client.post(
        reverse("admin:fila_troca_delete", args=[troca.pk]), {"post": "yes"}
    )

    nome = str(troca)
    assert mensagens(adicionada) == [f"A troca “{nome}” foi adicionada com sucesso."]
    assert mensagens(alterada)[-1] == (
        f"A troca “{nome}” foi alterada com sucesso. "
        "Você pode editá-la novamente abaixo."
    )
    assert mensagens(excluida)[-1] == f"A troca “{nome}” foi excluída com sucesso."


def test_mensagens_da_ausencia_no_feminino(client, admin_usuario, equipe):
    client.force_login(admin_usuario)
    hoje = datetime.date(2026, 11, 10)

    adicionada = client.post(
        reverse("admin:fila_ausencia_add"),
        {"usuario": equipe[0].pk, "inicio": data_br(hoje), "_addanother": "1"},
    )
    ausencia = Ausencia.objects.get()
    alterada = client.post(
        reverse("admin:fila_ausencia_change", args=[ausencia.pk]),
        {"usuario": equipe[0].pk, "inicio": data_br(hoje), "fim": data_br(hoje)},
    )
    ausencia.refresh_from_db()
    excluida = client.post(
        reverse("admin:fila_ausencia_delete", args=[ausencia.pk]), {"post": "yes"}
    )

    assert mensagens(adicionada) == [
        "A ausência “Pessoa 1: 10/11/2026 em diante (em aberto)” foi adicionada "
        "com sucesso. Você pode adicionar outra ausência abaixo."
    ]
    assert mensagens(alterada)[-1] == (
        "A ausência “Pessoa 1: 10/11/2026 a 10/11/2026” foi alterada com sucesso."
    )
    assert mensagens(excluida)[-1] == (
        "A ausência “Pessoa 1: 10/11/2026 a 10/11/2026” foi excluída com sucesso."
    )


def test_rodada_usa_o_mesmo_mixin(admin_usuario):
    pedido = RequestFactory().get("/")
    pedido.user = admin_usuario
    pedido.session = {}
    pedido._messages = FallbackStorage(pedido)
    rodada_admin = admin_django.site.get_model_admin(Rodada)

    rodada_admin.message_user(pedido, "O rodada “Rodada 3” foi removido com sucesso.")

    assert [str(m) for m in pedido._messages] == [
        "A rodada “Rodada 3” foi excluída com sucesso."
    ]


def test_mensagens_proprias_e_de_usuario_nao_mudam(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"),
        {
            "email": "pessoa9@exemplo.test",
            "first_name": "Pessoa 9",
            "usable_password": "false",
        },
    )

    assert resposta.status_code == 302
    (mensagem,) = mensagens(resposta)
    assert mensagem.startswith(
        "O usuário “pessoa9@exemplo.test” foi adicionado com sucesso."
    )


# B4: opcao vazia dos seletores de pessoa


def primeiras_opcoes(html, nome):
    select = re.search(rf'<select name="{nome}"[^>]*>(.*?)</select>', html, re.S)
    return re.findall(r'<option value=""[^>]*>([^<]*)</option>', select.group(1))


def test_opcao_vazia_nos_seletores_do_admin(client, admin_usuario, equipe):
    troca = pagina(client, admin_usuario, "admin:fila_troca_add")
    ausencia = pagina(client, admin_usuario, "admin:fila_ausencia_add")

    assert primeiras_opcoes(troca, "titular") == ["Escolha uma pessoa"]
    assert primeiras_opcoes(troca, "executor") == ["Escolha uma pessoa"]
    assert primeiras_opcoes(ausencia, "usuario") == ["Escolha uma pessoa"]
    for html in (troca, ausencia):
        assert "Select an option" not in html
