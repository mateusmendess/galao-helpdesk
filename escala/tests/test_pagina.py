import re
from datetime import date, timedelta

import pytest
from django.urls import reverse

from escala.models import ConfiguracaoEscala

from .conftest import SABADO

pytestmark = pytest.mark.django_db


def texto_do_cartao(client, usuario):
    client.force_login(usuario)
    resposta = client.get(reverse("escala"))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    corpo = html[html.index("<main") : html.index("</main>")]
    return " ".join(re.sub(r"<[^>]+>", " ", corpo).split())


@pytest.fixture
def configurada(django_user_model):
    primeiro = django_user_model.objects.create_user(
        email="pessoa2@exemplo.test", first_name="Pessoa 2", ordem_escala=1
    )
    return ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=primeiro)


def test_anonimo_vai_para_a_entrada(client):
    resposta = client.get(reverse("escala"))

    assert resposta.status_code == 302
    assert resposta.url == "/entrar/?next=/escala/"


def test_quem_precisa_trocar_a_senha_vai_para_a_troca(client, membro):
    membro.precisa_trocar_senha = True
    membro.save()
    client.force_login(membro)

    resposta = client.get(reverse("escala"))

    assert resposta.status_code == 302
    assert resposta.url == reverse("password_change")


def test_post_devolve_405(client, membro):
    client.force_login(membro)

    assert client.post(reverse("escala")).status_code == 405


def test_head_responde(client, membro):
    client.force_login(membro)

    assert client.head(reverse("escala")).status_code == 200


def test_titulo(client, membro):
    client.force_login(membro)

    html = client.get(reverse("escala")).content.decode()

    assert "<title>Escala de sábado · Help Desk Equipe</title>" in html


def test_sem_configuracao(client, membro, hoje):
    texto = texto_do_cartao(client, membro)

    assert texto == (
        "A escala de sábado ainda não foi ligada. Por enquanto a equipe segue "
        "a planilha. Quando o admin ligar a escala, os sábados aparecem aqui."
    )


def test_antes_do_inicio_mostra_a_data(client, membro, hoje, configurada):
    hoje(SABADO - timedelta(days=1))

    texto = texto_do_cartao(client, membro)

    assert texto == (
        "A escala começa em 05/12/2026. Até lá vale a planilha. "
        "A lista dos sábados aparece aqui a partir dessa data."
    )


@pytest.mark.parametrize("dia", [SABADO, date(2027, 1, 20)])
def test_no_inicio_ou_depois_esta_ligada(client, membro, hoje, configurada, dia):
    hoje(dia)

    texto = texto_do_cartao(client, membro)

    assert texto == (
        "A escala de sábado está ligada. A lista dos sábados aparece aqui em breve."
    )


def test_um_cartao_sem_botao_nem_link(client, membro, hoje):
    client.force_login(membro)
    html = client.get(reverse("escala")).content.decode()
    corpo = html[html.index("<main") : html.index("</main>")]

    assert 'class="mx-auto w-full max-w-md px-4 py-4 md:max-w-4xl"' in html
    assert corpo.count("rounded-[14px] border border-borda bg-white p-4") == 1
    assert "<a " not in corpo and "<button" not in corpo and "<form" not in corpo
    # O <h1> e o do cabecalho (marca_p nao).
    assert re.findall(r"<h1\b[^>]*>(.*?)</h1>", html) == ["Help Desk Equipe"]
