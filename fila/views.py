from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_safe

from .forms import RegistrarTrocaForm
from .models import Troca
from .regras import VezMudou, de_quem_e_a_vez, nome_de_exibicao, registrar_troca

NINGUEM_DISPONIVEL = "Ninguém disponível agora."
TROCAS_POR_PAGINA = 30


def descrever(troca):
    executor = nome_de_exibicao(troca.executor)
    if troca.executor_id == troca.titular_id:
        return f"{executor} trocou o galão"
    return f"{executor} trocou no lugar de {nome_de_exibicao(troca.titular)}"


@login_required
@require_http_methods(["GET", "POST"])
def registrar(request):
    vez = de_quem_e_a_vez()
    if vez is None:
        messages.error(request, NINGUEM_DISPONIVEL)
        return redirect("home")

    form = RegistrarTrocaForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        esperado = (
            get_user_model().objects.filter(pk=form.cleaned_data["titular"]).first()
        )
        try:
            troca = registrar_troca(
                esperado,
                form.executor_escolhido(),
                request.user,
                form.cleaned_data["observacao"],
            )
        except VezMudou as erro:
            if erro.vez is None:
                messages.error(request, NINGUEM_DISPONIVEL)
            else:
                messages.error(
                    request,
                    "A vez mudou enquanto você preenchia: agora é de "
                    f"{nome_de_exibicao(erro.vez)}. Confira e tente de novo.",
                )
            return redirect("home")
        except ValidationError as erro:
            form.add_error(None, erro)
        else:
            messages.success(request, f"Troca registrada: {descrever(troca)}.")
            return redirect("home")

    return render(request, "fila/registrar.html", {"form": form, "vez": vez})


@login_required
@require_safe
def historico(request):
    trocas = Troca.objects.select_related(
        "rodada", "titular", "executor", "registrada_por"
    ).order_by("-data_hora", "-id")
    pagina = Paginator(trocas, TROCAS_POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(
        request, "fila/historico.html", {"pagina": pagina, "grupos": agrupar(pagina)}
    )


def agrupar(pagina):
    """Trocas da pagina agrupadas por rodada, na ordem em que ja vieram.

    Cada grupo leva o total de trocas da rodada inteira (nao so da pagina),
    contado numa unica consulta agregada. Trocas de uma rodada que nao ficam
    em sequencia (data lancada a mao no admin) formam outro grupo com o mesmo
    titulo.
    """
    trocas = list(pagina.object_list)
    rodadas = {troca.rodada_id for troca in trocas}
    totais = dict(
        Troca.objects.filter(rodada_id__in=rodadas)
        .order_by()
        .values_list("rodada_id")
        .annotate(total=Count("id"))
    )
    grupos = []
    for troca in trocas:
        if not grupos or grupos[-1]["rodada"].pk != troca.rodada_id:
            grupos.append(
                {"rodada": troca.rodada, "total": totais[troca.rodada_id], "trocas": []}
            )
        grupos[-1]["trocas"].append(troca)
    return grupos
