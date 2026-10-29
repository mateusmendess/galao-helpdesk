import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

NOME = "Help Desk Equipe"
NAV = re.compile(r'<nav aria-label="Seções do sistema"[^>]*>(.*?)</nav>', flags=re.S)
LINK = re.compile(r"<a\b([^>]*)>(.*?)</a>", flags=re.S)
COM_CABECALHO = (
    "home",
    "escala",
    "registrar_troca",
    "historico",
    "password_change",
    "password_change_done",
)
SEM_ABAS = ("registrar_troca", "historico", "password_change", "password_change_done")


def html_de(client, usuario, nome):
    if usuario is not None:
        client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


def cabecalho(html):
    return html[html.index("<header") : html.index("</header>")]


def marcas(html):
    """Textos do cabecalho que citam o sistema, cada um exatamente como aparece."""
    textos = re.findall(r">([^<]*)<", cabecalho(html))
    return [t.strip() for t in textos if "Help Desk" in t]


def abas(html):
    """[(texto, href, ativa)] dos links do nav das secoes."""
    nav = NAV.search(html)
    assert nav, "sem o nav das secoes"
    return [
        (
            texto.strip(),
            re.search(r'href="([^"]+)"', atributos).group(1),
            'aria-current="page"' in atributos,
        )
        for atributos, texto in LINK.findall(nav.group(1))
    ]


@pytest.mark.parametrize("nome", COM_CABECALHO)
def test_marca_uma_vez_no_cabecalho(client, membro, nome):
    html = html_de(client, membro, nome)

    assert marcas(html) == [NOME]
    assert "Troca do Galão" not in html


def test_marca_uma_vez_na_troca_obrigatoria(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()

    html = html_de(client, membro, "password_change")

    assert marcas(html) == [NOME]
    assert "Troca do Galão" not in html


def test_entrada_tem_o_nome_como_h1_e_nao_tem_o_antigo(client):
    html = html_de(client, None, "login")

    assert re.findall(r"<h1\b[^>]*>(.*?)</h1>", html) == [NOME]
    assert "Troca do Galão" not in html


def test_home_tem_as_abas_com_galao_ativo(client, membro):
    html = html_de(client, membro, "home")

    assert abas(html) == [
        ("Galão", reverse("home"), True),
        ("Escala de sábado", reverse("escala"), False),
    ]
    assert html.count('aria-current="page"') == 1
    # As abas ficam dentro do <header>, depois da linha da marca.
    assert cabecalho(html).index(NOME) < cabecalho(html).index("<nav")


def test_escala_tem_as_abas_com_escala_ativa(client, membro):
    html = html_de(client, membro, "escala")

    assert abas(html) == [
        ("Galão", reverse("home"), False),
        ("Escala de sábado", reverse("escala"), True),
    ]
    assert html.count('aria-current="page"') == 1
    assert "<nav" in cabecalho(html)


def test_aba_ativa_e_inativa_com_as_classes_da_previa(client, membro):
    html = html_de(client, membro, "home")
    nav = NAV.search(html).group(1)
    ativa, inativa = (
        set(re.search(r'class="([^"]*)"', a).group(1).split())
        for a, _ in LINK.findall(nav)
    )

    comum = {"flex-1", "min-h-12", "text-[15px]", "border-b-[3px]", "justify-center"}
    assert comum | {"border-tinta", "font-bold", "text-tinta"} <= ativa
    assert comum | {"border-transparent", "font-medium", "text-texto-suave"} <= inativa
    assert "hover:bg-fundo" in inativa


@pytest.mark.parametrize("nome", SEM_ABAS)
def test_telas_sem_abas(client, membro, nome):
    html = html_de(client, membro, nome)

    assert "<nav" not in html
    assert "Seções do sistema" not in html


def test_troca_obrigatoria_e_entrada_sem_abas(client, membro):
    assert "<nav" not in html_de(client, None, "login")
    membro.precisa_trocar_senha = True
    membro.save()
    assert "<nav" not in html_de(client, membro, "password_change")


@pytest.mark.parametrize("nome", COM_CABECALHO)
def test_rodada_so_na_home(client, membro, nome):
    html = html_de(client, membro, nome)

    tem_rodada = re.search(r">Rodada \d+</span>", cabecalho(html)) is not None
    assert tem_rodada == (nome == "home")
