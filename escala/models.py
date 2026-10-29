from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from . import datas

DATA_NAO_E_SABADO = "A data precisa ser um sábado."
SABADO_JA_PASSOU = "Esse sábado já passou e não pode mais mudar."
SABADO = 5  # date.weekday(): segunda = 0 ... sabado = 5


class ConfiguracaoEscala(models.Model):
    """Configuracao unica da escala (sempre pk=1): quando comeca e com quem."""

    inicio = models.DateField("primeiro sábado da escala no sistema")
    primeiro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="primeiro da fila no início",
    )

    class Meta:
        verbose_name = "configuração da escala"
        verbose_name_plural = "configuração da escala"

    def __str__(self):
        return "Configuração da escala"

    def clean(self):
        super().clean()
        erros = {}
        if self.inicio and self.inicio.weekday() != SABADO:
            erros["inicio"] = "A data de início precisa ser um sábado."
        if self.primeiro_id and not (
            self.primeiro.is_active and self.primeiro.ordem_escala is not None
        ):
            erros["primeiro"] = "Escolha uma pessoa ativa que tenha posição na escala."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # Uma linha so: qualquer gravacao vai para a pk=1 (e sobrescreve).
        self.pk = 1
        kwargs.pop("force_insert", None)
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        """A configuracao, ou None se o admin ainda nao ligou a escala."""
        return cls.objects.filter(pk=1).select_related("primeiro").first()


class SabadoCadastrado(models.Model):
    """Base dos sabados cadastrados pelo admin: so sabado, de hoje em diante,
    e a mesma data nao pode estar nos dois cadastros."""

    data = models.DateField("data", unique=True)

    class Meta:
        abstract = True
        ordering = ["data"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y}"

    def outro_cadastro(self):
        """(modelo, mensagem) do outro cadastro de sabados."""
        raise NotImplementedError

    def ja_passou(self):
        return self.data < datas.hoje()

    def clean(self):
        super().clean()
        if self.data is None:
            return
        if self.data.weekday() != SABADO:
            raise ValidationError({"data": DATA_NAO_E_SABADO})
        if self.ja_passou():
            raise ValidationError({"data": SABADO_JA_PASSOU})
        outro, mensagem = self.outro_cadastro()
        if outro.objects.filter(data=self.data).exists():
            raise ValidationError({"data": mensagem})


class SabadoSemEscala(SabadoCadastrado):
    class Motivo(models.TextChoices):
        FERIADO = "feriado", "Feriado"
        IMPREVISTO = "imprevisto", "Imprevisto"
        OUTRO = "outro", "Outro"

    motivo = models.CharField(
        "motivo", max_length=20, choices=Motivo.choices, default=Motivo.FERIADO
    )
    passa_para_proximo = models.BooleanField(
        "Passar os escalados para o próximo sábado",
        default=True,
        help_text=(
            "Marcado: quem estava na vez vai para o próximo sábado. "
            "Desmarcado: a fila segue e a vez deles é gasta."
        ),
    )

    class Meta(SabadoCadastrado.Meta):
        verbose_name = "sábado sem escala"
        verbose_name_plural = "sábados sem escala"

    def outro_cadastro(self):
        return (
            SabadoDuasPessoas,
            "Este sábado já está cadastrado como sábado com 2 pessoas.",
        )


class SabadoDuasPessoas(SabadoCadastrado):
    data = models.DateField(
        "data",
        unique=True,
        help_text="Marque quando for preciso cobrir também a tarde.",
    )

    class Meta(SabadoCadastrado.Meta):
        verbose_name = "sábado com 2 pessoas"
        verbose_name_plural = "sábados com 2 pessoas"

    def outro_cadastro(self):
        return SabadoSemEscala, "Este sábado já está cadastrado como sábado sem escala."
