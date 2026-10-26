from django import forms
from django.contrib.auth import get_user_model
from django.db.models import F

from .regras import nome_de_exibicao

# Mesmas classes dos campos de templates/registration (o Tailwind so le templates/).
CAMPO = (
    "mt-1 block w-full rounded-lg border border-gray-500 bg-white px-3 py-2 "
    "focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/40"
)

FUI_EU = "eu"
OUTRA_PESSOA = "outra"


class RegistrarTrocaForm(forms.Form):
    # So o que a pessoa VIU na tela; a vez de verdade e conferida no servidor.
    titular = forms.IntegerField(widget=forms.HiddenInput)
    quem = forms.ChoiceField(
        label="Quem trocou o galão?",
        choices=[(FUI_EU, "Fui eu"), (OUTRA_PESSOA, "Foi outra pessoa")],
        widget=forms.RadioSelect,
        initial=FUI_EU,
        error_messages={"required": "Diga quem trocou o galão."},
    )
    executor = forms.ModelChoiceField(
        label="Escolher pessoa",
        queryset=get_user_model().objects.none(),
        required=False,
        empty_label="Escolher pessoa",
        widget=forms.Select(attrs={"class": CAMPO}),
    )
    observacao = forms.CharField(
        label="Observação (opcional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": CAMPO}),
    )

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        campo = self.fields["executor"]
        campo.queryset = (
            get_user_model()
            .objects.filter(is_active=True)
            .exclude(pk=usuario.pk)
            .order_by(F("ordem").asc(nulls_last=True), "email")
        )
        campo.label_from_instance = nome_de_exibicao

    def clean(self):
        dados = super().clean()
        if dados.get("quem") == OUTRA_PESSOA and not dados.get("executor"):
            if "executor" not in self.errors:
                self.add_error("executor", "Escolha quem trocou o galão.")
        return dados

    def executor_escolhido(self):
        if self.cleaned_data["quem"] == FUI_EU:
            return self.usuario
        return self.cleaned_data["executor"]
