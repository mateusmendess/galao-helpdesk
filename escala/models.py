from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from . import datas

DATA_NAO_E_SABADO = "A data precisa ser um sábado."
SABADO_JA_PASSOU = "Esse sábado já passou e não pode mais mudar."
SABADO = 5  # date.weekday(): segunda = 0 ... sabado = 5
ESCALA_JA_COMECOU = (
    "A escala já começou: o início e o primeiro da fila não podem mais mudar."
)


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
        # Com um sabado ja congelado, mudar o ponto de partida reescreveria a
        # historia: o inicio e o primeiro ficam travados.
        if SabadoFechado.objects.exists():
            gravada = ConfiguracaoEscala.objects.filter(pk=1).first()
            if gravada is not None and (
                gravada.inicio != self.inicio or gravada.primeiro_id != self.primeiro_id
            ):
                raise ValidationError(ESCALA_JA_COMECOU)

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
    """Base dos sabados cadastrados pelo admin: so sabado que ainda nao
    terminou, e a mesma data nao pode estar nos dois cadastros."""

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
        # Terminou = depois das 17h do proprio sabado.
        return datas.sabado_terminou(self.data)

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


class SabadoFechado(models.Model):
    """Sabado que ja passou, gravado como a fila o escalou (nunca mais muda).

    Guarda so o resultado da fila; trocas entre pessoas ficam em outro modelo.
    """

    data = models.DateField("data", unique=True)
    manha = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="manhã",
    )
    tarde = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="tarde",
    )
    # Pelo PuladoNoSabado: quem foi pulado nao pode ser apagado (PROTECT).
    pulados = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="PuladoNoSabado",
        blank=True,
        related_name="+",
        verbose_name="pulados por ausência",
    )
    sem_escala = models.BooleanField("sem escala", default=False)
    motivo = models.CharField(
        "motivo", max_length=20, blank=True, choices=SabadoSemEscala.Motivo.choices
    )
    passa_para_proximo = models.BooleanField(
        "passou os escalados para o próximo sábado", default=False
    )
    vagas = models.PositiveSmallIntegerField(
        "vagas", validators=[MinValueValidator(1), MaxValueValidator(2)]
    )
    # Ordem na escala da ultima pessoa vista (escalada ou pulada); 0 = antes
    # da primeira.
    cursor_depois = models.PositiveIntegerField("cursor depois")
    fechado_em = models.DateTimeField("fechado em", default=timezone.now)

    class Meta:
        verbose_name = "sábado fechado"
        verbose_name_plural = "sábados fechados"
        ordering = ["data"]

    def __str__(self):
        return f"{self.data:%d/%m/%Y}"


class PuladoNoSabado(models.Model):
    """Quem foi pulado por ausencia num sabado gravado."""

    fechado = models.ForeignKey(
        SabadoFechado, on_delete=models.CASCADE, verbose_name="sábado"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="pessoa",
    )

    class Meta:
        verbose_name = "pulado no sábado"
        verbose_name_plural = "pulados no sábado"
        constraints = [
            models.UniqueConstraint(
                fields=["fechado", "usuario"], name="pulado_uma_vez_por_sabado"
            ),
        ]

    def __str__(self):
        from fila.regras import nome_de_exibicao

        return f"{nome_de_exibicao(self.usuario)} em {self.fechado}"


class TrocaSabado(models.Model):
    """Duas pessoas trocam turnos de sabado (a fila nao muda).

    Efeito: (data_a, turno_a) passa a ser de pessoa_b e (data_b, turno_b)
    passa a ser de pessoa_a. Ativa = desfeita_em vazio. Nunca se apaga.
    """

    class Turno(models.TextChoices):
        MANHA = "manha", "manhã"
        TARDE = "tarde", "tarde"

    class Tipo(models.TextChoices):
        COMBINADA = "combinada", "Combinada"
        EMERGENCIA = "emergencia", "Emergência"

    pessoa_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="pessoa A",
    )
    data_a = models.DateField("data de A")
    turno_a = models.CharField("turno de A", max_length=5, choices=Turno.choices)
    pessoa_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="pessoa B",
    )
    data_b = models.DateField("data de B")
    turno_b = models.CharField("turno de B", max_length=5, choices=Turno.choices)
    tipo = models.CharField(
        "tipo", max_length=10, choices=Tipo.choices, default=Tipo.COMBINADA
    )
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="registrada por",
    )
    registrada_em = models.DateTimeField("registrada em", default=timezone.now)
    desfeita_em = models.DateTimeField("desfeita em", null=True, blank=True)
    desfeita_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="desfeita por",
    )

    class Meta:
        verbose_name = "troca de sábado"
        verbose_name_plural = "trocas de sábado"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(pessoa_a=models.F("pessoa_b")),
                name="troca_sabado_pessoas_diferentes",
            ),
            models.CheckConstraint(
                condition=~models.Q(data_a=models.F("data_b")),
                name="troca_sabado_datas_diferentes",
            ),
        ]

    def __str__(self):
        return f"{self.data_a:%d/%m} ⇄ {self.data_b:%d/%m}"

    @property
    def ativa(self):
        return self.desfeita_em is None
