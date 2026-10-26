from django import forms
from django.contrib.auth import get_user_model
from django.db.models import F

from .regras import nome_de_exibicao

# Mesmas classes dos campos de templates/registration/login.html (o Tailwind so le
# templates/): 48 px de altura, borda #7F8F97 e o foco global na tinta.
CAMPO = (
    "mt-1.5 block min-h-12 w-full rounded-[10px] border bg-white px-3 py-2.5 "
    "text-base text-texto border-[#7f8f97]"
)
# Com erro, so a cor da borda muda (border-erro ja existe nos templates).
CAMPO_COM_ERRO = CAMPO.replace("border-[#7f8f97]", "border-erro")

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

    def full_clean(self):
        super().full_clean()
        # O Django ja poe aria-invalid no campo com erro; aqui so a borda.
        for nome in ("executor", "observacao"):
            if nome in self.errors:
                self.fields[nome].widget.attrs["class"] = CAMPO_COM_ERRO

    def executor_escolhido(self):
        if self.cleaned_data["quem"] == FUI_EU:
            return self.usuario
        return self.cleaned_data["executor"]
