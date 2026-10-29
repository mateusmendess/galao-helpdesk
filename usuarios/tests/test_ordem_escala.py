import re

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from conftest import SENHA_DE_TESTE
from fila.regras import situacao_da_fila
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


def criar(n, **campos):
    return Usuario.objects.create_user(
        email=f"pessoa{n}@exemplo.test", first_name=f"Pessoa {n}", **campos
    )


def dados_de_alteracao(usuario, **mudancas):
    """O POST que a tela de alteracao do admin manda, com as mudancas."""
    dados = {
        "email": usuario.email,
        "first_name": usuario.first_name,
        "last_name": "",
        "ordem": usuario.ordem or "",
        "ordem_escala": usuario.ordem_escala or "",
        "is_active": "on",
        "last_login_0": "",
        "last_login_1": "",
        "date_joined_0": "01/01/2026",
        "date_joined_1": "08:00:00",
    }
    dados.update(mudancas)
    return dados


def erro_do_campo(html, campo):
    # Do inicio da linha do campo ate a proxima linha do formulario.
    bloco = re.search(
        rf'<div class="form-row[^"]*field-{campo}[" ](.*?)<div class="form-row',
        html,
        flags=re.S,
    )
    assert bloco, campo
    return " ".join(re.findall(r"<li>(.*?)</li>", bloco.group(1)))


def test_duas_pessoas_nao_tem_a_mesma_posicao():
    criar(1, ordem_escala=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        criar(2, ordem_escala=1)


def test_varias_pessoas_sem_posicao():
    for n in range(1, 4):
        criar(n)

    assert Usuario.objects.filter(ordem_escala__isnull=True).count() == 3


def test_posicao_comeca_em_1():
    pessoa = criar(1, ordem_escala=0)

    with pytest.raises(ValidationError) as erro:
        pessoa.full_clean()

    assert "ordem_escala" in erro.value.message_dict


def test_repetida_no_admin_da_o_mesmo_erro_que_a_ordem(client, admin_usuario):
    criar(1, ordem=1, ordem_escala=1)
    segunda = criar(2, ordem=2, ordem_escala=2)
    client.force_login(admin_usuario)
    alterar = reverse("admin:usuarios_usuario_change", args=[segunda.pk])

    ordem = client.post(alterar, dados_de_alteracao(segunda, ordem=1))
    escala = client.post(alterar, dados_de_alteracao(segunda, ordem_escala=1))

    assert ordem.status_code == escala.status_code == 200
    erro_ordem = erro_do_campo(ordem.content.decode(), "ordem")
    erro_escala = erro_do_campo(escala.content.decode(), "ordem_escala")
    assert erro_ordem == "Usuário com este Ordem já existe."
    assert erro_escala == "Usuário com este Posição na escala de sábado já existe."
    segunda.refresh_from_db()
    assert (segunda.ordem, segunda.ordem_escala) == (2, 2)


def test_admin_altera_a_posicao(client, admin_usuario):
    pessoa = criar(1, ordem=1)
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_change", args=[pessoa.pk]),
        dados_de_alteracao(pessoa, ordem_escala=3),
    )

    assert resposta.status_code == 302
    pessoa.refresh_from_db()
    assert (pessoa.ordem, pessoa.ordem_escala) == (1, 3)


def test_admin_cria_com_posicao(client, admin_usuario):
    client.force_login(admin_usuario)

    resposta = client.post(
        reverse("admin:usuarios_usuario_add"),
        {
            "email": "pessoa7@exemplo.test",
            "first_name": "Pessoa 7",
            "ordem": "7",
            "ordem_escala": "4",
            "usable_password": "true",
            "password1": SENHA_DE_TESTE,
            "password2": SENHA_DE_TESTE,
        },
    )

    assert resposta.status_code == 302
    nova = Usuario.objects.get(email="pessoa7@exemplo.test")
    assert (nova.ordem, nova.ordem_escala) == (7, 4)


def test_formularios_do_admin_mostram_o_campo_depois_da_ordem(client, admin_usuario):
    pessoa = criar(1, ordem=1)
    client.force_login(admin_usuario)

    criar_html = client.get(reverse("admin:usuarios_usuario_add")).content.decode()
    alterar_html = client.get(
        reverse("admin:usuarios_usuario_change", args=[pessoa.pk])
    ).content.decode()

    for html in (criar_html, alterar_html):
        assert 'name="ordem_escala"' in html
        assert html.index('name="ordem"') < html.index('name="ordem_escala"')
        assert "Posição no rodízio dos sábados." in html
    # Na alteracao, fica no grupo "Dados pessoais".
    dados = alterar_html[alterar_html.index("Dados pessoais") :]
    assert dados.index('name="ordem_escala"') < dados.index("Permissões")


def test_lista_do_admin_tem_a_coluna_depois_da_ordem(client, admin_usuario):
    criar(1, ordem=1, ordem_escala=2)
    client.force_login(admin_usuario)

    html = client.get(reverse("admin:usuarios_usuario_changelist")).content.decode()

    assert 'class="sortable column-ordem_escala' in html
    assert html.index("column-ordem ") < html.index("column-ordem_escala")
    assert "Posição na escala de sábado" in html


def test_fila_do_galao_nao_muda_com_a_posicao_da_escala():
    pessoas = [criar(n, ordem=n) for n in range(1, 5)]

    def fila():
        return [(p.usuario.pk, p.estado) for p in situacao_da_fila()]

    antes = fila()
    for pessoa, posicao in zip(pessoas, (3, 1, None, 2)):
        pessoa.ordem_escala = posicao
        pessoa.save()

    assert fila() == antes
    assert [pk for pk, _ in antes] == [p.pk for p in pessoas]
