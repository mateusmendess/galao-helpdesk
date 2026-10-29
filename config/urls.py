from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView

from core import views as core_views
from escala import views as escala_views
from fila import views as fila_views
from usuarios.forms import EntrarForm
from usuarios.views import TrocarSenhaView

# Nome do sistema no cabecalho e na aba do /admin/ (index_title fica o padrao).
admin.site.site_header = "Help Desk Equipe"
admin.site.site_title = "Help Desk Equipe"

urlpatterns = [
    path("", core_views.home, name="home"),
    path("saude/", core_views.saude, name="saude"),
    # Navegadores pedem /favicon.ico sozinhos, mesmo sem login.
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("img/favicon.ico"), permanent=True),
        name="favicon",
    ),
    path("trocas/", fila_views.historico, name="historico"),
    path("trocas/nova/", fila_views.registrar, name="registrar_troca"),
    path("escala/", escala_views.pagina, name="escala"),
    path("escala/trocar/", escala_views.trocar, name="escala_trocar"),
    path("escala/regras/", escala_views.regras, name="escala_regras"),
    path("escala/trocas/", escala_views.trocas, name="escala_trocas"),
    path(
        "escala/trocas/<int:pk>/desfazer/",
        escala_views.desfazer,
        name="escala_desfazer",
    ),
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
