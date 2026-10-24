from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from .limite import esta_bloqueado


class LimiteTentativasBackend(ModelBackend):
    """ModelBackend que recusa o e-mail bloqueado antes de conferir a senha.

    Vale para /entrar/ e para /admin/login/, que passam por authenticate().
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username
        if email is None:
            email = kwargs.get(get_user_model().USERNAME_FIELD)
        if email and esta_bloqueado(email):
            # authenticate() para nos backends e envia user_login_failed.
            raise PermissionDenied
        return super().authenticate(
            request, username=username, password=password, **kwargs
        )
