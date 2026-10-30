import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from escala.calculo import calendario
from escala.models import ConfiguracaoEscala, SabadoDuasPessoas
from escala.trocas import aplicar, registrar_troca

from .conftest import SABADO

pytestmark = pytest.mark.django_db
FAIXA = '<div class="bg-tinta text-white">'
BOTAO = {
    "botao-secundario",
    "flex",
    "min-h-12",
    "items-center",
    "justify-center",
    "rounded-[10px]",
    "border-2",
    "border-tinta",
    "bg-white",
    "font-bold",
    "text-tinta",
    "hover:bg-agua",
}


def s(k):
    return SABADO + timedelta(weeks=k)


@pytest.fixture
def equipe(django_user_model, hoje):
    pessoas = [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem_escala=n
        )
        for n in range(1, 8)
    ]
    ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=pessoas[0])
    hoje(SABADO - timedelta(days=10))
    return pessoas


def html_de(client, usuario, nome):
    client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


def linhas(html):
    corpo = html[html.index("<main") : html.index("</main>")]
    return [
        " ".join(re.sub(r"<[^>]+>", " ", li).split())
        for li in re.findall(r"<li\b.*?</li>", corpo, flags=re.S)
    ]


# Pagina "Proximos sabados"


def test_proximos_pede_login(client):
    resposta = client.get(reverse("escala_proximos"))

    assert resposta.status_code == 302 and resposta.url.startswith("/entrar/")


def test_proximos_mostra_26_com_aviso_voce_troca_e_2_pessoas(client, equipe):
    # s(0) Pessoa 1; s(1) Pessoa 2 e Pessoa 3 (2 pessoas); s(2) Pessoa 4.
    p1, p4 = equipe[0], equipe[3]
    SabadoDuasPessoas.objects.create(data=s(1))
    registrar_troca(p1, s(0), "manha", p4, s(2), "manha", por=p1)

    html = html_de(client, p1, "escala_proximos")
    lista = linhas(html)

    assert "<title>Próximos sábados · Help Desk Equipe</title>" in html
    assert (
        'Os sábados mais distantes são <span class="font-bold">previsão</span>: '
        "podem mudar com ausências, sábados sem escala e trocas."
    ) in html
    assert len(lista) == 26
    assert lista[0] == f"{s(0):%d/%m} Pessoa 4 no lugar de Pessoa 1 troca"
    assert lista[1] == f"{s(1):%d/%m} Pessoa 2 e Pessoa 3 2 pessoas"
    assert lista[2] == f"{s(2):%d/%m} Pessoa 1 você no lugar de Pessoa 4 troca"
    com_voce = [li for li in lista if "você" in li]
    assert com_voce and all("Pessoa 1 você" in li for li in com_voce)
    assert "<nav" not in html and f'href="{reverse("escala")}"' in html


def test_aba_continua_sem_voce_na_lista(client, equipe):
    html = html_de(client, equipe[0], "escala")
    lista_da_aba = html[html.index("Próximos sábados") :]

    assert "você" not in lista_da_aba.split("Ver mais sábados")[0]


def test_proximos_sem_configuracao_ou_invalida_volta_para_a_aba(client, equipe):
    equipe[0].is_active = False
    equipe[0].save()
    client.force_login(equipe[1])

    invalida = client.get(reverse("escala_proximos"))
    ConfiguracaoEscala.objects.all().delete()
    sem = client.get(reverse("escala_proximos"))

    assert invalida.status_code == sem.status_code == 302
    assert invalida.url == sem.url == reverse("escala")


@pytest.mark.parametrize("quantos", [7, 26])
def test_numero_fixo_de_consultas(equipe, quantos):
    aplicar(calendario(quantos))

    with CaptureQueriesContext(connection) as consultas:
        dias = aplicar(calendario(quantos))

    assert len(dias) == quantos
    assert len(consultas) == 9


# Botoes e faixa


def test_quatro_botoes_com_a_mesma_classe(client, equipe):
    home = html_de(client, equipe[0], "home")
    aba = html_de(client, equipe[0], "escala")

    botoes = re.findall(
        r'<a href="([^"]+)" class="(botao-secundario [^"]*)">([^<]+)</a>', home + aba
    )
    textos = {texto: set(classes.split()) for _, classes, texto in botoes}
    assert set(textos) == {
        "Ver histórico",
        "Trocas registradas",
        "Regras da escala",
        "Ver mais sábados ›",
    }
    assert all(BOTAO <= classes for classes in textos.values())


@pytest.mark.parametrize(
    "nome", ["home", "escala", "historico", "escala_trocas", "password_change"]
)
def test_faixa_azul_com_e_sem_abas(client, equipe, nome):
    html = html_de(client, equipe[0], nome)
    cabecalho = html[html.index("<header") : html.index("</header>")]

    assert FAIXA in cabecalho
    # A logo usa currentColor e fica branca sobre o azul.
    assert re.search(
        r'<svg class="[^"]*\btext-white\b[^"]*" viewBox="0 0 64 64"', cabecalho
    )
    assert 'fill="currentColor"' in cabecalho
    if "<nav" in cabecalho:
        assert cabecalho.index(FAIXA) < cabecalho.index(
            '<div class="border-b border-borda bg-white">'
        )


def test_menu_branco_com_foco_visivel_sobre_o_azul(client, equipe):
    html = html_de(client, equipe[0], "home")
    summary = re.search(r'<summary class="([^"]*)"', html).group(1).split()

    assert {"border-white/45", "focus-visible:outline-white", "h-11", "w-11"} <= set(
        summary
    )


def test_entrada_sem_a_faixa(client):
    html = client.get(reverse("login")).content.decode()

    assert FAIXA not in html and "<header" not in html
