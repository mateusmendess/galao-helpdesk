import re
import struct
import xml.etree.ElementTree as ET

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.urls import reverse

pytestmark = pytest.mark.django_db

TAGS_DO_ICONE = (
    r'<link rel="icon" href="([^"]+)" type="image/svg\+xml">',
    r'<link rel="icon" href="([^"]+)" sizes="32x32">',
    r'<link rel="apple-touch-icon" href="([^"]+)">',
)
ESPERADOS = ("img/favicon.svg", "img/favicon.ico", "img/apple-touch-icon.png")
PNG = b"\x89PNG\r\n\x1a\n"


def arquivo(caminho):
    encontrado = finders.find(caminho)
    assert encontrado, f"{caminho} nao existe em static/"
    with open(encontrado, "rb") as f:
        return f.read()


def lado_do_png(dados):
    assert dados[:8] == PNG
    largura, altura = struct.unpack(">II", dados[16:24])
    return largura, altura


def html_de(client, usuario, nome):
    if usuario is not None:
        client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


def confere_tags(html):
    cabeca = html[: html.index("</head>")]
    for padrao, esperado in zip(TAGS_DO_ICONE, ESPERADOS):
        achou = re.search(padrao, cabeca)
        assert achou, padrao
        href = achou.group(1)
        assert href == static(esperado)
        # O href aponta para um arquivo que existe de verdade em static/.
        assert finders.find(href.removeprefix("/" + settings.STATIC_URL.lstrip("/")))
    assert '<meta name="theme-color" content="#0B4F6C">' in cabeca


def test_tela_de_entrada_tem_o_icone(client):
    confere_tags(html_de(client, None, "login"))


@pytest.mark.parametrize(
    "nome",
    ["home", "registrar_troca", "historico", "password_change", "password_change_done"],
)
def test_telas_logadas_tem_o_icone(client, membro, nome):
    confere_tags(html_de(client, membro, nome))


def test_troca_de_senha_obrigatoria_tem_o_icone(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()

    confere_tags(html_de(client, membro, "password_change"))


def test_favicon_sem_login_vai_para_o_estatico(client):
    resposta = client.get("/favicon.ico")

    assert resposta.status_code == 301
    assert resposta["Location"] == static("img/favicon.ico")
    assert "/entrar/" not in resposta["Location"]


def test_favicon_com_senha_obrigatoria_nao_cai_na_troca_de_senha(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()
    client.force_login(membro)

    resposta = client.get("/favicon.ico")

    assert resposta.status_code == 301
    assert resposta["Location"] == static("img/favicon.ico")


def test_favicon_ico_tem_16_e_32():
    dados = arquivo("img/favicon.ico")
    reservado, tipo, quantidade = struct.unpack("<HHH", dados[:6])
    assert (reservado, tipo) == (0, 1)
    lados = set()
    for n in range(quantidade):
        largura, altura, *_, tamanho, inicio = struct.unpack(
            "<BBBBHHII", dados[6 + 16 * n : 22 + 16 * n]
        )
        imagem = dados[inicio : inicio + tamanho]
        assert len(imagem) == tamanho
        # Cada imagem do .ico e um PNG com o lado declarado no indice.
        assert lado_do_png(imagem) == (largura, altura)
        lados.add(largura)
    assert lados == {16, 32}


@pytest.mark.parametrize(
    "nome, lado",
    [("apple-touch-icon.png", 180)],
)
def test_pngs_com_as_dimensoes_certas(nome, lado):
    assert lado_do_png(arquivo(f"img/{nome}")) == (lado, lado)


def test_svg_valido_com_as_cores_da_identidade():
    raiz = ET.fromstring(arquivo("img/favicon.svg"))

    assert raiz.tag == "{http://www.w3.org/2000/svg}svg"
    assert raiz.get("viewBox") == "0 0 64 64"
    cores = {e.get(attr) for e in raiz.iter() for attr in ("fill", "stroke")}
    # Fundo azul e marca branca, para a aba se destacar em tema claro e escuro.
    assert cores - {None} == {"#0B4F6C", "#fff"}
    fundo = raiz.find("{http://www.w3.org/2000/svg}rect")
    assert fundo.get("rx") == "15" and fundo.get("fill") == "#0B4F6C"
    # O encontro dos dois quadrados fica vazado e mostra o azul.
    marca = next(raiz.iter("{http://www.w3.org/2000/svg}path"))
    assert marca.get("fill-rule") == "evenodd" and marca.get("fill") == "#fff"
    texto = arquivo("img/favicon.svg").decode()
    assert "mask" not in texto and " id=" not in texto
