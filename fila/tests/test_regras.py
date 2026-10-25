import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from fila.models import Rodada, Troca
from fila.regras import (
    AGUARDANDO,
    AUSENTE,
    TROCOU,
    VEZ,
    ausentes_hoje,
    de_quem_e_a_vez,
    fechar_rodada_se_completa,
    rodada_atual,
    situacao_da_fila,
    usuarios_da_fila,
)

pytestmark = pytest.mark.django_db


def estados(**kwargs):
    return [(p.usuario.ordem, p.estado) for p in situacao_da_fila(**kwargs)]


# 1. Fila vazia


def test_sem_ninguem_na_fila_nao_ha_vez(admin_usuario):
    assert usuarios_da_fila() == []
    assert de_quem_e_a_vez() is None
    assert situacao_da_fila() == []


def test_ausentes_hoje_ainda_e_vazio():
    assert ausentes_hoje() == set()


# 2. Primeira rodada


def test_com_a_equipe_e_sem_trocas_a_vez_e_da_ordem_1(equipe):
    assert de_quem_e_a_vez() == equipe[0]
    assert estados() == [(1, VEZ)] + [(n, AGUARDANDO) for n in range(2, 8)]


def test_rodada_atual_abre_a_rodada_1_uma_unica_vez(equipe):
    primeira = rodada_atual()

    assert primeira.numero == 1
    assert primeira.fechada_em is None
    assert rodada_atual() == primeira
    assert rodada_atual() == primeira
    assert Rodada.objects.count() == 1


def test_fila_segue_a_ordem_e_nao_a_ordem_de_cadastro(django_user_model):
    tres = django_user_model.objects.create_user(email="c@exemplo.test", ordem=3)
    um = django_user_model.objects.create_user(email="a@exemplo.test", ordem=1)
    dois = django_user_model.objects.create_user(email="b@exemplo.test", ordem=2)

    assert usuarios_da_fila() == [um, dois, tres]


# 3. A vez anda


def test_a_vez_anda_da_ordem_1_ate_a_7(equipe, registrar):
    for n, pessoa in enumerate(equipe[:-1], start=1):
        assert de_quem_e_a_vez() == pessoa
        registrar(pessoa)
        assert de_quem_e_a_vez() == equipe[n]
    assert de_quem_e_a_vez() == equipe[6]
    assert estados() == [(n, TROCOU) for n in range(1, 7)] + [(7, VEZ)]


# 4. Cobertura


def test_cobertura_conta_a_vez_do_titular_e_nao_a_do_executor(equipe, registrar):
    pessoa1, pessoa2, *_, pessoa7 = equipe
    registrar(pessoa1)

    troca = registrar(pessoa2, executor=pessoa7)

    assert troca.executor == pessoa7
    situacao = dict(estados())
    assert situacao[2] == TROCOU
    assert situacao[7] == AGUARDANDO
    assert de_quem_e_a_vez() == equipe[2]


def test_executor_que_cobriu_continua_devendo_a_propria_vez(equipe, registrar):
    pessoa1, pessoa2 = equipe[:2]

    registrar(pessoa1, executor=pessoa2)

    assert dict(estados())[2] == VEZ
    assert de_quem_e_a_vez() == pessoa2


# 5. Inativo e sem ordem


def test_inativo_e_sem_ordem_nao_entram_na_fila(equipe, admin_usuario):
    equipe[1].is_active = False
    equipe[1].save()

    fila = usuarios_da_fila()

    assert equipe[1] not in fila
    assert admin_usuario not in fila
    assert [u.ordem for u in fila] == [1, 3, 4, 5, 6, 7]


def test_inativo_e_sem_ordem_nao_sao_exigidos_para_fechar(
    equipe, admin_usuario, registrar
):
    equipe[1].is_active = False
    equipe[1].save()
    for pessoa in equipe:
        if pessoa != equipe[1]:
            registrar(pessoa)

    assert Rodada.objects.get(numero=1).fechada_em is not None
    assert rodada_atual().numero == 2


# 6. Ausencia


def test_ausente_e_pulado_e_aparece_como_ausente(equipe):
    ausentes = {equipe[1]}

    assert de_quem_e_a_vez(ausentes=ausentes) == equipe[0]
    assert dict(estados(ausentes=ausentes))[2] == AUSENTE


def test_com_a_ordem_2_ausente_a_vez_passa_para_a_ordem_3(equipe, registrar):
    registrar(equipe[0])
    ausentes = {equipe[1]}

    assert de_quem_e_a_vez(ausentes=ausentes) == equipe[2]
    assert estados(ausentes=ausentes)[:3] == [(1, TROCOU), (2, AUSENTE), (3, VEZ)]


def test_ausente_nao_e_exigido_para_fechar_a_rodada(equipe, registrar):
    ausentes = {equipe[1]}
    rodada = rodada_atual()
    for pessoa in equipe:
        if pessoa != equipe[1]:
            Troca.objects.create(
                rodada=rodada,
                titular=pessoa,
                executor=pessoa,
                registrada_por=pessoa,
            )

    # Sem ausentes a rodada continua aberta (falta a ordem 2)...
    rodada.refresh_from_db()
    assert rodada.fechada_em is None
    # ...com a ordem 2 ausente, fecha.
    assert fechar_rodada_se_completa(rodada, ausentes=ausentes) is True
    rodada.refresh_from_db()
    assert rodada.fechada_em is not None


def test_ausente_que_volta_retoma_o_lugar_na_ordem(equipe, registrar):
    registrar(equipe[0])
    assert de_quem_e_a_vez(ausentes={equipe[1]}) == equipe[2]

    # Voltou (saiu de ausentes): e a vez dele de novo, pela ordem fixa.
    assert de_quem_e_a_vez(ausentes=set()) == equipe[1]
    assert estados()[:3] == [(1, TROCOU), (2, VEZ), (3, AGUARDANDO)]


def test_ninguem_disponivel_quando_so_restam_ausentes(equipe, registrar):
    for pessoa in equipe[:5]:
        registrar(pessoa)

    assert de_quem_e_a_vez(ausentes={equipe[5], equipe[6]}) is None


# 7. Fechamento


def test_ultimo_presente_trocando_fecha_a_rodada_e_abre_a_proxima(equipe, registrar):
    primeira = rodada_atual()
    for pessoa in equipe:
        registrar(pessoa)

    primeira.refresh_from_db()
    assert primeira.fechada_em is not None
    segunda = rodada_atual()
    assert segunda.numero == 2
    assert segunda.fechada_em is None
    assert Rodada.objects.filter(fechada_em__isnull=True).count() == 1
    assert de_quem_e_a_vez() == equipe[0]
    assert estados() == [(1, VEZ)] + [(n, AGUARDANDO) for n in range(2, 8)]
    # A rodada fechada e as trocas dela continuam no banco.
    assert Troca.objects.filter(rodada=primeira).count() == 7


def test_a_vez_volta_para_a_menor_ordem_presente(equipe, registrar):
    for pessoa in equipe:
        registrar(pessoa)

    assert de_quem_e_a_vez(ausentes={equipe[0]}) == equipe[1]


def test_rodada_3_abre_depois_da_2(equipe, registrar):
    for _ in range(2):
        for pessoa in equipe:
            registrar(pessoa)

    assert rodada_atual().numero == 3
    assert list(Rodada.objects.values_list("numero", flat=True)) == [3, 2, 1]


# 8. Nao fecha antes da hora


def test_rodada_nao_fecha_enquanto_falta_alguem(equipe, registrar):
    for pessoa in equipe[:-1]:
        registrar(pessoa)

    rodada = rodada_atual()
    assert rodada.numero == 1
    assert fechar_rodada_se_completa(rodada) is False
    assert rodada_atual().numero == 1


def test_rodada_nao_fecha_com_a_fila_vazia(admin_usuario):
    rodada = rodada_atual()

    assert fechar_rodada_se_completa(rodada) is False
    rodada.refresh_from_db()
    assert rodada.fechada_em is None


# 9. Fechar duas vezes


def test_fechar_duas_vezes_nao_cria_duas_rodadas(equipe, registrar):
    for pessoa in equipe:
        registrar(pessoa)
    primeira = Rodada.objects.get(numero=1)
    fechada_em = primeira.fechada_em

    assert fechar_rodada_se_completa(primeira) is False
    assert fechar_rodada_se_completa(primeira) is False

    primeira.refresh_from_db()
    assert primeira.fechada_em == fechada_em
    assert Rodada.objects.count() == 2
    assert Rodada.objects.filter(fechada_em__isnull=True).count() == 1


# 10. Restricoes do banco


def test_banco_recusa_duas_rodadas_abertas():
    Rodada.objects.create(numero=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        Rodada.objects.create(numero=2)


def test_banco_aceita_varias_rodadas_fechadas():
    Rodada.objects.create(numero=1, fechada_em=timezone.now())
    Rodada.objects.create(numero=2, fechada_em=timezone.now())
    Rodada.objects.create(numero=3)

    assert Rodada.objects.count() == 3


def test_banco_recusa_numero_de_rodada_repetido():
    Rodada.objects.create(numero=1, fechada_em=timezone.now())

    with pytest.raises(IntegrityError), transaction.atomic():
        Rodada.objects.create(numero=1, fechada_em=timezone.now())


def test_banco_recusa_duas_trocas_do_mesmo_titular_na_rodada(equipe, registrar):
    registrar(equipe[0])

    with pytest.raises(IntegrityError), transaction.atomic():
        registrar(equipe[0])


# 11. Validacoes de Troca


def nova_troca(titular, executor, registrada_por):
    return Troca(
        rodada=rodada_atual(),
        titular=titular,
        executor=executor,
        registrada_por=registrada_por,
    )


def erros_de(troca):
    with pytest.raises(ValidationError) as erro:
        troca.full_clean()
    return erro.value.message_dict


def test_troca_valida_passa_na_validacao(equipe, admin_usuario):
    nova_troca(equipe[0], equipe[0], admin_usuario).full_clean()


def test_recusa_titular_fora_da_fila(equipe, admin_usuario):
    erros = erros_de(nova_troca(admin_usuario, admin_usuario, admin_usuario))

    assert "titular" in erros


def test_recusa_titular_inativo(equipe, admin_usuario):
    equipe[0].is_active = False
    equipe[0].save()

    erros = erros_de(nova_troca(equipe[0], equipe[1], admin_usuario))

    assert "titular" in erros


def test_recusa_executor_inativo(equipe, admin_usuario):
    equipe[1].is_active = False
    equipe[1].save()

    erros = erros_de(nova_troca(equipe[0], equipe[1], admin_usuario))

    assert "executor" in erros


def test_recusa_titular_repetido_na_rodada(equipe, admin_usuario, registrar):
    registrar(equipe[0])

    erros = erros_de(nova_troca(equipe[0], equipe[0], admin_usuario))

    assert "titular" in erros


def test_titular_da_rodada_anterior_pode_trocar_na_nova(
    equipe, admin_usuario, registrar
):
    for pessoa in equipe:
        registrar(pessoa)

    nova_troca(equipe[0], equipe[0], admin_usuario).full_clean()
