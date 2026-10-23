from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views as core_views
from usuarios.forms import EntrarForm

urlpatterns = [
    path("", core_views.home, name="home"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(authentication_form=EntrarForm),
        name="login",
    ),
    # LogoutView so aceita POST (GET devolve 405).
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
]
