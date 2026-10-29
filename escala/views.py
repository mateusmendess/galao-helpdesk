from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from fila.regras import nome_de_exibicao

from . import datas
from .calculo import ConfiguracaoInvalida, calendario
from .models import ConfiguracaoEscala, SabadoSemEscala

QUANTOS = 9  # destaque + 6 na lista + 2 no "Ver mais"
NA_LISTA = 6
MOTIVOS = dict(SabadoSemEscala.Motivo.choices)


def _linha(dia):
    """Textos de um sabado da lista: nomes, observacoes e etiquetas."""
    escalados = [nome_de_exibicao(u) for u in (dia.manha, dia.tarde) if u]
    observacoes = []
    if dia.sem_escala:
        nomes = f"Sem escala · {MOTIVOS.get(dia.motivo, dia.motivo)}"
        if dia.passa_para_proximo:
            proximo = dia.data + timedelta(days=7)
            observacoes.append(f"Quem estava na vez passa para {proximo:%d/%m}")
    else:
        nomes = " e ".join(escalados) or "ninguém disponível"
    if dia.pulados:
        pulados = ", ".join(nome_de_exibicao(u) for u in dia.pulados)
        observacoes.append(f"Ausente, pulado: {pulados}")
    return {"dia": dia, "nomes": nomes, "observacoes": observacoes}


def _turno(usuario, eu):
    return {
        "nome": nome_de_exibicao(usuario) if usuario else "",
        "voce": usuario is not None and usuario.pk == eu.pk,
    }


@login_required
@require_safe
def pagina(request):
    configuracao = ConfiguracaoEscala.obter()
    contexto = {"configuracao": configuracao}
    if configuracao is not None:
        contexto["antes_do_inicio"] = datas.hoje() < configuracao.inicio
        try:
            dias = calendario(QUANTOS)
        except ConfiguracaoInvalida as erro:
            contexto["erro"] = str(erro)
        else:
            if dias:
                destaque = dias[0]
                contexto["destaque"] = {
                    **_linha(destaque),
                    "manha": _turno(destaque.manha, request.user),
                    "tarde": _turno(destaque.tarde, request.user),
                }
                contexto["lista"] = [_linha(dia) for dia in dias[1 : 1 + NA_LISTA]]
                contexto["mais"] = [_linha(dia) for dia in dias[1 + NA_LISTA :]]
            contexto["vazio"] = not dias
    return render(request, "escala/pagina.html", contexto)
