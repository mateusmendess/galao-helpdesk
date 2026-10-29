import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import get_template
from django.urls import reverse

pytestmark = pytest.mark.django_db

NOME = "Help Desk Equipe"
NOME_ANTIGO = "Troca do Galão"


def titulo(html):
    return re.search(r"<title>(.*?)</title>", html, flags=re.S).group(1).strip()


def html_de(client, usuario, nome):
    if usuario is not None:
        client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


def test_titulo_padrao_do_base_e_o_nome_do_sistema():
    html = get_template("base.html").render({})

    assert titulo(html) == NOME


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("login", f"Entrar · {NOME}"),
        ("home", NOME),
        ("registrar_troca", f"Registrar troca · {NOME}"),
        ("historico", f"Histórico de trocas · {NOME}"),
        ("password_change", f"Trocar senha · {NOME}"),
        ("password_change_done", f"Senha alterada · {NOME}"),
    ],
)
def test_titulo_de_cada_tela_termina_com_o_nome(client, membro, nome, esperado):
    html = html_de(client, None if nome == "login" else membro, nome)

    assert titulo(html) == esperado
    assert titulo(html).endswith(NOME)
    assert NOME_ANTIGO not in titulo(html)


def test_titulo_da_troca_obrigatoria_termina_com_o_nome(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()

    html = html_de(client, membro, "password_change")

    assert titulo(html) == f"Trocar senha · {NOME}"


COM_CABECALHO = (
    "home",
    "registrar_troca",
    "historico",
    "password_change",
    "password_change_done",
)


@pytest.mark.parametrize("nome", COM_CABECALHO)
def test_cabecalho_mostra_o_nome(client, membro, nome):
    html = html_de(client, membro, nome)

    cabecalho = html[html.index("<header") : html.index("</header>")]
    assert re.search(r">\s*Help Desk Equipe\s*<", cabecalho)


def test_entrada_mostra_o_nome(client):
    html = html_de(client, None, "login")

    # So dentro do <main> (o <title> tambem tem o nome): o <h1> e a marca.
    corpo = html[html.index("<main") : html.index("</main>")]
    assert re.findall(r"<h1\b[^>]*>(.*?)</h1>", corpo) == [NOME]
    assert corpo.count(NOME) == 1
    assert NOME_ANTIGO not in corpo


@pytest.mark.parametrize("nome", ["login", "home"])
def test_atalho_do_celular_tem_o_nome(client, membro, nome):
    html = html_de(client, None if nome == "login" else membro, nome)

    cabeca = html[: html.index("</head>")]
    assert f'<meta name="apple-mobile-web-app-title" content="{NOME}">' in cabeca


def test_admin_usa_o_nome_no_cabecalho_e_na_aba(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.get(reverse("admin:index"))

    assert resposta.status_code == 200
    assert resposta.context["site_header"] == NOME
    assert resposta.context["site_title"] == NOME
    html = resposta.content.decode()
    assert f'<div id="site-name"><a href="/admin/">{NOME}</a></div>' in html
    assert titulo(html).endswith(f"| {NOME}")


def test_nome_antigo_nao_sobrou_nos_templates():
    pasta = Path(settings.BASE_DIR) / "templates"
    sobrou = set()
    for arquivo in pasta.rglob("*.html"):
        relativo = arquivo.relative_to(pasta).as_posix()
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if NOME_ANTIGO in linha:
                sobrou.add((relativo, linha.strip()))

    assert sobrou == set()
