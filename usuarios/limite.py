"""Limite de tentativas de login por e-mail, guardado no banco."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import FalhaLogin


def normalizar_email(email):
    return (email or "").strip().lower()


def _inicio_da_janela():
    return timezone.now() - timedelta(minutes=settings.LOGIN_JANELA_MINUTOS)


def esta_bloqueado(email):
    email = normalizar_email(email)
    if not email:
        return False
    falhas = FalhaLogin.objects.filter(email=email, criada_em__gte=_inicio_da_janela())
    return falhas.count() >= settings.LOGIN_MAX_TENTATIVAS


def registrar_falha(email):
    email = normalizar_email(email)
    if not email:
        return
    # Apaga de passagem o que ja saiu da janela, para a tabela nao crescer.
    FalhaLogin.objects.filter(criada_em__lt=_inicio_da_janela()).delete()
    FalhaLogin.objects.create(email=email)


def limpar_falhas(email):
    FalhaLogin.objects.filter(email=normalizar_email(email)).delete()
