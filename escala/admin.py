from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from fila.admin import MensagensNoFeminino

from .models import (
    ConfiguracaoEscala,
    PuladoNoSabado,
    SabadoDuasPessoas,
    SabadoFechado,
    SabadoSemEscala,
    TrocaSabado,
)
from .trocas import desfazer_troca, situacao


@admin.register(ConfiguracaoEscala)
class ConfiguracaoEscalaAdmin(MensagensNoFeminino, admin.ModelAdmin):
    # Uma linha so: adicionar enquanto nao existe; nunca apagar.
    list_display = ("inicio", "primeiro")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not (
            ConfiguracaoEscala.objects.exists()
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        # Depois do primeiro sabado congelado, o ponto de partida nao muda.
        if obj is not None and SabadoFechado.objects.exists():
            return ("inicio", "primeiro")
        return ()


class SabadoCadastradoAdmin(admin.ModelAdmin):
    # Sabado que ja passou fica so para consulta.
    ordering = ("data",)

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.ja_passou():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.ja_passou():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(SabadoSemEscala)
class SabadoSemEscalaAdmin(SabadoCadastradoAdmin):
    list_display = ("data", "motivo", "passa_para_proximo")


@admin.register(SabadoDuasPessoas)
class SabadoDuasPessoasAdmin(SabadoCadastradoAdmin):
    list_display = ("data",)


class PuladoNoSabadoInline(admin.TabularInline):
    model = PuladoNoSabado
    extra = 0
    verbose_name_plural = "pulados por ausência"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SabadoFechado)
class SabadoFechadoAdmin(admin.ModelAdmin):
    # So consulta: a fila grava sozinha os sabados que passaram.
    list_display = ("data", "manha", "tarde", "sem_escala", "vagas")
    inlines = [PuladoNoSabadoInline]
    list_select_related = ("manha", "tarde")
    ordering = ("-data",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TrocaSabado)
class TrocaSabadoAdmin(MensagensNoFeminino, admin.ModelAdmin):
    # So consulta; a unica mudanca e desfazer (a troca nunca se apaga).
    list_display = (
        "data_a",
        "data_b",
        "pessoa_a",
        "pessoa_b",
        "tipo",
        "situacao_da_troca",
        "registrada_por",
    )
    list_select_related = ("pessoa_a", "pessoa_b", "registrada_por", "desfeita_por")
    actions = ["desfazer_selecionadas"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="situação")
    def situacao_da_troca(self, obj):
        return situacao(obj)

    @admin.action(description="Desfazer trocas selecionadas")
    def desfazer_selecionadas(self, request, queryset):
        # Da mais recente para a mais antiga: a regra pede desfazer antes a
        # troca mais recente que mexe no mesmo sabado.
        desfeitas = 0
        for troca in queryset.order_by("-id"):
            try:
                desfazer_troca(troca, request.user)
            except ValidationError as erro:
                self.message_user(
                    request,
                    f"Troca {troca} não foi desfeita: {' '.join(erro.messages)}",
                    messages.ERROR,
                )
            else:
                desfeitas += 1
        if desfeitas:
            self.message_user(
                request, f"Trocas desfeitas: {desfeitas}.", messages.SUCCESS
            )
