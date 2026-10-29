from django.utils import timezone


def hoje():
    """Data de hoje no fuso do sistema. Todo codigo da escala usa esta funcao
    (os testes trocam a data com patch em escala.datas.hoje)."""
    return timezone.localdate()
