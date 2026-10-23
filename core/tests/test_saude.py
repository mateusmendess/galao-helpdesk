import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_saude_responde_ok_sem_login(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        resposta = client.get(reverse("saude"))

    assert resposta.status_code == 200
    assert resposta.content == b"ok"
    assert resposta["Content-Type"].startswith("text/plain")


def test_saude_aceita_head(client):
    assert client.head(reverse("saude")).status_code == 200


def test_saude_recusa_post(client):
    assert client.post(reverse("saude")).status_code == 405
