"""Rodizio da escala de sabado: quem e escalado em cada sabado.

Parte pura (sem banco): `projetar` recebe a fila, o cursor e os cadastros e
devolve um `Dia` por sabado. Parte com banco: `congelar_passados` grava os
sabados que ja passaram (que nunca mais mudam) e `calendario` devolve a
previsao de hoje em diante.

A fila (pessoas ativas com posicao na escala, em ordem) so anda para a frente.
O cursor guarda a ORDEM (ordem_escala) da ultima pessoa vista, nao a posicao
na lista: assim a fila pode ganhar ou perder pessoas sem quebrar.
"""

from dataclasses import dataclass, replace
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q

from fila.models import Ausencia

from . import datas
from .models import (
    ConfiguracaoEscala,
    SabadoDuasPessoas,
    SabadoFechado,
    SabadoSemEscala,
)

SEMANA = timedelta(days=7)
TENTATIVAS = 3


class ConfiguracaoInvalida(Exception):
    """A escala nao tem como andar (mensagem em portugues para a tela)."""


@dataclass(frozen=True)
class Dia:
    """Um sabado. manha/tarde/pulados sao ids de usuario (ou None) na parte
    pura; `calendario` troca pelos objetos Usuario."""

    data: object
    manha: object = None
    tarde: object = None
    pulados: tuple = ()
    sem_escala: bool = False
    motivo: str = ""
    passa_para_proximo: bool = False
    vagas: int = 1
    cursor_depois: int = 0


# Parte pura


def cursor_inicial(fila, primeiro_id):
    """Ordem do `primeiro` menos 1: a primeira pessoa escolhida e ele."""
    if not fila:
        raise ConfiguracaoInvalida(
            "Ninguém está na escala: dê uma posição na escala a pelo menos "
            "uma pessoa ativa."
        )
    for ordem, usuario_id in fila:
        if usuario_id == primeiro_id:
            return ordem - 1
    raise ConfiguracaoInvalida(
        "O primeiro da fila da configuração não está na escala (está inativo "
        "ou sem posição na escala)."
    )


def _ausente(periodos, usuario_id, data):
    # Ausencia vale do inicio ao fim, inclusive; fim vazio = em aberto.
    return any(
        inicio <= data and (fim is None or fim >= data)
        for inicio, fim in periodos.get(usuario_id, ())
    )


def _varrer(fila, cursor, data, vagas, periodos):
    """Percorre a fila a partir do cursor (no maximo uma volta) ate encher as
    vagas. Devolve (escalados, pulados, cursor_depois).

    Cada pessoa vista move o cursor, escalada ou pulada por ausencia. Quem
    vem depois da ultima vaga nao e visto. Se todos estiverem ausentes,
    ninguem e escalado, todos vao para os pulados e o cursor termina na
    ultima pessoa varrida (a de antes da partida): o proximo sabado comeca
    de novo pela mesma pessoa.
    """
    # Proxima a partir do cursor: a menor ordem MAIOR que ele; senao, a 1a.
    partida = next((i for i, (ordem, _) in enumerate(fila) if ordem > cursor), 0)
    escalados, pulados = [], []
    for passo in range(len(fila)):
        if len(escalados) == vagas:
            break
        ordem, usuario_id = fila[(partida + passo) % len(fila)]
        cursor = ordem
        if _ausente(periodos, usuario_id, data):
            pulados.append(usuario_id)
        else:
            escalados.append(usuario_id)
    return escalados, pulados, cursor


def projetar(fila, cursor, sabados, ausencias, sem_escala, duas):
    """Um Dia por sabado, em ordem.

    fila: [(ordem_escala, usuario_id)]; ausencias: [(usuario_id, inicio, fim)];
    sem_escala: {data: (motivo, passa_para_proximo)}; duas: {data}.
    """
    if not fila:
        raise ConfiguracaoInvalida(
            "Ninguém está na escala: dê uma posição na escala a pelo menos "
            "uma pessoa ativa."
        )
    fila = sorted(fila)
    periodos = {}
    for usuario_id, inicio, fim in ausencias:
        periodos.setdefault(usuario_id, []).append((inicio, fim))

    dias = []
    for data in sabados:
        if data in sem_escala:
            motivo, passa = sem_escala[data]
            pulados = ()
            if not passa:
                # Gasta a vez (e pula ausentes) como num sabado normal, mas
                # ninguem trabalha.
                _, pulados, cursor = _varrer(fila, cursor, data, 1, periodos)
            # passa=True: nada e gasto; a mesma pessoa vai para o proximo.
            dias.append(
                Dia(
                    data=data,
                    pulados=tuple(pulados),
                    sem_escala=True,
                    motivo=motivo,
                    passa_para_proximo=passa,
                    vagas=1,
                    cursor_depois=cursor,
                )
            )
            continue
        vagas = 2 if data in duas else 1
        escalados, pulados, cursor = _varrer(fila, cursor, data, vagas, periodos)
        escalados += [None] * (2 - len(escalados))
        dias.append(
            Dia(
                data=data,
                manha=escalados[0],
                tarde=escalados[1],
                pulados=tuple(pulados),
                vagas=vagas,
                cursor_depois=cursor,
            )
        )
    return dias


# Parte com banco


def _fila():
    return list(
        get_user_model()
        .objects.filter(is_active=True, ordem_escala__isnull=False)
        .order_by("ordem_escala")
        .values_list("ordem_escala", "id")
    )


def estado_atual(config, fila=None):
    """(cursor, proximo sabado a calcular): do ultimo sabado congelado, ou do
    cursor inicial e do inicio da escala."""
    ultimo = SabadoFechado.objects.order_by("-data").first()
    if ultimo is not None:
        return ultimo.cursor_depois, ultimo.data + SEMANA
    if fila is None:
        fila = _fila()
    return cursor_inicial(fila, config.primeiro_id), config.inicio


def _sabados(primeiro, ate_antes_de):
    """Sabados de `primeiro` (um sabado) ate antes de `ate_antes_de`."""
    sabados = []
    data = primeiro
    while data < ate_antes_de:
        sabados.append(data)
        data += SEMANA
    return sabados


def _terminados(primeiro):
    """Sabados de `primeiro` em diante que ja terminaram (17h)."""
    sabados = []
    data = primeiro
    while datas.sabado_terminou(data):
        sabados.append(data)
        data += SEMANA
    return sabados


def _projetar_do_banco(fila, cursor, sabados):
    """projetar() com as ausencias e os cadastros do periodo (uma consulta
    para cada, qualquer que seja a quantidade de sabados)."""
    if not sabados:
        return []
    primeiro, ultimo = sabados[0], sabados[-1]
    ausencias = (
        Ausencia.objects.filter(inicio__lte=ultimo)
        .filter(Q(fim__isnull=True) | Q(fim__gte=primeiro))
        .values_list("usuario_id", "inicio", "fim")
    )
    sem_escala = {
        data: (motivo, passa)
        for data, motivo, passa in SabadoSemEscala.objects.filter(
            data__range=(primeiro, ultimo)
        ).values_list("data", "motivo", "passa_para_proximo")
    }
    duas = set(
        SabadoDuasPessoas.objects.filter(data__range=(primeiro, ultimo)).values_list(
            "data", flat=True
        )
    )
    return projetar(fila, cursor, sabados, list(ausencias), sem_escala, duas)


def congelar_passados():
    """Grava os sabados que ja terminaram (17h do proprio sabado) e ainda nao
    foram gravados, com os dados de agora. Devolve quantos gravou.

    Idempotente. Sabado nao terminado nunca e gravado. Se outro processo gravar
    uma das datas antes (data unica), desfaz o lote, rele e tenta de novo.
    """
    config = ConfiguracaoEscala.obter()
    if config is None or not datas.sabado_terminou(config.inicio):
        return 0
    for _ in range(TENTATIVAS):
        fila = _fila()
        cursor, proximo = estado_atual(config, fila)
        dias = _projetar_do_banco(fila, cursor, _terminados(proximo))
        if not dias:
            return 0
        try:
            with transaction.atomic():
                for dia in dias:
                    fechado = SabadoFechado.objects.create(
                        data=dia.data,
                        manha_id=dia.manha,
                        tarde_id=dia.tarde,
                        sem_escala=dia.sem_escala,
                        motivo=dia.motivo,
                        passa_para_proximo=dia.passa_para_proximo,
                        vagas=dia.vagas,
                        cursor_depois=dia.cursor_depois,
                    )
                    if dia.pulados:
                        fechado.pulados.set(dia.pulados)
        except IntegrityError:
            continue
        return len(dias)
    raise IntegrityError("Não foi possível congelar os sábados passados.")


def calendario(quantidade):
    """Os proximos `quantidade` sabados a partir do primeiro nao terminado (o
    de hoje entra ate as 17h) e do inicio, com objetos Usuario em manha,
    tarde e pulados.
    Lista vazia sem configuracao. Numero fixo de consultas."""
    congelar_passados()
    config = ConfiguracaoEscala.obter()
    if config is None or quantidade <= 0:
        return []
    alvo = max(datas.primeiro_sabado_aberto(), config.inicio)
    fila = _fila()
    cursor, proximo = estado_atual(config, fila)
    dias = _projetar_do_banco(
        fila, cursor, _sabados(proximo, alvo + quantidade * SEMANA)
    )
    dias = [dia for dia in dias if dia.data >= alvo][:quantidade]

    ids = {i for dia in dias for i in (dia.manha, dia.tarde, *dia.pulados) if i}
    usuarios = get_user_model().objects.in_bulk(ids) if ids else {}
    return [
        replace(
            dia,
            manha=usuarios.get(dia.manha),
            tarde=usuarios.get(dia.tarde),
            pulados=tuple(usuarios[i] for i in dia.pulados),
        )
        for dia in dias
    ]
