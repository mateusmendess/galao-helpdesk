from datetime import date
from unittest import mock

import pytest

# Sabados de referencia (ficticios): o inicio da escala e o seguinte.
SABADO = date(2026, 12, 5)
PROXIMO_SABADO = date(2026, 12, 12)


@pytest.fixture
def hoje():
    """Troca a data de hoje da escala: hoje(date(...))."""
    with mock.patch("escala.datas.hoje") as falso:

        def _hoje(dia):
            falso.return_value = dia
            return dia

        _hoje(date(2026, 11, 28))
        yield _hoje
