from django.shortcuts import redirect

# Rotas que quem precisa trocar a senha ainda pode abrir. Compara o nome
# completo (com namespace): "admin:password_change" NAO entra, porque troca a
# senha sem desligar a marca.
ROTAS_LIBERADAS = {"password_change", "password_change_done", "logout", "saude"}


class TrocaDeSenhaObrigatoriaMiddleware:
    """Leva para "Trocar senha" quem entrou com senha provisoria."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        usuario = request.user
        if not (usuario.is_authenticated and usuario.precisa_trocar_senha):
            return None
        if request.resolver_match.view_name in ROTAS_LIBERADAS:
            return None
        return redirect("password_change")
