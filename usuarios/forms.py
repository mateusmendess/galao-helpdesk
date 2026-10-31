from django.contrib.admin.forms import AdminAuthenticationForm
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
        fields = (
            "email",
            "matricula",
            "first_name",
            "ordem",
            "ordem_escala",
            "precisa_trocar_senha",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Conta nova vem com senha provisoria: troca obrigatoria no 1o acesso.
        self.fields["precisa_trocar_senha"].initial = True


class UsuarioAlteracaoForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


class EntrarForm(AuthenticationForm):
    """Login por matricula ou e-mail, com uma so mensagem de erro."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail, matrícula ou senha incorretos.",
        "bloqueado": "Muitas tentativas de entrada. Tente de novo em alguns minutos.",
    }

    def clean(self):
        # Checa o bloqueio antes de conferir a senha: com a pessoa bloqueada,
        # nem a senha certa entra, e a tentativa nao e registrada.
        identificador = self.cleaned_data.get("username")
        if identificador and esta_bloqueado(identificador):
            raise ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        return super().clean()


class EntrarPainelForm(AdminAuthenticationForm):
    """Login do /admin/: mesmo rotulo e mesma mensagem de erro do /entrar/."""

    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": EntrarForm.error_messages["invalid_login"],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail ou matrícula"


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

    def validate_password_for_user(self, user, password_field_name="new_password2"):
        # O Django valida (e mostra o erro) na confirmacao; aqui o erro de
        # senha fraca vai para o campo "Nova senha". A regra e a mesma.
        super().validate_password_for_user(user, "new_password1")
