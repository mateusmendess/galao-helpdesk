from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from fila.regras import nome_de_exibicao

from . import datas
from .calculo import ConfiguracaoInvalida, calendario
from .forms import TrocarSabadoForm, opcao
from .models import ConfiguracaoEscala, SabadoSemEscala, TrocaSabado
from .trocas import (
    TURNOS,
    aplicar,
    desfazer_troca,
    eh_admin,
    pode_desfazer,
    registrar_troca,
    situacao,
    ultimo_dia_para_desfazer,
)

QUANTOS = 9  # destaque + 6 na lista + 2 no "Ver mais"
NA_LISTA = 6
PARA_TROCAR = 12  # sabados oferecidos em "Trocar de sabado"
TROCAS_POR_PAGINA = 30
MOTIVOS = dict(SabadoSemEscala.Motivo.choices)


def _linha(item, trocas_na_observacao=True):
    """Textos de um sabado da lista: nomes, observacoes e etiquetas. No
    destaque o "no lugar de" fica na linha do turno, nao na observacao."""
    dia = item.dia
    escalados = [nome_de_exibicao(u) for u in (dia.manha, dia.tarde) if u]
    observacoes = []
    if dia.sem_escala:
        nomes = f"Sem escala · {MOTIVOS.get(dia.motivo, dia.motivo)}"
        if dia.passa_para_proximo:
            proximo = dia.data + timedelta(days=7)
            observacoes.append(f"Quem estava na vez passa para {proximo:%d/%m}")
    else:
        nomes = " e ".join(escalados) or "ninguém disponível"
    for turno in TURNOS if trocas_na_observacao else ():
        original = item.no_lugar_de(turno)
        if original is None:
            continue
        lugar = f"no lugar de {nome_de_exibicao(original)}"
        atual = item.dono(turno)
        if dia.vagas == 2 and atual is not None:
            lugar = f"{nome_de_exibicao(atual)} {lugar}"
        observacoes.append(lugar)
    if dia.pulados:
        pulados = ", ".join(nome_de_exibicao(u) for u in dia.pulados)
        observacoes.append(f"Ausente, pulado: {pulados}")
    return {"dia": dia, "nomes": nomes, "observacoes": observacoes, "item": item}


def _turno(item, turno, eu):
    usuario = item.dono(turno)
    original = item.no_lugar_de(turno)
    return {
        "nome": nome_de_exibicao(usuario) if usuario else "",
        "voce": usuario is not None and usuario.pk == eu.pk,
        "no_lugar_de": nome_de_exibicao(original) if original else "",
    }


@login_required
@require_safe
def pagina(request):
    configuracao = ConfiguracaoEscala.obter()
    contexto = {"configuracao": configuracao}
    if configuracao is not None:
        contexto["antes_do_inicio"] = datas.hoje() < configuracao.inicio
        try:
            itens = aplicar(calendario(QUANTOS))
        except ConfiguracaoInvalida as erro:
            contexto["erro"] = str(erro)
        else:
            if itens:
                destaque = itens[0]
                contexto["destaque"] = {
                    **_linha(destaque, trocas_na_observacao=False),
                    "manha": _turno(destaque, "manha", request.user),
                    "tarde": _turno(destaque, "tarde", request.user),
                }
                contexto["lista"] = [_linha(i) for i in itens[1 : 1 + NA_LISTA]]
                contexto["mais"] = [_linha(i) for i in itens[1 + NA_LISTA :]]
            contexto["vazio"] = not itens
    return render(request, "escala/pagina.html", contexto)


def _opcoes(usuario, admin):
    """(meus, outros): turnos com dono dos proximos sabados. Membro: so data
    depois de hoje, os dele em "meus" e os dos outros em "outros"."""
    try:
        itens = aplicar(calendario(PARA_TROCAR))
    except ConfiguracaoInvalida:
        return [], []
    hoje = datas.hoje()
    meus, outros = [], []
    for item in itens:
        if item.dia.sem_escala or (not admin and item.dia.data <= hoje):
            continue
        for turno in TURNOS:
            dono = item.dono(turno)
            if dono is None:
                continue
            if admin:
                meus.append(opcao(item, turno))
                outros.append(opcao(item, turno))
            elif dono.pk == usuario.pk:
                meus.append(opcao(item, turno))
            else:
                outros.append(opcao(item, turno))
    return meus, outros


@login_required
def trocar(request):
    admin = eh_admin(request.user)
    meus, outros = _opcoes(request.user, admin)
    form = TrocarSabadoForm(request.POST or None, meus=meus, outros=outros, admin=admin)
    if request.method == "POST" and form.is_valid():
        data_a, turno_a, id_a = form.cleaned_data["meu"]
        data_b, turno_b, id_b = form.cleaned_data["outro"]
        pessoas = get_user_model().objects.in_bulk([id_a, id_b])
        try:
            if id_a not in pessoas or id_b not in pessoas:
                raise ValidationError("A escala mudou enquanto você preenchia.")
            troca = registrar_troca(
                pessoas[id_a],
                data_a,
                turno_a,
                pessoas[id_b],
                data_b,
                turno_b,
                por=request.user,
                tipo=form.cleaned_data.get("tipo") or None,
            )
        except ValidationError as erro:
            form.add_error(None, erro)
        else:
            messages.success(
                request,
                f"Troca registrada: {nome_de_exibicao(troca.pessoa_a)} ⇄ "
                f"{nome_de_exibicao(troca.pessoa_b)} ({troca.data_a:%d/%m} ⇄ "
                f"{troca.data_b:%d/%m}). Avise a equipe por e-mail.",
            )
            return redirect("escala_trocas")
    contexto = {"form": form, "sem_opcoes": not meus or not outros, "admin": admin}
    return render(request, "escala/trocar.html", contexto)


def _descrever(troca, usuario):
    return {
        "troca": troca,
        "situacao": situacao(troca),
        "pode_desfazer": pode_desfazer(troca, usuario),
        "ate": ultimo_dia_para_desfazer(troca),
    }


@login_required
@require_safe
def trocas(request):
    todas = TrocaSabado.objects.select_related(
        "pessoa_a", "pessoa_b", "registrada_por", "desfeita_por"
    ).order_by("-id")
    ativas = [
        _descrever(t, request.user)
        for t in todas.filter(desfeita_em__isnull=True)
        if situacao(t) == "ativa"
    ]
    pagina = Paginator(todas, TROCAS_POR_PAGINA).get_page(request.GET.get("pagina"))
    historico = [_descrever(t, request.user) for t in pagina.object_list]
    contexto = {
        "ativas": ativas,
        "historico": historico,
        "pagina": pagina,
        "admin": eh_admin(request.user),
    }
    return render(request, "escala/trocas.html", contexto)


@login_required
@require_POST
def desfazer(request, pk):
    troca = get_object_or_404(TrocaSabado, pk=pk)
    try:
        desfazer_troca(troca, request.user)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    else:
        messages.success(request, "Troca desfeita. Avise a equipe por e-mail.")
    return redirect("escala_trocas")


@login_required
@require_safe
def regras(request):
    return render(request, "escala/regras.html")
