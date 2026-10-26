from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from fila.models import Troca
from fila.regras import VEZ, rodada_atual, saldos_devendo, situacao_da_fila
from fila.views import descrever


@login_required
@require_safe
def home(request):
    # Abre a primeira rodada se ainda nao houver (escrita idempotente no GET).
    rodada = rodada_atual()
    posicoes = situacao_da_fila(rodada)
    vez = next((p.usuario for p in posicoes if p.estado == VEZ), None)
    saldos = saldos_devendo()
    ultima = (
        Troca.objects.select_related("titular", "executor")
        .order_by("-data_hora", "-id")
        .first()
    )
    contexto = {
        "rodada": rodada,
        "posicoes": posicoes,
        # Cada pessoa da fila com quanto deve (0 = nao mostra a marca).
        "linhas": [(p, saldos.get(p.usuario.pk, 0)) for p in posicoes],
        "vez": vez,
        "ultima": ultima,
        "ultima_texto": descrever(ultima) if ultima else "",
    }
    return render(request, "core/home.html", contexto)


@require_safe
def saude(request):
    # Healthcheck do Railway: sem login, sem banco, so GET/HEAD.
    return HttpResponse("ok", content_type="text/plain")
