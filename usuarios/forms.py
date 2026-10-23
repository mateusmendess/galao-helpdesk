from django.contrib.auth.forms import (
    AdminUserCreationForm,
    AuthenticationForm,
    UserChangeForm,
)

from .models import Usuario


class UsuarioCriacaoForm(AdminUserCreationForm):
    """Formulario de 'adicionar usuario' do /admin/, com e-mail no lugar do nome."""

    class Meta:
        model = Usuario
        fields = ("email", "first_name", "ordem")


class UsuarioAlteracaoForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


class EntrarForm(AuthenticationForm):
    """Login por e-mail com mensagem de erro unica, sem dizer qual campo errou."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail ou senha incorretos.",
    }
