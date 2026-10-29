import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from fila.models import Ausencia

pytestmark = pytest.mark.django_db

VAZIOS = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "path"}


class _Recorte(HTMLParser):
    """Guarda o HTML de dentro do primeiro elemento que casa com o filtro."""

    def __init__(self, filtro):
        super().__init__(convert_charrefs=False)
        self.filtro = filtro
        self.profundidade = 0
        self.partes = []
        self.achou = False
        self.terminou = False

    def handle_starttag(self, tag, attrs):
        if self.terminou:
            return
        if self.profundidade:
            self.partes.append(self.get_starttag_text())
            if tag not in VAZIOS:
                self.profundidade += 1
        elif self.filtro(tag, dict(attrs)):
            self.achou = True
            self.profundidade = 1

    def handle_startendtag(self, tag, attrs):
        if self.profundidade and not self.terminou:
            self.partes.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if not self.profundidade or self.terminou or tag in VAZIOS:
            return
        self.profundidade -= 1
        if self.profundidade == 0:
            self.terminou = True
        else:
            self.partes.append(f"</{tag}>")

    def handle_data(self, data):
        if self.profundidade and not self.terminou:
            self.partes.append(data)


def recorte(html, filtro):
    parser = _Recorte(filtro)
    parser.feed(html)
    assert parser.achou, "elemento nao encontrado"
    return "".join(parser.partes)


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def tela(client, usuario):
    client.force_login(usuario)
    resposta = client.get(reverse("home"))
    assert resposta.status_code == 200
    return resposta.content.decode()


def cartao(html):
    return recorte(html, lambda tag, a: a.get("id") == "cartao-da-vez")


def menu(html):
    return recorte(html, lambda tag, a: tag == "details")


def itens(html):
    return re.findall(r"<li\b.*?</li>", html, flags=re.S)


# Menu da conta


def test_menu_da_conta_do_membro(client, equipe):
    html = tela(client, equipe[0])
    conteudo = menu(html)

    assert re.search(r'<summary[^>]*aria-label="Menu da conta"', html)
    assert 'href="{}"'.format(reverse("password_change")) in conteudo
    assert "Trocar senha" in conteudo
    assert re.search(
        r'<form method="post" action="/sair/">\s*<input type="hidden" '
        r'name="csrfmiddlewaretoken"',
        conteudo,
    )
    assert "Painel de administração" not in html
    # "Sair" so existe uma vez na pagina, dentro do menu.
    assert html.count('action="/sair/"') == 1
    assert texto(html).split().count("Sair") == 1


def test_menu_da_conta_do_admin_tem_o_painel(client, admin_usuario, equipe):
    conteudo = menu(tela(client, admin_usuario))

    assert 'href="{}"'.format(reverse("admin:index")) in conteudo
    assert "Painel de administração" in conteudo


def test_menu_nao_usa_lista(client, equipe):
    conteudo = menu(tela(client, equipe[0]))

    assert not re.search(r"<(li|ul|ol)\b", conteudo)


# Cartao da vez


def test_botao_e_ultima_troca_ficam_dentro_do_cartao(client, equipe, registrar):
    registrar(equipe[0])

    html = tela(client, equipe[3])
    dentro = cartao(html)

    assert 'href="/trocas/nova/"' in dentro and "Troquei o galão" in dentro
    assert "Última troca:" in dentro
    assert html.count('href="/trocas/nova/"') == 1
    assert texto(html).count("Última troca") == 1


def test_cartao_verde_na_vez_do_proprio_usuario(client, equipe):
    html = tela(client, equipe[0])
    classes = re.search(r'<div id="cartao-da-vez" class="([^"]*)"', html).group(1)

    assert {"bg-ok-fundo", "border-ok", "border-2"} <= set(classes.split())
    assert "É a sua vez!" in cartao(html)


def test_cartao_azul_na_vez_de_outra_pessoa(client, equipe):
    html = tela(client, equipe[3])
    classes = re.search(r'<div id="cartao-da-vez" class="([^"]*)"', html).group(1)

    assert "bg-agua" in classes.split()
    assert "Vez de" in cartao(html)


def test_sem_vez_nao_ha_cartao_nem_botao(client, admin_usuario):
    html = tela(client, admin_usuario)

    assert 'id="cartao-da-vez"' not in html
    assert "já trocaram nesta rodada" not in html


# Progresso da rodada


def progresso(html):
    dentro = cartao(html)
    segmentos = re.findall(r'<span class="h-2 flex-1 rounded-full ([^"]*)">', dentro)
    feitos = sum("bg-tinta" in s for s in segmentos)
    frase = re.search(r"(\d+) de (\d+) já trocaram nesta rodada", dentro)
    return feitos, len(segmentos), (int(frase.group(1)), int(frase.group(2)))


def test_progresso_sem_trocas(client, equipe):
    assert progresso(tela(client, equipe[0])) == (0, 7, (0, 7))


def test_progresso_com_duas_trocas(client, equipe, registrar):
    registrar(equipe[0])
    registrar(equipe[1])

    assert progresso(tela(client, equipe[0])) == (2, 7, (2, 7))


def test_progresso_com_todos_menos_um(client, equipe, registrar):
    for pessoa in equipe[:6]:
        registrar(pessoa)

    assert progresso(tela(client, equipe[0])) == (6, 7, (6, 7))


def test_ausente_fora_do_total_e_quem_ja_trocou_conta_nos_dois(
    client, equipe, registrar
):
    registrar(equipe[0])
    hoje = timezone.localdate()
    Ausencia.objects.create(usuario=equipe[0], inicio=hoje)  # trocou e saiu
    Ausencia.objects.create(usuario=equipe[1], inicio=hoje)  # ausente sem trocar

    assert progresso(tela(client, equipe[3])) == (1, 6, (1, 6))


def test_sem_presentes_nao_ha_barra(client, equipe):
    hoje = timezone.localdate()
    for pessoa in equipe:
        Ausencia.objects.create(usuario=pessoa, inicio=hoje)

    html = tela(client, equipe[0])

    assert "Ninguém disponível agora." in html
    assert "já trocaram nesta rodada" not in html
    assert "h-2 flex-1" not in html


# Fila

MARCADOR = {
    "trocou": {"bg-ok", "text-white"},
    "vez": {"border-4", "border-tinta"},
    "ausente": {"border-dashed", "border-ausente"},
    "aguardando": {"border-2", "border-[#7f8f97]"},
}


def test_marcador_de_cada_estado(client, equipe, registrar):
    registrar(equipe[0])
    Ausencia.objects.create(usuario=equipe[2], inicio=timezone.localdate())

    html = tela(client, equipe[3])

    vistos = set()
    for item in itens(html):
        estado = re.search(r'data-estado="(\w+)"', item).group(1)
        classes = re.search(r'<span class="([^"]*)">\d+</span>', item).group(1)
        assert MARCADOR[estado] <= set(classes.split()), estado
        vistos.add(estado)
    assert vistos == set(MARCADOR)


def test_aria_current_so_na_linha_da_vez(client, equipe, registrar):
    registrar(equipe[0])

    html = tela(client, equipe[3])

    # Fora da fila, so a aba ativa do cabecalho ("page").
    assert html.count('aria-current="true"') == 1
    assert html.count("aria-current") == 2
    assert html.count('aria-current="page"') == 1
    vez = [i for i in itens(html) if 'aria-current="true"' in i]
    assert len(vez) == 1 and 'data-estado="vez"' in vez[0]


def test_nenhuma_li_fora_da_fila(client, admin_usuario, equipe):
    html = tela(client, admin_usuario)

    fila = recorte(html, lambda tag, a: tag == "ol")
    li = re.compile(r"<li\b")
    assert len(li.findall(html)) == len(li.findall(fila)) == 7
    assert not re.search(r"<ul\b", html)


def test_ver_historico_presente(client, equipe):
    html = tela(client, equipe[0])

    link = re.search(r'<a href="/trocas/"[^>]*>\s*Ver histórico\s*</a>', html)
    assert link


def test_home_sem_cartao_centralizado_na_tela_inteira(client, equipe):
    html = tela(client, equipe[0])

    classes = re.search(r'<main class="([^"]*)"', html).group(1).split()
    assert "min-h-screen" not in classes
    assert "justify-center" not in classes
    assert "md:grid-cols-2" in classes


# Mensagens do Django


def test_mensagem_com_icone_fora_do_paragrafo(client, equipe):
    client.force_login(equipe[0])

    resposta = client.post(
        reverse("registrar_troca"), {"titular": equipe[0].pk, "quem": "eu"}, follow=True
    )

    html = resposta.content.decode()
    assert re.search(
        r'<div class="flex[^"]*">\s*<svg[^>]*aria-hidden="true">.*?</svg>\s*'
        r'<p class="[^"]*wrap-anywhere[^"]*" role="status">Troca registrada',
        html,
        flags=re.S,
    )
    paragrafo = re.search(r'<p [^>]*role="status">(.*?)</p>', html, flags=re.S)
    assert "<svg" not in paragrafo.group(1)


# Tokens e consultas


def test_tokens_e_foco_existem_no_css():
    css = (Path(settings.BASE_DIR) / "static" / "css" / "output.css").read_text(
        encoding="utf-8"
    )

    for regra in (
        ".bg-agua{",
        ".text-tinta{",
        ".bg-ok-fundo{",
        ".text-aviso{",
        "--color-tinta:#0b4f6c",
        ":focus-visible{outline:3px solid var(--color-tinta)",
    ):
        assert regra in css, regra


def test_consultas_nao_crescem_com_o_progresso(client, equipe, registrar):
    client.force_login(equipe[0])
    client.get(reverse("home"))
    with CaptureQueriesContext(connection) as sem_trocas:
        client.get(reverse("home"))

    for pessoa in equipe[:4]:
        registrar(pessoa)
    with CaptureQueriesContext(connection) as com_trocas:
        client.get(reverse("home"))

    assert len(sem_trocas) == len(com_trocas) <= 14
