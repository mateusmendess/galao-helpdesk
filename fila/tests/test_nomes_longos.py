import re

import pytest
from django.urls import reverse
from django.utils import timezone

from fila.regras import registrar_troca

pytestmark = pytest.mark.django_db

# O navegador nao roda nos testes: conferimos a classe que faz o nome quebrar
# (overflow-wrap: anywhere) no elemento onde o nome e o conteudo principal.
QUEBRA = "wrap-anywhere"
EMAIL_LONGO = "pessoa.sem.primeiro.nome.com.email.bem.comprido@exemplo.test"
PALAVRA_LONGA = "Pessoadoisnomecompridosemespacosnenhumxx"


@pytest.fixture
def longos(equipe):
    """Pessoa 1 sem primeiro nome (e-mail longo); Pessoa 2 com uma palavra longa."""
    sem_nome, palavra = equipe[0], equipe[1]
    sem_nome.first_name = ""
    sem_nome.email = EMAIL_LONGO
    sem_nome.save()
    palavra.first_name = PALAVRA_LONGA
    palavra.save()
    return sem_nome, palavra


def classes_de(html, comeco_do_texto):
    """Classes do elemento cujo texto comeca com comeco_do_texto."""
    achado = re.search(
        r'<\w+ class="([^"]*)"[^>]*>\s*' + re.escape(comeco_do_texto), html
    )
    assert achado, f"elemento com {comeco_do_texto!r} nao encontrado"
    return achado.group(1).split()


def pagina(client, usuario, nome="home"):
    client.force_login(usuario)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200
    return resposta.content.decode()


def test_inicial_quebra_saudacao_cartao_da_vez_e_ultima_troca(client, longos):
    sem_nome, palavra = longos
    registrar_troca(sem_nome, palavra, palavra)  # a vez passa a ser da Pessoa 2

    html = pagina(client, sem_nome)

    assert QUEBRA in classes_de(html, f"Olá, {EMAIL_LONGO}")
    assert QUEBRA in classes_de(html, PALAVRA_LONGA)  # nome no cartao "Vez de"
    assert QUEBRA in classes_de(html, "Última troca:")


def test_inicial_quebra_o_nome_no_cartao_da_propria_vez(client, longos):
    sem_nome, _ = longos

    html = pagina(client, sem_nome)

    assert "É a sua vez!" in html
    assert QUEBRA in classes_de(html, EMAIL_LONGO)


def test_fila_continua_truncada_e_com_o_nome_completo_no_title(client, longos):
    sem_nome, palavra = longos

    html = pagina(client, palavra)

    for nome in (EMAIL_LONGO, PALAVRA_LONGA):
        span = re.search(
            r'<span class="([^"]*)" title="'
            + re.escape(nome)
            + r'">'
            + re.escape(nome),
            html,
        )
        assert span, nome
        assert "truncate" in span.group(1).split()


def test_registrar_quebra_o_titulo_o_fui_eu_e_o_aviso(client, longos):
    sem_nome, palavra = longos

    html = pagina(client, palavra, "registrar_troca")  # vez da Pessoa 1

    assert QUEBRA in classes_de(html, EMAIL_LONGO)  # "De quem era a vez"
    fui_eu = classes_de(html, f"Fui eu ({PALAVRA_LONGA})")
    assert QUEBRA in fui_eu and "min-w-0" in fui_eu
    assert QUEBRA in classes_de(html, f"Se quem trocou não for {EMAIL_LONGO}")


def test_historico_quebra_as_linhas_da_troca(client, longos):
    sem_nome, palavra = longos
    troca = registrar_troca(sem_nome, palavra, palavra)
    troca.observacao = PALAVRA_LONGA * 2
    troca.save()

    html = pagina(client, sem_nome, "historico")

    assert QUEBRA in classes_de(html, PALAVRA_LONGA)  # "X trocou no lugar de Y"
    data = timezone.localtime(troca.data_hora).strftime("%d/%m")
    assert QUEBRA in classes_de(html, data)  # "data · Rodada · registrada por"
    assert QUEBRA in classes_de(html, "“")


def test_mensagem_do_django_quebra(client, longos):
    sem_nome, palavra = longos
    client.force_login(palavra)

    resposta = client.post(
        reverse("registrar_troca"), {"titular": sem_nome.pk, "quem": "eu"}, follow=True
    )

    html = resposta.content.decode()
    assert (
        QUEBRA
        in re.search(r'<p class="([^"]*)"[^>]*>Troca registrada', html).group(1).split()
    )
