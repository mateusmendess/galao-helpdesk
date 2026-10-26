import datetime
import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from fila.models import Ausencia, Rodada, Troca
from fila.regras import rodada_atual

pytestmark = pytest.mark.django_db

UTC = datetime.timezone.utc
BOTAO = 'href="{}"'.format("/trocas/nova/")


def tela(client, usuario, nome="home", **params):
    client.force_login(usuario)
    resposta = client.get(reverse(nome), params)
    assert resposta.status_code == 200
    return resposta.content.decode()


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def itens_de_lista(html):
    return [texto(i) for i in re.findall(r"<li\b.*?</li>", html, flags=re.S)]


def troca_em(admin, titular, executor, quando, observacao=""):
    return Troca.objects.create(
        rodada=rodada_atual(),
        titular=titular,
        executor=executor,
        registrada_por=admin,
        data_hora=quando,
        observacao=observacao,
    )


# Tela inicial


def test_rota_do_historico_tem_o_nome_combinado():
    assert reverse("historico") == "/trocas/"


def test_botao_aparece_quando_ha_vez(client, equipe):
    conteudo = tela(client, equipe[3])

    assert BOTAO in conteudo
    assert "Troquei o galão" in conteudo
    assert 'href="/trocas/"' in conteudo
    assert "Ver histórico" in conteudo


def test_botao_some_quando_so_restam_ausentes(client, admin_usuario, equipe):
    # Ausencias de verdade, em aberto desde hoje.
    hoje = timezone.localdate()
    Ausencia.objects.bulk_create(Ausencia(usuario=u, inicio=hoje) for u in equipe)
    so_ausentes = tela(client, admin_usuario)

    assert "Ninguém disponível agora." in so_ausentes
    assert BOTAO not in so_ausentes
    assert "Troquei o galão" not in so_ausentes


def test_botao_some_com_a_fila_vazia(client, admin_usuario):
    conteudo = tela(client, admin_usuario)

    assert BOTAO not in conteudo


def test_devendo_aparece_so_quando_maior_que_zero(client, equipe, registrar):
    registrar(equipe[0], executor=equipe[1])  # Pessoa 1 deve 1; Pessoa 2 credito

    linhas = itens_de_lista(tela(client, equipe[0]))

    assert linhas[0] == "1 Pessoa 1 (você) devendo 1 ✓ já trocou"
    assert "devendo" not in linhas[1]
    assert sum("devendo" in linha for linha in linhas) == 1


def test_sem_trocas_nao_ha_linha_de_ultima_troca(client, equipe):
    assert "Última troca" not in tela(client, equipe[0])


def test_ultima_troca_normal_no_horario_local(client, equipe, admin_usuario):
    quando = datetime.datetime(2026, 10, 25, 17, 30, tzinfo=UTC)
    troca_em(admin_usuario, equipe[0], equipe[0], quando)

    conteudo = texto(tela(client, equipe[0]))

    assert "Última troca: Pessoa 1 trocou o galão · 25/10 às 14:30" in conteudo


def test_ultima_troca_cobertura_e_a_mais_recente(client, equipe, admin_usuario):
    antes = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    depois = datetime.datetime(2026, 10, 26, 13, 5, tzinfo=UTC)
    troca_em(admin_usuario, equipe[0], equipe[0], antes)
    troca_em(admin_usuario, equipe[1], equipe[6], depois)

    conteudo = texto(tela(client, equipe[0]))

    assert "Última troca: Pessoa 7 trocou no lugar de Pessoa 2 · 26/10 às 10:05" in (
        conteudo
    )
    assert conteudo.count("Última troca") == 1


def test_mensagem_de_sucesso_aparece_na_tela_inicial(client, equipe):
    client.force_login(equipe[0])

    resposta = client.post(
        reverse("registrar_troca"), {"titular": equipe[0].pk, "quem": "eu"}, follow=True
    )

    conteudo = resposta.content.decode()
    assert "Troca registrada: Pessoa 1 trocou o galão." in conteudo
    # Lida uma vez, some na proxima visita.
    assert "Troca registrada" not in client.get(reverse("home")).content.decode()


def test_link_do_painel_continua_so_para_admin(client, equipe, admin_usuario):
    painel = 'href="{}"'.format(reverse("admin:index"))

    assert painel not in tela(client, equipe[0])
    assert painel in tela(client, admin_usuario)


# Historico


def test_historico_vazio(client, equipe):
    conteudo = tela(client, equipe[0], "historico")

    assert "Histórico de trocas" in conteudo
    assert "Nenhuma troca registrada ainda." in conteudo
    assert 'href="{}"'.format(reverse("home")) in conteudo


def test_historico_do_mais_recente_ao_mais_antigo(client, equipe, admin_usuario):
    base = datetime.datetime(2026, 10, 25, 17, 30, tzinfo=UTC)
    troca_em(admin_usuario, equipe[0], equipe[0], base, "galão novo")
    troca_em(
        admin_usuario,
        equipe[1],
        equipe[6],
        base + datetime.timedelta(hours=1),
    )

    itens = itens_de_lista(tela(client, equipe[0], "historico"))

    # Desde o pedido 14: data e hora empilhadas antes da frase, e a rodada
    # no titulo do grupo (fora do cartao).
    assert itens == [
        "25/10 15:30 Pessoa 7 trocou no lugar de Pessoa 2 cobertura "
        "registrada por Pessoa Admin",
        "25/10 14:30 Pessoa 1 trocou registrada por Pessoa Admin “galão novo”",
    ]


def test_etiqueta_cobertura_so_nas_coberturas(client, equipe, registrar):
    registrar(equipe[0])
    registrar(equipe[1], executor=equipe[6])

    itens = itens_de_lista(tela(client, equipe[0], "historico"))

    assert ["cobertura" in item for item in itens] == [True, False]


def criar_31_trocas(equipe, admin_usuario):
    """31 trocas antigas (1 por hora), em rodadas ja fechadas de 7 em 7."""
    base = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    rodadas = [Rodada.objects.create(numero=100 + n, fechada_em=base) for n in range(5)]
    # bulk_create nao chama save(): so enche o historico, sem fechar rodadas.
    Troca.objects.bulk_create(
        Troca(
            rodada=rodadas[n // 7],
            titular=equipe[n % 7],
            executor=equipe[n % 7],
            registrada_por=admin_usuario,
            data_hora=base + datetime.timedelta(hours=n),
            observacao=f"troca {n + 1}",
        )
        for n in range(31)
    )


def test_historico_pagina_em_30(client, equipe, admin_usuario):
    criar_31_trocas(equipe, admin_usuario)

    primeira = tela(client, equipe[0], "historico")
    segunda = tela(client, equipe[0], "historico", pagina=2)

    assert len(itens_de_lista(primeira)) == 30
    assert "“troca 31”" in primeira and "“troca 1”" not in primeira
    assert "Mais antigas" in primeira and "Mais recentes" not in primeira
    assert len(itens_de_lista(segunda)) == 1
    assert "“troca 1”" in segunda
    assert "Mais recentes" in segunda and "Mais antigas" not in segunda


def test_historico_sem_paginacao_com_poucas_trocas(client, equipe, registrar):
    registrar(equipe[0])

    conteudo = tela(client, equipe[0], "historico")

    assert "Mais antigas" not in conteudo
    assert "Mais recentes" not in conteudo


def consultas_do_historico(client, usuario):
    client.force_login(usuario)
    with CaptureQueriesContext(connection) as consultas:
        assert client.get(reverse("historico")).status_code == 200
    return len(consultas)


def test_historico_tem_consultas_constantes(client, equipe, admin_usuario, registrar):
    registrar(equipe[0])
    com_1 = consultas_do_historico(client, admin_usuario)

    criar_31_trocas(equipe, admin_usuario)
    com_32 = consultas_do_historico(client, admin_usuario)

    assert com_1 == com_32


# Admin


def test_admin_mostra_a_ajuda_do_executor(client, admin_usuario, equipe):
    client.force_login(admin_usuario)

    form = client.get(reverse("admin:fila_troca_add")).context["adminform"].form

    assert form.fields["executor"].help_text == (
        "Se foi o próprio titular quem trocou, escolha o mesmo nome do titular. "
        "Escolha outro nome só quando houve cobertura."
    )
