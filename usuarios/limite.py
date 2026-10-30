"""Limite de tentativas de login por pessoa, guardado no banco."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import FalhaLogin, Usuario


def normalizar_email(email):
    return (email or "").strip().lower()


def chave_de_bloqueio(identificador):
    """E-mail do dono da matricula ou do e-mail digitado; senao, o texto digitado.

    Assim os erros pela matricula e pelo e-mail da mesma pessoa contam juntos.
    """
    try:
        return Usuario.objects.por_identificador(identificador).email
    except Usuario.DoesNotExist:
        return normalizar_email(identificador)


def _inicio_da_janela():
    return timezone.now() - timedelta(minutes=settings.LOGIN_JANELA_MINUTOS)


def esta_bloqueado(identificador):
    email = chave_de_bloqueio(identificador)
    if not email:
        return False
    falhas = FalhaLogin.objects.filter(email=email, criada_em__gte=_inicio_da_janela())
    return falhas.count() >= settings.LOGIN_MAX_TENTATIVAS


def registrar_falha(identificador):
    email = chave_de_bloqueio(identificador)
    if not email:
        return
    # Apaga de passagem o que ja saiu da janela, para a tabela nao crescer.
    FalhaLogin.objects.filter(criada_em__lt=_inicio_da_janela()).delete()
    FalhaLogin.objects.create(email=email)


def limpar_falhas(email):
    FalhaLogin.objects.filter(email=normalizar_email(email)).delete()
