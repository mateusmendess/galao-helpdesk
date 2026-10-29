"""Rodizio sem banco: cada teste escreve a fila e o resultado esperado.

Pessoa N tem id 10 + N (ids diferentes das ordens, de proposito).
"""

from datetime import timedelta

import pytest

from escala.calculo import ConfiguracaoInvalida, cursor_inicial, projetar

from .conftest import SABADO


def s(k):
    """k-esimo sabado a partir de SABADO (s(0) = SABADO)."""
    return SABADO + timedelta(weeks=k)


def fila_de(*ordens):
    return [(ordem, 10 + ordem) for ordem in ordens]


def rodar(fila, cursor, quantos, ausencias=(), sem_escala=None, duas=()):
    return projetar(
        fila,
        cursor,
        [s(k) for k in range(quantos)],
        list(ausencias),
        sem_escala or {},
        set(duas),
    )


def manhas(dias):
    return [dia.manha for dia in dias]


def test_1_sequencia_simples_e_volta_ao_inicio():
    dias = rodar(fila_de(1, 2, 3), 0, 5)

    assert manhas(dias) == [11, 12, 13, 11, 12]
    assert [dia.tarde for dia in dias] == [None] * 5
    assert [dia.cursor_depois for dia in dias] == [1, 2, 3, 1, 2]
    assert [dia.vagas for dia in dias] == [1] * 5
    assert all(dia.pulados == () and not dia.sem_escala for dia in dias)


def test_2_comeca_pelo_primeiro_no_meio_da_fila():
    fila = fila_de(1, 2, 3, 4, 5)

    cursor = cursor_inicial(fila, 13)
    dias = rodar(fila, cursor, 4)

    assert cursor == 2
    assert manhas(dias) == [13, 14, 15, 11]


def test_3_sabado_com_2_pessoas_gasta_2():
    dias = rodar(fila_de(1, 2, 3, 4, 5), 0, 3, duas={s(1)})

    assert [(d.manha, d.tarde, d.vagas) for d in dias] == [
        (11, None, 1),
        (12, 13, 2),
        (14, None, 1),
    ]
    assert [d.cursor_depois for d in dias] == [1, 3, 4]


def test_4_ausente_na_vez_nao_volta_para_a_frente():
    # Pessoa 3 ausente so no 3o sabado (a vez dela): escala a 4; no sabado
    # seguinte (3 ja presente) a vez e da 5; a 3 so na proxima volta.
    dias = rodar(fila_de(1, 2, 3, 4, 5, 6, 7), 0, 9, ausencias=[(13, s(2), s(2))])

    assert manhas(dias) == [11, 12, 14, 15, 16, 17, 11, 12, 13]
    assert dias[2].pulados == (13,)
    assert [d.pulados for d in dias if d is not dias[2]] == [()] * 8


def test_5_ausente_na_segunda_vaga():
    dias = rodar(fila_de(1, 2, 3, 4), 0, 2, ausencias=[(12, s(0), s(0))], duas={s(0)})

    assert (dias[0].manha, dias[0].tarde, dias[0].pulados) == (11, 13, (12,))
    assert dias[0].cursor_depois == 3
    assert dias[1].manha == 14


def test_6_so_uma_presente_com_2_vagas_deixa_a_tarde_vazia():
    ausencias = [(12, s(0), s(0)), (13, s(0), s(0))]

    dias = rodar(fila_de(1, 2, 3), 0, 2, ausencias=ausencias, duas={s(0)})

    assert (dias[0].manha, dias[0].tarde, dias[0].pulados) == (11, None, (12, 13))
    assert dias[0].cursor_depois == 3
    assert dias[1].manha == 11


def test_7_todos_ausentes():
    ausencias = [(10 + n, s(0), s(0)) for n in (1, 2, 3)]

    dias = rodar(fila_de(1, 2, 3), 1, 2, ausencias=ausencias)

    assert (dias[0].manha, dias[0].tarde) == (None, None)
    assert dias[0].pulados == (12, 13, 11)
    # O cursor termina na ultima varrida: o proximo comeca na mesma partida.
    assert dias[0].cursor_depois == 1
    assert dias[1].manha == 12


def test_8_sem_escala_passando_para_o_proximo_nao_gasta():
    dias = rodar(fila_de(1, 2, 3), 0, 3, sem_escala={s(1): ("feriado", True)})

    assert manhas(dias) == [11, None, 12]
    feriado = dias[1]
    assert (feriado.sem_escala, feriado.motivo, feriado.passa_para_proximo) == (
        True,
        "feriado",
        True,
    )
    assert (feriado.tarde, feriado.pulados, feriado.cursor_depois) == (None, (), 1)


def test_9_sem_escala_sem_passar_gasta_a_vez():
    dias = rodar(fila_de(1, 2, 3), 0, 3, sem_escala={s(1): ("imprevisto", False)})

    assert manhas(dias) == [11, None, 13]
    assert (dias[1].sem_escala, dias[1].motivo, dias[1].passa_para_proximo) == (
        True,
        "imprevisto",
        False,
    )
    assert dias[1].cursor_depois == 2


def test_9b_sem_escala_sem_passar_tambem_pula_ausente():
    dias = rodar(
        fila_de(1, 2, 3),
        0,
        2,
        ausencias=[(11, s(0), s(0))],
        sem_escala={s(0): ("outro", False)},
    )

    assert (dias[0].manha, dias[0].pulados, dias[0].cursor_depois) == (None, (11,), 2)
    assert dias[1].manha == 13


def test_10_fila_mudou_cursor_por_ordem():
    # Antes: ordens 1, 2 e 4 (buraco no 3). Dois sabados: 1 e 2.
    antes = rodar(fila_de(1, 2, 4), 0, 2)
    assert manhas(antes) == [11, 12]
    cursor = antes[-1].cursor_depois
    assert cursor == 2

    # Depois: entra a ordem 3 e a ordem 2 fica inativa (sai da fila).
    depois = projetar(
        [(1, 11), (3, 13), (4, 14)], cursor, [s(2), s(3), s(4)], [], {}, set()
    )

    assert manhas(depois) == [13, 14, 11]


def test_11_fila_de_uma_pessoa():
    dias = rodar(fila_de(5), 0, 3, duas={s(1)})

    assert [(d.manha, d.tarde) for d in dias] == [(15, None), (15, None), (15, None)]
    assert [d.cursor_depois for d in dias] == [5, 5, 5]


def test_12_ausencia_com_limites_no_proprio_sabado():
    ausencias = [
        (11, s(0), s(0)),  # comeca e termina no sabado
        (13, s(0) - timedelta(days=3), s(1)),  # termina no sabado seguinte
        (12, s(2) + timedelta(days=1), None),  # comeca no domingo depois
    ]

    dias = rodar(fila_de(1, 2, 3), 0, 3, ausencias=ausencias)

    assert manhas(dias) == [12, 11, 12]
    assert [d.pulados for d in dias] == [(11,), (13,), ()]


def test_12b_ausencia_em_aberto_vale_para_sempre():
    dias = rodar(fila_de(1, 2), 0, 3, ausencias=[(12, s(1), None)])

    assert manhas(dias) == [11, 11, 11]
    assert [d.pulados for d in dias] == [(), (12,), (12,)]


def test_13_fila_vazia_e_primeiro_fora_da_fila():
    with pytest.raises(ConfiguracaoInvalida, match="Ninguém está na escala"):
        projetar([], 0, [s(0)], [], {}, set())
    with pytest.raises(ConfiguracaoInvalida, match="Ninguém está na escala"):
        cursor_inicial([], 11)
    with pytest.raises(ConfiguracaoInvalida, match="não está na escala"):
        cursor_inicial(fila_de(1, 2), 99)
