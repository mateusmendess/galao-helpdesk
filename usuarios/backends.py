from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from .limite import esta_bloqueado


class LimiteTentativasBackend(ModelBackend):
    """ModelBackend que aceita matricula ou e-mail e recusa quem esta bloqueado.

    Vale para /entrar/ e para /admin/login/, que passam por authenticate().
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        Usuario = get_user_model()
        identificador = username
        if identificador is None:
            identificador = kwargs.get(Usuario.USERNAME_FIELD)
        if identificador and esta_bloqueado(identificador):
            # authenticate() para nos backends e envia user_login_failed.
            raise PermissionDenied
        if identificador:
            # Matricula de alguem vira o e-mail dessa pessoa; o resto (senha,
            # inativo, quem nao existe) segue pelo ModelBackend como antes.
            try:
                identificador = Usuario.objects.por_identificador(identificador).email
            except Usuario.DoesNotExist:
                pass
        return super().authenticate(
            request, username=identificador, password=password, **kwargs
        )
