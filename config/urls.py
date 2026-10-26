from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views as core_views
from fila import views as fila_views
from usuarios.forms import EntrarForm
from usuarios.views import TrocarSenhaView

urlpatterns = [
    path("", core_views.home, name="home"),
    path("saude/", core_views.saude, name="saude"),
    path("trocas/", fila_views.historico, name="historico"),
    path("trocas/nova/", fila_views.registrar, name="registrar_troca"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(authentication_form=EntrarForm),
        name="login",
    ),
    # LogoutView so aceita POST (GET devolve 405).
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    # So a troca de senha; sem "esqueci a senha" (nada de auth.urls inteiro).
    path("senha/trocar/", TrocarSenhaView.as_view(), name="password_change"),
    path(
        "senha/trocada/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("admin/", admin.site.urls),
]
