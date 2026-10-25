"""Regras da fila: rodada atual, de quem e a vez e fechamento da rodada."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from .models import Rodada, Troca

TROCOU = "trocou"
VEZ = "vez"
AGUARDANDO = "aguardando"
AUSENTE = "ausente"


@dataclass(frozen=True)
class Posicao:
    usuario: object
    estado: str


def nome_de_exibicao(usuario):
    """Primeiro nome; se estiver vazio, o e-mail."""
    return usuario.first_name or usuario.email


def _rodada_aberta():
    """A rodada aberta; se nao houver, abre a proxima (1 na primeira vez)."""
    rodada = Rodada.objects.filter(fechada_em__isnull=True).first()
    if rodada is not None:
        return rodada
    try:
        with transaction.atomic():
            maior = Rodada.objects.aggregate(maior=Max("numero"))["maior"] or 0
            return Rodada.objects.create(numero=maior + 1)
    except IntegrityError:
        # Outra requisicao abriu ao mesmo tempo: o banco recusou a segunda
        # rodada aberta, entao usamos a dela.
        return Rodada.objects.get(fechada_em__isnull=True)


def rodada_atual(ausentes=None):
    """A rodada aberta, ja conferida: se ela esta completa, fecha e devolve a nova.

    Cobre a rodada que completou sem uma troca nova (ex.: o ultimo que faltava
    foi desativado). Uma rodada recem-aberta nunca esta completa, entao isso
    fecha no maximo uma vez por chamada.
    """
    rodada = _rodada_aberta()
    if fechar_rodada_se_completa(rodada, ausentes):
        return _rodada_aberta()
    return rodada


def usuarios_da_fila():
    """Ativos com ordem preenchida, do 1 em diante."""
    return list(
        get_user_model()
        .objects.filter(is_active=True, ordem__isnull=False)
        .order_by("ordem")
    )


def ausentes_hoje():
    """Quem esta ausente hoje. Vazio por enquanto: o modulo 5 implementa."""
    return set()


def situacao_da_fila(rodada=None, ausentes=None):
    """Cada pessoa da fila, na ordem, com o estado dela na rodada."""
    if ausentes is None:
        ausentes = ausentes_hoje()
    if rodada is None:
        rodada = rodada_atual(ausentes)
    trocaram = set(
        Troca.objects.filter(rodada=rodada).values_list("titular_id", flat=True)
    )
    posicoes = []
    vez_ja_dada = False
    for usuario in usuarios_da_fila():
        if usuario.pk in trocaram:
            estado = TROCOU
        elif usuario in ausentes:
            estado = AUSENTE
        elif not vez_ja_dada:
            estado = VEZ
            vez_ja_dada = True
        else:
            estado = AGUARDANDO
        posicoes.append(Posicao(usuario, estado))
    return posicoes


def de_quem_e_a_vez(rodada=None, ausentes=None):
    """O primeiro da fila que nao trocou e nao esta ausente, ou None."""
    for posicao in situacao_da_fila(rodada, ausentes):
        if posicao.estado == VEZ:
            return posicao.usuario
    return None


def fechar_rodada_se_completa(rodada, ausentes=None):
    """Fecha a rodada e abre a proxima se todos os presentes ja trocaram.

    Devolve True se fechou. Trava a linha da rodada (no PostgreSQL; no SQLite
    o select_for_update nao faz nada e a escrita ja e serializada), entao duas
    trocas ao mesmo tempo nao fecham duas vezes.
    """
    if ausentes is None:
        ausentes = ausentes_hoje()
    with transaction.atomic():
        rodada = Rodada.objects.select_for_update().get(pk=rodada.pk)
        if rodada.fechada_em is not None:
            return False
        presentes = [u for u in usuarios_da_fila() if u not in ausentes]
        if not presentes:
            return False
        trocaram = set(rodada.trocas.values_list("titular_id", flat=True))
        if any(u.pk not in trocaram for u in presentes):
            return False
        rodada.fechada_em = timezone.now()
        rodada.save(update_fields=["fechada_em"])
        Rodada.objects.create(numero=rodada.numero + 1)
        return True
