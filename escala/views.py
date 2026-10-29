from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from . import datas
from .models import ConfiguracaoEscala


@login_required
@require_safe
def pagina(request):
    # Ainda sem lista (pedido 17b): so diz se a escala esta ligada.
    configuracao = ConfiguracaoEscala.obter()
    contexto = {
        "configuracao": configuracao,
        "comecou": configuracao is not None and datas.hoje() >= configuracao.inicio,
    }
    return render(request, "escala/pagina.html", contexto)
