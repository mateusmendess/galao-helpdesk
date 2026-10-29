from datetime import date

from django import forms

from fila.forms import CAMPO
from fila.regras import nome_de_exibicao

from .models import TrocaSabado

ROTULO_TURNO = dict(TrocaSabado.Turno.choices)
# Opcao que sumiu da lista (outra troca mudou o turno enquanto a pessoa via).
MUDOU = "A escala mudou enquanto você preenchia."


def opcao(item, turno):
    """(valor, rotulo) de um turno: "AAAA-MM-DD|turno|id" e "DD/MM · manhã · Fulano"."""
    dono = item.dono(turno)
    valor = f"{item.dia.data.isoformat()}|{turno}|{dono.pk}"
    rotulo = f"{item.dia.data:%d/%m} · {ROTULO_TURNO[turno]} · {nome_de_exibicao(dono)}"
    return valor, rotulo


def ler_opcao(valor):
    """(data, turno, id do dono que a pessoa viu)."""
    data, turno, dono = valor.split("|")
    return date.fromisoformat(data), turno, int(dono)


class TrocarSabadoForm(forms.Form):
    meu = forms.ChoiceField(
        label="Meu sábado",
        widget=forms.Select(attrs={"class": CAMPO}),
        error_messages={"required": "Escolha o seu sábado.", "invalid_choice": MUDOU},
    )
    outro = forms.ChoiceField(
        label="Sábado que vou assumir",
        widget=forms.Select(attrs={"class": CAMPO}),
        error_messages={
            "required": "Escolha o sábado que vai assumir.",
            "invalid_choice": MUDOU,
        },
    )
    tipo = forms.ChoiceField(
        label="Tipo",
        choices=TrocaSabado.Tipo.choices,
        initial=TrocaSabado.Tipo.COMBINADA,
        required=False,
        widget=forms.Select(attrs={"class": CAMPO}),
    )

    def __init__(self, *args, meus, outros, admin, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["meu"].choices = [("", "Escolha um sábado"), *meus]
        self.fields["outro"].choices = [("", "Escolha um sábado"), *outros]
        if admin:
            self.fields["outro"].label = "Sábado da outra pessoa"
        else:
            del self.fields["tipo"]

    def clean(self):
        dados = super().clean()
        for campo in ("meu", "outro"):
            if dados.get(campo):
                dados[campo] = ler_opcao(dados[campo])
        return dados
