from django.contrib.auth.forms import (
    AdminUserCreationForm,
    AuthenticationForm,
    PasswordChangeForm,
    UserChangeForm,
)
from django.core.exceptions import ValidationError

from .limite import esta_bloqueado
from .models import Usuario


class UsuarioCriacaoForm(AdminUserCreationForm):
    """Formulario de 'adicionar usuario' do /admin/, com e-mail no lugar do nome."""

    class Meta:
        model = Usuario
        fields = ("email", "first_name", "ordem", "precisa_trocar_senha")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Conta nova vem com senha provisoria: troca obrigatoria no 1o acesso.
        self.fields["precisa_trocar_senha"].initial = True


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


class TrocarSenhaForm(PasswordChangeForm):
    """Troca da propria senha; a nova precisa ser diferente da atual."""

    error_messages = {
        **PasswordChangeForm.error_messages,
        "senha_igual": "A nova senha precisa ser diferente da atual.",
    }

    def clean_new_password1(self):
        nova = self.cleaned_data.get("new_password1")
        # So compara se a senha atual ja foi conferida (old_password vem antes);
        # senao este erro diria se um chute e a senha atual sem saber a atual.
        senha_atual_ok = "old_password" in self.cleaned_data
        if nova and senha_atual_ok and self.user.check_password(nova):
            raise ValidationError(
                self.error_messages["senha_igual"], code="senha_igual"
            )
        return nova
