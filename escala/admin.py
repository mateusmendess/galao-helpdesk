from django.contrib import admin

from fila.admin import MensagensNoFeminino

from .models import ConfiguracaoEscala, SabadoDuasPessoas, SabadoSemEscala


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
