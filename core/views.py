from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe


@login_required
def home(request):
    return render(request, "core/home.html")


@require_safe
def saude(request):
    # Healthcheck do Railway: sem login, sem banco, so GET/HEAD.
    return HttpResponse("ok", content_type="text/plain")
