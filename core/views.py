from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from fila.regras import VEZ, rodada_atual, situacao_da_fila


@login_required
def home(request):
    # Abre a primeira rodada se ainda nao houver (escrita idempotente no GET).
    rodada = rodada_atual()
    posicoes = situacao_da_fila(rodada)
    vez = next((p.usuario for p in posicoes if p.estado == VEZ), None)
    contexto = {"rodada": rodada, "posicoes": posicoes, "vez": vez}
    return render(request, "core/home.html", contexto)


@require_safe
def saude(request):
    # Healthcheck do Railway: sem login, sem banco, so GET/HEAD.
    return HttpResponse("ok", content_type="text/plain")
