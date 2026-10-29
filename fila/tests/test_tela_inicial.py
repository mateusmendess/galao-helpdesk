import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from fila.models import Ausencia, Rodada

pytestmark = pytest.mark.django_db

FILA_VAZIA = "Ainda não há ninguém na fila. O admin define a ordem em /admin/."


def tela(client, usuario):
    client.force_login(usuario)
    resposta = client.get(reverse("home"))
    assert resposta.status_code == 200
    return resposta.content.decode()


def linhas_da_fila(conteudo):
    """Texto de cada <li> da fila, sem tags e com espacos normalizados."""
    itens = re.findall(r"<li\b.*?</li>", conteudo, flags=re.S)
    return [" ".join(re.sub(r"<[^>]+>", " ", item).split()) for item in itens]


def test_anonimo_continua_indo_para_o_login(client):
    resposta = client.get(reverse("home"))

    assert resposta.status_code == 302
    assert resposta.url == "/entrar/?next=/"


def test_fila_vazia_mostra_a_mensagem_sem_erro(client, admin_usuario):
    conteudo = tela(client, admin_usuario)

    assert FILA_VAZIA in conteudo
    assert "Rodada 1" in conteudo
    assert "Vez de" not in conteudo
    assert linhas_da_fila(conteudo) == []


def test_admin_ve_a_rodada_a_vez_e_a_fila_com_estados(client, admin_usuario, equipe):
    conteudo = tela(client, admin_usuario)

    assert "Rodada 1" in conteudo
    assert "Módulo 2" not in conteudo
    assert "Vez de" in conteudo
    assert "Pessoa 1" in conteudo
    assert "É a sua vez!" not in conteudo
    assert linhas_da_fila(conteudo) == ["1 Pessoa 1 vez agora"] + [
        f"{n} Pessoa {n} aguardando" for n in range(2, 8)
    ]


def test_estados_aparecem_em_texto_depois_de_trocas(
    client, admin_usuario, equipe, registrar
):
    registrar(equipe[0])
    registrar(equipe[1], executor=equipe[6])

    linhas = linhas_da_fila(tela(client, admin_usuario))

    assert linhas[0] == "1 Pessoa 1 ✓ já trocou"
    # A Pessoa 2 foi coberta pela 7: ja trocou e passa a dever 1.
    assert linhas[1] == "2 Pessoa 2 devendo 1 ✓ já trocou"
    assert linhas[2] == "3 Pessoa 3 vez agora"
    assert linhas[6] == "7 Pessoa 7 aguardando"


def test_quando_a_vez_e_da_pessoa_logada(client, equipe):
    conteudo = tela(client, equipe[0])

    assert "É a sua vez!" in conteudo
    assert "Vez de" not in conteudo
    assert linhas_da_fila(conteudo)[0] == "1 Pessoa 1 (você) vez agora"


def test_quem_nao_e_da_vez_ve_vez_de_e_se_reconhece(client, equipe):
    conteudo = tela(client, equipe[2])

    assert "Vez de" in conteudo
    assert "É a sua vez!" not in conteudo
    assert linhas_da_fila(conteudo)[2] == "3 Pessoa 3 (você) aguardando"


def test_sem_primeiro_nome_aparece_o_email(client, admin_usuario, equipe):
    equipe[0].first_name = ""
    equipe[0].save()

    conteudo = tela(client, admin_usuario)

    assert "pessoa1@exemplo.test" in conteudo
    assert linhas_da_fila(conteudo)[0] == "1 pessoa1@exemplo.test vez agora"


def test_ninguem_disponivel_quando_todos_estao_ausentes(client, admin_usuario, equipe):
    # Ausencias de verdade, em aberto desde hoje.
    hoje = timezone.localdate()
    Ausencia.objects.bulk_create(Ausencia(usuario=u, inicio=hoje) for u in equipe)

    conteudo = tela(client, admin_usuario)

    assert "Ninguém disponível agora." in conteudo
    assert "Rodada 1" in conteudo
    assert "Vez de" not in conteudo
    assert linhas_da_fila(conteudo) == [f"{n} Pessoa {n} ausente" for n in range(1, 8)]


def test_tela_mostra_a_rodada_2_depois_de_fechar(
    client, admin_usuario, equipe, registrar
):
    for pessoa in equipe:
        registrar(pessoa)

    conteudo = tela(client, admin_usuario)

    assert "Rodada 2" in conteudo
    assert linhas_da_fila(conteudo)[0] == "1 Pessoa 1 vez agora"


def test_abrir_a_tela_varias_vezes_abre_uma_rodada_so(client, admin_usuario, equipe):
    for _ in range(3):
        tela(client, admin_usuario)

    assert Rodada.objects.count() == 1


def test_links_e_sair_continuam(client, admin_usuario, equipe):
    painel = 'href="{}"'.format(reverse("admin:index"))
    trocar = 'href="{}"'.format(reverse("password_change"))
    sair = 'action="{}"'.format(reverse("logout"))

    do_admin = tela(client, admin_usuario)
    do_membro = tela(client, equipe[0])

    assert painel in do_admin and painel not in do_membro
    for conteudo in (do_admin, do_membro):
        assert trocar in conteudo
        assert sair in conteudo


def test_troca_de_senha_obrigatoria_continua_valendo(client, equipe):
    equipe[0].precisa_trocar_senha = True
    equipe[0].save()
    client.force_login(equipe[0])

    resposta = client.get(reverse("home"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("password_change")


def consultas_da_tela(client, usuario):
    client.force_login(usuario)
    client.get(reverse("home"))  # a primeira visita abre a rodada
    with CaptureQueriesContext(connection) as consultas:
        assert client.get(reverse("home")).status_code == 200
    return len(consultas)


def test_consultas_nao_crescem_com_o_tamanho_da_fila(
    client, admin_usuario, django_user_model
):
    for n in (1, 2):
        django_user_model.objects.create_user(email=f"p{n}@exemplo.test", ordem=n)
    com_2 = consultas_da_tela(client, admin_usuario)

    for n in range(3, 8):
        django_user_model.objects.create_user(email=f"p{n}@exemplo.test", ordem=n)
    com_7 = consultas_da_tela(client, admin_usuario)

    assert com_2 == com_7
    # 2 do login + 6 da fila (com a conferencia da rodada) + 2 savepoints
    # + 2 do saldo "devendo" + 1 da ultima troca + 1 das ausencias de hoje.
    assert com_7 <= 14


def test_subtitulo_e_so_help_desk(client, membro):
    conteudo = tela(client, membro)

    # So dentro do <header> (o <title> tambem tem o nome): a marca uma vez.
    cabecalho = conteudo[conteudo.index("<header") : conteudo.index("</header>")]
    assert cabecalho.count("Help Desk Equipe") == 1
    assert "Troca do Galão" not in cabecalho
    assert "em construção" not in conteudo
