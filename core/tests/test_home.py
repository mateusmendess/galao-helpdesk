from django.urls import reverse


def test_home_responde_com_template_e_titulo(client):
    resposta = client.get(reverse("home"))

    assert resposta.status_code == 200
    assert "core/home.html" in [t.name for t in resposta.templates]
    assert "Troca do Galão" in resposta.content.decode()
