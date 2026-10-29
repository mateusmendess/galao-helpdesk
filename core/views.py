from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from fila.models import Troca
from fila.regras import (
    AGUARDANDO,
    TROCOU,
    VEZ,
    ausencias_de_hoje,
    rodada_atual,
    saldos_devendo,
    situacao_da_fila,
)
from fila.views import descrever


@require_safe
def home(request):
    # Quem nao entrou ve a pagina publica: estatica, nao le nada do banco.
    if not request.user.is_authenticated:
        return render(request, "publica/inicio.html")
    # Abre a primeira rodada se ainda nao houver (escrita idempotente no GET).
    # Uma consulta de ausencias serve para a vez, o fechamento e o "ate DD/MM".
    ausencias = ausencias_de_hoje()
    ausentes = set(ausencias)
    rodada = rodada_atual(ausentes)
    posicoes = situacao_da_fila(rodada, ausentes)
    vez = next((p.usuario for p in posicoes if p.estado == VEZ), None)
    # Progresso da rodada (o "nivel do galao"), das posicoes ja carregadas:
    # presentes = quem a rodada ainda espera (trocou, vez ou aguardando); quem
    # ja trocou conta mesmo se ausente. Pulado e ausente nao contam.
    presentes = sum(1 for p in posicoes if p.estado in (TROCOU, VEZ, AGUARDANDO))
    trocaram = sum(1 for p in posicoes if p.estado == TROCOU)
    saldos = saldos_devendo()
    ultima = (
        Troca.objects.select_related("titular", "executor")
        .order_by("-data_hora", "-id")
        .first()
    )
    contexto = {
        "rodada": rodada,
        "posicoes": posicoes,
        # Cada pessoa da fila com quanto deve (0 = nao mostra a marca) e, se
        # ausente, ate quando (None = em aberto).
        "linhas": [
            (p, saldos.get(p.usuario.pk, 0), ausencias.get(p.usuario)) for p in posicoes
        ],
        "vez": vez,
        "presentes": presentes,
        "trocaram": trocaram,
        # Um segmento por presente: True = ja trocou.
        "segmentos": [True] * trocaram + [False] * (presentes - trocaram),
        "ultima": ultima,
        "ultima_texto": descrever(ultima) if ultima else "",
    }
    return render(request, "core/home.html", contexto)


@require_safe
def saude(request):
    # Healthcheck do Railway: sem login, sem banco, so GET/HEAD.
    return HttpResponse("ok", content_type="text/plain")
