"""Trocas de sabado por cima do calculo (calculo.py nao muda).

Quem tem o turno = resultado do calculo (ou do sabado gravado) + trocas
ativas aplicadas em ordem de registro. `aplicar` e a unica funcao que faz
isso; telas e validacoes passam por ela.
"""

from dataclasses import dataclass, replace
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from fila.models import Ausencia
from fila.regras import nome_de_exibicao

from . import datas
from .calculo import Dia, calendario, congelar_passados
from .models import ConfiguracaoEscala, SabadoFechado, TrocaSabado

MANHA = TrocaSabado.Turno.MANHA
TARDE = TrocaSabado.Turno.TARDE
TURNOS = (MANHA, TARDE)
ESCALA_MUDOU = "A escala mudou enquanto você preenchia."
DESFACA_A_MAIS_RECENTE = "Desfaça antes a troca mais recente que mexe nesse sábado."


@dataclass(frozen=True)
class DiaComTroca:
    """Um sabado depois das trocas (`dia`) e como o calculo deixou (`antes`)."""

    dia: Dia
    antes: Dia

    def dono(self, turno):
        return getattr(self.dia, turno)

    def no_lugar_de(self, turno):
        """Quem o calculo tinha escalado, se uma troca mudou o turno."""
        atual, original = getattr(self.dia, turno), getattr(self.antes, turno)
        return original if atual != original else None

    @property
    def trocado(self):
        return any(self.no_lugar_de(turno) for turno in TURNOS)


def eh_admin(usuario):
    return usuario.is_staff and usuario.is_superuser


def aplicar(dias, trocas=None):
    """Aplica as trocas ativas (em ordem de registro) aos sabados `dias`.

    `trocas` permite passar trocas ja buscadas (ou simuladas); sem ela, busca
    numa consulta so as ativas que tocam essas datas.
    """
    datas_dos_dias = [dia.data for dia in dias]
    if trocas is None:
        trocas = (
            TrocaSabado.objects.filter(desfeita_em__isnull=True)
            .filter(Q(data_a__in=datas_dos_dias) | Q(data_b__in=datas_dos_dias))
            .select_related("pessoa_a", "pessoa_b")
            .order_by("id")
        )
    donos = {(dia.data, t): getattr(dia, t) for dia in dias for t in TURNOS}
    for troca in trocas:
        # Mesmo que o calculo tenha mudado depois, a troca vale como registrada.
        if (troca.data_a, troca.turno_a) in donos:
            donos[(troca.data_a, troca.turno_a)] = troca.pessoa_b
        if (troca.data_b, troca.turno_b) in donos:
            donos[(troca.data_b, troca.turno_b)] = troca.pessoa_a
    return [
        DiaComTroca(
            dia=replace(
                dia, manha=donos[(dia.data, MANHA)], tarde=donos[(dia.data, TARDE)]
            ),
            antes=dia,
        )
        for dia in dias
    ]


def calendario_com_trocas(quantidade):
    """calendario() com as trocas aplicadas (numero fixo de consultas)."""
    return aplicar(calendario(quantidade))


def _de_fechado(fechado):
    return Dia(
        data=fechado.data,
        manha=fechado.manha,
        tarde=fechado.tarde,
        sem_escala=fechado.sem_escala,
        motivo=fechado.motivo,
        passa_para_proximo=fechado.passa_para_proximo,
        vagas=fechado.vagas,
        cursor_depois=fechado.cursor_depois,
    )


def sabados_em(datas_pedidas):
    """{data: DiaComTroca} das datas pedidas que existem na escala: gravadas
    (ja terminadas) ou previstas (do primeiro sabado aberto em diante)."""
    congelar_passados()
    pedidas = set(datas_pedidas)
    dias = [
        _de_fechado(f)
        for f in SabadoFechado.objects.filter(data__in=pedidas).select_related(
            "manha", "tarde"
        )
    ]
    abertas = [d for d in pedidas if d not in {dia.data for dia in dias}]
    if abertas:
        primeiro = datas.primeiro_sabado_aberto()
        semanas = (max(abertas) - primeiro).days // 7 + 1
        if semanas > 0:
            dias += [dia for dia in calendario(semanas) if dia.data in pedidas]
    return {item.dia.data: item for item in aplicar(dias)}


def _ausente(usuario, data):
    return (
        Ausencia.objects.filter(usuario=usuario, inicio__lte=data)
        .filter(Q(fim__isnull=True) | Q(fim__gte=data))
        .exists()
    )


def _outro(turno):
    return TARDE if turno == MANHA else MANHA


def registrar_troca(
    pessoa_a, data_a, turno_a, pessoa_b, data_b, turno_b, por, tipo=None
):
    """Registra a troca: (data_a, turno_a) de pessoa_a vai para pessoa_b e
    (data_b, turno_b) de pessoa_b vai para pessoa_a. Tudo e conferido dentro
    da transacao; erro = ValidationError com mensagem em portugues."""
    tipo = tipo or TrocaSabado.Tipo.COMBINADA
    if turno_a not in TURNOS or turno_b not in TURNOS:
        raise ValidationError("Escolha manhã ou tarde.")
    if tipo not in TrocaSabado.Tipo.values:
        raise ValidationError("Tipo de troca inválido.")
    if pessoa_a.pk == pessoa_b.pk:
        raise ValidationError("A troca precisa ser entre duas pessoas diferentes.")
    if data_a == data_b:
        raise ValidationError("Escolha dois sábados diferentes.")
    if not eh_admin(por):
        if por.pk not in (pessoa_a.pk, pessoa_b.pk):
            raise ValidationError("Você só pode registrar trocas suas.")
        if tipo != TrocaSabado.Tipo.COMBINADA:
            raise ValidationError("Só um admin registra troca de emergência.")
        hoje = datas.hoje()
        if not (data_a > hoje and data_b > hoje):
            raise ValidationError(
                "Só dá para trocar sábados que ainda não chegaram. "
                "No dia, fale com um admin."
            )

    with transaction.atomic():
        # Trava a configuracao: dois registros ao mesmo tempo entram em fila.
        ConfiguracaoEscala.objects.select_for_update().filter(pk=1).first()
        sabados = sabados_em([data_a, data_b])
        lado_a, lado_b = sabados.get(data_a), sabados.get(data_b)
        for lado in (lado_a, lado_b):
            if lado is None or lado.dia.sem_escala:
                raise ValidationError("Esse sábado não tem escala para trocar.")
        if lado_a.dono(turno_a) is None or lado_b.dono(turno_b) is None:
            raise ValidationError("Esse turno não tem ninguém escalado.")
        if lado_a.dono(turno_a) != pessoa_a or lado_b.dono(turno_b) != pessoa_b:
            raise ValidationError(ESCALA_MUDOU)
        # Ninguem duas vezes no mesmo sabado, ninguem numa data em que falta.
        for quem, data, lado, turno in (
            (pessoa_b, data_a, lado_a, turno_a),
            (pessoa_a, data_b, lado_b, turno_b),
        ):
            if lado.dono(_outro(turno)) == quem:
                raise ValidationError(
                    f"{nome_de_exibicao(quem)} já está na escala de {data:%d/%m}."
                )
            if _ausente(quem, data):
                raise ValidationError(
                    f"{nome_de_exibicao(quem)} está ausente em {data:%d/%m}."
                )
        return TrocaSabado.objects.create(
            pessoa_a=pessoa_a,
            data_a=data_a,
            turno_a=turno_a,
            pessoa_b=pessoa_b,
            data_b=data_b,
            turno_b=turno_b,
            tipo=tipo,
            registrada_por=por,
            registrada_em=datas.agora(),
        )


def ultimo_dia_para_desfazer(troca):
    """Ate quando o membro desfaz: a vespera do primeiro sabado da troca."""
    return min(troca.data_a, troca.data_b) - timedelta(days=1)


def pode_desfazer(troca, usuario):
    """Permissao (sem olhar trocas mais recentes): admin sempre; membro so se
    participa e hoje() e antes do primeiro sabado da troca."""
    if not troca.ativa:
        return False
    if eh_admin(usuario):
        return True
    return usuario.pk in (troca.pessoa_a_id, troca.pessoa_b_id) and datas.hoje() < min(
        troca.data_a, troca.data_b
    )


def desfazer_troca(troca, por):
    """Desfaz a troca (fica no historico). Erro = ValidationError."""
    with transaction.atomic():
        ConfiguracaoEscala.objects.select_for_update().filter(pk=1).first()
        troca = TrocaSabado.objects.get(pk=troca.pk)
        if not troca.ativa:
            raise ValidationError("Essa troca já foi desfeita.")
        if not pode_desfazer(troca, por):
            if por.pk not in (troca.pessoa_a_id, troca.pessoa_b_id):
                raise ValidationError(
                    "Só quem participa da troca (ou um admin) pode desfazê-la."
                )
            raise ValidationError(
                "O prazo para desfazer esta troca acabou. Fale com um admin."
            )
        turnos = Q()
        for data, turno in (
            (troca.data_a, troca.turno_a),
            (troca.data_b, troca.turno_b),
        ):
            turnos |= Q(data_a=data, turno_a=turno) | Q(data_b=data, turno_b=turno)
        if (
            TrocaSabado.objects.filter(desfeita_em__isnull=True, id__gt=troca.id)
            .filter(turnos)
            .exists()
        ):
            raise ValidationError(DESFACA_A_MAIS_RECENTE)
        troca.desfeita_em = datas.agora()
        troca.desfeita_por = por
        troca.save(update_fields=["desfeita_em", "desfeita_por"])
        return troca


def situacao(troca):
    """ "ativa", "feita" (ativa com as duas datas terminadas) ou "desfeita"."""
    if not troca.ativa:
        return "desfeita"
    if datas.sabado_terminou(max(troca.data_a, troca.data_b)):
        return "feita"
    return "ativa"
