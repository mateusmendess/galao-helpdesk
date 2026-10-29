from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from escala.models import ConfiguracaoEscala

from .conftest import PROXIMO_SABADO, SABADO

pytestmark = pytest.mark.django_db

PRECISA_TER_POSICAO = "Escolha uma pessoa ativa que tenha posição na escala."


@pytest.fixture
def pessoas(django_user_model):
    """Pessoa 1 e Pessoa 2 na escala; Pessoa 3 fora dela."""
    return [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem_escala=e
        )
        for n, e in ((1, 1), (2, 2), (3, None))
    ]


def erros(configuracao):
    with pytest.raises(ValidationError) as erro:
        configuracao.full_clean()
    return erro.value.message_dict


def test_valida_com_sabado_e_pessoa_da_escala(pessoas):
    ConfiguracaoEscala(inicio=SABADO, primeiro=pessoas[0]).full_clean()


@pytest.mark.parametrize("dias", [1, 2, 3, 4, 5, 6])
def test_inicio_precisa_ser_sabado(pessoas, dias):
    configuracao = ConfiguracaoEscala(
        inicio=SABADO + timedelta(days=dias), primeiro=pessoas[0]
    )

    assert erros(configuracao) == {
        "inicio": ["A data de início precisa ser um sábado."]
    }


def test_primeiro_precisa_ter_posicao_na_escala(pessoas):
    configuracao = ConfiguracaoEscala(inicio=SABADO, primeiro=pessoas[2])

    assert erros(configuracao) == {"primeiro": [PRECISA_TER_POSICAO]}


def test_primeiro_precisa_estar_ativo(pessoas):
    pessoas[0].is_active = False
    pessoas[0].save()
    configuracao = ConfiguracaoEscala(inicio=SABADO, primeiro=pessoas[0])

    assert erros(configuracao) == {"primeiro": [PRECISA_TER_POSICAO]}


def test_obter_sem_e_com_linha(pessoas):
    assert ConfiguracaoEscala.obter() is None

    criada = ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=pessoas[0])

    assert ConfiguracaoEscala.obter() == criada
    assert criada.pk == 1


def test_segunda_gravacao_vai_para_a_mesma_linha(pessoas):
    ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=pessoas[0])

    ConfiguracaoEscala(inicio=PROXIMO_SABADO, primeiro=pessoas[1]).save()
    ConfiguracaoEscala.objects.create(inicio=PROXIMO_SABADO, primeiro=pessoas[1])

    assert ConfiguracaoEscala.objects.count() == 1
    unica = ConfiguracaoEscala.obter()
    assert (unica.pk, unica.inicio, unica.primeiro) == (1, PROXIMO_SABADO, pessoas[1])


def test_admin_adiciona_so_quando_nao_existe_e_nunca_apaga(
    client, admin_usuario, pessoas
):
    client.force_login(admin_usuario)
    adicionar = reverse("admin:escala_configuracaoescala_add")
    lista = reverse("admin:escala_configuracaoescala_changelist")

    assert client.get(adicionar).status_code == 200
    resposta = client.post(
        adicionar, {"inicio": "05/12/2026", "primeiro": pessoas[0].pk}
    )
    assert resposta.status_code == 302
    assert ConfiguracaoEscala.obter().inicio == SABADO

    assert client.get(adicionar).status_code == 403
    assert adicionar not in client.get(lista).content.decode()
    apagar = reverse("admin:escala_configuracaoescala_delete", args=[1])
    assert client.get(apagar).status_code == 403
    assert client.post(apagar, {"post": "yes"}).status_code == 403
    assert ConfiguracaoEscala.objects.count() == 1


def test_admin_mostra_os_erros_e_nao_grava(client, admin_usuario, pessoas):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:escala_configuracaoescala_add"),
        {"inicio": "06/12/2026", "primeiro": pessoas[2].pk},
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "A data de início precisa ser um sábado." in html
    assert PRECISA_TER_POSICAO in html
    assert ConfiguracaoEscala.obter() is None


def test_mensagem_de_sucesso_no_feminino(client, admin_usuario, pessoas):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:escala_configuracaoescala_add"),
        {"inicio": "05/12/2026", "primeiro": pessoas[0].pk},
        follow=True,
    )

    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any(m.startswith("A configuração da escala “") for m in mensagens)
    assert any("foi adicionada com sucesso" in m for m in mensagens)
