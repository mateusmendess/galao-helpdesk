from django.contrib.auth.forms import (
    AdminUserCreationForm,
    AuthenticationForm,
    UserChangeForm,
)
from django.core.exceptions import ValidationError

from .limite import esta_bloqueado
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
        "bloqueado": "Muitas tentativas de entrada. Tente de novo em alguns minutos.",
    }

    def clean(self):
        # Checa o bloqueio antes de conferir a senha: com o e-mail bloqueado,
        # nem a senha certa entra, e a tentativa nao e registrada.
        email = self.cleaned_data.get("username")
        if email and esta_bloqueado(email):
            raise ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        return super().clean()
