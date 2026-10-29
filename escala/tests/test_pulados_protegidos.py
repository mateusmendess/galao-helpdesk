from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import ProtectedError
from django.urls import reverse

from escala.calculo import congelar_passados
from escala.models import (
    ConfiguracaoEscala,
    PuladoNoSabado,
    SabadoDuasPessoas,
    SabadoFechado,
)
from fila.models import Ausencia
from usuarios.models import Usuario

from .conftest import SABADO

pytestmark = pytest.mark.django_db


@pytest.fixture
def gravado(django_user_model, hoje):
    """Pessoa 2 so aparece como pulada (ausente) em 05/12, sabado de 2 pessoas;
    Pessoa 1 (manha) e Pessoa 3 (tarde) trabalharam."""
    equipe = [
        django_user_model.objects.create_user(
            email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", ordem_escala=n
        )
        for n in range(1, 4)
    ]
    ConfiguracaoEscala.objects.create(inicio=SABADO, primeiro=equipe[0])
    SabadoDuasPessoas.objects.create(data=SABADO)
    ausencia = Ausencia.objects.create(usuario=equipe[1], inicio=SABADO, fim=SABADO)
    hoje(SABADO + timedelta(days=8))
    congelar_passados()
    ausencia.delete()  # a ausencia nao segura ninguem; so o sabado gravado
    return equipe


def test_pulado_e_gravado_pelo_modelo_novo(gravado):
    fechado = SabadoFechado.objects.get(data=SABADO)

    assert list(fechado.pulados.all()) == [gravado[1]]
    assert PuladoNoSabado.objects.get().usuario == gravado[1]


def test_apagar_pulado_pelo_modelo_e_recusado(gravado):
    with pytest.raises(ProtectedError):
        gravado[1].delete()

    assert list(SabadoFechado.objects.get(data=SABADO).pulados.all()) == [gravado[1]]


def test_apagar_quem_trabalhou_e_recusado(gravado):
    with pytest.raises(ProtectedError):
        gravado[2].delete()


def test_admin_recusa_apagar_pulado_sem_erro(client, admin_usuario, gravado):
    client.force_login(admin_usuario)
    url = reverse("admin:usuarios_usuario_delete", args=[gravado[1].pk])

    tela = client.get(url)
    resposta = client.post(url, {"post": "yes"})

    assert tela.status_code == 200
    assert "Não é possível remover" in tela.content.decode()
    assert resposta.status_code == 200
    assert Usuario.objects.filter(pk=gravado[1].pk).exists()


def test_admin_excluir_selecionados_tambem_recusa(client, admin_usuario, gravado):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_changelist"),
        {
            "action": "delete_selected",
            "_selected_action": [gravado[1].pk],
            "post": "yes",
        },
    )

    assert resposta.status_code == 200
    assert "Não é possível remover" in resposta.content.decode()
    assert Usuario.objects.filter(pk=gravado[1].pk).exists()


def test_quem_nao_aparece_em_nada_pode_ser_apagado(client, admin_usuario, gravado):
    livre = Usuario.objects.create_user(email="pessoa9@exemplo.test")
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_delete", args=[livre.pk]), {"post": "yes"}
    )

    assert resposta.status_code == 302
    assert not Usuario.objects.filter(pk=livre.pk).exists()


def test_desativar_continua_livre(gravado):
    gravado[1].is_active = False
    gravado[1].save()

    gravado[1].refresh_from_db()
    assert not gravado[1].is_active


def test_admin_do_sabado_fechado_mostra_o_pulado(client, admin_usuario, gravado):
    client.force_login(admin_usuario)
    fechado = SabadoFechado.objects.get(data=SABADO)

    html = client.get(
        reverse("admin:escala_sabadofechado_change", args=[fechado.pk])
    ).content.decode()

    assert "pessoa2@exemplo.test" in html


@pytest.mark.django_db(transaction=True)
def test_migracao_0003_copia_os_pulados_e_volta():
    executor = MigrationExecutor(connection)
    # Os outros apps no estado atual; so a escala volta para a 0002.
    outros = [n for n in executor.loader.graph.leaf_nodes() if n[0] != "escala"]
    antes = [("escala", "0002_sabado_fechado"), *outros]
    depois = [("escala", "0003_pulado_no_sabado"), *outros]
    try:
        # Do zero ate a 0002, com dados no M2M antigo.
        executor.migrate([("escala", None)])
        executor.loader.build_graph()
        executor.migrate(antes)
        velhos = executor.loader.project_state(antes).apps
        Pessoa = velhos.get_model("usuarios", "Usuario")
        Fechado = velhos.get_model("escala", "SabadoFechado")
        p1 = Pessoa.objects.create(email="pessoa1@exemplo.test")
        p2 = Pessoa.objects.create(email="pessoa2@exemplo.test")
        fechado = Fechado.objects.create(data=SABADO, vagas=1, cursor_depois=3)
        fechado.pulados.add(p1, p2)

        executor.loader.build_graph()
        executor.migrate(depois)
        novos = executor.loader.project_state(depois).apps
        Pulado = novos.get_model("escala", "PuladoNoSabado")
        assert sorted(Pulado.objects.values_list("fechado_id", "usuario_id")) == [
            (fechado.pk, p1.pk),
            (fechado.pk, p2.pk),
        ]
        assert sorted(
            novos.get_model("escala", "SabadoFechado")
            .objects.get()
            .pulados.values_list("pk", flat=True)
        ) == sorted([p1.pk, p2.pk])

        # E a volta para a 0002 devolve as ligacoes.
        executor.loader.build_graph()
        executor.migrate(antes)
        velhos = executor.loader.project_state(antes).apps
        de_volta = velhos.get_model("escala", "SabadoFechado").objects.get()
        assert sorted(de_volta.pulados.values_list("pk", flat=True)) == sorted(
            [p1.pk, p2.pk]
        )
    finally:
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
