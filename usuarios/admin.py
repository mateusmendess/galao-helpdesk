from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import F

from .forms import UsuarioAlteracaoForm, UsuarioCriacaoForm
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioAlteracaoForm
    add_form = UsuarioCriacaoForm

    list_display = ("email", "first_name", "ordem", "is_active", "eh_admin")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    # Quem esta na fila primeiro (1, 2, 3...), quem esta sem ordem por ultimo.
    ordering = (F("ordem").asc(nulls_last=True), "email")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("first_name", "last_name", "ordem")}),
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
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    @admin.display(boolean=True, description="admin")
    def eh_admin(self, obj):
        return obj.is_staff and obj.is_superuser
