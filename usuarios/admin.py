from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth.admin import UserAdmin
from django.db.models import F

from .forms import UsuarioAlteracaoForm, UsuarioCriacaoForm
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioAlteracaoForm
    add_form = UsuarioCriacaoForm

    list_display = (
        "email",
        "first_name",
        "ordem",
        "ordem_escala",
        "is_active",
        "eh_admin",
    )
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    # Quem esta na fila primeiro (1, 2, 3...), quem esta sem ordem por ultimo.
    ordering = (F("ordem").asc(nulls_last=True), "email")

    fieldsets = (
        (None, {"fields": ("email", "password", "precisa_trocar_senha")}),
        (
            "Dados pessoais",
            {"fields": ("first_name", "last_name", "ordem", "ordem_escala")},
        ),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "ordem",
                    "ordem_escala",
                    "usable_password",
                    "password1",
                    "password2",
                    "precisa_trocar_senha",
                ),
            },
        ),
    )

    def user_change_password(self, request, id, form_url=""):
        # Usa a tela "alterar senha" do Django como esta e, se a senha de OUTRA
        # pessoa mudou de fato, liga a troca obrigatoria no proximo acesso.
        # A propria senha nao liga (o admin se trancaria fora do painel).
        antes = self.get_object(request, unquote(id))
        resposta = super().user_change_password(request, id, form_url)
        if request.method == "POST" and antes.pk != request.user.pk:
            depois = self.get_object(request, unquote(id))
            if depois.password != antes.password and depois.has_usable_password():
                depois.precisa_trocar_senha = True
                depois.save(update_fields=["precisa_trocar_senha"])
        return resposta

    @admin.display(boolean=True, description="admin")
    def eh_admin(self, obj):
        return obj.is_staff and obj.is_superuser
