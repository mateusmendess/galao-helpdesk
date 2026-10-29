import re
from datetime import timedelta
from html import unescape

import pytest
from django.urls import reverse

from escala.calculo import congelar_passados
from escala.models import ConfiguracaoEscala, TrocaSabado

from .conftest import SABADO

pytestmark = pytest.mark.django_db

REGRAS = [
    "1. Revezamento em dois turnos seguindo a tabela.",
    (
        "4. Sábado feriado: quem estava escalado passa automaticamente para o "
        "próximo sábado."
    ),
    (
        "5. Trabalhar no domingo para resolver demanda NÃO influencia a escala "
        "(não conta como sábado cumprido)."
    ),
    "6. Convocação para domingo não influencia a escala.",
    (
        "7. Substituição do dia é permitida se: 7.1 combinada previamente com a"
        " outra pessoa e informada à equipe; 7.2 em emergência sem tempo, "
        "analisada com o coordenador; 7.3 trocas temporárias valem só para "
        "datas específicas, depois a pessoa volta à tabela original; 7.4 "
        "substituição definitiva só com consenso das partes e do coordenador."
    ),
    (
        "9. Convocação fora da escala para trabalho no sábado não influencia a "
        "escala original."
    ),
    ("8. Qualquer alteração na tabela é informada à equipe exclusivamente por e-mail."),
    ("2. Suporte para o evento marcado e demandas do setor (pendentes ou não)."),
    (
        "3. Se o evento do turno não acontecer, a pessoa cumpre o horário até o"
        " fim se houver setor funcionando que possa acioná-la."
    ),
    (
        "10. Quem cobre escala de outro funcionário em outra unidade, ao voltar"
        " ao polo de origem, entra na escala atual."
    ),
    (
        "11. Convocação do gestor dentro da escala: quem está cumprindo "
        "permanece na convocação até cumpri-la."
    ),
]


def s(k):
    return SABADO + timedelta(weeks=k)


def texto(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def opcoes(html, campo):
    select = re.search(rf'<select name="{campo}".*?</select>', html, flags=re.S)
    assert select, campo
    return re.findall(r'<option value="[^"]+"[^>]*>(.*?)</option>', select.group(0))


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


# Item 1: regras


def test_regras_pede_login(client):
    resposta = client.get(reverse("escala_regras"))

    assert resposta.status_code == 302 and resposta.url.startswith("/entrar/")


def test_regras_com_os_tres_grupos_e_os_textos_exatos(client, membro):
    client.force_login(membro)
    resposta = client.get(reverse("escala_regras"))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    corpo = texto(html[html.index("<main") : html.index("</main>")])

    assert "<title>Regras da escala · Help Desk Equipe</title>" in html
    assert corpo.startswith(
        "‹ Voltar Regras da escala São as mesmas regras da planilha. O sistema "
        "aplica as de fila, data e troca; as demais valem como combinado da equipe."
    )
    posicoes = [corpo.index(regra) for regra in REGRAS]
    assert posicoes == sorted(posicoes)
    grupos = [
        "O sistema aplica",
        "A equipe faz (o sistema só lembra)",
        "Combinado da equipe no dia",
    ]
    assert [corpo.index(g) for g in grupos] == sorted(corpo.index(g) for g in grupos)
    assert corpo.index(grupos[1]) < corpo.index(REGRAS[6]) < corpo.index(grupos[2])
    assert corpo.endswith("Coordenador = os administradores do sistema.")
    # As quatro alineas da regra 7 em linhas separadas.
    for alinea in ("7.1 ", "7.2 ", "7.3 ", "7.4 "):
        assert re.search(rf'<p class="mt-1">{re.escape(alinea)}', html)


def test_regras_so_get(client, membro):
    client.force_login(membro)

    assert client.post(reverse("escala_regras")).status_code == 405


def test_links_para_as_regras(client, equipe):
    client.force_login(equipe[0])

    aba = client.get(reverse("escala")).content.decode()
    trocar = client.get(reverse("escala_trocar")).content.decode()

    link = f'<a href="{reverse("escala_regras")}"'
    assert re.search(rf"{re.escape(link)}[^>]*>Regras da escala</a>", aba)
    # Lado a lado, como na previa: "Trocas registradas" e depois "Regras".
    assert aba.index("Trocas registradas</a>") < aba.index("Regras da escala</a>")
    assert re.search(
        rf"\(regras 7.2 e 7.4\)\. {re.escape(link)}[^>]*>Regras da escala</a></p>",
        trocar,
    )


# Item 2: admin ve sabados gravados


@pytest.fixture
def com_gravados(equipe, hoje):
    """Hoje = domingo depois do 3o sabado: s(0), s(1) e s(2) gravados."""
    hoje(s(2) + timedelta(days=1))
    congelar_passados()
    return equipe


def test_admin_ve_os_gravados_antes_dos_abertos(client, com_gravados, admin_usuario):
    client.force_login(admin_usuario)

    html = client.get(reverse("escala_trocar")).content.decode()

    meus = opcoes(html, "meu")
    assert meus[:4] == [
        f"{s(0):%d/%m} · manhã · Pessoa 1",
        f"{s(1):%d/%m} · manhã · Pessoa 2",
        f"{s(2):%d/%m} · manhã · Pessoa 3",
        f"{s(3):%d/%m} · manhã · Pessoa 4",
    ]
    assert len(meus) == 3 + 12 and opcoes(html, "outro") == meus


def test_admin_ve_no_maximo_8_gravados(client, equipe, hoje, admin_usuario):
    hoje(s(9) + timedelta(days=1))
    congelar_passados()
    client.force_login(admin_usuario)

    meus = opcoes(client.get(reverse("escala_trocar")).content.decode(), "meu")

    assert meus[0].startswith(f"{s(2):%d/%m} ")
    assert len(meus) == 8 + 12


def test_membro_nao_ve_os_gravados(client, com_gravados):
    client.force_login(com_gravados[0])

    html = client.get(reverse("escala_trocar")).content.decode()

    for campo in ("meu", "outro"):
        assert not any(
            o.startswith(f"{s(k):%d/%m} ")
            for o in opcoes(html, campo)
            for k in range(3)
        )


def test_admin_registra_troca_de_sabado_passado_pela_tela(
    client, com_gravados, admin_usuario
):
    p1, p3 = com_gravados[0], com_gravados[2]
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("escala_trocar"),
        {
            "meu": f"{s(0).isoformat()}|manha|{p1.pk}",
            "outro": f"{s(2).isoformat()}|manha|{p3.pk}",
            "tipo": "combinada",
        },
        follow=True,
    )

    assert resposta.redirect_chain[-1][0] == reverse("escala_trocas")
    troca = TrocaSabado.objects.get()
    assert (troca.data_a, troca.data_b) == (s(0), s(2))
    linhas = texto(resposta.content.decode())
    assert f"Pessoa 1 ⇄ Pessoa 3 {s(0):%d/%m} ⇄ {s(2):%d/%m}" in linhas
    # A troca gravada aparece nas opcoes (passa por aplicar).
    html = client.get(reverse("escala_trocar")).content.decode()
    assert f"{s(0):%d/%m} · manhã · Pessoa 3" in opcoes(html, "meu")


# Item 4: marcacao do script


def test_formulario_tem_a_frase_o_script_e_o_texto_fixo(client, equipe):
    client.force_login(equipe[0])

    html = client.get(reverse("escala_trocar")).content.decode()

    assert re.search(r'<p id="frase-da-troca"[^>]*aria-live="polite" hidden></p>', html)
    assert "A fila de cada um não muda." in html
    script = html[html.index("<script>") : html.index("</script>")]
    assert "textContent" in script and "innerHTML" not in script
    assert "disabled" in script and 'select[name="meu"]' in script
    assert "<script src" not in html


def test_sem_javascript_o_formulario_envia_e_valida(client, equipe):
    p1, p2 = equipe[:2]
    client.force_login(p1)

    mesma_data = client.post(
        reverse("escala_trocar"),
        {
            "meu": f"{s(0).isoformat()}|manha|{p1.pk}",
            "outro": f"{s(0).isoformat()}|manha|{p1.pk}",
        },
    )
    ok = client.post(
        reverse("escala_trocar"),
        {
            "meu": f"{s(0).isoformat()}|manha|{p1.pk}",
            "outro": f"{s(1).isoformat()}|manha|{p2.pk}",
        },
    )

    assert mesma_data.status_code == 200
    assert ok.status_code == 302 and TrocaSabado.objects.count() == 1


def test_prazo_de_desfazer_com_a_vespera(client, equipe, hoje):
    p1, p3 = equipe[0], equipe[2]
    client.force_login(p1)
    client.post(
        reverse("escala_trocar"),
        {
            "meu": f"{s(0).isoformat()}|manha|{p1.pk}",
            "outro": f"{s(2).isoformat()}|manha|{p3.pk}",
        },
    )

    html = texto(client.get(reverse("escala_trocas")).content.decode())

    assert (
        "Você pode desfazer até 04/12 (véspera do primeiro sábado). "
        "Depois, só um admin." in html
    )
