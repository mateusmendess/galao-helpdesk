from django.utils.cache import add_never_cache_headers


class SemCacheParaLogados:
    """Pede ao navegador para nao guardar as paginas de quem esta logado.

    Assim, depois de "Sair", o "voltar" do navegador nao mostra a tela antiga.
    A entrada (/entrar/) e o logout ja vem do Django com never_cache; a pagina
    publica, o /saude/ e os estaticos (WhiteNoise, antes daqui) nao mudam.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
