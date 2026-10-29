import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

PAGINAS = [
    f"admin:escala_{modelo}_{acao}"
    for modelo in ("configuracaoescala", "sabadosemescala", "sabadoduaspessoas")
    for acao in ("changelist", "add")
]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_admin_abre_as_paginas_da_escala(client, admin_usuario, pagina):
    client.force_login(admin_usuario)

    assert client.get(reverse(pagina)).status_code == 200


def test_app_aparece_como_escala_de_sabado(client, admin_usuario):
    client.force_login(admin_usuario)

    html = client.get(reverse("admin:index")).content.decode()

    assert "Escala de sábado" in html
    for nome in (
        "Configuração da escala",
        "Sábados sem escala",
        "Sábados com 2 pessoas",
    ):
        assert nome in html


@pytest.mark.parametrize("pagina", PAGINAS)
def test_membro_comum_nao_abre(client, membro, pagina):
    client.force_login(membro)

    resposta = client.get(reverse(pagina))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("admin:login"))
