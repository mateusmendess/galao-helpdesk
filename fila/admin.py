from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.shortcuts import redirect
from django.utils import timezone

from .models import Ausencia, Rodada, Troca
from .regras import (
    TrocaNaoPodeSerApagada,
    apagar_troca,
    de_quem_e_a_vez,
    nome_de_exibicao,
    pode_apagar_troca,
    rodada_atual,
)

ORDEM_DOS_USUARIOS = (F("ordem").asc(nulls_last=True), "email")


@admin.register(Rodada)
class RodadaAdmin(admin.ModelAdmin):
    # So consulta: rodadas abrem e fecham sozinhas.
    list_display = ("numero", "aberta_em", "fechada_em")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Troca)
class TrocaAdmin(admin.ModelAdmin):
    # Adicionar; numa troca ja gravada, corrigir so executor e observacao, e
    # apagar so pela regra de pode_apagar_troca (uma por vez).
    list_display = (
        "rodada",
        "nome_do_titular",
        "nome_do_executor",
        "data_hora",
        "nome_de_quem_registrou",
    )
    list_filter = ("rodada",)
    list_select_related = ("rodada", "titular", "executor", "registrada_por")
    fields = ("titular", "executor", "data_hora", "observacao")
    campos_da_correcao = (
        "rodada",
        "nome_do_titular",
        "executor",
        "data_hora",
        "observacao",
        "nome_de_quem_registrou",
    )

    def get_fields(self, request, obj=None):
        if obj is not None:
            return self.campos_da_correcao
        return self.fields

    def get_readonly_fields(self, request, obj=None):
        # Titular, rodada, data e quem registrou nunca mudam depois de gravados.
        if obj is not None:
            return ("rodada", "nome_do_titular", "data_hora", "nome_de_quem_registrou")
        return ()

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is not None and "executor" in form.base_fields:
            # Ativos e o executor atual (mesmo se desativado depois), para dar
            # para corrigir so a observacao.
            form.base_fields["executor"].queryset = (
                get_user_model()
                .objects.filter(Q(is_active=True) | Q(pk=obj.executor_id))
                .order_by(*ORDEM_DOS_USUARIOS)
            )
        return form

    def get_actions(self, request, action_location=admin.ActionLocation.CHANGE_LIST):
        # Sem "apagar selecionadas": troca se apaga uma por vez.
        acoes = super().get_actions(request, action_location=action_location)
        acoes.pop("delete_selected", None)
        return acoes

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return False
        return super().has_delete_permission(request, obj) and pode_apagar_troca(obj)

    def delete_model(self, request, obj):
        reaberta = apagar_troca(obj)
        if reaberta is not None:
            messages.info(request, f"A rodada {reaberta.numero} foi reaberta.")

    def delete_view(self, request, object_id, extra_context=None):
        # A regra e conferida de novo dentro de apagar_troca, no POST. Se nao
        # vale mais, a transacao do Django e desfeita (inclusive o registro no
        # historico do admin) e nada e apagado.
        try:
            return super().delete_view(request, object_id, extra_context)
        except TrocaNaoPodeSerApagada as erro:
            messages.error(request, f"Não foi possível apagar: {erro}")
            return redirect("admin:fila_troca_changelist")

    def get_changeform_initial_data(self, request):
        # Abre com a pessoa da vez nos dois campos (sem cobertura).
        inicial = super().get_changeform_initial_data(request)
        vez = de_quem_e_a_vez()
        if vez is not None:
            inicial.setdefault("titular", vez.pk)
            inicial.setdefault("executor", inicial["titular"])
        return inicial

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ("titular", "executor"):
            ativos = get_user_model().objects.filter(is_active=True)
            if db_field.name == "titular":
                ativos = ativos.filter(ordem__isnull=False)
            kwargs["queryset"] = ativos.order_by(*ORDEM_DOS_USUARIOS)
        campo = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("titular", "executor", "registrada_por"):
            campo.label_from_instance = nome_de_exibicao
        if db_field.name == "executor":
            campo.help_text = (
                "Se foi o próprio titular quem trocou, escolha o mesmo nome do "
                "titular. Escolha outro nome só quando houve cobertura."
            )
        return campo

    def save_model(self, request, obj, form, change):
        if not change:
            obj.rodada = rodada_atual()
            obj.registrada_por = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="titular", ordering="titular__first_name")
    def nome_do_titular(self, obj):
        return nome_de_exibicao(obj.titular)

    @admin.display(description="executor", ordering="executor__first_name")
    def nome_do_executor(self, obj):
        return nome_de_exibicao(obj.executor)

    @admin.display(description="registrada por", ordering="registrada_por__first_name")
    def nome_de_quem_registrou(self, obj):
        return nome_de_exibicao(obj.registrada_por)


@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
    list_display = ("nome_da_pessoa", "inicio", "fim", "situacao")
    list_filter = ("usuario",)
    list_select_related = ("usuario",)
    fields = ("usuario", "inicio", "fim")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "usuario" in form.base_fields:
            # Quem esta na fila e, ao editar, a pessoa da ausencia (mesmo se
            # desativada ou tirada da fila depois).
            na_fila = Q(is_active=True, ordem__isnull=False)
            if obj is not None:
                na_fila |= Q(pk=obj.usuario_id)
            campo = form.base_fields["usuario"]
            campo.queryset = (
                get_user_model().objects.filter(na_fila).order_by(*ORDEM_DOS_USUARIOS)
            )
            campo.label_from_instance = nome_de_exibicao
        return form

    @admin.display(description="pessoa", ordering="usuario__first_name")
    def nome_da_pessoa(self, obj):
        return nome_de_exibicao(obj.usuario)

    @admin.display(description="situação")
    def situacao(self, obj):
        hoje = timezone.localdate()
        if obj.inicio > hoje:
            return "futura"
        if obj.fim is not None and obj.fim < hoje:
            return "encerrada"
        return "ausente hoje"
