from datetime import timedelta

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.urls import reverse

from escala.models import SabadoDuasPessoas, SabadoSemEscala

from .conftest import PROXIMO_SABADO, SABADO

pytestmark = pytest.mark.django_db

MODELOS = [SabadoSemEscala, SabadoDuasPessoas]
OUTRO = {SabadoSemEscala: SabadoDuasPessoas, SabadoDuasPessoas: SabadoSemEscala}
JA_ESTA = {
    SabadoSemEscala: "Este sábado já está cadastrado como sábado com 2 pessoas.",
    SabadoDuasPessoas: "Este sábado já está cadastrado como sábado sem escala.",
}


def erros(objeto):
    with pytest.raises(ValidationError) as erro:
        objeto.full_clean()
    return erro.value.message_dict


def url(modelo, acao, *args):
    return reverse(f"admin:escala_{modelo._meta.model_name}_{acao}", args=args)


@pytest.mark.parametrize("modelo", MODELOS)
def test_sabado_futuro_vale(hoje, modelo):
    modelo(data=SABADO).full_clean()


@pytest.mark.parametrize("modelo", MODELOS)
@pytest.mark.parametrize("dias", [1, 2, 3, 4, 5, 6])
def test_data_precisa_ser_sabado(hoje, modelo, dias):
    objeto = modelo(data=SABADO + timedelta(days=dias))

    assert erros(objeto) == {"data": ["A data precisa ser um sábado."]}


@pytest.mark.parametrize("modelo", MODELOS)
def test_sabado_passado_e_recusado(hoje, modelo):
    hoje(SABADO + timedelta(days=1))

    assert erros(modelo(data=SABADO)) == {
        "data": ["Esse sábado já passou e não pode mais mudar."]
    }


@pytest.mark.parametrize("modelo", MODELOS)
def test_sabado_de_hoje_ainda_vale(hoje, modelo):
    hoje(SABADO)

    modelo(data=SABADO).full_clean()


@pytest.mark.parametrize("modelo", MODELOS)
def test_data_repetida_o_banco_recusa(modelo):
    modelo.objects.create(data=SABADO)

    with pytest.raises(IntegrityError), transaction.atomic():
        modelo.objects.create(data=SABADO)


@pytest.mark.parametrize("modelo", MODELOS)
def test_mesma_data_nos_dois_cadastros_e_recusada(hoje, modelo):
    OUTRO[modelo].objects.create(data=SABADO)

    assert erros(modelo(data=SABADO)) == {"data": [JA_ESTA[modelo]]}
    # Outro sabado continua livre.
    modelo(data=PROXIMO_SABADO).full_clean()


def test_motivos_e_padroes(hoje):
    assert SabadoSemEscala.Motivo.choices == [
        ("feriado", "Feriado"),
        ("imprevisto", "Imprevisto"),
        ("outro", "Outro"),
    ]
    novo = SabadoSemEscala(data=SABADO)
    assert novo.motivo == "feriado"
    assert novo.passa_para_proximo is True
    for valor in ("imprevisto", "outro"):
        SabadoSemEscala(data=SABADO, motivo=valor).full_clean()
    assert "motivo" in erros(SabadoSemEscala(data=SABADO, motivo="chuva"))


@pytest.mark.parametrize("modelo", MODELOS)
def test_linha_passada_so_consulta_no_admin(hoje, admin_usuario, modelo):
    passado = modelo.objects.create(data=SABADO)
    futuro = modelo.objects.create(data=PROXIMO_SABADO)
    hoje(SABADO + timedelta(days=1))
    request = RequestFactory().get("/")
    request.user = admin_usuario
    modelo_admin = admin.site._registry[modelo]

    assert not modelo_admin.has_change_permission(request, passado)
    assert not modelo_admin.has_delete_permission(request, passado)
    assert modelo_admin.has_change_permission(request, futuro)
    assert modelo_admin.has_delete_permission(request, futuro)
    assert modelo_admin.has_add_permission(request)


@pytest.mark.parametrize("modelo", MODELOS)
def test_admin_nao_altera_nem_apaga_linha_passada(client, hoje, admin_usuario, modelo):
    passado = modelo.objects.create(data=SABADO)
    hoje(SABADO + timedelta(days=1))
    client.force_login(admin_usuario)

    tela = client.get(url(modelo, "change", passado.pk))
    assert tela.status_code == 200
    assert 'name="_save"' not in tela.content.decode()
    alterar = client.post(url(modelo, "change", passado.pk), {"data": "12/12/2026"})
    assert alterar.status_code == 403
    apagar = client.post(url(modelo, "delete", passado.pk), {"post": "yes"})
    assert apagar.status_code == 403
    # Nem pela acao "excluir selecionados" da lista.
    client.post(
        url(modelo, "changelist"),
        {"action": "delete_selected", "_selected_action": [passado.pk], "post": "yes"},
    )
    passado.refresh_from_db()
    assert passado.data == SABADO


@pytest.mark.parametrize("modelo", MODELOS)
def test_admin_cadastra_sabado_futuro_e_recusa_os_invalidos(
    client, hoje, admin_usuario, modelo
):
    client.force_login(admin_usuario)
    dados = {"motivo": "feriado", "passa_para_proximo": "on"}

    ok = client.post(url(modelo, "add"), {"data": "05/12/2026", **dados})
    domingo = client.post(url(modelo, "add"), {"data": "06/12/2026", **dados})
    OUTRO[modelo].objects.create(data=PROXIMO_SABADO)
    nos_dois = client.post(url(modelo, "add"), {"data": "12/12/2026", **dados})

    assert ok.status_code == 302
    assert "A data precisa ser um sábado." in domingo.content.decode()
    assert JA_ESTA[modelo] in nos_dois.content.decode()
    assert list(modelo.objects.values_list("data", flat=True)) == [SABADO]
