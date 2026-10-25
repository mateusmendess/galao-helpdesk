from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import F

from .models import Rodada, Troca
from .regras import de_quem_e_a_vez, nome_de_exibicao, rodada_atual


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
    # Adicionar e consultar; corrigir ou apagar fica para o modulo 4.
    list_display = ("rodada", "nome_do_titular", "nome_do_executor", "data_hora")
    list_filter = ("rodada",)
    list_select_related = ("rodada", "titular", "executor")
    fields = ("titular", "executor", "data_hora", "observacao")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_fields(self, request, obj=None):
        # Na consulta de uma troca ja gravada, mostra tambem os campos automaticos.
        if obj is not None:
            return ("rodada",) + self.fields + ("registrada_por",)
        return self.fields

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
            kwargs["queryset"] = ativos.order_by(
                F("ordem").asc(nulls_last=True), "email"
            )
        campo = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("titular", "executor", "registrada_por"):
            campo.label_from_instance = nome_de_exibicao
        return campo

    def save_model(self, request, obj, form, change):
        if not obj.rodada_id:
            obj.rodada = rodada_atual()
        obj.registrada_por = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="titular", ordering="titular__first_name")
    def nome_do_titular(self, obj):
        return nome_de_exibicao(obj.titular)

    @admin.display(description="executor", ordering="executor__first_name")
    def nome_do_executor(self, obj):
        return nome_de_exibicao(obj.executor)
