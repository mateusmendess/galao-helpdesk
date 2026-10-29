from datetime import datetime, time, timedelta

from django.utils import timezone

# O sabado termina quando acaba o turno da tarde (13h as 17h).
FIM_DO_SABADO = time(17, 0)
SABADO = 5  # date.weekday(): segunda = 0 ... sabado = 5


def agora():
    """Data e hora locais (fuso do projeto, com fuso). Todo codigo da escala
    pega a hora por aqui (os testes trocam com patch em escala.datas.agora)."""
    return timezone.localtime()


def hoje():
    """Data de hoje no fuso do projeto."""
    return agora().date()


def sabado_terminou(data):
    """Verdadeiro a partir das 17h (hora local) do sabado `data`."""
    return agora() >= timezone.make_aware(datetime.combine(data, FIM_DO_SABADO))


def primeiro_sabado_aberto():
    """O primeiro sabado que ainda nao terminou (o de hoje, ate as 17h)."""
    dia = hoje()
    sabado = dia + timedelta(days=(SABADO - dia.weekday()) % 7)
    if sabado_terminou(sabado):
        sabado += timedelta(days=7)
    return sabado
