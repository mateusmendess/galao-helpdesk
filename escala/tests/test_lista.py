import re
from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse

from escala.calculo import Dia
from escala.models import ConfiguracaoEscala, SabadoDuasPessoas, SabadoSemEscala
from fila.models import Ausencia

from .conftest import SABADO

pytestmark = pytest.mark.django_db


def s(k):
    return SABADO + timedelta(weeks=k)


@pytest.fixture
def equipe(django_user_model):
    """Pessoa 1 a Pessoa 7, posicao 1 a 7; a Pessoa 7 sem primeiro nome."""
    return [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test",
            first_name="" if n == 7 else f"Pessoa {n}",
            ordem_escala=n,
        )
        for n in range(1, 8)
    ]


@pytest.fixture
def ligada(equipe, hoje):
    ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=equipe[0])
    hoje(SABADO - timedelta(days=1))
    return equipe


def pagina(client, usuario):
    client.force_login(usuario)
    resposta = client.get(reverse("escala"))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    return html[html.index("<main") : html.index("</main>")]


def texto(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def destaque(html):
    inicio = html.index('<section id="proximo-sabado"')
    return html[inicio : html.index("</section>", inicio)]


def linhas(html):
    """Texto de cada <li> da lista, na ordem (inclusive os do "Ver mais")."""
    return [texto(li) for li in re.findall(r"<li\b.*?</li>", html, flags=re.S)]


def test_atalhos_logo_abaixo_do_proximo_sabado(client, ligada):
    html = pagina(client, ligada[0])

    fim_do_destaque = html.index("</section>", html.index('id="proximo-sabado"'))
    trocas = html.index(">Trocas registradas</a>")
    regras = html.index(">Regras da escala</a>")
    lista = html.index("Próximos sábados")
    assert fim_do_destaque < trocas < regras < lista
    assert lista < html.index("Ver mais sábados ›</a>")
    assert "Trocas registradas ›" not in html and "Regras da escala ›" not in html


def test_destaque_mais_6_e_botao_ver_mais_sabados(client, ligada):
    html = pagina(client, ligada[0])

    assert texto(destaque(html)).startswith("Próximo sábado · 05/12")
    assert [li.split()[0] for li in linhas(html)] == [
        f"{s(k):%d/%m}" for k in range(1, 7)
    ]
    assert "<details" not in html and "Ver mais (" not in html
    assert re.search(
        rf'<a href="{reverse("escala_proximos")}" class="botao-secundario [^"]*">'
        r"Ver mais sábados ›</a>",
        html,
    )


def test_destaque_com_voce_e_turnos(client, ligada):
    html = destaque(pagina(client, ligada[0]))

    assert texto(html) == (
        "Próximo sábado · 05/12 Manhã 08h às 12h Pessoa 1 você "
        "Tarde 13h às 17h sem escala de tarde Trocar de sábado"
    )
    assert re.search(
        r'<span class="[^"]*bg-agua[^"]*text-tinta[^"]*">você</span>', html
    )


def test_destaque_sem_voce_para_outra_pessoa(client, ligada):
    html = destaque(pagina(client, ligada[1]))

    assert "Pessoa 1" in texto(html) and "você" not in html


def test_nome_vazio_mostra_o_email(client, ligada):
    html = pagina(client, ligada[0])

    assert f"{s(6):%d/%m} pessoa7@exemplo.test" in linhas(html)


def test_sabado_com_2_pessoas(client, ligada):
    SabadoDuasPessoas.objects.create(data=s(0))
    SabadoDuasPessoas.objects.create(data=s(1))

    html = pagina(client, ligada[0])

    assert texto(destaque(html)) == (
        "Próximo sábado · 05/12 Manhã 08h às 12h Pessoa 1 você "
        "Tarde 13h às 17h Pessoa 2 Trocar de sábado"
    )
    assert linhas(html)[0] == f"{s(1):%d/%m} Pessoa 3 e Pessoa 4 2 pessoas"
    assert re.search(r'<span class="[^"]*bg-ok-fundo[^"]*text-ok[^"]*">2 pessoas', html)


def test_duas_vagas_com_a_tarde_vazia(client, ligada):
    SabadoDuasPessoas.objects.create(data=s(0))
    for pessoa in ligada[1:]:
        Ausencia.objects.create(usuario=pessoa, inicio=s(0), fim=s(0))

    html = destaque(pagina(client, ligada[0]))

    assert "Tarde 13h às 17h ninguém disponível" in texto(html)
    assert "Ausente, pulado: Pessoa 2, Pessoa 3" in texto(html)


def test_manha_vazia(client, ligada):
    for pessoa in ligada:
        Ausencia.objects.create(usuario=pessoa, inicio=s(0), fim=s(0))

    html = destaque(pagina(client, ligada[0]))

    assert "Manhã 08h às 12h ninguém disponível" in texto(html)


def test_sem_escala_passando_e_sem_passar(client, ligada):
    SabadoSemEscala.objects.create(data=s(1), motivo="feriado", passa_para_proximo=True)
    SabadoSemEscala.objects.create(
        data=s(3), motivo="imprevisto", passa_para_proximo=False
    )

    html = pagina(client, ligada[0])
    lista = linhas(html)

    assert lista[0] == (
        f"{s(1):%d/%m} Sem escala · Feriado "
        f"Quem estava na vez passa para {s(2):%d/%m} sem escala"
    )
    assert lista[1] == f"{s(2):%d/%m} Pessoa 2"
    assert lista[2] == f"{s(3):%d/%m} Sem escala · Imprevisto sem escala"
    assert lista[3] == f"{s(4):%d/%m} Pessoa 4"
    assert re.search(
        r'<span class="[^"]*bg-fundo[^"]*text-ausente[^"]*">sem escala', html
    )


def test_pulados_na_observacao(client, ligada):
    Ausencia.objects.create(usuario=ligada[2], inicio=s(2), fim=s(2))

    lista = linhas(pagina(client, ligada[0]))

    assert lista[1] == f"{s(2):%d/%m} Pessoa 4 Ausente, pulado: Pessoa 3"


def test_menos_sabados_mostra_o_que_ha_e_o_botao(client, ligada):
    poucos = [Dia(data=s(k), manha=ligada[k]) for k in range(4)]
    with mock.patch("escala.views.calendario", return_value=poucos):
        html = pagina(client, ligada[0])

    assert len(linhas(html)) == 3
    assert "<details" not in html and "Ver mais sábados ›" in html


def test_so_o_destaque_sem_lista(client, ligada):
    with mock.patch("escala.views.calendario", return_value=[Dia(data=s(0))]):
        html = pagina(client, ligada[0])

    assert "Próximos sábados" not in html and "<details" not in html


def test_estado_configuracao_invalida(client, ligada):
    ligada[0].is_active = False
    ligada[0].save()

    html = pagina(client, ligada[1])

    assert texto(html) == (
        "O primeiro da fila da configuração não está na escala (está inativo "
        "ou sem posição na escala). Peça a um admin para ajustar em Painel de "
        "administração &gt; Escala de sábado."
    )
    assert 'role="alert"' in html


def test_estado_sem_nenhum_sabado(client, ligada):
    with mock.patch("escala.views.calendario", return_value=[]):
        html = pagina(client, ligada[0])

    assert texto(html).endswith("Nenhum sábado para mostrar ainda.")
    assert "Próximo sábado" not in html


def test_titulo_e_abas_continuam_com_a_lista(client, ligada):
    client.force_login(ligada[0])
    html = client.get(reverse("escala")).content.decode()

    assert "<title>Escala de sábado · Help Desk Equipe</title>" in html
    nav = re.search(r'<nav aria-label="Seções do sistema".*?</nav>', html, flags=re.S)
    assert nav and 'aria-current="page"' in nav.group(0).split("Galão")[1]
    assert "Trocar de sábado" in html and "Trocas registradas" in html
    assert f'href="{reverse("escala_regras")}"' in html
