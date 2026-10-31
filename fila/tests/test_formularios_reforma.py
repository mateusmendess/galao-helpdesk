import re

import pytest
from django.urls import reverse

from conftest import SENHA_DE_TESTE

pytestmark = pytest.mark.django_db

CAMPO = {"min-h-12", "border-[#7f8f97]", "rounded-[10px]"}
PRIMARIO = {"min-h-[52px]", "bg-tinta", "text-white"}
# Senha ficticia derivada da do conftest (nada de senha escrita no teste).
NOVA_SENHA = SENHA_DE_TESTE + "-nova"
SECUNDARIO = {"min-h-12", "border-2", "border-tinta"}
FORM_SAIR = re.compile(
    r'<form method="post" action="/sair/"[^>]*>\s*'
    r'<input type="hidden" name="csrfmiddlewaretoken" value="[^"]+">\s*'
    r"<button[^>]*>\s*Sair\s*</button>\s*</form>"
)


def h1s(html):
    return re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, flags=re.S)


def classes(html, padrao):
    """Classes do primeiro elemento cuja tag de abertura casa com o padrao."""
    achado = re.search(padrao, html, flags=re.S)
    assert achado, padrao
    return set(re.search(r'class="([^"]*)"', achado.group(0)).group(1).split())


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def pagina(client, usuario, nome):
    if usuario is not None:
        client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


# Entrar


def test_login_tem_a_marca_como_h1_unico_e_nenhum_menu(client):
    html = pagina(client, None, "login")

    assert [t.strip() for t in h1s(html)] == ["Help Desk Equipe"]
    assert "<header" not in html
    assert "Menu da conta" not in html and 'action="/sair/"' not in html
    assert "Help Desk" in html


def test_login_campos_e_botao_com_as_classes_novas(client):
    html = pagina(client, None, "login")

    assert CAMPO <= classes(html, r'<input type="text"[^>]*>')
    assert CAMPO <= classes(html, r'<input type="password"[^>]*>')
    assert PRIMARIO <= classes(html, r'<button type="submit"[^>]*>')


def test_login_erro_fica_abaixo_do_subtitulo_com_icone_fora_do_texto(client, membro):
    resposta = client.post(
        reverse("login"),
        {"username": "pessoa1@exemplo.test", "password": "senha-errada"},
    )

    html = resposta.content.decode()
    titulo = html.index("Help Desk Equipe</h1>")
    subtitulo = html.index("Acesso só para quem foi cadastrado.")
    erro = html.index("E-mail, matrícula ou senha incorretos.")
    assert titulo < subtitulo < erro
    assert re.search(
        r'role="alert">\s*<svg[^>]*aria-hidden="true">.*?</svg>\s*'
        r'<div class="min-w-0"><p>E-mail, matrícula ou senha incorretos\.</p>',
        html,
        flags=re.S,
    )


# Registrar troca


def test_registrar_tem_menu_e_h1_proprio(client, equipe):
    html = pagina(client, equipe[0], "registrar_troca")

    assert [t.strip() for t in h1s(html)] == ["Registrar troca"]
    assert re.search(r"<p [^>]*>Help Desk Equipe</p>", html)  # marca como <p>
    assert 'aria-label="Menu da conta"' in html
    assert 'href="{}"'.format(reverse("password_change")) in html
    assert html.count('action="/sair/"') == 1


def test_registrar_opcoes_como_cartoes_marcados_sem_js(client, equipe):
    html = pagina(client, equipe[0], "registrar_troca")

    for valor in ("eu", "outra"):
        rotulo = re.search(
            r'<label class="([^"]*)">\s*<input type="radio" name="quem" value="'
            + valor,
            html,
        )
        assert rotulo, valor
        rotulo = set(rotulo.group(1).split())
        assert {"min-h-[52px]", "has-[:checked]:border-tinta"} <= rotulo
        assert "has-[:checked]:bg-agua" in rotulo
    assert 'value="eu" checked class="h-5 w-5 shrink-0 accent-tinta"' in html


def test_registrar_um_unico_cancelar_ao_lado_do_botao(client, equipe):
    html = pagina(client, equipe[0], "registrar_troca")

    assert texto(html).split().count("Cancelar") == 1
    par = re.search(
        r'<div class="flex gap-2.5">\s*<a href="/"\s+class="([^"]*)">Cancelar</a>\s*'
        r'<button type="submit"\s+class="([^"]*)">\s*Registrar troca',
        html,
    )
    assert par
    assert SECUNDARIO <= set(par.group(1).split())
    assert PRIMARIO <= set(par.group(2).split())


def test_registrar_aviso_com_icone_fora_do_texto(client, equipe):
    html = pagina(client, equipe[1], "registrar_troca")

    assert re.search(
        r'<div class="flex[^"]*bg-aviso-fundo[^"]*">\s*<svg[^>]*aria-hidden="true">'
        r'.*?</svg>\s*<p class="min-w-0 wrap-anywhere">Se quem trocou não for Pessoa 1',
        html,
        flags=re.S,
    )


def test_registrar_widgets_com_as_classes_novas(client, equipe):
    html = pagina(client, equipe[0], "registrar_troca")

    assert CAMPO <= classes(html, r'<select name="executor"[^>]*>')
    assert CAMPO <= classes(html, r'<textarea name="observacao"[^>]*>')


# Trocar senha


def test_senha_obrigatoria_sem_menu_sem_voltar_e_com_sair(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()

    html = pagina(client, membro, "password_change")

    assert [t.strip() for t in h1s(html)] == ["Trocar senha"]
    assert "Menu da conta" not in html and "<summary" not in html
    assert "Voltar" not in html
    sair = FORM_SAIR.search(html)
    assert sair
    assert SECUNDARIO <= classes(sair.group(0), r"<button[^>]*>")
    assert html.count('action="/sair/"') == 1


def test_senha_normal_com_voltar_no_topo_e_sem_sair(client, membro):
    html = pagina(client, membro, "password_change")

    assert 'action="/sair/"' not in html and "<summary" not in html
    voltar = re.search(r'<a href="/" class="([^"]*)">&lsaquo; Voltar</a>', html)
    assert voltar and "min-h-11" in voltar.group(1).split()
    assert html.index("&lsaquo; Voltar") < html.index("Trocar senha</h1>")


def test_campo_com_erro_ganha_a_borda_de_erro(client, membro):
    client.force_login(membro)

    resposta = client.post(
        reverse("password_change"),
        {
            "old_password": "nao-e-a-senha",
            "new_password1": NOVA_SENHA,
            "new_password2": NOVA_SENHA,
        },
    )

    html = resposta.content.decode()
    antiga = classes(html, r'<input type="password" name="old_password"[^>]*>')
    nova = classes(html, r'<input type="password" name="new_password1"[^>]*>')
    assert "border-erro" in antiga and "border-[#7f8f97]" not in antiga
    assert "border-[#7f8f97]" in nova and "border-erro" not in nova
    assert re.search(r'name="old_password"[^>]*aria-invalid="true"', html)


def test_regras_de_senha_em_lista_com_marcadores(client, membro):
    html = pagina(client, membro, "password_change")

    ajuda = re.search(
        r'<div id="ajuda-nova-senha" class="([^"]*)">(.*?)</div>', html, flags=re.S
    )
    assert "[&_ul]:list-disc" in ajuda.group(1).split()
    assert "<ul>" in ajuda.group(2) and ajuda.group(2).count("<li>") >= 3


# Senha alterada


def test_senha_alterada_com_icone_e_botao(client, membro):
    html = pagina(client, membro, "password_change_done")

    assert [t.strip() for t in h1s(html)] == ["Senha alterada"]
    assert re.search(
        r'<div class="[^"]*bg-ok-fundo[^"]*">\s*<svg[^>]*aria-hidden="true">', html
    )
    assert PRIMARIO <= classes(html, r'<a href="/"\s+class="[^"]*">')
    assert "Voltar ao início" in html
    assert "<summary" not in html


# Todas


@pytest.mark.parametrize(
    "nome, logado",
    [
        ("login", False),
        ("home", True),
        ("registrar_troca", True),
        ("password_change", True),
        ("password_change_done", True),
        ("historico", True),
    ],
)
def test_nenhuma_pagina_tem_mais_de_um_h1(client, equipe, nome, logado):
    html = pagina(client, equipe[0] if logado else None, nome)

    assert len(h1s(html)) == 1


def test_fluxo_de_ponta_a_ponta_login_e_registro(client, membro):
    entrada = client.post(
        reverse("login"),
        {"username": "pessoa1@exemplo.test", "password": SENHA_DE_TESTE},
        follow=True,
    )
    assert "Vez de" not in entrada.content.decode()  # a vez e dela
    assert "É a sua vez!" in entrada.content.decode()

    resposta = client.post(
        reverse("registrar_troca"), {"titular": membro.pk, "quem": "eu"}, follow=True
    )
    assert "Troca registrada: Pessoa 1 trocou o galão." in resposta.content.decode()
