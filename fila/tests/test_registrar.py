import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse

from fila import regras
from fila.models import Rodada, Troca
from fila.regras import VezMudou, de_quem_e_a_vez, registrar_troca, saldos_devendo

pytestmark = pytest.mark.django_db

URL = "/trocas/nova/"
VEZ_MUDOU = "A vez mudou enquanto você preenchia"
NINGUEM = "Ninguém disponível agora."


def test_rota_tem_o_nome_combinado():
    assert reverse("registrar_troca") == URL


def postar(client, quem_logado, titular, quem="eu", executor=None, observacao=""):
    client.force_login(quem_logado)
    dados = {"titular": titular.pk, "quem": quem, "observacao": observacao}
    if executor is not None:
        dados["executor"] = executor.pk
    return client.post(URL, dados)


def mensagens(resposta):
    # Inclui as ainda nao lidas de pedidos anteriores do mesmo cliente.
    return [str(m) for m in get_messages(resposta.wsgi_request)]


# 2. Registro normal


def test_pessoa_da_vez_registra_fui_eu(client, equipe):
    a = equipe[0]

    resposta = postar(client, a, a, observacao="galão novo")

    assert resposta.status_code == 302
    assert resposta.url == reverse("home")
    troca = Troca.objects.get()
    assert (troca.titular, troca.executor, troca.registrada_por) == (a, a, a)
    assert troca.observacao == "galão novo"
    assert de_quem_e_a_vez() == equipe[1]
    assert mensagens(resposta) == ["Troca registrada: Pessoa 1 trocou o galão."]


# 3. Cobertura com "Fui eu"


def test_outra_pessoa_registra_fui_eu_na_vez_de_a(client, equipe):
    a, c = equipe[0], equipe[2]

    resposta = postar(client, c, a)

    troca = Troca.objects.get()
    assert (troca.titular, troca.executor, troca.registrada_por) == (a, c, c)
    assert saldos_devendo() == {a.pk: 1}
    assert de_quem_e_a_vez() == equipe[1]
    assert mensagens(resposta) == [
        "Troca registrada: Pessoa 3 trocou no lugar de Pessoa 1."
    ]


# 4. "Foi outra pessoa"


def test_foi_outra_pessoa_grava_o_executor_escolhido(client, equipe, admin_usuario):
    a, g = equipe[0], equipe[6]

    postar(client, admin_usuario, a, quem="outra", executor=g)

    troca = Troca.objects.get()
    assert (troca.titular, troca.executor, troca.registrada_por) == (
        a,
        g,
        admin_usuario,
    )


def test_foi_outra_pessoa_sem_escolher_da_erro_no_campo(client, equipe):
    resposta = postar(client, equipe[0], equipe[0], quem="outra")

    assert resposta.status_code == 200
    form = resposta.context["form"]
    assert form.errors["executor"] == ["Escolha quem trocou o galão."]
    assert Troca.objects.count() == 0
    # Ao reabrir, "Foi outra pessoa" continua marcada.
    assert 'value="outra" checked' in resposta.content.decode()


def test_foi_outra_pessoa_inativa_e_recusada(client, equipe):
    equipe[6].is_active = False
    equipe[6].save()

    resposta = postar(client, equipe[0], equipe[0], quem="outra", executor=equipe[6])

    assert resposta.status_code == 200
    assert "executor" in resposta.context["form"].errors
    assert Troca.objects.count() == 0


def test_lista_tem_ativos_menos_quem_esta_logado(client, equipe, admin_usuario):
    equipe[6].is_active = False
    equipe[6].save()
    client.force_login(equipe[0])

    form = client.get(URL).context["form"]

    opcoes = list(form.fields["executor"].queryset)
    assert equipe[0] not in opcoes
    assert equipe[6] not in opcoes
    assert admin_usuario in opcoes
    assert equipe[1] in opcoes


def test_sem_dizer_quem_trocou_da_erro(client, equipe):
    client.force_login(equipe[0])

    resposta = client.post(URL, {"titular": equipe[0].pk})

    assert resposta.status_code == 200
    assert "quem" in resposta.context["form"].errors
    assert Troca.objects.count() == 0


# 5. O titular nunca vem do cliente


def test_titular_adulterado_nao_grava(client, equipe):
    resposta = postar(client, equipe[0], equipe[4])

    assert Troca.objects.count() == 0
    assert resposta.url == reverse("home")
    assert mensagens(resposta) == [
        "A vez mudou enquanto você preenchia: agora é de Pessoa 1. "
        "Confira e tente de novo."
    ]


def test_titular_inexistente_nao_grava(client, equipe):
    client.force_login(equipe[0])

    resposta = client.post(URL, {"titular": 999999, "quem": "eu"})

    assert Troca.objects.count() == 0
    assert VEZ_MUDOU in mensagens(resposta)[0]


def test_titular_antigo_depois_que_a_vez_andou_nao_grava(client, equipe, registrar):
    registrar(equipe[0])

    resposta = postar(client, equipe[2], equipe[0])

    assert Troca.objects.count() == 1
    assert VEZ_MUDOU in mensagens(resposta)[0]
    assert "agora é de Pessoa 2" in mensagens(resposta)[0]


# 6. Sem vez


def test_fila_vazia_get_e_post_nao_gravam(client, admin_usuario):
    client.force_login(admin_usuario)

    get = client.get(URL)
    post = client.post(URL, {"titular": admin_usuario.pk, "quem": "eu"})

    for resposta in (get, post):
        assert resposta.status_code == 302
        assert resposta.url == reverse("home")
        assert mensagens(resposta)[-1] == NINGUEM
    assert Troca.objects.count() == 0


def test_so_ausentes_get_e_post_nao_gravam(client, equipe, monkeypatch):
    monkeypatch.setattr(regras, "ausentes_hoje", lambda: set(equipe))
    client.force_login(equipe[0])

    get = client.get(URL)
    post = client.post(URL, {"titular": equipe[0].pk, "quem": "eu"})

    for resposta in (get, post):
        assert resposta.url == reverse("home")
        assert mensagens(resposta)[-1] == NINGUEM
    assert Troca.objects.count() == 0


# 7. Dois registros para a mesma vez


def test_dois_registros_seguidos_para_a_mesma_vez(client, equipe):
    primeiro = postar(client, equipe[0], equipe[0])
    segundo = postar(client, equipe[3], equipe[0])

    assert primeiro.status_code == segundo.status_code == 302
    assert Troca.objects.count() == 1
    # A mensagem mais recente (a do primeiro nao foi lida na tela inicial).
    assert VEZ_MUDOU in mensagens(segundo)[-1]


def test_corrida_no_banco_vira_vez_mudou(equipe, registrar, monkeypatch):
    # Simula duas requisicoes que leram a mesma vez antes de qualquer gravar:
    # a leitura fica "velha" e a validacao nao percebe; o banco recusa.
    registrar(equipe[0])
    monkeypatch.setattr(regras, "de_quem_e_a_vez", lambda *a, **k: equipe[0])
    monkeypatch.setattr(Troca, "full_clean", lambda self, *a, **k: None)

    with pytest.raises(VezMudou):
        registrar_troca(equipe[0], equipe[0], equipe[0])

    assert Troca.objects.count() == 1


def test_validacao_que_percebe_a_troca_repetida_vira_vez_mudou(
    equipe, registrar, monkeypatch
):
    registrar(equipe[0])
    monkeypatch.setattr(regras, "de_quem_e_a_vez", lambda *a, **k: equipe[0])

    with pytest.raises(VezMudou):
        registrar_troca(equipe[0], equipe[0], equipe[0])

    assert Troca.objects.count() == 1


# 8. Ultimo da rodada


def test_ultimo_da_rodada_fecha_e_a_tela_mostra_rodada_2(client, equipe, registrar):
    for pessoa in equipe[:6]:
        registrar(pessoa)

    resposta = postar(client, equipe[6], equipe[6])

    assert resposta.url == reverse("home")
    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert "Rodada 2" in client.get(reverse("home")).content.decode()


# 9. Seguranca


@pytest.mark.parametrize("nome", ["registrar_troca", "historico"])
def test_anonimo_vai_para_o_login(client, nome):
    resposta = client.get(reverse(nome))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))


@pytest.mark.parametrize("nome", ["registrar_troca", "historico"])
def test_quem_precisa_trocar_a_senha_e_levado_a_troca(client, equipe, nome):
    equipe[0].precisa_trocar_senha = True
    equipe[0].save()
    client.force_login(equipe[0])

    resposta = client.get(reverse(nome))

    assert resposta.status_code == 302
    assert resposta.url == reverse("password_change")


def test_get_mostra_o_formulario_e_nao_grava(client, equipe):
    client.force_login(equipe[2])

    resposta = client.get(URL)

    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert Troca.objects.count() == 0
    assert "Registrar troca" in conteudo
    assert "De quem era a vez" in conteudo
    assert "Fui eu (Pessoa 3)" in conteudo
    assert "Foi outra pessoa" in conteudo
    assert "Escolher pessoa" in conteudo
    assert (
        "Se quem trocou não for Pessoa 1, a vez de Pessoa 1 conta como cumprida e "
        "essa pessoa passa a dever 1 troca. Quem trocou no lugar dela abate 1 da "
        "própria dívida, se tiver."
    ) in conteudo
    assert "Observação (opcional)" in conteudo
    assert f'name="titular" value="{equipe[0].pk}"' in conteudo
    assert 'value="eu" checked' in conteudo
    assert 'href="{}"'.format(reverse("home")) in conteudo


def test_post_sem_csrf_e_recusado(equipe):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(equipe[0])

    resposta = cliente.post(URL, {"titular": equipe[0].pk, "quem": "eu"})

    assert resposta.status_code == 403
    assert Troca.objects.count() == 0


def test_outros_metodos_sao_recusados(client, equipe):
    client.force_login(equipe[0])

    assert client.put(URL).status_code == 405
    assert client.post(reverse("historico")).status_code == 405
    assert client.post(reverse("home")).status_code == 405
