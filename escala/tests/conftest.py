from datetime import date, datetime, time
from unittest import mock

import pytest
from django.utils import timezone

# Sabados de referencia (ficticios): o inicio da escala e o seguinte.
SABADO = date(2026, 12, 5)
PROXIMO_SABADO = date(2026, 12, 12)


@pytest.fixture
def hoje():
    """Troca a hora da escala (patch em escala.datas.agora): hoje(date(...))
    vale meio-dia local; hoje(date(...), time(16, 59)) escolhe a hora."""
    with mock.patch("escala.datas.agora") as falso:

        def _hoje(dia, hora=time(12, 0)):
            falso.return_value = timezone.make_aware(datetime.combine(dia, hora))
            return dia

        _hoje(date(2026, 11, 28))
        yield _hoje
