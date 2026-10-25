from django.contrib.auth.views import PasswordChangeView

from .forms import TrocarSenhaForm


class TrocarSenhaView(PasswordChangeView):
    """Troca de senha do Django que tambem desliga a troca obrigatoria."""

    form_class = TrocarSenhaForm

    def form_valid(self, form):
        resposta = super().form_valid(form)
        usuario = form.user
        if usuario.precisa_trocar_senha:
            usuario.precisa_trocar_senha = False
            usuario.save(update_fields=["precisa_trocar_senha"])
        return resposta
