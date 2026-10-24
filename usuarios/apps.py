from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    name = "usuarios"

    def ready(self):
        # Conecta os receivers do limite de tentativas de login.
        from . import sinais  # noqa: F401
